"""runtime 资源生命周期辅助函数的同步/异步兼容测试。"""

from __future__ import annotations

from contextlib import AsyncExitStack
from types import SimpleNamespace

import pytest

from shijiajing_agent.config import Settings
from shijiajing_agent.domain.taxonomy import load_taxonomy
from shijiajing_agent.facade import AgentDependencies
from shijiajing_agent.runtime import (
    _open_resource,
    _register_resource_close,
    open_agent_runtime,
)


class _SyncResource:
    def __init__(self) -> None:
        self.setup_calls = 0
        self.close_calls = 0

    def setup(self) -> None:
        self.setup_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class _AsyncResource:
    def __init__(self) -> None:
        self.setup_calls = 0
        self.close_calls = 0

    async def setup(self) -> None:
        self.setup_calls += 1

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_open_resource_supports_sync_and_async_lifecycle() -> None:
    sync_resource = _SyncResource()
    async_resource = _AsyncResource()

    async with AsyncExitStack() as stack:
        assert await _open_resource(stack, sync_resource) is sync_resource
        assert await _open_resource(stack, async_resource) is async_resource
        assert sync_resource.setup_calls == 1
        assert async_resource.setup_calls == 1
        assert sync_resource.close_calls == 0
        assert async_resource.close_calls == 0

    assert sync_resource.close_calls == 1
    assert async_resource.close_calls == 1


@pytest.mark.asyncio
async def test_open_resource_closes_when_setup_fails() -> None:
    class FailingResource:
        close_calls = 0

        async def setup(self) -> None:
            raise RuntimeError("simulated setup failure")

        async def close(self) -> None:
            FailingResource.close_calls += 1

    resource = FailingResource()
    async with AsyncExitStack() as stack:
        with pytest.raises(RuntimeError, match="simulated setup failure"):
            await _open_resource(stack, resource)

    assert FailingResource.close_calls == 1


@pytest.mark.asyncio
async def test_open_resource_preserves_setup_error_when_close_also_fails() -> None:
    class FailingResource:
        async def setup(self) -> None:
            raise RuntimeError("setup is the root cause")

        async def close(self) -> None:
            raise RuntimeError("close is a cleanup error")

    async with AsyncExitStack() as stack:
        with pytest.raises(RuntimeError, match="setup is the root cause"):
            await _open_resource(stack, FailingResource())


@pytest.mark.asyncio
async def test_runtime_closes_constructed_resources_when_early_setup_fails() -> None:
    close_order: list[str] = []

    class FailingTrace:
        async def setup(self) -> None:
            raise RuntimeError("trace setup failed")

        async def close(self) -> None:
            close_order.append("trace")

    class ConstructedResource:
        def __init__(self, name: str) -> None:
            self._name = name

        async def setup(self) -> None:
            return None

        async def close(self) -> None:
            close_order.append(self._name)

    trace = FailingTrace()
    vision = ConstructedResource("vision")
    retrieval = ConstructedResource("retrieval")
    checkpoint = ConstructedResource("checkpoint")

    def deps_factory(_: object) -> SimpleNamespace:
        return SimpleNamespace(
            settings=Settings(),
            trace=trace,
            vision=vision,
            retrieval=retrieval,
            checkpoint=checkpoint,
        )

    with pytest.raises(RuntimeError, match="trace setup failed"):
        async with open_agent_runtime(Settings(), deps_factory=deps_factory):
            raise AssertionError("runtime should not yield after setup failure")

    assert close_order == ["checkpoint", "retrieval", "vision", "trace"]


@pytest.mark.asyncio
async def test_runtime_closes_registered_resources_when_dependency_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    close_order: list[str] = []

    class ConstructedResource:
        def __init__(self, name: str, *, fail_on_close: bool = False) -> None:
            self._name = name
            self._fail_on_close = fail_on_close

        async def setup(self) -> None:
            return None

        async def close(self) -> None:
            close_order.append(self._name)
            if self._fail_on_close:
                raise RuntimeError("cleanup failure")

    trace = ConstructedResource("trace")
    vision = ConstructedResource("vision", fail_on_close=True)

    def failing_make_deps(_: Settings, *, resource_registrar) -> None:
        resource_registrar(trace)
        resource_registrar(vision)
        raise RuntimeError("dependency construction failed")

    monkeypatch.setattr("shijiajing_agent.runtime.make_deps", failing_make_deps)

    with pytest.raises(RuntimeError, match="dependency construction failed"):
        async with open_agent_runtime(Settings()):
            raise AssertionError("runtime should not yield after construction failure")

    assert close_order == ["vision", "trace"]


@pytest.mark.asyncio
async def test_resource_registration_is_identity_deduplicated() -> None:
    class Resource:
        def __init__(self) -> None:
            self.close_calls = 0

        async def setup(self) -> None:
            pass

        async def close(self) -> None:
            self.close_calls += 1

    resource = Resource()
    async with AsyncExitStack() as stack:
        await _open_resource(stack, resource)
        _register_resource_close(stack, resource)

    assert resource.close_calls == 1


@pytest.mark.asyncio
async def test_runtime_preserves_configured_supervisor_planner() -> None:
    settings = Settings(supervisor_planner_mode="shadow", supervisor_model="planner-test")
    planner = object()
    deps = AgentDependencies(
        taxonomy=load_taxonomy(settings.taxonomy_path_resolved),
        settings=settings,
        vision=_AsyncResource(),
        intent=SimpleNamespace(),
        query_rewrite=SimpleNamespace(),
        explanation=SimpleNamespace(),
        retrieval=_AsyncResource(),
        checkpoint=_AsyncResource(),
        trace=_AsyncResource(),
        metrics=SimpleNamespace(),
        supervisor_planner=planner,  # type: ignore[arg-type]
    )

    async with open_agent_runtime(settings, deps_factory=lambda _: deps) as facade:
        assert facade.dependencies.supervisor_planner is planner
