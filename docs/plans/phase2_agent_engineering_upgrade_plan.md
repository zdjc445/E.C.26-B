# 第二阶段：Agent 工程化升级实施方案

编制日期：2026-08-21  
方案状态：执行中（按可验证垂直切片推进）  
实施范围：持久化与可恢复执行、分层记忆、Multi-Agent、Human-in-the-Loop、
版本感知缓存与检索升级、追加式事件与可观测性

## 1. 目标与交付定义

本阶段在不改变识价镜核心业务正确性的前提下，把当前单图工作流升级为可长期运行、
可跨会话记忆、可人工介入、可回放审计、可分工并行的 Agent 工程平台。

完成后必须交付：

1. LangGraph 原生异步 Checkpointer 接管节点级持久化和恢复；现有自定义
   `agent_checkpoint` 只保留迁移期读取能力，不再承担新执行路径的逐节点写入。
2. 工作记忆、会话对话记忆、跨会话长期记忆三层分离；长期记忆具备用户隔离、
   显式写入、查看、遗忘、幂等和审计能力。
3. 根图升级为 Supervisor Graph；识别、意图、检索、解释、记忆成为受约束子图，
   同款匹配、SKU 拆分、价格计算和最终业务排序继续使用确定性领域代码。
4. 低置信识别、约束冲突、同款 review 区间和记忆变更支持暂停、审核、编辑、恢复。
5. 图片识别、意图解析、查询改写、商品召回、解释生成支持版本感知缓存；检索支持
   可配置融合策略和确定性二阶段相关性重排。
6. 增加追加式事件日志、请求结果账本和 OpenTelemetry GenAI 风格的 Trace；可以按
   `session_id`、`request_id`、`turn_id`、`agent_name` 还原完整执行轨迹。
7. 新增功能全部具备 SQLite 开发实现、PostgreSQL 生产实现或明确的生产实现路径；
   外部资源缺失时遵守当前项目的精确缺失项失败策略。
8. 所有不可逆副作用都以稳定 `mutation_id` 幂等；恢复、重放和并发不得产生重复记忆、
   重复事件、重复请求结果或重复外部写入。

## 2. 当前基线与已确认问题

### 2.1 已有能力

- `contracts.py` 使用 Pydantic 严格契约和 `extra="forbid"`。
- `domain/`、`nodes/`、`ports/`、`adapters/` 已形成单向依赖分层。
- `AgentFacade` 已实现 `request_id` 幂等检查、进程内会话锁、超时和乐观冲突重放。
- `SQLiteCheckpointAdapter` 与 `PostgresCheckpointAdapter` 已有契约测试。
- 检索已有 dense、sparse、image、metadata 多通道和固定权重融合。
- 同款匹配、SKU 拆分、价格聚合和最终排序不依赖 LLM。
- 评测、故障注入、降级和可观测端口已经存在。

### 2.2 已确认问题

1. `src/shijiajing_agent/graph.py` 当前以 `g.compile()` 编译，没有传入 LangGraph
   checkpointer、store 或 cache。
2. `src/shijiajing_agent/facade.py` 当前以 `astream(state, {}, stream_mode="values")`
   执行，并在每次快照后手动调用 `CheckpointPort.save()`；该路径不是 LangGraph 原生
   thread persistence，无法直接使用原生 interrupt、checkpoint history、pending writes、
   replay 和 fork。
3. 当前 `agent_checkpoint` 以 `session_id` 为主键，只保留一份最新状态；重复的旧
   `request_id` 不具备独立结果账本。
4. `AgentState` 只保存 `recognition_history` 和上一轮 `effective_constraints`，没有有界
   `recent_turns` 或对话摘要。
5. 项目没有跨会话的稳定用户作用域；`AgentRequest.metadata` 是普通输入字段，不能承担
   可信用户身份。
6. `IntentModelPort.extract_intent()` 只接收当前文本和上一轮约束，不能读取结构化长期
   记忆或明确生成记忆变更。
7. 多通道召回已经在 `MilvusHybridRetrievalAdapter` 内做固定权重融合；本阶段不能把
   “增加 RRF”错误实现为第二套重复召回，必须先抽取统一融合策略。
8. `TraceSinkPort` 当前只输出业务事件；没有持久化追加式事件表，也没有统一的 Agent、
   model、retrieval、cache、memory span 层次。
9. `pyproject.toml` 声明 `langgraph>=0.3.0`，当前 `uv.lock` 实际解析为：
   `langgraph==1.2.11`、`langgraph-checkpoint==4.2.0`、
   `langgraph-checkpoint-sqlite==3.1.1`、
   `langgraph-checkpoint-postgres==3.1.2`。执行 Agent 必须以锁文件版本为实现基准，
   不得按 `0.3.x` API 编码。
10. `.env.example` 当前使用 `ARK_API_KEY`、`CHECKPOINT_DSN` 等无前缀名称，
    `load_settings()` 实际只读取 `SHIJIAJING_` 前缀变量。本阶段必须统一为代码实际读取的
    精确名称。

## 3. 范围与非目标

### 3.1 本阶段范围

- 原生异步 SQLite/PostgreSQL Checkpointer 装配、原生 thread config、状态迁移与恢复。
- 独立请求结果账本，替代“只检查最新 response”的有限幂等语义。
- 有界会话摘要、显式长期记忆、Memory Policy、Memory Port 和双后端适配器。
- Supervisor Graph 和五个专业子图。
- Facade 的 start/resume 协议和四类 interrupt。
- 内容寻址、版本感知、TTL 缓存。
- 现有召回融合重构、Weighted/RRF 策略和确定性相关性重排。
- 追加式 Agent Event Log、OpenTelemetry span、指标和脱敏规则。
- 配置、文档、迁移工具、测试夹具、评测数据和发布门禁。

### 3.2 非目标

- 不实现 Web API、鉴权服务和客户端 UI；只定义可信调用上下文和 Facade 协议。
- 不接入真实电商平台 API，不实现 MCP。
- 不实现点击、收藏、购买驱动的自动偏好学习或 Learning-to-Rank。
- 不把用户单次搜索自动写成长期记忆。
- 不引入向量数据库保存结构化用户偏好。
- 不把同款、SKU、价格和最终业务排序改成 LLM Agent。
- 不让子 Agent 自由对话，不允许子 Agent 直接修改其他子 Agent 的私有状态。
- 不让 Event Log 在本阶段替代 Checkpoint 成为状态唯一事实源。
- 不引入 Temporal、消息队列或降价订阅。

## 4. 固定架构决策

### 4.1 目标结构

```text
可信调用方
  │ AgentRequest + AgentExecutionContext
  ▼
AgentFacade / Supervisor Graph
  ├── Native Checkpointer       会话状态、节点恢复、interrupt
  ├── RequestLedgerPort         全量 request_id 幂等结果
  ├── MemoryPort                跨会话显式偏好
  ├── VersionedCachePort        模型与检索缓存
  ├── EventStorePort            追加式审计事件
  └── TraceSinkPort/MetricsPort OpenTelemetry、日志、指标
  │
  ├────────────── 并行 ──────────────┐
  ▼                                  ▼
RecognitionSubgraph           IntentSubgraph
  │                                  │
  └───────────────┬──────────────────┘
                  ▼
           MemoryRecallSubgraph
                  ▼
            ConstraintPolicy
                  ▼
            RetrievalSubgraph
                  ▼
  normalize → same-item → SKU → rank
          （确定性领域节点）
                  ▼
           ExplanationSubgraph
                  ▼
             MemorySubgraph
                  ▼
            AgentTurnResult
```

### 4.2 单写原则

- Supervisor 是 `AgentState` 和 thread checkpoint 的唯一协调者。
- `MemorySubgraph` 是长期记忆的唯一写入入口；其他子图只能返回
  `proposed_memory_mutations`。
- `RequestLedgerPort` 是已完成请求响应的唯一幂等结果来源。
- `EventStorePort` 只追加，不更新既有事件。
- 同款、SKU、价格和最终业务排序只接收结构化输入，不读取自由文本记忆。
- Cache 失败必须降级为未命中，不能阻断业务结果。

### 4.3 状态与长期存储边界

- Checkpoint 保存本 thread 继续执行所需的有界状态。
- `previous_state` 继续不得嵌套持久化。
- Checkpoint 中只保存本轮召回到的精简 `memory_context`，不复制用户全部长期记忆。
- Event Log 保存 ID、版本、哈希、计数和状态变化摘要，不保存隐藏思维链。
- 原始图片、完整模型请求、完整模型响应、密钥、地址、支付和联系方式不得进入
  Checkpoint、Memory、Event、Trace 或 Cache。

## 5. 公共契约与精确标识符

以下为本方案新增的固定标识符。执行 Agent 不得另起同义命名。

### 5.1 调用上下文

在 `contracts.py` 新增：

```python
class AgentExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_owner_id: str | None = Field(default=None, min_length=1, max_length=128)
    memory_enabled: bool = False
```

`memory_owner_id` 只能由项目外的可信鉴权层填充。没有可信身份时必须为 `None`，长期
记忆读取和写入全部跳过。

### 5.2 Multi-Agent 契约

```python
class SpecialistAgentName(StrEnum):
    RECOGNITION = "recognition"
    INTENT = "intent"
    RETRIEVAL = "retrieval"
    EXPLANATION = "explanation"
    MEMORY = "memory"


class AgentTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    agent_name: SpecialistAgentName
    input_payload: dict[str, Any]
    memory_context: list[MemoryRecord] = Field(default_factory=list)


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent_name: SpecialistAgentName
    status: NodeStatus
    output_payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    proposed_memory_mutations: list[MemoryMutation] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
```

`input_payload` 和 `output_payload` 只用于根图与子图的统一信封；每个子图入口必须立即
把它校验为该子图的专用 Pydantic 模型，禁止在领域代码中继续传递无类型 dict。

### 5.3 记忆契约

