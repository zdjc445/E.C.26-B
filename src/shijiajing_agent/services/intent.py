"""意图服务：模型抽取失败时统一走既有规则降级。"""

from __future__ import annotations

from dataclasses import dataclass

from shijiajing_agent.contracts import (
    ConversationTurnSummary,
    IntentPatch,
    ShoppingConstraints,
)
from shijiajing_agent.domain.intent_rules import RuleIntentParser
from shijiajing_agent.domain.memory_policy import validate_memory_directives
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.ports.models import IntentModelPort


@dataclass(frozen=True)
class IntentOutcome:
    patch: IntentPatch | None
    fallback_reason: str | None = None
    model_calls: int = 0


class IntentService:
    def __init__(self, model: IntentModelPort, taxonomy: Taxonomy) -> None:
        self._model = model
        self._taxonomy = taxonomy

    async def run(
        self,
        text: str | None,
        previous_constraints: ShoppingConstraints | None,
        *,
        recent_turns: list[ConversationTurnSummary] | None = None,
    ) -> IntentOutcome:
        if not text:
            return IntentOutcome(None)
        try:
            try:
                patch = await self._model.extract_intent(
                    text,
                    previous_constraints,
                    self._taxonomy,
                    recent_turns=recent_turns,
                )
            except TypeError:
                patch = await self._model.extract_intent(text, previous_constraints, self._taxonomy)
            current_category = patch.category_id or (
                previous_constraints.category_id.value if previous_constraints is not None else None
            )
            patch = patch.model_copy(
                update={
                    "memory_directives": validate_memory_directives(
                        list(patch.memory_directives),
                        text=text,
                        taxonomy=self._taxonomy,
                        current_category_id=current_category,
                    )
                }
            )
            return IntentOutcome(patch, model_calls=1)
        except Exception:
            return IntentOutcome(
                RuleIntentParser(self._taxonomy).parse(text),
                fallback_reason="intent_model_unavailable",
                model_calls=1,
            )

    async def extract(
        self,
        text: str,
        previous_constraints: ShoppingConstraints | None = None,
        *,
        recent_turns: list[ConversationTurnSummary] | None = None,
    ) -> IntentPatch:
        outcome = await self.run(text, previous_constraints, recent_turns=recent_turns)
        return outcome.patch or IntentPatch()


__all__ = ["IntentOutcome", "IntentService"]
