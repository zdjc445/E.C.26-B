# 跨来源商品归一化

> 本文描述当前实现。动态局部 Schema 的完整迁移与生产 DoD 仍以
> [`docs/plans/dynamic_product_schema_implementation_plan.md`](plans/dynamic_product_schema_implementation_plan.md)
> 为准；当前默认模式仍是 `taxonomy`，动态模式已具备纯领域校验、通用基线、端口和安全降级。

## 结论

商品归一化实现为独立应用服务，由 Retrieval Agent 和 Workflow 的 `normalize_candidates` 节点
共同调用。它不是独立自主 Agent：Schema 发现和字段抽取都是受约束的结构化调用，不允许规划、
工具循环或修改全局商品知识。

LLM 只提出 proposal；平台结构化字段、已验证 Schema 和确定性规则拥有最终决定权。同款候选、
冲突否决、Complete-Link SPU 聚类和 SKU 拆分仍然是确定性流程。

## 运行链路

```text
ProductRetrievalPort -> Offer[]
    -> taxonomy: TaxonomyNormalizer + ProductCanonicalizationPort
    -> dynamic: GenericNormalizer
              -> DynamicSchemaInductionPort
              -> verify_dynamic_schema + 服务端 schema_id
              -> DynamicProductCanonicalizationPort
              -> apply_dynamic_patch（accepted/descriptive_only/rejected/unresolved）
    -> NormalizedCandidate[]
    -> SameItemMatcher（Complete-Link）
    -> variant keys 拆分 SKU -> 价格聚合与排序
```

`PRODUCT_CANONICALIZATION_MODE` 控制策略：

- `taxonomy`：当前稳定默认路径，静态 Taxonomy 负责品类与属性角色。
- `dynamic_shadow`：并行计算动态结果，但不改变当前候选、SPU、SKU、排序或用户响应。
- `hybrid`：保留可信 Taxonomy 字段，只用动态结果补齐缺失字段。
- `dynamic`：使用通用规则基线和请求级动态 Schema；模型/缓存失败时每批保守回退。

Workflow 与 Multi-Agent 使用同一个 `canonicalize_offers` 应用服务，避免两条链路出现不同的
模型采纳策略。

## 信任边界

模型输出是 proposal，不是可信事实。每个非空字段都必须提供：

- 稳定 `offer_id`；
- 对应输入中真实出现的 `raw_value`；
- 字段级 `confidence`；
- 动态模式下属于同一 Offer 的 `EvidenceSpan`，或 Taxonomy 模式下属于同一 Offer 的字段证据。

动态路径中的 Schema 只在当前候选窗口或短期缓存内有效。`schema_id` 由服务端对验证后的规范
JSON 计算 SHA-256，不信任模型生成的 ID。证据必须能在同一 Offer 的 `title`、结构化核心字段
或属性字段中按 NFKC/casefold/空白规范化后连续找到；任何越界、跨 Offer 或伪造证据都不能被采纳。

采纳优先级：

```text
平台权威键 > 平台结构化原始事实的受控规范表达 > 有同 Offer 原文证据的 LLM 抽取
            > descriptive_only > 缺失
```

具体约束：

- 已有可信结构化字段不会被 LLM 静默覆盖；冲突被记录并拒绝。
- 动态属性角色只有 `identity`、`variant`、`descriptive`。
- 角色置信度低于配置门槛或支持 Offer 不足时统一降为 `descriptive`。
- 没有可靠 variant Schema 时，动态 SKU 拆分将 Offer 单列，除非存在一致的权威 `sku_key`。
- 型号、空白和通用 SI 单位经过确定性规范化，但通用基线不猜测品类、品牌或属性角色。
- 商品标题中的文本全部按不可信数据处理，Prompt 明确禁止执行其中的指令。
- 模型调用、结构化输出或缓存失败时，按批回退规则基线，不阻断检索。

## 规范标题与同款

系统使用采纳后的 `category_concept/category_id + brand + model + identity_attributes` 构造
`Offer.normalized_title`。只有同时存在品牌和型号锚点时才构造，避免仅凭品类或通用属性把不同
商品拉近。候选生成优先使用规范标题，缺失时回退平台原始标题。最终成对评分仍保留原始标题
相似度，并将规范标题信号封顶为 `0.95`。

