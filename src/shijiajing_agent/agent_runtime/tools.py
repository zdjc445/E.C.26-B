"""主 Agent 工具目录；工具名称与权限在运行时固定。"""

from __future__ import annotations

from dataclasses import dataclass

from shijiajing_agent.services.evidence import EvidenceService
from shijiajing_agent.services.retrieval import RetrievalService


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str


class RuntimeToolbox:
    """不暴露 Python 函数名、命令或任意 URL 的有限工具目录。"""

    SPECS = (
        ToolSpec("search_once", "按当前硬约束执行一次商品召回"),
        ToolSpec("search_and_compare", "一次召回并执行共享归一化、同款和 SKU 比较"),
        ToolSpec("inspect_evidence", "读取本轮已登记的字段级证据"),
        ToolSpec("compare_candidates", "只对现有候选执行确定性比较"),
    )

    def __init__(self, retrieval: RetrievalService, evidence: EvidenceService) -> None:
        self.retrieval = retrieval
        self.evidence = evidence

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.SPECS)


__all__ = ["RuntimeToolbox", "ToolSpec"]