```python
class MemoryOperation(StrEnum):
    UPSERT = "upsert"
    FORGET = "forget"
    CLEAR_OWNER = "clear_owner"


class MemoryApplyMode(StrEnum):
    CONSTRAINT_DEFAULT = "constraint_default"
    RANKING_PRIOR = "ranking_prior"
    NEGATIVE_PREFERENCE = "negative_preference"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    FORGOTTEN = "forgotten"


class MemoryDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: MemoryOperation
    memory_key: str | None = None
    value: Any = None
    scope_key: str = "global"
    apply_mode: MemoryApplyMode | None = None


class MemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    memory_owner_id: str
    memory_key: str
    scope_key: str
    value: Any
    apply_mode: MemoryApplyMode
    confidence: float = Field(ge=0.0, le=1.0)
    status: MemoryStatus
    source_session_id: str
    source_request_id: str
    version: int = Field(ge=1)
    created_at: str
    updated_at: str
    expires_at: str | None = None


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_keys: list[str]
    memory_keys: list[str] = Field(default_factory=list)
    limit: int = Field(ge=1)


class MemoryMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutation_id: str
    operation: MemoryOperation
    memory_key: str | None = None
    scope_key: str
    value: Any = None
    apply_mode: MemoryApplyMode | None = None
    source_session_id: str
    source_request_id: str
```

`scope_key` 只允许：

- `global`
- `category:<category_id>`，其中 `<category_id>` 必须由 `Taxonomy` 精确校验。

第一版 `memory_key` 白名单固定为：

- `max_price`
- `min_price`
- `platforms`
- `min_rating`
- `colors`
- `sort_by`
- `preferences`
- `negative_terms`

`brand`、`model`、任意自由文本 Prompt、原始用户消息不允许作为第一版长期记忆键。

`MemoryDirective` 和 `MemoryMutation` 必须使用 model validator 固定校验：

- `UPSERT` 必须提供 `memory_key`、`value` 和 `apply_mode`。
- `FORGET` 必须提供 `memory_key`，`value` 和 `apply_mode` 必须为空。
- `CLEAR_OWNER` 的 `memory_key`、`value`、`apply_mode` 必须为空，`scope_key` 必须为
  `global`。

### 5.4 HITL 契约

```python
class InterruptKind(StrEnum):
    CLARIFICATION = "clarification"
    RECOGNITION_REVIEW = "recognition_review"
    SAME_ITEM_REVIEW = "same_item_review"
    MEMORY_CONFIRMATION = "memory_confirmation"


class AgentInterrupt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interrupt_id: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    kind: InterruptKind
    prompt: str
    payload: dict[str, Any]


class AgentResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interrupt_id: str
    value: dict[str, Any]


class AgentTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: AgentResponse | None = None
    interrupt: AgentInterrupt | None = None
```

`AgentTurnResult` 必须通过 model validator 保证 `response` 和 `interrupt` 恰好一个非空。

### 5.5 会话摘要契约

```python
class ConversationTurnSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    turn_id: str
    user_text: str | None
    user_text_sha256: str | None
    user_text_length: int | None
    intent_patch: IntentPatch | None
    completion_reason: CompletionReason | None
    selected_group_ids: list[str] = Field(default_factory=list)
    created_at: str
```

`user_text` 只在进程内用于构造终态摘要；写入 Checkpoint 前清空，并保存
`user_text_sha256`/`user_text_length`，只保留最近固定轮数，不生成隐藏推理摘要。

### 5.6 错误码与异常

`errors.py` 固定新增：

```python
class ErrorCode(StrEnum):
    # 保留现有成员
    REQUEST_LEDGER_UNAVAILABLE = "REQUEST_LEDGER_UNAVAILABLE"
    MEMORY_UNAVAILABLE = "MEMORY_UNAVAILABLE"
    MEMORY_CONFLICT = "MEMORY_CONFLICT"
    CACHE_UNAVAILABLE = "CACHE_UNAVAILABLE"
    EVENT_STORE_UNAVAILABLE = "EVENT_STORE_UNAVAILABLE"
    EVENT_CONFLICT = "EVENT_CONFLICT"


class RequestLedgerUnavailableError(ShijiajingError): ...
class MemoryUnavailableError(ShijiajingError): ...
class MemoryConflictError(ShijiajingError): ...
class CacheUnavailableError(ShijiajingError): ...
class EventStoreUnavailableError(ShijiajingError): ...
class EventConflictError(ShijiajingError): ...
```

Cache、普通 Event 和 Memory recall 的异常按各自降级策略被节点捕获；Request Ledger、
native Checkpointer、纯记忆写请求的异常进入用户可见失败响应。

## 6. 方案一：原生持久化与可恢复执行

### 6.1 目标实现

新增 `adapters/langgraph_persistence.py`：

- `open_graph_checkpointer(settings)` 是 `@asynccontextmanager`：
  - SQLite 返回当前锁定版本的
    `langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver`。
  - PostgreSQL 返回当前锁定版本的
    `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`。
- 两种 saver 都显式传入
  `JsonPlusSerializer(pickle_fallback=False, allowed_json_modules=...,`
  `allowed_msgpack_modules=...)`；allowlist 只包含 `shijiajing_agent.contracts`、
  `shijiajing_agent.domain.evidence` 和本方案新增的状态契约模块。禁止把 allowlist 设置为
  `True`。
- 应用启动时显式执行 saver 的 `setup()`；数据库迁移不得在首个用户请求内隐式执行。
- `build_graph(deps)` 改为：
  `g.compile(checkpointer=deps.graph_checkpointer, name="shijiajing-supervisor")`。
- Facade 每次 start/resume 使用精确 config：

```python
config = {"configurable": {"thread_id": session_id}}
```

- 删除原生路径中的手动 `astream(..., stream_mode="values")` 快照保存循环。
- 使用 graph state/history 判断 completed 或 interrupted，不从 trace 事件猜测执行位置。

### 6.2 Request Ledger

新增：

```text
ports/request_ledger.py
adapters/request_ledger.py
```

端口方法固定为：

```python
class RequestLedgerPort(Protocol):
    async def get_response(
        self, session_id: str, request_id: str
    ) -> AgentResponse | None: ...

    async def save_response(
        self,
        session_id: str,
        request_id: str,
        response: AgentResponse,
        expected_absent: bool = True,
    ) -> None: ...
```

逻辑表：

```sql
agent_request_result(
    session_id      TEXT NOT NULL,
    request_id      TEXT NOT NULL,
    response_json   TEXT/JSONB NOT NULL,
    created_at      TEXT/TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(session_id, request_id)
)
```

Facade 的执行顺序固定为：

1. 会话锁外查 `RequestLedgerPort.get_response()`。
2. 获取会话锁。
3. 会话锁内再次查询。
4. Ledger miss 时读取 native thread 最新 state；如果其中已经存在相同 `request_id` 的
   terminal `response`，先修复 Ledger，再直接返回，禁止重跑图。
5. 没有可修复响应时执行 start/resume。
6. completed 时先保存请求结果账本，再向调用方返回 terminal 响应。
7. interrupt 不写 completed response。
8. 重复保存同一响应视为幂等；同一主键不同响应抛 `SessionConflictError`。
9. Request Ledger 读取失败时不得启动工作流，返回新增
   `ErrorCode.REQUEST_LEDGER_UNAVAILABLE`；completed response 写入失败时不得向调用方返回
   成功，避免重试后重复执行业务。

Ledger 保存由图正常产出的 terminal `AgentResponse`，包括 success、no-results 和确定性
failed；不保存 interrupt、整轮 timeout、Checkpointer/Request Ledger 不可用时构造的裸
失败响应。Ledger 修复路径必须有独立 `request_ledger_repair_total` 指标和事件。

### 6.3 兼容迁移

保留现有 `CheckpointPort` 和 `adapters/checkpoint.py` 作为 legacy 读取路径，增加配置
`SHIJIAJING_GRAPH_PERSISTENCE_MODE=legacy|native`。

迁移规则：

1. 部署前统计现有 `agent_checkpoint` 行数。
2. 行数为 0 时直接启用 native，不执行导入。
3. 行数大于 0 时，native thread 首次启动前：
   - 先查询 native saver 是否已有该 `thread_id`；
   - 没有 native checkpoint 时加载 legacy `AgentState`，移除 `previous_state`，执行
     `SCHEMA_VERSION` 迁移，并作为首次 native 输入的历史基线；
   - native thread 成功写入后，向 `checkpoint_migration` 表追加完成记录；
   - legacy 表只读，不删除。
4. 所有活动 session 导入完成且观察期无回滚后，另行审批删除 legacy 写路径；本阶段不
   删除 legacy 数据。

新增 CLI：

```text
shijiajing-migrate-state inspect
shijiajing-migrate-state validate
```

`inspect` 只统计和验证，不写数据；`validate` 对比 legacy 最新状态与 native 最新状态的
关键业务字段和 schema 版本。

### 6.4 Facade 协议

新增：

```python
async def start(
    self,
    request: AgentRequest,
    context: AgentExecutionContext,
) -> AgentTurnResult: ...

async def resume(
    self,
    session_id: str,
    resume: AgentResume,
    context: AgentExecutionContext,
) -> AgentTurnResult: ...
```

现有 `run(request) -> AgentResponse` 保留兼容期包装：传入
`AgentExecutionContext(memory_enabled=False)`；如果图产生 interrupt，则将其转换为现有
`AgentStatus.CLARIFICATION` 响应，不自动 resume。

### 6.5 异步资源生命周期

当前 `make_deps(settings)` 是同步工厂，不能持有由 `from_conn_string()` 创建的异步 saver
上下文。新增 `runtime.py`，固定生产装配入口：

```python
@asynccontextmanager
async def open_agent_runtime(settings: Settings) -> AsyncIterator[AgentFacade]:
    ...
```

`open_agent_runtime()` 使用 `AsyncExitStack` 注册并最终关闭：

1. Trace sink；
2. Ark 模型适配器的共享客户端 owner；
3. Retrieval 适配器及其持有的文本/图像 Embedding、Milvus 客户端和本地兜底资源；
4. graph checkpointer；
5. Request Ledger；
6. Memory adapter；
7. Cache adapter；
8. Event Store。

