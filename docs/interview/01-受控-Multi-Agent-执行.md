# 受控 Multi-Agent 执行

## 讲解主线

1. **旧流程与问题。** 先说明早期是单 Agent 内的固定执行链，识别、意图、检索、解释等节点围绕
   同一份 `AgentState` 读写；再讲任务依赖固化、状态边界不清晰和任务级恢复困难三个问题。
2. **Supervisor 与类型化任务 DAG（重点）。** 说明 Supervisor 负责计划校验、就绪任务选择、派发、
   结果汇合、Checkpoint 和重规划；Planner 将一次请求转换成包含 Agent、任务类型、`depends_on`、
   预算、幂等键和类型化输入的 `ExecutionPlan`。
3. **五类专业 Agent。** 简要介绍 Recognition、Intent、Retrieval、Explanation 和 Memory；说明这样
   拆分是为了按能力、外部依赖、状态边界和副作用边界划分职责，而不是为了增加 Agent 数量。
4. **仅接收任务私有输入。** Agent 的执行入口接收 `AgentTaskV2`，但业务数据只读取对应的类型化
   `task.input`，不会获得完整 `SupervisorState`，也不能任意读写其他 Agent 的状态。
5. **依赖执行与编排选择（重点）。** Planner 用 `depends_on` 声明依赖；Supervisor 每轮只派发所有
   前置任务均已有终态结果的任务，同层任务并行执行。当前采用确定性规则建图，因为任务空间有限、
   依赖明确，并且恢复和副作用控制要求计划稳定；LLM Planner 只作为受限扩展能力保留。
6. **保存任务结果。** 每个 Agent 返回独立的 `AgentResultV2`，Supervisor 按 `task_id` 合并到
   `task_results`，启用持久化时再写入任务级 Checkpoint。
7. **恢复后已完成任务不重跑。** 恢复时先加载 Supervisor 和任务级 Checkpoint；调度时排除
   `task_id` 已经存在于 `task_results` 的任务，只继续执行尚未完成的部分。
8. **可重试故障与受控重规划。** 是否可重试由 `AgentTaskError.retryable` 显式标记；当前主要是
   Retrieval 执行失败或未捕获的 Agent 执行异常。Supervisor 在任务粒度创建带新 ID、attempt 和
   幂等键的重试任务，用 `ExecutionPlanPatch` 替换失败任务并重连下游依赖，而不是重跑整个请求。
9. **过渡到长期记忆。** 最后只说明重复恢复不会重复执行 Memory Commit，Adapter 还会通过稳定
   `mutation_id` 再做一层写入幂等；具体的长期记忆分层、授权和写入机制放到 `04` 展开。

## 必要建议

- 这 9 点适合作为准备清单，实际讲解时建议收敛成“旧架构问题 → 新架构与编排 → 结果保存与恢复
  → 记忆过渡”四段，否则容易像逐条解释简历关键词。
- 第 2 点和第 5 点应连在一起讲：先生成类型化 DAG，再由 Supervisor 根据 `depends_on` 分层派发，
  避免重复解释两次调度过程。
- 全程使用一个例子串联，例如“图片识别耳机并比价”：Recognition 与 Intent 并行，Retrieval 等待
  二者结果，Explanation 等待 Retrieval；这样 DAG、私有输入和依赖执行都能落到同一条链路上。
- 当前的“受控重规划”默认是确定性 retry Patch，不要讲成 LLM 在运行时自由重新设计计划。
- 当前可重试错误分类还比较粗：Retrieval 内部异常和 Dispatcher 捕获的未处理异常都会标记为可重试。
  面试时可以把网络抖动、临时服务不可用作为典型例子，但不要声称已经完成精细的异常分类体系。
- 第 9 点应说“重复恢复不会**重复**写入长期记忆”，不能说成“不会写入长期记忆”。
- 旧的单 Agent 固定链路已经不在当前主执行入口中；面试前需要准备对应的旧版提交或架构图，避免
  面试官追问旧拓扑代码时只能口头描述。
- 简历中的“故障注入测试”更准确的口径是“故障与恢复测试”：可重试 Retrieval 是直接故障注入，
  已完成任务复用和 Memory 幂等属于 Checkpoint 恢复测试。

## 问：为什么 Planner 选择规则，而不是 LLM？

