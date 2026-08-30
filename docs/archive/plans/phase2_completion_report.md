# 二期工程化升级完成报告（阶段性）

报告日期：2026-08-22  
当前结论：未满足全部 Definition of Done，保持“执行中”。

## 1. 已落地能力

- native LangGraph async Checkpointer：SQLite/PostgreSQL 装配、显式 setup、JSON-safe serializer、legacy 1.0 → 1.1 迁移读取；新增只读预览和显式 `migrate --apply`，事务内写入迁移审计记录并追加 `checkpoint_migrated`，Event Store 失败后可依据审计记录重试，缺少真实审计标识时不伪造事件；已补 native SQLite runtime 重开、Request Ledger 跨 runtime 幂等和 legacy/native 业务结果对照。
- native recovery 运维回归：新增 SQLite native active interrupt 跨 runtime 重开后 resume 测试；PostgreSQL contract 夹具优先读取 `SHIJIAJING_TEST_POSTGRES_DSN`，否则仅在显式 integration 模式且 Docker daemon 可用时自动启动隔离 PostgreSQL 16，环境不足时明确 skip。
- 外部依赖启动路径：新增 `deploy/phase2/docker-compose.yml`、固定 PostgreSQL 16 与 OTLP HTTP Collector，Compose 配置解析通过；未提供 `POSTGRES_PASSWORD` 时以退出码 1 拒绝启动。该资产只用于开发/集成验证，不替代真实 PostgreSQL contract、生产备份或外部 Collector 验收。
- 外部依赖验收编排：新增 `deploy/phase2/verify.ps1`，统一执行 PostgreSQL/Collector 健康检查、严格 integration gate、PostgreSQL 重启后的健康恢复、`--verify-trace`、Collector 日志和服务停止；每次运行使用独立 Compose project name，归档 transcript、机器可读 summary、命令清单、逐条退出结果和最终服务健康状态；Docker daemon 不可用时返回非零，不把基础设施缺失误报为通过。
- Runtime 资源生命周期：Trace sink、Ark 共享模型客户端 owner 和 Retrieval 适配器现在统一经过
  `open_resource()` 注册；Retrieval 退出时按对象身份去重关闭 Embedding、Milvus 客户端和本地兜底
  资源。所有 close 实现幂等，后续 Checkpoint/Memory 等资源 setup 失败时按逆序回收已注册资源，
  并在任何 setup 前先登记已构造的基础资源；最早的 setup 失败也会回收尚未 setup 的资源。
  `make_deps()` 构造阶段也通过 runtime registrar 立即登记 owner，后续构造失败同样回收。
  yield 前的 graph checkpointer enter、业务资源构造、setup 和 Facade 编译统一经过 startup
  error boundary，startup 根因不会被清理异常覆盖；已补正常退出、失败路径、早期失败、
  构造失败和重复 close 回归，避免外部客户端与 OpenTelemetry provider 泄漏。
- Port 生命周期契约：新增 `ports/lifecycle.py` 的同步/异步兼容 `setup()` / `close()` 协议，
  Checkpoint、Request Ledger、Memory、Cache 和 Event Store Port 显式继承该协议；已补结构化
  适配器契约测试，替换实现不能只提供业务方法而遗漏 runtime 生命周期。
- Retrieval/Trace 生命周期契约：`ProductRetrievalPort` 与 `TraceSinkPort` 也显式继承统一
  生命周期协议；Milvus、本地检索、structlog、OpenTelemetry 和 live 评测计数包装器均提供
  setup/close，OpenTelemetry close 幂等；已补实际适配器结构化契约测试。
- Vision owner 生命周期契约：runtime 注册的 `VisionModelPort` 显式继承统一生命周期协议；
  Ark Vision 适配器和 live 评测计数包装器委托 setup/close，避免共享 Ark 客户端 owner 在
  类型层遗漏资源管理；已补实际 owner 与包装器契约测试。
- 依赖容器类型边界：`AgentDependencies` 已将 Settings、Checkpoint、Request Ledger、Memory、
  Cache、Event Store 和业务 Port 改为显式类型；LangGraph graph checkpointer 现使用
  `BaseCheckpointSaver[str]`，仅在第三方 builder 未参数化 stub 的装配点保留局部 `Any` cast；
  Pyright strict 可直接检查替换适配器的接口一致性。
- 节点依赖协议：新增 `ports/dependencies.py` 的 `AgentDependenciesPort`，节点、子图和根图
  不再用 `Any` 接收业务依赖；该协议只暴露实际使用的固定字段，并由结构化类型连接到
  `AgentDependencies`，Pyright strict 已验证全链路兼容。
