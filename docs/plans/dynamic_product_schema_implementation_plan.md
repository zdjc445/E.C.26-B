# LLM 动态商品 Schema 实施方案

> 文档状态：目标设计（Target Design）；阶段 1 的契约、纯领域校验、通用基线和迁移入口已实现，
> 阶段 2 已具备字段级 shadow 差异记录、阶段 3 已具备缺失字段补齐入口，但 pair/cluster 评测与生产 DoD 尚未完成。
> 当前实现与运行行为见 [`docs/product_canonicalization.md`](../product_canonicalization.md)。
> 本方案的目标是逐步移除 `data/taxonomy.json` 对商品归一化、同款召回和 SKU 拆分的运行时准入作用。

## 1. 决策摘要

目标架构不再要求人工预先枚举品类、品牌别名、属性键、属性枚举以及
`identity/variant` 角色。系统改为：

1. 使用统一、与品类无关的结构化输出协议约束模型；
2. 由 LLM 对当前候选集批量生成请求级动态局部 Schema；
3. 再由 LLM 按已验证的局部 Schema 归一化每条 Offer；
4. 硬代码只处理跨品类不变的证据、冲突、一致性、置信度和安全降级规则；
5. SPU 判定、Complete-Link 聚类、SKU 签名与价格聚合继续保持确定性；
6. 模型、Schema 或缓存不可用时保留原 Offer，并保守地按独立商品处理，不阻断检索。

这里放弃的是**静态商品知识表**，不是结构化数据契约。运行时不再存在“品类必须先登记才能处理”
的条件，也不允许把品类规则重新写进 `if/elif` 硬编码。

## 2. 背景与当前问题

当前链路由 `TaxonomyNormalizer` 和 `data/taxonomy.json` 提供：

- 品类 ID 与别名；
- 品牌别名；
- 型号格式规则；
- `identity_attributes`、`variant_attributes` 和枚举值；
- 单位规则。

这种闭世界实现为现有演示数据提供了较强的确定性，但在开放电商域存在以下限制：

1. 未登记品类无法得到规范品类 ID；
2. 未登记属性不能成为模型补丁，无法参与同款或 SKU 判断；
3. 新品牌、新语言和平台新字段需要修改静态文件并发布；
4. 候选生成依赖规范品类，未知品类召回率天然受限；
5. 将更多规则搬入 Python 只会形成更难维护的隐式 Taxonomy；
6. 静态枚举无法覆盖同一属性在不同上下文中的不同角色，例如“容量”可能定义 SPU，也可能只是
   SKU 规格。

因此，目标不是扩大 `taxonomy.json`，而是把商品语义发现交给批量 LLM，把正确性边界留给
确定性代码。

## 3. 目标与非目标

### 3.1 目标

- 未登记品类、品牌、语言和属性可以进入归一化流程；
- 同一批候选使用一致的品类概念、属性键和值表达；
- 模型输出始终是 proposal，不能直接创建 SPU 或 SKU；
- 任一采纳字段都能回溯到同一 Offer 的原文位置；
- 低置信、角色不一致或证据不足的字段不会成为硬冲突依据；
- 模型和缓存失败不降低检索可用性，也不产生激进合并；
- Workflow 与 Multi-Agent 复用同一应用服务和采纳策略；
- 支持 shadow、hybrid、dynamic 分阶段迁移和一键回滚。

### 3.2 非目标

- 不让模型自主规划、调用工具或直接修改全局 Schema；
- 不在在线请求中自动发布长期商品知识；
- 不根据模型常识补充输入中不存在的型号、版本、容量或套装；
- 不用单次 LLM 判断替代 Complete-Link 聚类；
- 不把动态 Schema 缓存作为业务事实源；
- 不在本阶段建设完整的商品知识图谱或主数据平台。

## 4. 核心原则

### 4.1 通用协议不是 Taxonomy

通用协议只规定模型如何表达结果，不规定系统支持哪些商品：

- 固定核心字段：`offer_id`、`category_concept`、`brand`、`model`；
- 属性使用统一的 `canonical_key/canonical_value` 结构；
- 属性角色只能是 `identity`、`variant`、`descriptive`；
- 每个非空事实字段必须携带 `source_path`、`raw_value` 和字段置信度；
- 无法确认的字段进入 `unresolved_fields`。

