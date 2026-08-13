# 数据契约

跨层唯一数据形态是 `src/shijiajing_agent/contracts.py` 中的 Pydantic 模型（§5、§8）。
模型输出经 Pydantic + 语义双重校验后才是合法契约（§25）。

## 1. 核心模型

| 模型 | 用途 | 关键字段 |
|---|---|---|
| `AgentRequest` | 每轮输入 | `session_id`、`request_id`、`text`、`image`、`correction` |
| `AgentResponse` | 每轮输出 | `status`、`message`、`recognition`、`clarification`、`groups`、`notices` |
| `AgentStatus` | 状态枚举 | `success` / `clarification` / `failed` |
| `ImageRef` | 图片引用 | `image_id`、`uri`（data URL）、`content_type`、`sha256` |
| `RecognitionCorrection` | 用户修正（§6.3） | `recognition_id`（必须指向最新识别）+ `brand`/`model`/`category_id` |
| `RecognitionResult` | 识别输出 | `category_id`/`category_name`、`brand`、`model`、`attributes`、`overall_confidence` |
| `IntentPatch` | 意图增量 | `platforms`、`brand`、`model`、`category_id`、`attributes`、`price_range`、`negative_terms` 等 |
| `ShoppingConstraints` | 合并后约束 | 品牌/平台/价格/评分/销量/发货 + 硬过滤标记与来源（§12.3） |
| `RetrievalQuery` | 检索查询 | `query_text` + `hard_filters`（§13.4） |
| `RetrievalCandidate` | 候选 | `offer` + dense/sparse/recall 分数与通道来源 |
| `Offer` | 商品快照行 | `platform`（平台 ID）、`same_item_key`、`identity_attributes`、`variant_attributes`、`price`、`coupon_amount`、`shipping_fee`、`seller_type`、`rating`、`sales`、`source_updated_at` |
| `SkuGroup` | 比价组 | `group_id`、`sku_signature`、`min_price`、`average_price`、`price_range`、`offers`、`same_spu_key`（§15.1） |
| `Preference` | 排序偏好 | 价格/官方/评分/销量/发货（§15.4） |

## 2. 平台标识

`Offer.platform` 使用平台 ID（`taobao` / `jd` / `pinduoduo`），与真实数据契约一致；
中文别名（淘宝/京东/拼多多）只出现在展示与解释层，映射表见
`FactualConsistencyChecker._PLATFORM_NAMES`。

## 3. 硬过滤语义（§13.4）

`HardFilters` 与 Milvus filter 表达式、本地词法降级的
`offer_matches_hard_filters` 是**同一语义**（§25：同一领域协议）：
品牌/型号精确匹配、价格区间、平台、评分/销量下限、发货时效。
识别低置信约束不进入硬过滤（可放宽，见 workflow.md）。

## 4. 同款与 SKU（§14）

- 身份属性（`identity_attributes`）与变体属性（`variant_attributes`）分离：
  前者冲突 → 硬否决（不同 SPU）；后者差异 → 不同 SKU。
- `same_item_key` 是采集源对齐键；同款判定仍以属性+标题相似度为准。
- `SkuGroup.sku_signature` 由变体属性签名构成，同组内 SKU 唯一（§25）。

## 5. Checkpoint 序列化（§17.4）

- 状态经 `model_dump(mode="json")` 转 JSON 持久化；恢复时逐字段重建
  （`_SINGLE_MODEL_FIELDS` / `_LIST_MODEL_FIELDS` / `_ENUM_FIELDS` 驱动）。
- 证据束（`EvidenceBundle`）由纯 dataclass 按字段重建；`previous_state` 不入库。
- 模式版本 `SCHEMA_VERSION = "1.0"`；版本不符 → `CheckpointUnavailableError`。

## 6. 错误码（errors.py）

`InvalidRequestError`、`ImageUnavailableError`、`VisionUnavailableError`、
`ModelOutputInvalidError`、`UnknownCategoryError`、`ConstraintConflictError`、
`RetrievalUnavailableError`、`ProductSchemaInvalidError`、
`CheckpointUnavailableError`、`SessionConflictError`、`WorkflowStepLimitError`、
`TurnTimeoutError`。Pydantic 校验错误映射为 `ErrorCode` 后进入 FAILED 响应，
不泄漏内部细节。
