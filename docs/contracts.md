# 数据契约

跨模块数据统一定义在 `contracts.py`，Pydantic 模型默认使用 `extra="forbid"`，未知字段不能
跨越 Supervisor、Specialist Agent 或持久化边界。

## 1. 请求与响应

- `AgentRequest`：文本、图片、识别修正三类输入至少提供一种，并携带稳定的
  `session_id`、`request_id`。
- `AgentResponse`：返回状态、识别结果、有效约束、SKU 比价组、澄清信息和 notices。
- `AgentExecutionContext`：携带可信的 Memory owner、功能开关和执行上下文。
- `AgentInterrupt` / `AgentResume`：按中断类型使用独立 payload，禁止自由字典恢复。

## 2. 任务协议

- `ExecutionPlan`：计划 ID、任务列表、全局预算和最大重规划次数。
- `AgentTaskV2`：任务类型、目标 Agent、依赖、幂等键、截止时间、预算和类型化输入。
- `AgentResultV2`：任务状态、类型化输出、固定错误、用量、证据引用和输出哈希。
- `TaskRecord`：Supervisor 保存的任务生命周期，不由 Specialist Agent 修改。

任务类型与 Agent 的映射是固定 allowlist。例如 `retrieval.retrieve_and_rank` 必须由
Retrieval Agent 执行，并返回 `RetrievalTaskOutput`；类型不匹配直接拒绝。

## 3. 领域契约

- `RecognitionResult`：品类、品牌、型号、属性及逐字段置信度。
- `IntentPatch` / `ShoppingConstraints`：意图增量与带来源的规范约束。
- `RetrievalQuery` / `RetrievalCandidate`：召回输入与候选证据。
- `NormalizedCandidate` / `SkuGroup` / `RankedGroup`：归一化、同款聚类、SKU 拆分与排序结果。
- `MemoryQuery` / `MemoryMutation`：白名单化记忆查询和显式变更。

用户明确约束始终进入硬过滤；识别得到的低置信属性只能作为软信号，不能覆盖用户输入。
价格、销量、评分和解释数字必须来自结构化候选或证据对象。

## 4. 状态与幂等

`SupervisorState` 只保存计划、任务记录、任务结果、规范理解、预算、活动中断和审计事件。
`merge_task_results` 使用 `task_id + output_hash` 保证重放幂等：相同哈希重复写入不改变状态，
不同哈希则抛出 `TaskResultConflictError`。

Request Ledger 使用 `(session_id, request_id)` 保存最终响应；同一键不能被不同响应静默覆盖。

## 5. 持久化安全

- Checkpoint 写入前移除请求全文、图片 data URL 和自由 metadata。
- 只允许 serializer 白名单中的契约类型反序列化。
- 事件和 trace 只保存 ID、哈希、版本、计数、状态、错误码和降级标记。
- 模型原始响应、Prompt、密钥和隐藏推理过程不得进入 Checkpoint、Event Store 或日志。

## 6. 固定错误语义

对外错误使用 `ErrorCode` 和固定可操作消息。模型或外部服务异常可以触发明确的
`FALLBACK`，但不能把降级结果标记为原服务成功；任务级不可恢复错误使用 `FAILED`。

## 7. Main Agent runtime 契约

新路径不扩展旧 `AgentTaskV2`，而是在 `agent_runtime/contracts.py` 使用独立的严格判别联合：

| 契约 | 运行时责任 |
|---|---|
| `DecisionObservation` / `MainAction` | 主 Agent 每轮只提出一个有限动作；不能传入授权令牌、函数名、任意 URL 或新硬条件 |
| `ActionRecord` / `ToolObservation` | 记录动作 fingerprint、约束/证据版本、状态、结果引用和实际用量 |
| `SubagentTask` / `SubagentObservation` | 冻结约束、有限 evidence allowlist、允许工具、局部截止时间和父预算投影 |
| `SubagentResult` | 只能引用运行时登记的 candidate/evidence；`facts` 必须逐字段绑定 evidence |
| `EvidenceRecord` / `EvidenceQualityReport` | 绑定 offer、来源、数据版本和可在答案中出现的事实 |
| `RuntimeSessionSnapshot` / `MainRuntimeState` | 分离跨轮会话摘要与单轮可恢复状态 |

所有模型契约 `extra="forbid"`，serializer 只允许显式 allowlist 类型。主 Agent 的 `answer` 仍须
经过证据质量检查；Verification 的 `comparable/not_comparable/insufficient_evidence` 建议由
确定性比较服务重新计算，模型不能覆盖型号、容量、币种或优惠适用条件等硬冲突。

### 7.1 版本与引用规则

- 用户更新约束时 `constraints_version` 递增；旧 subagent 结果不能直接归并。
- `evidence_id` 由受控商品字段和来源内容哈希生成；未知 ID、跨请求 ID 或伪造 facts 均拒绝。
- `agent-runtime-v1/{session}/{request}/main` 保存主状态，会话摘要在
  `agent-runtime-v1/{session}/session`；子任务命名空间约定为
  `agent-runtime-v1/{session}/{request}/subagents/{task_id}`。
- subagent 没有长期 Memory commit 权限；HITL / Memory 授权由 runtime 绑定实际 mutation 集合。
