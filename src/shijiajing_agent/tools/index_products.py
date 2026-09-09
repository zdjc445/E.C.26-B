"""商品快照 → Milvus 索引。

CLI：``shijiajing-index-products``

- 读 JSONL 商品快照（每行一个 Offer）。
- 保留来源 SKU/Offer 原值，不依赖 taxonomy 推导字段。
- 用 ``build_raw_search_text`` 构造唯一 Dense/Sparse/BM25 输入。
- 文本 dense 向量 + sparse 词法向量（与查询侧同一 tokenizer/权重语义）。
- 分批 upsert（默认 100 条/批）。

注意：真实商品源没有提供的字段保持 null，本工具绝不生成评分、销量、
店铺类型、优惠或运费。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from shijiajing_agent.adapters.embeddings import ArkTextEmbedding
from shijiajing_agent.adapters.lexical import query_sparse_vector
from shijiajing_agent.config import Settings, load_settings
from shijiajing_agent.contracts import Offer, SellerType
from shijiajing_agent.domain.raw_offer import (
    RecordKind,
    prepare_raw_offer,
    raw_offer_from_mapping,
)
from shijiajing_agent.domain.taxonomy import Taxonomy, TaxonomyFile
from shijiajing_agent.ports.milvus import make_milvus_client
from shijiajing_agent.rag_contracts import IndexManifest
from shijiajing_agent.tools.cli_support import configure_utf8_output

_BATCH = 60


def load_taxonomy(path: str | Path) -> Taxonomy:
    data = TaxonomyFile.model_validate_json(Path(path).read_text(encoding="utf-8"))
    return Taxonomy(data)


def offer_to_entity(offer: Offer, search_text: str | None = None) -> dict[str, object]:
    """Offer → Milvus entity 字段映射，与检索适配器 _entity_to_offer 互逆。"""
    prepared = prepare_raw_offer(offer)
    text = search_text or prepared.search_text or ""
    payload: dict[str, object] = {}
    for name in (
        "offer_id",
        "platform",
        "source_product_id",
        "source_sku_id",
        "source_offer_id",
        "record_kind",
        "raw_category_path",
        "provenance",
        "source_revision",
        "source_content_hash",
        "availability",
        "price_basis",
        "source_updated_at",
        "data_version",
        "title",
        "normalized_title",
        "search_text_hash",
        "category_id",
        "brand",
        "model",
        "same_item_key",
        "sku_key",
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
    ):
        value = getattr(prepared, name)
        payload[name] = value.value if isinstance(value, SellerType) else value
        if hasattr(value, "value"):
            payload[name] = value.value
        if payload[name] is None:
            payload.pop(name, None)
    payload["identity_attributes_json"] = offer.identity_attributes
    payload["variant_attributes_json"] = offer.variant_attributes
    payload["descriptive_attributes_json"] = offer.descriptive_attributes
    payload["raw_attributes_json"] = [
        item.model_dump(mode="json") for item in prepared.raw_attributes
    ]
    payload["search_text"] = text
    payload["text_sparse"] = query_sparse_vector(text)
    return payload


def build_entity(offer: Offer) -> dict[str, object]:
    """保留来源事实并生成单一 raw search text，不依赖 taxonomy。"""
    return offer_to_entity(prepare_raw_offer(offer))


_KEY_FIELDS = (
    "title",
    "record_kind",
    "source_product_id",
    "source_sku_id",
    "price",
    "price_basis",
)


def _dry_run_summary(offers: list[Offer]) -> None:
    """dry-run 统计（§12）：总行数、合法/非法、品类分布、平台分布、空关键字段比例。"""
    n = len(offers)
    indexable = [offer for offer in offers if _is_indexable(offer)]
    cat = Counter(o.category_id or "（无品类）" for o in offers)
    platform = Counter(o.platform or "（无平台）" for o in offers)
    print(f"dry-run：解析 {n} 行，合法 {n} 行，非法 0 行")
    print(f"可进入 Offer 索引：{len(indexable)} 行，product_summary：{n - len(indexable)} 行")
    print("品类分布：" + ", ".join(f"{k}={v}" for k, v in sorted(cat.items())))
    print("平台分布：" + ", ".join(f"{k}={v}" for k, v in sorted(platform.items())))
    for key in _KEY_FIELDS:
        empty = sum(1 for o in offers if getattr(o, key) in (None, ""))
        ratio = f"{empty / n:.1%}" if n else "—"
        print(f"空关键字段 {key}：{empty}/{n}（{ratio}）")


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="把商品快照写入 Milvus 索引")
    parser.add_argument("snapshot", help="JSONL 商品快照路径")
    parser.add_argument("--batch", type=int, default=_BATCH, help="upsert 批大小")
    parser.add_argument("--manifest", type=Path, help="写入索引输入/发布 manifest 的路径")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析与统计，不写 Milvus（§12：不需要 Ark/Milvus/Checkpoint/Trace 配置）",
    )
    args = parser.parse_args(argv)
    if args.batch < 1:
        print("--batch 必须大于 0", file=sys.stderr)
        return 2

    settings = load_settings()
    # §12：dry-run 不要求外部配置，只要求 snapshot 与 taxonomy 可读
    if not args.dry_run:
        missing = settings.validate(require_real_adapters=True)
        if missing:
            print("缺少必要配置：" + ", ".join(missing), file=sys.stderr)
            return 2
    path = Path(args.snapshot)
    if not path.exists():
        print(f"快照不存在：{path}", file=sys.stderr)
        return 2

    entities: list[dict[str, object]] = []
    valid_offers: list[Offer] = []
    n_offers, n_bad = 0, 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n_offers += 1
            try:
                raw_payload = json.loads(line)
                if not isinstance(raw_payload, dict):
                    raise ValueError("来源记录必须是 JSON 对象")
                payload = cast(dict[str, Any], raw_payload)
                offer = raw_offer_from_mapping(payload)
                valid_offers.append(offer)
                if _is_indexable(offer):
                    entities.append(build_entity(offer))
            except Exception as exc:
                n_bad += 1
                print(f"第 {n_offers} 行跳过：{exc}", file=sys.stderr)

    if args.dry_run:
        _dry_run_summary(valid_offers)
        if args.manifest is not None:
            _write_manifest(args.manifest, _build_manifest(valid_offers, path, settings))
        if n_bad:
            print(f"dry-run：{n_bad} 行非法（无法解析为标准 Offer）", file=sys.stderr)
        return 0
    if not entities:
        print("没有可索引的商品", file=sys.stderr)
        return 2

    try:
        from shijiajing_agent.asyncio_compat import run as run_async

        dimension = run_async(_upsert(settings, entities, batch=args.batch))
        if args.manifest is not None:
            _write_manifest(
                args.manifest,
                _build_manifest(valid_offers, path, settings, embedding_dimension=dimension),
            )
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"已索引 {len(entities)} 条商品（跳过 {n_bad} 行）")
    return 0


async def _upsert(settings: Settings, entities: list[dict[str, object]], *, batch: int) -> int:
    embeddings = ArkTextEmbedding(settings)
    # main 里已通过 settings.validate(require_real_adapters=True) 校验
    client = make_milvus_client(settings)
    try:
        coll = settings.milvus_collection or ""
        if not client.has_collection(coll):
            raise RuntimeError(f"Collection {coll} 不存在，请先运行 shijiajing-init-milvus")
        expected_dimension: int | None = None
        for i in range(0, len(entities), batch):
            current = entities[i : i + batch]
            texts = [str(entity.get("search_text") or "") for entity in current]
            vectors = await embeddings.embed_texts(texts)
            if len(vectors) != len(current):
                raise RuntimeError("embedding 返回数量与输入不一致")
            for entity, vector in zip(current, vectors, strict=True):
                if not vector or any(not math.isfinite(float(value)) for value in vector):
                    raise RuntimeError("embedding 返回了空向量或非有限数值")
                if expected_dimension is None:
                    expected_dimension = len(vector)
                if len(vector) != expected_dimension:
                    raise RuntimeError("embedding 维度不一致")
                entity["text_dense"] = vector
            client.upsert(collection_name=coll, data=current)
            print(f"  upsert 进度 {min(i + batch, len(entities))}/{len(entities)}")
        if expected_dimension is None:
            raise RuntimeError("没有可用的 embedding 维度")
        return expected_dimension
    finally:
        await embeddings.close()
        client.close()


def _is_indexable(offer: Offer) -> bool:
    """仅真实 SKU Offer 进入可比索引；概要记录保留在原始快照中。"""
    return offer.record_kind is RecordKind.SKU_OFFER and bool(
        offer.source_sku_id or offer.sku_key or offer.source_product_id
    )


def _build_manifest(
    offers: list[Offer],
    snapshot_path: Path,
    settings: Settings,
    *,
    embedding_dimension: int | None = None,
) -> IndexManifest:
    source_hashes = [offer.source_content_hash for offer in offers if offer.source_content_hash]
    aggregate = hashlib.sha256(
        json.dumps(source_hashes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    snapshot_id = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()[:32]
    return IndexManifest(
        schema_version="raw-offer-v1",
        snapshot_id=snapshot_id,
        source_batches=[snapshot_path.name],
        source_content_hash=aggregate,
        text_generation_version="raw-search-text-v1",
        tokenizer_version="hash-bigram-v1",
        sparse_version="hash-tf-v1",
        embedding_model=settings.embedding_model,
        embedding_dimension=embedding_dimension,
        vector_normalization="provider_defined",
        distance_metric="IP",
        collection=settings.milvus_collection,
        built_at=datetime.now(UTC),
        valid_offer_count=sum(1 for offer in offers if _is_indexable(offer)),
    )


def _write_manifest(path: Path, manifest: IndexManifest) -> None:
    """manifest 只允许新建，避免覆盖已发布索引身份。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as fh:
        json.dump(manifest.model_dump(mode="json"), fh, ensure_ascii=False, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    sys.exit(main())
