# 二期本地 PostgreSQL / OTLP 验证环境

该目录只提供开发和集成测试基础设施，不包含生产密钥、商品数据或应用容器。PostgreSQL
使用 `postgres:16-alpine`；OpenTelemetry Collector 只把接收到的 traces 输出到容器日志，
用于验证 OTLP HTTP 发送、脱敏属性和关闭 flush，不代表外部观测系统验收。

## 启动

在仓库根目录执行 PowerShell：

```powershell
$env:POSTGRES_PASSWORD = "change-me-for-local-only"
docker compose --env-file deploy/phase2/.env.example `
  -f deploy/phase2/docker-compose.yml up -d
docker compose --env-file deploy/phase2/.env.example `
  -f deploy/phase2/docker-compose.yml ps
```

`POSTGRES_PASSWORD` 没有代码默认值；Compose 未获得该变量时会拒绝启动。首次启动后，
等待 `postgres` 状态为 `healthy`，再执行 PostgreSQL contract：

```powershell
$env:SHIJIAJING_TEST_POSTGRES_DSN = `
  "postgresql://shijiajing:change-me-for-local-only@127.0.0.1:5432/shijiajing"
uv run pytest -q -m integration
```

发布或 CI 验收不能接受 skip。设置严格开关后，缺少 DSN、Docker Engine 或数据库连接时
命令必须返回非零退出码：

```powershell
$env:SHIJIAJING_REQUIRE_POSTGRES = "1"
uv run pytest -q -m integration
```

数据库可用时该开关不改变 contract 内容；它只把基础设施缺失从明确 skip 提升为验收失败。

## 可重复验收编排

在具备 Docker Engine 的环境中，可用统一脚本执行健康检查、严格 PostgreSQL contract、
PostgreSQL 重启后的健康恢复、OTLP 合成 probe、Collector 日志输出和服务停止：

```powershell
pwsh -File .\deploy\phase2\verify.ps1
```

需要同时演练 PostgreSQL custom-format 备份与隔离恢复时，显式增加备份开关：

```powershell
pwsh -File .\deploy\phase2\verify.ps1 -VerifyBackupRestore
```

该开关在 PostgreSQL 16 容器内调用 `pg_dump`/`pg_restore`，把 dump 复制到本次
`reports/phase2-verification/run-<timestamp>/` 证据目录，执行 `pg_restore --list`，恢复到
隔离数据库 `phase2_restore`，并比较恢复前后的 public 表数量和固定哨兵数据。它验证本地
PostgreSQL 引擎的实际 dump/restore，不等同于生产备份策略，也不替代主机上
`shijiajing-backup-postgres` 对已安装 PostgreSQL client tools 的验收。

脚本默认使用 `55432`、`44318` 和 `44317` 避免占用常用开发端口；可通过参数覆盖。每次运行
默认使用独立的 Compose project name `shijiajing-phase2-<PowerShell进程号>`，避免并发运行
或残留服务之间互相操作；需要固定项目名时可传入 `-ProjectName`。脚本只会执行
`docker compose down`，不会删除 PostgreSQL volume；需要保留运行中的服务时使用
`-KeepServices`。脚本默认在 `reports/phase2-verification/run-<timestamp>/` 写入
`transcript.log` 和机器可读的 `summary.json`；summary 同时包含总体状态、命令清单和逐条
命令的开始/结束时间、退出码与状态，以及 `postgres` 和 `otel-collector` 的最终健康状态；
可用 `-EvidenceDir` 指定证据根目录。summary 先写入同目录临时文件，再移动为最终文件，
且拒绝覆盖已有 summary；即使 Docker、健康检查或 contract 失败，也会保留失败状态、健康
状态和已执行命令清单。脚本内的密码仅用于本地验证，不能用于生产环境。

同一实例也可用于应用 runtime。启用全部二期 PostgreSQL 资源时使用精确配置：

```powershell
$pg = "postgresql://shijiajing:change-me-for-local-only@127.0.0.1:5432/shijiajing"
$env:SHIJIAJING_POSTGRES_POOL_MIN_SIZE = "2"
$env:SHIJIAJING_POSTGRES_POOL_MAX_SIZE = "8"
$env:SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS = "12.5"
$env:SHIJIAJING_CHECKPOINT_BACKEND = "postgres"
$env:SHIJIAJING_CHECKPOINT_DSN = $pg
$env:SHIJIAJING_GRAPH_PERSISTENCE_MODE = "native"
$env:SHIJIAJING_REQUEST_LEDGER_BACKEND = "postgres"
$env:SHIJIAJING_REQUEST_LEDGER_DSN = $pg
$env:SHIJIAJING_MEMORY_ENABLED = "true"
$env:SHIJIAJING_MEMORY_BACKEND = "postgres"
$env:SHIJIAJING_MEMORY_DSN = $pg
$env:SHIJIAJING_CACHE_BACKEND = "postgres"
$env:SHIJIAJING_CACHE_DSN = $pg
$env:SHIJIAJING_EVENT_STORE_BACKEND = "postgres"
$env:SHIJIAJING_EVENT_STORE_DSN = $pg
$env:SHIJIAJING_TRACE_BACKEND = "opentelemetry"
$env:SHIJIAJING_TRACE_DSN = "http://127.0.0.1:4318/v1/traces"
uv run shijiajing-preflight --storage-only --json
```

`--storage-only` 只验证资源 setup/close；模型、Milvus 和本地商品快照仍需按根目录
`.env.example` 配置后执行完整 `shijiajing-preflight --json`。

Windows 下 preflight、live 评测、迁移、事件还原、事件修复、Milvus 初始化和商品索引 CLI
会使用 `SelectorEventLoop` 运行 psycopg 异步连接；其他平台保持默认事件循环策略。

## OTLP 验证

启动应用或测试后查看 collector 日志：

```powershell
docker compose --env-file deploy/phase2/.env.example `
  -f deploy/phase2/docker-compose.yml logs otel-collector
```

也可以直接用应用的合成 probe 验证 OTLP HTTP 发送：

```powershell
$env:SHIJIAJING_TRACE_BACKEND = "opentelemetry"
$env:SHIJIAJING_TRACE_DSN = "http://127.0.0.1:4318/v1/traces"
uv run shijiajing-preflight --storage-only --verify-trace --json
```

只有输出 `status=ok` 且 `trace_verified=true` 才算本地 Collector 接收成功；该命令不证明
生产 Collector 的持久化、告警或查询链路。

日志中只能出现脱敏后的 span 属性；不要把完整 prompt、用户文本、DSN、API key 或 data URL
写入日志。应用关闭后再检查一次日志，确认 exporter 已 flush。

`shijiajing-backup-postgres` 会把普通 PostgreSQL 密码从 `pg_dump`/`pg_restore` 命令行移到
子进程 `PGPASSWORD` 环境变量；不要把真实 DSN 写入脚本或日志。该安全解析路径需要
`shijiajing-agent[postgres]`，包含 `sslpassword` 的 DSN 会被拒绝。

## 停止与清理

只停止容器并保留数据库卷：

```powershell
docker compose --env-file deploy/phase2/.env.example `
  -f deploy/phase2/docker-compose.yml down
```

删除本地验证数据库卷是不可逆的开发操作，必须明确执行：

```powershell
docker compose --env-file deploy/phase2/.env.example `
  -f deploy/phase2/docker-compose.yml down --volumes
```

删除卷后，PostgreSQL contract 必须重新执行 setup/migration；本地命令不能替代生产备份、
隔离恢复、active interrupt 清单和正式 OTLP collector 验收。