- 缓存策略边界：`domain/cache_policy.py` 的 `safe_get`、`safe_set` 和
  `safe_delete_namespace` 现在显式接收 `VersionedCachePort` / `MetricsPort`；仅缓存载荷和
  版本键保留动态数据类型，避免缓存故障降级路径重新引入 `Any` 依赖边界。
- 适配器指标边界：Ark 模型、Milvus 混合检索和本地词法检索适配器的指标注入已改为显式
  `MetricsPort`，避免生产装配已创建的指标实例在适配器边界被动态类型掩盖；相关契约测试和
  Pyright 检查通过。
- live 评测 Port 边界：`CountedVision`、`CountedIntent`、`CountedQueryRewrite` 和
  `CountedRetrieval` 包装器已改用生产 Port 的精确输入输出类型，Gold catalog、运行清单的
  `Settings`/`Taxonomy` 依赖也已显式化；计数逻辑保持 evaluation-only。
- Runtime 类型边界：资源注册、setup 和 close 辅助函数现在以 `ResourceLifecyclePort` 泛型
  保留具体资源类型，第三方 LangGraph graph checkpointer 仍走独立 context-manager 边界；
  已补齐测试替身生命周期契约并通过 runtime 回归。
- Native graph 输入边界：新增 `NativeTurnInput` TypedDict，并将根图编译为
  `NativeTurnInput → AgentState`；新 turn 只提交明确的本轮增量，跨轮识别/约束/主题/会话摘要
  继续由 checkpointer 保留，避免完整 `AgentState` 输入造成语义覆盖。
- 状态字段契约：`image_ref`、`evidence_bundle` 和 `same_item_review_pairs` 已分别收紧为
  `ImageRef`、`EvidenceBundle` 和 `MatchPair`；SQLite 恢复会重建 `MatchPair`，HITL 入口只对
  历史兼容字典执行一次 `model_validate`。
- 运维 CLI 类型边界：`run_eval` 的 live 配置显式使用 `Settings`，benchmark 报告提交显式使用
  `BenchmarkReport`；仅跨十一类异构评测数据集的载荷入口保留 `list[Any]`，避免动态类型扩散到
  配置和报告契约。
- 本地检索配置边界：仅配置 `SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH` 时不再强制要求
  `SHIJIAJING_EMBEDDING_MODEL`；只有完整 Milvus 三件套启用时才要求 embedding model，
  已补两条配置分支回归。
- Memory 标识约束：`memory_id`/`mutation_id` 现在由公共契约强制为 64 位小写 SHA-256；
  repair 对契约收紧前历史库中的非十六进制 mutation_id 使用稳定哈希兼容，不改变合法 ID 的
  既有事件 ID。
- Trace replay 幂等：同一 `(session_id, turn_id)` 重复收到 `turn_started` 时保留原 root/agent
  span，不覆盖并遗失旧 span；已补重复生命周期事件回归。
- Memory adapter 边界：SQLite/PostgreSQL `commit()` 现在再次执行固定 `memory_key` 白名单和值域
  规范化；绕过节点直接提交未知键或自由 JSON 时在落库前拒绝，已补 SQLite 边界回归。
- Memory runtime 边界：legacy `start()` 收到 `memory_enabled=true` 时明确返回配置失败，避免
  在没有 native thread persistence 的路径上静默跳过长期记忆。
- Memory 灰度发布边界：新增 `SHIJIAJING_MEMORY_RECALL_ENABLED` 与
  `SHIJIAJING_MEMORY_COMMIT_ENABLED` 私有部署开关，支持先执行 recall、观察后再执行
  prepare/commit；commit 开启而 recall 关闭会被工程配置拒绝，客户端上下文不能覆盖这两个开关。
- Rollout preflight 审计：机器可读 preflight 结果现在同时输出 HITL、Memory confirmation、
  Retrieval fusion/rerank/index version 等实际生效开关，避免只校验资源 setup 而无法确认灰度配置。
- Facade 失败协议：legacy `run()` 的 Request Ledger 写入失败现在与 native `start()` 一致，返回
  类型化 `REQUEST_LEDGER_UNAVAILABLE` 失败响应，不向调用方泄漏未处理异常。
- Request Ledger 完整性：SQLite/PostgreSQL 读取响应时校验持久化 `response_hash`，摘要不一致
  即按账本不可用拒绝返回，已补 SQLite 篡改回归。
- Checkpoint/Cache 脱敏边界：legacy SQLite 与 LangGraph native serializer 统一清洗原始请求、
  correction、metadata、图片 URI 和会话摘要文本；图片只保留摘要与不可访问占位引用，Cache
  适配器拒绝自由 `text`/`prompt` 字段，解释缓存只接受通过事实校验的
  `explanation_text` 字段；已补 legacy/native 实际存取回归。
