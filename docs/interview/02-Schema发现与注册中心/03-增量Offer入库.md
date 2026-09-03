# 增量 Offer 入库

## 新 Offer 如何匹配注册中心中的 Schema

匹配采用两级路由：先使用 `platform + source_category_id` 精确查询；没有唯一精准结果时，再使用
商品标题通过 BM25 召回 Top-K Schema。

```text
新 Offer
→ platform + source_category_id 精确查询
├─ 唯一命中 ACTIVE Schema → 固定版本并直接执行字段映射
└─ 未命中或命中不唯一    → 标题 BM25 检索 → Top-K Schema
                              → 后续交给 LLM 消歧或返回 NO_MATCH
```

### 1. 新 Offer 提取路由字段

平台适配器先从增量事件中提取最小路由信息：

```jsonc
{
  "offer_key": "pinduoduo:92000003",
  "source_platform": "pinduoduo",
  "source_category_id": "600100",
  "product_name": "Keychron K2 84键机械键盘 蓝牙双模 红轴"
}
```

必须使用 `source_platform + source_category_id`，不能只使用 `category_id`，因为不同平台可能存在
相同的类目 ID。

### 2. 使用 category_id 精确匹配

注册中心将路由信息单独保存，通过 `schema_id` 与 Schema 整体信息关联：

```jsonc
{
  "route_id": "route_pdd_600100",
  "source_platform": "pinduoduo",
  "source_category_id": "600100",
  "schema_id": "product.mechanical_keyboard",
  "status": "ACTIVE"
}
```

规则服务执行等价于下面的查询：

```text
查找满足以下条件的路由：
source_platform = pinduoduo
source_category_id = 600100
status = ACTIVE
```

如果只命中一个 `schema_id`，继续读取它的当前生效版本：

```jsonc
{
  "schema_id": "product.mechanical_keyboard",
  "active_version": 1
}
```

还需要确认该版本存在当前平台可执行的 `field_bindings`。满足以下条件时得到直接匹配结果：

- 只命中一个 ACTIVE 路由。
- `schema_id` 对应的 `active_version` 存在。
- 当前平台和类目存在该版本的字段映射。
- Offer 的主要字段结构没有明显冲突。

```jsonc
{
  "decision": "DIRECT_MATCH",
  "route_id": "route_pdd_600100",
  "schema_id": "product.mechanical_keyboard",
  "schema_version": 1
}
```

得到 `DIRECT_MATCH` 后，后续直接执行注册中心中的 `field_bindings`，不需要调用 LLM 选择 Schema。

以下情况不能算精准匹配，需要进入标题 BM25 召回：

- `platform + source_category_id` 没有对应路由。
- 一个较粗的平台类目关联了多个 Schema。
- 路由存在，但对应 Schema 已停用。
- 路由存在，但缺少当前平台的字段映射或字段结构明显冲突。

### 3. 为每个 Schema 建立 BM25 路由文档

BM25 不检索完整的 Schema JSON，而是检索专门生成的轻量路由文档：

```jsonc
{
  "document_id": "product.mechanical_keyboard@1",
  "schema_id": "product.mechanical_keyboard",
  "schema_version": 1,
  "status": "ACTIVE",
  "category_name": "机械键盘",
  "category_aliases": ["机械式键盘", "游戏机械键盘"],
  "attribute_names": ["品牌", "型号", "轴体", "连接方式"],
  "representative_terms": ["青轴", "茶轴", "红轴", "蓝牙", "USB-C", "84键"],
  "search_text": "机械键盘 机械式键盘 游戏机械键盘 品牌 型号 轴体 青轴 茶轴 红轴 连接方式 蓝牙 USB-C 84键"
}
```

路由文档在 Schema 版本发布时生成，并且只为 ACTIVE 版本建立检索索引。其中：

- `category_name` 和 `category_aliases` 表示商品主体。
- `attribute_names` 来自 Schema 中的统一字段及平台别名。
- `representative_terms` 可以包含少量高区分度的枚举值和规格词。
- `search_text` 是最终用于分词和建立倒排索引的文本。

不能把所有商品标题直接拼接进去，否则品牌词和营销词会淹没真正的品类信息。

### 4. 使用商品标题进行 BM25 检索

对新 Offer 标题执行与路由文档相同的规范化和分词：

```text
原始标题：Keychron K2 84键机械键盘 蓝牙双模 红轴

分词结果：
Keychron / K2 / 84键 / 机械键盘 / 蓝牙 / 双模 / 红轴
```

