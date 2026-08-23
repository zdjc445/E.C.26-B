# 受控层级式 Multi-Agent 升级方案

- 文档状态：执行中（阶段 1 已完成；阶段 2–4 已落地基础能力；阶段 5–6 尚未完成）
- 基线日期：2026-08-23
- 适用范围：`shijiajing-agent` Agent 核心，不包含 Web API 与客户端

## 1. 结论与目标

本项目应升级为**受控层级式 Multi-Agent**，而不是让多个 LLM 通过自由文本自行协商。
商品比价涉及用户硬过滤、价格、同款关系、SKU、排序与长期记忆写入，这些边界必须保持
结构化、可审计和可恢复。

目标架构由一个 Supervisor Agent 和五个 Specialist Agent 组成：

- Recognition Agent
- Intent Agent
- Retrieval Agent
- Explanation Agent
- Memory Agent

升级完成后，专业 Agent 不再接收和回写完整共享 `AgentState`。Supervisor 通过显式
`AgentTask` 派发任务，专业 Agent 使用独立输入、私有状态和工具权限执行任务，只能通过
`AgentResult` 与 `HandoffRequest` 返回结构化结果。Supervisor 是唯一可以更新规范业务状态、
批准副作用和生成最终 `AgentResponse` 的角色。

该方案保留现有确定性领域算法、native checkpoint、HITL、Request Ledger、Event Store、
Cache、Memory owner 隔离与发布门禁，不把确定性算法迁入 LLM。

## 2. 当前基线与差距

当前实现是 Supervisor 编排的专业 LangGraph 子图，详细现状见
[`docs/multi_agent.md`](../multi_agent.md)。当前已经具备：

- 根图名称 `shijiajing-supervisor`。
- Recognition、Intent、Retrieval、Explanation、Memory 五个专业子图入口。
- Recognition 与 Intent 的静态并行执行和 Barrier 汇合。
- 五种 Pydantic 子图输出契约与父图写字段投影。
- native checkpoint、四类 HITL、Agent 生命周期事件和幂等恢复基础设施。
- `SpecialistAgentName`、`AgentTask`、`AgentResult` 以及 `AgentState.agent_results` 契约骨架。

当前仍不属于严格的 Multi-Agent，具体差距如下：

| 能力 | 当前状态 | 目标状态 |
|---|---|---|
| 专业模块 | 可独立编译的子图 | 具有独立输入、私有状态、工具权限和任务生命周期的 Agent |
| 调度 | 根图静态边 | Supervisor 根据计划和结果动态派发 |
| 通信 | 共享 `AgentState` 字段 | `AgentTask`、`AgentResult`、`HandoffRequest` |
| 状态隔离 | 返回字段受限，读取完整状态 | 输入和输出均字段级隔离 |
| 任务规划 | 固定拓扑 | 结构化计划、任务 DAG、受控 replan |
| Agent 协作 | 无显式 handoff | Agent 提议、Supervisor 审批并创建后续任务 |
| 恢复粒度 | turn/graph | Supervisor plan 与单个 Agent task 双层恢复 |
| 副作用 | 根图节点控制 | Supervisor 授权、Agent 执行、ledger 幂等 |

现有 `AgentTask.input_payload` 与 `AgentResult.output_payload` 仍为 `dict[str, Any]`，并且
`agent_results` 目前只参与状态初始化、序列化和迁移，没有进入实际任务派发和结果归并链路。
这些现有类型应作为兼容入口，而不是直接作为最终 Multi-Agent 协议。

## 3. 设计原则

### 3.1 单一规范状态所有者

只有 Supervisor 可以更新规范业务状态，包括有效约束、最终 Recognition、最终候选、最终排序、
HITL 状态和 `AgentResponse`。Specialist Agent 只能提交结果或建议。

### 3.2 任务而不是共享状态

每个 Agent invocation 必须对应稳定的 `task_id`。输入是最小化、严格类型化的任务载荷；输出是
严格类型化的任务结果。Agent 不能依赖父图中未在任务载荷声明的字段。

### 3.3 动态但受控

