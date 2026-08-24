# Multi-Agent 与专业子图

> 当前状态：受控 Multi-Agent 为默认路径；legacy `workflow` 保持原有 Supervisor + 专业子图兼容路径。Multi-Agent
> 已增加 2.0 协议、确定性计划、registry、五类私有 Agent invocation、双层 native
> checkpoint namespace、Send/Command 派发、受控 replan、四类 HITL resume 和三种灰度模式。
> shadow 对照报告与发布门禁已提供；正式外部证据仍需部署环境生成。
> 目标 Multi-Agent 架构和分阶段迁移方案见
> [`docs/plans/multi_agent_upgrade_plan.md`](plans/multi_agent_upgrade_plan.md)。模型 Supervisor
> Planner 当前只有可插拔接口和确定性回退骨架，尚未接入真实模型；实施设计见
> [`docs/plans/model_supervisor_planner_implementation_plan.md`](plans/model_supervisor_planner_implementation_plan.md)。

根图名称固定为 `shijiajing-supervisor`。专业子图提供可独立装配的 LangGraph 入口；根图负责依赖、汇合、HITL、持久化和最终响应，确定性业务算法仍留在 `domain/`。

## 0. 受控 Multi-Agent 实现入口

`shijiajing_agent.multi_agent` 提供新的协议和 Supervisor：

- `AgentTaskV2` / `AgentResultV2` 使用严格 discriminator 和 `extra="forbid"`；旧的
  `AgentTask` / `AgentResult` 保留用于 1.x checkpoint 兼容。
- `DeterministicPlanner` 生成受 allowlist、依赖、无环和预算约束的任务 DAG，Supervisor 只派发
  ready tasks，并在结果边界归并规范约束。
- `SpecialistAgentRegistry` 注册 Recognition、Intent、Retrieval、Explanation、Memory 五个
  Agent。它们只接收对应的 `AgentTaskV2.input` 和私有 state，不接收完整 `AgentState`。
- Retrieval Agent 内部继续调用现有确定性同款、SKU、价格聚合和排序算法；Agent 返回 proposal，
  不直接写 Supervisor 规范状态。
- `multi_agent`（默认）执行受控任务路径；`workflow` 保留旧图兼容路径；
  `multi_agent_shadow` 禁止 Memory commit。三种模式由 `SHIJIAJING_ORCHESTRATION_MODE` 选择。
- 配置了现有 LangGraph native saver 时，`multi_agent` 会把 Supervisor plan、活动 interrupt
  和每个 task result 分别保存到稳定 namespace，并在重放时先恢复已完成 task；未配置时使用纯内存执行。
- `GuardedSupervisorPlanner` 对结构化 Planner 的异常、非法 DAG 和非法 replan patch 统一回退到
  确定性 Planner；可恢复失败只生成新的 retry task，不覆盖原 task 结果。
- `multi_agent_shadow` 会在隔离的只读旧图副本与新 Supervisor 之间比较 status、识别、有效约束、
  候选分组和澄清结果，并在响应 notice 中标记 `shadow_compare:match|mismatch`。

## 1. 子图入口

| 入口 | 节点范围 | 根状态写入边界 |
|---|---|---|
| `build_recognition_subgraph()` | `recognize_image`、`apply_correction`、`normalize_recognition` | recognition、recognition history、recognition id、keywords |
| `build_intent_subgraph()` | `parse_intent` | intent patch、notices、fallbacks |
| `build_retrieval_subgraph()` | rewrite、retrieve、relax、normalize candidates | retrieval query、candidates 与 retrieval 控制字段 |
| `build_explanation_subgraph()` | evidence、explanation | evidence bundle、explanation text、verification |
| `build_memory_subgraph()` | recall、prepare、commit | memory context、pending mutations、notices |

入口和 `RecognitionSubgraphOutput`、`IntentSubgraphOutput`、`RetrievalSubgraphOutput`、
`ExplanationSubgraphOutput`、`MemorySubgraphOutput` 统一导出于 `shijiajing_agent.subgraphs`。
根图在边界处先用对应 Pydantic 输出模型校验，再保留领域对象回写；未知嵌套字段和非法类型
直接拒绝。子图不保存跨 invocation 的私有 thread。

## 2. 根图并行策略

`graph.py` 在 `prepare_subject` 后静态启动 `recognition_start` 和 `intent_start`，并实际装配
`recognition_subgraph` 与 `intent_subgraph`。根图通过边界适配器只接收各子图的授权字段，
不会把子图完整 state 快照回写到并行父图；append-only 的 notices、fallbacks、errors、
node_events 仍按根状态 reducer 合并。Recognition 分支只写识别字段，Intent 分支只写意图字段；
两支分别经过 `recognition_done`、`intent_done`，再由

```python
g.add_edge(["recognition_done", "intent_done"], "join_understanding")
```

进入 `join_understanding`。Memory 通过 `build_memory_subgraph(include_commit=False)` 执行
recall/prepare，确认中断和最终 commit 仍由根图控制；检索和解释分别实际进入
`retrieval_subgraph`、`explanation_subgraph`，再回到根图执行同款、SKU、排序和最终响应。
识别失败沿用文字路径，Intent 失败使用规则降级，不能伪造识别结果。

## 3. 确定性保护

同款硬冲突、complete-link 聚类、SKU 拆分、价格聚合、排序、证据事实检查不得迁入 LLM 子图。Weighted 是默认融合基线；RRF 和确定性 rerank 通过 Settings 显式启用，并由评测报告决定是否发布。

## 4. 可观测性

legacy `run` 和 native `start/resume` 均投影 turn、节点和终态事件。Recognition、Intent、
Retrieval、Explanation、Memory 的首个节点追加 `agent_started`，终止节点追加
`agent_completed`；节点失败时追加 `agent_failed`。这些子 Agent 事件的 `agent_name` 与
supervisor turn 事件分离，`event_id` 使用稳定输入并支持 replay 幂等。OpenTelemetry 只输出
ID、版本、哈希、计数、时长、错误和降级元数据，不输出用户全文、Prompt、图片内容或模型原始输出。
