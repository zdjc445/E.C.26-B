"""生产装配单元测试（§23）：make_retrieval / make_deps 的配置校验与分支选择。

验证点：
- 检索配置缺失且无本地快照 → 精确的 ValueError（不静默降级）；
- 仅本地快照 → LocalLexicalRetrievalAdapter，且可用快照真实检索；
- Milvus 配置齐全 → MilvusHybridRetrievalAdapter（不发起网络）；
- make_deps 缺外部配置 → ValueError 列出精确缺失项。
"""

from __future__ import annotations

import shutil
from contextlib import AsyncExitStack
from inspect import isawaitable
from pathlib import Path

import pytest

import shijiajing_agent
import shijiajing_agent.deps as deps_module
from shijiajing_agent.adapters.ark_supervisor_planner import ArkSupervisorPlanner
from shijiajing_agent.adapters.local_retrieval import LocalLexicalRetrievalAdapter
from shijiajing_agent.adapters.milvus_retrieval import MilvusHybridRetrievalAdapter
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import RetrievalQuery
from shijiajing_agent.deps import make_deps, make_retrieval
from tests.workflow.conftest import make_offer

# ---------------------------------------------------------------------------
# make_retrieval 分支
# ---------------------------------------------------------------------------


def test_make_retrieval_no_config_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        make_retrieval(Settings())
    message = str(excinfo.value)
    assert "MILVUS_URI" in message
    assert "LOCAL_PRODUCT_SNAPSHOT_PATH" in message


def test_make_retrieval_local_snapshot_path(tmp_path: Path) -> None:
    snapshot = tmp_path / "offers.jsonl"
    adapter = make_retrieval(Settings(local_product_snapshot_path=str(snapshot)))
    assert isinstance(adapter, LocalLexicalRetrievalAdapter)
    # 快照缺失时不得在构造期崩溃，使用期才报精确错误
    from shijiajing_agent.errors import RetrievalUnavailableError

    with pytest.raises(RetrievalUnavailableError) as excinfo:
        import asyncio

        asyncio.run(adapter.search(RetrievalQuery(query_text="索尼耳机")))
    assert "本地商品快照不可用" in str(excinfo.value)


def test_make_retrieval_milvus_prefers_milvus(tmp_path: Path) -> None:
    """Milvus 三件套齐全 → 走 Milvus 混合检索（构造不发起网络）。"""
    settings = Settings(
        milvus_uri="https://mock-milvus.example:19530",
        milvus_token="mock-token",
        milvus_collection="products_v1",
        ark_api_key="mock-key",
        ark_base_url="https://mock-ark.example/v1",
        embedding_model="mock-embed",
        local_product_snapshot_path=str(tmp_path / "offers.jsonl"),
    )
    adapter = make_retrieval(settings)
    assert isinstance(adapter, MilvusHybridRetrievalAdapter)
    # 本地兜底也按配置挂载
    assert adapter._local is not None


def test_make_retrieval_milvus_without_models_raises() -> None:
    """Milvus 配置齐全但模型配置缺失 → 构造时报精确缺失项（不是网络错误）。"""
    settings = Settings(
        milvus_uri="https://mock-milvus.example:19530",
        milvus_token="mock-token",
        milvus_collection="products_v1",
    )
    with pytest.raises(ValueError) as excinfo:
        make_retrieval(settings)
    assert "ARK_API_KEY" in str(excinfo.value) or "SHIJIAJING_ARK_API_KEY" in str(excinfo.value)


# ---------------------------------------------------------------------------
# make_deps 配置校验
# ---------------------------------------------------------------------------


def test_make_deps_missing_config_raises_precise() -> None:
    with pytest.raises(ValueError) as excinfo:
        make_deps(Settings())
    message = str(excinfo.value)
    assert "缺少必要配置" in message
    for name in ("ARK_API_KEY", "MILVUS_URI", "CHECKPOINT_DSN", "LOCAL_PRODUCT_SNAPSHOT_PATH"):
        assert name in message


def test_make_deps_assembles_with_full_config(tmp_path: Path) -> None:
    """全量配置（本地快照 + sqlite checkpoint）→ 无需网络即可装配。"""
    packaged_taxonomy = Path(shijiajing_agent.__file__).parent / "data" / "taxonomy.json"
    taxonomy_file = tmp_path / "taxonomy.json"
    shutil.copy(packaged_taxonomy, taxonomy_file)
    snapshot = tmp_path / "offers.jsonl"
    snapshot.write_text(make_offer("o-1", price=1999.0).model_dump_json(), encoding="utf-8")
    settings = Settings(
        ark_api_key="mock-key",
        ark_base_url="https://mock-ark.example/v1",
        ark_vision_model="mock-vision",
        ark_text_model="mock-text",
        embedding_model="mock-embed",
        milvus_uri="https://mock-milvus.example:19530",
        milvus_token="mock-token",
        milvus_collection="products_v1",
        taxonomy_path=str(taxonomy_file),
        local_product_snapshot_path=str(snapshot),
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
    )
    deps = make_deps(settings)
    assert deps.taxonomy is not None
    # Milvus 配置齐全 → 走 Milvus 混合检索（不发起网络）
    assert isinstance(deps.retrieval, MilvusHybridRetrievalAdapter)
    assert deps.retrieval._metrics is deps.metrics
    assert deps.vision._client._metrics is deps.metrics
    assert deps.checkpoint is not None


