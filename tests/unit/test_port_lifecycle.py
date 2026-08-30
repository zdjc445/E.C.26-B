"""二期 runtime-managed Port 的 setup/close 结构化契约。"""

from __future__ import annotations

from inspect import isawaitable

import pytest

from shijiajing_agent.adapters.ark_models import ArkVisionModel
from shijiajing_agent.adapters.cache import InMemoryVersionedCache
from shijiajing_agent.adapters.event_store import InMemoryEventStore
from shijiajing_agent.adapters.local_retrieval import LocalLexicalRetrievalAdapter
from shijiajing_agent.adapters.memory import DisabledMemoryAdapter
from shijiajing_agent.adapters.observability import (
    OpenTelemetryTraceSink,
    StructlogTraceSink,
)
from shijiajing_agent.adapters.request_ledger import InMemoryRequestLedger
from shijiajing_agent.evals_live import CallCounts, CountedRetrieval, CountedVision
from shijiajing_agent.ports.cache import VersionedCachePort
from shijiajing_agent.ports.event_store import EventStorePort
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort
from shijiajing_agent.ports.memory import MemoryPort
from shijiajing_agent.ports.models import VisionModelPort
from shijiajing_agent.ports.observability import TraceSinkPort
from shijiajing_agent.ports.request_ledger import RequestLedgerPort
from shijiajing_agent.ports.retrieval import ProductRetrievalPort


def test_persistence_ports_declare_runtime_lifecycle(tmp_path) -> None:
    resources_and_ports = (
        (InMemoryRequestLedger(), RequestLedgerPort),
        (DisabledMemoryAdapter(), MemoryPort),
        (InMemoryVersionedCache(), VersionedCachePort),
        (InMemoryEventStore(), EventStorePort),
    )

    for resource, port in resources_and_ports:
        assert isinstance(resource, ResourceLifecyclePort)
        assert isinstance(resource, port)


@pytest.mark.asyncio
async def test_retrieval_and_trace_ports_declare_runtime_lifecycle(tmp_path) -> None:
    class LifecycleClient:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    vision = ArkVisionModel(LifecycleClient())
    resources_and_ports = (
        (LocalLexicalRetrievalAdapter(tmp_path / "snapshot.jsonl"), ProductRetrievalPort),
        (StructlogTraceSink(), TraceSinkPort),
        (OpenTelemetryTraceSink(), TraceSinkPort),
        (vision, VisionModelPort),
    )

    for resource, port in resources_and_ports:
        assert isinstance(resource, ResourceLifecyclePort)
        assert isinstance(resource, port)
        setup_result = resource.setup()
        if isawaitable(setup_result):
            await setup_result
        close_result = resource.close()
        if isawaitable(close_result):
            await close_result


@pytest.mark.asyncio
async def test_counted_retrieval_delegates_runtime_lifecycle() -> None:
    class InnerRetrieval:
        def __init__(self) -> None:
            self.setup_calls = 0
            self.close_calls = 0

        async def setup(self) -> None:
            self.setup_calls += 1

        async def close(self) -> None:
            self.close_calls += 1

        async def search(self, query, **kwargs):
            del query, kwargs
            raise AssertionError("search is not part of this lifecycle test")

    inner = InnerRetrieval()
    counted = CountedRetrieval(inner, CallCounts())
    await counted.setup()
    await counted.close()

    assert inner.setup_calls == 1
    assert inner.close_calls == 1


@pytest.mark.asyncio
async def test_counted_vision_delegates_runtime_lifecycle() -> None:
    class InnerVision:
        def __init__(self) -> None:
            self.setup_calls = 0
            self.close_calls = 0

        async def setup(self) -> None:
            self.setup_calls += 1

        async def close(self) -> None:
            self.close_calls += 1

        async def recognize(self, image, taxonomy):
            del image, taxonomy
            raise AssertionError("recognize is not part of this lifecycle test")

    inner = InnerVision()
    counted = CountedVision(inner, CallCounts())
    await counted.setup()
    await counted.close()

    assert inner.setup_calls == 1
    assert inner.close_calls == 1