Supervisor 可以动态跳过、并行、重试、降级或新增任务，但所有任务类型、Agent、依赖和工具
必须来自 allowlist。LLM Planner 只能提出结构化计划，不能直接执行工具或修改业务结果。

### 3.4 确定性领域逻辑不迁移到 LLM

以下能力继续保留在 `domain/`，由对应 Agent 调用：

- 用户硬过滤和来源优先级
- 查询改写硬过滤保护
- 同款硬冲突和 complete-link 聚类
- SKU 拆分
- 价格聚合与排序
- 证据事实一致性校验
- Memory 白名单、owner 隔离和 mutation 幂等

### 3.5 副作用必须显式授权

商品检索是只读外部调用。长期 Memory commit 是业务副作用，只能在最终响应确定、HITL 完成、
owner 验证通过和 mutation ledger 确认未执行后，由 Supervisor 派发专用 commit 任务。

### 3.6 全链路可恢复和可审计

计划、任务状态、Agent 结果、handoff、replan、interrupt 和副作用授权必须具备稳定 ID、事件记录
和 checkpoint 恢复语义。不得保存思维链、原始 Prompt、图片内容或模型原始响应。

## 4. 目标架构

```text
                            ┌────────────────────────────┐
AgentRequest ─→ AgentFacade │      Supervisor Agent      │
                            │ validate / plan / dispatch │
                            │ collect / reconcile / HITL │
                            │ replan / respond / commit  │
                            └─────────────┬──────────────┘
                                          │ AgentTask
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
             Recognition Agent      Intent Agent         Memory Agent
              private state          private state        private state
                    │                     │                     │
                    └──────────── AgentResult / Handoff ────────┘
                                          │
                                   Retrieval Agent
                                     private state
                                          │
                                  Explanation Agent
                                     private state
                                          │
                                     AgentResult
                                          │
                                    Supervisor finalize
```

建议的包结构：

```text
src/shijiajing_agent/
├── multi_agent/
│   ├── contracts.py
│   ├── state.py
│   ├── supervisor.py
│   ├── planner.py
│   ├── dispatcher.py
│   ├── reducers.py
│   ├── registry.py
│   ├── result_validation.py
│   └── agents/
│       ├── recognition.py
│       ├── intent.py
│       ├── retrieval.py
│       ├── explanation.py
│       └── memory.py
├── domain/
├── ports/
├── adapters/
├── subgraphs/                 # 迁移期间保留
└── graph.py                   # 迁移期间保留旧 Workflow
```

## 5. Supervisor Agent

### 5.1 职责

Supervisor 负责：

1. 校验请求、可信执行上下文和会话状态。
2. 生成并校验本轮 `ExecutionPlan`。
3. 找出依赖已满足的任务并并行派发。
4. 校验、去重和归并 `AgentResult`。
5. 合并 Recognition、Intent 与 Memory recall 结果。
6. 处理来源优先级、冲突、缺失字段和 HITL。
7. 根据失败类型执行 retry、fallback、handoff 或 replan。
8. 生成唯一的规范 `AgentResponse`。
9. 批准或拒绝 Memory commit 等副作用。
10. 写 Supervisor checkpoint、Request Ledger 和审计事件。

### 5.2 Planner

建议新增 `SupervisorPlannerPort`，名称属于本方案的新接口：

```python
class SupervisorPlannerPort(Protocol):
    async def create_plan(
        self,
        request: SupervisorPlanningInput,
    ) -> ExecutionPlan: ...

    async def revise_plan(
        self,
        request: SupervisorReplanningInput,
    ) -> ExecutionPlanPatch: ...
```

采用双层 Planner：

1. 确定性 Planner 根据输入形态生成合法基础计划。
2. Supervisor Model 可以在白名单内提出跳过、重试、handoff 或补充任务。
3. `PlanValidator` 对模型计划执行确定性校验。
4. 模型不可用或计划非法时使用基础计划，并记录 `planner_fallback`。

`PlanValidator` 必须验证：

- Agent 和任务类型均在 allowlist。
- 任务 DAG 无环。
- 所有依赖任务存在。
- 不超过配置的任务数、重规划次数、时间和 token 预算。
- Retrieval 只能在规范约束形成后启动。
- Explanation 必须依赖成功的 Retrieval 结果。
- Memory commit 必须依赖 Supervisor 授权。
- Planner 不能构造任意工具调用。
- Planner 不能修改用户锁定的硬过滤。