- Event payload 脱敏边界：`AgentEventRecord` 递归拒绝凭证、DSN、原始文本/Prompt、图片 data URL
  和模型原始输出字段，事件白名单由公共契约强制执行，已补嵌套敏感 payload 回归。
- 诊断字段边界：Milvus 降级原因及识别/检索/同款匹配错误不再把底层异常字符串写入状态，
  只保留固定错误码与用户可操作消息，避免 host/DSN/供应商响应进入 Checkpoint。
- 配置边界：`SHIJIAJING_CHECKPOINT_DSN` 现在在 legacy/native 两种 Checkpoint 模式下都由工程配置校验统一要求；Fake `deps_factory` 仅用于测试和示例，保持不依赖生产 DSN。
- PostgreSQL 备份安全边界：`pg_dump` 临时归档在 `pg_restore --list` 校验成功后才替换目标；校验失败保留已有 dump 并清理 staging，已补失败路径契约测试。普通数据库密码从 client-tool 命令行移到子进程 `PGPASSWORD` 环境变量，`sslpassword` 直接拒绝；生产备份存储与主机 client tools 仍需外部 PostgreSQL 环境。
- PostgreSQL 本地恢复演练：`verify.ps1 -VerifyBackupRestore` 使用 PostgreSQL 16 容器内的
  `pg_dump`/`pg_restore` 生成 custom-format dump，执行归档列表校验并恢复到隔离库；本次源库和
  恢复库均有 10 个 public 表，固定哨兵数据恢复 1 行，隔离恢复库已清理。生产备份存储、
  加密、保留、权限、跨区域恢复和主机 client tools 仍需外部验收。
- OTLP probe：新增 `shijiajing-preflight --storage-only --verify-trace --json`，发送固定合成 turn span 并把 exporter 非成功结果转为退出码 2；已在本地 Compose OTLP Collector 上完成真实接收验证，生产 Collector 的持久化、告警和查询链路仍需外部验收。
- preflight 失败边界：`shijiajing-preflight --json` 只保留精确配置缺失项或固定资源错误消息，不把 provider 异常、主机、DSN 或密钥原文输出到 CLI。
- 运维 CLI 错误边界：迁移、事件修复和事件还原命令复用同一公开错误工具；领域异常保留可操作用户消息，其他外部异常统一降级，不输出 provider、主机、DSN 或密钥。
- 生产发布证据门禁：新增 `shijiajing-release-check`，严格校验本地 verification/backup summary、正式评测阻断列表、正式性能策略/阈值/实际 p95、主机 client tools 和带 SHA-256 的生产外部证据 manifest；新增 `create-manifest` 子命令自动计算摘要、拒绝目录穿越和覆盖；缺少证据返回未就绪，不把本地通过推断为生产发布通过。
- 评测报告防伪通过边界：`eval_report.json` 新增 schema 和完整 threshold 元数据；发布门禁现在
  校验十一类数据集摘要、所有阻断指标、代码定义阈值、`passed`/blocking 列表与 gate 派生字段
  的一致性。`benchmark_report.json` 通过完整 `BenchmarkReport` 校验，并要求三种策略均存在，
  防止仅凭少量布尔字段伪造正式评测或性能通过。
- 生产证据契约：`postgres_ha`、`backup_storage`、`otel_collector` 的证据文件现在必须声明精确的 `check_id`、`prod` 环境、UTC 验证时间和完整 claims 集合，生成器与发布门禁共享校验逻辑；不完整或错配的外部证据不能仅凭文件摘要进入发布门禁。
- 验收证据完整性：verification 门禁拒绝含失败命令的 summary；PostgreSQL backup/restore 门禁同时校验 summary 证据目录内的非空 dump 和独立 token 形式的成功 `pg_dump`/`pg_restore` 命令记录；`verify.ps1` 的 summary 通过同目录临时文件原子提交并拒绝覆盖；全部运维 CLI 复用共享 UTF-8 输出配置，避免 Windows 门禁原因乱码。
- Windows 异步运行时边界：测试 hook、preflight、live 评测、迁移、事件还原、事件修复、Milvus 初始化、商品索引 CLI 和三个示例脚本在 Windows 使用 `SelectorEventLoop`，兼容 `psycopg` 异步连接；其他平台保持默认事件循环行为。
- 配置解析边界：数值环境变量解析失败时保留精确的 `SHIJIAJING_*` 字段名，preflight 的安全错误边界不会把字段错误降级为通用消息；解析成功后仍由 `validate_engineering()` 执行有限性、范围和跨字段校验。
- PostgreSQL 连接池配置：新增 `SHIJIAJING_POSTGRES_POOL_MIN_SIZE`、
  `SHIJIAJING_POSTGRES_POOL_MAX_SIZE` 和 `SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS`，
  统一传递到 Checkpoint、Request Ledger、Memory、Cache 和 Event Store 业务适配器；
  配置范围在工程校验阶段拒绝。native LangGraph saver 受依赖库 API 限制保持单个异步连接，
  不把该路径伪装成连接池。
