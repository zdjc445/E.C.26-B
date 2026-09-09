# 识价镜 Agent（shijiajing-agent）

图片/文本输入 → 商品识别 → 意图理解 → 混合召回 → 同款匹配 → SKU 拆分 →
比价排序 → 多轮筛选修正 的**可恢复 Agent runtime**（LangGraph）。生产只有
`AgentFacade → MainAgentRuntime` 一条执行链；普通请求可以零次委派，复杂检索或详情核验
缺口才由主 Agent 按需委派 subagent。

工程只实现 Agent 逻辑，不包含 Web API 与客户端（方案 §3.2 非目标）。

## 快速开始

```bash
uv sync
uv run pytest -q          # 离线单测（不需要任何外部资源）
uv run shijiajing-eval    # 离线评测（种子数据集，见"数据状态"）
```

## 配置

所有外部配置通过环境变量注入（无代码默认值，缺失时启动失败并列出精确缺失项）：

```bash
cp .env.example .env      # 然后按注释填写
```

| 组 | 变量 |
|---|---|
| 模型 | `SHIJIAJING_ARK_API_KEY` `SHIJIAJING_ARK_BASE_URL` `SHIJIAJING_ARK_VISION_MODEL` `SHIJIAJING_ARK_TEXT_MODEL` `SHIJIAJING_EMBEDDING_MODEL` |
| 云端精排 | 生产必填 `SHIJIAJING_RERANKER_PROVIDER=aliyun_bailian`、`RERANKER_BASE_URL`、`RERANKER_API_KEY`、`RERANKER_MODEL`；开发/单测显式使用 Fake |
| 检索 | `SHIJIAJING_MILVUS_URI` `SHIJIAJING_MILVUS_TOKEN` `SHIJIAJING_MILVUS_COLLECTION`（或 `SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH` 本地词法降级） |
| 持久化 | `SHIJIAJING_CHECKPOINT_BACKEND` `SHIJIAJING_CHECKPOINT_DSN` `SHIJIAJING_REQUEST_LEDGER_BACKEND` `SHIJIAJING_REQUEST_LEDGER_DSN` |
| 主 Agent / subagent | `SHIJIAJING_MAIN_AGENT_MODEL` `SHIJIAJING_SUBAGENT_MODEL`；预算由 `MAIN_AGENT_*`、`SUBAGENT_*` 和 `RETRIEVAL_*` 控制，不选择架构 |
| 二期能力 | `SHIJIAJING_MEMORY_*` `SHIJIAJING_HITL_ENABLED` `SHIJIAJING_CACHE_*` `SHIJIAJING_EVENT_STORE_*` |
| 可观测 | `SHIJIAJING_TRACE_BACKEND` `SHIJIAJING_TRACE_DSN` |
| 数据 | `SHIJIAJING_TAXONOMY_PATH` `SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH` |

运行参数（超时/重试/阈值）均有方案 §13 配置定义，可按需覆盖。
详见 [docs/configuration.md](docs/configuration.md)。

## 运行示例

需要完整外部配置（模型 + 检索 + checkpoint）；缺失时打印精确缺失项并退出码 2。

```bash
# 文本比价（可追加一轮追问）
uv run python -m examples.text_example "索尼耳机 预算2000以内"
uv run python -m examples.text_example "索尼耳机 预算2000以内" "只要黑色款"

# 图片识别 + 比价（可选补充文本）
uv run python -m examples.image_example --image photo.jpg --text "预算2000以内"

# 用户修正：第一轮图片识别，第二轮修正品牌/型号，修正后不再调用 VLM
uv run python -m examples.correction_example --image photo.jpg --brand Sony --model WH-1000XM5

# 主 Agent 模型为生产必填；未配置子模型时沿用主模型
export SHIJIAJING_MAIN_AGENT_MODEL="$SHIJIAJING_ARK_TEXT_MODEL"
```

示例脚本与生产 CLI 共用 `shijiajing_agent.asyncio_compat`；Windows 下会使用
`SelectorEventLoop`，不直接调用 `asyncio.run()`。

## 离线评测

```bash
uv run shijiajing-eval                     # 离线评测 → reports/eval_report.md
uv run shijiajing-benchmark --report-dir reports --warmup 5 --iterations 30  # 本机延迟基线
# 正式数据延迟门禁必须显式声明 source、数据目录和 p95 阈值
uv run shijiajing-benchmark --source formal --datasets-dir <frozen_dir> \
  --gate-strategy weighted --max-p95-ms <threshold> --report-dir reports/frozen
uv run shijiajing-eval --frozen            # 门禁通过后写冻结报告
uv run shijiajing-eval --live --output-datasets-dir <dir>  # 真实数据实时输出副本（目录须不存在）
# 人工仲裁完成后，用 shijiajing-build-eval freeze 晋级为 frozen 数据集
```

- 11 项指标与阈值门禁；4 项**阻断指标**未达标（含未测量）即失败。
- 退出码：0 达标 / 1 阻断失败 / 2 配置或数据集错误。
- 详见 [docs/evaluation.md](docs/evaluation.md)。

## 数据状态（请先阅读）

**仓库内没有真实电商数据。** 按方案 §3.2 非目标与 §16 评测数据边界明确披露如下：

