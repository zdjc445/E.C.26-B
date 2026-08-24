# 模型 Supervisor Planner 实施方案

- 文档状态：待实现
- 基线日期：2026-08-24
- 适用范围：`shijiajing-agent` 受控 Multi-Agent 编排核心
- 关联文档：[受控层级式 Multi-Agent 升级方案](multi_agent_upgrade_plan.md)

## 1. 当前事实与目标

当前仓库已经具备：

- `SupervisorPlannerPort`、`SupervisorPlanningInput`、`SupervisorReplanningInput`；
- `DeterministicPlanner`、`DeterministicSupervisorPlanner`、`PlanValidator`；
- `GuardedSupervisorPlanner` 的 candidate 注入与异常回退骨架；
- `SHIJIAJING_SUPERVISOR_MODEL` 配置字段。

当前尚未具备：

- 真实模型 Planner 适配器和 Supervisor Prompt；
- `SHIJIAJING_SUPERVISOR_MODEL` 到生产 runtime 的装配；
- 模型输出到 `ExecutionPlan` / `ExecutionPlanPatch` 的安全物化；
- 合法模型计划被接受、非法模型 patch 被回退的完整测试；
- `planner_fallback`、`plan_created`、`plan_revised` 等 trace、指标和审计事件；
- 模型 Planner 的 shadow、正式评测和生产外部证据。

本方案的目标是实现一个**可选、受控、可回退、可恢复和可审计**的模型 Planner。模型只提出
结构化动作，不能直接执行工具、修改业务结果、构造任意任务载荷或批准 Memory 副作用。

## 2. 核心决策

### 2.1 模型不直接生成可执行任务

模型不得直接生成完整 `AgentTaskV2`、`ExecutionPlan` 或任意工具调用。推荐链路为：

```text
DeterministicPlanner 生成基础计划
        ↓
Supervisor 生成 AllowedActionCatalog
        ↓
Ark Supervisor Model 输出 PlannerProposal
        ↓ Pydantic 严格校验
PlanMaterializer 将允许动作物化为计划或 patch
        ↓ PlanValidator
通过：使用模型建议形成的计划
失败：回退确定性计划并记录类型化原因
```

模型不能控制以下字段：

- `task_id`、`plan_id`、`idempotency_key`；
- deadline、重试次数、token 和任务预算；
- Memory owner、Memory commit authorization；
- 工具名称、模型名称、检索索引和 capability；
- 用户锁定的硬过滤、候选、价格、排序和最终响应。

### 2.2 确定性 Planner 始终是安全基线

每轮先生成合法基础计划。模型不可用、超时、输出非法、动作越权或计划校验失败时，必须使用
基础计划或确定性 retry patch。回退不能静默发生。

### 2.3 首期优先 replan，不强制每轮调用模型

正常输入的基础 DAG 已经明确。首期推荐将模型用于可恢复失败、多个 fallback 候选或 handoff
建议的受控选择，避免每轮请求都增加一次模型延迟和成本。完整初始计划优化在 shadow 数据证明
有收益后再启用。

## 3. 模式与配置

新增配置：

```text
SHIJIAJING_SUPERVISOR_PLANNER_MODE=off|shadow|active_replan|active
SHIJIAJING_SUPERVISOR_MODEL=
SHIJIAJING_SUPERVISOR_PLANNER_TIMEOUT_SECONDS=8
SHIJIAJING_SUPERVISOR_PLANNER_MAX_REPAIRS=1
SHIJIAJING_SUPERVISOR_PLANNER_MAX_TOKENS=1500
```

语义：

| 模式 | create plan | replan | 实际执行 |
|---|---|---|---|
| `off` | 不调用模型 | 不调用模型 | 确定性计划 |
| `shadow` | 调用并校验 | 调用并校验 | 始终执行确定性结果 |
| `active_replan` | 确定性 | 模型可参与 | 仅执行通过校验的模型 patch |
| `active` | 模型可参与 | 模型可参与 | 执行通过校验的模型计划/patch |

约束：

- `SHIJIAJING_SUPERVISOR_MODEL` 为空时必须等价于 `off`；
- 不得静默复用 `SHIJIAJING_ARK_TEXT_MODEL`；
- 模型名由部署显式配置，不在代码中硬编码；
- 使用 Ark OpenAI 兼容协议和现有 `ArkModelClient`；
- 温度固定为 0（上游协议支持时）；
- 网络重试沿用 Ark 客户端策略，结构修复最多一次。