- `Settings.validate_engineering()` 已覆盖全部运行时超时、重试次数、工作流/检索/
  匹配/记忆上限、置信度和阈值：拒绝非有限数、非法边界和同款复核阈值高于接受阈值；
  `MAX_MODEL_REPAIRS` 与 `MAX_NETWORK_ATTEMPTS` 明确允许配置为 `0`。
- 五类缓存 TTL 已从节点硬编码提取到 `Settings`，通过对应的
  `SHIJIAJING_*_CACHE_TTL_SECONDS` 配置加载并执行至少 `1` 秒校验；preflight 的
  `cache_ttl_seconds` 输出实际生效值，vision/intent/query_rewrite/retrieval/explanation
  节点均从同一配置读取。
- `MATCHING_CANDIDATE_LIMIT` 现在在检索重排结果进入同款匹配前生效；标准化阶段按该上限
  截断候选并记录可审计 notice，避免配置存在但同款候选仍无限进入配对和聚类。
- SQLite 多资源恢复回归：checkpoint、Request Ledger、Memory、Cache、Event Store 分别经过
  SQLite backup API 的隔离 backup/restore 后，native active interrupt 可继续 resume，
  Memory/Event Store 数据可读，重复 request 命中恢复后的 Ledger；`backup`、`restore`、
  `verify` 对已存在目标的覆盖保护均有回归测试。
- InMemory 适配器语义对齐：Event Store、Request Ledger、Cache 均改为写入快照和读取副本，
  Event Store 与 SQLite/PostgreSQL 使用相同的事件类型优先级稳定排序规则，已补可变引用与
  同时间戳生命周期顺序回归。
- Request Ledger：SQLite/PostgreSQL/InMemory，`session_id + request_id` 幂等和冲突校验。
- 三层记忆边界：AgentState 工作记忆、bounded recent turns、按可信 `memory_owner_id` 隔离的长期 Memory；白名单值域、覆盖、遗忘、mutation 幂等和事件补写。
- Supervisor 根图：Recognition/Intent 分支并行，`join_understanding` barrier 后再进入 Memory/约束合并；五个专业子图入口可独立装配。
- HITL：clarification、recognition review、same-item review、memory confirmation 四类 typed resume；native `start/resume`、重复 resume 拒绝。
- HITL 完善：recognition review 对缺少 category、未解析字段和低置信度均会触发；编辑会清除/规范化字段；resume 严格校验 session/request/interrupt/execution context；live 评测通过受 runtime 管理的依赖执行。
- Cache：vision、intent、query rewrite、retrieval、explanation 五类版本感知 wrapper；
  Cache 失败按 miss 处理并增加 `cache_failure_total`，载荷读取后分别执行 Pydantic、
  检索硬过滤和解释事实一致性校验；损坏缓存不会直接改变业务结果。
