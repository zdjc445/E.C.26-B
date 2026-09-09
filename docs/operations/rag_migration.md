# RAG 索引迁移与验收

本文记录原始 SKU/Offer RAG 的迁移边界和可重复验收步骤。它是运维说明，不把本地
fixture 或 dry-run 结果当作真实平台验收。

## 1. 产物身份

新索引使用 `raw-offer-v1` 数据契约。每次快照构建必须生成独立的 `IndexManifest`：

- `snapshot_id` 是输入 JSONL 的内容摘要；
- `manifest_id` 是完整 manifest 内容摘要；
- `search_text`、Dense embedding 和 Sparse 文本必须来自同一份 `raw-search-text-v1`；
- `valid_offer_count` 只统计 `record_kind=sku_offer` 且来源身份有效的记录；
- `product_summary` 保留在原始快照中，不进入可比 Offer 索引。

Milvus 部署将 `SHIJIAJING_RETRIEVAL_INDEX_VERSION` 设置为已发布的
`manifest_id`。本地快照路径则使用其 `snapshot_id` 作为检索身份。Prepared Query 的
指纹包含该身份，因此索引切换后不会复用旧查询缓存或旧会话查询。

## 2. Dry-run 与构建

先在独立输出目录生成报告，不能覆盖已有 manifest：

```bash
uv run shijiajing-index-products \
  <raw-offers.jsonl> \
  --dry-run \
  --manifest reports/rag/<snapshot-id>.dry-run.manifest.json
```

核对输出中的非法行、可索引 Offer 数、概要记录数、身份字段、价格口径和平台分布。
真实 Milvus 构建使用新的 collection 名，不在旧 collection 上执行默认覆盖：

```bash
export SHIJIAJING_MILVUS_COLLECTION=offers_raw_v1_<release>
uv run shijiajing-init-milvus
uv run shijiajing-index-products \
  <raw-offers.jsonl> \
  --manifest reports/rag/<release>.manifest.json
```

`--drop` 只允许用于已确认废弃的独立 collection；不能把线上旧 collection 作为迁移
目标。构建后的 manifest 必须保存到发布证据目录，并与快照和代码版本一起备份。

## 3. 切换顺序

1. 保存旧应用版本、旧 collection、旧快照、旧检索配置和旧报告摘要。
2. 对新快照执行 dry-run；身份冲突、过期更新、缺少真实 SKU 或价格口径的记录进入报告，
   不静默修复。
3. 在新 collection 完成建表、分批 embedding/upsert 和抽样回读，确认 Offer 原始属性、
   scope、价格基准、`search_text_hash` 和向量维度一致。
4. 用新 manifest 的 `manifest_id` 更新应用配置，清理/失效旧检索与 Schema cache，
   再执行 preflight。
5. 排空旧活动请求后切换应用。新请求进入 `agent-runtime-v2`；一次请求不跨 manifest
   混读。已完成旧 Ledger 和旧事件保留只读。
6. 保留旧应用、collection、快照和 manifest 作为完整回滚单元。回滚时整体切回，不在
   新 runtime 中增加旧 RAG 执行分支。

## 4. 验收矩阵

本地可重复检查：

```bash
uv run pytest -q
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run pyright
```

必须额外抽样确认：

- 相同 Offer 的 Dense/Sparse 输入等于保存的 `search_text`；
- Prepared Query 的 fingerprint 随约束版本、图片哈希或 manifest 变化；
- 数据库搜索尝试和 embedding 请求分别进入 runtime usage，失败/重试不冒充零成本；
- 新旧 manifest 不一致时拒绝把结果绑定到旧查询；
- `agent-runtime-v2` checkpoint 恢复不重跑已提交查询，不重置父预算；
- 本地词法降级明确标记 fallback，不声称执行了 Dense 检索。

## 5. 当前验收状态

仓库当前已具备：原始 Offer 契约、单源检索文本、不可覆盖 manifest、独立 collection
初始化入口、批量 embedding/upsert、查询身份绑定、物理调用计量、共享预算预留和离线
回归测试。

真实 Milvus、embedding provider、平台原始 SKU 快照、跨语言 Recall/Precision、线上
延迟与切换演练仍需在部署环境执行。没有这些证据前，发布门禁保持未就绪；本地 Fake、
dry-run 和 seed 数据只能证明契约与确定性边界。