协议中不得出现耳机、手机、背包等具体品类的属性清单。

### 4.2 LLM 发现语义，硬代码执行政策

LLM 可以提出：

- 哪些标题属于相同的局部品类概念；
- 不同语言或平台字段对应的规范属性键；
- 属性在当前商品上下文中的 `identity/variant/descriptive` 角色；
- 品牌、型号和属性的规范表达。

硬代码只负责：

- 输出结构和长度限制；
- `offer_id` 与输入集合一致；
- 原文证据真实存在且属于同一 Offer；
- 平台结构化事实优先；
- 字段、角色和批次一致性；
- 置信度门槛与不确定字段降级；
- 硬冲突否决、Complete-Link、SKU 签名和失败回退。

### 4.3 保守失败

系统的错误偏好是“漏合并优于错比价”：

- Schema 不确定：属性降为 `descriptive`；
- identity 不确定：不用于硬冲突或自动合并；
- variant 不完整：Offer 单独成为 SKU 组；
- 模型不可用：仅使用通用规则标准化；
- 匹配异常：所有候选拆成独立 SPU。

## 5. 目标运行链路

```text
ProductRetrievalPort -> RetrievalCandidate[]
    -> GenericNormalizer 通用规则基线
    -> DynamicSchemaInductionPort 批量发现局部 Schema
    -> verify_dynamic_schema 证据、支持度与一致性校验
    -> DynamicProductCanonicalizationPort 按已验证 Schema 批量归一化
    -> apply_dynamic_patch 字段级采纳、降级与审计
    -> OpenWorldNormalizedCandidate[]
    -> SameItemMatcherV2 候选与成对判定
    -> Complete-Link SPU 聚类
    -> verified variant attributes 精确拆分 SKU
    -> 价格聚合与排序
```

动态 Schema 只在当前请求或短期缓存范围内有效，不会在请求过程中写回全局配置。

## 6. 阶段 A：动态局部 Schema 发现

### 6.1 输入

Schema 发现以一次检索候选窗口为输入，默认不超过 `matching_candidate_limit`。每条输入只包含：

- `offer_id`、平台和来源标识；
- 原始标题；
- 平台结构化的品类、品牌、型号；
- 原始 identity、variant、descriptive 属性；
- 不包含价格、店铺评分等与商品身份无关的排序字段。

所有字符串都按不可信数据处理。Prompt 必须明确商品标题和属性值不是指令。

### 6.2 Schema proposal 契约

建议新增以下 Pydantic 契约；字段名为目标命名，实施时以 `contracts.py` 为唯一事实源：

```python
class EvidenceSpan(BaseModel):
    offer_id: str
    source_path: str
    raw_value: str
    start: int | None = None
    end: int | None = None

class DynamicAttributeProposal(BaseModel):
    canonical_key: str
    aliases: list[str]
    role: Literal["identity", "variant", "descriptive"]
    value_kind: Literal["string", "number", "boolean"]
    unit_family: str | None
    role_confidence: float
    support_offer_ids: list[str]
    evidence: list[EvidenceSpan]

class DynamicConceptProposal(BaseModel):
    local_concept_id: str
    canonical_label: str
    label_confidence: float
    evidence: list[EvidenceSpan]
    attributes: list[DynamicAttributeProposal]

class OfferConceptAssignment(BaseModel):
    offer_id: str
    local_concept_id: str
    confidence: float
    evidence: list[EvidenceSpan]

class DynamicSchemaProposal(BaseModel):
    concepts: list[DynamicConceptProposal]
    assignments: list[OfferConceptAssignment]
```

`local_concept_id` 只用于关联本次响应，不作为持久 ID。`schema_id` 必须由服务端对验证后的规范 JSON
计算哈希，禁止信任模型生成的 ID。

### 6.3 Schema 确定性校验

`verify_dynamic_schema()` 至少执行以下规则：

