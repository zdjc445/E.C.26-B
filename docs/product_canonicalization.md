# 开放域商品归一化

## 结论

商品归一化固定使用动态局部 Schema，不再提供模式开关。它是
Retrieval Agent 调用的应用服务，不是能自主规划或调用工具的独立 Agent。

LLM 只提出 Schema 和字段 proposal；原始商品、已验证 Schema 和确定性规则拥有最终决定权。
同款候选、硬冲突、Complete-Link SPU 聚类和 SKU 拆分仍由确定性代码完成。

## 运行链路

```text
ProductRetrievalPort -> Offer[]
    -> GenericNormalizer（通用规则基线）
    -> DynamicSchemaInductionPort（局部 Schema proposal）
    -> verify_dynamic_schema（原文、置信度、支持度、结构校验）
    -> DynamicProductCanonicalizationPort（按已验证 Schema 抽取字段）
    -> apply_dynamic_patch（accepted / descriptive_only / rejected）
    -> NormalizedCandidate[]
    -> SameItemMatcher（Complete-Link）
    -> dynamic variant keys 拆分 SKU
    -> 价格聚合与排序
```

Schema 发现默认每批 60 条，字段归一化默认每批 20 条。任一批模型超时、结构化输出非法、
Schema 校验失败或缓存损坏时，只将当前批次回退到 `GenericNormalizer`，不阻断其他批次和检索。

## 信任边界

模型输出不是可信事实。每个非空提议必须提供稳定 `offer_id`、字段置信度和属于同一 Offer 的
`EvidenceSpan`。系统对原文和证据执行 NFKC、大小写与空白规范化后，检查 `raw_value` 是否真实
连续出现在指定 `source_path` 中；越界、跨 Offer 或伪造证据不能被采纳。

`schema_id` 由服务端对验证后的规范 JSON 计算 SHA-256，不接受模型自报 ID。Schema 校验还会
限制 concept 数、属性数、assignment 唯一性、`canonical_key` 格式和 alias 唯一映射。

采纳优先级为：

```text
平台权威键 > 平台结构化事实的受控规范表达 > 有同 Offer 原文证据的模型提议
            > descriptive_only > 缺失
```

属性角色只有三种：

- `identity`：参与商品身份、规范标题和同款冲突判断；
- `variant`：同一 SPU 内拆分精确 SKU；
- `descriptive`：仅保留描述或审计信息，不进入硬判断。

角色置信度低于门槛或跨样本有效支持数不足时，`identity`/`variant` 会降为 `descriptive`。具体字段
值置信度不足、证据无效、字段不属于 Schema 或与结构化来源冲突时，字段直接 `rejected`。

## 通用规则基线

`GenericNormalizer` 不维护品类、品牌和属性角色枚举，只做跨品类稳定操作：Unicode NFKC、空白、
型号分隔符以及毫升/升、克/千克、瓦/千瓦等通用单位规范化。它保留平台已有属性桶，但不从标题
猜测未知语义。例如 `500 ml` 可确定性转为 `0.5L`，但不会猜“轴体”属于 identity 还是 variant。

没有可靠动态品类概念时，不用静态 `category_id` 制造同款硬冲突；没有品牌+型号或相同权威
`same_item_key` 时，不自动合并 SPU；没有可靠 variant Schema 或权威 `sku_key` 时，每个 Offer
单独形成 SKU 组。整体错误偏好是“漏合并优于错比价”。

## 批处理、缓存与观测

- `dynamic_schema` 缓存键包含候选输入指纹、模型/Prompt 版本、通用规则版本和校验策略版本；
- `dynamic_canonicalization` 缓存键额外包含服务端生成的 `schema_id`；
- 缓存只是性能优化，读取、解析、过期或写入失败均按 miss/降级处理；
- 只缓存通过 Pydantic 和领域校验的结构化对象，不保存模型原始响应或 Prompt。

核心指标包括 `dynamic_schema_model_batch_total`、`dynamic_schema_cache_hit_total`、
`dynamic_schema_fallback_total`、`dynamic_schema_role_demoted_total{reason}`、
`dynamic_canonicalization_model_batch_total`、`dynamic_canonicalization_cache_hit_total`、
`dynamic_canonicalization_missing_item_total`、
`dynamic_canonicalization_field_total{status,field_kind}` 和
`open_world_candidate_total{decision}`。

## 评测要求

真实评测至少覆盖未知品类、中英文品牌、型号分隔符、标题词序、单位、营销词、字段缺失和近型号
负例，并分层统计 concept assignment、字段采纳/拒绝/降级、候选 Recall、同款成对 Precision/Recall、
SPU 聚类、SKU 拆分、错比价率、延迟、成本与缓存命中率。现有 provisional 模拟集不能替代真实
平台数据和独立人工金标。