### 5.3 结果协调

Specialist Agent 的结果只是 proposal。Supervisor 根据当前公共契约中的来源优先级形成规范理解：

```text
USER_CORRECTION > USER_TEXT > VISION > MEMORY_EXPLICIT > DEFAULT
```

Retrieval 不能覆盖 `locked_by_user=True` 的字段；Explanation 不能修改价格、平台、排序或候选；
Memory mutation 在 commit 之前不能改变业务响应。

## 6. Specialist Agent 设计

### 6.1 Recognition Agent

输入：

- `ImageRef`
- 当前轮 `RecognitionCorrection`
- 上一轮有效 `RecognitionResult` 的授权摘要
- taxonomy 版本

私有状态：

- VLM 调用和 repair 次数
- 结构化输出摘要
- 标准化步骤
- 字段置信度、可见证据和未解析字段

输出：

- `RecognitionResult`
- 证据引用
- 是否建议 recognition review
- 固定错误码和降级信息

工具权限：Vision Port、taxonomy。不得读取长期 Memory、检索商品或修改有效约束。

### 6.2 Intent Agent

输入：

- 当前轮用户文本
- 上一轮有效约束摘要
- bounded recent turns
- 澄清选择或 resume 输入

输出：

- `IntentPatch`
- 缺失字段和澄清建议
- 冲突提示
- Memory directive proposal

工具权限：Intent Model、规则解析器。不得直接写 `ShoppingConstraints`，不得调用商品检索。

### 6.3 Retrieval Agent

Retrieval Agent 应拥有从查询改写到可解释排序结果的完整只读商品处理链路：

- 查询改写
- 混合召回
- 允许范围内的识别条件放宽
- 候选标准化
- 同款匹配
- SKU 拆分
- 价格聚合和排序
- 检索证据构建

这些算法继续使用现有 `domain/` 实现，不改为 LLM 推理。

输入：

- Supervisor 已确认的 `ShoppingConstraints`
- 已确认的 `RecognitionResult`
- 检索、融合、rerank 和索引版本
- 候选限制和执行预算

输出：

- `RetrievalQuery`
- `RankedGroup` 列表
- 检索证据引用
- 召回、放宽、fallback 和版本元数据
- 补充条件或 replan 建议

严格规则：

- 不得放宽 `locked_by_user=True` 的条件。
- 不得修改用户预算、平台等硬过滤。
- 查询改写模型不得覆盖 Supervisor 生成的硬过滤。
- 无证据候选不得进入 Explanation。

### 6.4 Explanation Agent

输入：

- `RankedGroup`
- `EvidenceBundle`
- 有效约束
- 允许引用的平台、价格、属性和证据 ID

输出：

- 解释文本
- `explanation_verified`
- 实际使用的证据引用
- 模板降级原因

工具权限：Explanation Model、事实验证器。不得执行检索，不得修改排序、价格或候选。事实检查失败
必须返回失败结果，由 Supervisor 派发模板解释任务或直接使用确定性模板。

### 6.5 Memory Agent

Memory Agent 拆分为三种任务：

```text
memory.recall
memory.prepare
memory.commit
```

- `memory.recall` 可以与 Recognition、Intent 并行，只读取经过验证的 `memory_owner_id`。
- `memory.prepare` 只能生成 `MemoryMutation` proposal，不能写数据库。
- `memory.commit` 只能在 Supervisor 授权后执行，并以 `mutation_id` 保证幂等。

Memory Agent 不接收原始图片、候选商品全集或其他 owner 的数据。

## 7. 任务与结果协议

### 7.1 任务类型

以下名称均为本方案建议新增的标识符：

```python
class AgentTaskKind(StrEnum):
    RECOGNIZE = "recognition.recognize"
    APPLY_CORRECTION = "recognition.apply_correction"
    PARSE_INTENT = "intent.parse"
    RETRIEVE_AND_RANK = "retrieval.retrieve_and_rank"
    EXPLAIN = "explanation.explain"
    MEMORY_RECALL = "memory.recall"
    MEMORY_PREPARE = "memory.prepare"
    MEMORY_COMMIT = "memory.commit"
```

