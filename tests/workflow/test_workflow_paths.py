"""Workflow 路径测试（方案 §21.3 的 17 条路径）。

全部通过 Fake Ports 注入确定性行为；不依赖任何真实模型或外部服务。
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

import pytest

from shijiajing_agent.contracts import (
    AgentRequest,
    AgentStatus,
    ConstraintSource,
    HardFilters,
    RecognitionCorrection,
    RetrievalQuery,
)
from shijiajing_agent.domain.same_item import SameItemMatcher
from shijiajing_agent.errors import (
    ModelOutputInvalidError,
    RequestLedgerUnavailableError,
    VisionUnavailableError,
)
from shijiajing_agent.graph import build_graph
from shijiajing_agent.nodes.input_nodes import make_initial_state
from shijiajing_agent.ports.retrieval import RetrievalResult

from .conftest import WorkflowSettings as Settings
from .conftest import make_image, two_candidate_result, two_sku_result


def req(*, text: str | None = None, request_id: str | None = None, **kwargs: Any) -> AgentRequest:
    kwargs.setdefault("session_id", "s1")
    kwargs["request_id"] = request_id or f"req-{uuid.uuid4().hex[:8]}"
    kwargs["text"] = text
    return AgentRequest(**kwargs)


# ---------------------------------------------------------------------------
# 1. 纯文本成功路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_success_full_pipeline(deps_factory: Any, facade_factory: Any) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result()]

    response = await facade_factory(deps).run(req(text="索尼耳机 预算2000以内"))

    assert response.status == AgentStatus.SUCCESS
    assert response.groups, "应产出比价组"
    assert len(response.groups) == 1
    assert response.groups[0].group.min_price == 1899.0
    assert response.groups[0].group.offer_count == 2
    assert response.effective_constraints is not None
    assert response.effective_constraints.category_id.value == "headphone"
    assert response.effective_constraints.brand.source == ConstraintSource.USER_TEXT
    assert response.effective_constraints.max_price.value == 2000.0
    assert response.trace_id
    assert "1899" in response.message


@pytest.mark.asyncio
async def test_matching_candidate_limit_truncates_after_retrieval(
    deps_factory: Any, facade_factory: Any
) -> None:
    settings = replace(Settings(), matching_candidate_limit=1)
    deps, fakes = deps_factory(settings)
    fakes["retrieval"].sequence = [two_candidate_result()]

    response = await facade_factory(deps).run(req(text="索尼耳机", request_id="matching-limit"))

    assert response.groups
    assert response.groups[0].group.offer_count == 1
    saved_state = fakes["checkpoint"].store["s1"][0]
    assert len(saved_state["candidates"]) == 2
    assert len(saved_state["normalized_candidates"]) == 1
    assert "同款匹配候选超过上限，已截断至 1 条" in saved_state["notices"]


@pytest.mark.asyncio
async def test_legacy_recent_turns_are_independent_of_long_term_memory(
    deps_factory: Any, facade_factory: Any
) -> None:
    """legacy workflow 也必须在长期 Memory 关闭时恢复并追加 bounded conversation memory。"""
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result(), two_candidate_result()]
    facade = facade_factory(deps)

    first = await facade.run(req(text="索尼耳机", request_id="r1"))
    second = await facade.run(req(text="索尼耳机", request_id="r2"))

    assert first.status == AgentStatus.SUCCESS
    assert second.status == AgentStatus.SUCCESS
    saved = fakes["checkpoint"].store["s1"][0]
    assert [summary.request_id for summary in saved["recent_turns"]] == ["r1", "r2"]


@pytest.mark.asyncio
async def test_legacy_run_maps_request_ledger_write_failure_to_typed_response(
    deps_factory: Any, facade_factory: Any
) -> None:
    deps, _ = deps_factory()

    class FailingLedger:
        async def get_response(self, session_id: str, request_id: str) -> None:
            del session_id, request_id
            return None

        async def save_response(
            self, session_id: str, request_id: str, response: Any, expected_absent: bool = True
        ) -> None:
            del session_id, request_id, response, expected_absent
            raise RequestLedgerUnavailableError("injected ledger write failure")

    deps.request_ledger = FailingLedger()
    response = await facade_factory(deps).run(req(text="索尼耳机", request_id="ledger-write"))

    assert response.status is AgentStatus.FAILED
    assert response.message == "请求结果账本不可用，请稍后重试。"


@pytest.mark.asyncio
async def test_recognition_intent_barrier_precedes_constraint_merge(
    deps_factory: Any, facade_factory: Any
) -> None:
    """两条 understanding 分支都完成后才允许进入 join/约束合并。"""
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result()]

    response = await facade_factory(deps).run(req(text="索尼耳机"))

    assert response.status == AgentStatus.SUCCESS
    edges = {(edge.source, edge.target) for edge in build_graph(deps).get_graph().edges}
    assert ("recognition_done", "join_understanding") in edges
    assert ("intent_done", "join_understanding") in edges
    assert ("join_understanding", "merge_constraints") in edges


# ---------------------------------------------------------------------------
# 2. 无品类 → 澄清
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_category_clarification(deps_factory: Any, facade_factory: Any) -> None:
    deps, _ = deps_factory()

    response = await facade_factory(deps).run(req(text="帮我比个价"))

    assert response.status == AgentStatus.CLARIFICATION
    assert response.clarification is not None
    assert response.clarification.question
    assert response.clarification.reason_code == "MISSING_CATEGORY"
    assert "category_id" in response.clarification.missing_fields
    assert response.message == "需要补充信息后继续比价。"


# ---------------------------------------------------------------------------
# 3. 图片识别成功路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_recognition_success(deps_factory: Any, facade_factory: Any) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result()]

    response = await facade_factory(deps).run(req(text="这个怎么样", image=make_image()))

    assert response.status == AgentStatus.SUCCESS
    assert fakes["vision"].calls == 1
    assert response.recognition is not None
    assert response.recognition.category_id == "headphone"
    assert response.effective_constraints is not None
    assert response.effective_constraints.brand.source == ConstraintSource.VISION
    assert response.groups


# ---------------------------------------------------------------------------
# 4. 图片识别失败 + 文字提供品类 → 继续
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_failure_continues_with_text_category(
    deps_factory: Any, facade_factory: Any
) -> None:
    deps, fakes = deps_factory()
    fakes["vision"].errors = [VisionUnavailableError("vlm 服务不可用")]
    fakes["retrieval"].sequence = [two_candidate_result()]

    response = await facade_factory(deps).run(req(text="索尼耳机", image=make_image()))

    assert response.status == AgentStatus.SUCCESS
    assert response.recognition is None
    assert any("图片识别不可用" in n for n in response.notices)
    assert response.groups
    # 识别错误被记录到 errors（trace 可审计）
    saved = fakes["checkpoint"].store["s1"][0]
    assert any(e["error_code"] == "VISION_UNAVAILABLE" for e in saved.get("errors", []))


# ---------------------------------------------------------------------------
# 5. 用户修正跳过 VLM（vision 调用数不增加）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correction_skips_vlm(deps_factory: Any, facade_factory: Any) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result(), two_candidate_result()]
    facade = facade_factory(deps)

    r1 = await facade.run(req(text="这个怎么样", image=make_image(), request_id="r1"))
    assert r1.status == AgentStatus.SUCCESS
    assert fakes["vision"].calls == 1
    rec_id = r1.recognition.recognition_id

    r2 = await facade.run(
        req(
            text=None,
            request_id="r2",
            correction=RecognitionCorrection(
                recognition_id=rec_id,
                brand="Sony",
                model="WH-1000XM4",
            ),
        )
    )
    assert r2.status == AgentStatus.SUCCESS
    assert fakes["vision"].calls == 1, "修正轮不得再次调用 VLM"
    assert r2.recognition is not None
    assert r2.recognition.model == "WH 1000XM4"
    assert r2.effective_constraints.brand.source == ConstraintSource.USER_CORRECTION
    assert fakes["retrieval"].calls == 2, "品牌来源变化应触发重查"


# ---------------------------------------------------------------------------
# 6. 仅排序变化 → 复用识别/改写/检索/匹配缓存
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sort_only_rerun_reuses_cache(deps_factory: Any, facade_factory: Any) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_sku_result()]
    facade = facade_factory(deps)

    r1 = await facade.run(req(text="索尼耳机", request_id="r1"))
    assert r1.status == AgentStatus.SUCCESS
    calls_after_t1 = {
        "vision": fakes["vision"].calls,
        "rewrite": fakes["rewrite"].calls,
        "retrieval": fakes["retrieval"].calls,
        "match": 0,  # 无法直接计数，改用 retrieval 代理
    }

    r2 = await facade.run(req(text="按价格排序", request_id="r2"))

    assert r2.status == AgentStatus.SUCCESS
    # 排序变化只重排：识别/改写/检索都不重跑
    assert fakes["vision"].calls == calls_after_t1["vision"]
    assert fakes["rewrite"].calls == calls_after_t1["rewrite"]
    assert fakes["retrieval"].calls == calls_after_t1["retrieval"]
    assert r2.groups[0].group.min_price == 1799.0, "价格升序后最便宜组排第一"
    # 同款匹配确实未重跑：SPU 聚类结果复用（白 1799 / 黑 1899 两组不变）
    assert len(r2.groups) == 2


# ---------------------------------------------------------------------------
# 7. 硬预算零结果 → 不放宽，直接无结果
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_budget_zero_results_no_relax(deps_factory: Any, facade_factory: Any) -> None:
    deps, fakes = deps_factory()  # 检索默认零结果
    fakes["retrieval"].sequence = []  # 显式零结果

    response = await facade_factory(deps).run(req(text="索尼耳机 预算500以内"))

    assert response.status == AgentStatus.NO_RESULTS
    assert response.message == "当前条件下没有符合要求的比价结果。"
    saved = fakes["checkpoint"].store["s1"][0]
    assert saved.get("relaxation_attempted") is True
    assert saved.get("relaxed_attributes") == [], "预算属于用户硬过滤，不允许放宽"
    assert fakes["retrieval"].calls == 1, "不重查"


# ---------------------------------------------------------------------------
# 8. 图片识别硬过滤零结果 → 放宽 model→brand 后重查成功
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_hard_filter_relax_then_requery(
    deps_factory: Any, facade_factory: Any
) -> None:
    deps, fakes = deps_factory()
    # 第一次检索零结果，放宽后第二次返回结果
    fakes["retrieval"].sequence = [
        RetrievalResult(candidates=[], total_found=0),
        two_candidate_result(),
    ]

    response = await facade_factory(deps).run(req(text="这个怎么样", image=make_image()))

    assert response.status == AgentStatus.SUCCESS
    assert fakes["retrieval"].calls == 2
    assert any("已放宽图片识别的型号条件" in n for n in response.notices)
    assert any("已放宽图片识别的品牌条件" in n for n in response.notices)
    saved = fakes["checkpoint"].store["s1"][0]
    assert saved.get("relaxed_attributes") == ["model", "brand"]
    # 放宽后的重查必须使用放宽后的查询（模型改写不会撤销放宽）
    assert saved.get("retrieval_query").hard_filters.model is None
    assert saved.get("retrieval_query").hard_filters.brand is None
    # soft_terms 中的型号是 §12.3 标准化后的形式（分隔符统一为空格）
    assert "WH 1000XM5" in saved.get("retrieval_query").soft_terms
    assert "Sony" in saved.get("retrieval_query").soft_terms


# ---------------------------------------------------------------------------
# 9. 意图模型输出非法 → 规则解析兜底
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_intent_output_falls_back_to_rules(
    deps_factory: Any, facade_factory: Any
) -> None:
    deps, fakes = deps_factory()
    fakes["intent"].errors = [ModelOutputInvalidError("输出不是合法 JSON")]
    fakes["retrieval"].sequence = [two_candidate_result()]

    response = await facade_factory(deps).run(req(text="索尼耳机 2000以内"))

    assert response.status == AgentStatus.SUCCESS
    assert response.effective_constraints.brand.value == "Sony"
    assert response.effective_constraints.max_price.value == 2000.0
    assert any("意图模型不可用" in n for n in response.notices)
    saved = fakes["checkpoint"].store["s1"][0]
    assert any(
        f.get("node_name") == "parse_intent" and f.get("fallback_provider") == "rules"
        for f in saved.get("fallbacks", [])
    )


# ---------------------------------------------------------------------------
# 10. 查询改写篡改硬过滤 → 拒绝并走确定性拼接
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_rewrite_tampering_rejected(deps_factory: Any, facade_factory: Any) -> None:
    deps, fakes = deps_factory()
    fakes["rewrite"].results = [
        RetrievalQuery(query_text="索尼耳机", hard_filters=HardFilters(brand="Bose"))
    ]
    fakes["retrieval"].sequence = [two_candidate_result()]

    response = await facade_factory(deps).run(req(text="索尼耳机"))

    assert response.status == AgentStatus.SUCCESS
    # 检索使用的必须是确定性 base（品牌 Sony），篡改值被拒绝
    assert fakes["retrieval"].last_query is not None
    assert fakes["retrieval"].last_query.hard_filters.brand == "Sony"
    saved = fakes["checkpoint"].store["s1"][0]
    assert any(
        f.get("node_name") == "rewrite_query" and f.get("fallback_provider") == "deterministic"
        for f in saved.get("fallbacks", [])
    )
    assert any("篡改硬过滤" in n for n in response.notices)


# ---------------------------------------------------------------------------
# 11. Milvus 超时 → 本地词法降级（fallback_used）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_local_fallback_on_unavailable(
    deps_factory: Any, facade_factory: Any
) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [
        RetrievalResult(
            candidates=two_candidate_result().candidates,
            total_found=2,
            fallback_used=True,
            fallback_reason="milvus_timeout",
            channel_counts={"sparse": 2},
        )
    ]

    response = await facade_factory(deps).run(req(text="索尼耳机"))

    assert response.status == AgentStatus.SUCCESS
    assert any("本地词法索引" in n for n in response.notices)
    saved = fakes["checkpoint"].store["s1"][0]
    assert saved.get("retrieval_fallback_used") is True
    assert any(
        f.get("node_name") == "retrieve_candidates"
        and f.get("fallback_provider") == "local_lexical"
        for f in saved.get("fallbacks", [])
    )


# ---------------------------------------------------------------------------
# 12. 同款匹配异常 → 独立展示，不误比价
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matching_exception_independent_display(
    deps_factory: Any, facade_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_sku_result()]

    def boom(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("matcher exploded")

    monkeypatch.setattr(SameItemMatcher, "cluster", boom)

    response = await facade_factory(deps).run(req(text="索尼耳机"))

    assert response.status == AgentStatus.SUCCESS
    assert any("同款匹配异常" in n for n in response.notices)
    # 两个候选独立成组
    assert len(response.groups) == 2
    saved = fakes["checkpoint"].store["s1"][0]
    assert saved.get("spu_clusters") == [[0], [1]]
    assert all(
        "matcher exploded" not in str(error.get("message")) for error in saved.get("errors", [])
    )


# ---------------------------------------------------------------------------
# 13. 解释幻觉 → 事实校验失败 → 模板解释
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explanation_hallucination_uses_template(
    deps_factory: Any, facade_factory: Any
) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result()]
    fakes["explanation"].results = ["该商品最低 1 元，来自拼多多。"]  # 数字/平台均不在证据中

    response = await facade_factory(deps).run(req(text="索尼耳机"))

    assert response.status == AgentStatus.SUCCESS
    assert response.message.startswith("为您找到以下同款商品报价：")
    assert "1 元" not in response.message
    assert response.groups[0].explanation_verified is False
    saved = fakes["checkpoint"].store["s1"][0]
    assert any(
        f.get("node_name") == "generate_explanation"
        and f.get("reason") == "factual_check_failed"
        and f.get("fallback_provider") == "template"
        for f in saved.get("fallbacks", [])
    )


# ---------------------------------------------------------------------------
# 14. 重复 request_id → 幂等返回，不重复调用外部依赖
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_request_id_idempotent(deps_factory: Any, facade_factory: Any) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result()]
    facade = facade_factory(deps)
    first_req = req(text="索尼耳机", request_id="same-id")

    r1 = await facade.run(first_req)
    assert r1.status == AgentStatus.SUCCESS
    snapshot = {
        "vision": fakes["vision"].calls,
        "intent": fakes["intent"].calls,
        "rewrite": fakes["rewrite"].calls,
        "explanation": fakes["explanation"].calls,
        "retrieval": fakes["retrieval"].calls,
    }

    r2 = await facade.run(first_req)

    assert r2.request_id == r1.request_id
    assert r2.status == AgentStatus.SUCCESS
    assert r2.turn_id == r1.turn_id
    assert fakes["vision"].calls == snapshot["vision"]
    assert fakes["intent"].calls == snapshot["intent"]
    assert fakes["rewrite"].calls == snapshot["rewrite"]
    assert fakes["explanation"].calls == snapshot["explanation"]
    assert fakes["retrieval"].calls == snapshot["retrieval"]


# ---------------------------------------------------------------------------
# 15. 中断恢复：上一轮未完成 → 从最近成功点继续
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_from_partial_checkpoint(deps_factory: Any, facade_factory: Any) -> None:
    deps, fakes = deps_factory()
    # 第一轮通过图直跑完整流程，产出带全部缓存的最终状态
    graph = build_graph(deps)
    fakes["retrieval"].sequence = [two_candidate_result()]
    t1_req = req(text="索尼耳机", request_id="t1")
    state = make_initial_state(t1_req, None)
    final_state = await graph.ainvoke(state)
    # 模拟进程在保存最终响应前中断：去掉 response
    final_state["response"] = None
    final_state["node_events"] = [
        e for e in final_state.get("node_events", []) if e["node_name"] != "build_response"
    ]
    final_state["state_version"] = 3
    fakes["checkpoint"].seed("s1", final_state, version=3)

    calls_before = {
        "rewrite": fakes["rewrite"].calls,
        "retrieval": fakes["retrieval"].calls,
        "vision": fakes["vision"].calls,
    }

    # 新请求：只改排序 → 全部缓存复用
    response = await facade_factory(deps).run(req(text="按价格排序", request_id="t2"))

    assert response.status == AgentStatus.SUCCESS
    saved = fakes["checkpoint"].store["s1"][0]
    assert saved.get("is_resumed") is True
    assert saved.get("resumed_node") == "generate_explanation"
    # 中断恢复后不重跑已完成的识别/改写/检索
    assert fakes["rewrite"].calls == calls_before["rewrite"]
    assert fakes["retrieval"].calls == calls_before["retrieval"]
    assert fakes["vision"].calls == calls_before["vision"]


# ---------------------------------------------------------------------------
# 16. 乐观版本冲突 → 重放一次 → 再冲突返回 SESSION_CONFLICT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_conflict_replay_once_then_failed(
    deps_factory: Any, facade_factory: Any
) -> None:
    deps, fakes = deps_factory()
    fakes["checkpoint"].conflict_on_save = True

    response = await facade_factory(deps).run(req(text="索尼耳机"))

    assert response.status == AgentStatus.FAILED
    assert "冲突" in response.message
    # 两个回合各启动了一次（首次 + 重放）
    turn_started = [e for e in fakes["trace"].events if e.event_type.value == "turn_started"]
    assert len(turn_started) == 2


# ---------------------------------------------------------------------------
# 17. 步数超限 → FAILED 且保留 trace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_step_limit_failed_with_trace(
    deps_factory: Any, facade_factory: Any
) -> None:
    settings = Settings(max_workflow_steps=1)
    deps, fakes = deps_factory(settings=settings)

    response = await facade_factory(deps).run(req(text="索尼耳机"))

    assert response.status == AgentStatus.FAILED
    assert "上限" in response.message
    assert response.trace_id
    saved = fakes["checkpoint"].store["s1"][0]
    assert saved.get("trace_id") == response.trace_id
    assert any(e.get("error_code") == "WORKFLOW_STEP_LIMIT" for e in saved.get("errors", []))
    # 失败状态本身也被保存（保留 Checkpoint）
    assert saved.get("response") is not None
    assert saved.get("response").status == AgentStatus.FAILED
    assert [summary.request_id for summary in saved["recent_turns"]] == [response.request_id]
