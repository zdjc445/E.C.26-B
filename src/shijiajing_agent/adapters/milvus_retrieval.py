"""Milvus 混合召回适配器。

- dense 文本 + sparse 词法 + （可选）图像三个通道并行取 Top K，并集按融合分
  排序截断 union_limit。
- 每信号在当前候选集 min-max 归一化到 [0,1]；融合权重按文本/图片公式；
  缺失通道按可用权重重新归一化。
- 硬过滤生成 Milvus filter 表达式，与本地降级 ``offer_matches_hard_filters``
  同一语义（价格比较字段均为 ``price``）。
- Milvus 失败/超时/schema 不匹配 → 本地词法降级，``fallback_used=true``；
  本地快照也不可用 → 抛 ``RetrievalUnavailableError``。
- 图像通道只在图片可用且图像向量 provider 已配置时执行，缺失时如实不参与融合。
"""

from __future__ import annotations

import asyncio
import json
import random
from inspect import isawaitable
from typing import Any, cast

from shijiajing_agent.adapters.embeddings import UnavailableImageEmbedding
from shijiajing_agent.adapters.lexical import query_sparse_vector
from shijiajing_agent.adapters.local_retrieval import (
    LocalLexicalRetrievalAdapter,
    metadata_match,
)
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    HardFilters,
    ImageRef,
    Offer,
    RetrievalCandidate,
    RetrievalQuery,
)
from shijiajing_agent.errors import RetrievalUnavailableError
from shijiajing_agent.ports.milvus import MilvusClientPort, make_milvus_client
from shijiajing_agent.ports.models import ImageEmbeddingPort, TextEmbeddingPort
from shijiajing_agent.ports.observability import MetricsPort
from shijiajing_agent.ports.retrieval import RetrievalResult
from shijiajing_agent.rag_contracts import ChannelKind, ChannelResult, ChannelStatus

# 所有 Offer 标量字段 + 三个 JSON 属性字段。
_OUTPUT_FIELDS = [
    "offer_id",
    "platform",
    "source_product_id",
    "source_sku_id",
    "source_offer_id",
    "record_kind",
    "raw_category_path",
    "raw_attributes_json",
    "provenance",
    "source_revision",
    "source_content_hash",
    "availability",
    "price_basis",
    "source_updated_at",
    "data_version",
    "title",
    "normalized_title",
    "search_text",
    "search_text_hash",
    "category_id",
    "brand",
    "model",
    "same_item_key",
    "sku_key",
    "identity_attributes_json",
    "variant_attributes_json",
    "descriptive_attributes_json",
    "price",
    "original_price",
    "shipping_fee",
    "coupon_amount",
    "currency",
    "shop_id",
    "shop_name",
    "seller_type",
    "rating",
    "sales",
    "review_count",
    "delivery_days",
    "source_payload_ref",
]


def escape_milvus_string(value: str) -> str:
    """Milvus filter 表达式字符串转义（单引号包裹）。"""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_filter_expr(hf: HardFilters) -> str:
    """硬过滤 → Milvus filter 表达式。空过滤返回空字符串。"""
    parts: list[str] = []
    if hf.category_id:
        parts.append(f"category_id == {escape_milvus_string(hf.category_id)}")
    if hf.min_price is not None:
        parts.append(f"price >= {hf.min_price:g}")
    if hf.max_price is not None:
        parts.append(f"price <= {hf.max_price:g}")
    if hf.platforms:
        quoted = ", ".join(escape_milvus_string(p) for p in hf.platforms)
        parts.append(f"platform in [{quoted}]")
    if hf.min_rating is not None:
        parts.append(f"rating >= {hf.min_rating:g}")
    if hf.brand:
        parts.append(f"brand == {escape_milvus_string(hf.brand)}")
    if hf.model:
        parts.append(f"model == {escape_milvus_string(hf.model)}")
    return " && ".join(parts)


