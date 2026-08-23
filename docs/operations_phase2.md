# 二期存储与发布运维

本文档对应第二阶段方案的备份、迁移、事件修复和回滚边界。Checkpoint 是工作流状态事实源；Request Ledger、Memory 和 Event Store 分别保存请求结果、长期记忆和追加式审计数据。Event Store 不能反向覆盖 Checkpoint。

专项 runbook：

- [Legacy Checkpoint 状态迁移](operations/state_migration.md)
- [一致性事件修复](operations/event_repair.md)

## 0. 启动前 preflight

`shijiajing-preflight` 只校验配置，并对已启用的 Checkpoint、Request Ledger、Memory、Cache、Event Store 和 Trace 资源执行 setup/close 生命周期。runtime 还会统一持有并关闭 Ark 共享模型客户端，以及 Retrieval 适配器持有的 Embedding、Milvus 客户端和本地兜底资源；后续资源 setup 失败时仍按逆序关闭已创建资源。preflight 不调用模型、不查询 Milvus、不写入业务数据。

JSON 输出同时记录实际生效的 `hitl_enabled`、Memory recall/commit、
`retrieval_fusion_strategy`、`retrieval_rerank_enabled`、`retrieval_index_version` 和五类
`cache_ttl_seconds`，用于发布灰度审计；这些字段只读展示配置，不接受客户端请求覆盖。

真实部署配置完成后执行：

```powershell
uv run shijiajing-preflight --json
```

只演练二期存储资源时执行：

```powershell
uv run shijiajing-preflight --storage-only --json
```

需要验证 OTLP HTTP endpoint 是否真正接收时，先设置精确配置，再执行合成 trace probe：

```powershell
$env:SHIJIAJING_TRACE_BACKEND = "opentelemetry"
$env:SHIJIAJING_TRACE_DSN = "http://127.0.0.1:4318/v1/traces"
uv run shijiajing-preflight --storage-only --verify-trace --json
```

该 probe 只发送固定的 `preflight-trace-probe` 标识，不包含用户文本、Prompt、DSN 或密钥。
命令返回 `status=ok` 且 `trace_verified=true` 才表示 exporter 完成了一次真实发送；连接
失败、HTTP 非成功响应或 exporter 返回 `SpanExportResult.FAILURE` 时退出码为 2。
preflight 失败的 JSON 只保留精确配置缺失项或固定资源错误消息，不输出 provider 异常、主机、
DSN 或密钥。`shijiajing-migrate-state`、`shijiajing-repair-events` 和
`shijiajing-reconstruct-turn` 也使用同一公开错误边界。

`status=ok` 只证明配置、资源 setup 和（若显式启用）trace probe 成功；PostgreSQL contract、
重启连续性和正式评测仍必须分别执行。

## 0.1 生产发布证据门禁

`shijiajing-release-check` 汇总已执行的机器可读证据，缺少任一项时返回退出码 1；它不会
把本地 integration 通过推断为生产 HA、备份或 OTLP 通过。正式评测 JSON 必须同时包含
`trust_level=frozen`、`label_method=adjudicated`、`metric_gate_passed=true`、
`release_gate_eligible=true`、`release_gate_passed=true`，且 `blocking_failures` 与
`blocking_pending` 都必须为空；正式性能报告必须包含 `source=formal`、通过的
`gate_strategy`、正数 `gate_max_p95_ms`、空的 `gate_failures`，并且所选策略的实际
`duration_ms_p95` 不得超过阈值。backup/restore summary 还必须指向非空 dump，并记录
成功的 `pg_dump` 与 `pg_restore` 命令结果；verification summary 的每一条已记录命令也
必须是 `status=passed` 且 `exit_code=0`。dump 必须位于 summary 所在的证据目录内，且
命令记录中的 `pg_dump`/`pg_restore` 必须是独立的 executable token，不能用相似子串替代。

```powershell
uv run shijiajing-release-check `
  --verification-summary reports/phase2-verification/<passed-run>/summary.json `
  --backup-summary reports/phase2-verification/<backup-run>/summary.json `
  --eval-report reports/frozen/eval_report.json `
  --benchmark-report reports/frozen/benchmark_report.json `
  --production-evidence-manifest release/prod-evidence.json `
  --json
```

生产证据 manifest 的固定结构如下；`checks` 只能包含下列三项，三项证据文件必须与
`sha256` 完全匹配，路径相对于 manifest 所在目录，且不得使用绝对路径或 `..` 穿越。
每个证据文件本身也必须满足固定
机器可读契约：`check_id` 必须与 manifest 条目一致，`status=passed`，`verified_at` 必须
是带 UTC 时区的 ISO-8601 时间，并且 `claims` 必须完整覆盖对应的验收项且全部为
`passed`；生成器和发布门禁使用同一份契约校验。

