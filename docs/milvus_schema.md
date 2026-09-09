# Milvus Schema 与索引

## 1. Collection 结构

CLI：`shijiajing-init-milvus`（src/shijiajing_agent/tools/init_milvus.py）。
全部地址/Token/模型来自 `SHIJIAJING_*`；集合已存在时默认报错退出，`--drop` 显式重建。

当前发布身份以 `IndexManifest` 为准。快照内容摘要是 `snapshot_id`，完整 manifest 内容摘要
是 `manifest_id`；查询、缓存和 runtime 结果必须绑定同一个 manifest，不能只用手工版本字符串
代替。

| 字段 | 类型 | 说明 |
|---|---|---|
| `offer_id` | VARCHAR(128) **主键** | 唯一报价 ID |
| `platform` | VARCHAR(32) | 平台 ID（taobao/jd/pinduoduo） |
| `source_product_id` / `source_updated_at` / `data_version` | VARCHAR | 采集源标识与版本 |
| `title` / `normalized_title` / `search_text` | VARCHAR | 标题与检索文本（search_text 由品类词+标题拼接） |
| `category_id` / `brand` / `model` | VARCHAR | 规范化品类/品牌/型号 |
| `same_item_key` / `sku_key` | VARCHAR | 采集源对齐键与 SKU 键 |
| `identity_attributes_json` / `variant_attributes_json` / `descriptive_attributes_json` | JSON | 身份/变体/描述属性 |
| `price` / `original_price` / `shipping_fee` / `coupon_amount` / `currency` | FLOAT/VARCHAR | 价格（实付 = price − coupon + shipping） |
| `shop_id` / `shop_name` / `seller_type` | VARCHAR | 店铺与卖家类型 |
| `rating` / `sales` / `review_count` / `delivery_days` | FLOAT | 质量与时效信号 |
| `source_payload_ref` | VARCHAR | 原始快照行引用（可追溯） |
| `text_dense` | FLOAT_VECTOR | 文本向量（维度按 embedding 模型契约首次调用后取） |
| `text_sparse` | SPARSE_FLOAT_VECTOR | SPLADE/BM25 稀疏向量 |
| `image_dense` | FLOAT_VECTOR（可选） | 图像向量，仅 `SHIJIAJING_IMAGE_EMBEDDING_DIMENSION` 显式提供时创建；**不伪造图像向量** |

索引：`text_dense` AUTOINDEX(IP)、`text_sparse` SPARSE_INVERTED_INDEX(IP)、
`image_dense` AUTOINDEX(IP)（存在时）。

## 2. 商品数据索引脚本

CLI：`shijiajing-index-products <snapshot.jsonl> [--batch 100]`
（src/shijiajing_agent/tools/index_products.py）。

- 输入与本地降级同源的**只读原始 Offer 快照**（JSONL，每行一个 `Offer`）。
- 仅 `record_kind=sku_offer` 且来源身份有效的记录进入可比索引；商品概要保留在快照中，
  不能伪装成 SKU 报价。
- `search_text` 由单一的 `raw-search-text-v1` 规则生成，并由 Dense、Sparse 与本地词法路径
  共享；索引脚本分批生成向量并 upsert，同时写入不可覆盖的 manifest。
- manifest 至少记录快照摘要、文本/分词/稀疏版本、embedding 模型与维度、距离度量、集合名和
  有效 Offer 数。dry-run 与正式构建必须使用独立输出路径。

## 3. 混合召回

`MilvusHybridRetrievalAdapter.search(query, image=..., ...)` 并行执行：

- **dense**：`text_dense` / `image_dense` 向量 Top-K（IP 相似度）。
- **sparse**：`text_sparse` 词法分数。
- **metadata**：`filter` 表达式实现硬过滤（与 `offer_matches_hard_filters`
  同一语义）——平台、价格区间、品牌、型号、评分/销量下限。
- 适配器保留各通道有界命中，不在这里做跨通道分数归一化。服务层按固定
  `best-query-channel-rrf-v1` 融合：每通道取同一 Offer 的最佳查询名次，RRF `k=RETRIEVAL_RRF_K`，
  截断到 `RETRIEVAL_UNION_LIMIT`（默认 200）。
- RRF 非空时固定进入云端 Reranker（生产百炼 `qwen3-rerank`），然后按商品/卖家桶轮转选择
  `MATCHING_CANDIDATE_LIMIT`（默认 60）条；精排失败完整回退 RRF 后再选择窗口。

每个 `PreparedQuery` 绑定当前 manifest 身份；约束版本、图片哈希、查询文本或 manifest 变化
都会改变 fingerprint。

返回 `RetrievalResult`（领域协议），每候选带 `channel_sources` 如实标注命中通道。

精排输入由安全摘要构造器生成，价格、评分、销量、店铺质量、`source_payload_ref`、联系方式、凭证、
session/request/owner 标识不进入模型文本。`RerankResult` 保存模型/指令/摘要/Token 版本、候选集指纹、
全量分数、延迟、费用和降级原因；未知/重复/缺失 ID、非有限分数或候选版本漂移整批拒绝。

## 4. 物理调用计量与降级路径

逻辑 `retrieval_calls` 不等于物理调用次数。Milvus 每次数据库搜索、Embedding provider
每次请求以及 Reranker 每次云端请求都会写入 runtime usage；批量检索在执行前预留
`db_search_attempts`、`embedding_calls` 和 `reranker_requests`，失败与重试仍按真实尝试计量。

Milvus 不可用（超时/连接失败）→ `local_fallback`：同一快照的本地 BM25
词法检索 + 相同硬过滤语义；响应标记 `fallback_used`，**不声称执行了向量检索**。
两者皆不可用 → `RetrievalUnavailableError` → 图进入 `build_failed_response`。
