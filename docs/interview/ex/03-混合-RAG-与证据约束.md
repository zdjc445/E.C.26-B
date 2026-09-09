# 混合 RAG、Offer 身份与证据约束

> 本文讲解当前 `raw-offer-v1` RAG 实现；旧的 Supervisor 重规划描述已移除。

## 1. 先保证商品事实不丢失

索引最小单元是原始 `Offer`，而不是只含标题的商品摘要。Offer 保留平台、来源版本、身份属性、
变体属性、价格基准、店铺和可追溯的 `source_payload_ref`。只有来源身份有效的 `sku_offer` 进入
可比索引，概要记录不能冒充 SKU 报价。

检索文本只由一份 `raw-search-text-v1` 规则生成。Dense、Sparse 和本地词法降级共享同一文本，
避免“入库文本”和“查询文本”各自拼接后产生不可解释的偏差。

## 2. 混合召回与明确降级

```text
PreparedQuery
  ├─ text dense
  ├─ sparse lexical
  ├─ image dense（有真实图片向量时）
  └─ metadata hard filter
        ↓
通道结果 → 分数融合 → 有界候选池 → 动态归一化与资格校验
```

品牌、型号、预算、平台等可下推条件在数据库侧过滤，但返回候选仍由
`offer_matches_hard_filters()` 复核；`unknown` 不算满足。Milvus 超时或不可用时可以回退同一
快照的 BM25 词法检索，响应标记 `fallback_used`，不会伪装成执行了 Dense 检索。

## 3. 查询和索引身份

每次快照发布生成 `IndexManifest`：

- `snapshot_id` 是输入快照内容摘要；
- `manifest_id` 是完整 manifest 内容摘要；
- manifest 固定文本生成、tokenizer、sparse、embedding、维度、距离和有效行数。

`PreparedQuery` 的 fingerprint 包含 `constraints_version`、图片哈希和 `index_manifest_id`。
补充检索只使用主 Agent 已提出的有界文本，不重复触发 query rewrite；索引切换后旧查询和缓存
不能误复用。

## 4. 资格校验与回答

召回后的固定顺序是：动态局部 Schema 或通用基线 → 需求三态匹配 → Complete-Link 同款聚类 →
SKU 拆分 → 价格与偏好排序 → 证据构建 → 回答。模型可以提出查询或解释，但不能改变硬条件、
商品价格、SKU 分组或缺失证据的语义。

解释只允许引用登记的证据字段。模型解释需通过事实一致性检查；失败时使用明确标记的模板
降级。没有来源详情时只能报告证据不足，不能把快照价格描述成实时优惠资格。

## 5. 物理调用预算

`retrieval_calls` 只表示逻辑检索动作；数据库搜索次数、embedding 请求次数和 embedding 输入/Token
单独计量。批量动作执行前预留剩余额度，执行后按真实用量结算；失败与重试不能按零成本处理。

## 6. 代码位置

- 查询/manifest 契约：`src/shijiajing_agent/rag_contracts.py:45`
- Offer 预处理：`src/shijiajing_agent/domain/raw_offer.py:1`
- Milvus 混合适配器：`src/shijiajing_agent/adapters/milvus_retrieval.py:1`
- 本地词法降级：`src/shijiajing_agent/adapters/local_retrieval.py:1`
- 查询服务：`src/shijiajing_agent/services/retrieval.py:70`
- 索引 manifest：`src/shijiajing_agent/tools/index_products.py:262`
