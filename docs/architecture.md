# 架构说明

识价镜 Agent 是一个**可恢复的层级式多轮比价 Multi-Agent**：图片/文本输入 → 商品识别 →
意图理解 → 混合召回 → 同款匹配 → SKU 拆分 → 比价排序 → 多轮筛选修正。
工程只实现 Agent 逻辑，不包含 Web API 与客户端（方案 §3.2 非目标）。

## 1. 分层

```text
src/shijiajing_agent/
├── contracts.py       Pydantic 数据契约（§5、§8）——跨层唯一数据形态
├── config.py          Settings：外部资源无代码默认值，缺失启动失败（方案 §13）
├── deps.py            生产装配：按 Settings 构建真实端口实现
├── facade.py          AgentFacade：会话编排、幂等、并发控制、事件流
├── graph.py / routing.py   Supervisor StateGraph、并行汇合与条件路由
├── subgraphs/              专业子图入口及严格输出边界模型（§8）
├── state.py           图状态 AgentState 与 dirty flags
├── domain/            纯领域层：约束合并/同款/SKU/价格聚合/排序/证据
├── nodes/             图节点
├── ports/             全部外部能力的 Protocol 端口
├── adapters/          端口实现：Ark 模型、Milvus/本地检索、Checkpoint、Ledger、Memory、Cache、Event、可观测性
├── prompts/           模型 Prompt 文件（带版本）
├── tools/             初始化与运维 CLI（init_milvus / index_products / run_eval）
├── evals.py           离线评测
└── data/              taxonomy.json 与评测种子数据集（data/eval/）
```

受控层级式 Multi-Agent 的新增边界位于 `multi_agent/`：

```text
multi_agent/contracts.py  → 2.0 任务/结果/计划协议（兼容导出）
multi_agent/planner.py    → 确定性 DAG、预算、依赖与 handoff 门禁
multi_agent/registry.py   → 五个 Specialist Agent 的唯一 dispatch 注册表
multi_agent/agents/       → 五类私有 input/state/output invocation
multi_agent/dispatcher.py → Send/Command 动态派发与 ready-task barrier
multi_agent/supervisor.py → 结果归并、规范约束、HITL、checkpoint 与副作用授权
multi_agent/shadow.py     → 旧 Workflow/新 Supervisor 只读业务不变量对照
```

`SHIJIAJING_ORCHESTRATION_MODE` 默认 `multi_agent`，使用 Supervisor/task 双层 native
checkpoint 和四类 HITL resume。`multi_agent_shadow` 运行受控任务但跳过 Memory commit、
账本、事件与缓存写入，且执行旧图/新图对照；`workflow` 保留为显式兼容与回滚路径。
正式评测、性能阈值和生产外部证据仍必须通过升级方案第 16 节发布门禁。

依赖方向严格单向：`nodes/ → domain/ + ports/`，`adapters/ → ports/ + domain/`，
`domain/` 不依赖任何适配器。

## 2. 端口（Port）

所有外部能力通过 Protocol 注入，图节点只感知端口抽象：

| 端口 | 实现 | 说明 |
|---|---|---|
| `VisionModelPort` | `ArkVisionModel` | 图片 → RecognitionResult |
| `IntentModelPort` | `ArkIntentModel` / `RuleIntentParser`（降级） | 文本 → IntentPatch |
| `QueryRewritePort` | `ArkQueryRewrite` / `HardFilterBuilder`（降级） | 意图 → RetrievalQuery |
| `ExplanationModelPort` | `ArkExplanationModel` / 模板（降级） | 证据 → 解释文本 |
| `ProductRetrievalPort` | `MilvusHybridRetrievalAdapter` / `LocalLexicalRetrievalAdapter` | 混合召回 |
| `CheckpointPort` | `SQLiteCheckpointAdapter` / `PostgresCheckpointAdapter` | 状态持久化 |
| `TraceSinkPort` / `MetricsPort` | `StructlogTraceSink` / `OpenTelemetryTraceSink` / `PrometheusMetrics` | 可观测性（§11.3） |