### 7.2 AgentTaskV2

保留现有 `AgentTask` 作为 1.x checkpoint 兼容类型，新协议使用显式版本：

```python
class AgentTaskV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"]
    plan_id: str
    task_id: str
    parent_task_id: str | None
    agent_name: SpecialistAgentName
    task_kind: AgentTaskKind
    depends_on: list[str]
    attempt: int
    idempotency_key: str
    deadline_at: str
    budget: AgentTaskBudget
    input: AgentTaskInput
```

`AgentTaskInput` 使用带 discriminator 的严格 Pydantic 联合类型：

```python
AgentTaskInput = Annotated[
    RecognitionTaskInput
    | IntentTaskInput
    | RetrievalTaskInput
    | ExplanationTaskInput
    | MemoryTaskInput,
    Field(discriminator="kind"),
]
```

通用顶层不再携带 `memory_context`。只有确实获准读取 Memory 的任务输入才能包含相应字段，避免
把长期记忆默认暴露给所有 Agent。

### 7.3 AgentResultV2

```python
class AgentResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"]
    plan_id: str
    task_id: str
    agent_name: SpecialistAgentName
    task_kind: AgentTaskKind
    status: NodeStatus
    output: AgentTaskOutput | None
    error: AgentTaskError | None
    evidence_refs: list[str]
    handoff_requests: list[HandoffRequest]
    proposed_memory_mutations: list[MemoryMutation]
    usage: AgentTaskUsage
    output_hash: str
```

结果验证器必须执行：

- `agent_name` 与 `task_kind` 匹配。
- 输出类型与任务类型匹配。
- `FAILED` 必须携带类型化 `error`。
- `SUCCESS` 必须携带相应输出。
- 相同 `task_id` 重放时 `output_hash` 必须一致。
- 输出不能包含该 Agent 未授权的规范状态字段。

### 7.4 HandoffRequest

Agent 不能直接调用另一个 Agent，只能提交 handoff proposal：

```python
class HandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_agent: SpecialistAgentName
    requested_task_kind: AgentTaskKind
    reason_code: str
    input_refs: list[str]
```

Supervisor 校验依赖、权限、预算和重复任务后，才能创建新的 `AgentTaskV2`。

## 8. Supervisor 状态与并发归并

建议新增独立状态，不让 Specialist 继续共享当前完整 `AgentState`：

```python
class SupervisorState(TypedDict, total=False):
    schema_version: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    current_request: AgentRequest
    execution_context: AgentExecutionContext

    plan: ExecutionPlan
    task_records: dict[str, TaskRecord]
    task_results: Annotated[
        dict[str, AgentResultV2],
        merge_task_results,
    ]

    canonical_understanding: CanonicalUnderstanding
    active_interrupt: AgentInterrupt | None
    final_response: AgentResponse | None

    replan_count: int
    total_task_count: int
    budget_usage: SupervisorBudgetUsage
    notices: Annotated[list[str], merge_history]
    events: Annotated[list[AgentEventRecord], merge_history]
```

`merge_task_results` 按 `task_id` 合并：

- 首次结果写入。
- 相同 `task_id + output_hash` 视为幂等重放。
- 相同 `task_id` 但 hash 不同，产生 `TASK_RESULT_CONFLICT`，不得静默覆盖。

Specialist Agent 分别使用：

- `RecognitionAgentState`
- `IntentAgentState`
- `RetrievalAgentState`
- `ExplanationAgentState`
- `MemoryAgentState`

每个私有状态只包含对应任务、内部步骤、调用预算、错误、fallback、证据和最终结果。子图不再以
完整 `AgentState` 作为 input/output schema。

## 9. Supervisor 执行图

建议节点：

```text
validate_request
load_session
create_plan
validate_plan
dispatch_ready_tasks
collect_results
reconcile_understanding
validate_constraints
replan_or_continue
build_response
authorize_memory_commit
finalize_turn
```