| 数据 | 状态 |
|---|---|
| 商品快照 / 商品 | **样例数据**（测试夹具与评测种子数据集），不是任何真实平台数据；平台使用契约 ID（taobao/jd/pinduoduo） |
| `src/shijiajing_agent/data/eval/` 评测集 | **CI 回归种子样例**，不是正式冻结评测集；`reports/frozen_eval_report.md` 是基于种子数据的回归报告，不代表真实商品上的达标 |
| 模型输出（`recorded` 字段） | 冻结的样例输出；需要模型调用次数插桩的指标如实标注 `pending` |
| 真实数据接入 | `shijiajing-index-products` 索引真实快照 → Milvus；`shijiajing-eval --live --output-datasets-dir` 产出待仲裁副本，随后用 `shijiajing-build-eval freeze` 产出正式评测集 |

**降级状态**：Milvus 不可用时自动降级本地词法检索（同一领域协议，响应标记
`fallback_used`，不声称执行了向量检索）；Reranker 超时、限流、网络或非法响应时保留完整
RRF 顺序并继续多样性窗口，结果记录 `RerankResult` 降级原因；模型失败时规则/模板降级并在 notice 中
标注。测试环境通过 Fake 端口注入样例数据，生产装配不会静默回退到样例数据或静默跳过精排。

## 架构

```text
请求或恢复 → AgentFacade → 主 Agent 观察/决策
                         ├→ 检索比较 / 证据读取
                         ├→ 按需 Research / Verification subagent
                         └→ 追问 / 回答 / 无结果
                         ↓
                   运行时校验 → Checkpoint
```

- 分层：contracts（Pydantic）→ domain/services（业务能力）→ agent_runtime（主/子 Agent 运行时）→ adapters（外部能力）
- `AgentFacade` 始终进入 `MainAgentRuntime`；主 Agent 的动作、预算、HITL、证据和恢复由确定性
  runtime 控制，subagent 没有主状态或长期记忆写权限。
- 全部外部能力通过 Protocol 端口注入（VLM/意图/改写/解释/检索/Reranker/Checkpoint/Trace/指标）
- 幂等（request_id）、乐观版本冲突重放、同会话并发控制
- 详细：[docs/architecture.md](docs/architecture.md)、[docs/multi_agent.md](docs/multi_agent.md)

## 文档

| 文档 | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | 分层、端口、主/子 Agent 与会话恢复 |
| [docs/contracts.md](docs/contracts.md) | 数据契约、硬过滤语义、Checkpoint 序列化 |
| [docs/memory.md](docs/memory.md) | 三层上下文、显式记忆写入、scope/apply mode、HITL、持久化与验收设计 |
| [docs/multi_agent.md](docs/multi_agent.md) | 主 Agent 按需委派、动作权限与确定性边界 |
| [主 Agent + 按需 subagent 改造设计](docs/plans/main_agent_on_demand_subagents_design.md) | 设计、阶段实施记录、兼容回滚及验收清单 |
| [单一主／子 Agent 架构收敛方案](docs/plans/subagent_only_architecture_design.md) | 已实施：只保留 Main + 按需 Subagent |
| [SKU 原始数据与按需补召回 RAG 方案](docs/plans/sku_offer_rag_on_demand_retrieval_design.md) | 原始 Offer、混合召回、动态 Schema、按需补查与验收设计 |
| [意图理解与 Query Expansion 一体化设计](docs/plans/intent_understanding_query_expansion_design.md) | 意图体系、指代消解、槽位合并、查询改写与主 Agent 路由的完整链路 |
| [Query Expansion 完整系统设计](docs/plans/query_expansion_system_design.md) | 扩写策略、通道编译、安全校验、预算、评测和分阶段实施方案 |
| [docs/product_canonicalization.md](docs/product_canonicalization.md) | 当前商品归一化、动态 Schema 四种迁移模式、证据校验、SPU/SKU 确定性处理 |
| [docs/plans/dynamic_product_schema_implementation_plan.md](docs/plans/dynamic_product_schema_implementation_plan.md) | 无静态 Taxonomy 的 LLM 动态局部 Schema 目标架构、迁移与验收方案 |
| [docs/configuration.md](docs/configuration.md) | 全部配置项与缺失行为 |
| [docs/milvus_schema.md](docs/milvus_schema.md) | Collection 结构、索引脚本、混合召回、降级 |
| [docs/operations/rag_migration.md](docs/operations/rag_migration.md) | RAG 索引/快照迁移、切换与验收 |
| [docs/evaluation.md](docs/evaluation.md) | 数据集、指标阈值、冻结流程、诚实性说明 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 常见故障与处理 |
| [docs/operations_phase2.md](docs/operations_phase2.md) | 二期备份、迁移、事件修复与回滚 |
| [docs/operations/event_repair.md](docs/operations/event_repair.md) | Event Store 一致性事件 dry-run/apply 与冲突处理 |
| `shijiajing-release-check` | 汇总本地、正式评测和生产外部证据；缺失证据时 fail-closed |
| [deploy/phase2/README.md](deploy/phase2/README.md) | PostgreSQL/OTLP 本地依赖与可重复验收编排 |
| [docs/archive/README.md](docs/archive/README.md) | 已完成或已被当前实现替代的历史方案与阶段报告 |

## 开发

```bash
uv run ruff check src tests examples && uv run ruff format --check src tests examples
uv run pyright                # strict，0 错误
uv run pytest -q              # 离线测试；集成测试（-m integration）需要真实外部资源
```
