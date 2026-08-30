# Memory 设计

Memory Agent 管理跨会话、显式授权的用户记忆。它与单轮 `SupervisorState`、会话摘要和模型
上下文相互独立，不能把请求中的自由 metadata 自动当作用户画像。

## 1. 三类上下文

| 类型 | 存储位置 | 生命周期 | 用途 |
|---|---|---|---|
| 单轮执行状态 | `SupervisorState` | 一个 turn，可由 Checkpoint 恢复 | 计划、任务结果、中断和预算 |
| 会话摘要 | `recent_turns` | 当前会话的有界窗口 | 多轮指代和近期约束 |
| 长期记忆 | `MemoryPort` | 跨会话，按 owner 隔离 | 用户明确要求保存的偏好或默认约束 |

`recent_turns` 受条数和序列化字节上限控制，不等同于长期 Memory。

## 2. 读取链路

```text
Intent / Recognition 结果
        ↓
Supervisor 构造当前品类 MemoryQuery
        ↓
Memory Agent recall(memory_owner_id, query)
        ↓
Supervisor 按 scope、apply_mode 和来源合并
```

- `memory_owner_id` 必须来自可信调用上下文，不能由用户文本或请求 metadata 指定。
- 查询只允许白名单键，并携带当前品类范围。
- 用户本轮明确约束优先于 Memory 默认值。
- 负向记忆和排除项不能被低置信识别结果覆盖。

## 3. 写入链路

长期记忆遵循 prepare → confirm → commit：

1. Intent Agent 从用户明确表达中生成 `MemoryDirective`。
2. Memory Agent 将合法 directive 转换为稳定 `MemoryMutation`。
3. Supervisor 保存待确认 mutation 的 ID 和 payload hash。
4. 需要确认时返回 `MemoryConfirmation` 中断。
5. 恢复后 Supervisor 为同一 mutation 集合生成授权。
6. Memory Agent 校验授权 ID、interrupt ID、mutation ID 列表和 payload hash 后提交。

任何授权字段不一致都返回 `CAPABILITY_DENIED`；失败不能伪装为“已记住”。

## 4. Scope 与应用方式

Memory 使用 `scope_key` 隔离全局和品类偏好，并通过 `apply_mode` 控制作用：

- `constraint_default`：只在本轮没有用户明确值时补充默认约束；
- `ranking_preference`：影响排序权重，不进入硬过滤；
- `negative_term`：表示排除偏好，按白名单规则应用。

同一 owner、scope 和 memory key 的更新必须满足版本/幂等约束，禁止静默覆盖冲突写入。

## 5. 任务与状态边界

- Memory Agent 只接收 `MemoryTaskInput`，不接收完整 `SupervisorState`。
- recall、prepare、commit 分别对应独立的 `AgentTaskKind`。
- task result 以 `output_hash` 幂等保存；Checkpoint 重放不会重复已完成任务。
- Supervisor 是 mutation 授权和最终规范状态的唯一写入者。
- Memory commit 是副作用任务；只读评估必须显式抑制该任务。

## 6. 配置

| 配置 | 说明 |
|---|---|
| `SHIJIAJING_MEMORY_ENABLED` | 总开关 |
| `SHIJIAJING_MEMORY_RECALL_ENABLED` | 是否创建 recall 任务 |
| `SHIJIAJING_MEMORY_COMMIT_ENABLED` | 是否创建 prepare/commit 任务 |
| `SHIJIAJING_MEMORY_BACKEND` | `disabled` / `sqlite` / `postgres` |
| `SHIJIAJING_MEMORY_DSN` | 存储连接信息 |
| `SHIJIAJING_MEMORY_RECALL_LIMIT` | recall 去重后的最大记录数 |
| `SHIJIAJING_MEMORY_CONFIRMATION_REQUIRED` | commit 前是否要求 HITL |
| `SHIJIAJING_RECENT_TURNS_LIMIT` | 会话摘要最大轮数 |
| `SHIJIAJING_RECENT_TURNS_MAX_BYTES` | 会话摘要序列化大小上限 |

启用 commit 时必须同时启用 recall。启用长期记忆时，调用方必须提供可信
`AgentExecutionContext.memory_owner_id`。

## 7. 故障语义

- recall 不可用：任务返回 `FALLBACK`，主业务可以继续，但响应必须标记降级。
- prepare 失败：不生成 mutation，不影响比价结果。
- commit 失败：任务返回 `FAILED`，不得返回保存成功。
- Checkpoint 恢复：同一 task/mutation 重放必须幂等。
- Event Store 失败：不回滚已经成功的 Memory 事务，但需要记录可修复的一致性缺口。

## 8. 验收重点

- owner 隔离、scope 去重和用户显式约束优先级；
- 非白名单键、越权 owner 和伪造授权全部拒绝；
- commit 重放不产生重复记录；
- HITL resume 只能消费匹配的活动中断；
- recall/commit 服务故障时状态和用户提示真实；
- Checkpoint、事件和日志中不保存用户全文或敏感 metadata。
