"""LangGraph PostgreSQL native Checkpointer contract。"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.base import empty_checkpoint

from shijiajing_agent.adapters.langgraph_persistence import open_graph_checkpointer
from shijiajing_agent.config import Settings

pytestmark = pytest.mark.integration


async def test_postgres_native_checkpointer_setup_and_teardown(postgres_dsn: str) -> None:
    settings = Settings(checkpoint_backend="postgres", checkpoint_dsn=postgres_dsn)
    async with open_graph_checkpointer(settings) as saver:
        assert saver is not None


async def test_postgres_native_checkpointer_save_resume_history_delete(
    postgres_dsn: str,
) -> None:
    """验证原生 saver 的 §15.1 setup/save/resume/history/delete 契约。"""

    settings = Settings(checkpoint_backend="postgres", checkpoint_dsn=postgres_dsn)
    thread_id = "contract-native-checkpointer"
    base_config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": "",
        }
    }

    async with open_graph_checkpointer(settings) as saver:
        await saver.setup()

        first_checkpoint = empty_checkpoint()
        first_config = await saver.aput(
            base_config,
            first_checkpoint,
            {"source": "input", "step": -1, "parents": {}},
            {},
        )
        assert first_config["configurable"]["checkpoint_id"] == first_checkpoint["id"]

        second_checkpoint = empty_checkpoint()
        second_config = await saver.aput(
            first_config,
            second_checkpoint,
            {"source": "loop", "step": 0, "parents": {}},
            {},
        )

        latest = await saver.aget_tuple(base_config)
        assert latest is not None
        assert latest.checkpoint["id"] == second_checkpoint["id"]
        assert latest.parent_config == first_config

        history = [item async for item in saver.alist(base_config)]
        assert [item.checkpoint["id"] for item in history] == [
            second_checkpoint["id"],
            first_checkpoint["id"],
        ]

        first = await saver.aget_tuple(first_config)
        assert first is not None
        assert first.checkpoint["id"] == first_checkpoint["id"]

        await saver.adelete_thread(thread_id)
        assert await saver.aget_tuple(base_config) is None
        assert [item async for item in saver.alist(base_config)] == []

        # Keep the returned config in the contract: it is the resume handle
        # produced by the native saver after the second write.
        assert second_config["configurable"]["checkpoint_id"] == second_checkpoint["id"]