- Memory 并发：PostgreSQL commit 增加 owner 级事务 advisory lock，避免跨连接 replay 的重复应用；新增 SQLite 并发 Event Store 幂等回归。
- Retrieval：weighted 基线、RRF、确定性 rerank、index/fusion/rerank 版本进入 key。
- 工程评测夹具：新增 memory、multi-agent、interrupt、cache 四类严格行模型和种子数据；离线报告纳入工程数据集摘要，但不把工程夹具计入商品质量门禁。策略比较夹具可由 live RetrievalResult 重建真实通道顺序，且保留 Gold 期望字段和行级审计 meta；缺少外部 Gold catalog 映射直接失败，不从 Offer source key 回退。
- 工程评测执行：`shijiajing-eval` 已实际执行四类夹具，使用 SQLite Memory、内存 Cache 和四类专用 resume 模型，当前种子结果为 2/2、2/2、4/4、2/2 全部通过。
- 固定不变量证据：工程报告已按 §15.7 输出六项不变量的样本数、违规数和证据来源；当前本地夹具/结构化投影的六项违规数均为 0，缺少样本时报告状态为待测，不会自动通过。
- 性能基线与门禁：`shijiajing-benchmark` 使用 2 条 seed retrieval 样本、warmup 5、iterations 30 实测 weighted/RRF/weighted+rerank；当前 `reports/benchmark_report.json`（Windows/Python 3.12.13）的 p95 分别为 0.0226ms、0.0099ms、0.1313ms。默认 seed/offline 运行禁止进入门禁；新增显式 `source=formal` + `max-p95-ms` 的机器可读延迟门禁路径，并强制校验 frozen manifest、文件摘要、非空 `retrieval_strategy_dataset.jsonl`、策略行的 `meta.label_source=adjudicated` 以及每个候选的 Gold SPU/SKU 映射，但尚未用正式数据执行。
- 评测晋级保护：新增 `shijiajing-build-eval freeze`，严格校验仲裁记录的 dataset_id/version、全量 `adjudicated` 标签、至少两个不同仲裁人，并拒绝覆盖已有输出目录；冻结结果写入 `adjudication_record.json`，重新计算包含该记录的 manifest 文件摘要，并标记为 `frozen`/`gate_eligible=true`。该路径已有模拟数据的 CLI 回归，但当前仓库仍没有正式人工仲裁数据。
- frozen 发布门禁复核：`shijiajing-eval --frozen` 现在再次要求 `label_method=adjudicated`，并只有完整阻断门禁通过时才写 `frozen_eval_report.md`；非仲裁或指标失败均不会生成冻结报告。
- frozen 报告失效语义：每次 `--frozen` 运行先删除旧的 `frozen_eval_report.md`，成功时经同目录临时文件原子替换；失败运行不会留下可误用的陈旧或半截冻结报告。
- 发布门禁字段一致性：`release_gate_eligible` 同时要求 frozen、adjudicated 和 manifest 的 `gate_eligible=true`；即使已测指标通过，只要任一阻断指标 pending，`release_gate_passed` 仍为 false。
- 评测报告失效语义：每次运行先清除已知的 `eval_report.*`、`engineering_eval_report.*` 和 `retrieval_strategy_comparison.*` 旧产物，再把本次报告全部写入同目录 staging 后提交；缺少可选策略数据时不会残留旧对比结果。
- 延迟报告失效语义：`shijiajing-benchmark` 每次运行先清除旧的 `benchmark_report.{json,md}`；新报告先写入 staging 后提交，配置或写入失败不会保留可误读的旧门禁结果。
- live 输出保护：`--output-datasets-dir`/deprecated `--freeze-dir` 拒绝覆盖已有目录，数据文件和 `run_manifest.json` 在同一 staging 目录完整写入后才提交；序列化或 manifest 写入失败会清理 staging。
- live CLI 失败语义：适配器或 runtime 的非中断执行异常统一转为退出码 2，错误类型和消息写入 stderr，不把未处理 traceback 暴露为命令协议。
- Retrieval 对比：新增共享候选/通道排序夹具，实际运行 weighted、RRF、weighted+rerank 三组策略；当前种子三组 SKU/SPU Recall、MRR 和硬过滤满足率均为 1，违规数为 0，推荐默认仍为 weighted。
- Event/Trace：SQLite/PostgreSQL Event Store、稳定 `event_id`、一致性事件和 repair CLI；structlog 与脱敏 OpenTelemetry/OTLP HTTP sink；legacy/native 统一 turn、agent、model、retrieval、cache、memory、checkpoint、request-ledger 和终态投影；模型节点投影实际 prompt/taxonomy 版本，检索节点投影 index/fusion/rerank 版本，并将 token usage 以数值属性投影；native HITL 追加 `agent_interrupted` / `agent_resumed`，Memory recall 追加 `memory_recalled`，五类版本缓存追加 `cache_hit` / `cache_miss`；OTLP Trace ID 由业务 `trace_id` 稳定派生，已补跨 sink 重启连续性回归；exporter 返回 `SpanExportResult.FAILURE` 时会进入既有 `trace_sink_failure_total` 捕获路径。
- Event Store 只读还原：`shijiajing-reconstruct-turn` 按 `session_id` + `turn_id` 读取事件，严格校验 `request_id` / `trace_id` 一致性，输出有序节点、版本元数据和终态；不写数据库、不伪造标识。
- 存储运维 runbook：按方案补齐独立的 `docs/operations/state_migration.md` 与
  `docs/operations/event_repair.md`，分别固定 legacy Checkpoint 迁移、审计补发、事件
  修复的 dry-run/apply、冲突、回滚和证据边界；`docs/operations_phase2.md` 作为总入口索引。
- 方案引用一致性：清理 README、配置、架构、契约、工作流、评测和排障文档中指向已不存在
  的 §23–§25、§22.3、§13.7 章节引用，改为当前二期方案章节或文档内的明确描述，并加入静态
  契约测试防止旧编号回归。