## 4. Planner 输入最小化

模型不接收完整 `AgentState`、原始图片、候选全集、Memory 内容或模型原始输出。Planner 输入只包含：

- 请求形态：`has_text`、`has_image`、`has_correction`、`has_selected_option`；
- taxonomy 版本和规范约束摘要；
- Memory/HITL/检索等部署能力开关；
- 基础计划中的任务 ID、任务类型、Agent、依赖和终态摘要；
- 失败任务 ID、固定错误码、`retryable`、fallback 类型；
- 剩余任务数、replan 次数、wall-clock 和 token 预算；
- 本轮 `AllowedActionCatalog`。

Planner 调用期间可以在内存中使用经过长度限制的用户文本，但不得将用户全文、Prompt 或模型原始
响应写入 checkpoint、Event Store 或 trace。若任务选择不需要语义内容，应只传输入形态和约束摘要。

## 5. 提议契约

建议新增 `multi_agent/planner_contracts.py`，定义模型专用协议。模型协议与可执行任务协议分离。

```python
class PlannerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action: Literal["keep", "skip", "retry", "add_template"]
    target_task_id: str | None = None
    template_id: str | None = None
    reason_code: str


class PlannerProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    base_plan_id: str
    actions: list[PlannerAction]
```

`action_id` 和 `template_id` 必须来自 Supervisor 生成的目录，例如：

```text
keep:intent-1
skip:memory-recall-1
retry:retrieval-1
add:template-explanation-fallback
add:template-retrieval-recognition-relaxation
```

模型不能在目录之外创造 action、task kind、Agent 或输入载荷。

## 6. AllowedActionCatalog 与 Materializer

新增 `multi_agent/planner_catalog.py` 和 `multi_agent/planner_materializer.py`。

`AllowedActionCatalog` 由确定性规则产生，每个动作携带：

- 稳定 `action_id`；
- 目标 task 或模板；
- 所需 capability 和依赖；
- 是否允许 skip/retry；
- 最大 attempt 和预算；
- Supervisor 可安全构造输入所需的授权引用；
- 禁止原因（如有）。

`PlanMaterializer` 负责：

1. 校验模型选择的 action 全部存在；
2. 拒绝重复、互斥或超过预算的动作；
3. 从基础计划和授权引用构造完整 `AgentTaskV2`；
4. 由系统生成 ID、deadline、幂等键和 authorization；
5. 应用 skip/retry/add/replace；
6. 将结果交给 `PlanValidator`；
7. 输出 `ExecutionPlan` 或 `ExecutionPlanPatch`。

## 7. create plan 流程

`create_plan()` 的实现顺序：

1. `DeterministicPlanner.create_plan()` 生成基础计划；
2. 根据请求形态、执行上下文和预算生成 create action catalog；
3. `ArkSupervisorPlanner` 使用 `supervisor_create_plan.md` 请求 `PlannerProposal`；
4. Pydantic 拒绝缺字段、额外字段、错误类型和未知 action；
5. Materializer 将提议应用到基础计划；
6. `PlanValidator` 验证 allowlist、依赖、无环、预算和副作用授权；
7. `active` 使用通过的计划；`shadow` 只保存比较摘要；
8. 任一环节失败时返回基础计划和类型化 fallback 元数据。

## 8. revise plan 流程

`revise_plan()` 的输入应补充：

- 剩余预算；
- 允许重试的任务和 attempt；
- 允许的 fallback/handoff 模板；
- 当前规范约束摘要；
- Supervisor 授权的输入引用。

执行顺序：

1. 确定性规则先生成合法 retry/fallback 候选；
2. 模型只能从候选目录选择；
3. Materializer 生成 `ExecutionPlanPatch`；
4. `apply_plan_patch()` 应用后重新执行完整 `PlanValidator`；
5. 非法 patch 回退 `DeterministicSupervisorPlanner.revise_plan()`；
6. Memory commit 结果未知时不得由模型建议盲目重试。

## 9. 现有代码前置修正

模型接入前必须完成：

1. `apply_plan_patch()` 实际处理 `skip_task_ids`；
2. 跳过仍被依赖的任务时拒绝计划，或同时使用合法 replacement；
3. 明确 `retry_task_ids`、`add_tasks` 和 `replace_task_ids` 的一致语义；
4. `PlanValidator` 将 `KeyError` 等内部异常统一转换成 `PlanValidationError`；
5. `GuardedSupervisorPlanner` 不再使用 `except Exception: pass` 静默吞错；
6. Supervisor 主循环处理或明确拒绝 `handoff_requests`；
7. 恢复时优先读取已保存 Planner outcome，不重复调用模型。