1. proposal 中所有 `offer_id` 必须属于当前输入；
2. 一个 Offer 最多有一个 concept assignment；
3. `source_path` 必须指向允许的原始字段；
4. `raw_value` 必须在该 `source_path` 中按 NFKC、casefold 和空白规范化后连续出现；
5. `canonical_key` 必须满足稳定键格式，例如 `^[a-z][a-z0-9_]{0,63}$`；
6. 同一个 concept 内 `canonical_key` 唯一且只能有一个角色；
7. 同一个 alias 不能映射到多个 canonical key；
8. `support_offer_ids` 必须能由证据重新计算，不能信任模型声明；
9. 未达到角色置信度或最小支持度的属性统一降为 `descriptive`；
10. 无有效概念证据的 assignment 被拒绝，该 Offer 使用开放域降级路径。

建议首版安全参数如下，最终值必须由离线金标校准：

| 参数 | 建议初值 | 行为 |
|---|---:|---|
| `dynamic_schema_concept_min_confidence` | `0.90` | 低于阈值不建立概念 assignment |
| `dynamic_schema_role_min_confidence` | `0.90` | 低于阈值降为 descriptive |
| `dynamic_schema_role_min_support` | `2` | 少于两个 Offer 支持时不作为硬角色 |
| `dynamic_schema_max_concepts` | `16` | 防止异常输出膨胀 |
| `dynamic_schema_max_attributes_per_concept` | `64` | 防止异常输出膨胀 |

单个 Offer 可以形成临时 concept，但其属性角色不能仅凭单条样本成为自动合并或 SKU 拆分依据。

## 7. 阶段 B：按局部 Schema 归一化 Offer

### 7.1 归一化 proposal 契约

```python
class DynamicCanonicalField(BaseModel):
    canonical_key: str
    canonical_value: str
    role: Literal["identity", "variant", "descriptive"]
    confidence: float
    evidence: EvidenceSpan

class DynamicCanonicalizationItem(BaseModel):
    offer_id: str
    local_concept_id: str | None
    category_concept: str | None
    category_confidence: float | None
    brand: str | None
    brand_confidence: float | None
    model: str | None
    model_confidence: float | None
    fields: list[DynamicCanonicalField]
    unresolved_fields: list[str]

class DynamicCanonicalizationBatch(BaseModel):
    schema_id: str
    items: list[DynamicCanonicalizationItem]
```

品牌、型号和品类也必须有对应证据。可以在最终契约中统一使用 `CanonicalValue` 包装，避免为三个
核心字段重复定义 evidence 字段。

### 7.2 通用规则基线

`GenericNormalizer` 不依赖任何商品知识，只执行：

- Unicode NFKC 和空白规范化；
- 比较用文本的 casefold；
- 型号中空白和常见分隔符的规范化，同时保留原值；
- 通用 SI 单位换算；
- 明确的平台权威键透传，例如 `same_item_key`、`sku_key`；
- 原始字段、标准值、规则版本和失败原因同时保留。

它不猜测品类，不维护品牌词典，也不决定属性角色。

### 7.3 字段采纳状态

每个模型字段经过 `apply_dynamic_patch()` 后只能处于以下状态之一：

| 状态 | 含义 | 后续用途 |
|---|---|---|
| `accepted` | 证据、置信度、Schema 和来源优先级均通过 | 可按角色参与匹配或 SKU |
| `descriptive_only` | 事实可信，但角色或批次一致性不足 | 只参与软召回/展示 |
| `rejected` | 无证据、冲突、越界或输出非法 | 不参与任何规范匹配 |
| `unresolved` | 模型明确无法判断 | 保留缺失和风险说明 |

### 7.4 采纳优先级

```text
平台权威键
    > 平台结构化原始事实的受控规范表达
    > 有同 Offer 原文证据的 LLM 抽取
    > descriptive_only
    > 缺失
```

平台结构化字段可以被转换为规范表面形式，例如 `索尼 -> Sony`，但不得被转换成另一个语义实体。
由于无静态品牌表时硬代码不能证明别名语义，首版必须遵循以下限制：

- 别名统一只能作为高置信软信号，不能单独触发自动 SPU 合并；
- 品牌和型号同时有证据且批次内表达一致时，才可组成强身份锚点；
- 原始结构化品牌与模型必须与规范值一起保留在审计数据中；
- 若模型对同一原值给出多个规范实体，则全部相关映射降为 `descriptive_only`。

硬代码能够验证 grounding 和一致性，但不能证明模型的语义判断绝对正确，因此自动合并必须依赖
多信号和 Complete-Link，而不是依赖单个模型字段。

## 8. 规范身份与同款判定

### 8.1 规范身份

