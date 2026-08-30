# 配置说明

所有配置通过环境变量（或 `.env`，见下）注入，前缀统一 `SHIJIAJING_`。
**外部地址、Token、Collection、模型标识符和数据路径没有代码默认值**（方案 §13）；
使用真实适配器时缺失会启动失败，并列出精确缺失项。

## 1. 加载方式

```bash
# 方式一：环境变量
export SHIJIAJING_ARK_API_KEY=...

# 方式二：.env 文件（键名必须带前缀，如 SHIJIAJING_ARK_API_KEY=...）
# 示例见仓库根 .env.example，复制后填写即可
```

`shijiajing_agent.config.load_settings()` 读取 `SHIJIAJING_*`；`Settings` 不可变，
`settings.validate(require_real_adapters=True)` 返回缺失项列表。
数值环境变量在解析阶段即以完整的 `SHIJIAJING_*` 字段名报告类型错误；解析成功后再由
`validate_engineering()` 校验有限性、正负范围和跨字段约束。

## 2. 外部资源（无默认值，缺失即失败）

| 环境变量 | 说明 |
|---|---|
| `SHIJIAJING_ARK_API_KEY` | 模型 Provider（OpenAI 兼容）API Key |
| `SHIJIAJING_ARK_BASE_URL` | 模型 Provider Base URL |
| `SHIJIAJING_ARK_VISION_MODEL` | VLM 模型标识符 |
| `SHIJIAJING_ARK_TEXT_MODEL` | 意图/改写/解释共用文本模型标识符 |
| `SHIJIAJING_EMBEDDING_MODEL` | Milvus 混合检索使用的文本向量模型标识符；仅本地词法快照路径不需要 |
| `SHIJIAJING_MILVUS_URI` | Milvus 地址 |
| `SHIJIAJING_MILVUS_TOKEN` | Milvus Token |
| `SHIJIAJING_MILVUS_COLLECTION` | Milvus Collection 名 |
| `SHIJIAJING_CHECKPOINT_BACKEND` | `sqlite` / `postgres` |
| `SHIJIAJING_CHECKPOINT_DSN` | sqlite 文件路径或 postgres DSN |
| `SHIJIAJING_TRACE_BACKEND` | `structlog` 或 `opentelemetry` |
| `SHIJIAJING_TRACE_DSN` | OTLP HTTP endpoint；OpenTelemetry 后端必填 |
| `SHIJIAJING_TAXONOMY_PATH` | taxonomy.json 路径（缺省用包内置文件） |
| `SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH` | 本地商品快照 JSONL（词法降级索引） |

### 检索配置的组合

- **Milvus 三件套齐全**（URI + TOKEN + COLLECTION）→ 走 `MilvusHybridRetrievalAdapter`；
  其本地兜底使用快照（未配置快照时，仅当 Milvus 不可用才报精确错误）。
- **仅本地快照** → 直接使用 `LocalLexicalRetrievalAdapter`（BM25 词法 + 相同硬过滤语义）。
- **两者皆无** → 启动报错并列出缺失项（`make_retrieval` 抛 ValueError）。