- 指标装配闭环：生产 `make_deps()` 现在先创建唯一 `MetricsPort`，并将同一实例注入 Ark
  模型、Milvus/本地检索适配器和 `AgentDependencies`；检索降级与模型调用指标不再因装配时
  `metrics=None` 而静默丢失，补充了两种检索装配的 identity 回归。
- native HITL resume fence：Checkpoint 数据库新增 `agent_resume_claim` 唯一键表，按
  `(session_id, interrupt_id)` 原子抢占，跨进程重复恢复在进入 Graph 前拒绝；native
  runtime 启动阶段完成 fence setup，resume 在 Graph 未完成时遇到异常或取消会释放未完成
  claim 以支持重试；SQLite
  已有并发幂等/释放回归，PostgreSQL contract 已接入；`interrupt_generation` 持久化并
  纳入 interrupt ID，覆盖同一 turn 内重复同类 clarification 的恢复回归。
- native thread turn boundary：同一 session 的新请求显式重置本轮工作结果和事件历史，
  保留有效约束、识别历史、subject 与 recent turns，并新增回归防止上一轮响应、候选和查询泄漏。
- bounded conversation memory 解耦：`recent_turns` 在长期 Memory 关闭时仍由 native/legacy
  终态路径追加，legacy 下一轮会恢复上一轮摘要；`FAILED` 终态也进入摘要，已补双路径回归。
- native failure durability：图 timeout/内部异常的 FAILED response 在 Request Ledger 已装配
  时写入 Ledger，并尝试保存包含错误与 `recent_turns` 的 native checkpoint；已补失败重放只
  执行一次的回归。
- native completed replay：Request Ledger 未装配时，同一 thread 仍通过 checkpoint 对已完成
  `request_id` 直接返回 terminal response，避免重复执行图；Ledger 已装配但记录缺失时会先
  补写 Ledger，并追加 `request_ledger_repaired` 事件及 `request_ledger_repair_total` 指标；
  已补 Ledger 短暂失败后的修复回归。
- Multi-Agent lifecycle：节点投影已为 Recognition、Intent、Retrieval、Explanation、Memory
  追加稳定幂等的 `agent_started` / `agent_completed` / `agent_failed` 事件，并与 supervisor
  turn 生命周期分离；已补 HITL 事件序列回归。
- Multi-Agent subgraph execution：根图已实际装配 Recognition、Intent、Retrieval、Explanation
  子图；Memory 子图在根图中以 recall/prepare 边界接入，确认中断和最终 commit 仍保持根图时序。
  新增独立子图执行回归，覆盖五个 `build_*_subgraph()` 入口及根图节点装配；新增五类
  Pydantic 输出契约，校验嵌套领域对象和未知字段。
- Multi-Agent boundary failure：子图输出契约校验失败会标记对应的 `*_subgraph` 入口，
  native/legacy 异常路径可继续投影成成对的子 Agent `agent_started` / `agent_failed` 事件，
  不会无事件退出。
- native active interrupt replay：相同 `request_id` 的重复 `start()` 原样返回已有 interrupt，
  不同 request 不得覆盖待恢复 turn；已补内存 Checkpointer 与 SQLite 跨 runtime 回归。
- native Facade 异常映射：持锁后的 Request Ledger 读取失败、resume checkpoint 读取失败、
  resume Ledger 写入失败和 resume timeout 均返回对应的可操作失败响应；timeout 会释放未完成
  resume claim，避免把可重试故障误报成内部错误或悬挂恢复凭证。
- 用户修正：`apply_correction` 现在实际写回识别字段、属性和清除字段，随后执行 taxonomy normalization，且不调用 VLM。
- README 承诺的文本、图片和用户修正示例已补齐；修正示例验证二次请求不再调用 VLM。

## 2. 实测门禁

