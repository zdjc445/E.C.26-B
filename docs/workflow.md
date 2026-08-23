# 工作流说明

LangGraph StateGraph 实现，`thread_id = session_id`，多轮在会话内恢复。
本文档描述图结构、条件路由、多轮行为与故障处理。

## 1. 状态（AgentState）

状态含：输入请求、识别结果、意图 patch、合并后约束、检索查询、候选、
SPU/SKU 分组、排序结果、证据、解释、响应、bounded `recent_turns`、dirty flags
与上一轮状态。
节点按 dirty flags **局部重算**，避免整图重跑。

## 1.1 受控 Multi-Agent 模式

当 `SHIJIAJING_ORCHESTRATION_MODE=multi_agent` 或 `multi_agent_shadow` 时，Facade 进入
`multi_agent.supervisor.MultiAgentSupervisor`：Planner 先生成 `ExecutionPlan`，Supervisor
按依赖选择 ready tasks，Recognition、Intent 和启用的 Memory recall 可以并行；没有图片时
不创建 Recognition，缺少品类时将 Retrieval/Explanation 标记为 `SKIPPED` 并返回澄清。

每个 Specialist 只接收自身的 `AgentTaskInput`，通过 `AgentResultV2` 返回 proposal。Retrieval
Agent 继续持有确定性查询改写硬过滤、同款 complete-link、SKU 拆分、价格聚合和排序；Explanation
降级只使用模板，不重新执行 Retrieval。`multi_agent_shadow` 明确跳过 Memory commit，避免
评测路径产生副作用；配置 native saver 时，受控路径会按 Supervisor/task namespace 恢复已完成
结果。默认模式仍是 legacy `workflow`，端到端 HITL resume 和正式发布门禁完成前不得切换默认值。

## 2. 节点与路由

| 节点 | 职责 | 关键行为 |
|---|---|---|
| `validate_input` | 请求校验（字段、图片格式、请求号） | 非法输入 → FAILED |
| `load_session` | 按 session_id 恢复状态 | 幂等：同 request_id 直接返回 |
| `prepare_subject` | 启动理解阶段 | 静态启动 `recognition_start` 与 `intent_start` 两条分支 |
| `recognition_start` | 识别分支路由 | 有图片 → `recognize_image`；无图片 → `apply_correction`（无修正时 no-op） |
| `recognition_done` | 识别分支完成标记 | 等待 `intent_done` 后进入 `join_understanding` |
| `intent_start` / `intent_done` | 意图分支与完成标记 | `parse_intent` 后写入汇合 barrier |
| `join_understanding` | 两支汇合 | 两条分支完成后才进入 Memory/`merge_constraints` |
| `recognize_image` | 调 VLM | 超时/失败重试，失败 → FAILED |
| `apply_correction` | 应用用户修正 | **不调用 VLM**；修正绑定当前 `recognition_id` |
| `normalize_recognition` | 识别结果规范化为品类/品牌/型号/属性 | 未知品类 → 语义校验错误处理 |
| `parse_intent` | 意图提取（含历史） | 结构化失败修复 2 次 → 规则降级 |
| `merge_constraints` | 约束合并（历史+新意图） | 冲突检测 |
| `validate_constraints` | 约束完整性/冲突检查 | 不完整或冲突 → `build_clarification`；否则继续 |
| `build_clarification` | 生成澄清问题与选项 | 响应携带 `clarification` |
| `rewrite_query` | 意图 → 检索查询（文本+硬过滤） | 模型失败 → `HardFilterBuilder` 降级 |
| `retrieve_candidates` | 混合召回（dense/sparse/image/metadata） | 命中 → 匹配；零结果或识别约束过严 → 分路由 |
| `relax_recognition_constraints` | 放宽**识别低置信**产生的约束（限 1 次） | 用户硬过滤永不自动放宽 |
| `normalize_candidates` | 候选规范化（品类/品牌/型号/属性） | 与识别同套归一化 |
| `match_same_item` | 同款判定：硬冲突否决 → complete-link 聚类 | |
| `split_sku` | SKU 拆分 | 组内必须同 SKU |
| `rank_groups` | 比价排序 | 纯领域计算，不依赖 LLM |
| `build_evidence` | 生成证据束（价格、平台、排名） | 解释只允许引用证据 |
| `generate_explanation` | 解释生成 | 模型失败 → 模板解释并标记 `explanation_verified=False` |
| `build_response` / `build_no_results` | 组装响应 | 含 notice（降级/待人工复核） |
| `build_failed_response` | 故障响应（FAILED） | 进入 `append_turn_summary` 后结束 |