## 3. 运行参数（均有方案默认值，可按需覆盖）

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `SHIJIAJING_ENV` | `dev` | 精确环境枚举：`dev` / `test` / `prod` |
| `SHIJIAJING_VISION_TIMEOUT_SECONDS` | 30 | VLM 调用超时 |
| `SHIJIAJING_TEXT_MODEL_TIMEOUT_SECONDS` | 15 | 文本模型调用超时 |
| `SHIJIAJING_RETRIEVAL_TIMEOUT_SECONDS` | 3 | 检索超时 |
| `SHIJIAJING_TURN_TIMEOUT_SECONDS` | 60 | 单轮整体超时 |
| `SHIJIAJING_VISION_CACHE_TTL_SECONDS` | 2592000 | vision 缓存 TTL |
| `SHIJIAJING_INTENT_CACHE_TTL_SECONDS` | 604800 | intent 缓存 TTL |
| `SHIJIAJING_QUERY_REWRITE_CACHE_TTL_SECONDS` | 604800 | query_rewrite 缓存 TTL |
| `SHIJIAJING_RETRIEVAL_CACHE_TTL_SECONDS` | 300 | retrieval 缓存 TTL |
| `SHIJIAJING_EXPLANATION_CACHE_TTL_SECONDS` | 86400 | explanation 缓存 TTL |
| `SHIJIAJING_PRODUCT_CANONICALIZATION_CACHE_TTL_SECONDS` | 604800 | 商品归一化结构化结果缓存 TTL |
| `SHIJIAJING_POSTGRES_POOL_MIN_SIZE` | 1 | PostgreSQL 业务适配器连接池最小连接数 |
| `SHIJIAJING_POSTGRES_POOL_MAX_SIZE` | 4 | PostgreSQL 业务适配器连接池最大连接数 |
| `SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS` | 30 | PostgreSQL 连接池等待连接超时 |
| `SHIJIAJING_MAX_MODEL_REPAIRS` | 2 | 模型结构化输出修复次数 |
| `SHIJIAJING_MAX_NETWORK_ATTEMPTS` | 2 | 网络重试次数 |
| `SHIJIAJING_RETRIEVAL_TOP_K_PER_CHANNEL` | 100 | 每通道 Top-K |
| `SHIJIAJING_RETRIEVAL_UNION_LIMIT` | 200 | 通道合并上限 |
| `SHIJIAJING_MATCHING_CANDIDATE_LIMIT` | 60 | 同款匹配候选上限 |
| `SHIJIAJING_PRODUCT_CANONICALIZATION_ENABLED` | `true` | 是否在聚类前调用 LLM 商品归一化组件 |
| `SHIJIAJING_PRODUCT_CANONICALIZATION_BATCH_SIZE` | 20 | 单次商品归一化模型调用的 Offer 数量 |
| `SHIJIAJING_PRODUCT_CANONICALIZATION_MIN_CONFIDENCE` | 0.75 | 采纳模型字段的最低证据置信度 |
| `SHIJIAJING_BRAND_HARD_FILTER_CONFIDENCE` | 0.85 | 品牌硬过滤最低置信 |
| `SHIJIAJING_MODEL_HARD_FILTER_CONFIDENCE` | 0.90 | 型号硬过滤最低置信 |
| `SHIJIAJING_SAME_ITEM_ACCEPT_THRESHOLD` | 0.82 | 同款接受阈值 |
| `SHIJIAJING_SAME_ITEM_REVIEW_THRESHOLD` | 0.68 | 同款人工复核阈值 |