验证后的候选生成两个独立表示：

```text
identity_text = category_concept + brand + model + sorted(accepted identity fields)
variant_text  = sorted(accepted variant fields)
```

原始标题始终保留。`identity_text` 只用于候选和评分，不替换用户展示标题。

### 8.2 候选生成

候选生成不再要求静态 `category_id` 存在，按信号强度分层：

1. 相同权威 `same_item_key`：直接进入候选；
2. 高置信 concept 兼容且品牌、型号规范值均一致：强候选；
3. concept 不确定但品牌、型号均有原文证据且一致：提高阈值后进入候选；
4. 型号缺失但 identity/title 多信号高度相似：只进入 review 候选；
5. 仅标题相似：不得自动合并；
6. 高置信品牌、型号或 accepted identity 字段冲突：直接否决。

品类 concept 的差异只有在双方高置信且证据充分时才作为硬冲突；否则作为软分数，不因模型标签漂移
直接切断召回。

### 8.3 成对评分与门槛

建议复用现有标题、identity、图像和来源键信号，但新增以下限制：

- `descriptive_only` 字段不得进入 identity overlap；
- 缺失维度继续从权重中移除并重新归一；
- 没有品牌+型号或权威键锚点时，分数再高也最多进入 `review`；
- 自动同款阈值在动态模式首版应高于当前闭世界阈值；
- review 对不参与自动聚类，只作为 HITL 或后续补证入口。

建议初始值：`accept=0.88`、`review=0.74`，必须通过真实未知品类金标校准后才能成为生产默认值。

### 8.4 Complete-Link 不变

两个簇合并时，跨簇每一对 Offer 都必须满足 `same`，或具有相同权威 `same_item_key`。任何缺失
pair、review pair、硬冲突 pair 都阻止合并。这样继续避免 `A≈B、B≈C、A≉C` 的传递误合并。

## 9. SKU 拆分

### 9.1 variant key 的采用

只有同时满足以下条件的动态属性才能成为 SKU key：

- 在已验证局部 Schema 中角色为 `variant`；
- `role_confidence` 达标；
- 支持 Offer 数达标；
- 当前 Offer 的字段证据和字段置信度达标；
- 同一局部 concept 内不存在角色冲突。

### 9.2 签名和缺失行为

```text
sku_signature = sorted(canonical_key=canonical_value)
```

- 签名相同的 Offer 才能进入同一 SKU 比价组；
- 缺少任一已采用关键 variant 的 Offer 单独成组；
- 没有可靠 variant schema 时，不得据此断言多个 Offer 是相同精确 SKU；
- 权威 `sku_key` 一致时可以旁路动态 variant，但仍保留来源审计；
- 价格去重、应付价计算和新鲜度聚合继续复用现有确定性实现。

## 10. 缓存设计

### 10.1 两级缓存

1. **精确结果缓存**：以规范化 Offer 输入、模型版本、Prompt 版本、校验策略版本组成键，缓存已通过
   Pydantic 校验的模型输出；
2. **已验证局部 Schema 缓存**：以候选概念指纹、模型版本、Prompt 版本、Schema 校验策略版本组成
   键，缓存 `VerifiedDynamicSchema`。

Schema 缓存是性能优化，不是事实源。命中后仍要检查输入字段、版本、TTL 和证据适用范围。

### 10.2 Schema 指纹

`schema_id` 由服务端计算：

```text
sha256(canonical_json(verified_schema_without_runtime_timestamps))
```

缓存键至少包含：

- Schema induction Prompt 版本；
- Canonicalization Prompt 版本；
- 模型标识；
- 通用规范化规则版本；
- Schema 校验策略版本；
- 候选概念/输入指纹。

### 10.3 缓存安全

- 读取异常、类型错误、版本不符和过期全部按 miss 处理；
- 写入异常只记录指标，不影响主流程；
- 缓存命中不得绕过字段证据校验；
- 只缓存结构化对象，不缓存模型原始自由文本；
- 缓存中不得保存密钥，原始商品文本按现有数据保留策略处理；
- 发现同一指纹产生不兼容 Schema 时驱逐缓存并降级，不选择性相信其中一个结果。

## 11. 故障与降级矩阵