动态派发使用当前依赖版本已经提供的 `langgraph.types.Send` 和 `Command`。示意代码：

```python
def dispatch_ready_tasks(state: SupervisorState) -> list[Send]:
    ready = find_ready_tasks(state["plan"], state["task_records"])
    return [
        Send(
            AGENT_NODE_BY_NAME[task.agent_name],
            {"task": task},
        )
        for task in ready
    ]
```

`collect_results` 必须根据当前批次 task ID 验证所有任务均进入终态，不能只依赖图拓扑推断 Barrier。

典型任务 DAG：

```text
T1 Recognition ─┐
T2 Intent ──────┼→ reconcile_understanding
T3 MemoryRecall ┘              │
                               ├─ 信息不足 → clarification HITL
                               │
                               └→ T4 Retrieval
                                      │
                                      ├─ 可恢复失败 → replan/retry/fallback
                                      │
                                      └→ T5 Explanation
                                             │
                                      build_response
                                             │
                                      T6 MemoryPrepare
                                             │
                                   可选 memory confirmation
                                             │
                                      T7 MemoryCommit
```

动态规则：

- 无图片且无 correction 时不创建 Recognition 任务。
- Memory 未启用时不创建 Memory 任务。
- 缺少品类时不创建 Retrieval，先进入 clarification。
- Retrieval 的条件放宽必须经 Supervisor 批准后重新派发。
- Explanation 失败不重跑 Retrieval，改用模板解释。
- Agent 的 handoff 只是 proposal，不直接改变计划。

## 10. 工具与数据权限

| Agent | 允许能力 | 明确禁止 |
|---|---|---|
| Supervisor | Planner、Agent registry、结果校验、HITL、规范状态归并 | 直接访问 Milvus 或直接写 Memory |
| Recognition | Vision、taxonomy | 长期 Memory、商品检索、约束归并 |
| Intent | Intent Model、规则解析 | 商品检索、直接写有效约束 |
| Retrieval | Query Rewrite、Embedding、Milvus、本地索引、确定性领域算法 | Memory owner、修改用户硬过滤 |
| Explanation | Explanation Model、事实验证 | 新检索、修改价格/候选/排序 |
| Memory | Memory Store、Memory policy | 原始图片、无关候选、跨 owner 数据 |

数据最小化要求：

- Intent 不接收图片 URI。
- Explanation 不接收原始图片。
- Retrieval 不接收 `memory_owner_id`。
- Recognition 不接收长期偏好。
- Event Store 不保存用户全文、Prompt、图片内容或模型原始响应。

## 11. 失败、重试与降级

| Agent/组件 | 处理策略 |
|---|---|
| Recognition | 有文本品类时继续；无可靠理解时进入 recognition review |
| Intent | 使用规则解析；仍缺少必要字段时进入 clarification |
| Retrieval | Milvus 不可用时本地词法降级；用户硬过滤零结果不放宽 |
| Explanation | 事实校验失败后使用确定性模板，不重跑 Retrieval |
| Memory recall | 非阻断，返回空上下文并记录 notice |
| Memory prepare | 非阻断，不产生 mutation |
| Memory commit | 不改变已生成的比价结果，但必须明确标记“记忆未保存” |
| Supervisor Planner | 回退确定性计划并记录 `planner_fallback` |

只有幂等只读任务可以自动重试。Memory commit 必须先查询 mutation ledger；当提交结果未知时，
不得盲目重试。

预算至少覆盖：

- 单 Agent deadline
- 单任务模型调用次数
- 单任务 token 使用量
- 每轮最大任务数
- 每轮最大 replan 次数
- 整轮 wall-clock timeout

达到预算时返回类型化失败或降级结果，并保留完整审计事件。

## 12. Checkpoint、幂等与恢复

Multi-Agent 模式必须使用 native graph persistence。建议新增以下配置；这些名称不是当前已有变量：

```text
SHIJIAJING_ORCHESTRATION_MODE=workflow|multi_agent_shadow|multi_agent
SHIJIAJING_SUPERVISOR_MODEL=
SHIJIAJING_MAX_AGENT_TASKS=
SHIJIAJING_MAX_SUPERVISOR_REPLANS=
SHIJIAJING_AGENT_TASK_TIMEOUT_SECONDS=
```