资源按注册逆序关闭。Ark 四个模型 Port 共享一个底层客户端，只注册一个 owner；所有
`close()` 实现必须幂等。Milvus 适配器对持有资源按对象身份去重，并在某一资源关闭失败后
继续尝试其余资源，再抛出首个关闭错误。

所有已构造的资源在 setup 前先登记到 `AsyncExitStack`，再完成 setup；因此任何 setup 失败
都会按逆序关闭已构造资源，包括尚未 setup 的资源，并阻止启动。只有全部资源 setup 成功
后才构建 `AgentDependencies`、编译根图并 yield Facade。示例、live eval 和生产调用全部迁移到：

```python
async with open_agent_runtime(settings) as facade:
    result = await facade.start(request, context)
```

`make_deps()` 只负责同步构造依赖；生产调用必须通过 `open_agent_runtime()` 获得资源所有权，
测试可以直接使用它装配 Fake，不把同步工厂本身当作生命周期入口。生产 runtime 会向
`make_deps()` 传入同步 `resource_registrar`；每个资源 owner 构造成功后立即登记到同一
`AsyncExitStack`，因此构造阶段后续失败也不会遗失已经创建的异步客户端。
`open_graph_checkpointer()` enter、业务资源构造、资源 setup 和 Facade 编译也统一纳入
yield 前 startup error boundary；startup 根因优先于清理异常，yield 后调用方异常不被误判为
startup failure。

`AgentDependencies` 必须对 Settings、Checkpoint、Request Ledger、Memory、Cache、Event Store
和业务 Port 使用显式类型；仅第三方 LangGraph graph checkpointer 可以保留 `Any`，避免依赖
容器用动态类型绕过端口契约。

节点和子图装配函数使用 `ports/dependencies.py` 的 `AgentDependenciesPort`，只暴露业务节点
实际使用的固定字段；`AgentDependencies` 通过结构化类型满足该协议，避免节点层反向依赖
Facade 或用 `Any` 放弃类型检查。

缓存 miss-safe 辅助函数也必须以 `VersionedCachePort` 和 `MetricsPort` 接收外部能力；动态
缓存载荷可以保留 `dict[str, Any]`，但不得把载荷的动态类型扩散成 Cache/指标依赖的 `Any`。
同一原则适用于 Ark 模型、Milvus 混合检索和本地词法检索适配器：指标注入必须显式使用
`MetricsPort`，避免适配器构造边界重新引入动态依赖。
live 评测计数包装器必须保持 `VisionModelPort`、`IntentModelPort`、`QueryRewritePort` 和
`ProductRetrievalPort` 的精确方法签名，只增加调用计数和 fallback 统计，不得用 `Any` 改写
生产 Port 的输入输出边界。

二期由 runtime 管理的 Checkpoint、Request Ledger、Memory、Cache、Event Store、Retrieval、
Trace 和 Vision owner Port 统一继承 `ports/lifecycle.py` 的同步/异步兼容生命周期协议；适配器必须同时
提供业务方法和 `setup()` / `close()`，由 `open_agent_runtime()` 负责调用与逆序回收。没有
外部连接的本地 Retrieval 与 structlog Trace 也提供明确 no-op 生命周期，避免替换实现出现
结构不一致。
runtime 的资源辅助函数必须以 `ResourceLifecyclePort` 泛型保留具体资源类型，不能用 `Any` 逃避
生命周期契约；LangGraph 第三方 graph checkpointer 仍保持独立的 context-manager 边界。

## 7. 方案二：分层记忆

### 7.1 三层边界

1. 工作记忆：现有结构化 `AgentState`，由 native Checkpointer 按 thread 保存。
2. 对话记忆：`recent_turns: list[ConversationTurnSummary]`，保存在 `AgentState`，固定只
   保留最近 6 轮。
3. 长期记忆：由 `MemoryPort` 按 `memory_owner_id` 和 `scope_key` 跨 thread 保存。

### 7.2 Memory Port

新增 `ports/memory.py`：

```python
class MemoryPort(Protocol):
    async def recall(
        self,
        memory_owner_id: str,
        query: MemoryQuery,
    ) -> list[MemoryRecord]: ...

    async def commit(
        self,
        memory_owner_id: str,
        mutations: list[MemoryMutation],
    ) -> list[MemoryRecord]: ...

    async def list_memories(
        self,
        memory_owner_id: str,
    ) -> list[MemoryRecord]: ...

    async def clear_owner(
        self,
        memory_owner_id: str,
        mutation_id: str,
    ) -> None: ...
```

新增 `adapters/memory.py`：

- `SQLiteMemoryAdapter`
- `PostgresMemoryAdapter`
- `DisabledMemoryAdapter`

逻辑表：

```sql
user_memory(
    memory_id          TEXT PRIMARY KEY,
    memory_owner_id    TEXT NOT NULL,
    memory_key         TEXT NOT NULL,
    scope_key          TEXT NOT NULL,
    value_json         TEXT/JSONB NOT NULL,
    apply_mode         TEXT NOT NULL,
    confidence         REAL/DOUBLE PRECISION NOT NULL,
    status             TEXT NOT NULL,
    source_session_id  TEXT NOT NULL,
    source_request_id  TEXT NOT NULL,
    version            INTEGER NOT NULL,
    created_at         TEXT/TIMESTAMPTZ NOT NULL,
    updated_at         TEXT/TIMESTAMPTZ NOT NULL,
    expires_at         TEXT/TIMESTAMPTZ NULL,
    UNIQUE(memory_owner_id, scope_key, memory_key)
)

memory_mutation(
    mutation_id       TEXT PRIMARY KEY,
    memory_owner_id   TEXT NOT NULL,
    operation         TEXT NOT NULL,
    payload_json      TEXT/JSONB NOT NULL,
    applied_at        TEXT/TIMESTAMPTZ NOT NULL
)
```

同一事务先检查/插入 `memory_mutation`，再修改 `user_memory`。重复 `mutation_id` 返回首次
提交结果，不重复增加 version。

### 7.3 Memory Policy

新增 `domain/memory_policy.py`：

- `validate_directive(directive, taxonomy)`：执行作用域、键名和值类型白名单校验。
- `build_memory_query(state)`：只查询 `global` 和当前有效
  `category:<category_id>`。
- `apply_memory_defaults(constraints, memories)`：仅填充当前请求和当前会话都没有值的
  字段。
- `build_ranking_priors(memories)`：只生成排序先验，不生成 `HardFilters`。
- `make_prepare_memory_mutations_node(deps)`：只把明确的 `MemoryDirective` 经过
  `validate_directive()` 后交给 `build_memory_mutation()` 变成写操作。

合并优先级固定为：

1. 当前轮用户修正。
2. 当前轮用户文本或明确选项。
3. 当前会话已有用户锁定值。
4. 显式长期记忆默认值。
5. 当前图片识别值。
6. 系统默认值。

长期记忆应用到 `ShoppingConstraints` 时增加
`ConstraintSource.MEMORY_EXPLICIT = "memory_explicit"`，并设置
`locked_by_user=False`。当前轮用户文本始终可以覆盖它。

### 7.4 记忆提取与图节点

`IntentPatch` 增加：

```python
memory_directives: list[MemoryDirective] = Field(default_factory=list)
```

同时更新 `prompts/intent.md` 和 `ArkIntentModel` 的结构化输出：只有用户明确表达“记住、
以后默认、以后优先、忘记、清除”等长期意图时才能产生 directive。普通搜索、模型猜测、
重复选择和单次排序不得产生 directive。

新增 `nodes/memory_nodes.py`：

- `recall_memory`：在 `parse_intent` 之后、`merge_constraints` 之前执行。
- `prepare_memory_mutations`：校验 directive，生成稳定 mutation。
- `commit_memory`：在最终响应构建后执行；只有提交成功才能向 response 增加“已记住”或
  “已忘记”提示。
- `append_turn_summary`：completed 响应后追加有界会话摘要。

`mutation_id` 精确计算输入为：

```text
memory_owner_id | session_id | request_id | directive_index | operation | scope_key | memory_key
```

使用 SHA-256 十六进制摘要，不使用随机 UUID，确保 replay 稳定。

### 7.5 失败策略

- `memory_enabled=False` 或 `memory_owner_id=None`：使用 `DisabledMemoryAdapter`，不读不写。
- recall 失败：本轮继续，`notices` 增加“历史偏好读取失败，本轮未应用”，指标增加
  `memory_recall_failure_total`。
- 显式 commit 失败：业务比价结果仍可成功，但不得声称保存成功；`notices` 增加精确
  失败说明，指标增加 `memory_commit_failure_total`。
- 纯记忆请求写入失败：返回 `AgentStatus.FAILED`。
- clear/forget 产生 tombstone 和事件记录，不在同一事务物理删除审计事件。

## 8. 方案三：Multi-Agent 专业子图

### 8.1 目录结构

新增：

```text
src/shijiajing_agent/subgraphs/
├── __init__.py
├── recognition.py
├── intent.py
├── retrieval.py
├── explanation.py
└── memory.py
```

根图仍位于 `graph.py`，名称固定为 `shijiajing-supervisor`。

### 8.2 子图职责

| 子图 | 包含节点 | 可写根状态字段 |
|---|---|---|
| `RecognitionSubgraph` | recognize/apply correction/normalize | recognition、recognition_history、recognition_id、keywords |
| `IntentSubgraph` | parse intent | intent_patch、notices、fallbacks |
| `RetrievalSubgraph` | rewrite/retrieve/relax/normalize candidates | retrieval_query、candidates、normalized_candidates、retrieval control fields |
| `ExplanationSubgraph` | build evidence/explain/verify | evidence_bundle、explanation_text、explanation_verified |
| `MemorySubgraph` | recall/prepare/confirm/commit | memory_context、pending_memory_mutations、notices |

子图不得写入表中未授权字段。根图在子图结果返回后以专用 Pydantic 输出模型校验。

### 8.3 并行与汇合

- 请求同时包含图片和文本时，`RecognitionSubgraph` 与 `IntentSubgraph` 并行执行。
- 无新图片时 Recognition 分支读取会话现有 recognition，不调用 VLM。
- 两个分支只写互不重叠字段；在 `join_understanding` 节点汇合。
- `MemoryRecallSubgraph` 在汇合后运行，因为品类作用域来自 normalization 或 intent。
- Retrieval、same-item、SKU、rank、explanation 保持严格顺序。
- 同一子图实例不使用跨 invocation 私有 thread；子图状态只服务当前根图调用。

