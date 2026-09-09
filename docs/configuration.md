# 配置说明

所有部署配置通过环境变量（或 `.env`）注入，变量前缀统一为
`SHIJIAJING_`。算法参数有代码默认值；外部地址、凭据、模型标识和商品数据路径没有
代码默认值，使用真实装配时缺失会被明确报告。

## 1. 加载与启动校验

```bash
cp .env.example .env
# 填写 .env 后由 CLI 或部署入口加载
```

`shijiajing_agent.config.load_settings()` 负责读取和类型转换，`Settings` 是不可变配置。
`make_deps()` 依次执行：

1. `validate(require_real_adapters=True)` 检查外部资源和主 Agent 模型；
2. `validate_engineering()` 检查枚举、范围、DSN 以及跨字段约束；
3. 通过后才创建真实模型、检索和持久化适配器。

解析错误会指出完整变量名，例如 `SHIJIAJING_TURN_TIMEOUT_SECONDS` 必须是数字。缺失配置
会以 `缺少必要配置：...` 失败，退出码为 2；不会静默装配样例数据。

## 2. 外部资源

| 变量 | 说明 |
|---|---|
| `SHIJIAJING_ARK_API_KEY` | Ark/OpenAI-compatible API Key |
| `SHIJIAJING_ARK_BASE_URL` | 模型服务 Base URL |
| `SHIJIAJING_ARK_VISION_MODEL` | 图片识别模型 |
| `SHIJIAJING_ARK_TEXT_MODEL` | 意图、查询改写和解释模型 |
| `SHIJIAJING_EMBEDDING_MODEL` | Milvus 文本向量模型；仅本地词法快照时可不填 |
| `SHIJIAJING_MILVUS_URI` / `TOKEN` / `COLLECTION` | Milvus 连接和集合；三项必须同时提供 |
| `SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH` | 本地 Offer JSONL；Milvus 不可用时也可作为降级路径 |
| `SHIJIAJING_CHECKPOINT_BACKEND` / `CHECKPOINT_DSN` | `sqlite` 或 `postgres` 的 runtime checkpoint |
| `SHIJIAJING_MAIN_AGENT_MODEL` | 主 Agent 模型，真实装配必填 |
| `SHIJIAJING_SUBAGENT_MODEL` | 子 Agent 模型；为空时沿用主 Agent 模型 |
| `SHIJIAJING_TRACE_BACKEND` / `TRACE_DSN` | `structlog` 或 `opentelemetry`；后者需要 OTLP endpoint |
| `SHIJIAJING_TAXONOMY_PATH` | taxonomy 文件；为空时使用包内置版本 |

检索配置二选一：Milvus 三项齐全时使用混合检索，本地快照存在时可直接使用词法检索；两者
均未提供则启动失败。Milvus 路径仍应配置本地快照，作为明确的本地降级来源。

## 3. 主/子 Agent 预算与运行参数

生产只有 `AgentFacade → MainAgentRuntime` 一条执行链。配置只限制资源，不选择 Workflow、
Planner 或其他执行模式。

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `SHIJIAJING_MAIN_AGENT_MAX_DECISIONS` | 8 | 主 Agent 决策轮数 |
| `SHIJIAJING_MAIN_AGENT_MAX_TOOL_CALLS` | 24 | 工具动作总数 |
| `SHIJIAJING_MAIN_AGENT_MAX_RETRIEVAL_CALLS` | 6 | 逻辑检索动作数 |
| `SHIJIAJING_MAIN_AGENT_MAX_MODEL_CALLS` | 32 | 主/工具/子任务模型调用数 |
| `SHIJIAJING_MAIN_AGENT_MAX_TOKENS` | 100000 | 主请求 token 上限 |
| `SHIJIAJING_MAIN_AGENT_MAX_SUBAGENT_STARTS` | 2 | 子任务启动数；运行时仍限制单层执行 |
| `SHIJIAJING_SUBAGENT_MAX_DECISIONS` | 4 | 单个子 Agent 决策轮数 |
| `SHIJIAJING_SUBAGENT_MAX_TOOL_CALLS` | 6 | 单个子 Agent 工具动作数 |
| `SHIJIAJING_SUBAGENT_MAX_SECONDS` | 30 | 单个子 Agent 时限 |
| `SHIJIAJING_SUBAGENT_MAX_TOKENS` | 20000 | 单个子 Agent token 上限 |
| `SHIJIAJING_TURN_TIMEOUT_SECONDS` | 60 | 单轮总时限 |
| `SHIJIAJING_VISION_TIMEOUT_SECONDS` | 30 | VLM 超时 |
| `SHIJIAJING_TEXT_MODEL_TIMEOUT_SECONDS` | 15 | 文本模型超时 |
| `SHIJIAJING_RETRIEVAL_TIMEOUT_SECONDS` | 3 | 检索超时 |
| `SHIJIAJING_MAX_MODEL_REPAIRS` | 2 | 结构化输出修复次数 |
| `SHIJIAJING_MAX_NETWORK_ATTEMPTS` | 2 | 网络尝试次数 |

