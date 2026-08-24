"""受控层级式 Multi-Agent public API。"""

from shijiajing_agent.multi_agent.checkpoint import (
    InMemoryMultiAgentCheckpoint,
    LangGraphMultiAgentCheckpoint,
)
from shijiajing_agent.multi_agent.contracts import *  # noqa: F403
from shijiajing_agent.multi_agent.dispatcher import dispatch_ready_tasks, find_ready_tasks
from shijiajing_agent.multi_agent.planner import (
    DeterministicPlanner,
    DeterministicSupervisorPlanner,
    GuardedSupervisorPlanner,
    PlanValidator,
    apply_plan_patch,
)
from shijiajing_agent.multi_agent.planner_catalog import (
    AllowedAction,
    AllowedActionCatalog,
    build_action_catalog,
)
from shijiajing_agent.multi_agent.planner_contracts import (
    PlannerAction,
    PlannerProposal,
    PlanningOutcome,
)
from shijiajing_agent.multi_agent.planner_materializer import (
    MaterializationResult,
    PlanMaterializer,
)
from shijiajing_agent.multi_agent.registry import SpecialistAgentRegistry, build_registry
from shijiajing_agent.multi_agent.shadow import (
    PlannerShadowEvidence,
    ShadowComparison,
    ShadowComparisonReport,
    build_planner_shadow_evidence,
    compare_responses,
    run_shadow_case,
    run_shadow_suite,
    validate_shadow_report_payload,
)
from shijiajing_agent.multi_agent.supervisor import MultiAgentSupervisor, SupervisorRunResult

__all__ = [
    "AllowedAction",
    "AllowedActionCatalog",
    "DeterministicPlanner",
    "DeterministicSupervisorPlanner",
    "GuardedSupervisorPlanner",
    "InMemoryMultiAgentCheckpoint",
    "LangGraphMultiAgentCheckpoint",
    "MaterializationResult",
    "MultiAgentSupervisor",
    "PlanMaterializer",
    "PlanValidator",
    "PlannerAction",
    "PlannerProposal",
    "PlannerShadowEvidence",
    "PlanningOutcome",
    "ShadowComparison",
    "ShadowComparisonReport",
    "SpecialistAgentRegistry",
    "SupervisorRunResult",
    "apply_plan_patch",
    "build_action_catalog",
    "build_planner_shadow_evidence",
    "build_registry",
    "compare_responses",
    "dispatch_ready_tasks",
    "find_ready_tasks",
    "run_shadow_case",
    "run_shadow_suite",
    "validate_shadow_report_payload",
]
