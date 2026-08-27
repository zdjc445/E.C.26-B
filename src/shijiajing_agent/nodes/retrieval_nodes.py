"""检索节点：查询改写、混合召回、零结果放宽、候选标准化。

- ``rewrite_query``：模型只能改写 ``query_text`` 与扩展 ``soft_terms``；
  任何 ``hard_filters`` 变化都会被拒绝并进入确定性拼接。
- ``retrieve_candidates``：Milvus 失败时适配器内部降级本地词法索引。
- ``relax_recognition_constraints``：零结果时只放宽识别产生且未锁定的字段。
- ``normalize_candidates``：单条坏数据隔离，全部非法时失败。
"""

from __future__ import annotations

from typing import Any

from shijiajing_agent.contracts import HardFilters, RetrievalCandidate, RetrievalQuery
from shijiajing_agent.domain.cache_policy import safe_get, safe_set, versioned_key
from shijiajing_agent.domain.filters import HardFilterBuilder, offer_matches_hard_filters
from shijiajing_agent.domain.product_canonicalization import canonicalize_offers
from shijiajing_agent.domain.retrieval_reranking import CandidateRelevanceReranker
from shijiajing_agent.errors import RetrievalUnavailableError
from shijiajing_agent.nodes.node_support import clear_dirty, record_cache_event, timed
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.ports.models import QueryRewritePort
from shijiajing_agent.ports.retrieval import ProductRetrievalPort
from shijiajing_agent.state import AgentState


def build_deterministic_query(deps: AgentDependenciesPort, state: AgentState) -> RetrievalQuery:
    """确定性查询拼接：硬过滤来自约束构建，软词来自识别字段。"""
    req = state["current_request"]
    constraints = state.get("effective_constraints")
    recognition = state.get("recognition")
    hf = (
        HardFilterBuilder(
            brand_confidence_threshold=deps.settings.brand_hard_filter_confidence,
            model_confidence_threshold=deps.settings.model_hard_filter_confidence,
        ).build(constraints)
        if constraints
        else HardFilters()
    )
    query = RetrievalQuery(query_text=req.text or "", hard_filters=hf)
    soft_terms: list[str] = []
    if recognition:
        if (
            recognition.brand
            and (recognition.field_confidences.get("brand", 0) or 0)
            < deps.settings.brand_hard_filter_confidence
        ):
            soft_terms.append(recognition.brand)
        if (
            recognition.model
            and (recognition.field_confidences.get("model", 0) or 0)
            < deps.settings.model_hard_filter_confidence
        ):
            soft_terms.append(recognition.model)
    for kw in state.get("keywords") or []:
        if kw not in soft_terms:
            soft_terms.append(kw)
    query.soft_terms = soft_terms
    patch = state.get("intent_patch")
    if patch is not None:
        query.negative_terms = list(getattr(patch, "negative_terms", []) or [])
    application = state.get("memory_application")
    for term in list(getattr(application, "negative_preferences", []) or []):
        if term not in query.negative_terms:
            query.negative_terms.append(term)
    return query


