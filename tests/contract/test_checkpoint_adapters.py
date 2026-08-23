"""Checkpoint 适配器 contract 测试（方案 §21.2：版本校验和原子性；§17.1、§17.3）。

Postgres 真实读写需要可用实例，标 ``integration`` 且默认被 ``-m "not integration"``
排除；无 DSN / 无 Docker 时自动跳过。
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from typing import Any

import pytest

from shijiajing_agent.adapters.checkpoint import (
    PostgresCheckpointAdapter,
    SQLiteCheckpointAdapter,
    make_checkpoint,
)
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentRequest,
    AgentResponse,
    AgentStatus,
    CompletionReason,
    ImageContentType,
    ImageRef,
    MatchPair,
    RecognitionResult,
)
from shijiajing_agent.domain.evidence import EvidenceBundle, GroupEvidence
from shijiajing_agent.errors import CheckpointUnavailableError, SessionConflictError
from shijiajing_agent.state import SCHEMA_VERSION, AgentState, new_state


def make_state(**overrides: Any) -> AgentState:
    """构造含模型实例字段的完整状态（用于验证序列化重建）。"""
    req = AgentRequest(session_id="s1", request_id="r1", text="索尼耳机")
    state = new_state(
        schema_version=SCHEMA_VERSION,
        session_id="s1",
        request_id="r1",
        turn_id="t:test",
        trace_id="tr:test",
        current_request=req,
    )
    state["response"] = AgentResponse(
        session_id="s1",
        request_id="r1",
        turn_id="t:test",
        status=AgentStatus.SUCCESS,
        message="比价完成",
        trace_id="tr:test",
    )
    state["recognition"] = RecognitionResult(
        recognition_id="rec-1",
        category_id="headphone",
        category_name="耳机",
        brand="Sony",
        model="WH-1000XM5",
        keywords=["头戴式"],
        attributes={},
        field_confidences={"category_id": 0.95},
        overall_confidence=0.93,
    )
    state["completion_reason"] = CompletionReason.SUCCESS
    # previous_state 只由 facade 注入，不得进入持久化（§7.3）
    state["previous_state"] = new_state(
        schema_version=SCHEMA_VERSION,
        session_id="s0",
        request_id="r0",
        turn_id="t:0",
        trace_id="tr:0",
        current_request=AgentRequest(session_id="s0", request_id="r0", text="旧请求"),
    )
    state["evidence_bundle"] = EvidenceBundle(
        query_summary="Sony WH-1000XM5 耳机比价",
        groups=[
            GroupEvidence(
                group_id="spu:1",
                title="Sony WH-1000XM5",
                min_price=1999.0,
                average_price=2050.0,
                price_range="1999 ~ 2199",
                platform_names=["淘宝"],
                match_confidence=0.95,
                offer_count=3,
                hit_conditions=["价格最低"],
                missing_data=[],
                risks=["价格波动"],
                rank=1,
            )
        ],
        notices=["价格含运费"],
    )
    state["same_item_review_pairs"] = [
        MatchPair(
            offer_a_id="offer-a",
            offer_b_id="offer-b",
            same_item_score=0.7,
            hard_conflicts=["identity:color"],
            verdict="review",
        )
    ]
    state.update(overrides)
    return state


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "checkpoints.db")


@pytest.fixture
def adapter(db_path: str) -> SQLiteCheckpointAdapter:
    return SQLiteCheckpointAdapter(db_path)


class TestSQLiteCheckpoint:
    async def test_roundtrip_preserves_model_instances(self, adapter) -> None:
        state = make_state()
        version = await adapter.save("s1", state, None)
        assert version == 1
        assert state["state_version"] == 1  # §17：state_version 由 Checkpoint 维护

        loaded, loaded_version = await adapter.load("s1")
        assert loaded is not None and loaded_version == 1
        assert loaded["state_version"] == 1
        # 模型实例重建（facade 依赖 .request_id / isinstance 判断）
        assert isinstance(loaded["current_request"], AgentRequest)
        assert isinstance(loaded["response"], AgentResponse)
        assert isinstance(loaded["recognition"], RecognitionResult)
        assert loaded["response"].request_id == "r1"
        assert loaded["response"].status == AgentStatus.SUCCESS
        assert loaded["recognition"].model == "WH-1000XM5"
        assert loaded["completion_reason"] == CompletionReason.SUCCESS
        # evidence_bundle 是纯 dataclass，同样重建
        bundle = loaded["evidence_bundle"]
        assert isinstance(bundle, EvidenceBundle)
        assert isinstance(bundle.groups[0], GroupEvidence)
        assert bundle.groups[0].min_price == pytest.approx(1999.0)
        assert bundle.query_summary == "Sony WH-1000XM5 耳机比价"
        review_pairs = loaded["same_item_review_pairs"]
        assert isinstance(review_pairs[0], MatchPair)
        assert review_pairs[0].verdict == "review"
        assert review_pairs[0].hard_conflicts == ["identity:color"]

    async def test_version_increments_and_stays_consistent(self, adapter) -> None:
        state = make_state()
        v1 = await adapter.save("s1", state, None)
        v2 = await adapter.save("s1", state, v1)
        assert (v1, v2) == (1, 2)
        loaded, version = await adapter.load("s1")
        assert loaded is not None and version == 2
        assert loaded["state_version"] == 2

    async def test_persisted_request_does_not_contain_raw_input(
        self, adapter, db_path: str
    ) -> None:
        state = make_state(
            current_request=AgentRequest(
                session_id="s1",
                request_id="r1",
                text="完整用户文本",
                image=ImageRef(
                    image_id="img-1",
                    uri="data:image/png;base64,AAAA",
                    content_type=ImageContentType.PNG,
                    sha256="b" * 64,
                ),
            )
        )
        await adapter.save("s1", state, None)
        with sqlite3.connect(db_path) as conn:
            raw = conn.execute(
                "SELECT state_json FROM agent_checkpoint WHERE session_id = ?", ("s1",)
            ).fetchone()[0]
        assert "完整用户文本" not in raw
        assert "data:image/png;base64,AAAA" not in raw

        loaded, _ = await adapter.load("s1")
        assert loaded is not None
        persisted_request = loaded["current_request"]
        assert isinstance(persisted_request, AgentRequest)
        assert persisted_request.text is None
        assert persisted_request.image is not None
        assert persisted_request.image.uri.startswith("https://redacted.invalid/image/")

    async def test_optimistic_version_conflict(self, adapter) -> None:
        state = make_state()
        v1 = await adapter.save("s1", state, None)
        v2 = await adapter.save("s1", state, v1)
        with pytest.raises(SessionConflictError, match="乐观版本冲突"):
            await adapter.save("s1", state, v1)
        # 冲突后已提交版本不受影响
        _, version = await adapter.load("s1")
        assert version == v2

    async def test_conflict_when_expected_but_no_row(self, adapter) -> None:
        with pytest.raises(SessionConflictError):
            await adapter.save("missing", make_state(), 3)

    async def test_load_missing_returns_none(self, adapter) -> None:
        assert await adapter.load("nobody") is None

    async def test_schema_version_mismatch_rejected(self, db_path: str) -> None:
        # 直接种入旧 schema 版本的行（§17.1：不兼容版本不得直接加载）
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE agent_checkpoint (session_id TEXT PRIMARY KEY, state_json TEXT,"
            " state_version INTEGER, schema_version TEXT, saved_at TEXT)"
        )
        conn.execute("INSERT INTO agent_checkpoint VALUES ('s1', '{}', 5, '0.9', '2026-01-01')")
        conn.commit()
        conn.close()
        adapter = SQLiteCheckpointAdapter(db_path)
        with pytest.raises(CheckpointUnavailableError, match="需显式迁移"):
            await adapter.load("s1")

    async def test_corrupted_json_rejected(self, db_path: str) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE agent_checkpoint (session_id TEXT PRIMARY KEY, state_json TEXT,"
            " state_version INTEGER, schema_version TEXT, saved_at TEXT)"
        )
        conn.execute(
            "INSERT INTO agent_checkpoint VALUES ('s1', '{not json', 1, '1.0', '2026-01-01')"
        )
        conn.commit()
        conn.close()
        adapter = SQLiteCheckpointAdapter(db_path)
        with pytest.raises(CheckpointUnavailableError, match="数据损坏"):
            await adapter.load("s1")

    async def test_previous_state_not_persisted(self, adapter) -> None:
        state = make_state()
        assert "previous_state" in state
        await adapter.save("s1", state, None)
        loaded, _ = await adapter.load("s1")
        assert loaded is not None
        assert "previous_state" not in loaded

    async def test_restart_recovery_durability(self, db_path: str) -> None:
        """§17.4：进程重启后从最近成功 super-step 恢复。"""
        state = make_state()
        first = SQLiteCheckpointAdapter(db_path)
        await first.save("s1", state, None)
        first.close()
        second = SQLiteCheckpointAdapter(db_path)
        loaded, version = await second.load("s1")
        assert loaded is not None and version == 1
        assert loaded["response"].request_id == "r1"
        second.close()

    async def test_closed_adapter_rejects_io(self, db_path: str) -> None:
        adapter = SQLiteCheckpointAdapter(db_path)
        adapter.close()
        with pytest.raises(CheckpointUnavailableError, match="已关闭"):
            await adapter.load("s1")
        with pytest.raises(CheckpointUnavailableError, match="已关闭"):
            await adapter.save("s1", make_state(), None)

    async def test_resume_claim_is_idempotent(self, adapter) -> None:
        first, second, other = await asyncio.gather(
            adapter.claim_resume("resume-session", "interrupt-1"),
            adapter.claim_resume("resume-session", "interrupt-1"),
            adapter.claim_resume("resume-session", "interrupt-2"),
        )
        assert sorted((first, second)) == [False, True]
        assert other is True

    async def test_resume_claim_can_be_released_for_retry(self, adapter) -> None:
        assert await adapter.claim_resume("resume-release", "interrupt-1") is True
        await adapter.release_resume("resume-release", "interrupt-1")
        assert await adapter.claim_resume("resume-release", "interrupt-1") is True

    async def test_empty_dsn_rejected(self) -> None:
        with pytest.raises(ValueError, match="CHECKPOINT_DSN"):
            SQLiteCheckpointAdapter("")

    async def test_make_checkpoint_backend_selection(self, tmp_path) -> None:
        sqlite = make_checkpoint(
            Settings(checkpoint_backend="sqlite", checkpoint_dsn=str(tmp_path / "c.db"))
        )
        assert isinstance(sqlite, SQLiteCheckpointAdapter)
        with pytest.raises(ValueError, match="未知 checkpoint_backend"):
            make_checkpoint(Settings(checkpoint_backend="memory"))

    async def test_dsn_prefix_stripped(self, tmp_path) -> None:
        path = tmp_path / "prefixed.db"
        adapter = SQLiteCheckpointAdapter(f"sqlite:///{path}")
        await adapter.save("s1", make_state(), None)
        loaded, _ = await adapter.load("s1")
        assert loaded is not None
        # 真实文件落盘（前缀被剥离，而非创建名为 sqlite:// 的目录）
        assert path.exists()

    async def test_two_sessions_independent_versions(self, adapter) -> None:
        """不同 session 各自版本独立（§17.3 不同 session 可并发执行）。"""
        a = await adapter.save("a", make_state(), None)
        b = await adapter.save("b", make_state(), None)
        assert (a, b) == (1, 1)
        a2 = await adapter.save("a", make_state(), a)
        b2 = await adapter.save("b", make_state(), b)
        assert (a2, b2) == (2, 2)

    async def test_state_json_schema_version_stored(self, adapter) -> None:
        await adapter.save("s1", make_state(), None)
        raw = json.loads(
            adapter._connect().execute("SELECT state_json FROM agent_checkpoint").fetchone()[0]
        )
        assert raw["schema_version"] == SCHEMA_VERSION
        assert "previous_state" not in raw


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("SHIJIAJING_TEST_POSTGRES_DSN")
    and os.environ.get("SHIJIAJING_REQUIRE_POSTGRES") != "1",
    reason="需要 SHIJIAJING_TEST_POSTGRES_DSN 指向可用 Postgres",
)
class TestPostgresCheckpointAdapter:
    @pytest.fixture
    async def pg_adapter(self):
        dsn = os.environ.get("SHIJIAJING_TEST_POSTGRES_DSN")
        if not dsn:
            pytest.fail("SHIJIAJING_TEST_POSTGRES_DSN 必须指向可用 Postgres")
        adapter = PostgresCheckpointAdapter(dsn)
        yield adapter
        await adapter.close()

    async def test_roundtrip_and_conflict(self, pg_adapter) -> None:
        state = make_state()
        v1 = await pg_adapter.save("pg-1", state, None)
        assert v1 == 1
        loaded, version = await pg_adapter.load("pg-1")
        assert loaded is not None and version == 1
        assert isinstance(loaded["response"], AgentResponse)
        with pytest.raises(SessionConflictError):
            await pg_adapter.save("pg-1", state, v1 + 10)

    async def test_concurrent_saves_serialized_by_advisory_lock(self, pg_adapter) -> None:
        """§17.3：同 session 并发写被 advisory lock 串行化，最终版本为 2 且无异常。"""
        import asyncio

        state = make_state()
        results = await asyncio.gather(
            pg_adapter.save("pg-lock", state, None),
            pg_adapter.save("pg-lock", state, None),
        )
        assert sorted(results) == [1, 2]
        _, version = await pg_adapter.load("pg-lock")
        assert version == 2

    async def test_resume_claim_is_idempotent(self, pg_adapter) -> None:
        import asyncio

        results = await asyncio.gather(
            pg_adapter.claim_resume("pg-resume", "interrupt-1"),
            pg_adapter.claim_resume("pg-resume", "interrupt-1"),
        )
        assert sorted(results) == [False, True]

    async def test_resume_claim_can_be_released_for_retry(self, pg_adapter) -> None:
        assert await pg_adapter.claim_resume("pg-resume-release", "interrupt-1") is True
        await pg_adapter.release_resume("pg-resume-release", "interrupt-1")
        assert await pg_adapter.claim_resume("pg-resume-release", "interrupt-1") is True

    async def test_empty_dsn_rejected(self) -> None:
        with pytest.raises(ValueError, match="CHECKPOINT_DSN"):
            PostgresCheckpointAdapter("")


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("SHIJIAJING_TEST_DOCKER") != "1"
    and os.environ.get("SHIJIAJING_REQUIRE_POSTGRES") != "1",
    reason="需要 SHIJIAJING_TEST_DOCKER=1 且本机可用 Docker",
)
class TestPostgresViaTestcontainers:
    async def test_restart_recovery(self) -> None:
        from testcontainers.community.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine") as pg:
            dsn = pg.get_connection_url()
            adapter = PostgresCheckpointAdapter(dsn)
            try:
                state = make_state()
                await adapter.save("tc-1", state, None)
                loaded, version = await adapter.load("tc-1")
                assert loaded is not None and version == 1
                assert loaded["response"].request_id == "r1"
            finally:
                await adapter.close()
