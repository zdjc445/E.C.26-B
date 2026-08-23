# 记忆说明

系统分离三层记忆：本轮 `AgentState` 工作记忆、会话级 bounded `recent_turns`，以及
显式、可审计、按 owner 隔离的长期 Memory。长期 Memory 不是模型自由写入的用户画像。

## 0. 会话记忆

- 每个 `SUCCESS`、`CLARIFICATION`、`NO_RESULTS` 或 `FAILED` 终态响应追加一条
  `ConversationTurnSummary`。
- `recent_turns` 由 `RECENT_TURNS_LIMIT` 限制长度，native 从 thread checkpoint 继续，
  legacy 从上一轮状态恢复；它不依赖 `memory_enabled` 或长期 Memory adapter。
- 会话摘要不持久化完整用户文本；`user_text` 在终态构造时不写入，Checkpoint 只保存
  `user_text_sha256` 和 `user_text_length`。
- 新 turn 清空本轮查询、候选、响应和控制字段，但保留 `recent_turns`、有效约束、识别历史
  与 `subject_id`。

## 1. 长期 Memory 数据边界

- 可信 owner 只能来自 `AgentExecutionContext.memory_owner_id`；普通请求 `metadata` 不参与 owner 推断。
- `memory_enabled=false` 或没有 owner 时使用 `DisabledMemoryAdapter`，不读不写长期记忆。
- `AgentExecutionContext.memory_enabled=true` 只允许 native runtime；legacy `start()` 会明确失败，
  不把“未执行长期记忆”的结果伪装成已启用记忆。
- `recall_memory` 在 Recognition/Intent 汇合后执行；`commit_memory` 在最终响应后执行。
- `MemoryMutation` 先经过 `validate_directive()` 和 `build_memory_mutation()`；SQLite/PostgreSQL
  适配器边界再调用 `validate_mutation()`（内部使用 `canonical_memory_value()`），不接受未经
  白名单校验的自由 JSON。

## 2. 第一版白名单

| `memory_key` | 值域 |
|---|---|
| `max_price` / `min_price` / `min_rating` | 有限非负 `float`；评分范围 `0..5`，价格最多两位小数 |
| `platforms` / `colors` / `negative_terms` | 非空字符串列表，去空白、去重、保持首次出现顺序 |
| `sort_by` | 现有 `SortBy` 枚举值 |
| `preferences` | 现有 `Preference` 枚举值列表，去重后最多 10 项 |

`memory_id`、`mutation_id` 都由稳定输入计算 SHA-256，不使用随机 UUID；公共契约强制校验为 64 位小写十六进制。相同 mutation replay 只返回既有结果；不同 owner 的 recall 永远不能互相读取。

## 3. HITL 与失败策略

当 `SHIJIAJING_MEMORY_CONFIRMATION_REQUIRED=true` 时，UPSERT、FORGET 和 CLEAR_OWNER 在 `memory_confirmation_interrupt` 后才提交。recall 失败继续当前业务请求并增加 `memory_recall_failure_total`；commit 失败不得添加“已记住/已忘记”成功提示，并增加 `memory_commit_failure_total`。

## 4. 运维验证

离线 contract 覆盖白名单、owner 隔离、覆盖、遗忘和 mutation 幂等。PostgreSQL contract 使用：

```powershell
$env:SHIJIAJING_TEST_POSTGRES_DSN="postgresql://..."
uv run pytest -q -m integration tests/contract/test_memory_adapters.py
```

没有该环境变量时测试明确 skip，不把 skip 计为 PostgreSQL 已通过。