def make_rewrite_query_node(deps: AgentDependenciesPort) -> Any:
    """查询改写。校验硬过滤不被篡改；失败/篡改 → 确定性拼接。"""

    rewrite_model: QueryRewritePort = deps.query_rewrite

    @timed("rewrite_query")
    async def rewrite_query_node(state: AgentState) -> dict[str, Any]:
        # 局部重算（§10）：query 未变时复用
        if not (state.get("dirty_flags") or {}).get("query_dirty", True):
            if state.get("retrieval_query") is not None:
                return {"next_action": "query_ready"}
        base = build_deterministic_query(deps, state)
        fallback_used = False
        query = base
        req = state["current_request"]
        constraints = state.get("effective_constraints")
        recognition = state.get("recognition")
        cache_key = versioned_key(
            {
                "text": req.text or "",
                "constraints": constraints.model_dump(mode="json") if constraints else None,
                "recognition": recognition.model_dump(mode="json") if recognition else None,
                "memory_negative_terms": list(
                    getattr(state.get("memory_application"), "negative_preferences", []) or []
                ),
            },
            {
                "model": deps.settings.ark_text_model,
                "prompt": "v1",
                "taxonomy": deps.taxonomy.taxonomy_version,
            },
        )
        cached = await safe_get(deps.cache, "query_rewrite", cache_key, metrics=deps.metrics)
        cached_query = None
        cached_payload = cached.get("retrieval_query") if isinstance(cached, dict) else None
        # 缺少 query_text 时必须按 miss 处理，不能把空查询误当作模型改写结果并改变召回结果。
        if isinstance(cached_payload, dict) and "query_text" in cached_payload:
            try:
                candidate = RetrievalQuery.model_validate(cached_payload)
                if candidate.hard_filters == base.hard_filters:
                    cached_query = candidate
            except Exception:
                cached_query = None
        await record_cache_event(
            deps,
            state,
            node_name="rewrite_query",
            namespace="query_rewrite",
            cache_key=cache_key,
            hit=cached_query is not None,
        )
        if cached_query is not None:
            cached_query = base.model_copy(
                update={
                    "query_text": cached_query.query_text,
                    "soft_terms": cached_query.soft_terms,
                    "negative_terms": list(
                        dict.fromkeys([*cached_query.negative_terms, *base.negative_terms])
                    ),
                }
            )
            return {
                "retrieval_query": cached_query,
                "next_action": "query_ready",
                **clear_dirty(state, "query_dirty"),
            }
        try:
            rewritten = await rewrite_model.rewrite(req.text or "", constraints, recognition)
            if rewritten.hard_filters != base.hard_filters:
                # 篡改硬过滤：拒绝并进入确定性拼接
                fallback_used = True
            else:
                query = rewritten
                deterministic = build_deterministic_query(deps, state)
                query = query.model_copy(
                    update={
                        "negative_terms": list(
                            dict.fromkeys([*query.negative_terms, *deterministic.negative_terms])
                        )
                    }
                )
        except Exception:
            fallback_used = True
        delta: dict[str, Any] = {
            "retrieval_query": query,
            "next_action": "query_ready",
            "notices": list(state.get("notices") or []),
            **clear_dirty(state, "query_dirty"),
        }
        if fallback_used:
            delta["notices"].append("查询改写模型不可用或篡改硬过滤，已使用确定性查询拼接")
            delta["fallbacks"] = [
                *list(state.get("fallbacks") or []),
                {
                    "node_name": "rewrite_query",
                    "reason": "invalid_or_failed",
                    "fallback_provider": "deterministic",
                },
            ]
        await safe_set(
            deps.cache,
            "query_rewrite",
            cache_key,
            {"retrieval_query": query.model_dump(mode="json")},
            deps.settings.query_rewrite_cache_ttl_seconds,
            metrics=deps.metrics,
        )
        return delta

    return rewrite_query_node


