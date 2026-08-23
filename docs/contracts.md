# 数据契约

跨层唯一数据形态是 `src/shijiajing_agent/contracts.py` 中的 Pydantic 模型（§5、§8）。
模型输出经 Pydantic + 语义双重校验后才是合法契约（子图边界按方案 §5.2 校验）。专业子图返回根图前还必须通过
`src/shijiajing_agent/subgraphs/outputs.py` 中对应的严格输出模型；未知字段不得跨越子图
边界，已解析的领域对象保持 Pydantic/dataclass 类型，不转换为无类型 dict。

## 1. 核心模型

| 模型 | 用途 | 关键字段 |
|---|---|---|
| `AgentRequest` | 每轮输入 | `session_id`、`request_id`、`text`、`image`、`correction` |
| `AgentResponse` | 每轮输出 | `status`、`message`、`recognition`、`clarification`、`groups`、`notices` |
| `AgentStatus` | 状态枚举 | `success` / `clarification` / `failed` |
| `ImageRef` | 图片引用 | `image_id`、`uri`（data URL）、`content_type`、`sha256` |
| `RecognitionCorrection` | 用户修正 | `recognition_id`（必须指向最新识别）+ `brand`/`model`/`category_id` |
| `RecognitionResult` | 识别输出 | `category_id`/`category_name`、`brand`、`model`、`attributes`、`overall_confidence` |
| `IntentPatch` | 意图增量 | `platforms`、`brand`、`model`、`category_id`、`attributes`、`price_range`、`negative_terms` 等 |
| `ShoppingConstraints` | 合并后约束 | 品牌/平台/价格/评分/销量/发货 + 硬过滤标记与来源 |
| `RetrievalQuery` | 检索查询 | `query_text` + `hard_filters` |
| `RetrievalCandidate` | 候选 | `offer` + dense/sparse/recall 分数与通道来源 |
| `Offer` | 商品快照行 | `platform`（平台 ID）、`same_item_key`、`identity_attributes`、`variant_attributes`、`price`、`coupon_amount`、`shipping_fee`、`seller_type`、`rating`、`sales`、`source_updated_at` |
| `SkuGroup` | 比价组 | `group_id`、`sku_signature`、`min_price`、`average_price`、`price_range`、`offers`、`same_spu_key` |
| `Preference` | 排序偏好 | 价格/官方/评分/销量/发货 |

## 1.1 受控 Multi-Agent 2.0 契约

`shijiajing_agent.multi_agent.contracts` 是稳定导出入口，实际 Pydantic 模型定义在
`contracts.py`，全部使用 `extra="forbid"`：

- `AgentTaskV2` 通过 `AgentTaskKind`、`agent_name` 和 `AgentTaskInput` discriminator
  校验任务边界；Recognition/Intent/Retrieval/Explanation/Memory 输入分别拒绝原始图片、
  Memory owner 或其他未授权字段。
- `AgentResultV2` 强制校验 `agent_name`、`task_kind`、output discriminator、FAILED error、
  以及 64 位 `output_hash`。`merge_task_results` 对同 hash 重放幂等，对不同 hash 抛出
  `TASK_RESULT_CONFLICT`，绝不静默覆盖。
- `ExecutionPlan` 在模型层校验唯一 task、依赖存在、DAG 无环和任务预算；`PlanValidator`
  额外校验 Retrieval→Intent、Explanation→Retrieval 和 Memory commit 授权关系。
- 旧 `AgentTask`、`AgentResult` 与 `AgentState` 仍保留，默认 `workflow` 不改变其业务结果。

## 2. 平台标识

`Offer.platform` 使用平台 ID（`taobao` / `jd` / `pinduoduo`），与真实数据契约一致；
中文别名（淘宝/京东/拼多多）只出现在展示与解释层，映射表见
`FactualConsistencyChecker._PLATFORM_NAMES`。

## 3. 硬过滤语义

`HardFilters` 与 Milvus filter 表达式、本地词法降级的
`offer_matches_hard_filters` 与 Milvus filter 表达式使用**同一领域语义**：
品牌/型号精确匹配、价格区间、平台、评分/销量下限、发货时效。
识别低置信约束不进入硬过滤（可放宽，见 workflow.md）。

## 4. 同款与 SKU

- 身份属性（`identity_attributes`）与变体属性（`variant_attributes`）分离：
  前者冲突 → 硬否决（不同 SPU）；后者差异 → 不同 SKU。
- `same_item_key` 是采集源对齐键；同款判定仍以属性+标题相似度为准。
- `SkuGroup.sku_signature` 由变体属性签名构成，同组内 SKU 唯一。

## 5. Checkpoint 序列化（方案 §12）

- 状态经 `model_dump(mode="json")` 转 JSON 持久化；恢复时逐字段重建
  （`_SINGLE_MODEL_FIELDS` / `_LIST_MODEL_FIELDS` / `_ENUM_FIELDS` 驱动）。
- 证据束（`EvidenceBundle`）由纯 dataclass 按字段重建；`previous_state` 不入库。
- legacy SQLite 与 native LangGraph Checkpoint 共用持久化脱敏边界：`current_request` 的
  原始 text、correction、metadata 和图片 URI 不入库；图片只保留 `image_id`、类型、摘要与
  不可访问的占位引用，会话摘要只保留文本摘要的 SHA-256/长度，`RetrievalQuery.query_text`
  在存储读取边界清空。