## 10. 模型适配器与 Prompt

新增：

```text
src/shijiajing_agent/adapters/ark_supervisor_planner.py
src/shijiajing_agent/prompts/supervisor_create_plan.md
src/shijiajing_agent/prompts/supervisor_revise_plan.md
```

`ArkSupervisorPlanner` 实现 `SupervisorPlannerPort`，内部职责为：

- 构造脱敏、最小化的模型输入；
- 调用 `ArkModelClient.structured_call()`；
- 使用 `PlannerProposal` Schema；
- 在结构修复时只反馈精简字段错误和允许动作；
- 调用 Materializer 返回可执行计划或 patch；
- 记录模型、Prompt 版本、token、耗时、repair 和输出 hash；
- 不记录模型原始响应。

Prompt 必须明确：

- 只能选择目录中的 action；
- 不输出工具调用、自然语言计划或思维过程；
- 不修改硬过滤、价格、候选、排序和 Memory authorization；
- 信息不足时保持基础计划；
- 输出必须严格符合 JSON Schema。

## 11. 类型化 Outcome 与回退

建议让保护门面返回带审计元数据的 outcome，而不是只返回计划：

```python
class PlanningOutcome(BaseModel):
    plan: ExecutionPlan
    source: Literal["model", "deterministic"]
    model_attempted: bool
    fallback_reason: str | None
    model: str | None
    prompt_version: str | None
    repair_count: int
    duration_ms: float
    proposal_hash: str | None
    plan_hash: str
```

回退原因至少包含：

```text
MODEL_DISABLED
MODEL_TIMEOUT
MODEL_NETWORK_ERROR
MODEL_OUTPUT_INVALID
ACTION_NOT_ALLOWED
PLAN_MATERIALIZATION_FAILED
PLAN_VALIDATION_FAILED
BUDGET_EXCEEDED
MODEL_PLAN_SHADOWED
```

若保持现有 `SupervisorPlannerPort` 返回类型不变，则必须通过独立 `PlannerAuditSink` 输出等价元数据，
不得继续静默回退。

## 12. Runtime 装配

生产装配流程：

1. `load_settings()` 读取 Planner mode、model、timeout 和 repair；
2. mode 非 `off` 且配置完整时构造 `ArkSupervisorPlanner`；
3. 将实例写入 `AgentDependencies.supervisor_planner`；
4. `MultiAgentSupervisor` 使用 `GuardedSupervisorPlanner` 包装；
5. `workflow` 模式不创建或调用模型 Planner；
6. Planner 资源与其他 Ark 模型适配器共享客户端生命周期，但保留独立 Prompt 和调用记录。

配置缺少模型或 Ark 凭据时：

- `off` 模式允许启动；
- `shadow`、`active_replan`、`active` 必须启动失败并列出精确缺失项；
- 不允许配置为 active 后静默退回永久 off。

## 13. Checkpoint、幂等与恢复

Supervisor checkpoint 增加：

- Planner mode、source、model 和 Prompt version；
- proposal hash、plan hash、fallback reason；
- create/replan attempt 和预算使用；
- shadow 比较摘要；
- 已接受的 `ExecutionPlan` / `ExecutionPlanPatch`。

恢复规则：

1. 已存在终态 PlanningOutcome 时不再次调用模型；
2. 模型请求结果未知但 outcome 未保存时，重新调用只能生成新 attempt ID；
3. 已接受计划必须通过 hash 校验后恢复；
4. 相同 plan/replan attempt 出现不同 hash 时拒绝覆盖；
5. HITL resume 延续原 plan/task，不重新规划整个 turn；
6. Memory 副作用仍以 mutation ledger 为事实源。

## 14. 可观测性

新增事件：

```text
planner_call_started
planner_proposal_received
planner_plan_accepted
planner_plan_rejected
planner_fallback
plan_created
plan_revised
```

事件和 span 只记录：

- model、Prompt version、Planner mode；
- proposal/plan hash；
- source、accepted、fallback/error code；
- latency、token、repair、action/task 数量；
- create/replan attempt。

不得记录用户全文、Prompt、原始图片、Memory 内容、模型原始响应或思维链。

新增指标：

