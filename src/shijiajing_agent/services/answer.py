"""证据约束回答服务；事实值始终从确定性结果渲染。"""

from __future__ import annotations

from dataclasses import dataclass

from shijiajing_agent.agent_runtime.contracts import EvidenceQualityReport
from shijiajing_agent.contracts import RankedGroup, ShoppingConstraints
from shijiajing_agent.domain.evidence import EvidenceBuilder, FactualConsistencyChecker
from shijiajing_agent.ports.models import ExplanationModelPort
from shijiajing_agent.services.evidence import EvidenceService


@dataclass(frozen=True)
class AnswerResult:
    text: str
    verified: bool
    reports: list[EvidenceQualityReport]
    used_model: bool = False


class AnswerService:
    def __init__(
        self,
        evidence: EvidenceService | None = None,
        explanation: ExplanationModelPort | None = None,
    ) -> None:
        self._evidence = evidence or EvidenceService()
        self._explanation = explanation

    async def render(
        self,
        groups: list[RankedGroup],
        constraints: ShoppingConstraints,
        records: dict[str, object],
        *,
        constraints_version: int,
        notices: list[str] | None = None,
    ) -> AnswerResult:
        typed_records = {key: value for key, value in records.items() if hasattr(value, "fields")}
        typed_reports = self._evidence.quality_for_groups(
            groups,
            typed_records,  # type: ignore[arg-type]
            constraints_version=constraints_version,
        )
        bundle = EvidenceBuilder().build(groups, constraints, notices=notices)
        checker = FactualConsistencyChecker()
        if self._explanation is not None and groups:
            try:
                candidate = await self._explanation.explain(bundle)
                valid, _ = checker.verify(candidate, bundle)
                # 自由文本即使包含合法数字，也不能把 A 的数字暗写到 B。
                # V1 只采纳同时带有商品标题和对应价格的受控行，否则使用模板。
                if valid and self._has_local_price_binding(candidate, groups):
                    return AnswerResult(candidate, True, typed_reports, used_model=True)
            except Exception:
                pass
        return AnswerResult(checker.template_explanation(bundle), True, typed_reports)

    @staticmethod
    def _has_local_price_binding(text: str, groups: list[RankedGroup]) -> bool:
        lines = text.splitlines() or [text]
        for ranked in groups:
            title = ranked.group.title or ""
            if not title or ranked.group.min_price is None:
                continue
            price = f"{ranked.group.min_price:g}"
            if any(title in line and price in line for line in lines):
                return True
        return False


__all__ = ["AnswerResult", "AnswerService"]