持久化分层：

- Request Ledger：用户请求级全局幂等。
- Supervisor checkpoint：计划、任务状态、结果摘要、HITL 和预算。
- Agent checkpoint：单个 task 的私有执行状态。
- Event Store：计划、派发、handoff、replan 和 Agent 生命周期。
- Memory mutation ledger：写入副作用幂等。

Agent checkpoint namespace 使用稳定层级：

```text
session_id / turn_id / plan_id / task_id
```

恢复流程：

1. 加载 Supervisor checkpoint。
2. 找出 `DISPATCHED/RUNNING` 但没有终态结果的任务。
3. 查询对应 Agent checkpoint。
4. 已完成任务只重放 `AgentResult`，不重复调用外部服务。
5. 未完成的幂等任务从最近成功节点继续。
6. 状态不明的写任务通过 ledger 或人工仲裁确认。
7. HITL resume 回到原 task/plan，不重新执行整个 turn。

## 13. 可观测性

建议新增事件语义：

```text
plan_created
plan_revised
task_created
task_dispatched
task_started
task_completed
task_failed
handoff_requested
handoff_accepted
handoff_rejected
budget_exhausted
```

事件必须携带稳定的 `plan_id`、`task_id`、`agent_name`、输入/输出 hash、attempt、状态、耗时、
token、fallback 和错误码，不携带思维链或原始内容。

核心指标：

- 各 Agent 成功、失败、fallback 和 retry 次数
- Agent task p50/p95/p99
- 每轮任务数和 replan 次数
- 并行执行节省时间
- handoff 请求与接受率
- `AgentResult` 契约拒绝次数
- replay 重复副作用次数
- Planner fallback 次数
- Multi-Agent 与旧 Workflow 业务结果差异

## 14. 测试与评测

### 14.1 契约测试

- 每种 `AgentTaskInput` 与 `AgentTaskOutput` 的合法/非法载荷。
- `agent_name`、`task_kind` 与 output 类型不匹配时拒绝。
- 未授权字段、未知字段和错误 discriminator 拒绝。
- 相同 task 重放的 hash 一致性和冲突检测。
- Handoff allowlist 和任务依赖校验。

### 14.2 单元测试

- 确定性 Planner。
- `PlanValidator` 的无环、依赖、权限和预算校验。
- ready task 选择和动态派发。
- `merge_task_results` 幂等与冲突。
- Supervisor 来源优先级与规范状态归并。
- 各 Agent capability enforcement。

### 14.3 Workflow 测试

- Recognition、Intent、Memory recall 三路并行与动态 Barrier。
- 无图片时跳过 Recognition。
- 缺品类时中止后续任务并进入 clarification。
- Retrieval handoff、条件放宽和重新派发。
- Explanation 失败只执行模板降级。
- Memory confirmation 后执行唯一 commit。
- Agent task 中断后跨 runtime 恢复。
- 重复 resume、重复 result 和 request replay 不产生重复副作用。

### 14.4 对照评测

- 使用现有 seed/frozen 格式对比旧 Workflow 与 Multi-Agent 的最终 `AgentResponse`。
- 硬过滤、同款、SKU、排序和事实一致性不变量必须保持。
- 单独统计 Planner、handoff、replan 和 task recovery 指标。
- shadow 模式不得提交 Memory 副作用。
- 正式数据、性能和生产外部证据门禁通过前，不切换默认模式。

## 15. 实施阶段

截至 2026-08-23 的实际状态如下。状态只在对应代码和测试已经落地后更新，未把接口占位或
测试替身当作阶段完成：