| 故障 | 行为 | 是否继续检索 |
|---|---|---|
| 动态 Schema 功能关闭 | 使用当前 taxonomy 路径或通用规则基线，取决于迁移模式 | 是 |
| Schema induction 超时/异常 | 使用 GenericNormalizer；无可靠角色字段 | 是 |
| Schema proposal 非法 | 拒绝整份 Schema；记录原因；进入通用规则基线 | 是 |
| 部分 Offer 无 concept assignment | 仅这些 Offer 进入开放域降级，不影响其他 Offer | 是 |
| Canonicalization 批次失败 | 该批使用 GenericNormalizer | 是 |
| 单条模型结果缺失 | 该 Offer 使用 GenericNormalizer | 是 |
| 缓存读取/解析失败 | 按 miss 调模型；模型也失败时使用规则基线 | 是 |
| 缓存写入失败 | 忽略写失败并记录指标 | 是 |
| 字段证据伪造 | 拒绝字段 | 是 |
| 角色置信度不足/冲突 | 降为 descriptive_only | 是 |
| SKU 关键属性缺失 | Offer 单独 SKU | 是 |
| 同款算法异常 | 每个 Offer 独立 SPU | 是 |

通用规则降级时，除非有相同权威键或双方都有可信的结构化品牌+型号锚点，否则不执行跨来源自动
合并。

## 12. 安全与审计

### 12.1 Prompt 注入边界

- system prompt 明确声明商品标题、店铺名和属性值全部是不可信数据；
- 用户消息只包含长度受限的 JSON 数据；
- 使用结构化输出和 `extra="forbid"`；
- 限制 concept、attribute、evidence 和 unresolved 字段数量；
- 输出中的 `offer_id`、路径和证据全部由确定性代码复核；
- 修复 Prompt 只能要求满足同一 Schema，不能扩大任务权限。

### 12.2 决策审计

每个采纳或拒绝结果至少记录：

- 请求和 Offer 标识；
- Prompt、模型、校验策略与通用规则版本；
- `schema_id`；
- 字段原值、规范值、角色和证据路径的安全哈希；
- 字段状态与 reason code；
- role 降级、冲突否决、SPU 合并和 SKU 单列原因；
- 模型耗时、token、修复次数和缓存命中状态。

面向用户的响应不展示内部 Prompt 或完整模型原始响应。

## 13. 可观测性

建议新增：

- `dynamic_schema_model_batch_total`
- `dynamic_schema_cache_hit_total`
- `dynamic_schema_fallback_total`
- `dynamic_schema_rejected_total{reason}`
- `dynamic_schema_role_demoted_total{reason}`
- `dynamic_canonicalization_model_batch_total`
- `dynamic_canonicalization_field_total{status,field_kind}`
- `dynamic_canonicalization_missing_item_total`
- `open_world_candidate_total{decision}`
- `open_world_singleton_spu_total`
- `open_world_singleton_sku_total`
- `same_item_pair_total{verdict,mode}`
- `schema_drift_total{concept_fingerprint}`

Trace 中增加 `mode`、`schema_id`、`concept_count`、`accepted_field_count`、
`descriptive_only_count` 和降级原因，不写入未经脱敏的完整标题。

## 14. 代码改造范围

### 14.1 契约与端口

- `contracts.py`
  - 增加 Schema proposal、verified schema、证据 span、动态归一化输出和字段状态契约；
  - 保留现有 `Offer`、`MatchPair`、`SkuGroup` 对外兼容。
- `ports/models.py`
  - 增加 `DynamicSchemaInductionPort`；
  - 增加或升级 `DynamicProductCanonicalizationPort`，输入必须包含 verified schema；
  - 不允许适配器返回最终 `NormalizedCandidate` 或聚类结果。

### 14.2 领域层

- 新增 `domain/dynamic_schema.py`
  - Schema 校验、角色降级、服务端哈希和漂移比较；
- 新增 `domain/open_world_normalization.py`
  - `GenericNormalizer`、证据校验和动态补丁采纳；
- 调整 `domain/product_canonicalization.py`
  - 统一 `taxonomy/dynamic_shadow/hybrid/dynamic` 四种策略入口；
- 调整 `domain/same_item.py`
  - 移除动态模式对静态 category ID 的硬依赖；
  - 增加强身份锚点门禁和高置信 concept 冲突；
