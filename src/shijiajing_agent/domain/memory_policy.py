"""长期记忆的值域、作用域和约束应用策略。"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from shijiajing_agent.contracts import (
    ConstraintSource,
    IgnoredMemoryRecord,
    MemoryApplication,
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
    content_hash,
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
}
_ALLOWED_MODES: dict[str, frozenset[MemoryApplyMode]] = {
    "max_price": frozenset({MemoryApplyMode.CONSTRAINT_DEFAULT}),
    "min_price": frozenset({MemoryApplyMode.CONSTRAINT_DEFAULT}),
    "min_rating": frozenset({MemoryApplyMode.CONSTRAINT_DEFAULT}),
    "sort_by": frozenset({MemoryApplyMode.CONSTRAINT_DEFAULT}),
    "platforms": frozenset({MemoryApplyMode.CONSTRAINT_DEFAULT, MemoryApplyMode.RANKING_PRIOR}),
    "colors": frozenset({MemoryApplyMode.CONSTRAINT_DEFAULT, MemoryApplyMode.RANKING_PRIOR}),
    "preferences": frozenset({MemoryApplyMode.RANKING_PRIOR}),
    "negative_terms": frozenset({MemoryApplyMode.NEGATIVE_PREFERENCE}),
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


def _category_from_text(text: str, taxonomy: Taxonomy) -> str | None:
    matches: list[str] = []
    for category in taxonomy.categories():
        names = (category.category_id, category.category_name, *category.aliases)
        if any(name and name in text for name in names):
            matches.append(category.category_id)
    return matches[0] if len(set(matches)) == 1 else None


def _has_global_scope_language(text: str) -> bool:
    return any(
        token in text
        for token in (
            "所有商品",
            "所有品类",
            "全局",
            "以后都",
            "全部商品",
            "所有购物偏好",
            "全部偏好",
            "所有偏好",
            "所有记忆",
        )
    )


def validate_memory_directives(
    directives: list[MemoryDirective],
    *,
    text: str,
    taxonomy: Taxonomy,
    current_category_id: str | None = None,
) -> list[MemoryDirective]:
    """验证模型/规则 candidate 是否真的得到当前原文的显式授权。

    该函数是模型路径、规则路径和多 Agent 路径共用的服务端门槛。失败的 candidate
    被丢弃，不影响普通购物意图 patch。
    """
    raw = (text or "").strip()
    has_save = any(token in raw for token in ("记住", "记为", "保存", "默认", "以后买"))
    has_forget = any(token in raw for token in ("忘记", "忘掉", "不要记", "别记"))
    has_clear = any(token in raw for token in ("清空", "清除", "删除全部", "全部忘掉"))
    explicit_category = _category_from_text(raw, taxonomy)
    global_scope = _has_global_scope_language(raw)
    validated: list[MemoryDirective] = []
    for candidate in directives:
        try:
            if candidate.operation is MemoryOperation.CLEAR_OWNER:
                if not has_clear or not global_scope:
                    continue
                validated.append(
                    validate_directive(
                        candidate.model_copy(
                            update={
                                "scope_key": "global",
                                "memory_key": None,
                                "value": None,
                                "apply_mode": None,
                            }
                        ),
                        taxonomy,
                    )
                )
                continue
            if candidate.operation is MemoryOperation.UPSERT and not has_save:
                continue
            if candidate.operation is MemoryOperation.FORGET and not has_forget:
                continue
            if candidate.operation is MemoryOperation.FORGET and not candidate.memory_key:
                continue
            scope_key = candidate.scope_key
            if explicit_category is not None:
                scope_key = f"category:{explicit_category}"
            elif not global_scope:
                if any(token in raw for token in ("这类", "这个", "当前")) and current_category_id:
                    scope_key = f"category:{current_category_id}"
                elif scope_key.startswith("category:"):
                    category_id = scope_key.removeprefix("category:")
                    if category_id != current_category_id:
                        continue
                else:
                    # 没有明确全局语义时，不能把普通记忆命令扩大到 global。
                    continue
            else:
                scope_key = "global"
            validated.append(
                validate_directive(candidate.model_copy(update={"scope_key": scope_key}), taxonomy)
            )
        except InvalidRequestError:
            continue
    return validated


def validate_directive(directive: MemoryDirective, taxonomy: Taxonomy) -> MemoryDirective:
    if directive.scope_key.startswith("category:"):
        category_id = directive.scope_key.removeprefix("category:")
        if taxonomy.get_category(category_id) is None:
            raise InvalidRequestError(f"记忆作用域品类不存在: {category_id}")
    if directive.memory_key is not None and directive.memory_key not in _MEMORY_KEYS:
        raise InvalidRequestError(f"不允许的 memory_key: {directive.memory_key}")
    if directive.operation.value == "upsert":
        value = canonical_memory_value(directive.memory_key or "", directive.value)
        mode = directive.apply_mode
        if mode not in _ALLOWED_MODES.get(directive.memory_key or "", frozenset()):
            raise InvalidRequestError(f"memory_key={directive.memory_key} 不允许 apply_mode={mode}")
        return directive.model_copy(update={"value": value})
    return directive


def validate_mutation(mutation: MemoryMutation) -> MemoryMutation:
    """在 Memory adapter 边界再次校验 mutation，防止绕过节点写入自由 JSON。"""
    if mutation.operation is MemoryOperation.UPSERT:
        value = canonical_memory_value(mutation.memory_key or "", mutation.value)
        if mutation.apply_mode not in _ALLOWED_MODES.get(mutation.memory_key or "", frozenset()):
            raise InvalidRequestError(
                f"memory_key={mutation.memory_key} 不允许 apply_mode={mutation.apply_mode}"
            )
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


def memory_authorization_id(interrupt_id: str, mutations: list[MemoryMutation]) -> str:
    binding = "|".join(
        [
            interrupt_id,
            *(
                f"{item.mutation_id}:{content_hash(item.model_dump(mode='json'))}"
                for item in mutations
            ),
        ]
    )
    return hashlib.sha256(binding.encode("utf-8")).hexdigest()


def build_memory_query(state: Mapping[str, Any], limit: int) -> MemoryQuery:
    scopes: list[str] = []
    constraints = state.get("effective_constraints")
    category_id: Any = None
    if isinstance(constraints, ShoppingConstraints):
        category_id = constraints.category_id.value
    elif isinstance(constraints, dict):
        constraint_dict = cast(dict[str, Any], constraints)
        raw: Any = constraint_dict.get("category_id")
        raw_dict = cast(dict[str, Any], raw) if isinstance(raw, dict) else None
        category_id = (
            raw_dict.get("value") if raw_dict is not None else raw if isinstance(raw, str) else None
        )
    if isinstance(category_id, str) and category_id:
        scopes.append(f"category:{category_id}")
    scopes.append("global")
    return MemoryQuery(scope_keys=scopes, limit=limit)


def _record_is_active(record: MemoryRecord) -> bool:
    if record.status is not MemoryStatus.ACTIVE:
        return False
    if record.expires_at is None:
        return True
    try:
        expires_at = datetime.fromisoformat(record.expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at > datetime.now(UTC)
    except ValueError:
        return False


def resolve_memory_application(
    constraints: ShoppingConstraints,
    memories: list[MemoryRecord],
) -> MemoryApplication:
    """按 category > global 去重并把三种 apply_mode 分流。"""
    category_id = constraints.category_id.value
    category_scope = f"category:{category_id}" if category_id else None
    ordered = sorted(
        enumerate(memories),
        key=lambda pair: (
            0 if category_scope and pair[1].scope_key == category_scope else 1,
            pair[0],
        ),
    )
    selected: dict[str, MemoryRecord] = {}
    ignored: list[IgnoredMemoryRecord] = []
    for _, record in ordered:
        if not _record_is_active(record):
            ignored.append(IgnoredMemoryRecord(memory_id=record.memory_id, reason_code="inactive"))
            continue
        if record.scope_key not in {"global", category_scope}:
            ignored.append(
                IgnoredMemoryRecord(memory_id=record.memory_id, reason_code="scope_mismatch")
            )
            continue
        if record.memory_key in selected:
            ignored.append(
                IgnoredMemoryRecord(memory_id=record.memory_id, reason_code="scope_overridden")
            )
            continue
        allowed = _ALLOWED_MODES.get(record.memory_key, frozenset())
        if record.apply_mode not in allowed:
            ignored.append(
                IgnoredMemoryRecord(memory_id=record.memory_id, reason_code="mode_mismatch")
            )
            continue
        try:
            canonical_memory_value(record.memory_key, record.value)
        except InvalidRequestError:
            ignored.append(
                IgnoredMemoryRecord(memory_id=record.memory_id, reason_code="invalid_value")
            )
            continue
        selected[record.memory_key] = record

    application = MemoryApplication(ignored_records=ignored)
    # 统一使用同一生产 helper 构造 ranking prior，避免只在单元测试中存在的死接口。
    application.ranking_priors = build_ranking_priors(list(selected.values()))
    for key, record in selected.items():
        if record.apply_mode is MemoryApplyMode.CONSTRAINT_DEFAULT:
            field = getattr(constraints, key, None)
            if field is None or field.value is not None:
                application.ignored_records.append(
                    IgnoredMemoryRecord(
                        memory_id=record.memory_id, reason_code="current_value_present"
                    )
                )
                continue
            application.constraint_defaults[key] = record.value
            application.applied_memory_ids.append(record.memory_id)
        elif record.apply_mode is MemoryApplyMode.RANKING_PRIOR:
            application.applied_memory_ids.append(record.memory_id)
        elif record.apply_mode is MemoryApplyMode.NEGATIVE_PREFERENCE:
            application.negative_preferences.extend(cast(list[str], record.value))
            application.applied_memory_ids.append(record.memory_id)
    application.negative_preferences = list(dict.fromkeys(application.negative_preferences))
    return application


def apply_memory_defaults(
    constraints: ShoppingConstraints, memories: list[MemoryRecord]
) -> ShoppingConstraints:
    result = constraints.model_copy(deep=True)
    application = resolve_memory_application(result, memories)
    for key, value in application.constraint_defaults.items():
        field = getattr(result, key)
        if field.value is None:
            field.value = value
            field.source = ConstraintSource.MEMORY_EXPLICIT
            field.confidence = next(
                (
                    record.confidence
                    for record in memories
                    if record.memory_id in application.applied_memory_ids
                    and record.memory_key == key
                ),
                1.0,
            )
            field.locked_by_user = False
    return result


def build_ranking_priors(memories: list[MemoryRecord]) -> dict[str, Any]:
    return {
        record.memory_key: record.value
        for record in memories
        if _record_is_active(record)
        and record.apply_mode is MemoryApplyMode.RANKING_PRIOR
        and record.memory_key in _ALLOWED_MODES
        and record.apply_mode in _ALLOWED_MODES[record.memory_key]
    }


def build_negative_preferences(memories: list[MemoryRecord]) -> list[str]:
    values: list[str] = []
    for record in memories:
        if (
            _record_is_active(record)
            and record.memory_key == "negative_terms"
            and record.apply_mode is MemoryApplyMode.NEGATIVE_PREFERENCE
        ):
            values.extend(cast(list[str], record.value))
    return list(dict.fromkeys(values))


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