两种检索实现返回**同一领域协议**（检索适配器的统一端口契约），
本地降级如实标注 `fallback_used`，不做伪向量。

## 3. 主图

```text
START → validate_input → load_session → prepare_subject
  ├─→ recognition_start → recognize_image/apply_correction → normalize_recognition → recognition_done ─┐
  └─→ intent_start → parse_intent → intent_done ───────────────────────────────────────────────────────┤
                                                                                         join_understanding
                                                                                         → Memory/merge_constraints → validate_constraints
  ├─(不完整/冲突)→ build_clarification → build_response → [commit_memory] → append_turn_summary → END
  └─(完整)→ rewrite_query → retrieve_candidates
retrieve_candidates
  ├─(命中)→ normalize_candidates → match_same_item → split_sku
   │          → rank_groups → build_evidence → generate_explanation → build_response → [commit_memory] → append_turn_summary → END
  ├─(识别约束过严)→ relax_recognition_constraints → rewrite_query（重试，限 1 次）
   ├─(无结果)→ build_no_results → build_response → append_turn_summary → END
   └─(检索不可用)→ build_failed_response → append_turn_summary → END
```

- **硬冲突否决 → complete-link 聚类 → SKU 拆分**：同款匹配先否决
  品类/品牌/型号/身份属性冲突对，再聚类成 SPU，再按变体属性拆 SKU。
- **只有相同 SKU 进入同一个比价组**：组内价格聚合为 `min_price`（券后实付）。
- **排序与价格计算不依赖 LLM**：`GroupRanker` 纯领域计算。
- **修正后不再调用 VLM**：`apply_correction` 直接把修正值写入识别结果。
- **识别与意图并行**：`prepare_subject` 启动两个互不覆盖字段的分支，静态 barrier
  `g.add_edge(["recognition_done", "intent_done"], "join_understanding")` 保证两支完成后才进入记忆与约束合并。
- **用户硬过滤不会被自动放宽**：`relax_recognition_constraints` 只放宽
  **识别低置信**产生的约束，且带 `dirty flag` 局部重算。

## 4. 多轮会话与恢复

- `session_id` 作为 LangGraph `thread_id`；每轮请求从 Checkpoint 恢复状态。
- `request_id` 幂等：同会话同请求号直接返回已产出的响应。
- 乐观版本号：保存时带 `expected_version`，冲突触发重放一次。
- 同会话并发：会话锁，冲突抛 `SessionConflictError`。

## 5. 可观测性（方案 §11.3）

- Trace：structlog 输出结构化事件，或 `OpenTelemetryTraceSink` 输出
  `shijiajing.turn` 根 span 和节点子 span；只保留 ID、版本、哈希、计数、错误和降级标记，
  不包含密钥、自由文本与隐藏思维链（方案 §11.3）。
- Metrics：prometheus-client 计数器/直方图（模型调用、检索降级、修复次数、延迟）。
- 节点日志不得包含 API Key 与模型内部推理链。

## 6. 二期资源边界

- Checkpoint 是 workflow 状态事实源；Request Ledger 负责 `request_id` 幂等结果。
- `open_agent_runtime()` 在 setup 前先登记已经构造的 Trace、Ark 共享模型客户端 owner、
  Retrieval 适配器及其 Embedding/Milvus/本地兜底资源和 Checkpoint，再按顺序 setup；因此
  即使最早的 setup 失败，尚未 setup 的已构造资源也会按注册逆序关闭。随后打开 Request
  Ledger、Memory、Cache 和 Event Store；生产 `make_deps()` 在同步构造每个 owner 后通过
  registrar 立即登记，构造阶段后续失败也由同一退出栈回收；关闭实现必须幂等。
- `open_agent_runtime()` 的 yield 前构造、graph checkpointer enter、资源 setup 和 Facade
  编译统一属于 startup 阶段；startup 根因优先于清理异常，yield 后调用方业务异常不改变
  close 错误语义。