### 8.4 Agent 失败隔离

- Recognition 失败沿用现有精确故障语义，不伪造识别结果。
- Intent 失败使用 `RuleIntentParser`。
- Memory recall 失败按 §7.5 降级。
- Retrieval 失败沿用 Milvus → local lexical 降级，两者均失败才返回 FAILED。
- Explanation 失败使用证据模板。
- 子图失败必须产生 `agent_completed` 或 `agent_failed` 事件，不允许无事件退出。

### 8.5 确定性保护

以下代码不得迁入 LLM 子图：

- `domain/constraints.py` 的优先级与冲突规则。
- `domain/filters.py` 的硬过滤语义。
- `domain/same_item.py` 的硬冲突和聚类。
- `domain/sku.py` 的 SKU 拆分。
- `domain/ranking.py` 的价格、质量、排序计算。
- `domain/evidence.py` 的事实约束检查。

## 9. 方案四：Human-in-the-Loop

### 9.1 Interrupt 触发点

1. `CLARIFICATION`：品类缺失、约束冲突或 intent 明确要求澄清。
2. `RECOGNITION_REVIEW`：`recognition.category_id is None`、存在关键
   `unresolved_fields`，或 `overall_confidence` 低于
   `SHIJIAJING_RECOGNITION_REVIEW_THRESHOLD`。
3. `SAME_ITEM_REVIEW`：候选对分数位于现有
   `same_item_review_threshold <= score < same_item_accept_threshold`，且该 review 会影响
   是否把不同 offer 放入同一个比价组。
4. `MEMORY_CONFIRMATION`：`CLEAR_OWNER`，或配置要求确认的 `FORGET`/`UPSERT`。

### 9.2 Resume 行为

- 节点调用 `interrupt()` 时只传 JSON 可序列化的 `AgentInterrupt` dump。
- Facade 把 interrupt 转为 `AgentTurnResult(interrupt=...)`。
- `resume()` 校验调用方 session、`interrupt_id` 和可信 `memory_owner_id` 与原 checkpoint
  一致，再以 `Command(resume=resume.value)` 恢复。
- approve/edit/reject 都必须映射为专用 Pydantic resume payload，不能透传任意 dict 到
  领域节点。
- interrupt 所在节点从开头重放；interrupt 之前不得执行非幂等写操作。
- Memory commit 必须位于 confirmation interrupt 之后。

### 9.3 向后兼容

- `SHIJIAJING_HITL_ENABLED=false` 时保留当前 clarification response 流程。
- 兼容 `run()` 不自动阻塞等待用户；interrupt 转为现有 clarification response。
- start/resume 是新调用方使用的正式 HITL 协议。

## 10. 方案五：版本感知缓存与检索升级

### 10.1 Cache Port

新增：

```text
ports/cache.py
adapters/cache.py
```

```python
class VersionedCachePort(Protocol):
    async def get(self, namespace: str, key: str) -> dict[str, Any] | None: ...
    async def set(
        self,
        namespace: str,
        key: str,
        value: dict[str, Any],
        ttl_seconds: int,
    ) -> None: ...
    async def delete_namespace(self, namespace: str) -> None: ...
```

适配器固定为：

- `InMemoryVersionedCache`：测试。
- `SQLiteVersionedCacheAdapter`：开发。
- `PostgresVersionedCacheAdapter`：生产第一版。
- `DisabledVersionedCache`：关闭时。

Cache 不是正确性来源。get/set/delete 失败全部转为 miss 并增加指标，不改变业务响应。

SQLite/PostgreSQL 共用逻辑表：

```sql
versioned_cache(
    namespace      TEXT NOT NULL,
    cache_key      TEXT NOT NULL,
    value_json     TEXT/JSONB NOT NULL,
    created_at     TEXT/TIMESTAMPTZ NOT NULL,
    expires_at     TEXT/TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(namespace, cache_key)
)
```

get 时必须忽略并异步清理过期记录；set 对同一主键执行确定性 upsert。

### 10.2 Cache key

所有 key 都是 canonical JSON 的 SHA-256；canonical JSON 使用 `orjson` 排序键输出。

| namespace | key 输入 | 首版 TTL |
|---|---|---:|
| `vision` | image.sha256、vision model、vision prompt version、taxonomy version | 2,592,000 秒 |
| `intent` | text、effective constraints、text model、intent prompt version、taxonomy version | 604,800 秒 |
| `query_rewrite` | text、constraints、recognition、text model、rewrite prompt version | 604,800 秒 |
| `retrieval` | RetrievalQuery、image sha256、index_version、fusion version、rerank version | 300 秒 |
| `explanation` | EvidenceBundle、text model、explanation prompt version | 86,400 秒 |

禁止缓存：失败响应、interrupt、含未脱敏自由 metadata 的请求、Memory commit 结果。

### 10.3 召回融合重构

新增 `domain/retrieval_fusion.py`：

```python
class RetrievalFusionStrategy(Protocol):
    def fuse(
        self,
        channel_results: dict[str, list[RetrievalCandidate]],
        limit: int,
    ) -> list[RetrievalCandidate]: ...
```

实现：

- `WeightedScoreFusion`：复现当前 `_TEXT_WEIGHTS` / `_IMAGE_WEIGHTS` 行为，作为兼容基线。
- `ReciprocalRankFusion`：按各通道排名执行 RRF；参数由
  `SHIJIAJING_RETRIEVAL_RRF_K` 提供。

`MilvusHybridRetrievalAdapter` 负责获取通道结果，不再内嵌不可替换的融合政策。默认仍为
`weighted`；只有离线 retrieval 门禁证明 RRF 不降低阻断指标后才切换默认值。

### 10.4 确定性二阶段重排

新增 `domain/retrieval_reranking.py` 的 `CandidateRelevanceReranker`，只使用：

- category 精确一致。
- brand/model 规范值一致。
- 用户明确 attributes 覆盖率。
- query keywords 标题覆盖率。
- negative terms 命中惩罚。
- 原 recall score。

输出仍是 `RetrievalCandidate`，增加契约字段：

```python
rerank_score: float | None = None
rerank_version: str | None = None
```

重排只影响进入 same-item 的候选顺序和截断，不计算价格、店铺、销量和最终推荐分。
首版对 `retrieval_union_limit` 内候选重排，再按现有 `matching_candidate_limit` 截断。

### 10.5 检索版本

`RetrievalResult.index_version` 已存在；本阶段新增并贯穿 trace/cache：

- `fusion_version`
- `rerank_version`

任何版本变化必须自然导致缓存 miss，不能手工复用旧缓存。

## 11. 方案六：追加式事件与可观测性

### 11.1 Event Store

新增：

```text
ports/event_store.py
adapters/event_store.py
```

```python
class AgentEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    agent_name: str
    node_name: str | None
    event_type: str
    status: str | None
    input_hash: str | None
    output_hash: str | None
    state_version: int | None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str


class EventStorePort(Protocol):
    async def append(self, event: AgentEventRecord) -> None: ...
    async def list_turn(self, session_id: str, turn_id: str) -> list[AgentEventRecord]: ...
```

逻辑表：

```sql
agent_event(
    event_id       TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,
    request_id     TEXT NOT NULL,
    turn_id        TEXT NOT NULL,
    trace_id       TEXT NOT NULL,
    agent_name     TEXT NOT NULL,
    node_name      TEXT NULL,
    event_type     TEXT NOT NULL,
    status         TEXT NULL,
    input_hash     TEXT NULL,
    output_hash    TEXT NULL,
    state_version  INTEGER NULL,
    payload_json   TEXT/JSONB NOT NULL,
    occurred_at    TEXT/TIMESTAMPTZ NOT NULL
)
```

`event_id` 使用稳定输入 SHA-256：

```text
session_id | request_id | turn_id | agent_name | node_name | event_type | sequence
```

重复 event_id 且内容一致视为 replay 幂等；内容不一致抛事件冲突错误并增加指标。

本阶段 Event Store 是追加式审计与回放依据，Checkpoint 仍是工作流状态事实源。禁止根据
Event Store 自动重建并覆盖生产 Checkpoint。

### 11.2 事件类型

固定新增：

- `agent_started`
- `agent_completed`
- `agent_failed`
- `agent_interrupted`
- `agent_resumed`
- `memory_recalled`
- `memory_committed`
- `memory_forgotten`
- `cache_hit`
- `cache_miss`
- `checkpoint_migrated`
- `request_result_committed`

现有 `AgentEvent` 继续用于实时 TraceSink；持久化事件使用新的
`AgentEventRecord`，不得把两个模型混为同一个契约。

### 11.3 OpenTelemetry span 层次

```text
shijiajing.turn
├── shijiajing.agent
│   ├── shijiajing.model
│   ├── shijiajing.retrieval
│   ├── shijiajing.cache
│   └── shijiajing.memory
├── shijiajing.checkpoint
└── shijiajing.request_ledger
```

必须记录：

- session/request/turn/trace ID。
- workflow、agent、model、prompt、taxonomy、index、fusion、rerank 版本。
- duration、retry、fallback、cache hit、candidate count、token usage。
- interrupt kind、memory operation 数量、checkpoint migration 状态。

禁止记录：

- API key、DSN、Token。
- 完整系统 Prompt、完整用户文本、完整模型输入输出。
- 图片 data URL、base64、地址、支付、联系方式。
- 模型内部推理链。

自由文本只记录 SHA-256 和长度；结构化 payload 必须经过白名单字段投影。

### 11.4 失败策略

- TraceSink 和普通指标失败继续不阻断业务。
- Event Store 写失败时增加 `event_store_failure_total`；普通诊断事件允许业务继续。
- `memory_committed`、`memory_forgotten`、`request_result_committed` 属于一致性事件：先完成
  真实存储事务，再追加事件。事件追加失败不得回滚已经成功的真实操作，必须由
  `audit_event_repair` 运维任务根据 Request Ledger/Memory Mutation 补写。