```json
{
  "schema_version": "1.0",
  "environment": "prod",
  "checks": {
    "postgres_ha": {"status": "verified", "evidence_path": "postgres-ha.json", "sha256": "<64 lowercase hex>"},
    "backup_storage": {"status": "verified", "evidence_path": "backup-storage.json", "sha256": "<64 lowercase hex>"},
    "otel_collector": {"status": "verified", "evidence_path": "otel-collector.json", "sha256": "<64 lowercase hex>"}
  }
}
```

三类证据文件的固定 `claims` 集合为：

```json
{
  "postgres_ha": ["ha_failover", "connection_pool_load", "real_data_recovery"],
  "backup_storage": ["encryption", "retention", "permissions", "cross_region_restore"],
  "otel_collector": ["persistence", "alerts", "query", "permissions", "retention"]
}
```

例如 `postgres-ha.json` 至少应具有以下结构：

```json
{
  "schema_version": "1.0",
  "environment": "prod",
  "check_id": "postgres_ha",
  "status": "passed",
  "verified_at": "2026-08-22T00:00:00Z",
  "claims": {
    "ha_failover": "passed",
    "connection_pool_load": "passed",
    "real_data_recovery": "passed"
  }
}
```

摘要校验只证明证据文件未被替换，不替代生产系统本身的 HA、跨区域恢复、保留策略和
观测告警验收；这些证据缺失时发布门禁必须保持未就绪。

可使用同一 CLI 生成 manifest，命令拒绝读取 manifest 目录外的证据，也拒绝覆盖已有文件：

```powershell
uv run shijiajing-release-check create-manifest `
  --output release/prod-evidence.json `
  --postgres-ha release/postgres-ha.json `
  --backup-storage release/backup-storage.json `
  --otel-collector release/otel-collector.json
```

Windows 下所有会进入异步外部资源的 CLI 统一使用 `SelectorEventLoop` 兼容 psycopg；
这包括 preflight、live 评测、迁移、事件还原、事件修复、Milvus 初始化和商品索引，
其他平台保持默认事件循环策略。

仓库提供可重复的本地依赖环境：[`deploy/phase2/README.md`](../deploy/phase2/README.md)
和 `deploy/phase2/docker-compose.yml` 启动隔离 PostgreSQL 16 与 OTLP HTTP Collector。
该环境只用于开发/集成验证，Collector 的 debug exporter 输出容器日志，不等同于生产观测
系统。Compose 启动前必须显式设置 `POSTGRES_PASSWORD`；应用在宿主机运行时使用
`postgresql://...@127.0.0.1:5432/...` 和 `http://127.0.0.1:4318/v1/traces`，容器内运行时
改用实际服务名和端口映射，不能把示例 DSN 当作生产凭据。

具备 Docker Engine 时，可直接执行统一验收编排；它会等待两个服务健康、启用严格 PostgreSQL
gate、执行 `--verify-trace`，最后输出 Collector 日志并停止服务（不删除 volume）：

```powershell
pwsh -File .\deploy\phase2\verify.ps1
```

PostgreSQL contract 的测试夹具按以下顺序选择数据库：优先使用
`SHIJIAJING_TEST_POSTGRES_DSN`；未设置时，在显式执行 `-m integration` 且 Docker daemon
可用的环境中自动启动隔离的 PostgreSQL 16 容器；两者都不可用时明确 skip。普通测试不会
隐式启动容器，也不会把 skip 当作 contract 通过。

```powershell
# 已有隔离数据库
$env:SHIJIAJING_TEST_POSTGRES_DSN = "postgresql://user:password@127.0.0.1:5432/test"
uv run pytest -q -m integration

# 或者在 Docker daemon 已启动时让测试夹具自动启动 PostgreSQL 16
uv run pytest -q -m integration
```

正式验收必须禁止基础设施缺失被当作通过：

```powershell
$env:SHIJIAJING_REQUIRE_POSTGRES = "1"
uv run pytest -q -m integration
```

该开关下缺少 `SHIJIAJING_TEST_POSTGRES_DSN`、Docker Engine 或数据库连接会返回非零退出码；
普通开发运行不设置该开关时，环境不足仍只产生明确 skip。

对已完成 turn 做只读轨迹还原：