def make_retrieve_candidates_node(deps: AgentDependenciesPort) -> Any:
    """混合召回。零结果时记录状态供路由判断。"""

    retrieval: ProductRetrievalPort = deps.retrieval

    @timed("retrieve_candidates")
    async def retrieve_candidates_node(state: AgentState) -> dict[str, Any]:
        if not (state.get("dirty_flags") or {}).get("retrieval_dirty", True):
            if state.get("candidates"):
                return {"next_action": "results"}
        query = state.get("retrieval_query")
        if query is None:
            return {"next_action": "no_results"}
        try:
            cache_key = None
            image = state.get("image_ref")
            if deps.settings.retrieval_index_version:
                cache_key = versioned_key(
                    {
                        "query": query.model_dump(mode="json"),
                        "image_sha256": image.sha256 if image is not None else None,
                        "top_k": deps.settings.retrieval_top_k_per_channel,
                        "union_limit": deps.settings.retrieval_union_limit,
                    },
                    {
                        "index": deps.settings.retrieval_index_version,
                        "fusion": deps.settings.retrieval_fusion_strategy,
                        "rerank": CandidateRelevanceReranker.version
                        if deps.settings.retrieval_rerank_enabled
                        else None,
                    },
                )
                cached = await safe_get(deps.cache, "retrieval", cache_key, metrics=deps.metrics)
                cached_candidates: list[RetrievalCandidate] | None = None
                if isinstance(cached, dict) and isinstance(cached.get("candidates"), list):
                    try:
                        parsed = [
                            RetrievalCandidate.model_validate(item) for item in cached["candidates"]
                        ]
                        if all(
                            offer_matches_hard_filters(item.offer, query.hard_filters)
                            for item in parsed
                        ):
                            cached_candidates = parsed
                    except Exception:
                        cached_candidates = None
                await record_cache_event(
                    deps,
                    state,
                    node_name="retrieve_candidates",
                    namespace="retrieval",
                    cache_key=cache_key,
                    hit=cached_candidates is not None,
                )
                if cached_candidates is not None:
                    return {
                        "candidates": cached_candidates,
                        "next_action": "results" if cached_candidates else "no_results",
                        "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
                        "retrieval_index_version": (
                            cached.get("index_version") if isinstance(cached, dict) else None
                        ),
                        "fusion_version": (
                            cached.get("fusion_version") if isinstance(cached, dict) else None
                        ),
                        "rerank_version": (
                            cached.get("rerank_version") if isinstance(cached, dict) else None
                        ),
                    }
            result = await retrieval.search(
                query,
                image=state.get("image_ref"),
                top_k=deps.settings.retrieval_top_k_per_channel,
                union_limit=deps.settings.retrieval_union_limit,
                category_names={c.category_id: c.category_name for c in deps.taxonomy.categories()},
            )
        except RetrievalUnavailableError as exc:
            return {
                "next_action": "failed",
                "errors": [
                    *list(state.get("errors") or []),
                    {
                        "node_name": "retrieve_candidates",
                        "error_code": exc.code.value,
                        "message": exc.user_message,
                    },
                ],
            }
        candidates = result.candidates
        rerank_version = result.rerank_version
        if deps.settings.retrieval_rerank_enabled and candidates:
            candidates = CandidateRelevanceReranker().rerank(
                candidates,
                query,
                deps.settings.retrieval_rerank_limit,
            )
            rerank_version = CandidateRelevanceReranker.version
        next_action = "results" if candidates else "no_results"
        delta: dict[str, Any] = {
            "candidates": candidates,
            "next_action": next_action,
            "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
            "retrieval_index_version": result.index_version,
            "fusion_version": result.fusion_version,
            "rerank_version": rerank_version,
        }
        if result.fallback_used:
            delta["retrieval_fallback_used"] = True
            delta["notices"] = [
                *list(state.get("notices") or []),
                "向量检索不可用，已使用本地词法索引",
            ]
            delta["fallbacks"] = [
                *list(state.get("fallbacks") or []),
                {
                    "node_name": "retrieve_candidates",
                    "reason": result.fallback_reason or "milvus_unavailable",
                    "fallback_provider": "local_lexical",
                },
            ]
        if cache_key is not None:
            await safe_set(
                deps.cache,
                "retrieval",
                cache_key,
                {
                    "candidates": [item.model_dump(mode="json") for item in candidates],
                    "index_version": result.index_version,
                    "fusion_version": result.fusion_version,
                    "rerank_version": rerank_version,
                },
                deps.settings.retrieval_cache_ttl_seconds,
                metrics=deps.metrics,
            )
        return delta

    return retrieve_candidates_node