动态模式不要求静态 `category_id` 存在；双方必须具有品牌+型号或相同权威 `same_item_key` 才能
进入自动同款合并，缺少锚点的高分 pair 最多进入 review。高置信且证据充分的动态概念冲突才是
硬冲突，Complete-Link 规则保持不变。

规范标题只用于候选和评分，不替换对用户展示的原始标题。variant attributes 不进入规范标题，
同一 SPU 的颜色、容量和套装差异留给后续 SKU 拆分处理。

## 批处理与缓存

- 默认 Taxonomy 归一化每批 20 条 Offer；动态 Schema 发现默认每批 60 条，动态字段归一化默认每批 20 条。
- Taxonomy 缓存键包含商品字段、Taxonomy 版本和 Prompt 版本。
- 动态 Schema 缓存键包含候选输入指纹、模型/Prompt 版本、通用规则版本和校验策略版本。
- 缓存不是正确性来源；读取、解析、版本不符、过期和写入错误都按 miss/降级处理。
- 只缓存 Pydantic 校验通过的结构化对象，不保存模型原始响应或 Prompt。

## 可观测性

当前记录以下 Taxonomy 指标：

- `product_canonicalization_model_batch_total`
- `product_canonicalization_cache_hit_total`
- `product_canonicalization_fallback_total`
- `product_canonicalization_rejected_field_total`

动态路径补充记录 `dynamic_schema_model_batch_total`、`dynamic_schema_cache_hit_total`、
`dynamic_schema_fallback_total`、`dynamic_schema_rejected_total{reason}`、
`dynamic_schema_role_demoted_total{reason}`、`dynamic_canonicalization_model_batch_total`、
`dynamic_canonicalization_cache_hit_total`、`dynamic_canonicalization_missing_item_total`、
`dynamic_canonicalization_field_total{status,field_kind}` 和
`open_world_candidate_total{decision}`。动态匹配节点另记录
`open_world_singleton_spu_total`、`open_world_singleton_sku_total` 和
`same_item_pair_total{verdict,mode}`。

`dynamic_shadow` 额外记录 `dynamic_shadow_candidate_diff_total` 和
`dynamic_shadow_field_diff_total`，并在状态中只保留候选数、字段差异数、品类补齐/冲突数、
品牌/型号/identity/variant/descriptive 差异数等计数，不保存原始标题、属性值或模型原始响应。
当前 shadow 差异仍只覆盖归一化字段；pair、SPU cluster 和 SKU group 的离线评测尚未完成。
Checkpoint 只保留 `schema_id` 及概念/assignment/采纳数摘要，不保存模型原始响应。

模型调用继续进入统一 `ModelCallRecord`，记录 Prompt 版本、模型、耗时、token、修复次数及输入输出
哈希。

## 评测要求

必须新增“不同平台写法、相同 SKU”样本，至少覆盖中英文品牌、型号分隔符、标题词序、单位、营销
词、缺失字段、未知品类和近型号负例。指标分层统计：

1. 品类 concept assignment 覆盖率与准确率；
2. 品牌、型号和属性规范化准确率与拒绝/降级率；
3. 候选生成 Recall；
4. 同款成对 Precision/Recall；
5. SPU 聚类与 SKU 拆分准确率；
6. 最终错比价率、模型成本、延迟与缓存命中率。

现有 provisional 模拟集不能替代真实平台数据和独立人工金标。

## 当前验证

- 已有单元测试覆盖中英文品牌、型号分隔符、字段冲突、伪造证据、模型失败回退、版本化缓存、
  shadow 输出隔离和 hybrid 只补缺失字段。
- 动态路径已具备纯领域契约、证据连续出现校验、角色降级、schema hash、通用规则基线、缓存
  失效和整批回退能力。
- 已有 Ark 适配器契约测试，验证结构化输出和商品文本 Prompt 注入边界。
- 在 provisional `same_item_pairs.jsonl` 的 600 对样本上按“规则归一化 → 候选生成 →
  成对判定”重算得到 TP=450、TN=150、FP=0、FN=0。该结果只说明当前模拟数据全部通过，
  不代表真实平台 LLM 归一化准确率或线上同款指标。

动态方案当前完成阶段 1 的主要代码能力，以及阶段 2 的字段级 shadow 差异记录和阶段 3 的
hybrid 缺失字段补齐入口。pair/cluster 差异评测、真实金标、生产灰度和完整发布门槛仍未完成，
因此不能将静态 Taxonomy 宣布为已被生产动态方案替代。
