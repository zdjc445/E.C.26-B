"""MemorySubgraph：召回、变更准备和唯一提交入口。"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shijiajing_agent.nodes.memory_nodes import (
    make_commit_memory_node,
    make_prepare_memory_mutations_node,
    make_recall_memory_node,
)
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.state import AgentState


def build_memory_subgraph(
    deps: AgentDependenciesPort, *, include_commit: bool = True, include_prepare: bool = True
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    """装配 Memory 子图。

    根图在 HITL 场景必须把 commit 放在最终响应之后，因此通过
    ``include_commit=False`` 复用 recall/prepare 子图，再由根图单独接入 commit。
    独立调用入口默认保留完整 recall/prepare/commit 流程。
    """
    graph: Any = StateGraph(AgentState)
    graph.add_node("recall_memory", make_recall_memory_node(deps))
    graph.add_edge(START, "recall_memory")
    if include_prepare:
        graph.add_node("prepare_memory_mutations", make_prepare_memory_mutations_node(deps))
        graph.add_edge("recall_memory", "prepare_memory_mutations")
        previous = "prepare_memory_mutations"
    else:
        previous = "recall_memory"
    if include_commit:
        graph.add_node("commit_memory", make_commit_memory_node(deps))
        if not include_prepare:
            graph.add_node("prepare_memory_mutations", make_prepare_memory_mutations_node(deps))
            graph.add_edge(previous, "prepare_memory_mutations")
            previous = "prepare_memory_mutations"
        graph.add_edge(previous, "commit_memory")
        graph.add_edge("commit_memory", END)
    else:
        graph.add_edge(previous, END)
    return cast(
        CompiledStateGraph[AgentState, None, AgentState, AgentState],
        graph.compile(name="memory-subgraph"),
    )