| 阶段 | 状态 | 已落地范围 | 未完成入口 |
|---|---|---|---|
| 阶段 1：协议与兼容层 | 已完成 | 2.0 任务/结果、严格 discriminator、计划 DAG、SupervisorState、幂等 reducer；1.x 契约未删除；native Supervisor checkpoint 适配 | — |
| 阶段 2：固定计划 Multi-Agent | 执行中 | registry、五个 Agent wrapper、固定任务 DAG、Facade 模式入口 | 新旧路径逐案例对照与持久化事件投影 |
| 阶段 3：私有状态 | 已完成 | 五类私有 invocation state；Retrieval wrapper 持有同款/SKU/排序算法；Supervisor/Agent task native namespace 实际读写与恢复 | — |
| 阶段 4：动态 Planner 与 handoff | 执行中 | 确定性 Planner、PlanValidator、ready-task barrier、受控 skip、handoff 输入授权门禁、SupervisorPlannerPort deterministic adapter | LangGraph Send/Command 实际接入、模型 Planner fallback/replan |
| 阶段 5：恢复、HITL 与副作用 | 未开始 | 复用旧 workflow 的 HITL/ledger 基础设施 | 双层 native 恢复、memory confirmation 与唯一 commit 的端到端路径 |
| 阶段 6：灰度发布 | 执行中 | 三种配置模式，默认 workflow；shadow 禁止 Memory commit | 新旧结果正式对照、发布门禁和外部证据 |

### 阶段 1：协议与兼容层

- 新增 `AgentTaskV2`、`AgentResultV2`、`ExecutionPlan` 和严格输入输出联合类型。
- 新增 `SupervisorState` 与 `merge_task_results`。
- 保留现有 `AgentTask`、`AgentResult` 和 1.1 checkpoint 读取。
- 当前业务执行路径不变。

### 阶段 2：固定计划 Multi-Agent

- 通过 Agent registry 包装五个现有子图。
- Supervisor 创建固定任务 DAG。
- 调用路径改为 `AgentTaskV2 → AgentResultV2`。
- 与当前 Workflow 逐案例对照业务结果。

### 阶段 3：私有状态

- 五个 Agent 改用独立 input/output/private state。
- 禁止 Agent 接收完整 `AgentState`。
- 将同款、SKU 和排序的调用所有权归入 Retrieval Agent。
- 接入 Agent task checkpoint namespace。

### 阶段 4：动态 Planner 与 handoff

- 增加确定性 Planner、可选 Supervisor Model 和 `PlanValidator`。
- 使用 `Send` 动态并发派发。
- 增加 handoff、replan、预算和 capability 校验。

### 阶段 5：恢复、HITL 与副作用

- 完成 Supervisor/Agent 双层恢复。
- 覆盖 clarification、recognition review、same-item review、memory confirmation。
- 接入 Memory commit 授权和 mutation ledger 仲裁。
- 验证重复 resume 不产生重复副作用。

### 阶段 6：灰度发布

- `workflow`：只运行旧图。
- `multi_agent_shadow`：新图进行对照，不提交 Memory 副作用。
- `multi_agent`：新图作为主路径。
- 正式评测、配置的性能阈值和生产外部证据门禁通过后，才允许修改默认模式。

## 16. Definition of Done

只有全部满足以下条件，项目才正式声明为 Multi-Agent：

1. 每个专业 Agent 使用独立输入、输出和私有状态。
2. Supervisor 通过 `AgentTaskV2` 动态派发，不直接调用专业业务节点。
3. Agent 只通过 `AgentResultV2` 和 `HandoffRequest` 通信。
4. 支持动态跳过、并行、失败重派和受控 replan。
5. Agent 不能直接修改 Supervisor 规范状态。
6. 工具和数据权限按 Agent 隔离并有拒绝测试。
7. Supervisor 与 Agent task 均支持 native checkpoint 恢复。
8. replay、retry 和 resume 不重复执行 Memory 等副作用。
9. HITL resume 继续原 plan/task，不重新运行整个 turn。
10. Multi-Agent 与旧 Workflow 在冻结业务用例上保持确定性业务不变量。
11. 所有任务输入和输出通过 Pydantic 契约校验。
12. 正式评测、性能和生产外部依赖门禁通过后才切换默认模式。

## 17. 明确非目标

- 不实现多个 Agent 的自由文本群聊。
- 不允许 Specialist Agent 直接相互调用。
- 不让 LLM 决定价格、硬过滤、同款、SKU 或 Memory 写入。
- 不在本阶段拆分为多个网络服务或独立部署单元。
- 不用 Multi-Agent 名称替代正式数据、性能和生产基础设施验收。
