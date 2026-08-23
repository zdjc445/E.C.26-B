"""节点与子图所需的业务依赖协议。"""

from __future__ import annotations

from typing import Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    ExecutionPlan,
    ExecutionPlanPatch,
    SupervisorPlanningInput,
    SupervisorReplanningInput,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.ports.cache import VersionedCachePort
from shijiajing_agent.ports.event_store import EventStorePort
from shijiajing_agent.ports.memory import MemoryPort
from shijiajing_agent.ports.models import (
    ExplanationModelPort,
    IntentModelPort,
    QueryRewritePort,
    VisionModelPort,
)
from shijiajing_agent.ports.observability import MetricsPort, TraceSinkPort
from shijiajing_agent.ports.request_ledger import RequestLedgerPort
from shijiajing_agent.ports.retrieval import ProductRetrievalPort


class AgentDependenciesPort(Protocol):
    """业务节点可使用的依赖字段；不暴露第三方 graph checkpointer。"""

    settings: Settings
    taxonomy: Taxonomy
    vision: VisionModelPort
    intent: IntentModelPort
    query_rewrite: QueryRewritePort
    explanation: ExplanationModelPort
    retrieval: ProductRetrievalPort
    trace: TraceSinkPort
    metrics: MetricsPort
    request_ledger: RequestLedgerPort | None
    memory: MemoryPort | None
    cache: VersionedCachePort | None
    event_store: EventStorePort | None
    supervisor_planner: SupervisorPlannerPort | None


class AgentGraphDependenciesPort(AgentDependenciesPort, Protocol):
    """根图装配额外需要的 LangGraph checkpointer 类型边界。"""

    graph_checkpointer: BaseCheckpointSaver[str] | None


class SupervisorPlannerPort(Protocol):
    """结构化可选 Planner；输出仍必须交给 PlanValidator。"""

    async def create_plan(self, request: SupervisorPlanningInput) -> ExecutionPlan: ...

    async def revise_plan(self, request: SupervisorReplanningInput) -> ExecutionPlanPatch: ...