- 新增 CLI `shijiajing-repair-events --dry-run`，默认只报告缺失事件，不写数据；显式
  `--apply` 才执行补写。

## 12. AgentState 与序列化变更

`AgentState` 新增固定字段：

```python
execution_context: AgentExecutionContext | None
recent_turns: list[ConversationTurnSummary]
memory_context: list[MemoryRecord]
pending_memory_mutations: list[MemoryMutation]
agent_results: list[AgentResult]
active_interrupt: AgentInterrupt | None
fusion_version: str | None
rerank_version: str | None
```

要求：

- `SCHEMA_VERSION` 从 `"1.0"` 升为 `"1.1"`。
- `adapters/checkpoint.py` legacy 反序列化映射补齐所有新增 Pydantic 字段，以服务迁移读取。
- native checkpointer 使用项目现有 JSON 安全 serializer，不允许 pickle。
- `recent_turns` 每次追加后保留最后 6 项。
- `recent_turns` 在每个 terminal response 后追加，与长期 Memory 开关独立；legacy/native
  下一轮都必须恢复并继续追加该 bounded conversation memory。
- `memory_context` 最多 20 项。
- `agent_results` 只保留本轮每个子图的精简结果，不保存模型原始输出。
- 新 turn 开始时清空 `pending_memory_mutations`、`agent_results` 和 `active_interrupt`，
  `recent_turns` 与有效业务状态继续保留。

## 13. 配置与装配

### 13.1 新增 Settings 字段

```text
 graph_persistence_mode
request_ledger_backend
request_ledger_dsn
memory_enabled
memory_recall_enabled
memory_commit_enabled
memory_backend
memory_dsn
memory_recall_limit
recent_turns_limit
hitl_enabled
recognition_review_threshold
memory_confirmation_required
cache_backend
cache_dsn
retrieval_fusion_strategy
retrieval_rrf_k
retrieval_rerank_limit
retrieval_rerank_enabled
retrieval_index_version
event_store_backend
event_store_dsn
vision_cache_ttl_seconds
intent_cache_ttl_seconds
query_rewrite_cache_ttl_seconds
retrieval_cache_ttl_seconds
explanation_cache_ttl_seconds
```

### 13.2 精确环境变量

```dotenv
SHIJIAJING_GRAPH_PERSISTENCE_MODE=legacy
SHIJIAJING_REQUEST_LEDGER_BACKEND=disabled
SHIJIAJING_REQUEST_LEDGER_DSN=

SHIJIAJING_VISION_CACHE_TTL_SECONDS=2592000
SHIJIAJING_INTENT_CACHE_TTL_SECONDS=604800
SHIJIAJING_QUERY_REWRITE_CACHE_TTL_SECONDS=604800
SHIJIAJING_RETRIEVAL_CACHE_TTL_SECONDS=300
SHIJIAJING_EXPLANATION_CACHE_TTL_SECONDS=86400

SHIJIAJING_MEMORY_ENABLED=false
SHIJIAJING_MEMORY_RECALL_ENABLED=true
SHIJIAJING_MEMORY_COMMIT_ENABLED=true
SHIJIAJING_MEMORY_BACKEND=disabled
SHIJIAJING_MEMORY_DSN=
SHIJIAJING_MEMORY_RECALL_LIMIT=20
SHIJIAJING_RECENT_TURNS_LIMIT=6

SHIJIAJING_HITL_ENABLED=false
SHIJIAJING_RECOGNITION_REVIEW_THRESHOLD=0.70
SHIJIAJING_MEMORY_CONFIRMATION_REQUIRED=true

SHIJIAJING_CACHE_BACKEND=disabled
SHIJIAJING_CACHE_DSN=

SHIJIAJING_RETRIEVAL_FUSION_STRATEGY=weighted
SHIJIAJING_RETRIEVAL_RRF_K=60
SHIJIAJING_RETRIEVAL_RERANK_LIMIT=60
SHIJIAJING_RETRIEVAL_RERANK_ENABLED=false
SHIJIAJING_RETRIEVAL_INDEX_VERSION=

SHIJIAJING_EVENT_STORE_BACKEND=disabled
SHIJIAJING_EVENT_STORE_DSN=
```

`memory_backend`、`event_store_backend` 首版只接受 `disabled|sqlite|postgres`；
`cache_backend` 额外接受 `memory`。未知值启动失败并列出精确字段和值。

### 13.3 配置校验

- `memory_enabled=true` 时 `MEMORY_BACKEND` 不能为 disabled，且 DSN 必填。
- `memory_commit_enabled=true` 时 `memory_recall_enabled` 必须为 true；两个字段只接受
  部署配置，不由客户端请求覆盖。
- `graph_persistence_mode=native` 时现有 `CHECKPOINT_BACKEND`、`CHECKPOINT_DSN` 必填。
- `hitl_enabled=true` 只允许 native persistence。
- cache disabled 时 DSN 不需要；sqlite/postgres 时 DSN 必填。
- Event Store disabled 只允许测试；生产装配必须配置 sqlite 或 postgres。
- 所有 threshold、limit、TTL 在 `Settings` 初始化后执行范围校验；五类缓存 TTL 必须为
  至少 `1` 秒，并由对应节点从 `Settings` 读取。

### 13.4 `.env.example` 修正

现有 `.env.example` 的全部变量必须增加 `SHIJIAJING_` 前缀，与 `_env_name()` 精确一致。
本阶段新增变量也使用同一前缀。文档、示例、测试环境字典不得继续使用无前缀名称。

### 13.5 AgentDependencies

`AgentDependencies` 固定新增：

```python
graph_checkpointer: BaseCheckpointSaver[Any]
request_ledger: RequestLedgerPort
memory: MemoryPort
cache: VersionedCachePort
event_store: EventStorePort
```

legacy 兼容期保留原 `checkpoint: CheckpointPort | None`，只允许迁移路径调用；native 正常
执行节点不得调用它。

## 14. 目录与文件改动清单

### 14.1 新增文件

```text
src/shijiajing_agent/
├── runtime.py
├── adapters/
│   ├── langgraph_persistence.py
│   ├── request_ledger.py
│   ├── memory.py
│   ├── cache.py
│   └── event_store.py
├── domain/
│   ├── memory_policy.py
│   ├── retrieval_fusion.py
│   └── retrieval_reranking.py
├── nodes/
│   └── memory_nodes.py
├── ports/
│   ├── request_ledger.py
│   ├── memory.py
│   ├── cache.py
│   └── event_store.py
├── subgraphs/
│   ├── __init__.py
│   ├── recognition.py
│   ├── intent.py
│   ├── retrieval.py
│   ├── explanation.py
│   └── memory.py
└── tools/
    ├── migrate_state.py
    └── repair_events.py

tests/
├── contract/
│   ├── test_native_checkpointers.py
│   ├── test_request_ledger.py
│   ├── test_memory_adapters.py
│   ├── test_cache_adapters.py
│   └── test_event_store.py
├── unit/
│   ├── test_engineering_components.py
│   ├── test_hitl_nodes.py
│   ├── test_migrate_state.py
│   ├── test_repair_events.py
│   ├── test_retrieval_fusion.py
│   └── test_runtime.py
└── workflow/
    ├── test_cache_safety.py
    ├── test_native_hitl.py
    ├── test_runtime.py
    ├── test_subgraphs.py
    └── test_workflow_paths.py

docs/
├── memory.md
├── multi_agent.md
└── operations/
    ├── state_migration.md
    └── event_repair.md
```

实现阶段将领域/路径测试合并到上述实际文件；合并不减少覆盖范围，完整验证仍以 `pytest`
收集到的全部测试和 §15 各项断言为准。

### 14.2 必改文件

- `contracts.py`：新增 §5 契约，扩展 `IntentPatch`、`RetrievalCandidate`、
  `ConstraintSource`。
- `errors.py`：新增 §5.6 的精确错误码、异常类型和响应映射。
- `state.py`：升级 schema，增加 §12 字段和 turn 初始化规则。
- `graph.py`：根图改为 Supervisor、装配子图、并行汇合、native compile。
- `facade.py`：start/resume、Request Ledger、native config、兼容 run。
- `config.py`：新增 Settings、环境变量、交叉校验。
- `deps.py`：装配 checkpointer、ledger、memory、cache、event store。
- `runtime.py`：统一持有全部异步资源的打开、setup、关闭生命周期。
- `adapters/checkpoint.py`：只补 legacy 迁移读取和 schema 1.1 反序列化。
- `adapters/milvus_retrieval.py`：抽离融合策略，接入 reranker 版本。
- `nodes/intent_nodes.py`：接入 memory directives 和 memory defaults。
- `nodes/matching_nodes.py`：输出同款 review interrupt 所需结构化候选。
- `prompts/intent.md`：增加显式记忆 directive 输出规则。
- `.env.example`：修正全部前缀并增加新变量。
- `pyproject.toml`：注册两个运维 CLI；收紧 LangGraph 依赖到当前 1.x 主版本并保持
  `uv.lock` 已解析版本。
- `README.md`、`docs/architecture.md`、`docs/workflow.md`、`docs/contracts.md`、
  `docs/configuration.md`、`docs/troubleshooting.md`：同步最终行为。

## 15. 测试计划

### 15.1 持久化与幂等

- SQLite/PostgreSQL native saver setup、save、resume、history、delete thread contract。
- 每个主节点后模拟进程中断，恢复后不重复执行已完成的非幂等动作。
- 同一 `(session_id, request_id)` 并发两次只产生一个 Request Ledger 结果。
- 相同 request 重放返回字节等价业务响应，不增加模型调用、记忆 version 和事件副作用。
- legacy 1.0 状态导入 1.1 后业务约束、recognition、候选缓存和响应一致。
- schema 不兼容、损坏 payload、数据库不可用保持精确错误语义。

### 15.2 记忆