- `ports/lifecycle.py` 定义同步/异步兼容的 `setup()` / `close()` 协议；Checkpoint、Request
  Ledger、Memory、Cache、Event Store、Retrieval、Trace 和 runtime 注册的 Vision owner Port
  显式继承该协议，替换适配器不能只实现业务方法而遗漏 runtime 生命周期。
- `runtime.py` 的资源注册、setup、close 函数以 `ResourceLifecyclePort` 泛型保留具体资源类型；
  第三方 LangGraph graph checkpointer 不经过该业务资源函数，继续由独立 async context manager 管理。
- `AgentDependencies` 对 Settings、Checkpoint、Request Ledger、Memory、Cache、Event Store
  和其他 Port 使用显式类型；根图使用 LangGraph `BaseCheckpointSaver[str]`，只在
  LangGraph builder 的未参数化 stub 装配点保留一个局部 `Any` cast。
- `ports/dependencies.py` 的 `AgentDependenciesPort` 为节点、子图和根图提供同一业务依赖
  视图，避免节点工厂用 `Any` 绕过模型、检索、记忆、缓存和事件 Port 契约。
- `domain/cache_policy.py` 的 miss-safe 包装器对 Cache 和 Metrics 使用对应 Port；`Any` 只保留
  在缓存载荷和版本键的动态数据位置，不扩散到外部能力调用边界。
- Ark 模型、Milvus 混合检索和本地词法检索适配器的指标注入也统一使用 `MetricsPort`，
  适配器不再以动态类型接收业务指标依赖。
- live 评测的 `CountedVision`、`CountedIntent`、`CountedQueryRewrite`、`CountedRetrieval`
  包装器复用对应模型/检索 Port 的精确输入输出类型；评测计数不改变生产业务协议。
- 评测与性能 CLI 的固定边界使用 `Settings`、`BenchmarkReport` 等精确类型；跨数据集的
  `dict[str, list[Any]]` 仅保留在异构评测载荷入口，不向配置、报告或外部能力调用扩散。
- native 根图使用独立的 `NativeTurnInput` 输入契约，仅重置本轮工作字段；编译后的 graph
  输出继续是 `AgentState`，避免用完整状态类型掩盖跨轮保留字段不会被覆盖的语义。
- `AgentState.image_ref`、`AgentState.evidence_bundle` 和
  `AgentState.same_item_review_pairs` 分别使用 `ImageRef`、`EvidenceBundle` 和
  `MatchPair`；同款复核的历史字典只在 HITL 入口执行一次模型校验，不再沿状态链传播自由字典。
- Memory 只接受 `domain/memory_policy.py` 白名单键和值域，并按可信 `memory_owner_id` 隔离。
- Cache 只提供 miss-safe 加速，Cache 失败不改变业务结果。
- Event Store 使用稳定 `event_id` 追加审计；`request_result_committed`、
  `memory_committed`、`memory_forgotten` 在真实事务成功后追加。
- `src/shijiajing_agent/subgraphs/` 提供 Recognition、Intent、Retrieval、Explanation、
  Memory 的独立装配入口和五类 Pydantic 输出模型；`graph.py` 通过边界适配器只回写授权
  字段，并在并行 Recognition/Intent 分支汇合前避免完整 state 快照冲突。根图的并行执行由
  Supervisor barrier 负责。

## 7. 与方案对应

| 机制 | 位置 |
|---|---|
| 契约与状态 | [contracts.md](contracts.md) |
| 图与多轮 | [workflow.md](workflow.md) |
| 检索与 Milvus | [milvus_schema.md](milvus_schema.md) |
| 配置 | [configuration.md](configuration.md) |
| 评测与报告门禁 | [evaluation.md](evaluation.md) |
| 故障排查 | [troubleshooting.md](troubleshooting.md) |
| 二期存储与发布运维 | [operations_phase2.md](operations_phase2.md) |