> 当前我使用的是确定性规则 Planner。因为系统现阶段只有 Recognition、Intent、Retrieval、
> Explanation 和 Memory 五类 Agent，任务组合主要由是否有图片、是否启用记忆等明确条件决定，
> 用规则就能准确生成 DAG。
>
> 规则方案的优势是延迟低、没有额外模型成本，而且计划稳定、可验证、可复现，这对任务级恢复、
> 幂等重试和长期记忆写入非常重要。当前即使引入 LLM，它也只能从 `keep`、`skip`、`retry` 和
> `add_template` 等白名单动作中选择，实际可优化的空间有限，因此还不足以覆盖额外复杂度。
>
> 不过我保留了受控 LLM Planner 接口。后续如果 Agent、工具和执行策略明显增多，我会先用
> Shadow 模式评测模型规划效果，再考虑只开放故障重规划，而不是直接把执行控制权交给模型。

## 追问：规则 Planner 是不是固定拓扑？

> 不是。固定的是建图规则，不是每次生成的拓扑。Planner 会根据请求动态组合任务。

```text
纯文本：Intent → Retrieval → Explanation

图片：Recognition ─┐
                   ├→ Retrieval → Explanation
       Intent ─────┘

启用记忆：Intent / Recognition → Memory Recall → Retrieval → Explanation
```

## 追问：LLM Planner 当前能做什么？

> 它不能任意创建 Agent、任务或修改任务输入，只能从 Supervisor 提供的动作目录中提出结构化
> 调整。提议还必须经过 `PlanMaterializer` 和 `PlanValidator`，不合法或调用失败就回退到规则计划。

## 追问：保存任务结果是什么意思？

> 它不是只保存最终回答，也不是写入长期记忆。每个 Specialist Agent 完成任务后都会返回独立的
> `AgentResultV2`，其中包含任务状态、类型化输出、错误、证据引用、资源用量和结果哈希。Supervisor
> 以 `task_id` 为键把结果合并到 `task_results`；启用持久化时，还会写入该任务独立的 Checkpoint。
> 这样既能用前置任务结果解锁下游任务，也能在故障恢复时识别已经完成的任务，直接从断点继续。

例如，Intent 已经完成，而 Retrieval 执行时服务中断。恢复后 Supervisor 会先加载 Intent 的任务
结果，因此不会重新调用 Intent Agent，而是从 Retrieval 继续执行。相同结果重复恢复时通过
`output_hash` 保持幂等，不同结果则拒绝静默覆盖。

## 追问：如何证明故障恢复和重规划有效？

> 我使用 Fake Agent 和可控 Registry 做故障与恢复测试。对于已完成任务，测试会记录中断前的 Agent
> 调用次数，使用同一个 Checkpoint 恢复后断言调用次数没有增加，证明结果被复用。对于可重试故障，
> `FailOnceRegistry` 会让 Retrieval 第一次返回 `retryable=True` 的失败，测试最终断言 Retrieval
> 执行两次、`replan_count` 增加一次，并生成带 `:retry:2` 的替代任务。

## 追问：Checkpoint 持久化在哪里启动？

> 系统没有单独的持久化开关，`SHIJIAJING_CHECKPOINT_DSN` 是否为空就是启动条件。
> `open_agent_runtime()` 检测到 DSN 后调用 `open_graph_checkpointer()`，根据配置初始化 SQLite 或
> PostgreSQL Saver，再由 `AgentFacade` 包装成 `LangGraphMultiAgentCheckpoint` 并注入 Supervisor。
> 测试中不连接数据库，而是直接注入 `InMemoryMultiAgentCheckpoint`。

## 代码位置

- 规则建图：`src/shijiajing_agent/multi_agent/planner.py` 中的 `DeterministicPlanner.create_plan()`
- 计划校验：同文件中的 `PlanValidator`
- LLM 动作白名单：`src/shijiajing_agent/multi_agent/planner_catalog.py` 中的 `build_action_catalog()`
- LLM 提议物化：`src/shijiajing_agent/multi_agent/planner_materializer.py` 中的 `PlanMaterializer`
- 重规划触发：`src/shijiajing_agent/multi_agent/supervisor.py` 中的 `_maybe_replan()`
- 任务结果协议：`src/shijiajing_agent/contracts.py` 中的 `AgentResultV2`
- 结果归并与幂等校验：`src/shijiajing_agent/state.py` 中的 `merge_task_results()`
- 任务级结果保存：`src/shijiajing_agent/multi_agent/supervisor.py` 中的 `_save_task_checkpoint()`
- Checkpoint 实现：`src/shijiajing_agent/multi_agent/checkpoint.py`
- 持久化启动：`src/shijiajing_agent/runtime.py` 中的 `open_agent_runtime()` 和 `_build_agent_facade()`
- SQLite/PostgreSQL Checkpointer：`src/shijiajing_agent/adapters/langgraph_persistence.py`
- 故障与恢复测试：`tests/multi_agent/test_supervisor.py`