二期工程化开关：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `SHIJIAJING_REQUEST_LEDGER_BACKEND` | `sqlite`（环境加载） | `disabled` / `sqlite` / `postgres` |
| `SHIJIAJING_REQUEST_LEDGER_DSN` | 空 | 未填写时复用 `SHIJIAJING_CHECKPOINT_DSN` |
| `SHIJIAJING_MEMORY_ENABLED` | `false` | 是否启用跨会话显式记忆 |
| `SHIJIAJING_MEMORY_RECALL_ENABLED` | `true` | 内部灰度开关；是否执行长期记忆 recall |
| `SHIJIAJING_MEMORY_COMMIT_ENABLED` | `true` | 内部灰度开关；是否准备并提交显式记忆变更 |
| `SHIJIAJING_MEMORY_BACKEND` | `disabled` | `disabled` / `sqlite` / `postgres` |
| `SHIJIAJING_MEMORY_DSN` | 空 | Memory SQLite 文件或 PostgreSQL DSN |
| `SHIJIAJING_MEMORY_RECALL_LIMIT` | `20` | 召回并完成 scope 去重后的最大记录数 |
| `SHIJIAJING_RECENT_TURNS_LIMIT` | `6` | 会话摘要最大轮数 |
| `SHIJIAJING_RECENT_TURNS_MAX_BYTES` | `65536` | 会话摘要序列化字节上限 |
| `SHIJIAJING_MEMORY_PURGE_ENABLED` | `false` | 仅受信管理入口可用的物理清除开关 |
| `SHIJIAJING_MEMORY_MUTATION_LEDGER_RETENTION_DAYS` | `90` | 仅 hash ledger 的保留天数 |
| `SHIJIAJING_HITL_ENABLED` | `false` | 是否返回 `AgentTurnResult.interrupt` |
| `SHIJIAJING_RECOGNITION_REVIEW_THRESHOLD` | `0.70` | 低于此识别置信度暂停审核 |
| `SHIJIAJING_MEMORY_CONFIRMATION_REQUIRED` | `true` | 记忆变更提交前暂停确认 |
| `SHIJIAJING_CACHE_BACKEND` | `disabled` | `disabled` / `memory` / `sqlite` / `postgres` |
| `SHIJIAJING_CACHE_DSN` | 空 | Cache SQLite 文件或 PostgreSQL DSN |
| `SHIJIAJING_RETRIEVAL_FUSION_STRATEGY` | `weighted` | `weighted` 或 `rrf` |
| `SHIJIAJING_RETRIEVAL_RERANK_ENABLED` | `false` | 是否启用确定性二阶段重排 |
| `SHIJIAJING_RETRIEVAL_INDEX_VERSION` | 空 | 非空时才启用检索结果缓存 |
| `SHIJIAJING_EVENT_STORE_BACKEND` | `disabled` | `disabled` / `sqlite` / `postgres` |
| `SHIJIAJING_EVENT_STORE_DSN` | 空 | Event Store SQLite 文件或 PostgreSQL DSN |

Supervisor Planner 配置：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `SHIJIAJING_SUPERVISOR_MODEL` | 空 | Planner 专用 Ark 模型标识；不自动复用 `ARK_TEXT_MODEL` |
| `SHIJIAJING_SUPERVISOR_PLANNER_MODE` | `off` | `off` / `shadow` / `active_replan` / `active`；非 `off` 必须显式配置 Supervisor 模型 |
| `SHIJIAJING_SUPERVISOR_PLANNER_TIMEOUT_SECONDS` | 8 | Supervisor Planner 单次调用超时 |
| `SHIJIAJING_SUPERVISOR_PLANNER_MAX_REPAIRS` | 1 | 结构化输出修复最多次数 |
| `SHIJIAJING_SUPERVISOR_PLANNER_MAX_TOKENS` | 1500 | Planner 单次输出 token 上限 |
| `SHIJIAJING_MAX_AGENT_TASKS` | 32 | 单计划任务上限 |
| `SHIJIAJING_MAX_SUPERVISOR_REPLANS` | 2 | 单轮受控 replan 上限 |
| `SHIJIAJING_AGENT_TASK_TIMEOUT_SECONDS` | 30 | 单 Agent task deadline 默认值 |

`shadow` 只校验模型提议并执行确定性计划，`active_replan` 只允许模型参与可恢复失败的
replan，`active` 允许模型参与 create 与 replan。启用模型 Planner 前必须另外提交包含样本数、
计划差异、p50/p95 延迟、token、回退和业务不变量的 Planner shadow 报告。

真实 Planner shadow 报告使用独立 CLI 生成；报告仅保存模型、Prompt 版本、token、延迟、回退原因与
哈希，不保存请求文本、Prompt、任务输入或模型原始响应。输出路径必须不存在，避免覆盖历史证据：

```bash
uv run --env-file .env shijiajing-planner-shadow \
  --dataset src/shijiajing_agent/data/eval/multi_agent_dataset.jsonl \
  --data-version provisional-v1 \
  --output reports/planner-shadow/planner-shadow.json
```

