# shijiajing-provisional-sim-v1（provisional）

本目录由 `shijiajing-build-eval simulate → prepare → generate` 产出（Phase 1 方案）。

## 来源声明（必须阅读）

- 本数据集为**确定性模拟数据**（用户授权，2026-08-21）：商品、价格、平台均为
  生成器构造，不是真实商品页采集；`sources.jsonl` 使用保留域名 example.com。
- `trust_level=provisional`、`label_method=agent_only`、`gate_eligible=false`：
  **不可作为发布门禁**。晋级 frozen 需满足计划 §16 条件。
- 识别图片为 32x32 模拟主图（`image_domain=listing_image`），不冒充用户实拍。

## 文件

| 文件 | 行数 | 说明 |
|---|---|---|
| manifest.json | - | 数据集清单（含文件 SHA-256） |
| offers_snapshot.jsonl | 1000 | 脱敏 Offer 快照 |
| offer_labels.jsonl | 1000 | Agent Gold 标签目录 |
| asset_inventory.jsonl | 300 | 图片资产清单 |
| recognition_dataset.jsonl | 300 | 识别 |
| intent_dataset.jsonl | 300 | 意图 |
| retrieval_dataset.jsonl | 150 | 检索 |
| same_item_pairs.jsonl | 600 | 同款 |
| ranking_dataset.jsonl | 90 | 排序 |
| end_to_end_dataset.jsonl | 120 | 端到端多 Agent 执行 |

## 校验与评测

```powershell
uv run shijiajing-build-eval validate `
  --datasets-dir evals/datasets/provisional/v1 `
  --assets-dir evals/private/provisional_v1/raw/images
uv run shijiajing-eval --datasets-dir evals/datasets/provisional/v1 `
  --report-dir reports/provisional/v1 --no-gate
```
