# Legacy Checkpoint 状态迁移 Runbook

本 runbook 只处理 legacy SQLite `agent_checkpoint` 中 `schema_version="1.0"` 到
`schema_version="1.1"` 的迁移。Checkpoint 是工作流状态事实源；迁移不会把 Event Store
反向写回 Checkpoint，也不会为缺失的 `request_id`、`turn_id` 或 `trace_id` 猜造审计标识。

## 迁移前

1. 停止会写入目标 Checkpoint 文件的应用实例，并记录 active interrupt。
2. 使用 SQLite backup API 完成可恢复备份；不要直接复制正在使用的 SQLite 文件。
3. 确认目标 DSN 是 SQLite 文件路径或 `sqlite:///` / `sqlite://` 路径。该 CLI 不执行
   PostgreSQL Checkpoint 的 legacy 表迁移；native LangGraph Checkpointer 的 DDL 由 runtime
   启动阶段的 `open_graph_checkpointer()` 完成。

## 只读检查

```powershell
uv run shijiajing-migrate-state inspect `
  --dsn $env:SHIJIAJING_CHECKPOINT_DSN

uv run shijiajing-migrate-state validate `
  --dsn $env:SHIJIAJING_CHECKPOINT_DSN
```

`inspect` 输出总行数和各 `schema_version` 数量。`validate` 还会解析每条 `1.0` 状态并
执行纯函数迁移校验；发现损坏 payload 时返回退出码 `1`，配置或数据库异常返回退出码
`2`。没有提供 DSN 时命令安全退出，不执行迁移。

## 预览与提交

默认 `migrate` 只预览，不写数据库：

```powershell
uv run shijiajing-migrate-state migrate `
  --dsn $env:SHIJIAJING_CHECKPOINT_DSN
```

确认备份、active interrupt 清单和预览结果后，才显式提交：

```powershell
uv run shijiajing-migrate-state migrate `
  --dsn $env:SHIJIAJING_CHECKPOINT_DSN `
  --apply
```

提交 Event Store 审计事件时，必须同时显式提供 backend 和 DSN：

```powershell
uv run shijiajing-migrate-state migrate `
  --dsn $env:SHIJIAJING_CHECKPOINT_DSN `
  --apply `
  --event-store-backend sqlite `
  --event-store-dsn $env:SHIJIAJING_EVENT_STORE_DSN
```

事务行为固定如下：

- `state_json` 和 `schema_version` 在同一个 SQLite 事务中提交；
- 同一事务写入 `checkpoint_migration_audit`，重复执行不会重复迁移已审计行；
- Checkpoint 更新成功后才追加 `checkpoint_migrated`；Event Store 暂时不可用时，可根据
  `checkpoint_migration_audit` 重试补发；
- 缺少任一真实业务标识的行只计入 `audit_skipped_missing_ids`，不会生成伪造事件；
- 事件追加失败不回滚已经提交的 Checkpoint 迁移，必须先修复 Event Store，再重新执行
  `--apply`。

## 验证与回滚

提交后重新执行 `validate` 和 `migrate` 预览，确认 `schema_versions` 中没有待迁移的
`1.0` 行，并保存 CLI JSON 输出、退出码、备份摘要和 Event Store 追加结果。

迁移失败或需要回滚时，停止写入并从迁移前备份恢复到隔离文件，先验证
`integrity_check`、schema 版本和 active interrupt，再切换应用 DSN。不要直接手工修改
`schema_version` 或删除 `checkpoint_migration_audit`；native Checkpointer 的迁移/回滚必须
按对应 runtime 和数据库备份流程执行。

## 证据边界

本 runbook 的成功只证明指定 Checkpoint 文件完成了可验证的 schema 迁移。它不证明生产
高可用、跨区域恢复、备份存储策略或正式发布门禁已通过；这些仍需
`shijiajing-release-check` 所要求的外部证据。