中文分词时需要保留品牌、型号、键数、轴体和 `USB-C` 等中英文混合词。然后以分词结果查询
BM25 倒排索引，只检索 ACTIVE Schema 路由文档。

BM25 主要根据以下因素打分：

- 查询词和 Schema 路由文档的重合程度。
- 关键词在当前文档中的词频。
- 关键词在所有 Schema 中的稀有程度。
- 路由文档长度归一化。

例如可能得到：

```jsonc
{
  "decision": "TOP_K",
  "query_text": "Keychron K2 84键机械键盘 蓝牙双模 红轴",
  "candidates": [
    {
      "schema_id": "product.mechanical_keyboard",
      "schema_version": 1,
      "bm25_score": 12.7,
      "matched_terms": ["机械键盘", "84键", "蓝牙", "红轴"]
    },
    {
      "schema_id": "product.gaming_keyboard",
      "schema_version": 2,
      "bm25_score": 8.4,
      "matched_terms": ["键盘", "蓝牙", "红轴"]
    },
    {
      "schema_id": "product.keyboard_accessory",
      "schema_version": 1,
      "bm25_score": 3.1,
      "matched_terms": ["键盘"]
    }
  ]
}
```

`K` 可以先取 3。BM25 分数只在同一次查询的候选之间用于排序，不能把固定分数直接解释为概率。
如果 Top-1 低于通过验证集确定的最低召回门槛，则直接返回 `NO_MATCH`，不把无关候选交给 LLM。

### 5. Top-K 之后的处理边界

标题中可能出现“适用于机械键盘的键帽”，因此 BM25 命中“机械键盘”并不代表商品主体就是机械键盘。
Top-K 只表示可能匹配的候选，后续 LLM 必须被限制为：

```text
从 Top-K 中选择一个 schema_id + schema_version
或者返回 NO_MATCH
```

LLM 不能创建新的 Schema，也不能选择候选列表之外的 Schema。服务端还需要校验选择结果、原文证据、
字段类型和重要属性覆盖情况。

如果 LLM 返回 `NO_MATCH`，系统保存原始 Offer 并送入 Schema 发现队列。单条 Offer 不会直接创建
Schema；发现队列需要按照平台类目和相近字段结构聚合多条样本，再执行阶段一发现。

如果某个没有精确路由的平台类目连续多次通过 BM25 和后续校验命中同一 Schema，可以离线生成新的
`schema_route` 和平台 `field_bindings`，验证通过后再发布到注册中心。之后该类目的 Offer 就可以走
category_id 精确匹配。

### 6. 固定版本校验

确定 Schema 后，先把本次转换使用的 `schema_id + schema_version` 固定下来；如果命中了可执行的平台
映射，还要同时固定 `route_id + binding_version`。校验时始终读取这些不可变版本，不能在处理中途自动切换到
最新版本。

无论前面是规则直接填值，还是 LLM 从 Top-K 中选择并填值，最终都进入同一个校验器，主要检查：

- **版本一致性**：Schema 和字段映射版本存在、处于可用状态，而且二者声明的版本关系一致。
- **结构约束**：输出字段必须属于该版本 Schema，必填字段不能缺失，字段类型必须正确。
- **枚举与业务约束**：例如 `switch_type` 只能取该版本允许的枚举；价格必须大于等于 0，币种和价格单位必须统一。
- **原文证据**：每个动态字段都要能追溯到原始 Offer 的字段路径和值，防止 LLM 凭空补充属性。
- **映射重放**：存在 `field_binding` 时，规则服务重新执行映射，并比较结果；LLM 结果与规则冲突时以规则为准或拒绝入库。
- **role 约束**：字段的 `identity / variant / descriptive` 只能读取注册中心定义，LLM 不能自行修改 role。

例如固定使用机械键盘 Schema v1 时，原始值“红轴”按照绑定规则转换为 `red`，且 `red` 在 v1 的
枚举集合中，因此通过；如果输出 `silver`，但 v1 没有该枚举，则不能直接修改 v1，可以将该值保留到
`unmapped_attributes` 并进入 Schema 演进队列。

校验结果分为：`PASS` 进入商品库，`SCHEMA_MISMATCH` 进入 Schema 发现或演进队列，`INVALID_OUTPUT` 进入重试或错误队列。工程上可以使用
JSON Schema 或 Pydantic 做结构校验，再用自定义规则完成版本、证据、映射重放和 role 校验。