def make_relax_recognition_constraints_node(deps: AgentDependenciesPort) -> Any:
    """零结果放宽：只放宽识别产生且未锁定的字段，最多一次。"""

    @timed("relax_recognition_constraints")
    async def relax_recognition_constraints_node(state: AgentState) -> dict[str, Any]:
        query = state.get("retrieval_query")
        constraints = state.get("effective_constraints")
        if query is None or constraints is None:
            return {"next_action": "no_results"}
        builder = HardFilterBuilder(
            brand_confidence_threshold=deps.settings.brand_hard_filter_confidence,
            model_confidence_threshold=deps.settings.model_hard_filter_confidence,
        )
        result = builder.relax(query.model_copy(deep=True), constraints)
        if not result.relaxed_fields:
            # 已尝试放宽但无可放宽字段（如全部来自用户输入）→ 结束
            return {"relaxation_attempted": True, "next_action": "no_results"}
        flags = clear_dirty(state, "query_dirty")["dirty_flags"]
        flags["retrieval_dirty"] = True
        return {
            "retrieval_query": result.query,
            "relaxed_attributes": list(state.get("relaxed_attributes") or [])
            + result.relaxed_fields,
            "relaxation_attempted": True,
            "notices": list(state.get("notices") or []) + result.notices,
            "next_action": "rewrite",
            # 放宽是查询级覆盖，模型改写会从约束重建硬过滤（撤销放宽），
            # 因此清除 query_dirty 跳过改写、只重跑检索。
            "dirty_flags": flags,
        }

    return relax_recognition_constraints_node


def make_normalize_candidates_node(deps: AgentDependenciesPort) -> Any:
    """候选标准化。单条坏数据隔离；全部非法 → PRODUCT_SCHEMA_INVALID。"""

    @timed("normalize_candidates")
    async def normalize_candidates_node(state: AgentState) -> dict[str, Any]:
        if not (state.get("dirty_flags") or {}).get("matching_dirty", True):
            if state.get("normalized_candidates"):
                return {"next_action": "candidates_ready"}
        candidates = state.get("candidates") or []
        matching_limit = deps.settings.matching_candidate_limit
        candidate_window = candidates[:matching_limit]
        run = await canonicalize_offers(
            [candidate.offer for candidate in candidate_window],
            deps.taxonomy,
            getattr(deps, "product_canonicalizer", None),
            enabled=deps.settings.product_canonicalization_enabled,
            batch_size=deps.settings.product_canonicalization_batch_size,
            min_confidence=deps.settings.product_canonicalization_min_confidence,
            cache=getattr(deps, "cache", None),
            cache_ttl_seconds=deps.settings.product_canonicalization_cache_ttl_seconds,
            metrics=deps.metrics,
            mode=deps.settings.product_canonicalization_mode,
            dynamic_schema_inducer=getattr(deps, "dynamic_schema_inducer", None),
            dynamic_product_canonicalizer=getattr(
                deps, "dynamic_product_canonicalizer", None
            ),
            dynamic_schema_batch_size=deps.settings.dynamic_schema_batch_size,
            dynamic_concept_min_confidence=deps.settings.dynamic_schema_concept_min_confidence,
            dynamic_role_min_confidence=deps.settings.dynamic_schema_role_min_confidence,
            dynamic_role_min_support=deps.settings.dynamic_schema_role_min_support,
            dynamic_field_min_confidence=deps.settings.dynamic_canonicalization_field_min_confidence,
        )
        normalized = run.candidates
        for item, candidate in zip(normalized, candidate_window, strict=True):
            item.recall_score = candidate.recall_score
        notices = [*list(state.get("notices") or []), *(run.notices or [])]
        if len(candidates) > matching_limit:
            notices.append(f"同款匹配候选超过上限，已截断至 {matching_limit} 条")
        dynamic_schema_summary: dict[str, Any] = {}
        if run.verified_schema is not None:
            dynamic_schema_summary.update(
                {
                    "concept_count": len(run.verified_schema.concepts),
                    "assignment_count": len(run.verified_schema.assignments),
                    "accepted_field_count": run.accepted_fields,
                    "descriptive_only_count": run.descriptive_only_fields,
                }
            )
        return {
            "normalized_candidates": normalized,
            "dynamic_schema_id": run.schema_id,
            "dynamic_schema_summary": dynamic_schema_summary or None,
            "dynamic_shadow_summary": run.shadow_summary,
            "notices": notices,
            "next_action": "candidates_ready",
        }

    return normalize_candidates_node