运行时还限制物理检索成本。`RETRIEVAL_CALLS` 是逻辑查询数；数据库搜索和 embedding 调用
分别计量并在动作执行前预留预算：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `SHIJIAJING_RETRIEVAL_INITIAL_MAX_QUERIES` | 3 | 首轮最多查询数 |
| `SHIJIAJING_RETRIEVAL_SUPPLEMENT_MAX_QUERIES` | 3 | 补充检索最多查询数 |
| `SHIJIAJING_RETRIEVAL_MAX_DB_SEARCH_ATTEMPTS` | 24 | 物理数据库搜索尝试数 |
| `SHIJIAJING_RETRIEVAL_QUERY_CONCURRENCY` | 2 | 查询并发上限 |
| `SHIJIAJING_RETRIEVAL_TOP_K_PER_CHANNEL` | 100 | 每召回通道 Top-K |
| `SHIJIAJING_RETRIEVAL_UNION_LIMIT` | 200 | 通道合并上限 |
| `SHIJIAJING_MATCHING_CANDIDATE_LIMIT` | 60 | 同款匹配候选上限 |
| `SHIJIAJING_RETRIEVAL_INDEX_VERSION` | 空 | 结果缓存使用的索引身份；manifest 发布时优先使用其身份 |
| `SHIJIAJING_RETRIEVAL_RRF_K` | 60 | RRF 计算参数 |

## 4. 动态 Schema 与商品处理

商品归一化固定使用请求级局部动态 Schema；没有模式切换开关。Schema 发现或字段归一化
失败时，当前批次保守回退到通用规则基线，并在结果中保留降级信息。

| 变量 | 默认值 |
|---|---:|
| `SHIJIAJING_DYNAMIC_SCHEMA_BATCH_SIZE` | 60 |
| `SHIJIAJING_DYNAMIC_SCHEMA_CONCEPT_MIN_CONFIDENCE` | 0.90 |
| `SHIJIAJING_DYNAMIC_SCHEMA_ROLE_MIN_CONFIDENCE` | 0.90 |
| `SHIJIAJING_DYNAMIC_SCHEMA_ROLE_MIN_SUPPORT` | 2 |
| `SHIJIAJING_DYNAMIC_SCHEMA_MAX_CONCEPTS` | 16 |
| `SHIJIAJING_DYNAMIC_SCHEMA_MAX_ATTRIBUTES_PER_CONCEPT` | 64 |
| `SHIJIAJING_DYNAMIC_SCHEMA_CACHE_TTL_SECONDS` | 604800 |
| `SHIJIAJING_DYNAMIC_CANONICALIZATION_BATCH_SIZE` | 20 |
| `SHIJIAJING_DYNAMIC_CANONICALIZATION_FIELD_MIN_CONFIDENCE` | 0.80 |
| `SHIJIAJING_BRAND_HARD_FILTER_CONFIDENCE` | 0.85 |
| `SHIJIAJING_MODEL_HARD_FILTER_CONFIDENCE` | 0.90 |
| `SHIJIAJING_SAME_ITEM_ACCEPT_THRESHOLD` | 0.88 |
| `SHIJIAJING_SAME_ITEM_REVIEW_THRESHOLD` | 0.74 |