class MilvusHybridRetrievalAdapter:
    """Milvus 混合召回（ProductRetrievalPort 实现）。"""

    def __init__(
        self,
        settings: Settings,
        *,
        text_embeddings: TextEmbeddingPort,
        local_fallback: LocalLexicalRetrievalAdapter,
        image_embeddings: ImageEmbeddingPort | None = None,
        metrics: MetricsPort | None = None,
        client: MilvusClientPort | None = None,
    ) -> None:
        missing = [
            n
            for n in ("milvus_uri", "milvus_token", "milvus_collection")
            if not getattr(settings, n)
        ]
        if missing:
            raise ValueError(
                "Milvus 配置缺失，请设置环境变量："
                + ", ".join(f"SHIJIAJING_{n.upper()}" for n in missing)
            )
        self._settings = settings
        self._text_embeddings = text_embeddings
        self._image_embeddings = image_embeddings or UnavailableImageEmbedding()
        self._local = local_fallback
        self._metrics = metrics
        self._client = client  # 测试注入 FakeMilvusClient；None 时按配置构建
        self._closed = False

    async def setup(self) -> None:
        """Milvus 与 Embedding 客户端按首次检索惰性连接；此处统一完成生命周期契约。"""

    async def close(self) -> None:
        """关闭适配器持有的 Milvus、Embedding 与本地兜底资源。"""
        if self._closed:
            return
        self._closed = True
        first_error: BaseException | None = None
        seen: set[int] = set()
        for resource in (
            self._client,
            self._text_embeddings,
            self._image_embeddings,
            self._local,
        ):
            if resource is None or id(resource) in seen:
                continue
            seen.add(id(resource))
            close = getattr(resource, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if isawaitable(result):
                    await result
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    def _real_client(self) -> MilvusClientPort:
        if self._client is None:
            # 构造前已校验缺失项（__init__ 抛 ValueError）
            self._client = make_milvus_client(self._settings)
        return self._client

    async def search(
        self,
        query: RetrievalQuery,
        *,
        image: ImageRef | None = None,
        top_k: int = 100,
        union_limit: int = 200,
        category_names: dict[str, str] | None = None,
    ) -> RetrievalResult:
        try:
            return await self._search_milvus(
                query, image=image, top_k=top_k, union_limit=union_limit
            )
        except Exception:
            # Milvus 连接失败/超时/schema 不匹配 → 本地词法降级
            if self._metrics is not None:
                self._metrics.inc("provider_fallback_total", {"provider": "local_lexical"})
            result = await self._local.search(
                query,
                image=image,
                top_k=top_k,
                union_limit=union_limit,
                category_names=category_names,
            )
            result.fallback_used = True
            # 底层异常可能包含 host、DSN 或供应商响应；只把固定原因带入 Agent 结果，
            # 详细异常不进入 Checkpoint/Event payload，适配器仅增加降级指标。
            result.fallback_reason = "milvus_unavailable"
            return result

    async def _search_milvus(
        self,
        query: RetrievalQuery,
        *,
        image: ImageRef | None,
        top_k: int,
        union_limit: int,
    ) -> RetrievalResult:
        client = self._real_client()
        expr = build_filter_expr(query.hard_filters)
        # 每通道一次搜索；Milvus 失败由外层统一降级
        for _attempt in range(max(1, self._settings.max_network_attempts)):
            try:
                return await self._search_once(
                    client, query, expr=expr, image=image, top_k=top_k, union_limit=union_limit
                )
            except Exception:
                if _attempt + 1 >= max(1, self._settings.max_network_attempts):
                    raise
                await asyncio.sleep(0.05 * (2**_attempt) + random.uniform(0, 0.02))
        raise AssertionError("unreachable")  # pragma: no cover

    async def _search_once(
        self,
        client: MilvusClientPort,
        query: RetrievalQuery,
        *,
        expr: str,
        image: ImageRef | None,
        top_k: int,
        union_limit: int,
    ) -> RetrievalResult:
        results_by_id: dict[str, dict[str, Any]] = {}
        channel_scores: dict[str, dict[str, float]] = {"dense": {}, "sparse": {}, "image": {}}
        sources_by_id: dict[str, list[str]] = {}
        channel_health: dict[str, ChannelStatus] = {}
        # __init__ 已校验非空；`or ""` 仅为把类型收窄到 str
        coll = self._settings.milvus_collection or ""

        # dense 文本通道
        try:
            dense_vectors = await self._text_embeddings.embed_texts([query.query_text or ""])
            if not dense_vectors:
                raise RetrievalUnavailableError("文本 embedding 返回空向量")
            dense_hits = await self._search_channel(
                client,
                coll,
                dense_vectors[0],
                "text_dense",
                expr,
                top_k,
            )
            self._collect(
                dense_hits, results_by_id, channel_scores["dense"], sources_by_id, "dense"
            )
            channel_health["dense"] = (
                ChannelStatus.SUCCESS if channel_scores["dense"] else ChannelStatus.EMPTY
            )
        except Exception:
            channel_health["dense"] = ChannelStatus.FAILED

        # sparse 词法通道
        sparse_vec = query_sparse_vector(query.query_text)
        if sparse_vec:
            try:
                sparse_hits = await self._search_channel(
                    client,
                    coll,
                    sparse_vec,
                    "text_sparse",
                    expr,
                    top_k,
                )
                self._collect(
                    sparse_hits, results_by_id, channel_scores["sparse"], sources_by_id, "sparse"
                )
                channel_health["sparse"] = (
                    ChannelStatus.SUCCESS if channel_scores["sparse"] else ChannelStatus.EMPTY
                )
            except Exception:
                channel_health["sparse"] = ChannelStatus.FAILED
        else:
            channel_health["sparse"] = ChannelStatus.EMPTY

        # 图像通道：只在有图片且 provider 可用时执行
        if image is not None:
            try:
                image_vec = await self._image_embeddings.embed_image(image)
            except RetrievalUnavailableError:
                image_vec = None
                channel_health["image"] = ChannelStatus.UNAVAILABLE
            except Exception:
                image_vec = None
                channel_health["image"] = ChannelStatus.FAILED
            if image_vec is not None:
                try:
                    image_hits = await self._search_channel(
                        client,
                        coll,
                        image_vec,
                        "image_dense",
                        expr,
                        top_k,
                    )
                    self._collect(
                        image_hits, results_by_id, channel_scores["image"], sources_by_id, "image"
                    )
                    channel_health["image"] = (
                        ChannelStatus.SUCCESS if channel_scores["image"] else ChannelStatus.EMPTY
                    )
                except Exception:
                    channel_health["image"] = ChannelStatus.FAILED

        core_statuses = [channel_health.get("dense"), channel_health.get("sparse")]
        if not results_by_id and ChannelStatus.FAILED in core_statuses:
            raise RetrievalUnavailableError("Milvus 所有可用召回通道均失败")

        # 融合前保留各通道的全部有界命中；不能因 dense 先返回而丢弃 sparse 命中。
        candidates_by_id: dict[str, RetrievalCandidate] = {}
        for row in results_by_id.values():
            offer = _entity_to_offer(row)
            candidates_by_id[offer.offer_id] = RetrievalCandidate(
                offer=offer,
                dense_text_score=channel_scores["dense"].get(offer.offer_id),
                sparse_score=channel_scores["sparse"].get(offer.offer_id),
                image_similarity=channel_scores["image"].get(offer.offer_id),
                metadata_match=metadata_match(query, offer),
                recall_score=0.0,
                channel_sources=sources_by_id.get(offer.offer_id, []),
            )
        candidates = list(candidates_by_id.values())
        if not candidates:
            return RetrievalResult(
                candidates=[],
                total_found=0,
                index_version=self._settings.retrieval_index_version,
                channel_counts={
                    name: len(scores)
                    for name, scores in channel_scores.items()
                    if channel_health.get(name) == ChannelStatus.SUCCESS
                },
                channel_results=self._channel_results(candidates_by_id, channel_health),
                channel_health=channel_health,
                selected_candidates=[],
            )

        # ``candidates`` 是命中池的并集；每通道命中保持独立有序，融合交给服务层。
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                -max(
                    candidate.dense_text_score or 0.0,
                    candidate.sparse_score or 0.0,
                    candidate.image_similarity or 0.0,
                ),
                candidate.offer.offer_id,
            ),
        )

        if self._metrics is not None:
            self._metrics.inc("retrieval_candidate_count", value=float(len(ranked)))
            if not ranked:
                self._metrics.inc("retrieval_zero_result_rate")
        return RetrievalResult(
            candidates=ranked,
            total_found=len(ranked),
            channel_counts={
                name: len(scores)
                for name, scores in channel_scores.items()
                if channel_health.get(name) == ChannelStatus.SUCCESS
            },
            index_version=self._settings.retrieval_index_version,
            channel_results=self._channel_results(candidates_by_id, channel_health),
            channel_health=channel_health,
            selected_candidates=ranked,
        )

    async def _search_channel(
        self,
        client: MilvusClientPort,
        collection: str,
        vector: Any,
        anns_field: str,
        expr: str,
        top_k: int,
    ) -> list[list[dict[str, Any]]]:
        """把同步 pymilvus 调用放入受控线程，避免阻塞事件循环。"""
        return await asyncio.to_thread(
            client.search,
            collection_name=collection,
            data=[vector],
            anns_field=anns_field,
            search_params={"metric_type": "IP", "params": {}},
            limit=top_k,
            filter=expr,
            output_fields=_OUTPUT_FIELDS,
        )

    @staticmethod
    def _channel_results(
        candidates: dict[str, RetrievalCandidate],
        health: dict[str, ChannelStatus],
    ) -> list[ChannelResult]:
        fields = {
            "dense": (ChannelKind.DENSE, "dense_text_score"),
            "sparse": (ChannelKind.SPARSE, "sparse_score"),
            "image": (ChannelKind.IMAGE, "image_similarity"),
        }
        result: list[ChannelResult] = []
        for name, (kind, field) in fields.items():
            status = health.get(name)
            if status is None:
                continue
            hits = [
                item.model_copy(update={"recall_score": float(getattr(item, field) or 0.0)})
                for item in candidates.values()
                if getattr(item, field) is not None
            ]
            hits.sort(key=lambda item: (-item.recall_score, item.offer.offer_id))
            result.append(
                ChannelResult(
                    query_id="q:adapter",
                    channel=kind,
                    hits=hits,
                    status=status,
                )
            )
        return result

    @staticmethod
    def _collect(
        hits: list[list[dict[str, Any]]],
        results: dict[str, dict[str, Any]],
        scores: dict[str, float],
        sources: dict[str, list[str]],
        channel: str,
    ) -> None:
        """把一次 Milvus 搜索的返回并入并集（保留首见通道分数）。"""
        for row in hits[0]:
            raw_entity = row.get("entity")
            if not isinstance(raw_entity, dict):
                continue
            # isinstance 收窄 Any 会得到 dict[Unknown, Unknown]，cast 保证可读字段
            entity = cast(dict[str, Any], raw_entity)
            raw_id = entity.get("offer_id") or row.get("id")
            if not isinstance(raw_id, str):
                continue
            if raw_id not in results:
                results[raw_id] = entity
            if raw_id not in scores:
                scores[raw_id] = float(row.get("distance", 0.0))
            src = sources.setdefault(raw_id, [])
            if channel not in src:
                src.append(channel)


def _entity_to_offer(entity: dict[str, Any]) -> Offer:
    """Milvus entity（JSON 属性字段展开）→ Offer。"""
    payload: dict[str, Any] = dict(entity)
    for key in (
        "identity_attributes_json",
        "variant_attributes_json",
        "descriptive_attributes_json",
        "raw_attributes_json",
    ):
        raw = entity.get(key)
        if isinstance(raw, str) and raw:
            try:
                payload[key.replace("_json", "")] = json.loads(raw)
            except json.JSONDecodeError:
                payload[key.replace("_json", "")] = {}
        elif isinstance(raw, dict):
            payload[key.replace("_json", "")] = raw
        payload.pop(key, None)
    return Offer.model_validate(payload)
