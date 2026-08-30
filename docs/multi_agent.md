# 受控 Multi-Agent 执行

生产入口只有 `AgentFacade → MultiAgentSupervisor` 一条路径。系统通过严格任务契约和
确定性门禁控制模型参与范围。

## 1. 核心组件

- `AgentTaskV2` / `AgentResultV2`：任务和结果的类型化协议，禁止额外字段。
- `DeterministicPlanner`：根据请求生成带依赖、预算、截止时间和幂等键的任务 DAG。
- `GuardedSupervisorPlanner`：接收可选模型建议；建议必须物化并通过 `PlanValidator`。
- `SpecialistAgentRegistry`：Recognition、Intent、Retrieval、Explanation、Memory 的唯一派发入口。
- `MultiAgentSupervisor`：执行 barrier、汇合结果、控制 replan、HITL 和 Memory 副作用。
- `LangGraphMultiAgentCheckpoint`：分别持久化 Supervisor 状态与单任务结果。

## 2. 任务边界

每个 Specialist Agent 只接收 `AgentTaskV2.input` 中与当前任务有关的数据，并返回
`AgentResultV2`。它不能取得或修改完整 `SupervisorState`。

例如 Retrieval Agent 接收规范约束、识别结果和查询文本，在私有调用内完成召回、商品归一化、
同款匹配、SKU 拆分和排序，最后一次性返回 `RetrievalTaskOutput`。Supervisor 校验结果后才写入
规范理解和后续任务输入。

## 3. 调度与重规划

1. Planner 生成 `ExecutionPlan`。
2. Supervisor 找出依赖均已终止的 ready tasks。
3. Dispatcher 使用 LangGraph `Send` 并行执行同一 barrier 的任务。
4. Supervisor 按 `task_id + output_hash` 幂等归并结果。
5. 可恢复失败可以生成新的 retry task；原任务结果不会被覆盖。
6. 所有终态结果汇合后构造响应，或在需要人工确认时保存中断。

模型 Planner 的 `shadow` 模式只评估候选计划，实际执行仍使用确定性基线；`active` 和
`active_replan` 模式下，候选计划同样必须通过动作 allowlist、确定性物化与计划校验。

## 4. 确定性保护

以下规则不交给 LLM 决策：

- 用户硬约束过滤；
- 同款硬冲突与 complete-link 聚类；
- SKU 变体拆分；
- 券后价格聚合与排序；
- 解释数字的证据一致性检查；
- Memory commit 授权与幂等校验。

## 5. 恢复与可观测性

- Supervisor、活动中断和每个任务结果使用稳定 namespace。
- Checkpoint 重放先恢复已完成任务，避免重复模型或外部服务调用。
- Trace 记录 Agent、Planner、任务状态、延迟、哈希、错误码和降级标记。
- Trace、Checkpoint 和事件记录不保存用户全文、图片内容、Prompt 或模型原始响应。
