"""商品快照 → Milvus 索引。

CLI：``shijiajing-index-products``

- 读 JSONL 商品快照（每行一个 Offer）。
- 用 TaxonomyNormalizer 标准化品类/品牌/型号/属性。
- 构造 ``search_text``（§13.3 拼接顺序）。
- 文本 dense 向量 + sparse 词法向量（与查询侧同一 tokenizer/权重语义）。
- 分批 upsert（默认 100 条/批）。

注意：真实商品源没有提供的字段保持 null，本工具绝不生成评分、销量、
店铺类型、优惠或运费。
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from shijiajing_agent.adapters.embeddings import ArkTextEmbedding
from shijiajing_agent.adapters.lexical import query_sparse_vector
from shijiajing_agent.config import Settings, load_settings
from shijiajing_agent.contracts import Offer, SellerType
from shijiajing_agent.domain.normalization import TaxonomyNormalizer, build_search_text
from shijiajing_agent.domain.taxonomy import Taxonomy, TaxonomyFile
from shijiajing_agent.ports.milvus import make_milvus_client
from shijiajing_agent.tools.cli_support import configure_utf8_output

_BATCH = 100


def load_taxonomy(path: str | Path) -> Taxonomy:
    data = TaxonomyFile.model_validate_json(Path(path).read_text(encoding="utf-8"))
    return Taxonomy(data)


def offer_to_entity(offer: Offer, taxonomy: Taxonomy, search_text: str) -> dict[str, object]:
    """Offer → Milvus entity 字段映射，与检索适配器 _entity_to_offer 互逆。"""
    payload: dict[str, object] = {}
    for name in (
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
        value = getattr(offer, name)
        payload[name] = value.value if isinstance(value, SellerType) else value
        if payload[name] is None:
            payload.pop(name, None)
    payload["identity_attributes_json"] = offer.identity_attributes
    payload["variant_attributes_json"] = offer.variant_attributes
    payload["descriptive_attributes_json"] = offer.descriptive_attributes
    payload["text_sparse"] = query_sparse_vector(search_text)
    return payload


def build_entity(
    offer: Offer, taxonomy: Taxonomy, normalizer: TaxonomyNormalizer
) -> dict[str, object]:
    """标准化 + search_text 后生成 entity。返回 (entity, 标准品类名)。"""
    nc = normalizer.normalize_offer(offer)
    normalized = offer.model_copy(
        update={
            "category_id": nc.normalized_category_id or offer.category_id,
            "brand": nc.normalized_brand or offer.brand,
            "model": nc.normalized_model or offer.model,
            "identity_attributes": nc.normalized_identity,
            "variant_attributes": nc.normalized_variant,
        }
    )
    cat = taxonomy.get_category(normalized.category_id or "") if normalized.category_id else None
    cat_name = cat.category_name if cat else None
    search_text = build_search_text(normalized, category_name=cat_name, taxonomy=taxonomy)
    entity = offer_to_entity(normalized, taxonomy, search_text)
    return entity


_KEY_FIELDS = ("title", "category_id", "brand", "model", "price", "sku_key")


def _dry_run_summary(offers: list[Offer]) -> None:
    """dry-run 统计（§12）：总行数、合法/非法、品类分布、平台分布、空关键字段比例。"""
    n = len(offers)
    cat = Counter(o.category_id or "（无品类）" for o in offers)
    platform = Counter(o.platform or "（无平台）" for o in offers)
    print(f"dry-run：解析 {n} 行，合法 {n} 行，非法 0 行")
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析与统计，不写 Milvus（§12：不需要 Ark/Milvus/Checkpoint/Trace 配置）",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    # §12：dry-run 不要求外部配置，只要求 snapshot 与 taxonomy 可读
    if not args.dry_run:
        missing = settings.validate(require_real_adapters=True)
        if missing:
            print("缺少必要配置：" + ", ".join(missing), file=sys.stderr)
            return 2
    try:
        taxonomy = load_taxonomy(settings.taxonomy_path_resolved)
    except Exception as exc:
        print(f"taxonomy 加载失败：{exc}", file=sys.stderr)
        return 2

    normalizer = TaxonomyNormalizer(taxonomy)
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
                offer = Offer.model_validate_json(line)
                valid_offers.append(offer)
                entities.append(build_entity(offer, taxonomy, normalizer))
            except Exception as exc:
                n_bad += 1
                print(f"第 {n_offers} 行跳过：{exc}", file=sys.stderr)

    if args.dry_run:
        _dry_run_summary(valid_offers)
        if n_bad:
            print(f"dry-run：{n_bad} 行非法（无法解析为标准 Offer）", file=sys.stderr)
        return 0
    if not entities:
        print("没有可索引的商品", file=sys.stderr)
        return 2

    try:
        from shijiajing_agent.asyncio_compat import run as run_async

        run_async(_upsert(settings, entities, batch=args.batch))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"已索引 {len(entities)} 条商品（跳过 {n_bad} 行）")
    return 0


async def _upsert(settings: Settings, entities: list[dict[str, object]], *, batch: int) -> None:
    embeddings = ArkTextEmbedding(settings)
    # main 里已通过 settings.validate(require_real_adapters=True) 校验
    client = make_milvus_client(settings)
    try:
        coll = settings.milvus_collection or ""
        if not client.has_collection(coll):
            raise RuntimeError(f"Collection {coll} 不存在，请先运行 shijiajing-init-milvus")
        texts = [str(e.get("search_text") or "") for e in entities]
        vectors = await embeddings.embed_texts(texts)
        for entity, vec in zip(entities, vectors, strict=True):
            entity["text_dense"] = vec
        for i in range(0, len(entities), batch):
            client.upsert(collection_name=coll, data=entities[i : i + batch])
            print(f"  upsert 进度 {min(i + batch, len(entities))}/{len(entities)}")
    finally:
        await embeddings.close()
        client.close()


if __name__ == "__main__":
    sys.exit(main())