```powershell
uv run shijiajing-reconstruct-turn `
  --dsn $env:SHIJIAJING_EVENT_STORE_DSN `
  --session-id <session_id> `
  --turn-id <turn_id> `
  --json
```

工具只读取 Event Store，不调用模型、不写入事件；Trace sink 对 replay 的重复 `turn_started`
保持同一棵 root span，不创建悬挂的重复 Trace 树；还原工具会拒绝同一 turn 内
`session_id`、`request_id`、`turn_id` 或 `trace_id` 不一致的事件，并输出节点顺序、
Agent、版本元数据和终态。Trace 后端使用输出的 `trace_id` 查询；该命令不把 Event
Store 记录冒充外部 Collector 的完整 Trace。
命令在 Event Store setup、读取或还原失败时也会关闭已创建的资源，不把失败连接池留在进程中。

## 1. 启动前检查

先确认配置使用精确的 `SHIJIAJING_` 前缀：

```powershell
uv run shijiajing-migrate-state inspect --dsn $env:SHIJIAJING_CHECKPOINT_DSN
uv run shijiajing-migrate-state validate --dsn $env:SHIJIAJING_CHECKPOINT_DSN
uv run shijiajing-repair-events --dry-run
```

`shijiajing-migrate-state` 当前检查 legacy SQLite `agent_checkpoint` 表；native LangGraph Checkpointer 的 DDL 由 `open_graph_checkpointer()` 在 runtime 启动阶段完成。任何数据库都必须先完成 setup，再允许业务请求进入。

Checkpoint 数据库同时维护 `agent_resume_claim`；native HITL resume 在执行前按
`(session_id, interrupt_id)` 原子抢占，重复恢复直接拒绝。该表与 Checkpoint 位于同一数据库，
随同数据库备份和恢复，不单独迁移业务状态。

### 1.1 Legacy checkpoint 迁移

`inspect` 和 `validate` 只读。需要实际把 legacy 1.0 checkpoint 写成 1.1 时，先做
预览，再在已完成备份的文件上显式执行 `migrate --apply`：

```powershell
uv run shijiajing-migrate-state migrate --dsn $env:SHIJIAJING_CHECKPOINT_DSN
uv run shijiajing-migrate-state migrate `
  --dsn $env:SHIJIAJING_CHECKPOINT_DSN `
  --apply `
  --event-store-backend sqlite `
  --event-store-dsn $env:SHIJIAJING_EVENT_STORE_DSN
```

迁移先在 SQLite 事务中提交 `state_json` 与 `schema_version=1.1`，成功后才追加
`checkpoint_migrated`。只有 checkpoint 中真实存在非空的 `request_id`、`turn_id`、
`trace_id` 才会追加该事件；缺少任何标识时只报告 `audit_skipped_missing_ids`，不填充
推测值。事务同时写入 `checkpoint_migration_audit`，因此 Event Store 暂时不可用时，
再次执行同一 `migrate --apply` 可以补发缺失的 `checkpoint_migrated`，不会把已完成的
checkpoint 再次当成新迁移。默认不写入 Event Store；启用审计时必须显式提供 backend 和 DSN。

## 2. SQLite 备份

SQLite 生产文件必须使用 SQLite backup API，不使用运行中的文件复制。对每个实际启用的文件分别执行；路径来自对应 DSN：

```powershell
uv run shijiajing-backup-sqlite --mode backup `
  --source-dsn $env:SHIJIAJING_CHECKPOINT_DSN `
  --target-dsn backup/checkpoint-2026-08-22.sqlite
uv run shijiajing-backup-sqlite --mode backup `
  --source-dsn $env:SHIJIAJING_REQUEST_LEDGER_DSN `
  --target-dsn backup/request-ledger-2026-08-22.sqlite
uv run shijiajing-backup-sqlite --mode backup `
  --source-dsn $env:SHIJIAJING_MEMORY_DSN `
  --target-dsn backup/memory-2026-08-22.sqlite
uv run shijiajing-backup-sqlite --mode backup `
  --source-dsn $env:SHIJIAJING_CACHE_DSN `
  --target-dsn backup/cache-2026-08-22.sqlite
uv run shijiajing-backup-sqlite --mode backup `
  --source-dsn $env:SHIJIAJING_EVENT_STORE_DSN `
  --target-dsn backup/event-store-2026-08-22.sqlite
```

`backup` 默认拒绝覆盖已有目标文件；需要替换既有归档时必须显式追加 `--apply`。

恢复必须在隔离目标上执行，并显式指定 `--apply`：

