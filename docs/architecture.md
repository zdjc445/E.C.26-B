# 架构说明

识价镜 Agent 是一个**可恢复的多轮比价 Workflow Agent**：图片/文本输入 → 商品识别 →
意图理解 → 混合召回 → 同款匹配 → SKU 拆分 → 比价排序 → 多轮筛选修正。
工程只实现 Agent 逻辑，不包含 Web API 与客户端（§25）。

## 1. 分层

```text
src/shijiajing_agent/
├── contracts.py       Pydantic 数据契约（§5、§8）——跨层唯一数据形态
├── config.py          Settings：外部资源无代码默认值，缺失启动失败（§23）
├── deps.py            生产装配：按 Settings 构建真实端口实现
├── facade.py          AgentFacade：会话编排、幂等、并发控制、事件流（§17）
├── graph.py / routing.py   StateGraph 主图与条件路由（§9、§10）
├── state.py           图状态 AgentState 与 dirty flags（§9.4、§16）
├── domain/            纯领域层：约束合并/同款/SKU/价格聚合/排序/证据（§12–§15）
├── nodes/             图节点（§9.2 节点表）
├── ports/             全部外部能力的 Protocol 端口（§11.1）
├── adapters/          端口实现：Ark 模型、Milvus/本地检索、Checkpoint、可观测性
├── prompts/           模型 Prompt 文件（带版本）
├── tools/             初始化与运维 CLI（init_milvus / index_products / run_eval）
├── evals.py           离线评测（§22）
└── data/              taxonomy.json 与评测种子数据集（data/eval/）
```

依赖方向严格单向：`nodes/ → domain/ + ports/`，`adapters/ → ports/ + domain/`，
`domain/` 不依赖任何适配器。

## 2. 端口（Port，§11.1）

所有外部能力通过 Protocol 注入，图节点只感知端口抽象：

| 端口 | 实现 | 说明 |
|---|---|---|
| `VisionModelPort` | `ArkVisionModel` | 图片 → RecognitionResult |
| `IntentModelPort` | `ArkIntentModel` / `RuleIntentParser`（降级） | 文本 → IntentPatch |
| `QueryRewritePort` | `ArkQueryRewrite` / `HardFilterBuilder`（降级） | 意图 → RetrievalQuery |
| `ExplanationModelPort` | `ArkExplanationModel` / 模板（降级） | 证据 → 解释文本 |
| `ProductRetrievalPort` | `MilvusHybridRetrievalAdapter` / `LocalLexicalRetrievalAdapter` | 混合召回（§13） |
| `CheckpointPort` | `SQLiteCheckpointAdapter` / `PostgresCheckpointAdapter` | 状态持久化（§17.4） |
| `TraceSinkPort` / `MetricsPort` | `StructlogTraceSink` / `PrometheusMetrics` | 可观测性（§18） |

两种检索实现返回**同一领域协议**（§25：Milvus 和本地降级返回同一领域协议），
本地降级如实标注 `fallback_used`，不做伪向量。

## 3. 主图（§9）

```text
START → validate_input → load_session → prepare_subject
  ├─(有图片)→ recognize_image ─┐
  ├─(有修正)→ apply_correction ─┴→ normalize_recognition
  └─(无图片)→ 直接到 normalize_recognition
normalize_recognition → parse_intent → merge_constraints → validate_constraints
  ├─(不完整/冲突)→ build_clarification → build_response → END
  └─(完整)→ rewrite_query → retrieve_candidates
retrieve_candidates
  ├─(命中)→ normalize_candidates → match_same_item → split_sku
  │          → rank_groups → build_evidence → generate_explanation → build_response → END
  ├─(识别约束过严)→ relax_recognition_constraints → rewrite_query（重试，限 1 次）
  ├─(无结果)→ build_no_results → build_response → END
  └─(检索不可用)→ build_failed_response → END
```

- **硬冲突否决 → complete-link 聚类 → SKU 拆分**（§14）：同款匹配先否决
  品类/品牌/型号/身份属性冲突对，再聚类成 SPU，再按变体属性拆 SKU（§14.5）。
- **只有相同 SKU 进入同一个比价组**（§25）：组内价格聚合为 `min_price`（券后实付，§15.1）。
- **排序与价格计算不依赖 LLM**（§25）：`GroupRanker` 纯领域计算。
- **修正后不再调用 VLM**（§25）：`apply_correction` 直接把修正值写入识别结果。
- **用户硬过滤不会被自动放宽**（§25）：`relax_recognition_constraints` 只放宽
  **识别低置信**产生的约束，且带 `dirty flag` 局部重算（§9.4、§16）。

## 4. 多轮会话与恢复（§17）

- `session_id` 作为 LangGraph `thread_id`；每轮请求从 Checkpoint 恢复状态。
- `request_id` 幂等：同会话同请求号直接返回已产出的响应（§17.2）。
- 乐观版本号：保存时带 `expected_version`，冲突触发重放一次（§17.3）。
- 同会话并发：会话锁，冲突抛 `SessionConflictError`。

## 5. 可观测性（§18）

- Trace：structlog 输出结构化事件（事件名、request_id、节点耗时、降级标记），
  不包含密钥与隐藏思维链（§25）。
- Metrics：prometheus-client 计数器/直方图（模型调用、检索降级、修复次数、延迟）。
- 节点日志不得包含 API Key 与模型内部推理链。

## 6. 与方案对应

| 机制 | 位置 |
|---|---|
| 契约与状态 | [contracts.md](contracts.md) |
| 图与多轮 | [workflow.md](workflow.md) |
| 检索与 Milvus | [milvus_schema.md](milvus_schema.md) |
| 配置 | [configuration.md](configuration.md) |
| 评测 | [evaluation.md](evaluation.md) |
| 故障排查 | [troubleshooting.md](troubleshooting.md) |
