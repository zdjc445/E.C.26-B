"""五个 Specialist Agent 的最小隔离实现。

每个执行器只接受对应的 ``AgentTaskV2.input``，并把已有端口和确定性 domain 算法封装在
自己的私有 invocation 中。它们从不接收完整 legacy AgentState，也没有更新 Supervisor
状态的引用。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskUsage,
    AgentTaskV2,
    ExplanationTaskInput,
    ExplanationTaskOutput,
    IntentTaskInput,
    IntentTaskOutput,
    MatchPair,
    MemoryTaskInput,
    MemoryTaskOutput,
    NodeStatus,
    RecognitionTaskInput,
    RecognitionTaskOutput,
    RetrievalQuery,
    RetrievalTaskInput,
    RetrievalTaskOutput,
    SkuGroup,
    SpecialistAgentName,
    content_hash,
)
from shijiajing_agent.domain.evidence import EvidenceBuilder, FactualConsistencyChecker
from shijiajing_agent.domain.filters import HardFilterBuilder
from shijiajing_agent.domain.intent_rules import RuleIntentParser
from shijiajing_agent.domain.memory_policy import (
    build_memory_mutation,
    memory_authorization_id,
    validate_directive,
    validate_memory_directives,
)
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.domain.product_canonicalization import canonicalize_offers
from shijiajing_agent.domain.ranking import GroupRanker
from shijiajing_agent.domain.same_item import default_same_item_matcher
from shijiajing_agent.domain.sku import SkuSplitter, spu_id_for
from shijiajing_agent.errors import CapabilityDeniedError
from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for
from shijiajing_agent.ports.dependencies import AgentDependenciesPort


def _usage(start: float, *, calls: int = 0, fallback: bool = False) -> AgentTaskUsage:
    return AgentTaskUsage(
        model_calls=calls,
        duration_ms=max(0.0, (perf_counter() - start) * 1000),
        retry_count=1 if fallback else 0,
    )


class RecognitionAgent:
    name = SpecialistAgentName.RECOGNITION

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, RecognitionTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Recognition input 类型不匹配"),
            )
        try:
            recognition = data.previous_recognition
            if data.correction is not None:
                if (
                    recognition is None
                    or data.correction.recognition_id != recognition.recognition_id
                ):
                    raise ValueError("修正必须指向当前任务授权的 recognition_id")
                update: dict[str, Any] = {
                    "category_id": recognition.category_id,
                    "category_name": recognition.category_name,
                    "brand": recognition.brand,
                    "model": recognition.model,
                    "attributes": dict(recognition.attributes),
                    "field_confidences": dict(recognition.field_confidences),
                }
                attributes = dict(recognition.attributes)
                field_confidences = dict(recognition.field_confidences)
                update["attributes"] = attributes
                update["field_confidences"] = field_confidences
                for field in data.correction.clear_fields:
                    if field in {"category_id", "category_name", "brand", "model"}:
                        update[field] = None
                    if field == "attributes":
                        attributes.clear()
                for field in ("category_id", "brand", "model"):
                    value = getattr(data.correction, field)
                    if value is not None:
                        update[field] = value
                        field_confidences[field] = 1.0
                for key, value in data.correction.attributes.items():
                    if value is None:
                        attributes.pop(key, None)
                    else:
                        attributes[key] = value
                recognition = recognition.model_copy(update=update)
            elif data.image is not None:
                recognition = await self._deps.vision.recognize(data.image, self._deps.taxonomy)
            else:
                raise ValueError("Recognition 任务缺少 image 或 correction")
            normalized = TaxonomyNormalizer(self._deps.taxonomy).normalize_recognition(
                category_id=recognition.category_id,
                brand=recognition.brand,
                model=recognition.model,
                attributes=recognition.attributes,
            )
            recognition = recognition.model_copy(update=normalized)
            review = (
                recognition.overall_confidence < self._deps.settings.recognition_review_threshold
            )
            output = RecognitionTaskOutput(
                recognition=recognition,
                review_recommended=review,
            )
            return result_for(
                task,
                status=NodeStatus.SUCCESS,
                output=output,
                usage=_usage(start, calls=0 if data.correction else 1),
            )
        except Exception:
            return result_for(
                task,
                status=NodeStatus.FALLBACK,
                output=RecognitionTaskOutput(
                    recognition=None,
                    fallback_reason="recognition_unavailable",
                ),
                error=fixed_error("RECOGNITION_UNAVAILABLE", "图片识别不可用，可继续文字理解"),
                usage=_usage(start, calls=1),
            )


class IntentAgent:
    name = SpecialistAgentName.INTENT

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, IntentTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Intent input 类型不匹配"),
            )
        if not data.text:
            return result_for(task, status=NodeStatus.SUCCESS, output=IntentTaskOutput(patch=None))
        try:
            try:
                patch = await self._deps.intent.extract_intent(
                    data.text,
                    data.previous_constraints,
                    self._deps.taxonomy,
                    recent_turns=data.recent_turns,
                )
            except TypeError:
                patch = await self._deps.intent.extract_intent(
                    data.text, data.previous_constraints, self._deps.taxonomy
                )
            current_category = patch.category_id or (
                data.previous_constraints.category_id.value
                if data.previous_constraints is not None
                else None
            )
            patch = patch.model_copy(
                update={
                    "memory_directives": validate_memory_directives(
                        list(patch.memory_directives),
                        text=data.text,
                        taxonomy=self._deps.taxonomy,
                        current_category_id=current_category,
                    )
                }
            )
            return result_for(
                task,
                status=NodeStatus.SUCCESS,
                output=IntentTaskOutput(patch=patch),
                usage=_usage(start, calls=1),
            )
        except Exception:
            patch = RuleIntentParser(self._deps.taxonomy).parse(data.text)
            return result_for(
                task,
                status=NodeStatus.FALLBACK,
                output=IntentTaskOutput(patch=patch),
                error=fixed_error("INTENT_MODEL_UNAVAILABLE", "意图模型不可用，已使用规则解析"),
                usage=_usage(start, calls=1, fallback=True),
            )


class RetrievalAgent:
    name = SpecialistAgentName.RETRIEVAL

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, RetrievalTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Retrieval input 类型不匹配"),
            )
        try:
            hard_filters = HardFilterBuilder().build(data.constraints)
            try:
                query = await self._deps.query_rewrite.rewrite(
                    data.query_text, data.constraints, data.recognition
                )
                if query.hard_filters != hard_filters:
                    query = query.model_copy(update={"hard_filters": hard_filters})
            except Exception:
                query = RetrievalQuery(query_text=data.query_text, hard_filters=hard_filters)
            retrieval = await self._deps.retrieval.search(
                query,
                image=None,
                top_k=data.top_k,
                union_limit=data.union_limit,
                category_names={
                    category.category_id: category.category_name
                    for category in self._deps.taxonomy.categories()
                },
            )
            canonicalization = await canonicalize_offers(
                [item.offer for item in retrieval.candidates],
                self._deps.taxonomy,
                getattr(self._deps, "product_canonicalizer", None),
                enabled=self._deps.settings.product_canonicalization_enabled,
                batch_size=self._deps.settings.product_canonicalization_batch_size,
                min_confidence=self._deps.settings.product_canonicalization_min_confidence,
                cache=getattr(self._deps, "cache", None),
                cache_ttl_seconds=self._deps.settings.product_canonicalization_cache_ttl_seconds,
                metrics=self._deps.metrics,
                mode=self._deps.settings.product_canonicalization_mode,
                dynamic_schema_inducer=getattr(self._deps, "dynamic_schema_inducer", None),
                dynamic_product_canonicalizer=getattr(
                    self._deps, "dynamic_product_canonicalizer", None
                ),
                dynamic_schema_batch_size=self._deps.settings.dynamic_schema_batch_size,
                dynamic_concept_min_confidence=self._deps.settings.dynamic_schema_concept_min_confidence,
                dynamic_role_min_confidence=self._deps.settings.dynamic_schema_role_min_confidence,
                dynamic_role_min_support=self._deps.settings.dynamic_schema_role_min_support,
                dynamic_field_min_confidence=self._deps.settings.dynamic_canonicalization_field_min_confidence,
            )
            normalized = canonicalization.candidates
            for item, candidate in zip(normalized, retrieval.candidates, strict=True):
                item.recall_score = candidate.recall_score
            matcher = default_same_item_matcher(
                self._deps.taxonomy,
                accept_threshold=(
                    self._deps.settings.dynamic_same_item_accept_threshold
                    if self._deps.settings.product_canonicalization_mode
                    in {"dynamic", "hybrid"}
                    else self._deps.settings.same_item_accept_threshold
                ),
                review_threshold=(
                    self._deps.settings.dynamic_same_item_review_threshold
                    if self._deps.settings.product_canonicalization_mode
                    in {"dynamic", "hybrid"}
                    else self._deps.settings.same_item_review_threshold
                ),
                mode=(
                    "taxonomy"
                    if self._deps.settings.product_canonicalization_mode == "dynamic_shadow"
                    else self._deps.settings.product_canonicalization_mode
                ),
            )
            pairs = matcher.generate_candidates(normalized)
            review_pairs = [
                MatchPair(
                    offer_a_id=pair.a_id,
                    offer_b_id=pair.b_id,
                    same_item_score=pair.score,
                    title_similarity=pair.title_similarity,
                    identity_overlap=pair.identity_overlap,
                    image_similarity=pair.image_similarity,
                    source_key_signal=pair.source_key_signal,
                    hard_conflicts=pair.hard_conflicts,
                    verdict="review",
                )
                for left, right in pairs
                if (pair := matcher.judge_pair(normalized[left], normalized[right])).verdict
                == "review"
            ]
            clusters = matcher.cluster(normalized, pairs)
            if data.same_item_review_action == "split" and data.same_item_review_offer_ids:
                review_ids = set(data.same_item_review_offer_ids)
                split_clusters: list[list[int]] = []
                for cluster in clusters:
                    remaining = [
                        index for index in cluster if normalized[index].offer_id not in review_ids
                    ]
                    split_clusters.extend([[index] for index in cluster if index not in remaining])
                    if remaining:
                        split_clusters.append(remaining)
                clusters = split_clusters
            splitter = SkuSplitter(
                self._deps.taxonomy,
                dynamic=self._deps.settings.product_canonicalization_mode
                in {"dynamic", "hybrid"},
            )
            groups: list[SkuGroup] = []
            for cluster in clusters:
                members = [normalized[index] for index in cluster]
                groups.extend(splitter.split_spu(members, spu_id_for(members)))
            ranking = GroupRanker(preference_weights=self._deps.settings.preference_weights).rank(
                groups,
                data.constraints,
                memory_priors=data.ranking_context.memory_priors,
                memory_negative_terms=data.ranking_context.memory_negative_terms,
            )
            output = RetrievalTaskOutput(
                query=query,
                candidates=retrieval.candidates,
                normalized_candidates=normalized,
                ranked_groups=ranking.ranked,
                fallback_used=retrieval.fallback_used,
                same_item_review_pairs=review_pairs,
            )
            return result_for(
                task,
                status=NodeStatus.FALLBACK if retrieval.fallback_used else NodeStatus.SUCCESS,
                output=output,
                usage=_usage(
                    start,
                    calls=canonicalization.model_calls,
                    fallback=canonicalization.fallback_batches > 0,
                ),
            )
        except Exception:
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error(
                    "RETRIEVAL_UNAVAILABLE", "检索不可用，未放宽用户硬过滤", retryable=True
                ),
                usage=_usage(start),
            )


class ExplanationAgent:
    name = SpecialistAgentName.EXPLANATION

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, ExplanationTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Explanation input 类型不匹配"),
            )
        bundle = data.evidence_bundle
        if bundle is None:
            bundle = EvidenceBuilder().build(data.ranked_groups, data.constraints)
        checker = FactualConsistencyChecker()
        try:
            candidate = await self._deps.explanation.explain(bundle)
            verified, _ = checker.verify(candidate, bundle)
            if verified:
                output = ExplanationTaskOutput(
                    explanation_text=candidate,
                    verified=True,
                )
                return result_for(
                    task, status=NodeStatus.SUCCESS, output=output, usage=_usage(start, calls=1)
                )
        except Exception:
            pass
        output = ExplanationTaskOutput(
            explanation_text=checker.template_explanation(bundle),
            verified=False,
            fallback_reason="factual_check_failed",
        )
        return result_for(
            task,
            status=NodeStatus.FALLBACK,
            output=output,
            error=fixed_error("EXPLANATION_FALLBACK", "解释已降级为确定性模板"),
            usage=_usage(start, calls=1, fallback=True),
        )


class MemoryAgent:
    name = SpecialistAgentName.MEMORY

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps
        self._committed_mutation_ids: set[str] = set()

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, MemoryTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Memory input 类型不匹配"),
            )
        if not data.memory_owner_id or self._deps.memory is None:
            return result_for(
                task,
                status=NodeStatus.FALLBACK,
                output=MemoryTaskOutput(operation=data.operation),
                error=fixed_error("MEMORY_UNAVAILABLE", "长期记忆不可用，本轮不阻断业务"),
            )
        try:
            if data.operation == "recall":
                if data.query is None:
                    raise ValueError("memory.recall 必须由 Supervisor 提供当前品类 MemoryQuery")
                query = data.query
                records = await self._deps.memory.recall(data.memory_owner_id, query)
                return result_for(
                    task,
                    status=NodeStatus.SUCCESS,
                    output=MemoryTaskOutput(operation="recall", records=records),
                    usage=_usage(start),
                )
            if data.operation == "prepare":
                if not data.session_id or not data.request_id:
                    raise ValueError("memory.prepare 缺少 session_id/request_id")
                mutations = []
                for index, item in enumerate(data.directives):
                    try:
                        mutations.append(
                            build_memory_mutation(
                                data.memory_owner_id,
                                data.session_id,
                                data.request_id,
                                index,
                                validate_directive(item, self._deps.taxonomy),
                            )
                        )
                    except Exception:
                        continue
                return result_for(
                    task,
                    status=NodeStatus.SUCCESS,
                    output=MemoryTaskOutput(operation="prepare", mutations=mutations),
                    proposed_memory_mutations=mutations,
                    usage=_usage(start),
                )
            if not data.authorization_id or not data.authorization_interrupt_id:
                raise CapabilityDeniedError("Memory commit 必须携带 Supervisor 授权")
            expected_payload_hashes = {
                item.mutation_id: content_hash(item.model_dump(mode="json"))
                for item in data.mutations
            }
            if (
                data.authorization_id
                != memory_authorization_id(data.authorization_interrupt_id, data.mutations)
                or data.authorization_mutation_ids != [item.mutation_id for item in data.mutations]
                or data.authorization_payload_hashes != expected_payload_hashes
            ):
                raise CapabilityDeniedError("Memory commit 授权与当前 mutations 不匹配")
            pending = [
                mutation
                for mutation in data.mutations
                if mutation.mutation_id not in self._committed_mutation_ids
            ]
            if not pending:
                return result_for(
                    task,
                    status=NodeStatus.SUCCESS,
                    output=MemoryTaskOutput(
                        operation="commit",
                        mutations=data.mutations,
                        committed=True,
                        saved=True,
                    ),
                    usage=_usage(start),
                )
            records = await self._deps.memory.commit(data.memory_owner_id, pending)
            self._committed_mutation_ids.update(item.mutation_id for item in pending)
            return result_for(
                task,
                status=NodeStatus.SUCCESS,
                output=MemoryTaskOutput(
                    operation="commit",
                    records=records,
                    mutations=pending,
                    committed=True,
                    saved=True,
                ),
                usage=_usage(start),
            )
        except CapabilityDeniedError:
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("CAPABILITY_DENIED", "Memory commit 未获 Supervisor 授权"),
                usage=_usage(start),
            )
        except Exception:
            return result_for(
                task,
                status=NodeStatus.FAILED if data.operation == "commit" else NodeStatus.FALLBACK,
                output=(
                    None
                    if data.operation == "commit"
                    else MemoryTaskOutput(operation=data.operation)
                ),
                error=fixed_error("MEMORY_OPERATION_FAILED", "记忆操作失败，结果未伪装为已保存"),
                usage=_usage(start),
            )
