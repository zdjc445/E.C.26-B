"""生产 runtime 的异步资源生命周期。"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from inspect import isawaitable
from weakref import WeakKeyDictionary

from shijiajing_agent.adapters.cache import make_cache_adapter
from shijiajing_agent.adapters.event_store import make_event_store_adapter
from shijiajing_agent.adapters.langgraph_persistence import open_graph_checkpointer
from shijiajing_agent.adapters.memory import make_memory_adapter
from shijiajing_agent.adapters.request_ledger import make_request_ledger
from shijiajing_agent.config import Settings
from shijiajing_agent.deps import make_deps
from shijiajing_agent.facade import AgentDependencies, AgentFacade
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort

_SETUP_FAILED_STACKS: WeakKeyDictionary[AsyncExitStack, bool] = WeakKeyDictionary()
_REGISTERED_RESOURCES: WeakKeyDictionary[AsyncExitStack, set[int]] = WeakKeyDictionary()


async def open_resource[ResourceT: ResourceLifecyclePort](
    stack: AsyncExitStack, resource: ResourceT | None
) -> ResourceT | None:
    if resource is None:
        return None
    _register_resource_close(stack, resource)
    return await _setup_resource(resource, stack=stack)


_open_resource = open_resource


async def _setup_resource[ResourceT: ResourceLifecyclePort](
    resource: ResourceT | None, *, stack: AsyncExitStack | None = None
) -> ResourceT | None:
    """完成单个资源 setup；调用方必须已把资源注册到退出栈。"""
    if resource is None:
        return None
    try:
        result = resource.setup()
        if isawaitable(result):
            await result
    except BaseException:
        if stack is not None:
            # setup 原因优先于清理期间的次生错误；正常退出仍传播 close 错误。
            _SETUP_FAILED_STACKS[stack] = True
        raise
    return resource


async def _close_resource(resource: ResourceLifecyclePort) -> None:
    result = resource.close()
    if isawaitable(result):
        await result


async def _close_registered_resource(
    stack: AsyncExitStack, resource: ResourceLifecyclePort
) -> None:
    try:
        await _close_resource(resource)
    except BaseException:
        if _SETUP_FAILED_STACKS.get(stack, False):
            return
        raise


def _register_resource_close(stack: AsyncExitStack, resource: ResourceLifecyclePort | None) -> None:
    if resource is None:
        return
    registered = _REGISTERED_RESOURCES.setdefault(stack, set())
    resource_id = id(resource)
    if resource_id in registered:
        return
    registered.add(resource_id)
    stack.push_async_callback(_close_registered_resource, stack, resource)


async def _build_agent_facade(
    stack: AsyncExitStack,
    settings: Settings,
    deps_factory: Callable[[Settings], AgentDependencies] | None,
) -> AgentFacade:
    """在 yield 前完成装配；调用方负责把所有异常标记为 startup failure。"""
    if deps_factory is None:
        base = make_deps(
            settings,
            resource_registrar=lambda resource: _register_resource_close(stack, resource),
        )
    else:
        base = deps_factory(settings)
    runtime_settings = base.settings
    if deps_factory is None:
        config_errors = runtime_settings.validate_engineering()
        if config_errors:
            raise ValueError("二期配置错误：" + ", ".join(config_errors))

    # make_deps 已经构造了这些资源，但它们尚未全部 setup。先把所有已构造的
    # owner 注册到退出栈；生产 make_deps 已在构造时登记，这里按对象身份去重，
    # 同时覆盖测试 deps_factory，确保最早的 setup 失败也会回收尚未 setup 的资源。
    for resource in (base.trace, base.vision, base.retrieval):
        _register_resource_close(stack, resource)

    trace = await _setup_resource(base.trace, stack=stack)
    assert trace is not None
    # 生产 Ark 模型的四个 Port 共享同一个客户端；vision 适配器暴露该
    # 客户端的所有权 close，避免四个 Port 重复注册同一底层资源。
    vision = await _setup_resource(base.vision, stack=stack)
    assert vision is not None
    retrieval = await _setup_resource(base.retrieval, stack=stack)
    assert retrieval is not None
    graph_checkpointer = None
    if runtime_settings.checkpoint_dsn:
        graph_checkpointer = await stack.enter_async_context(
            open_graph_checkpointer(runtime_settings)
        )
    request_ledger = await _open_resource(
        stack,
        make_request_ledger(
            runtime_settings.request_ledger_backend,
            runtime_settings.request_ledger_dsn or runtime_settings.checkpoint_dsn,
            pool_min_size=runtime_settings.postgres_pool_min_size,
            pool_max_size=runtime_settings.postgres_pool_max_size,
            pool_timeout_seconds=runtime_settings.postgres_pool_timeout_seconds,
        ),
    )
    memory = await _open_resource(
        stack,
        make_memory_adapter(
            runtime_settings.memory_backend,
            runtime_settings.memory_dsn,
            pool_min_size=runtime_settings.postgres_pool_min_size,
            pool_max_size=runtime_settings.postgres_pool_max_size,
            pool_timeout_seconds=runtime_settings.postgres_pool_timeout_seconds,
        ),
    )
    cache = await _open_resource(
        stack,
        make_cache_adapter(
            runtime_settings.cache_backend,
            runtime_settings.cache_dsn,
            pool_min_size=runtime_settings.postgres_pool_min_size,
            pool_max_size=runtime_settings.postgres_pool_max_size,
            pool_timeout_seconds=runtime_settings.postgres_pool_timeout_seconds,
        ),
    )
    event_store = await _open_resource(
        stack,
        make_event_store_adapter(
            runtime_settings.event_store_backend,
            runtime_settings.event_store_dsn,
            pool_min_size=runtime_settings.postgres_pool_min_size,
            pool_max_size=runtime_settings.postgres_pool_max_size,
            pool_timeout_seconds=runtime_settings.postgres_pool_timeout_seconds,
        ),
    )

    deps = AgentDependencies(
        taxonomy=base.taxonomy,
        settings=base.settings,
        vision=vision,
        intent=base.intent,
        query_rewrite=base.query_rewrite,
        explanation=base.explanation,
        retrieval=retrieval,
        trace=trace,
        metrics=base.metrics,
        graph_checkpointer=graph_checkpointer,
        request_ledger=request_ledger,
        memory=memory,
        cache=cache,
        event_store=event_store,
        supervisor_planner=getattr(base, "supervisor_planner", None),
        product_canonicalizer=getattr(base, "product_canonicalizer", None),
    )
    return AgentFacade(deps)


@asynccontextmanager
async def open_agent_runtime(
    settings: Settings,
    *,
    deps_factory: Callable[[Settings], AgentDependencies] | None = None,
) -> AsyncGenerator[AgentFacade, None]:
    """打开全部 runtime 资源，setup 完成后才构建 Facade。

    ``deps_factory`` 只为测试和示例注入 fake 端口；生产调用保持默认装配。
    """

    async with AsyncExitStack() as stack:
        try:
            facade = await _build_agent_facade(stack, settings, deps_factory)
        except BaseException:
            # 只覆盖 yield 前的初始化阶段；调用方在 Facade 运行期间的异常不应被
            # 误判为 startup failure。清理异常不能覆盖真正的启动根因。
            _SETUP_FAILED_STACKS[stack] = True
            raise
        yield facade
