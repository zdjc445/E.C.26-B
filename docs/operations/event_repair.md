# 一致性事件修复 Runbook

本 runbook 用 Request Ledger 和 Memory 的真实事务记录补建 Event Store 一致性事件。
Checkpoint 仍是工作流状态事实源，Event Store 不得覆盖 Checkpoint。普通诊断事件不是本
命令的修复对象。

## 修复范围与前提

当前只补建以下一致性事件：

- `request_result_committed`：来源为 `agent_request_result`；
- `memory_committed` / `memory_forgotten`：来源为 `memory_mutation`，且必须能在 Request
  Ledger 找到同一 `(session_id, request_id)`，从而取得真实 `turn_id` 和 `trace_id`。

开始前：

1. 停止或隔离会写入来源表和 Event Store 的应用实例，避免修复期间数据继续变化；
2. 完成 Checkpoint、Request Ledger、Memory 和 Event Store 的可恢复备份；
3. 确认 Event Store backend、来源 backend 与 DSN 使用实际部署值，不把示例 DSN 当作凭据；
4. 先执行 `--dry-run`，确认候选数量和来源范围。

## SQLite dry-run

```powershell
uv run shijiajing-repair-events --dry-run `
  --dsn $env:SHIJIAJING_EVENT_STORE_DSN `
  --ledger-dsn $env:SHIJIAJING_REQUEST_LEDGER_DSN `
  --memory-dsn $env:SHIJIAJING_MEMORY_DSN
```

PostgreSQL 来源需要显式指定 backend：

```powershell
uv run shijiajing-repair-events --dry-run `
  --event-store-backend postgres `
  --dsn $env:SHIJIAJING_EVENT_STORE_DSN `
  --ledger-backend postgres `
  --ledger-dsn $env:SHIJIAJING_REQUEST_LEDGER_DSN `
  --memory-backend postgres `
  --memory-dsn $env:SHIJIAJING_MEMORY_DSN
```

`--dry-run` 只读取来源和 Event Store，不追加事件。输出中的“可补建”数量必须与维护
窗口记录一致。若出现 `event_id` 已存在但内容不同，命令返回退出码 `2` 并停止；不能
用 `--apply` 绕过冲突。

## 显式提交

确认 dry-run 结果和备份后，把同一组参数中的 `--dry-run` 替换为 `--apply`：

```powershell
uv run shijiajing-repair-events --apply `
  --dsn $env:SHIJIAJING_EVENT_STORE_DSN `
  --ledger-dsn $env:SHIJIAJING_REQUEST_LEDGER_DSN `
  --memory-dsn $env:SHIJIAJING_MEMORY_DSN
```

提交语义固定如下：

- `event_id` 由真实 session/request/turn、agent、node、事件类型和稳定 attempt 计算；
- 已存在且内容一致的事件保持幂等，不重复追加；
- 缺少 Request Ledger 上下文的 Memory mutation 被跳过，不合成 `turn_id` 或 `trace_id`；
- append 失败返回退出码 `2`，已成功追加的事件不回滚，重试前必须重新 dry-run；
- runtime/adapter 在 setup、追加或读取失败后都执行 close，不保留悬挂连接或连接池。

## 验证、冲突和回滚

提交后用同一参数再次执行 `--dry-run`，期望可补建数量为 `0`；保存命令输出、退出码、
来源行数、Event Store 行数和事件 ID 列表。再使用只读还原工具按真实
`session_id` + `turn_id` 检查事件顺序与四个标识一致：

```powershell
uv run shijiajing-reconstruct-turn `
  --dsn $env:SHIJIAJING_EVENT_STORE_DSN `
  --session-id <session_id> `
  --turn-id <turn_id> `
  --json
```

内容冲突不是自动回滚条件。应停止写入、保留冲突证据、从修复前备份恢复到隔离环境并
人工比较来源表与 Event Store；不得删除或覆盖已存在的 Event Store 事件来“消除”冲突。

## 敏感数据与证据边界

修复事件只写入 response hash、mutation ID、operation 等字段化信息，不写入用户原文、
Prompt、DSN、密钥、图片 data URL 或模型原始输出。修复成功只证明 Event Store 的一致性
事件已按真实来源补齐，不证明外部 Collector、生产备份存储或生产 HA 已验收。