```text
planner_call_total
planner_model_plan_accepted_total
planner_fallback_total{reason}
planner_validation_rejected_total{reason}
planner_latency_ms
planner_repair_total
planner_plan_task_count
planner_replan_total
```

## 15. 测试计划

### 15.1 契约与单元测试

- 合法模型 proposal 通过并被采用；
- 缺字段、额外字段、错误 action 和未知 template 拒绝；
- 循环依赖、未知依赖、错误 Agent/task kind、越权 capability 拒绝；
- 超任务数、replan、token 和 wall-clock 预算拒绝；
- 模型修改用户硬过滤或 Memory authorization 时拒绝；
- `skip_task_ids`、retry、add、replace 的真实应用；
- candidate 异常、超时和非法计划回退并记录类型化原因；
- 非法 model patch 回退确定性 retry patch；
- shadow 始终执行确定性计划。

### 15.2 Ark 适配器测试

使用 `httpx.MockTransport` 覆盖：

- 首次合法结构化输出；
- 缺字段后一次 repair 成功；
- 额外字段、错误类型和纯文本输出；
- 持续非法后回退；
- 网络失败、超时、限流和 HTTP 5xx；
- model、Prompt version、token、repair 和 hash 记录；
- trace 和 checkpoint 中不出现原始模型响应。

### 15.3 Workflow 测试

- 合法模型计划实际改变 ready task 派发；
- 非法计划不执行任何越权任务；
- Retrieval 可重试失败触发模型 replan；
- 非法 patch 回退确定性 retry；
- checkpoint replay 不重复调用 Planner；
- HITL resume 复用原 plan；
- `planner_fallback` 可从 Event Store 查询；
- replan/replay 不重复 Memory 副作用；
- `off`、`shadow`、`active_replan`、`active` 四种模式行为符合契约。

### 15.4 Live 与对照评测

真实模型评测必须显式记录：

- 数据来源、版本、样本数和模型版本；
- 合法计划接受率与按原因回退率；
- 相同输入多次执行的一致性；
- Multi-Agent 业务不变量差异；
- Planner 增加的 p50/p95 延迟、token 和成本；
- hard filter、错误 SKU/价格事实和重复副作用违规数。

seed/provisional 数据只能用于工程回归，不得作为正式上线证据。

## 16. 灰度发布

1. **阶段 A：off**  
   完成契约、Materializer、patch 语义、trace 和离线测试。
2. **阶段 B：shadow**  
   调用真实模型并校验，但执行确定性计划；生成逐案例差异报告。
3. **阶段 C：active_replan**  
   只在可重试失败或多个 fallback/handoff 候选时采用模型决定。
4. **阶段 D：active**  
   正式数据、性能、成本和生产外部证据门禁通过后，才允许模型参与初始计划。

任一阶段出现硬约束违规、越权任务或重复副作用，立即切回 `off`，不依赖模型自行修复。

## 17. 实施顺序

### PR 1：契约与确定性安全边界

- PlannerProposal、AllowedActionCatalog、PlanningOutcome；
- 完整 patch 语义和 PlanValidator 错误归一；
- Materializer 与单元测试。

### PR 2：Ark 模型适配器

- create/replan Prompt；
- `ArkSupervisorPlanner`；
- 配置和 runtime 装配；
- MockTransport 契约测试。

### PR 3：审计与恢复

- Planner 事件、指标和 trace；
- Supervisor checkpoint outcome；
- replay/HITL/副作用幂等测试。

### PR 4：shadow 与发布门禁

- 模型计划与确定性计划逐案例比较；
- 延迟、token、fallback 和业务不变量报告；
- release check 接入 Planner 正式证据。

## 18. Definition of Done

只有全部满足以下条件，才可声明模型 Planner 已实现：

1. `SHIJIAJING_SUPERVISOR_MODEL` 能在生产 runtime 中创建真实 Planner；
2. create 和 revise 都有真实 Ark 结构化调用与版本化 Prompt；
3. 模型只选择 allowlist 动作，不能直接构造工具调用和敏感载荷；
4. 合法模型计划通过测试并实际影响派发；
5. 非法计划和 patch 可靠回退，且 trace 中可证明；
6. `planner_fallback` 不再静默；
7. checkpoint replay 不重复调用模型或执行副作用；
8. shadow 报告包含样本、计划差异、延迟、token、fallback 和不变量；
9. 硬过滤、价格事实、SKU 和 Memory 副作用违规数为 0；
10. 正式评测、性能、成本和生产外部证据门禁通过后才启用 `active`。