- owner A 的任何记忆不能被 owner B recall，`cross_user_memory_leakage=0`。
- global 和 category scope 精确隔离。
- 当前文本覆盖长期默认值。
- ranking prior 不进入 HardFilters。
- 普通搜索不生成 MemoryMutation。
- UPSERT/FORGET/CLEAR_OWNER 重放幂等，重复 mutation 数为 0。
- commit 失败不出现“已记住”。
- list/forget/clear 能处理空 owner、未知 key 和已 forgotten 记录。
- `recent_turns` 永远不超过配置上限。

### 15.3 Multi-Agent

- 相同 recorded fixture 下，拆分前后 `effective_constraints`、SKU group、价格、排序和
  completion reason 一致。
- Recognition/Intent 并行分支写字段无冲突。
- 单个子图超时或失败按 §8.4 精确降级。
- 子图不能修改授权表之外的根状态字段。
- 每个 Agent 开始和结束都有成对事件。

### 15.4 HITL

- 四类 interrupt 触发、序列化、暂停、approve/edit/reject、resume 全路径。
- 错误 session、错误 owner、错误 interrupt_id 拒绝恢复。
- resume 重放节点不重复 commit memory、event 或 request result。
- `hitl_enabled=false` 完全保持现有 clarification 回归行为。

### 15.5 Cache 与检索

- canonical JSON 不受 dict 插入顺序影响。
- model/prompt/taxonomy/index/fusion/rerank 任一版本变化都 cache miss。
- Cache 故障等价于 miss，不影响最终结果。
- WeightedScoreFusion 与当前固定夹具输出一致。
- RRF 在输入通道排列变化时结果稳定。
- reranker 不违反 HardFilters，不修改 Offer 价格，不修改最终 GroupRanker 业务分。
- retrieval 评测比较 weighted、RRF、weighted+rerank，只有非阻断回归方案允许成为默认。

### 15.6 Event 与可观测性

- Event append 幂等和冲突检测。
- turn/agent/model/retrieval/cache/memory/checkpoint span 父子关系正确。
- Trace/Event payload 不出现 API key、DSN、data URL、完整用户文本和完整 Prompt。
- Event Store 故障增加指标；request/memory 真实事务结果不被错误回滚。
- repair CLI dry-run 不写数据，apply 只补缺失一致性事件。

### 15.7 固定不变量门禁

- 用户硬过滤违反数 = 0。
- 跨用户记忆泄漏数 = 0。
- 重放重复副作用数 = 0。
- 错 SKU 同组数 = 0。
- 价格事实错误数 = 0。
- Event/Trace 敏感字段泄漏数 = 0。
- 现有阻断评测指标不得低于本阶段执行前记录的基线。

## 16. 评测数据扩展

新增种子数据：

```text
src/shijiajing_agent/data/eval/
├── memory_dataset.jsonl
├── multi_agent_dataset.jsonl
├── interrupt_dataset.jsonl
└── cache_dataset.jsonl
```

每条 memory 样本必须含：owner、session 序列、显式 directive、期望 scope、期望 key/value、
期望最终约束、期望 notices 和 forget 后状态。

每条 multi-agent 样本必须含：子图输入、子图输出、汇合状态和最终业务结果。

每条 interrupt 样本必须含：触发前状态、interrupt payload、resume payload、期望恢复节点和
副作用计数。

每条 cache 样本必须含：完整版本向量、预期 hit/miss、模型调用计数和最终结果哈希。

仓库现有 provisional 模拟数据不能用于证明真实用户偏好学习效果。本阶段只评测显式记忆
规则和工程不变量，不声称获得线上个性化收益。

## 17. 执行顺序

执行 Agent 必须按下列顺序实施；前一步门禁失败不得进入下一步：

1. 记录当前 `uv.lock` 版本、测试、ruff、pyright、离线评测和关键延迟基线。
2. 修正 `.env.example` 全部 `SHIJIAJING_` 前缀，补配置契约测试。
3. 在 `contracts.py` 增加 §5 全部契约和序列化测试，不改图行为。
4. 将 `SCHEMA_VERSION` 升到 1.1，完成 legacy 1.0 → 1.1 纯函数迁移和测试。
5. 实现 Request Ledger 双后端，先替换 Facade 的 cached response 查询，不改图持久化。
6. 实现 native async checkpointer、`open_agent_runtime()` 生命周期和 native recovery 测试。
7. 增加 persistence mode，legacy/native 双路径跑相同 workflow fixtures。
8. 完成 inspect/validate 迁移 CLI；检查现有 checkpoint 数据后才能把开发默认切到 native。
9. 实现 MemoryPort、双后端、mutation 幂等和 Memory Policy。
10. 增加 recent turns、memory directives、recall/prepare/commit 节点；默认 memory disabled。
11. 增加 memory 数据集与全部隔离、覆盖、遗忘、故障测试。
12. 抽取五个子图；先串行接回根图，证明业务结果与原图一致。
13. 只并行 Recognition/Intent，增加汇合和故障隔离测试。
14. 实现 AgentTurnResult、start/resume 和四类 interrupt；默认 HITL disabled。
15. 实现 VersionedCachePort 和五类 cache wrapper；默认测试使用 disabled/in-memory。
16. 抽取 WeightedScoreFusion，证明与现有召回完全一致。
17. 增加 RRF 和 CandidateRelevanceReranker；运行三组 retrieval 对比评测后选择配置，
    默认仍保持 weighted，直到门禁证明可切换。
18. 实现 EventStorePort、事件表、事件修复 CLI。
19. 实现 OpenTelemetry span、指标和脱敏测试。
20. 更新全部文档、示例、运维手册和完整回归报告。
21. native persistence、memory、HITL、cache、event store 按独立 feature flag 灰度启用。
22. 观察期通过后删除 Facade 的 legacy 写路径；legacy 数据删除不属于本阶段。

## 18. 验收命令

执行 Agent 必须在完成报告中记录每条命令的退出码和摘要：

```bash
uv sync --all-extras
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright
uv run pytest -q
uv run shijiajing-eval --no-gate
uv run shijiajing-migrate-state inspect
uv run shijiajing-migrate-state validate
uv run shijiajing-repair-events --dry-run
uv run shijiajing-preflight --json
uv run shijiajing-preflight --storage-only --verify-trace --json
uv run shijiajing-benchmark --report-dir reports --warmup 5 --iterations 30
```

由于仓库现有完成报告记录过 pyright 基线错误，执行第一步必须重新记录当前实际基线。
本阶段新增和修改文件必须贡献 0 个新 pyright 错误；不得以“既有错误”为理由引入新增错误。

PostgreSQL contract 测试使用 `-m integration` 单独执行并记录：

```bash
uv run pytest -q -m integration tests/contract/test_native_checkpointers.py
uv run pytest -q -m integration tests/contract/test_request_ledger.py
uv run pytest -q -m integration tests/contract/test_memory_adapters.py
uv run pytest -q -m integration tests/contract/test_cache_adapters.py
uv run pytest -q -m integration tests/contract/test_event_store.py
```

发布验收必须同时设置 `SHIJIAJING_REQUIRE_POSTGRES=1`；缺少
`SHIJIAJING_TEST_POSTGRES_DSN`、Docker Engine 或数据库连接时必须返回非零退出码，不能把
skip 计为通过。普通开发运行不设置该开关时，环境不足可以明确 skip。

## 19. 发布与回滚

### 19.1 Feature flags

发布时按以下顺序切换：

1. `SHIJIAJING_GRAPH_PERSISTENCE_MODE=legacy`，只上线新契约和新存储表。
2. 仅测试 session 使用 native，比较最终状态和 Request Ledger。
3. 全量 native，保留 legacy 表只读。
4. 开启 Memory recall，保持 `SHIJIAJING_MEMORY_COMMIT_ENABLED=false`。
5. 观察 recall 指标后开启 `SHIJIAJING_MEMORY_COMMIT_ENABLED=true`。
6. 开启子图并行。
7. 开启 HITL。
8. 开启 cache。
9. 开启 RRF/rerank 的评测胜出配置。
10. 开启持久化 Event Store 和 OpenTelemetry 导出。

`SHIJIAJING_MEMORY_RECALL_ENABLED` 与 `SHIJIAJING_MEMORY_COMMIT_ENABLED` 是 Settings 的
私有部署配置，只允许通过环境变量装配，不得暴露给客户端输入；commit 开启时 recall 必须
同时开启。

### 19.2 回滚原则

- native 持久化失败：切回 legacy 只允许在没有 native-only interrupt 中间态时执行；回滚
  工具必须先列出 active interrupts。
- Memory 失败：关闭 Memory，不删除数据；会话工作流继续运行。
- Multi-Agent 失败：关闭并行，子图串行运行；不回退领域算法。
- HITL 失败：关闭 HITL，恢复 clarification response。
- Cache 失败：切换 disabled，不清除正确性数据。
- RRF/rerank 回归：切回 weighted 基线。
- Event/OTel 失败：关闭导出，保留本地修复队列和真实业务存储。

## 20. Definition of Done

只有同时满足以下条件，本阶段才能标记完成：

1. §17 全部步骤完成，未跳步。
2. §18 所有非 integration 命令完成并记录；PostgreSQL integration 测试完成并记录。
3. §15.7 六项固定不变量全部为 0 违规。
4. legacy/native 在相同 workflow fixture 上业务输出一致。
5. 跨 session 显式记忆可以 recall、覆盖、查看、遗忘和清除，跨 owner 不泄漏。
6. 四类 interrupt 均可安全 resume，重放无重复副作用。
7. 缓存版本变化全部产生 miss，Cache 故障不改变最终业务结果。
8. Weighted 融合与改造前基线一致；RRF/rerank 是否启用由评测报告明确决定。
9. 任一 request 可以通过 Event Log 和 Trace 还原 Agent/节点/版本/降级路径。
10. 所有新增数据库结构都有 setup/migration、contract 测试、备份和回滚说明。
11. README、架构、工作流、契约、配置、故障排查、记忆、Multi-Agent 和运维文档与代码一致。
12. 完成报告如实列出未完成项、数据可信等级、外部依赖和实测结果，不以计划目标代替
   实际完成状态。

## 21. 本次修订的可执行补充

本节是对前述设计中容易产生实现歧义的部分的固定解释，执行代码和测试必须以本节为准。