def test_make_deps_assembles_configured_supervisor_planner(tmp_path: Path) -> None:
    snapshot = tmp_path / "offers.jsonl"
    snapshot.write_text(make_offer("o-planner", price=1999.0).model_dump_json(), encoding="utf-8")
    settings = Settings(
        ark_api_key="mock-key",
        ark_base_url="https://mock-ark.example/v1",
        ark_vision_model="mock-vision",
        ark_text_model="mock-text",
        supervisor_model="mock-supervisor",
        supervisor_planner_mode="active_replan",
        local_product_snapshot_path=str(snapshot),
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
    )
    deps = make_deps(settings)
    assert isinstance(deps.supervisor_planner, ArkSupervisorPlanner)


def test_make_deps_does_not_create_planner_for_legacy_workflow(tmp_path: Path) -> None:
    snapshot = tmp_path / "offers.jsonl"
    snapshot.write_text(make_offer("o-workflow", price=1999.0).model_dump_json(), encoding="utf-8")
    settings = Settings(
        orchestration_mode="workflow",
        supervisor_model="mock-supervisor",
        supervisor_planner_mode="active",
        ark_api_key="mock-key",
        ark_base_url="https://mock-ark.example/v1",
        ark_vision_model="mock-vision",
        ark_text_model="mock-text",
        local_product_snapshot_path=str(snapshot),
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
    )
    deps = make_deps(settings)
    assert deps.supervisor_planner is None


def test_make_deps_assembles_with_local_snapshot_only(tmp_path: Path) -> None:
    """本地快照是 Milvus 三件套的正式替代配置，不要求同时提供 Milvus。"""
    snapshot = tmp_path / "offers.jsonl"
    snapshot.write_text(make_offer("o-local", price=1999.0).model_dump_json(), encoding="utf-8")
    settings = Settings(
        ark_api_key="mock-key",
        ark_base_url="https://mock-ark.example/v1",
        ark_vision_model="mock-vision",
        ark_text_model="mock-text",
        embedding_model="mock-embed",
        local_product_snapshot_path=str(snapshot),
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
    )
    deps = make_deps(settings)
    assert isinstance(deps.retrieval, LocalLexicalRetrievalAdapter)


def test_local_snapshot_does_not_require_embedding_model(tmp_path: Path) -> None:
    """本地词法检索不构造 embedding port，因此不应要求 embedding model。"""
    snapshot = tmp_path / "offers.jsonl"
    snapshot.write_text(
        make_offer("o-local-no-embedding", price=1999.0).model_dump_json(), encoding="utf-8"
    )
    settings = Settings(
        ark_api_key="mock-key",
        ark_base_url="https://mock-ark.example/v1",
        ark_vision_model="mock-vision",
        ark_text_model="mock-text",
        local_product_snapshot_path=str(snapshot),
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
    )

    deps = make_deps(settings)

    assert isinstance(deps.retrieval, LocalLexicalRetrievalAdapter)
    assert deps.retrieval._metrics is deps.metrics


def test_milvus_requires_embedding_model(tmp_path: Path) -> None:
    settings = Settings(
        ark_api_key="mock-key",
        ark_base_url="https://mock-ark.example/v1",
        ark_vision_model="mock-vision",
        ark_text_model="mock-text",
        milvus_uri="https://mock-milvus.example:19530",
        milvus_token="mock-token",
        milvus_collection="products_v1",
        local_product_snapshot_path=str(tmp_path / "offers.jsonl"),
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
    )

    assert settings.validate(require_real_adapters=True) == ["EMBEDDING_MODEL"]


@pytest.mark.asyncio
async def test_make_deps_registers_owners_before_later_construction_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    close_order: list[str] = []

    class ConstructedResource:
        def __init__(self, name: str) -> None:
            self._name = name

        async def close(self) -> None:
            close_order.append(self._name)

    trace = ConstructedResource("trace")
    vision = ConstructedResource("vision")

    monkeypatch.setattr(deps_module, "make_trace_sink", lambda _: trace)
    monkeypatch.setattr(
        deps_module,
        "build_ark_models",
        lambda *args, **kwargs: (vision, object(), object(), object()),
    )

    def fail_retrieval(*args, **kwargs):
        raise RuntimeError("retrieval construction failed")

    monkeypatch.setattr(deps_module, "make_retrieval", fail_retrieval)

    settings = Settings(
        ark_api_key="mock-key",
        ark_base_url="https://mock-ark.example/v1",
        ark_vision_model="mock-vision",
        ark_text_model="mock-text",
        local_product_snapshot_path=str(tmp_path / "offers.jsonl"),
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
    )

    async def close_resource(resource: ConstructedResource) -> None:
        result = resource.close()
        if isawaitable(result):
            await result

    async with AsyncExitStack() as stack:
        with pytest.raises(RuntimeError, match="retrieval construction failed"):
            deps_module.make_deps(
                settings,
                resource_registrar=lambda resource: stack.push_async_callback(
                    close_resource, resource
                ),
            )

    assert close_order == ["vision", "trace"]