- 调整 `domain/sku.py`
  - 从 verified schema 读取当前 SPU 的 variant keys；
  - 缺失或不确定时单列。

领域层不得依赖 Ark 或具体缓存适配器。

### 14.3 模型适配器和 Prompt

- `adapters/ark_models.py`
  - 实现两个结构化端口；
  - 继续复用统一的重试、修复、调用记录和超时机制；
- 新增 `prompts/product_schema_induction.md`；
- 新增 `prompts/product_canonicalization_dynamic.md`；
- 两个 Prompt 独立版本化，任一版本变化都使相关缓存失效。

### 14.4 编排与配置

- `multi_agent/agents/specialists.py` 和 `nodes/retrieval_nodes.py`
  - 必须调用同一 `canonicalize_offers` 策略服务；
  - shadow 结果不能改变当前输出；
- `ports/dependencies.py`、`deps.py`
  - 注入两个新端口；
- `config.py`、`.env.example`、`docs/configuration.md`
  - 增加迁移模式、阈值、批大小和缓存 TTL；
- `state.py`
  - 只保存后续恢复确实需要的 verified schema 摘要和 `schema_id`，避免放大 Checkpoint。

建议配置：

```text
PRODUCT_CANONICALIZATION_MODE=taxonomy|dynamic_shadow|hybrid|dynamic
DYNAMIC_SCHEMA_BATCH_SIZE=60
DYNAMIC_SCHEMA_CONCEPT_MIN_CONFIDENCE=0.90
DYNAMIC_SCHEMA_ROLE_MIN_CONFIDENCE=0.90
DYNAMIC_SCHEMA_ROLE_MIN_SUPPORT=2
DYNAMIC_SCHEMA_CACHE_TTL_SECONDS=604800
DYNAMIC_CANONICALIZATION_BATCH_SIZE=20
DYNAMIC_CANONICALIZATION_FIELD_MIN_CONFIDENCE=0.80
DYNAMIC_SAME_ITEM_ACCEPT_THRESHOLD=0.88
DYNAMIC_SAME_ITEM_REVIEW_THRESHOLD=0.74
```

这些值是实施初值，不是未经评测即可上线的承诺。

## 15. 分阶段迁移

### 阶段 0：建立真实金标

- 从真实平台采集中英文品牌、型号分隔符、标题词序、属性错位和未知品类样本；
- 按已知品类、未知品类、近型号负例、同 SPU 不同 SKU 分层；
- 金标包含字段规范值、属性角色、同款 pair、SPU cluster 和 SKU group；
- 冻结数据版本并记录人工标注规范。

退出条件：数据可以区分字段抽取错误、角色错误、聚类错误和 SKU 错比价。

### 阶段 1：契约与纯领域校验

- 实现动态 Schema/归一化契约；
- 实现 `GenericNormalizer`、证据校验、角色降级和 schema hash；
- 用 fake model 覆盖所有拒绝和降级路径；
- 不接入生产编排。

退出条件：纯领域测试无外部依赖、完全可复现，非法模型输出不能越过校验层。

### 阶段 2：`dynamic_shadow`

- 在 Retrieval Agent 中并行执行动态链路；
- 不改变候选、SPU、SKU、排序或用户响应；
- 记录动态结果与当前 taxonomy 结果的字段、pair、cluster 差异；
- shadow 路径不允许产生业务缓存之外的副作用。

退出条件：获得足够真实差异样本，Schema 漂移和成本可量化。

### 阶段 3：`hybrid`

- 当前 taxonomy 可解析的商品继续使用现有结果；
- taxonomy miss 或字段缺失商品使用动态结果；
- 动态字段只能补缺，不覆盖当前可信结构化字段；
- 自动合并使用动态模式高阈值，其他结果进入 review 或 singleton。

退出条件：未知品类召回提升，且错误跨 SPU/SKU 合并不高于发布门槛。

### 阶段 4：`dynamic`

- 动态 Schema 成为主路径；
- `taxonomy` 模式保留一个发布周期作为显式回滚；
- `data/taxonomy.json` 不再作为请求时准入和属性角色事实源；
- 观察稳定后删除旧路径及其专用配置。

退出条件：生产灰度、回滚演练、缓存故障和模型故障演练全部通过。

## 16. 测试与评测

### 16.1 单元测试

