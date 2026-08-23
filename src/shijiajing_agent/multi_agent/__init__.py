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
from shijiajing_agent.multi_agent.registry import SpecialistAgentRegistry, build_registry
from shijiajing_agent.multi_agent.shadow import (
    ShadowComparison,
    ShadowComparisonReport,
    compare_responses,
    run_shadow_case,
    run_shadow_suite,
    validate_shadow_report_payload,
)
from shijiajing_agent.multi_agent.supervisor import MultiAgentSupervisor, SupervisorRunResult

__all__ = [
    "DeterministicPlanner",
    "DeterministicSupervisorPlanner",
    "GuardedSupervisorPlanner",
    "InMemoryMultiAgentCheckpoint",
    "LangGraphMultiAgentCheckpoint",
    "MultiAgentSupervisor",
    "PlanValidator",
    "ShadowComparison",
    "ShadowComparisonReport",
    "SpecialistAgentRegistry",
    "SupervisorRunResult",
    "apply_plan_patch",
    "build_registry",
    "compare_responses",
    "dispatch_ready_tasks",
    "find_ready_tasks",
    "run_shadow_case",
    "run_shadow_suite",
    "validate_shadow_report_payload",
]
