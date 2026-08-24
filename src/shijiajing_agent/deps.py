"""生产装配：按 Settings 构建真实端口实现（示例与评测 CLI 共用）。

外部资源（API Key、模型标识符、Milvus 地址、数据路径）一律来自环境变量，
缺失时返回精确缺失项列表，不提供代码默认值（方案 §13）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shijiajing_agent.adapters.ark_models import build_ark_models
from shijiajing_agent.adapters.ark_supervisor_planner import ArkSupervisorPlanner
from shijiajing_agent.adapters.checkpoint import make_checkpoint
from shijiajing_agent.adapters.embeddings import build_embedding_ports
from shijiajing_agent.adapters.local_retrieval import LocalLexicalRetrievalAdapter
from shijiajing_agent.adapters.milvus_retrieval import MilvusHybridRetrievalAdapter
from shijiajing_agent.adapters.observability import make_metrics, make_trace_sink
from shijiajing_agent.config import Settings
from shijiajing_agent.domain.taxonomy import load_taxonomy
from shijiajing_agent.facade import AgentDependencies
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort
from shijiajing_agent.ports.observability import MetricsPort
from shijiajing_agent.ports.retrieval import ProductRetrievalPort


def make_retrieval(
    settings: Settings, *, metrics: MetricsPort | None = None
) -> ProductRetrievalPort:
    """检索装配：Milvus 配置齐全时用 Milvus，否则降级本地快照。

    两种实现返回同一领域协议。Milvus 路径的本地兜底是惰性适配器：快照未配置时
    指向必然不存在的路径，仅当 Milvus 不可用触发降级时才报精确错误。
    """
    missing_milvus = [
        n for n in ("milvus_uri", "milvus_token", "milvus_collection") if not getattr(settings, n)
    ]
    snapshot = (
        Path(settings.local_product_snapshot_path) if settings.local_product_snapshot_path else None
    )

    if not missing_milvus:
        text_embeddings, image_embeddings = build_embedding_ports(settings)
        local = LocalLexicalRetrievalAdapter(
            snapshot or (Path.cwd() / "no-local-snapshot-configured.jsonl"), metrics=metrics
        )
        return MilvusHybridRetrievalAdapter(
            settings,
            text_embeddings=text_embeddings,
            image_embeddings=image_embeddings,
            local_fallback=local,
            metrics=metrics,
        )

    if snapshot is not None:
        return LocalLexicalRetrievalAdapter(snapshot, metrics=metrics)

    raise ValueError(
        "检索配置缺失：Milvus（SHIJIAJING_MILVUS_URI / SHIJIAJING_MILVUS_TOKEN /"
        " SHIJIAJING_MILVUS_COLLECTION）与本地快照（SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH）"
        "至少提供一组"
    )


def make_deps(
    settings: Settings,
    *,
    resource_registrar: Callable[[ResourceLifecyclePort], None] | None = None,
) -> AgentDependencies:
    """构建生产依赖（示例与评测 ``--live`` 共用）。缺配置时抛 ValueError 列出缺失项。"""
    missing = settings.validate(require_real_adapters=True)
    if missing:
        names = ", ".join(f"SHIJIAJING_{n}" for n in missing)
        raise ValueError(f"缺少必要配置：{names}")
    engineering_errors = settings.validate_engineering()
    if engineering_errors:
        raise ValueError("二期配置错误：" + ", ".join(engineering_errors))

    metrics = make_metrics(settings)
    taxonomy = load_taxonomy(settings.taxonomy_path_resolved)
    trace = make_trace_sink(settings)
    if resource_registrar is not None:
        resource_registrar(trace)

    vision, intent, query_rewrite, explanation = build_ark_models(settings, metrics=metrics)
    if resource_registrar is not None:
        # 四个 Ark Port 共享同一个客户端，只登记 Vision owner。
        resource_registrar(vision)

    supervisor_planner = None
    if (
        settings.orchestration_mode != "workflow"
        and settings.supervisor_planner_mode != "off"
    ):
        client = getattr(vision, "client", None)
        if client is None:
            raise ValueError("Supervisor Planner 无法取得共享 ArkModelClient")
        supervisor_planner = ArkSupervisorPlanner(client, taxonomy, settings)

    retrieval = make_retrieval(settings, metrics=metrics)
    if resource_registrar is not None:
        resource_registrar(retrieval)

    checkpoint = make_checkpoint(settings)
    if resource_registrar is not None:
        resource_registrar(checkpoint)

    return AgentDependencies(
        taxonomy=taxonomy,
        settings=settings,
        vision=vision,
        intent=intent,
        query_rewrite=query_rewrite,
        explanation=explanation,
        retrieval=retrieval,
        checkpoint=checkpoint,
        trace=trace,
        metrics=metrics,
        supervisor_planner=supervisor_planner,
    )
