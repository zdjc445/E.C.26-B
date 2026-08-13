"""初始化 Milvus Collection（方案 §13.2 Collection 字段）。

CLI：``shijiajing-init-milvus``

- 全部外部地址/Token/模型来自环境变量（SHIJIAJING_*），缺失时列出精确缺失项。
- 文本向量维度按实际 embedding 模型契约决定（首次调用后取）。
- 图像向量字段只在 ``SHIJIAJING_IMAGE_EMBEDDING_DIMENSION`` 显式提供时创建
  （可配置多模态 provider 接入后使用），否则跳过并打印提示——不伪造图像向量。
- 集合已存在时默认报错退出（--drop 显式删除重建）。
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Protocol, cast

from pymilvus import CollectionSchema, DataType, FieldSchema
from pymilvus.milvus_client.index import IndexParams

from shijiajing_agent.adapters.embeddings import ArkTextEmbedding
from shijiajing_agent.config import Settings, load_settings
from shijiajing_agent.ports.milvus import make_milvus_client

_TEXT_DENSE_INDEX = "AUTOINDEX"
_SPARSE_INDEX = "SPARSE_INVERTED_INDEX"


class _IndexParamsLike(Protocol):
    """pymilvus ``IndexParams`` 的最小使用面。

    库内桩把 ``add_index`` 的参数标为 ``**kwargs: Unknown``，strict 下直接调用
    会触发 reportUnknownMemberType；这里声明实际使用的签名并在构建处 cast。
    """

    def add_index(
        self,
        field_name: str,
        index_type: str = "",
        index_name: str = "",
        **kwargs: Any,
    ) -> None: ...


def _schema(dim: int, image_dim: int | None) -> tuple[CollectionSchema, _IndexParamsLike]:
    """§13.2 逻辑字段 → pymilvus CollectionSchema 与 IndexParams。"""

    def varchar(name: str, max_length: int) -> FieldSchema:
        return FieldSchema(name=name, dtype=DataType.VARCHAR, max_length=max_length)

    def float_field(name: str) -> FieldSchema:
        return FieldSchema(name=name, dtype=DataType.FLOAT)

    fields = [
        FieldSchema(name="offer_id", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
        varchar("platform", 32),
        varchar("source_product_id", 128),
        varchar("source_updated_at", 32),
        varchar("data_version", 64),
        varchar("title", 1024),
        varchar("normalized_title", 1024),
        varchar("search_text", 4096),
        varchar("category_id", 64),
        varchar("brand", 128),
        varchar("model", 128),
        varchar("same_item_key", 128),
        varchar("sku_key", 128),
        FieldSchema(name="identity_attributes_json", dtype=DataType.JSON),
        FieldSchema(name="variant_attributes_json", dtype=DataType.JSON),
        FieldSchema(name="descriptive_attributes_json", dtype=DataType.JSON),
        float_field("price"),
        float_field("original_price"),
        float_field("shipping_fee"),
        float_field("coupon_amount"),
        varchar("currency", 8),
        varchar("shop_id", 128),
        varchar("shop_name", 256),
        varchar("seller_type", 16),
        float_field("rating"),
        float_field("sales"),
        float_field("review_count"),
        float_field("delivery_days"),
        varchar("source_payload_ref", 512),
        FieldSchema(name="text_dense", dtype=DataType.FLOAT_VECTOR, dim=dim),
        FieldSchema(name="text_sparse", dtype=DataType.SPARSE_FLOAT_VECTOR),
    ]
    if image_dim is not None:
        fields.append(FieldSchema(name="image_dense", dtype=DataType.FLOAT_VECTOR, dim=image_dim))
    schema = CollectionSchema(fields, description="识价镜商品比价索引（§13.2）")

    index_params = cast(_IndexParamsLike, IndexParams())
    index_params.add_index(field_name="text_dense", index_type=_TEXT_DENSE_INDEX, metric_type="IP")
    index_params.add_index(field_name="text_sparse", index_type=_SPARSE_INDEX, metric_type="IP")
    if image_dim is not None:
        index_params.add_index(
            field_name="image_dense", index_type=_TEXT_DENSE_INDEX, metric_type="IP"
        )
    return schema, index_params


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化 Milvus 商品比价 Collection")
    parser.add_argument("--drop", action="store_true", help="已存在时先删除再重建")
    args = parser.parse_args(argv)

    settings = load_settings()
    missing = settings.validate(require_real_adapters=True)
    if missing:
        print("缺少必要配置：" + ", ".join(missing), file=sys.stderr)
        return 2
    image_dim: int | None = None
    raw_dim = os.environ.get("SHIJIAJING_IMAGE_EMBEDDING_DIMENSION")
    if raw_dim and raw_dim.strip():
        image_dim = int(raw_dim)

    import asyncio

    dim = asyncio.run(_resolve_dim(settings))
    schema, index_params = _schema(dim, image_dim)

    client = make_milvus_client(settings)
    coll = settings.milvus_collection or ""
    if client.has_collection(coll):
        if not args.drop:
            print(f"Collection {coll} 已存在（--drop 可删除重建）", file=sys.stderr)
            return 1
        client.drop_collection(coll)
    client.create_collection(
        collection_name=coll,
        schema=schema,
        index_params=index_params,
    )
    print(
        f"Collection {coll} 已创建：text_dense dim={dim}"
        + (f"，image_dense dim={image_dim}" if image_dim is not None else "（未启用 image_dense）")
    )
    return 0


async def _resolve_dim(settings: Settings) -> int:
    embeddings = ArkTextEmbedding(settings)
    try:
        await embeddings.embed_texts(["初始化维度探测"])
    finally:
        await embeddings.close()
    return embeddings.dimension


if __name__ == "__main__":
    sys.exit(main())
