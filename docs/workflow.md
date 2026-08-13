# 工作流说明

LangGraph StateGraph 实现（§9），`thread_id = session_id`，多轮在会话内恢复。
本文档描述图结构、条件路由、多轮行为与故障处理。

## 1. 状态（AgentState，§9.4）

状态含：输入请求、识别结果、意图 patch、合并后约束、检索查询、候选、
SPU/SKU 分组、排序结果、证据、解释、响应、dirty flags 与上一轮状态。
节点按 dirty flags **局部重算**（§16），避免整图重跑。

## 2. 节点与路由

| 节点 | 职责 | 关键行为 |
|---|---|---|
| `validate_input` | 请求校验（字段、图片格式、请求号） | 非法输入 → FAILED |
| `load_session` | 按 session_id 恢复状态 | 幂等：同 request_id 直接返回 |
| `prepare_subject` | 决定识别路径 | 有图片 → `recognize_image`；有修正 → `apply_correction`；否则跳过 |
| `recognize_image` | 调 VLM | 超时/失败重试，失败 → FAILED |
| `apply_correction` | 应用用户修正（§6.3） | **不调用 VLM**；修正绑定当前 `recognition_id` |
| `normalize_recognition` | 识别结果规范化为品类/品牌/型号/属性 | 未知品类 → 语义校验错误处理 |
| `parse_intent` | 意图提取（含历史） | 结构化失败修复 2 次 → 规则降级 |
| `merge_constraints` | 约束合并（§12.3，历史+新意图） | 冲突检测（§12.4） |
| `validate_constraints` | 约束完整性/冲突检查 | 不完整或冲突 → `build_clarification`；否则继续 |
| `build_clarification` | 生成澄清问题与选项 | 响应携带 `clarification` |
| `rewrite_query` | 意图 → 检索查询（文本+硬过滤） | 模型失败 → `HardFilterBuilder` 降级 |
| `retrieve_candidates` | 混合召回（dense/sparse/image/metadata） | 命中 → 匹配；零结果或识别约束过严 → 分路由 |
| `relax_recognition_constraints` | 放宽**识别低置信**产生的约束（限 1 次） | 用户硬过滤永不自动放宽（§25） |
| `normalize_candidates` | 候选规范化（品类/品牌/型号/属性） | 与识别同套归一化 |
| `match_same_item` | 同款判定：硬冲突否决 → complete-link 聚类（§14.2–14.4） | |
| `split_sku` | SKU 拆分（§14.5） | 组内必须同 SKU |
| `rank_groups` | 比价排序（§15.3） | 纯领域计算，不依赖 LLM |
| `build_evidence` | 生成证据束（价格、平台、排名） | 解释只允许引用证据 |
| `generate_explanation` | 解释生成（§15.5） | 模型失败 → 模板解释并标记 `explanation_verified=False` |
| `build_response` / `build_no_results` | 组装响应 | 含 notice（降级/待人工复核） |
| `build_failed_response` | 故障响应（FAILED） | 不经过后续节点，直达 END |

条件路由（routing.py）：

- `route_recognition`：识别 / 修正 / 跳过（§10.1）。
- `route_after_validation`：澄清或继续（§10.2）。
- `route_retrieval`：命中 / 识别约束过严重试 / 无结果 / 检索不可用（§10.3）。
- `route_after_relax`：重写重试或无结果（§10.4）。

## 3. 多轮交互

- 每轮 `AgentRequest(session_id, request_id, text, image, correction)`；
  同会话串行执行，状态增量合并（IntentPatch 与识别 dirty flags）。
- 澄清轮：`build_clarification` 输出选项，下一轮用户用选项文本回复，
  意图节点带历史解析，合并约束后继续。
- 修正轮：`RecognitionCorrection(recognition_id=当前轮最新识别 ID, ...)` 必须指向
  会话最新识别结果（§6.3）；修正后不触发 VLM（§25），直接以修正值继续。
- 硬过滤：用户表达的约束（预算、平台、品牌）自动合并为硬过滤；
  识别低置信产生的约束是**软**的，可被放宽——两者在代码中明确区分。

## 4. 幂等、并发与恢复（§17）

- 幂等：`request_id` 唯一键；重复请求直接返回既有响应（状态恢复，不重跑模型）。
- 乐观版本：Checkpoint 保存带 `expected_version`；冲突 → 重放当前请求一次；
  仍冲突 → `SessionConflictError`。
- 会话锁：同会话并发请求只允许一个执行，其余返回冲突错误。
- 恢复：任何节点失败后，新请求从最近 checkpoint 恢复（SQLite/Postgres 双后端）。

## 5. 模型故障路径

模型输出经过 Pydantic + 语义双重校验（§25）：

1. 结构化输出校验失败 → 修复循环（最多 `MAX_MODEL_REPAIRS=2` 次，带错误回传）。
2. 修复仍失败 → 规则/模板降级：意图 → `RuleIntentParser`；查询改写 → `HardFilterBuilder`；
   解释 → 模板（证据内数字），并在响应 notice 中如实标注降级。
3. 检索失败 → Milvus 不可用时降级本地词法（同一领域协议）；
   两者皆不可用 → `build_failed_response`（FAILED + 精确原因）。
