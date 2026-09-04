# Schema 发现、注册与检索口播稿

> 建议时长：约 10 分钟。下面内容可以直接口述。

我在识价镜里重点解决的一个问题，是怎样把淘宝、拼多多等平台结构不同的商品数据，统一成可以跨平台检索、
聚合和比价的标准 Offer。

我设计了一套生产化演进方案，整体分为三个部分：Schema 发现与注册、增量 Offer 入库，以及在线
混合检索。

一、先讲 Schema 发现。不同平台表达同一个商品属性的方式差别很大。

比如同样是 Keychron K2 机械键盘，淘宝可能用 `title` 表示商品名，通过 `pid:vid` 表示“轴体等于青轴”；
拼多多使用 `goods_name` 表示商品名，在 `sku_list.spec` 中用“轴体类型等于青轴”表达 SKU 规格。

因此我先定义了一组所有品类都需要的固定字段，比如来源平台、平台商品和 SKU ID、商品名、品牌、价格、
运费和在售状态。这部分由平台适配器按确定性规则抽取。
固定字段消费过的原始路径会记入 `consumed_paths`，避免品牌之类的字段又重复进入动态属性。

剩余的结构化属性先进入 `unmapped_attributes`。平台适配器还会保留 role 证据，例如淘宝的
`is_key_prop`、`is_sale_prop`，或者某个字段是否位于拼多多的 SKU 规格中、是否真的在不同 SKU 之间
变化。离线任务再汇总同品类的多条 Offer，形成候选池。

第一阶段 LLM 的工作不是直接填写商品，而是合并不同平台中的同义字段。比如把淘宝的“轴体”和拼多多的
“轴体类型”统一成 `switch_type`。为了限制模型输出，我会给每个候选属性分配 `candidate_id`，要求 LLM
生成的每个统一字段必须引用输入候选，服务端再验证引用、原始路径和枚举值，避免模型凭空生成属性。

接下来还要用统计信息判断这个字段是否值得进入 Schema，例如字段在同品类 Offer 中的覆盖率、类型一致性、
平台支持度，以及它在多 SKU 商品中的变化率。证据不足的字段继续积累样本，明显是噪声的字段直接拒绝，
只有稳定的字段才进入 Schema 草案。

字段 role 也不是完全交给 LLM 决定。LLM 只给建议，最终由平台信号和统计规则确认。像品牌、型号这类在同一
商品的 SKU 间保持稳定，并且能区分不同商品的字段，可以作为 `identity`；轴体、颜色这类位于销售规格中，
并且确实随 SKU 变化的字段，可以作为 `variant`；连接方式、材质等只对检索和展示有帮助的字段，则作为
`descriptive`。价格、库存和促销属于交易信息，不参与 role 判断。

Schema 草案通过原文证据、类型、枚举、role 和兼容性校验后，才会发布到 Schema Registry。注册中心主要
保存四部分数据：第一是 `schema_route`，负责用平台和原平台 category ID 精确找到 Schema；第二是
`schema_search_index`，用于精确路由失败后的 BM25 模糊召回；第三是不可变的 `schema_version`，保存统一
字段、类型、role 和约束；第四是 `field_binding`，保存某个平台的原始字段怎样提取并转换成统一字段。

版本发布以后不能原地修改。字段定义变化时发布新的 `schema_version`，平台字段路径或转换规则变化时发布
新的 `binding_version`。标准 Offer 会记录自己实际使用的 Schema 和映射版本，因此以后即使 ACTIVE 版本
发生变化，也可以复现当时的转换结果。

第二部分是增量 Offer 入库。新 Offer 到来后，先使用 `platform + category_id` 查询
`schema_route`。如果唯一命中 ACTIVE Schema，而且对应的 `field_binding` 完整，就直接执行规则转换，不
调用 LLM。

如果 category ID 没有命中、类目太粗或者映射不完整，就使用商品标题查询 Schema 的 BM25 搜索索引，召回
Top-K ACTIVE Schema。阶段二 LLM 只能从候选中选择一个并填值，或者返回 `NO_MATCH`，不能选择候选以外
的 Schema，也不能直接创建新 Schema。连续出现的 `NO_MATCH` Offer 会回到离线发现队列，聚合成多条样本
后再执行阶段一。

无论走规则转换还是 LLM 候选消歧，最后都进入相同的固定版本校验。这里会检查版本引用、字段白名单、必填
字段、类型和枚举，还会校验每个动态属性是否能追溯到原始 Offer。存在 `field_binding` 时，规则服务还会
重新执行一次映射进行比对。比如机械键盘 Schema v1 只允许 `blue`、`brown` 和 `red`，模型输出
`silver` 时不能修改 v1，而是进入 Schema 演进流程。

校验通过后，完整标准 Offer 先按 `offer_id` 幂等写入商品库。然后根据 role 生成 `search_text`，内容包含
商品名、identity、variant 和重要的 descriptive 字段。价格和库存变化频繁，只作为元数据保存。

同一份 `search_text` 会生成两套检索表示：外部 Embedding 模型生成 Dense 向量，用于语义召回；Milvus
内置 BM25 Function 经过中文分词后自动生成 Sparse 向量，用于匹配品牌、型号和规格词。每个标准 SKU
Offer 作为一条 Entity，连同平台、品类、价格、状态和 Schema 版本一起，按照 `offer_id` upsert 到
Milvus。商品库保存完整事实，Milvus 保存可重建的检索副本。

最后是在线检索。用户请求到来后，如果上游已经知道品类，就直接读取对应的 ACTIVE Schema；否则先用原始
请求查询 `schema_search_index`，通过 BM25 找到候选 Schema。确定版本后，再按照它的字段、role 和枚举
生成标准 Query。

例如用户说“找一个五百元以内的 Keychron K2 青轴无线机械键盘”，系统会把品牌 Keychron 和型号 K2
整理为 identity 条件，把青轴归一化成 `switch_type=blue` 作为 variant 条件，把价格、币种和在售状态
作为硬过滤。“无线”可能同时表示蓝牙或 2.4G，如果语义还不明确，就先作为软偏好，避免过早过滤掉正确商品。

标准 Query 最终产生三部分：`dense_text` 用来生成 Query Dense 向量，`bm25_text` 保留品牌、型号、规格
原词和统一枚举，`hard_filters` 用于限制 Schema、价格和状态。

检索时，Milvus 在元数据过滤范围内并行执行 Dense ANN 和 BM25 召回。Dense 更适合“适合办公的无线键盘”
这类语义表达，BM25 更适合 `Keychron`、`K2` 和“青轴”这类精确词。因为两路分数尺度不同，我优先使用
RRF 按排名进行融合，得到 Top-N `offer_id`。

服务端再根据这些 ID 回查商品库，读取最新价格、库存和原始证据。随后根据 `identity` 字段把不同平台的
同款商品聚合成 SPU，再根据 `variant` 字段拆分具体 SKU，并在统一价格口径后排序。返回之前还要检查商品
是否仍然在售、价格条件是否一致，以及聚合和规格判断能否追溯到原始证据。

这套设计的关键是把 LLM 放在语义发现和歧义处理的位置，把字段映射、版本、role 和最终校验交给可复现的
规则系统。这样首次遇到新结构时可以发现 Schema，后续大多数增量 Offer 又能直接复用已发布规则，同时保留
跨平台检索、同款聚合和 SKU 比价所需的结构化信息。
