"""长期记忆的值域、作用域和约束应用策略。"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Any, cast

from shijiajing_agent.contracts import (
    ConstraintSource,
    MemoryApplyMode,
    MemoryDirective,
    MemoryMutation,
    MemoryOperation,
    MemoryQuery,
    MemoryRecord,
    MemoryStatus,
    Preference,
    ShoppingConstraints,
    SortBy,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.errors import InvalidRequestError

_MEMORY_KEYS = {
    "max_price",
    "min_price",
    "platforms",
    "min_rating",
    "colors",
    "sort_by",
    "preferences",
    "negative_terms",
}
_LIST_KEYS = {"platforms", "colors", "negative_terms"}
_NUMERIC_KEYS = {"max_price", "min_price", "min_rating"}
_CONSTRAINT_KEYS = {
    "max_price",
    "min_price",
    "platforms",
    "min_rating",
    "colors",
    "sort_by",
    "preferences",
}


def canonical_memory_value(memory_key: str, value: Any) -> Any:
    if memory_key not in _MEMORY_KEYS:
        raise InvalidRequestError(f"不允许的 memory_key: {memory_key}")
    if memory_key in _NUMERIC_KEYS:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidRequestError(f"{memory_key} 必须是数字")
        numeric = float(value)
        if (
            not math.isfinite(numeric)
            or numeric < 0
            or (memory_key == "min_rating" and numeric > 5)
        ):
            raise InvalidRequestError(f"{memory_key} 数值范围非法")
        return round(numeric, 2)
    if memory_key in _LIST_KEYS:
        if not isinstance(value, list):
            raise InvalidRequestError(f"{memory_key} 必须是 1..20 项字符串列表")
        items = cast(list[Any], value)
        if not items or len(items) > 20:
            raise InvalidRequestError(f"{memory_key} 必须是 1..20 项字符串列表")
        result: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise InvalidRequestError(f"{memory_key} 只能包含字符串")
            text = item.strip()
            if not text or len(text) > 128:
                raise InvalidRequestError(f"{memory_key} 包含空值或过长值")
            if text not in result:
                result.append(text)
        return result
    if memory_key == "sort_by":
        try:
            return SortBy(value).value
        except ValueError as exc:
            raise InvalidRequestError(f"sort_by 值非法: {value}") from exc
    if memory_key == "preferences":
        if not isinstance(value, list):
            raise InvalidRequestError("preferences 必须是 1..10 项列表")
        items = cast(list[Any], value)
        if not items or len(items) > 10:
            raise InvalidRequestError("preferences 必须是 1..10 项列表")
        result: list[str] = []
        for item in items:
            try:
                normalized = Preference(item).value
            except ValueError as exc:
                raise InvalidRequestError(f"preferences 值非法: {item}") from exc
            if normalized not in result:
                result.append(normalized)
        return result
    raise InvalidRequestError(f"不允许的 memory_key: {memory_key}")


def validate_directive(directive: MemoryDirective, taxonomy: Taxonomy) -> MemoryDirective:
    if directive.scope_key.startswith("category:"):
        category_id = directive.scope_key.removeprefix("category:")
        if taxonomy.get_category(category_id) is None:
            raise InvalidRequestError(f"记忆作用域品类不存在: {category_id}")
    if directive.memory_key is not None and directive.memory_key not in _MEMORY_KEYS:
        raise InvalidRequestError(f"不允许的 memory_key: {directive.memory_key}")
    if directive.operation.value == "upsert":
        value = canonical_memory_value(directive.memory_key or "", directive.value)
        return directive.model_copy(update={"value": value})
    return directive


def validate_mutation(mutation: MemoryMutation) -> MemoryMutation:
    """在 Memory adapter 边界再次校验 mutation，防止绕过节点写入自由 JSON。"""
    if mutation.operation is MemoryOperation.UPSERT:
        value = canonical_memory_value(mutation.memory_key or "", mutation.value)
        return mutation.model_copy(update={"value": value})
    if mutation.memory_key is not None and mutation.memory_key not in _MEMORY_KEYS:
        raise InvalidRequestError(f"不允许的 memory_key: {mutation.memory_key}")
    return mutation


def memory_id(memory_owner_id: str, scope_key: str, memory_key: str) -> str:
    raw = f"{memory_owner_id}|{scope_key}|{memory_key}".encode()
    return hashlib.sha256(raw).hexdigest()


def mutation_id(
    memory_owner_id: str,
    session_id: str,
    request_id: str,
    directive_index: int,
    directive: MemoryDirective,
) -> str:
    raw = "|".join(
        (
            memory_owner_id,
            session_id,
            request_id,
            str(directive_index),
            directive.operation.value,
            directive.scope_key,
            directive.memory_key or "",
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_memory_query(state: Mapping[str, Any], limit: int) -> MemoryQuery:
    scopes = ["global"]
    constraints = state.get("effective_constraints")
    category_id: Any = None
    if isinstance(constraints, ShoppingConstraints):
        category_id = constraints.category_id.value
    elif isinstance(constraints, dict):
        constraint_dict = cast(dict[str, Any], constraints)
        raw: Any = constraint_dict.get("category_id")
        raw_dict = cast(dict[str, Any], raw) if isinstance(raw, dict) else None
        category_id = raw_dict.get("value") if raw_dict is not None else None
    if isinstance(category_id, str) and category_id:
        scopes.append(f"category:{category_id}")
    return MemoryQuery(scope_keys=scopes, limit=limit)


def apply_memory_defaults(
    constraints: ShoppingConstraints, memories: list[MemoryRecord]
) -> ShoppingConstraints:
    result = constraints.model_copy(deep=True)
    for record in memories:
        if record.status is not MemoryStatus.ACTIVE or record.memory_key not in _CONSTRAINT_KEYS:
            continue
        field = getattr(result, record.memory_key)
        if field.value is None:
            field.value = record.value
            field.source = ConstraintSource.MEMORY_EXPLICIT
            field.confidence = record.confidence
            field.locked_by_user = False
    return result


def build_ranking_priors(memories: list[MemoryRecord]) -> dict[str, Any]:
    return {
        record.memory_key: record.value
        for record in memories
        if record.status is MemoryStatus.ACTIVE
        and record.apply_mode is MemoryApplyMode.RANKING_PRIOR
    }


def build_memory_mutation(
    owner_id: str,
    session_id: str,
    request_id: str,
    directive_index: int,
    directive: MemoryDirective,
) -> MemoryMutation:
    return MemoryMutation(
        mutation_id=mutation_id(owner_id, session_id, request_id, directive_index, directive),
        operation=directive.operation,
        memory_key=directive.memory_key,
        scope_key=directive.scope_key,
        value=directive.value,
        apply_mode=directive.apply_mode,
        source_session_id=session_id,
        source_request_id=request_id,
    )