```powershell
uv run shijiajing-backup-sqlite --mode restore `
  --source-dsn backup/checkpoint-2026-08-22.sqlite `
  --target-dsn restore/checkpoint.sqlite `
  --apply
```

需要同时验证完整性和备份内容摘要时，使用隔离目标执行 `verify`；目标文件已存在时也
必须显式指定 `--apply`：

```powershell
uv run shijiajing-backup-sqlite --mode verify `
  --source-dsn $env:SHIJIAJING_CHECKPOINT_DSN `
  --target-dsn restore/checkpoint-verify.sqlite
```

`backup`、`restore`、`verify` 三种模式都严格按 `source-dsn → target-dsn` 方向执行：
`restore` 的 source 是备份文件，`verify` 会把 source 复制到隔离 target 后比较摘要。
命令会输出源文件和目标文件的 `integrity_check`、SHA-256 内容摘要及
`content_equal`。它不替代生产写入停机、active interrupt 清单和 PostgreSQL dump/restore
演练。命令先把 SQLite backup API 的结果写入目标同目录 staging 文件，完成完整性和内容摘要
校验后才原子替换目标；校验或写入失败时保留已有目标文件并清理 staging 文件。

未启用的 backend 不执行对应备份命令。备份后用 `sqlite3 <file> "PRAGMA integrity_check;"` 验证，并把备份文件、命令输出和 schema 版本一起归档。

### 2.1 Native active interrupt 恢复演练

Native 模式至少要把同一停机窗口内启用的 `checkpoint`、`request_ledger`、`memory`、
`cache` 和 `event_store` SQLite 文件作为一组处理：先停止写入并记录 active interrupt，再分别执行
`backup`，在隔离目录分别执行带 `--apply` 的 `restore`，完成五个文件的
`integrity_check`、内容摘要和 schema 检查后，使用恢复后的 DSN 启动 runtime。恢复后的
演练必须实际执行一次原 `interrupt_id` 的 `resume`，验证 Memory、Event Store 和 Request
Ledger 可读，并再次提交同一 `(session_id, request_id)` 验证幂等结果。不能只验证文件可
打开；`agent_resume_claim` 与 LangGraph native checkpoint 必须位于同一个恢复后的
checkpoint 文件中。

## 3. PostgreSQL 备份与恢复

PostgreSQL backend 使用对应的 DSN；一份数据库 dump 覆盖该数据库内已启用的 Checkpoint、Request Ledger、Memory、Cache 和 Event Store 表。项目封装只调用已安装的 `pg_dump` 和 `pg_restore`，不通过 shell 拼接命令：

```powershell
uv run shijiajing-backup-postgres backup `
  --source-dsn $env:SHIJIAJING_CHECKPOINT_DSN `
  --dump backup/shijiajing-2026-08-22.dump

# 独立验证 custom-format dump；只读，不连接目标数据库
uv run shijiajing-backup-postgres verify `
  --dump backup/shijiajing-2026-08-22.dump
```

备份和恢复命令会按 libpq 规则解析 DSN，把普通数据库密码从 `pg_dump`/`pg_restore` 的
进程参数移到子进程 `PGPASSWORD` 环境变量；命令行中不会出现完整带密码 DSN。包含
`sslpassword` 的 DSN 直接拒绝，避免把未实现安全传递的密钥密码放入命令行。需要该安全
解析路径时安装 `shijiajing-agent[postgres]`；密码应通过受控环境变量或密钥注入系统提供，
不要把真实 DSN 写入脚本、日志或 shell 历史。

备份默认拒绝覆盖已有 dump；确认替换时必须显式追加 `--apply`。备份先写同目录临时文件，
通过 `pg_restore --list` 后才替换最终路径；归档校验失败时保留已有 dump 并清理临时文件。

恢复必须在隔离数据库中完成校验，再切换应用 DSN；恢复是写入操作，必须显式指定 `--apply`：

```powershell
uv run shijiajing-backup-postgres restore `
  --dump backup/shijiajing-2026-08-22.dump `
  --target-dsn <isolated_restore_dsn> `
  --apply