### 7. 校验通过后写入商品库和 Milvus

校验结果为 `PASS` 后，按照下面的链路完成入库：

```text
标准 Offer
→ 按 offer_id 幂等写入商品库
→ 根据 role 生成统一的 search_text
→ Embedding 模型生成 dense_vector
→ 将 search_text、dense_vector 和元数据写入 Milvus
→ Milvus 内置 BM25 自动生成 sparse_vector
```

#### 7.1 标准 Offer 写入商品库

商品库保存完整的 `basic_data`、`dynamic_attributes`、`unmapped_attributes`、原始数据引用以及
`schema_id + schema_version`。使用 `source_platform + source_sku_id` 生成唯一的 `offer_id`，
并以它作为幂等键执行新增或更新。商品库是事实源，后续可以用它重新生成 Milvus 索引。

#### 7.2 生成统一检索文本

根据注册中心定义的 role，选取商品名、`identity`、`variant` 和重要的 `descriptive` 字段：

```text
机械键盘；品牌：Keychron；型号：K2；轴体：青轴；
键数：84键；连接方式：蓝牙、USB-C
```

品牌和型号帮助识别 SPU，轴体等 `variant` 字段帮助区分 SKU，描述字段用于补充语义。价格和库存变化
频繁，不放入检索文本，而是作为 Milvus 的标量字段保存。

#### 7.3 生成 Dense 和 BM25 Sparse

```text
search_text ──→ Embedding 模型 ──→ dense_vector（语义匹配）
      │
      └──────→ Milvus 中文 Analyzer + BM25 Function
                                     └─→ sparse_vector（关键词匹配）
```

Dense 向量由外部 Embedding 模型生成。BM25 Sparse 向量由 Milvus 对 `search_text` 分词后自动生成，
业务服务不需要自己计算。`K2`、`84键`、`青轴` 等精确规格主要由 BM25 命中，“适合办公的无线键盘”
这类表达主要由 Dense 向量命中。

Milvus Collection 需要提前配置 Dense 向量索引、`SPARSE_INVERTED_INDEX`，以及
`search_text → sparse_vector` 的 BM25 Function。

#### 7.4 写入 Milvus

每个标准 SKU Offer 对应一条 Entity，使用 `offer_id` 作为主键执行 `upsert`：

```jsonc
{
  "offer_id": "pinduoduo:92000001",
  "search_text": "机械键盘 品牌 Keychron 型号 K2 轴体 青轴 84键 蓝牙 USB-C",
  "dense_vector": [0.12, -0.31, 0.56], // 仅示意，实际维度由 Embedding 模型决定
  "schema_id": "product.mechanical_keyboard",
  "schema_version": 1,
  "source_platform": "pinduoduo",
  "category": "mechanical_keyboard",
  "price": 419.00,
  "listing_status": "onsale"
}
```

写入时不需要传 `sparse_vector`，Milvus 会根据 `search_text` 自动生成。最终一条 Entity 同时包含
Dense、Sparse 和标量字段，可以用于语义召回、BM25 关键词召回以及价格、平台和状态过滤。

### 8. 最终匹配与入库流程

```text
新 Offer
→ 查询 schema_route(platform, source_category_id)
  ├─ 唯一 ACTIVE 路由且映射完整
  │  → DIRECT_MATCH
  │  → schema_id + active_version
  │  → 规则直接填值
  │  → 固定版本校验
  │
  └─ 未精准匹配
     → 使用 product_name 查询 BM25 Schema 索引
     → 过滤低于最低门槛的结果
     → 返回 Top-3 ACTIVE Schema
     → LLM 选择其中一个或返回 NO_MATCH
        ├─ MATCH    → 固定版本后进入字段填值和固定版本校验
        └─ NO_MATCH → 回到 Schema 发现队列

固定版本校验通过
→ 标准 Offer 写入商品库
→ 生成 search_text 和 dense_vector
→ 按 offer_id upsert 到 Milvus
→ Milvus BM25 Function 自动生成 sparse_vector
```

面试时可以概括为：

> 新 Offer 首先使用 platform 和 category_id 精确匹配 Schema，没有精准路由时再通过标题 BM25 召回 Top-K，并让 LLM 在候选中选择或返回 NO_MATCH。固定版本校验通过后，标准 Offer 先幂等写入商品库，再按 role 生成 search_text：Embedding 模型生成 Dense 向量，Milvus 内置 BM25 生成 Sparse 向量，最后按 offer_id 写入 Milvus。