| 命令 | 结果 |
|---|---|
| `uv sync --all-extras --locked` | 退出码 0；锁定环境 80 packages |
| `uv run ruff check src tests examples` | 退出码 0 |
| `uv run ruff format --check src tests examples` | 退出码 0；158 files already formatted |
| `uv run pyright` | 退出码 0；0 errors / 0 warnings / 0 informations |
| `uv run pytest -q` | 退出码 0；505 passed，14 deselected（integration 默认排除） |
| `uv run shijiajing-eval --no-gate --report-dir reports` | 退出码 0；已测阻断指标达标，但可信等级 provisional、发布门禁资格不具备；同时生成工程夹具和召回策略对比报告 |
| `uv run shijiajing-benchmark --report-dir reports --warmup 5 --iterations 30` | 退出码 0；生成 `reports/benchmark_report.{json,md}`，记录三组 Retrieval 策略的本机 p50/p95/p99 |
| `uv run shijiajing-benchmark --max-p95-ms 100 --report-dir reports` | 退出码 2；默认 `seed_offline` 明确拒绝性能阈值，必须显式声明 `source=formal` |
| `uv run shijiajing-release-check --verification-summary ... --backup-summary ... --eval-report reports/eval_report.json --benchmark-report reports/benchmark_report.json --json` | 退出码 1；本地 verification 与 backup/restore 通过，但正式评测、正式性能门禁、主机 client tools 和生产外部证据 manifest 未就绪，未误报发布通过 |
| `shijiajing-backup-postgres` | CLI help 退出码 0；新增 7 项命令契约测试，覆盖 DSN 密码不进入命令行、`sslpassword` 拒绝和归档失败路径；真实 `pg_dump`/`pg_restore` 工具缺失时返回明确配置错误 |
| `shijiajing-build-eval freeze` | 已通过模拟数据 CLI 回归；写入 `adjudication_record.json`，staging 成功后提交，不改变源目录、不覆盖已有输出，并只允许全量 `adjudicated` 数据集晋级 |
| `reports/engineering_eval_report.md` | 4 类工程夹具实际执行通过：memory 2/2、multi_agent 2/2、interrupt 4/4、cache 2/2 |
| `reports/retrieval_strategy_comparison.md` | weighted、rrf、weighted_rerank 各 2 条；硬过滤违规 0；推荐保持 weighted |
| `uv run shijiajing-migrate-state inspect` | 退出码 0；未配置 `SHIJIAJING_CHECKPOINT_DSN`，安全 no-op |
| `uv run shijiajing-migrate-state validate` | 退出码 0；未配置 `SHIJIAJING_CHECKPOINT_DSN`，安全 no-op |
| `uv run shijiajing-repair-events --dry-run` | 退出码 0；未配置 `SHIJIAJING_EVENT_STORE_DSN`，安全 no-op |
| `SHIJIAJING_MEMORY_ENABLED=true SHIJIAJING_MEMORY_RECALL_ENABLED=true SHIJIAJING_MEMORY_COMMIT_ENABLED=false uv run shijiajing-preflight --storage-only --json` | 退出码 0；真实 SQLite setup/close 通过，输出 recall `true`、commit `false`，未执行 Memory 写入 |
| `SHIJIAJING_GRAPH_PERSISTENCE_MODE=native ... uv run shijiajing-preflight --storage-only --json` | 退出码 0；临时 SQLite/native 配置成功 setup/close，检查 checkpoint、native checkpointer、Request Ledger 和 Trace |
| `SHIJIAJING_TRACE_BACKEND=opentelemetry ... uv run shijiajing-preflight --storage-only --verify-trace --json` | 退出码 2；临时 endpoint `http://127.0.0.1:9/v1/traces` 不可达时 exporter 失败被严格识别，未误报成功 |
| `uv run shijiajing-preflight --json` | 退出码 2；机器可读地列出缺失的模型、checkpoint、Milvus 和本地商品快照配置，未伪造资源可用性 |
| `docker compose --env-file deploy/phase2/.env.example -f deploy/phase2/docker-compose.yml config` | 退出码 0；PostgreSQL 16、OTLP HTTP/GRPC 端口和只读 Collector 配置挂载解析成功 |
| `docker compose -f deploy/phase2/docker-compose.yml config` | 退出码 1；缺少 `POSTGRES_PASSWORD` 时明确拒绝配置，未使用隐式数据库密码 |
| `pwsh -NoProfile -File deploy/phase2/verify.ps1 -HealthTimeoutSeconds 120` | 退出码 0；证据目录 `reports/phase2-verification/run-20260822-115908-020/`，PostgreSQL/Collector 均 healthy；native Checkpointer 2、Request Ledger 2、Memory 2、Cache 1、Event Store 1，共 8 个真实 PostgreSQL contract 测试通过；PostgreSQL 重启后健康检查通过；preflight `trace_verified=true`，Collector 日志收到 3 spans |
| `pwsh -NoProfile -File deploy/phase2/verify.ps1 -VerifyBackupRestore -HealthTimeoutSeconds 120` | 退出码 0；证据目录 `reports/phase2-verification/run-20260822-120647-895/`；容器内 custom dump 生成并通过 `pg_restore --list`，恢复到 `phase2_restore` 后 public 表数量为 10 对 10，固定哨兵数据为 1 行，恢复库已清理 |
| `$env:SHIJIAJING_POSTGRES_POOL_MIN_SIZE=2; $env:SHIJIAJING_POSTGRES_POOL_MAX_SIZE=8; $env:SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS=12.5; pwsh -NoProfile -File deploy/phase2/verify.ps1 -HealthTimeoutSeconds 120` | 退出码 0；证据目录 `reports/phase2-verification/run-20260822-122827-512/summary.json` 明确记录 pool `2/8/12.5`，PostgreSQL/Collector healthy，8 个 PostgreSQL contract、重启恢复和 OTLP preflight 通过 |
| `pwsh -NoProfile -File deploy/phase2/verify.ps1 -HealthTimeoutSeconds 1` | 退出码 1；Docker/健康检查或 contract 失败时执行清理并归档失败 summary，不进入伪造的 integration/probe 成功路径 |
| `$env:SHIJIAJING_REQUIRE_POSTGRES=1; uv run pytest -q -m integration --maxfail=1` | 严格开关会把外部依赖缺失从 skip 提升为失败；具备 Docker Engine 时由 contract fixture 自动启动隔离 PostgreSQL，完整 Compose/OTLP 验收使用上一行 verify.ps1 |
| `uv run shijiajing-reconstruct-turn --dsn <sqlite> --session-id <id> --turn-id <id> --json` | 退出码 0；SQLite 事件还原测试通过，命令只读并输出 trace_id、节点、版本和终态 |
| `uv run pytest -q -m integration` | 退出码 0；当前 Docker 可用时 8 passed、6 skipped、505 deselected；真实 PostgreSQL/OTLP 端到端证据使用上一行 verify.ps1 |
| `git diff --check` | 退出码 0 |