### 21.1 LangGraph 1.x Checkpointer 装配

当前 `uv.lock` 固定为 `langgraph==1.2.11`、`langgraph-checkpoint==4.2.0`、
`langgraph-checkpoint-sqlite==3.1.1`、`langgraph-checkpoint-postgres==3.1.2`。

- `AsyncPostgresSaver.from_conn_string()` 支持 `serde` 参数，使用
  `JsonPlusSerializer(pickle_fallback=False, allowed_json_modules=...,` 
  `allowed_msgpack_modules=...)` 直接装配。
- `AsyncSqliteSaver.from_conn_string()` 只接受连接字符串，不接受 `serde`。SQLite 必须由
  `open_graph_checkpointer()` 自己打开 `aiosqlite.Connection`，再构造
  `AsyncSqliteSaver(connection, serde=serializer)`；退出上下文时先关闭 saver，再关闭连接。
- 两种 saver 在 runtime 启动阶段都显式执行 `await saver.setup()`；禁止在首个请求中执行 DDL。
- `build_graph()` 只在 `graph_checkpointer` 非空时传入 `checkpointer`，兼容现有 Fake 测试装配。

### 21.2 Memory 值域与稳定标识

第一版长期记忆键和值类型固定为：

| `memory_key` | 值类型与规范化 |
|---|---|
| `max_price` / `min_price` / `min_rating` | 有限非负 `float`；价格最多两位小数，评分范围 `0..5` |
| `platforms` / `colors` / `negative_terms` | 非空字符串列表；去除首尾空白、去重、保持首次出现顺序，最多 20 项 |
| `sort_by` | 现有 `SortBy` 枚举值 |
| `preferences` | 现有 `Preference` 枚举值列表，去重后最多 10 项 |

`memory_id` 使用 `sha256(memory_owner_id | scope_key | memory_key)` 的 64 位十六进制摘要。
`mutation_id` 仍使用 §7.4 的 directive 输入计算。`MemoryMutation` 的 `value` 必须在
进入 adapter 前完成白名单校验，adapter 不接受未经校验的自由 JSON。

### 21.3 HITL 专用恢复契约

`AgentInterrupt.payload` 和 `AgentResume.value` 仅作为外层 JSON 信封；内部必须按
`InterruptKind` 使用专用模型：

- `CLARIFICATION`：`ClarificationResume(action=select, option_id)` 或
  `ClarificationResume(action=answer, text)`。
- `RECOGNITION_REVIEW`：`RecognitionReviewResume(action=approve|reject|edit, correction)`。
- `SAME_ITEM_REVIEW`：`SameItemReviewResume(action=accept|split)`。
- `MEMORY_CONFIRMATION`：`MemoryConfirmationResume(action=approve|reject)`。

`interrupt_id` 使用
`sha256(session_id | request_id | turn_id | kind | node_name | interrupt_generation)` 计算；
其中 `interrupt_generation` 从 `0` 开始持久化在 `AgentState`，每次实际产生 interrupt
时递增一次。这样同一 turn 内同一节点连续产生同类 interrupt 时仍然拥有不同的恢复凭证。
checkpoint 记录 `resume_consumed=false`，成功恢复后原子改为 `true`。已消费或不匹配的
`interrupt_id` 必须拒绝恢复，禁止重复执行副作用；异常 resume 释放未完成的 claim，允许
同一个原始 interrupt 在不产生新副作用的前提下重试。
如果 native `start()` 在同一 thread 发现 active interrupt，相同 `request_id` 且调用上下文
一致时直接返回原 interrupt；不同 `request_id` 必须拒绝覆盖，避免悬挂 checkpoint 和重复
触发副作用。

### 21.4 Event Store 的可恢复边界

`request_result_committed`、`memory_committed`、`memory_forgotten` 是一致性事件，必须由
真实事务成功后追加，并由 repair CLI 可重建。普通诊断事件允许降级丢失；因此 Definition of
Done 的“完整还原”仅对一致性事件、Checkpoint 和成功写入的诊断事件生效，不把普通诊断事件
写入失败误报为完整审计。

`sequence` 不使用并行完成顺序；由 `(agent_name, node_name, event_type, attempt)` 组成，
`attempt` 存入 checkpoint 并在节点重放时复用，保证 event_id 在 replay 和并行执行中稳定。

### 21.5 垂直切片门禁

二期不以“全部文件已创建”作为阶段完成标准，而按下列门禁推进：

1. Reliability slice：`.env.example`、完整 pytest、ruff format、native SQLite、Request
   Ledger、legacy/native 对照和进程重启恢复全部通过。
2. Memory/HITL slice：owner 隔离、值域校验、覆盖/遗忘、四类 interrupt 和重复 resume
   全部通过，默认关闭不改变现有 workflow 输出。
3. Retrieval/Observability slice：weighted 输出与基线一致、版本变化必 miss、缓存故障不
   改变结果、事件幂等与脱敏测试通过后才允许切换默认策略。

## 22. 当前实施状态（2026-08-22）

本文件保持“执行中”，不把已创建文件等同于阶段完成。当前代码已落地：

- Reliability：schema 1.0 → 1.1 迁移、native SQLite/PostgreSQL Checkpointer 装配、
  Request Ledger、native `start/resume`、运行时资源生命周期和旧图回归；迁移 CLI 提供
  只读预览与显式 `migrate --apply`，checkpoint 提交成功后追加 `checkpoint_migrated`；
  `checkpoint_migration_audit` 保障 Event Store 暂时不可用时可重复补发审计事件；新增
  SQLite native active interrupt 跨 runtime 重开后 resume 回归；native runtime 启动阶段
  setup resume fence，异常 resume 释放未完成 claim；`interrupt_generation` 持久化并参与
  interrupt ID，避免同一 turn 内重复同类 interrupt 复用恢复凭证；repair CLI 已支持
  SQLite/PostgreSQL source 与 Event Store，SQLite backup/restore 使用 SQLite backup API
  并执行 integrity_check，backup 工具新增 `verify` 模式比较内容摘要；新增真实 SQLite
  native runtime 重开与
  Request Ledger 跨 runtime 幂等回归，以及 legacy/native 相同 fixture 业务结果对照。
  Request Ledger 读取会校验持久化 `response_hash`，摘要冲突按账本不可用拒绝返回；legacy
  `run()` 与 native `start()` 对 Ledger 写入失败统一返回类型化失败响应。
  legacy SQLite 与 LangGraph native serializer 共用持久化脱敏边界，Checkpoint 不保存原始
  request text、correction、metadata 或图片 URI；会话摘要只保存文本摘要哈希/长度，检索查询
  的持久化读取不保留原始 query text；Cache adapter 拒绝自由 `text`/`prompt` 字段，
  explanation cache 只接受通过事实校验的字段化 `explanation_text`。
  Retrieval fallback 与节点错误只保留固定原因和用户可操作消息，不把底层异常、host 或 DSN
  写入 AgentState。
  `shijiajing-preflight` 已提供配置、资源 setup/close 和机器可读结果检查；SQLite
  backup/restore/verify 已改为 staging 完整性与内容摘要校验后原子提交，失败不改写已有目标。
  新增 SQLite 多资源 backup/restore 恢复演练：checkpoint、Request Ledger、Memory、Cache
  和 Event Store 经过隔离恢复后，native active interrupt 可继续 resume，Memory/Event Store
  可读，重复 request 命中恢复后的 Ledger。
  native thread 新 turn 已建立明确边界：重置本轮查询、候选、排序、解释、响应、HITL
   状态和事件历史，保留有效约束、识别历史、subject 与 recent turns，并以回归测试防止
   同一 session 的上一轮结果泄漏到下一轮。
   `recent_turns` 已从长期 Memory 分支解耦：legacy/native 在长期 Memory 关闭时也会在
   terminal response 后追加并恢复 bounded conversation memory，失败终态同样纳入摘要。
   native 图 timeout/内部异常的 FAILED response 在 Request Ledger 已装配时写入 Ledger，并
   尝试写回 `append_turn_summary` 终态 checkpoint；存储不可用时不伪造持久化成功。
   节点投影为 Recognition、Intent、Retrieval、Explanation、Memory 追加稳定幂等的
   `agent_started` / `agent_completed` / `agent_failed` 事件，和 supervisor turn 事件分离。
   `graph.py` 已实际装配 Recognition、Intent、Retrieval、Explanation 专业子图；Memory
   以 recall/prepare 子图边界接入，commit 继续由根图在最终响应后执行。并行理解分支通过
   授权字段适配器回写，避免完整子图快照造成并发状态写冲突；五个子图入口均有独立执行回归。
   根图边界已增加五类 Pydantic 子图输出模型；未知嵌套字段、非法结构会在回写前拒绝，
   边界校验异常会标记对应子图入口，继续沿用 Agent failure 事件语义。
  新增 `shijiajing-backup-postgres`，对 `pg_dump`/`pg_restore` 提供不经 shell 的安全封装：
   dump 默认拒绝覆盖，先用 `pg_restore --list` 验证临时归档后再替换；restore 必须显式
   `--apply`；归档校验失败会保留已有 dump 并清理 staging，已补失败路径契约测试。普通
   数据库密码移出 client-tool 命令行并通过 `PGPASSWORD` 传递，`sslpassword` 直接拒绝。
  当前真实生产数据库演练仍未执行。
- External dependency path：新增 `deploy/phase2/docker-compose.yml`、
  `deploy/phase2/otel-collector-config.yaml` 和对应 README，固定 PostgreSQL 16、
  OTLP HTTP/GRPC receiver、Collector debug exporter 与本地端口映射；Compose 静态配置
  解析通过，缺少 `POSTGRES_PASSWORD` 时明确失败。该路径用于开发/集成环境，不能替代真实
  PostgreSQL contract、生产备份恢复或外部 Collector 验收。
- External verification orchestration：新增 `deploy/phase2/verify.ps1`，固定执行两个服务的
  health check、严格 PostgreSQL integration gate、`shijiajing-preflight --verify-trace`、
  Collector 日志和 `docker compose down`；默认使用独立开发端口且不删除数据库 volume；每次
  运行归档 transcript、机器可读 summary 和已执行命令清单。Docker daemon 不可用时脚本以非零
  退出并清理，不把环境缺失转成验收通过。