## 5. 二期存储、HITL 与缓存

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SHIJIAJING_REQUEST_LEDGER_BACKEND` | `sqlite`（环境加载） | `disabled` / `sqlite` / `postgres` |
| `SHIJIAJING_REQUEST_LEDGER_DSN` | 空 | 为空时复用 checkpoint DSN |
| `SHIJIAJING_MEMORY_ENABLED` | `false` | 长期记忆总开关 |
| `SHIJIAJING_MEMORY_RECALL_ENABLED` | `true` | 是否启用记忆召回 |
| `SHIJIAJING_MEMORY_COMMIT_ENABLED` | `true` | 是否启用记忆变更准备/提交 |
| `SHIJIAJING_MEMORY_BACKEND` | `disabled` | `disabled` / `sqlite` / `postgres` |
| `SHIJIAJING_MEMORY_DSN` | 空 | Memory 存储 DSN |
| `SHIJIAJING_MEMORY_RECALL_LIMIT` | 20 | 召回上限 |
| `SHIJIAJING_RECENT_TURNS_LIMIT` | 6 | 会话摘要轮数上限 |
| `SHIJIAJING_RECENT_TURNS_MAX_BYTES` | 65536 | 会话摘要字节上限 |
| `SHIJIAJING_MEMORY_PURGE_ENABLED` | `false` | 受信管理入口的物理清除开关 |
| `SHIJIAJING_MEMORY_MUTATION_LEDGER_RETENTION_DAYS` | 90 | mutation hash ledger 保留天数 |
| `SHIJIAJING_HITL_ENABLED` | `false` | 是否允许 start/resume 中断 |
| `SHIJIAJING_RECOGNITION_REVIEW_THRESHOLD` | 0.70 | 低于此识别置信度建议复核 |
| `SHIJIAJING_MEMORY_CONFIRMATION_REQUIRED` | `true` | 记忆提交前是否要求确认 |
| `SHIJIAJING_CACHE_BACKEND` | `disabled` | `disabled` / `memory` / `sqlite` / `postgres` |
| `SHIJIAJING_CACHE_DSN` | 空 | Cache 存储 DSN |
| `SHIJIAJING_EVENT_STORE_BACKEND` | `disabled` | 生产环境不能保持 disabled |
| `SHIJIAJING_EVENT_STORE_DSN` | 空 | Event Store DSN |

缓存是 miss-safe 性能层，不是事实来源。版本、约束和 manifest 变化必须形成不同的缓存
身份；缓存读回后仍要重新校验契约、硬过滤和证据一致性。

PostgreSQL 业务适配器连接池参数为 `SHIJIAJING_POSTGRES_POOL_MIN_SIZE=1`、
`SHIJIAJING_POSTGRES_POOL_MAX_SIZE=4`、`SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS=30`。
生产环境还要求 `SHIJIAJING_ENV=prod` 时启用 Event Store 并提供 DSN。

## 6. TTL 与校验规则

缓存 TTL 默认值为：vision `2592000`、intent `604800`、query rewrite `604800`、retrieval
`300`、explanation `86400` 秒。所有 TTL 必须为正数；超时必须是有限正数；计数上限必须为
正整数（`MAIN_AGENT_MAX_SUBAGENT_STARTS` 可为 0）；置信度和同款阈值必须在 `0..1`，且
`SAME_ITEM_REVIEW_THRESHOLD` 不得大于 `SAME_ITEM_ACCEPT_THRESHOLD`。

主模型、checkpoint、trace 和检索来源的缺失检查由真实装配入口执行；Fake 端口只应由测试
或离线示例显式注入。

## 7. 已移除配置

以下变量不再被解析，也不会选择或启动兼容引擎。环境中仍携带它们时，加载器会直接指出
应删除的变量：

```text
SHIJIAJING_EXECUTION_MODE
SHIJIAJING_RESEARCH_SUBAGENT_ENABLED
SHIJIAJING_VERIFICATION_SUBAGENT_ENABLED
SHIJIAJING_SUPERVISOR_MODEL
SHIJIAJING_SUPERVISOR_PLANNER_MODE
SHIJIAJING_SUPERVISOR_PLANNER_TIMEOUT_SECONDS
SHIJIAJING_SUPERVISOR_PLANNER_MAX_REPAIRS
SHIJIAJING_SUPERVISOR_PLANNER_MAX_TOKENS
SHIJIAJING_MAX_AGENT_TASKS
SHIJIAJING_MAX_SUPERVISOR_REPLANS
SHIJIAJING_AGENT_TASK_TIMEOUT_SECONDS
SHIJIAJING_RETRIEVAL_FUSION_STRATEGY
SHIJIAJING_RETRIEVAL_RERANK_ENABLED
SHIJIAJING_RETRIEVAL_RERANK_LIMIT
```

删除这些变量后，生产、CLI 和实时评测都使用同一条 `AgentFacade → MainAgentRuntime` 路径。
