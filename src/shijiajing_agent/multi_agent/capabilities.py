"""固定 capability allowlist。

Agent executor 只能使用这里声明的能力；Supervisor 不暴露商品检索和 Memory 写端口。
"""

from __future__ import annotations

from collections.abc import Collection

from shijiajing_agent.contracts import AgentTaskKind, SpecialistAgentName
from shijiajing_agent.errors import CapabilityDeniedError

CAPABILITY_ALLOWLIST: dict[SpecialistAgentName, frozenset[str]] = {
    SpecialistAgentName.RECOGNITION: frozenset({"vision", "taxonomy"}),
    SpecialistAgentName.INTENT: frozenset({"intent_model", "rule_parser"}),
    SpecialistAgentName.RETRIEVAL: frozenset(
        {"query_rewrite", "embedding", "milvus", "local_index", "domain_algorithms"}
    ),
    SpecialistAgentName.EXPLANATION: frozenset({"explanation_model", "fact_validator"}),
    SpecialistAgentName.MEMORY: frozenset({"memory_store", "memory_policy"}),
}

TASK_CAPABILITIES: dict[AgentTaskKind, frozenset[str]] = {
    AgentTaskKind.RECOGNIZE: frozenset({"vision", "taxonomy"}),
    AgentTaskKind.APPLY_CORRECTION: frozenset({"taxonomy"}),
    AgentTaskKind.PARSE_INTENT: frozenset({"intent_model", "rule_parser"}),
    AgentTaskKind.RETRIEVE_AND_RANK: frozenset(
        {"query_rewrite", "embedding", "milvus", "local_index", "domain_algorithms"}
    ),
    AgentTaskKind.EXPLAIN: frozenset({"explanation_model", "fact_validator"}),
    AgentTaskKind.MEMORY_RECALL: frozenset({"memory_store", "memory_policy"}),
    AgentTaskKind.MEMORY_PREPARE: frozenset({"memory_policy"}),
    AgentTaskKind.MEMORY_COMMIT: frozenset({"memory_store", "memory_policy"}),
}


def validate_capability(agent: SpecialistAgentName, capability: str) -> None:
    if capability not in CAPABILITY_ALLOWLIST[agent]:
        raise CapabilityDeniedError(f"{agent.value} 不允许使用 {capability}")


def validate_capabilities(
    agent: SpecialistAgentName,
    requested: Collection[str],
) -> None:
    denied = set(requested) - set(CAPABILITY_ALLOWLIST[agent])
    if denied:
        raise CapabilityDeniedError(f"{agent.value} 包含未授权能力: {sorted(denied)}")