- EvidenceSpan 正常、越界、跨 Offer 和伪造原文；
- 重复 concept assignment；
- alias 映射冲突；
- 同 key 多角色与低角色置信度降级；
- 未知品类和单样本 concept；
- 品牌中英文、型号分隔符和标题词序；
- structured source 与模型冲突；
- variant 缺失单列；
- Complete-Link 非传递合并；
- 缓存污染、版本失效和读写异常；
- 模型缺项、超时、修复失败和整批回退。

### 16.2 契约与工作流测试

- Ark 两阶段结构化输出符合 Pydantic 契约；
- 商品文本 Prompt 注入不能改变输出协议；
- Workflow 与 Multi-Agent 对相同输入产生相同 verified candidates 和 SKU groups；
- `dynamic_shadow` 不改变对外结果或副作用；
- `hybrid` 只对 miss/缺失字段启用动态补丁；
- `dynamic` 故障时检索仍成功并返回保守结果；
- Checkpoint 恢复不重复执行已缓存的模型批次。

### 16.3 离线指标

至少分层统计：

1. category concept assignment 准确率与覆盖率；
2. brand/model/attribute 规范化准确率；
3. identity/variant/descriptive 角色准确率；
4. proposal 字段接受、降级和拒绝率；
5. 同款候选 Recall；
6. pair Precision/Recall；
7. SPU B-cubed 或 pairwise 聚类指标；
8. SKU 拆分准确率；
9. 错误跨 SKU 比价率；
10. 模型调用数、token、p50/p95 延迟和缓存命中率。

### 16.4 初始发布门槛

以下是实施阶段的初始 gate，真实数据建立后可以调整，但必须版本化记录：

- 金标集错误跨 SKU 合并数为 `0`；
- 同款 pair precision 不低于当前 taxonomy 基线；
- 未知品类候选 Recall 相对当前基线至少提升 `5` 个百分点；
- 模型、缓存故障注入下请求成功率为 `100%`，结果允许降级为 singleton；
- 相同输入、模型版本、Prompt 和缓存内容下确定性后处理结果完全一致；
- shadow 模式对对外响应、账本、Memory 和事件副作用影响为 `0`；
- 成本和延迟满足发布时确定的服务预算，缺少生产证据时 fail-closed。

## 17. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 属性角色跨批次漂移 | SPU/SKU 边界不稳定 | 两阶段批处理、角色支持度、Schema cache、低置信降级 |
| 品牌别名误归并 | 不同品牌错合并 | 品牌不能单信号自动合并、保留原值、多信号门禁 |
| 型号近似误判 | 近型号错比价 | 通用格式化不删除实质字符、型号冲突硬否决 |
| 标题 Prompt 注入 | 输出越权或污染 Schema | 数据隔离提示、结构化契约、ID/证据复核、长度限制 |
| 缓存污染 | 错误跨请求复用 | 服务端 schema hash、版本键、命中后复核、漂移驱逐 |
| LLM 成本和延迟增加 | p95 与成本恶化 | 批处理、两级缓存、候选上限、shadow 量化 |
| 无模型时召回下降 | 更多 singleton | 保留 GenericNormalizer 和权威键路径，不牺牲正确性 |
| 动态 Schema 逐渐变成隐式 Taxonomy | 知识治理失控 | TTL、版本和审计；不把缓存作为永久事实源 |

## 18. 完成定义（DoD）

只有同时满足以下条件，才能宣布静态 Taxonomy 已被动态方案替代：

- 动态 Schema、归一化和 verified candidate 契约落地；
- 两阶段模型端口、Prompt 和结构化修复路径落地；
- 所有字段均经过同 Offer 证据校验和状态化采纳；
- 未知品类不再因缺少静态 category ID 被召回层直接排除；
- Complete-Link 和 SKU 缺失单列安全边界保持；
- Workflow/Multi-Agent 行为对齐；
- 四种迁移模式、指标、审计和回滚文档齐全；
- 单元、契约、工作流、故障注入和真实金标评测通过；
- 发布门槛包含生产外部证据，不能用模拟集替代；
- `data/taxonomy.json` 已不再参与生产请求决策，旧代码删除有单独回滚版本。

在 DoD 达成前，文档和对外说明必须将本方案标记为目标设计，不能描述为当前已上线能力。
