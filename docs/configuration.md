# 配置说明

所有配置通过环境变量（或 `.env`，见下）注入，前缀统一 `SHIJIAJING_`。
**外部地址、Token、Collection、模型标识符和数据路径没有代码默认值**（§23）；
使用真实适配器时缺失会启动失败，并列出精确缺失项。

## 1. 加载方式

```bash
# 方式一：环境变量
export SHIJIAJING_ARK_API_KEY=...

# 方式二：.env 文件（键名不含前缀，如 ARK_API_KEY=...）
# 示例见仓库根 .env.example，复制后填写即可
```

`shijiajing_agent.config.load_settings()` 读取 `SHIJIAJING_*`；`Settings` 不可变，
`settings.validate(require_real_adapters=True)` 返回缺失项列表。

## 2. 外部资源（无默认值，缺失即失败）

| 环境变量 | 说明 |
|---|---|
| `SHIJIAJING_ARK_API_KEY` | 模型 Provider（OpenAI 兼容）API Key |
| `SHIJIAJING_ARK_BASE_URL` | 模型 Provider Base URL |
| `SHIJIAJING_ARK_VISION_MODEL` | VLM 模型标识符 |
| `SHIJIAJING_ARK_TEXT_MODEL` | 意图/改写/解释共用文本模型标识符 |
| `SHIJIAJING_EMBEDDING_MODEL` | 文本向量模型标识符 |
| `SHIJIAJING_MILVUS_URI` | Milvus 地址 |
| `SHIJIAJING_MILVUS_TOKEN` | Milvus Token |
| `SHIJIAJING_MILVUS_COLLECTION` | Milvus Collection 名 |
| `SHIJIAJING_CHECKPOINT_BACKEND` | `sqlite` / `postgres` |
| `SHIJIAJING_CHECKPOINT_DSN` | sqlite 文件路径或 postgres DSN |
| `SHIJIAJING_TRACE_BACKEND` | 当前仅 `structlog`（预留扩展） |
| `SHIJIAJING_TRACE_DSN` | Trace 目标地址（structlog 后端可不填） |
| `SHIJIAJING_TAXONOMY_PATH` | taxonomy.json 路径（缺省用包内置文件） |
| `SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH` | 本地商品快照 JSONL（词法降级索引） |

### 检索配置的组合（§13.7）

- **Milvus 三件套齐全**（URI + TOKEN + COLLECTION）→ 走 `MilvusHybridRetrievalAdapter`；
  其本地兜底使用快照（未配置快照时，仅当 Milvus 不可用才报精确错误）。
- **仅本地快照** → 直接使用 `LocalLexicalRetrievalAdapter`（BM25 词法 + 相同硬过滤语义）。
- **两者皆无** → 启动报错并列出缺失项（`make_retrieval` 抛 ValueError）。

## 3. 运行参数（均有方案默认值，可按需覆盖）

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `SHIJIAJING_ENV` | `dev` | 环境名 |
| `VISION_TIMEOUT_SECONDS` | 30 | VLM 调用超时 |
| `TEXT_MODEL_TIMEOUT_SECONDS` | 15 | 文本模型调用超时 |
| `RETRIEVAL_TIMEOUT_SECONDS` | 3 | 检索超时 |
| `TURN_TIMEOUT_SECONDS` | 60 | 单轮整体超时 |
| `MAX_MODEL_REPAIRS` | 2 | 模型结构化输出修复次数 |
| `MAX_NETWORK_ATTEMPTS` | 2 | 网络重试次数 |
| `MAX_WORKFLOW_STEPS` | 40 | 单轮图执行步数上限 |
| `RETRIEVAL_TOP_K_PER_CHANNEL` | 100 | 每通道 Top-K |
| `RETRIEVAL_UNION_LIMIT` | 200 | 通道合并上限 |
| `MATCHING_CANDIDATE_LIMIT` | 60 | 同款匹配候选上限 |
| `BRAND_HARD_FILTER_CONFIDENCE` | 0.85 | 品牌硬过滤最低置信 |
| `MODEL_HARD_FILTER_CONFIDENCE` | 0.90 | 型号硬过滤最低置信 |
| `SAME_ITEM_ACCEPT_THRESHOLD` | 0.82 | 同款接受阈值 |
| `SAME_ITEM_REVIEW_THRESHOLD` | 0.68 | 同款人工复核阈值 |

偏好权重表（价格/店铺/评分/销量/发货，§15.4）默认内置，见
`Settings.preference_weights`；可按环境扩展并在 trace 中透出。

## 4. 缺失配置的行为

- 示例与 `shijiajing-eval --live`：`load_settings_or_exit()` 打印
  `缺少必要配置：SHIJIAJING_ARK_API_KEY, ...` 后退出码 2。
- `make_deps(settings)`：抛 `ValueError("缺少必要配置：...")`。
- 应用层（`AgentFacade`）不产生任何配置默认值——缺失即报错，不做静默降级
  到假数据（样例数据只能通过显式 Fake 端口注入，见 tests/workflow/conftest.py）。
