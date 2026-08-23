# 工程不变量夹具执行报告

- 总体结果：通过

| kind | n | passed | failed_ids |
|---|---:|---:|---|
| memory | 2 | 2 | — |
| multi_agent | 2 | 2 | — |
| interrupt | 4 | 4 | — |
| cache | 2 | 2 | — |

## 固定不变量

| name | samples | violations | status | evidence |
|---|---:|---:|---|---|
| user_hard_filter_violation_count | 6 | 0 | ✅ | Weighted/RRF/weighted_rerank 真实策略输出 |
| cross_user_memory_leakage_count | 2 | 0 | ✅ | SQLiteMemoryAdapter owner recall probe |
| replay_duplicate_side_effect_count | 2 | 0 | ✅ | SQLiteMemoryAdapter mutation replay |
| wrong_sku_group_count | 2 | 0 | ✅ | candidate sku_key → same_item_key consistency |
| price_fact_error_count | 6 | 0 | ✅ | 真实召回策略 model_copy 后 Offer.price 保持一致 |
| sensitive_field_leakage_count | 1 | 0 | ✅ | OpenTelemetry structured span projection |

Memory/Cache 使用真实 adapter；HITL 使用专用 resume 模型；固定不变量只覆盖本地工程夹具和脱敏投影；本报告不参与商品质量发布门禁。