本次已使用 Docker Desktop Linux daemon 启动 PostgreSQL 16 与 OTLP Collector：真实 PostgreSQL setup、事务契约、PostgreSQL 重启后的健康恢复、五组 contract（共 8 个测试）和 OTLP 合成 probe 均通过；证据归档于 `reports/phase2-verification/run-20260822-115908-020/summary.json`，Collector 日志记录收到 3 个 spans。另一次带 `-VerifyBackupRestore` 的演练已生成并校验 custom dump，恢复库 public 表数量为 10 对 10，哨兵数据为 1 行，证据归档于 `reports/phase2-verification/run-20260822-120647-895/summary.json`。本次额外使用 pool `2/8/12.5` 配置完成真实 preflight、contract、重启恢复和 OTLP 验收，证据归档于 `reports/phase2-verification/run-20260822-122827-512/summary.json`。主机仍未安装 `pg_dump`/`pg_restore`，因此主机上的 `shijiajing-backup-postgres` 命令契约尚未执行真实 client tools；正式生产 PostgreSQL 高可用/故障切换、生产备份恢复、生产 OTLP Collector 的持久化/告警/查询链路仍需外部环境验收。

## 3. 仍未完成的 DoD

1. 本地 Docker PostgreSQL setup、事务、重启后的健康恢复、五组 contract 和可配置业务连接池已完成；生产 PostgreSQL 的高可用、连接池容量压测、故障切换和真实业务数据恢复演练仍未完成。
2. 本地 OTLP Collector 接收已完成；生产 Collector 的持久化、告警、查询、权限和保留策略仍需外部观测系统验证。
3. 正式线上评测数据、人工标注冻结报告和真实商品数据性能实测尚未具备；延迟门禁代码路径已实现，但尚未用正式数据执行。当前商品质量评测仍是 seed/offline provisional。工程夹具已接入独立执行报告，但尚未作为商品发布门禁指标。
4. SQLite backup API 工具、隔离数据库恢复和完整性校验已有自动化演练；本地 PostgreSQL 容器已完成 custom dump、归档校验和隔离恢复；`shijiajing-backup-postgres` 的真实主机 client tools、生产 SQLite 文件、生产 PostgreSQL dump/restore、备份存储策略和跨区域恢复仍未完成。
5. 默认 feature flags 仍为 `legacy`、`memory disabled`、`hitl disabled`、`cache disabled`、`weighted`；没有实测证据前不切换默认值。

## 4. 下一步执行顺序

1. 已完成 Docker Compose PostgreSQL/OTLP 验收；后续保留 `verify.ps1` 作为 CI/预发布重复验收入口。
2. 在具备 PostgreSQL client tools 的环境执行 `shijiajing-backup-postgres backup/verify/restore`，并在生产备份存储上完成加密、保留、权限、跨区域恢复和 repair 演练。
3. 在生产 OTLP Collector 上验证持久化、告警、查询、权限和保留策略；在生产 PostgreSQL 上执行高可用与真实数据恢复演练。
4. 导入正式标注数据，运行 `shijiajing-eval --live --output-datasets-dir <dir>`，完成人工仲裁后用 `shijiajing-build-eval freeze` 晋级，再依据 frozen 报告决定是否调整默认融合/缓存开关。
