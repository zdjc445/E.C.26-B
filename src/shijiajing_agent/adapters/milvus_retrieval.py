"""Milvus 混合召回适配器（方案 §13）。

- dense 文本 + sparse 词法 + （可选）图像三个通道并行取 Top K，并集按融合分
  排序截断 union_limit（§13.4）。
- 每信号在当前候选集 min-max 归一化到 [0,1]；融合权重按 §13.4 文本/图片公式；
  缺失通道按可用权重重新归一化。
- 硬过滤生成 Milvus filter 表达式（§13.5），与本地降级 ``offer_matches_hard_filters``
  同一语义（价格比较字段均为 ``price``）。
- Milvus 失败/超时/schema 不匹配 → 本地词法降级（§13.7），``fallback_used=true``；
  本地快照也不可用 → 抛 ``RetrievalUnavailableError``。
- 图像通道只在图片可用且图像向量 provider 已配置时执行，缺失时如实不参与融合。
"""

from __future__ import annotations

import asyncio
import json
import random
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
from shijiajing_agent.ports.retrieval import RetrievalResult

# 所有 Offer 标量字段 + 三个 JSON 属性字段（§13.2 Collection 字段）
_OUTPUT_FIELDS = [
    "offer_id",
    "platform",
    "source_product_id",
    "source_updated_at",
    "data_version",
    "title",
    "normalized_title",
    "search_text",
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

# §13.4 融合权重
_TEXT_WEIGHTS = {"dense": 0.50, "sparse": 0.30, "metadata": 0.20}
_IMAGE_WEIGHTS = {"dense": 0.35, "sparse": 0.20, "image": 0.25, "metadata": 0.20}


def escape_milvus_string(value: str) -> str:
    """Milvus filter 表达式字符串转义（单引号包裹）。"""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_filter_expr(hf: HardFilters) -> str:
    """§13.5 硬过滤 → Milvus filter 表达式。空过滤返回空字符串。"""
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
        metrics: Any | None = None,
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
        except RetrievalUnavailableError:
            raise
        except Exception as exc:
            # §13.7：Milvus 连接失败/超时/schema 不匹配 → 本地词法降级
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
            result.fallback_reason = f"milvus_unavailable: {exc}"
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
        # __init__ 已校验非空；`or ""` 仅为把类型收窄到 str
        coll = self._settings.milvus_collection or ""

        # dense 文本通道
        dense_vec = (await self._text_embeddings.embed_texts([query.query_text or ""]))[0]
        dense_hits = client.search(
            collection_name=coll,
            data=[dense_vec],
            anns_field="text_dense",
            search_params={"metric_type": "IP", "params": {}},
            limit=top_k,
            filter=expr,
            output_fields=_OUTPUT_FIELDS,
        )
        self._collect(dense_hits, results_by_id, channel_scores["dense"], sources_by_id, "dense")

        # sparse 词法通道
        sparse_vec = query_sparse_vector(query.query_text)
        if sparse_vec:
            sparse_hits = client.search(
                collection_name=coll,
                data=[sparse_vec],
                anns_field="text_sparse",
                search_params={"metric_type": "IP"},
                limit=top_k,
                filter=expr,
                output_fields=_OUTPUT_FIELDS,
            )
            self._collect(
                sparse_hits, results_by_id, channel_scores["sparse"], sources_by_id, "sparse"
            )

        # 图像通道：只在有图片且 provider 可用时执行
        image_channel = False
        if image is not None:
            try:
                image_vec = await self._image_embeddings.embed_image(image)
            except RetrievalUnavailableError:
                image_vec = None
            if image_vec is not None:
                image_hits = client.search(
                    collection_name=coll,
                    data=[image_vec],
                    anns_field="image_dense",
                    search_params={"metric_type": "IP", "params": {}},
                    limit=top_k,
                    filter=expr,
                    output_fields=_OUTPUT_FIELDS,
                )
                self._collect(
                    image_hits, results_by_id, channel_scores["image"], sources_by_id, "image"
                )
                image_channel = True

        # 并集截断
        candidates = list(results_by_id.values())
        if len(candidates) > union_limit:
            candidates = candidates[:union_limit]
        if not candidates:
            return RetrievalResult(candidates=[], total_found=0)

        # 每信号在当前候选集归一化（§13.4）
        for channel in ("dense", "sparse", "image"):
            _min_max_normalize(channel_scores[channel], candidates)
        weights = _pick_weights(image_channel, channel_scores)

        ranked: list[RetrievalCandidate] = []
        for row in candidates:
            offer = _entity_to_offer(row)
            scores = {
                "dense": channel_scores["dense"].get(offer.offer_id),
                "sparse": channel_scores["sparse"].get(offer.offer_id),
                "image": channel_scores["image"].get(offer.offer_id),
            }
            meta = metadata_match(query, offer)  # 恒为 [0,1] 的 float，metadata 通道恒参与
            used, denom = 0.0, 0.0
            for name, weight in weights.items():
                if name == "metadata":
                    used += weight * meta
                    denom += weight
                elif scores.get(name) is not None:
                    used += weight * (scores[name] or 0.0)
                    denom += weight
            recall = used / denom if denom else 0.0
            ranked.append(
                RetrievalCandidate(
                    offer=offer,
                    dense_text_score=scores["dense"],
                    sparse_score=scores["sparse"],
                    image_similarity=scores["image"],
                    metadata_match=meta,
                    recall_score=recall,
                    channel_sources=sources_by_id.get(offer.offer_id, []),
                )
            )
        ranked.sort(key=lambda c: c.recall_score, reverse=True)

        if self._metrics is not None:
            self._metrics.inc("retrieval_candidate_count", value=float(len(ranked)))
            if not ranked:
                self._metrics.inc("retrieval_zero_result_rate")
        return RetrievalResult(
            candidates=ranked,
            total_found=len(ranked),
            channel_counts={name: len(ids) for name, ids in channel_scores.items() if ids},
        )

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


def _pick_weights(
    image_channel: bool, channel_scores: dict[str, dict[str, float]]
) -> dict[str, float]:
    """§13.4 权重：按是否有图像通道选公式；缺失通道由融合循环剔除分母。"""
    weights = dict(_IMAGE_WEIGHTS) if image_channel else dict(_TEXT_WEIGHTS)
    # dense 缺失时（embedding 成功但通道空集不影响），融合循环按可用通道归一化
    return weights


def _min_max_normalize(scores: dict[str, float], candidates: list[dict[str, Any]]) -> None:
    """把通道分数在候选集内 min-max 到 [0,1]（§13.4）。"""
    values: list[float] = []
    for c in candidates:
        cid = c.get("offer_id")
        if isinstance(cid, str) and cid in scores:
            values.append(scores[cid])
    if not values:
        return
    lo, hi = min(values), max(values)
    if hi <= lo:
        for key in list(scores):
            scores[key] = 1.0 if hi > 0 else 0.0
        return
    for key in list(scores):
        scores[key] = (scores[key] - lo) / (hi - lo)


def _entity_to_offer(entity: dict[str, Any]) -> Offer:
    """Milvus entity（JSON 属性字段展开）→ Offer。"""
    payload: dict[str, Any] = dict(entity)
    for key in (
        "identity_attributes_json",
        "variant_attributes_json",
        "descriptive_attributes_json",
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
