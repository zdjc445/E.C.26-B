# Retrieval 策略对比报告

- RRF k：60
- limit：20
- 推荐默认：`weighted`（正式门禁前保持 weighted）

| strategy | n | sku_recall_at_20 | spu_recall_at_20 | mrr_at_10 | hard_filter_satisfaction_rate | zero_result_rate | hard_filter_violation_count |
|---|---:|---:|---:|---:|---:|---:|---:|
| weighted | 2 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| rrf | 2 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |
| weighted_rerank | 2 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 0.000000 | 0 |

策略来自生产领域实现：WeightedScoreFusion、ReciprocalRankFusion、CandidateRelevanceReranker。此报告不证明正式线上数据质量，也不改变生产默认配置。