- Integration gate：PostgreSQL contract 增加 `SHIJIAJING_REQUIRE_POSTGRES=1` 严格模式；
  该模式把无 DSN、无 Docker Engine 或连接失败转换为非零退出码，普通开发模式仍保留
  明确 skip。
- Memory/HITL：白名单记忆值域、SQLite/PostgreSQL Memory、owner 隔离与 mutation 幂等；
  Memory adapter 边界再次执行白名单和值域校验，同一 `mutation_id` 的不同 payload 明确
  抛出 `MemoryConflictError`，不允许绕过节点写入自由 JSON；
  clarification、recognition review、same-item review、memory confirmation 四类
  interrupt 已有类型化 resume 路径；recognition review 覆盖缺 category、未解析字段和低
  置信度触发，编辑后执行 taxonomy normalization；native start/resume 已追加
  `agent_interrupted` / `agent_resumed` 审计事件，Memory recall 已追加 `memory_recalled`
  审计事件；PostgreSQL Memory commit 已增加 owner 级事务 advisory lock，避免并发 replay
  重复应用；重复 clarification 的新 interrupt ID 与 resume fence 回归已通过。
- Retrieval/Observability：Weighted/RRF、确定性 rerank、vision/intent/query-rewrite/
  retrieval/explanation 版本感知 cache、SQLite/PostgreSQL Event Store、事件修复 CLI、
  OpenTelemetry span sink，以及五个专业子图的独立装配入口；turn/agent/model/retrieval/
  cache/memory/checkpoint/request-ledger 层次已接入，节点事件投影 prompt/taxonomy/index/
  fusion/rerank 版本与 token usage；
  `AgentEventRecord` 对事件 payload 递归拒绝凭证、DSN、原始文本/Prompt、图片 data URL
  和模型原始输出字段，防止绕过事件适配器写入未脱敏内容；
  五类 cache get 已追加 `cache_hit` / `cache_miss` 审计事件；wrapper 读取后执行
  Pydantic、检索硬过滤和解释事实一致性校验，get/set/delete 故障按 miss 处理并增加
  `cache_failure_total`；新增只读
  `shijiajing-reconstruct-turn`，对同一 turn 的四个标识做一致性校验并输出
  节点、版本和终态时间线；Event Store 的 InMemory/SQLite/PostgreSQL/还原工具共用
  `(occurred_at, event_type_priority, event_id)` 稳定排序，避免同时间戳生命周期反转；OTLP span 的 Trace ID 由业务 `trace_id` 稳定派生，跨 sink
  重启连续性已有本地 exporter 回归。
- OTLP failure semantics：`OpenTelemetryTraceSink` 包装 exporter 的结果，遇到
  `SpanExportResult.FAILURE` 会抛出可由 Facade 捕获的异常；业务仍不被 trace sink 故障阻断，
  但 `trace_sink_failure_total` 不再漏计 exporter 返回失败。
 - OTLP verification path：`shijiajing-preflight --storage-only --verify-trace --json` 会向
   配置的 `SHIJIAJING_TRACE_DSN` 发送固定无业务数据的合成 turn span，并在 exporter 失败
   时返回退出码 2；它提供本地/临时 Collector 的真实发送验证，不替代外部观测系统验收。
 - Preflight failure semantics：`shijiajing-preflight --json` 对配置校验保留精确缺失字段，
   对资源/provider 异常只返回固定可操作消息，禁止把原始异常、主机、DSN 或密钥写入 CLI。
   `shijiajing-migrate-state`、`shijiajing-repair-events` 和 `shijiajing-reconstruct-turn`
   复用同一公开错误边界。
- 评测与运行时补强：新增 `memory_dataset.jsonl`、`multi_agent_dataset.jsonl`、
  `interrupt_dataset.jsonl`、`cache_dataset.jsonl` 及严格行模型；离线加载器现支持十一类
  数据集，报告只记录这四类工程夹具摘要，不将其混入商品质量指标；新增工程执行报告
  实际运行 Memory/Cache adapter 和四类专用 resume 模型。另新增
  `retrieval_strategy_dataset.jsonl`，实际比较 weighted、RRF、weighted+rerank，当前
  硬过滤违规数为 0，推荐默认仍为 weighted；工程报告同时输出 §15.7 六项固定不变量的
  样本数、违规数和证据来源。`--live` 路径通过 `open_agent_runtime()`
   复用受生命周期管理的依赖资源；已有策略夹具会由真实 `RetrievalResult` 重建通道顺序，
   不改写 expected Gold ID；Gold catalog 缺少任一候选映射时直接失败，不回退到 Offer source key
   或旧夹具映射。
- 性能基线与延迟门禁：`shijiajing-benchmark` 默认使用 seed/offline 样本输出
  p50/p95/p99、迭代参数及运行环境，禁止附带性能阈值；显式 `source=formal`、数据目录
  和 `max-p95-ms` 后才执行指定策略的 p95 门禁；formal 目录还必须通过 frozen manifest、
  文件摘要、非空 `retrieval_strategy_dataset.jsonl`、策略行的
  `meta.label_source=adjudicated` 和完整 Gold SPU/SKU 映射校验，失败返回退出码 1 并保留
机器可读报告；每次运行先清理旧延迟报告，并通过 staging 提交新报告，失败不保留旧产物。
  当前尚未用正式数据执行该门禁。
- 发布门禁读取 `eval_report.json` 时必须校验报告 schema、十一类数据集摘要、全部阻断指标、
  代码定义的阈值及派生 gate 字段；读取 `benchmark_report.json` 时必须校验完整
  `BenchmarkReport` 和 weighted/RRF/weighted_rerank 三种策略，不能只依据少量布尔字段判定通过。
- 评测数据晋级：`shijiajing-build-eval freeze` 已实现严格的人工仲裁记录、dataset_id/
  dataset_version、全量 `adjudicated` 行校验和不可覆盖复制；它只提供正式数据进入
  `frozen` 的安全路径，不代表当前已拥有正式人工仲裁数据。
- 生产配置约束：`SHIJIAJING_ENV` 已固定为 `dev|test|prod`；当且仅当环境为 `prod`
  时，`EVENT_STORE_BACKEND=disabled` 被拒绝；Checkpoint 的 sqlite/postgres DSN 在
  legacy/native 两种模式下均按 backend 强制校验。Fake `deps_factory` 只用于测试/示例，
  不触发生产资源配置校验。
- Windows 异步 CLI 兼容：所有连接外部异步资源的 CLI 统一经过
  `shijiajing_agent.asyncio_compat.run`；Windows 使用 `SelectorEventLoop`，避免
  `psycopg` 与 `ProactorEventLoop` 不兼容，Linux/macOS 仍调用默认 `asyncio.run` 行为；
  三个 `examples/` 入口同样经过该兼容入口。
- 配置解析错误边界：数值环境变量在 `load_settings()` 阶段以精确的
  `SHIJIAJING_*` 字段名返回安全配置错误，preflight 保留该字段信息；解析后的有限性、
  范围和跨字段关系继续由 `Settings.validate_engineering()` 统一校验。

截至 2026-08-22，本地可执行的 PostgreSQL/OTLP 验收已完成：
`deploy/phase2/verify.ps1 -HealthTimeoutSeconds 120` 使用 PostgreSQL 16 与 OTLP Collector
真实容器执行五组 contract，共 8 个测试通过；PostgreSQL 重启后的健康恢复通过；
`shijiajing-preflight --storage-only --verify-trace --json` 返回
`status=ok`、`trace_verified=true`，Collector 日志收到 3 个 spans。带
`-VerifyBackupRestore` 的本地演练生成 custom-format dump，通过 `pg_restore --list`，
恢复库 public 表数量为 10 对 10，固定哨兵数据恢复 1 行；证据分别归档于
`reports/phase2-verification/run-20260822-115908-020/summary.json` 和
`reports/phase2-verification/run-20260822-120647-895/summary.json`。

业务 PostgreSQL 适配器的连接池已支持 `SHIJIAJING_POSTGRES_POOL_MIN_SIZE=2`、
`SHIJIAJING_POSTGRES_POOL_MAX_SIZE=8`、`SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS=12.5`，
并已在 `reports/phase2-verification/run-20260822-122827-512/summary.json` 中完成真实
setup、contract、preflight、重启恢复和 OTLP 验收；native LangGraph saver 仍是依赖库 API
提供的单异步连接。

仍未满足 Definition of Done 的项目是生产范围事项：生产 PostgreSQL 的高可用、连接池容量、
故障切换、真实业务数据恢复、备份存储加密/保留/权限/跨区域恢复；生产 OTLP Collector 的
持久化、告警、查询、权限和保留策略；正式线上评测数据、人工仲裁冻结报告和正式数据上的
性能门禁；以及主机上 `shijiajing-backup-postgres` 使用已安装 `pg_dump`/`pg_restore` 的
真实 client tools 验收。上述门禁代码路径已具备，但当前没有对应的生产输入和外部系统证据。

Recognition/Intent 并行汇合、native/legacy 事件投影、五类缓存 wrapper、turn 只读还原工具和文档已落地，
三个 README 示例和用户修正实际写回也已补齐，但尚未据此把默认开关切换为新策略。因此发布默认继续使用 `legacy`、`memory disabled`、
`hitl disabled`、`cache disabled` 和 `weighted`，不得在没有对应实测记录时宣称二期已完成。

生产 `make_deps()` 先创建唯一 `MetricsPort`，并将其注入 Ark 模型、Milvus/本地检索适配器
和 `AgentDependencies`，保证模型调用、候选数量、零结果和 provider fallback 指标不会在装配
边界因 `metrics=None` 丢失；该行为由两种检索分支的 identity 回归锁定。

存储运维文档已按 §14.1 拆分为 `docs/operations/state_migration.md` 和
`docs/operations/event_repair.md`，`docs/operations_phase2.md` 保留为总入口；两个 runbook
均以对应 CLI 源码的精确参数为准，并覆盖 dry-run/apply、冲突、回滚和证据边界。