```

禁止直接对生产 Checkpoint 执行覆盖式恢复；恢复前停止写入并保存当前 active interrupt 清单。
`pg_restore --list` 只验证归档可读，不证明目标数据库已经完成业务级恢复；必须另行执行
setup、contract 和数据计数校验。

在 Docker 本地验收环境中，可用统一脚本完成一次真实 custom-format dump/restore 演练：

```powershell
pwsh -File .\deploy\phase2\verify.ps1 -VerifyBackupRestore
```

该路径使用 PostgreSQL 16 容器内的 `pg_dump`/`pg_restore`，恢复到隔离数据库
`phase2_restore`，比较恢复前后的 public 表数量并校验固定哨兵数据；dump 和机器可读结果
保存在本次 `reports/phase2-verification/run-<timestamp>/` 目录。该演练证明本地数据库引擎
的备份恢复链路，不证明生产备份存储、加密、保留、权限、跨区域恢复或主机上的
`shijiajing-backup-postgres` client tools 已验收。

## 4. 事件修复

一致性事件只在真实事务成功后追加。事件追加失败不回滚真实事务，修复前先 dry-run：

```powershell
uv run shijiajing-repair-events --dry-run `
  --dsn $env:SHIJIAJING_EVENT_STORE_DSN `
  --ledger-dsn $env:SHIJIAJING_REQUEST_LEDGER_DSN `
  --memory-dsn $env:SHIJIAJING_MEMORY_DSN
```

repair 使用的 Event Store 在 setup、追加或读取失败时都会执行 close；失败不会留下未关闭的
连接或连接池。

确认缺失事件集合、来源表和数量后，使用相同参数改为 `--apply`。Event Store 已存在且内容一致的 `event_id` 必须保持幂等；内容冲突必须停止修复并人工处理。

SQLite 与 PostgreSQL 必须使用实际 backend 配置；PostgreSQL 修复示例：

```powershell
uv run shijiajing-repair-events --dry-run `
  --event-store-backend postgres `
  --dsn $env:SHIJIAJING_EVENT_STORE_DSN `
  --ledger-backend postgres `
  --ledger-dsn $env:SHIJIAJING_REQUEST_LEDGER_DSN `
  --memory-backend postgres `
  --memory-dsn $env:SHIJIAJING_MEMORY_DSN
```

Memory mutation 只有在 Request Ledger 提供真实 `turn_id` 与 `trace_id` 时才会补建；
缺少来源账本时跳过，不生成合成轨迹。

普通诊断事件包括 `agent_started`、`agent_completed`、`agent_failed`、`agent_interrupted`、`agent_resumed`、`memory_recalled`、`cache_hit`、`cache_miss` 和 `request_ledger_repaired`。HITL 事件只保存 `interrupt_id` 与 `interrupt_kind`；memory recall 只保存条数；缓存事件只保存 namespace 与 SHA-256 cache key；Ledger repair 只保存 response hash 和 `native_checkpoint` 来源，不保存 prompt、用户文本或模型输入输出。

缓存是 miss-safe 加速层，不是业务事实来源。版本向量变化会生成不同的 canonical key；
缓存载荷读取后由各 wrapper 重新执行 Pydantic、检索硬过滤或解释事实一致性校验，
校验失败按 miss 重新调用真实提供方。Cache get/set/delete 故障只增加
`cache_failure_total{operation="get|set|delete"}`，不改变响应正确性。

native runtime 除了打开 LangGraph Checkpointer，还会在启动阶段 setup `CheckpointPort`
使用的 resume fence 表 `agent_resume_claim`；不会把该 DDL 延迟到首个 resume。resume
开始时先原子 claim；流程异常会释放未完成 claim，成功恢复后的 claim 保留，跨进程重复
resume 直接拒绝。同一 turn 内重复产生的同类 interrupt 由持久化的
`interrupt_generation` 区分，其参与 `interrupt_id` 的 SHA-256 计算。

## 5. 回滚顺序

回滚属于部署操作，不是客户端输入：

1. 停止新请求写入，记录 `session_id`、`request_id`、`turn_id` 和每个 native checkpoint 的 `active_interrupt`。
2. 存在 active interrupt 时，不切回 legacy；先完成 resume，或在业务确认后清理对应会话。
3. native 持久化故障只切回 legacy 的读取路径；Event Store 不得覆盖 Checkpoint。
4. Memory、Cache、Event Store 或 OpenTelemetry 故障分别切换到 `disabled`，不得删除正确性数据；Cache 关闭只产生 miss。
5. RRF/rerank 回归时把 `SHIJIAJING_RETRIEVAL_FUSION_STRATEGY` 设为 `weighted`，并将 `SHIJIAJING_RETRIEVAL_RERANK_ENABLED` 设为 `false`。
6. 完成恢复后重新执行迁移检查、离线测试和 `shijiajing-repair-events --dry-run`，再开放写入。

回滚完成条件是：Checkpoint schema 可读、Request Ledger 可重放、Memory owner 隔离仍成立、Event Store 不出现新的冲突事件，且 active interrupt 清单与切换前一致或已被明确消费。