逐案例 `planner_outcome.validated=true` 表示候选计划已通过确定性校验；shadow 模式下
`accepted=false` 与 `fallback_reason=MODEL_PLAN_SHADOWED` 表示候选没有进入业务执行。随后可用
`shijiajing-release-check --planner-shadow-report <report>` 校验报告结构与业务不变量门禁。
Supervisor/task Checkpoint 要求 `SHIJIAJING_CHECKPOINT_DSN`；启用 HITL 时必须确保该
存储可用。Request Ledger 在生产环境应使用持久化后端；
生产 PostgreSQL 适配器来自 `uv sync --extra postgres`。长期记忆只接受白名单键和值域，
普通请求的 `metadata` 不会被当作记忆 owner。

`MEMORY_RECALL_ENABLED` 和 `MEMORY_COMMIT_ENABLED` 只来自部署配置，不接受客户端请求覆盖。
启用 `MEMORY_COMMIT_ENABLED` 时必须同时启用 `MEMORY_RECALL_ENABLED`；两者都不改变
`AgentExecutionContext.memory_enabled` 的调用方权限校验。

上述 PostgreSQL pool 参数作用于 Request Ledger、Memory、Cache 和 Event Store
业务适配器；LangGraph Checkpointer 当前由依赖库 `AsyncPostgresSaver` 使用单个
异步连接，不能通过该三项参数伪装为连接池。连接池最小值必须至少为 1，最大值不能小于
最小值，等待超时必须是有限正数。

所有运行时数值配置在 `Settings.validate_engineering()` 阶段执行范围校验：超时和连接池
等待时间必须是有限正数；模型修复次数和网络尝试次数允许为 `0`，但不得为负数；
检索/匹配/记忆上限以及 RRF 参数必须至少为 `1`；置信度和阈值必须是有限的 `0..1`，
且 `SAME_ITEM_REVIEW_THRESHOLD` 不得大于 `SAME_ITEM_ACCEPT_THRESHOLD`。校验失败返回
精确字段名，启动检查不得静默继续。

六类缓存 TTL 分别对应 `vision`、`intent`、`query_rewrite`、`retrieval`、`explanation` 和
`product_canonicalization`
命名空间，并由对应 Agent 或领域服务从 `Settings` 读取。preflight JSON 的
`cache_ttl_seconds` 显示实际生效值，所有 TTL 必须为至少 `1` 秒。

`SHIJIAJING_ENV=prod` 时，`SHIJIAJING_EVENT_STORE_BACKEND` 不得为 `disabled`，并且
`sqlite`/`postgres` backend 必须提供 `SHIJIAJING_EVENT_STORE_DSN`。`dev` 和 `test`
允许使用 `disabled` 进行本地和单元测试；未知环境值会在工程配置校验中按精确字段报错。

偏好权重表（价格/店铺/评分/销量/发货）默认内置，见
`Settings.preference_weights`；可按环境扩展并在 trace 中透出。

## 4. 缺失配置的行为

- 示例与 `shijiajing-eval --live`：`load_settings_or_exit()` 打印
  `缺少必要配置：SHIJIAJING_ARK_API_KEY, ...` 后退出码 2。
- `make_deps(settings)`：抛 `ValueError("缺少必要配置：...")`。
- 应用层（`AgentFacade`）不产生任何配置默认值——缺失即报错，不做静默降级
  到假数据（样例数据只能通过显式 Fake 端口注入，见 tests/multi_agent/conftest.py）。
### 商品归一化迁移

`PRODUCT_CANONICALIZATION_MODE` 支持 `taxonomy`、`dynamic_shadow`、`hybrid` 和 `dynamic`。
默认值为 `taxonomy`；动态模式使用请求级局部 Schema，Schema 与模型不可用时保守回退到通用
规则基线，不阻断检索。动态阈值、批大小与缓存 TTL 分别由 `DYNAMIC_SCHEMA_*` 和
`DYNAMIC_CANONICALIZATION_*` 配置项控制。动态 Schema 缓存只是性能优化，不是商品事实源。