条件路由（routing.py）：

- `route_recognition`：识别 / 修正 / 跳过。
- `prepare_subject` 的静态双边与 `g.add_edge(["recognition_done", "intent_done"], "join_understanding")`：Recognition/Intent 并行与 barrier 汇合。
- `route_after_validation`：澄清或继续。
- `route_retrieval`：命中 / 识别约束过严重试 / 无结果 / 检索不可用。
- `route_after_relax`：重写重试或无结果。

## 3. 多轮交互

- 每轮 `AgentRequest(session_id, request_id, text, image, correction)`；
  同会话串行执行，状态增量合并（IntentPatch 与识别 dirty flags）。
- 每个终态响应都会追加一条 bounded `recent_turns` 摘要，最多保留
  `RECENT_TURNS_LIMIT` 条；该会话记忆与长期 Memory 开关独立。
- 澄清轮：`build_clarification` 输出选项，下一轮用户用选项文本回复，
  意图节点带历史解析，合并约束后继续。
- 修正轮：`RecognitionCorrection(recognition_id=当前轮最新识别 ID, ...)` 必须指向
  会话最新识别结果；修正后不触发 VLM，直接以修正值继续。
- 硬过滤：用户表达的约束（预算、平台、品牌）自动合并为硬过滤；
  识别低置信产生的约束是**软**的，可被放宽——两者在代码中明确区分。

## 4. 幂等、并发与恢复

- 幂等：`request_id` 唯一键；重复请求直接返回既有响应（状态恢复，不重跑模型）。
- native 即使未装配 Request Ledger，也会从 thread checkpoint 对已完成的相同 `request_id`
  返回既有 terminal response；Ledger 装配后由 Ledger 提供跨资源幂等记录。
- 乐观版本：Checkpoint 保存带 `expected_version`；冲突 → 重放当前请求一次；
  仍冲突 → `SessionConflictError`。
- 会话锁：同会话并发请求只允许一个执行，其余返回冲突错误。
- 恢复：任何节点失败后，新请求从最近 checkpoint 恢复（SQLite/Postgres 双后端）。
- native `start/resume` 与 legacy `run` 使用相同的 turn、节点和结果事件投影；resume 从 checkpoint
  中已有的 `node_events` 长度继续，避免重复写入审计事件。
- native 图 timeout 或内部异常时，Facade 生成 FAILED response；Request Ledger 已装配时写入
  Ledger，并尝试将失败状态和 `recent_turns` 保存到 native checkpoint；checkpoint 不可用时
  只保留可返回的失败响应与终态事件。

## 5. 模型故障路径

模型输出经过 Pydantic + 语义双重校验（子图边界按方案 §5.2 校验）：

1. 结构化输出校验失败 → 修复循环（最多 `MAX_MODEL_REPAIRS=2` 次，带错误回传）。
2. 修复仍失败 → 规则/模板降级：意图 → `RuleIntentParser`；查询改写 → `HardFilterBuilder`；
   解释 → 模板（证据内数字），并在响应 notice 中如实标注降级。
3. 检索失败 → Milvus 不可用时降级本地词法（同一领域协议）；
   两者皆不可用 → `build_failed_response`（FAILED + 精确原因）。

## 6. 工程化资源路径

- `request_result_committed` 在 Request Ledger 成功提交后追加；事件追加失败不回滚已提交结果，
  由 `shijiajing-repair-events` 修复。
- native checkpoint 补写缺失 Ledger 记录时追加 `request_ledger_repaired`，并增加
  `request_ledger_repair_total`；补写失败返回 `REQUEST_LEDGER_UNAVAILABLE`。
- Memory `commit` 成功后追加 `memory_committed` 或 `memory_forgotten`；Cache 读写异常统一按 miss
  处理并增加指标。
- `open_agent_runtime()` 负责外部客户端生命周期：Ark 四个模型 Port 共享的客户端只关闭一次；
  Retrieval 适配器退出时关闭其 Embedding、Milvus 客户端和本地兜底资源，且 setup 失败会回收
  已注册资源。
- `SHIJIAJING_TRACE_BACKEND=opentelemetry` 时，OTLP endpoint 由
  `SHIJIAJING_TRACE_DSN` 提供；Trace 只写脱敏元数据和哈希。
