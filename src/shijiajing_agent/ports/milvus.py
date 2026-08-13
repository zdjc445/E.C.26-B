"""Milvus 客户端 Port（方案 §13）。

pymilvus 的公开方法被 ``@retry_on_rpc_failure`` 等无类型装饰器包装，pyright
将其推断为 ``_Wrapped -> CoroutineType``（运行时实际为同步调用）。为避免
strict 类型检查污染，这里声明本项目实际使用的方法面（子集 Protocol），
在构建处 cast 一次；测试的 FakeMilvusClient 结构化匹配同一 Protocol，
保证 fake 与真实客户端签名一致。
"""

from __future__ import annotations

from typing import Any, Protocol, cast

from shijiajing_agent.config import Settings


class MilvusClientPort(Protocol):
    """pymilvus ``MilvusClient`` 的方法子集（全部同步）。"""

    def has_collection(
        self, collection_name: str, timeout: float | None = None, **kwargs: Any
    ) -> bool: ...
    def drop_collection(
        self, collection_name: str, timeout: float | None = None, **kwargs: Any
    ) -> None: ...
    def create_collection(
        self,
        collection_name: str,
        dimension: int | None = None,
        primary_field_name: str = "id",
        id_type: str = "int",
        vector_field_name: str = "vector",
        metric_type: str = "COSINE",
        auto_id: bool = False,
        timeout: float | None = None,
        schema: Any | None = None,
        index_params: Any | None = None,
        **kwargs: Any,
    ) -> None: ...
    def search(
        self,
        collection_name: str,
        data: Any = None,
        filter: str = "",
        limit: int = 10,
        output_fields: list[str] | None = None,
        search_params: dict[str, Any] | None = None,
        timeout: float | None = None,
        partition_names: list[str] | None = None,
        anns_field: str | None = None,
        **kwargs: Any,
    ) -> list[list[dict[str, Any]]]: ...
    def upsert(
        self,
        collection_name: str,
        data: dict[str, Any] | list[dict[str, Any]],
        timeout: float | None = None,
        partition_name: str | None = "",
        **kwargs: Any,
    ) -> dict[str, Any]: ...
    def close(self) -> None: ...


def make_milvus_client(settings: Settings) -> MilvusClientPort:
    """构建真实 MilvusClient 并 cast 到 Port（调用方需先校验配置非空）。"""
    from pymilvus import MilvusClient

    raw = MilvusClient(
        uri=cast(str, settings.milvus_uri),
        token=cast(str, settings.milvus_token),
        timeout=settings.retrieval_timeout_seconds,
    )
    return cast(MilvusClientPort, raw)