- `AgentState.errors` 与 `fallbacks` 只保存固定错误码、用户可操作消息和固定降级原因；
  供应商异常字符串、host、DSN 与原始响应不得从适配器进入 Checkpoint 或 Event payload。
- InMemory Event Store、Request Ledger 和 Cache 只用于测试/单进程运行，但必须保持持久化
  适配器的语义：写入快照、读取副本；Event Store 按统一的
  `(occurred_at, event_type_priority, event_id)` 稳定排序，生命周期事件在同一时间戳下仍
  保持 `agent_started → agent_interrupted → agent_resumed → agent_completed/agent_failed`；
  调用方修改读取结果不得反向修改存储内容。
- legacy 状态迁移后的模式版本为 `SCHEMA_VERSION = "1.1"`；版本不符 →
  `CheckpointUnavailableError`。native Checkpointer 使用
  `JsonPlusSerializer(pickle_fallback=False, allowed_json_modules=..., allowed_msgpack_modules=...)`，
  生产执行路径不调用 legacy `agent_checkpoint` 写入。
- native thread 开始新 turn 时，`intent_patch`、约束冲突、检索查询与候选、匹配与排序结果、
  解释、响应、挂起状态、记忆 mutation、`agent_results`、dirty/retry 控制字段和本轮事件历史
  必须重置；`effective_constraints`、识别历史、`subject_id` 与 `recent_turns` 按会话继续保留。
- 每个 terminal response（包括 `SUCCESS`、`CLARIFICATION`、`NO_RESULTS` 和 `FAILED`）都必须
  追加一条 bounded `recent_turns` 摘要；该会话记忆不依赖长期 Memory 是否启用。legacy
  workflow 必须在下一轮加载上一状态中的 `recent_turns`，native workflow 必须从 thread
  checkpoint 继续追加。
- native 图在 timeout 或内部异常后构造的 FAILED response 在 Request Ledger 已装配时写入
  Ledger，并尝试以 `append_turn_summary` 终态更新 native checkpoint；checkpoint 存储不可用
  时保留失败响应和终态事件，但不能声称 checkpoint 已持久化。
- native `start()` 发现 active interrupt 时：相同 `request_id` 且
  `execution_context` 一致必须原样返回已有 `AgentInterrupt`，不得重新执行图；不同
  `request_id` 必须拒绝覆盖待恢复 turn，原 interrupt 仍必须可以 resume。
- native `start()` 发现 thread 已保存同一 `request_id` 的 terminal response 时，必须直接返回
  checkpoint 中的 response；Request Ledger 未装配时该规则仍成立，不能重新执行图。Ledger
  已装配但缺少该 response 记录时，必须先补写 Ledger，补写失败则返回
  `REQUEST_LEDGER_UNAVAILABLE`；补写成功追加 `request_ledger_repaired` 事件并增加
  `request_ledger_repair_total`。

## 6. 二期契约

- `AgentExecutionContext.memory_owner_id` 是可信调用上下文；不得从普通请求 `metadata` 推断 owner。
- `AgentTurnResult` 必须且只能包含一个 `response` 或 `interrupt`。
- `AgentInterrupt.payload` 与 `AgentResume.value` 按 `InterruptKind` 映射到
  `ClarificationResume`、`RecognitionReviewResume`、`SameItemReviewResume`、
  `MemoryConfirmationResume`，不得透传任意 dict。
- `CheckpointPort.claim_resume()` 对 `(session_id, interrupt_id)` 原子抢占；resume
  流程异常时调用 `release_resume()` 释放未完成抢占，成功恢复后的 claim 不释放，
  从而允许失败重试但拒绝重复副作用。
- `interrupt_id` 按
  `sha256(session_id | request_id | turn_id | kind | node_name | interrupt_generation)`
  计算；`interrupt_generation` 是 `AgentState` 中从 `0` 开始并在每次实际 interrupt
  产生时递增的持久化计数器，不能省略。
- `AgentEventRecord.event_id` 是 64 位十六进制稳定摘要；payload 只保存白名单元数据、状态和哈希。
  契约递归拒绝凭证、各类 DSN、原始用户文本/Prompt、图片 data URL 和模型原始输出，避免只依赖
  调用方自律完成脱敏。
- Memory 的 `MemoryMutation` 必须先通过 `domain/memory_policy.py` 白名单值域校验，
  `mutation_id` 与 `memory_id` 必须是 64 位小写十六进制 SHA-256；
  Cache key 使用 `canonical_cache_key()` 的 canonical JSON SHA-256；五类缓存 wrapper
  读取后还必须通过对应的 Pydantic、硬过滤或事实一致性校验，损坏载荷按 miss 处理，
  不得改变业务结果。Cache get/set/delete 故障增加 `cache_failure_total` 指标，
  同样不阻断业务。

## 7. 错误码（errors.py）

`InvalidRequestError`、`ImageUnavailableError`、`VisionUnavailableError`、
`ModelOutputInvalidError`、`UnknownCategoryError`、`ConstraintConflictError`、
`RetrievalUnavailableError`、`ProductSchemaInvalidError`、
`CheckpointUnavailableError`、`SessionConflictError`、`WorkflowStepLimitError`、
`TurnTimeoutError`。Pydantic 校验错误映射为 `ErrorCode` 后进入 FAILED 响应，
不泄漏内部细节。
