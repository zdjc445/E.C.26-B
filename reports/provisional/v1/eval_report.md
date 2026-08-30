# 识价镜 Agent 离线评测报告

- 生成时间：2026-08-21T02:25:36+00:00
- 数据来源：offline
- 可信等级：provisional
- 标签方法：agent_only
- 指标门禁：✅ 已测阻断指标全部达标
- 发布门禁资格：❌ 不具备（需 frozen + 人工仲裁）
- 发布门禁结果：❌ 未通过

> 说明：仓库内数据集为回归种子样例或 provisional 数据；只有 frozen + 人工
> 仲裁标签 + 全部阻断指标达标才可作为发布门禁，见 docs/evaluation.md。

## 数据集

| 数据集 | 行数 | recorded | 文件摘要 |
|---|---|---|---|
| recognition | 300 | 0 | b5d030025c02f4ab |
| intent | 300 | 0 | 86b1c31f50b39d1b |
| retrieval | 150 | 0 | aa9dc0a33d9d4313 |
| same_item | 600 | 0 | 2fd3362991b09be4 |
| ranking | 90 | 0 | 843c31d508bca4ee |
| end_to_end | 120 | 0 | e6bbcf19b01e00ca |

## 指标

| 指标 | 值 | n | 待测 | 阈值 | 阻断 | 状态 | 备注 |
|---|---|---|---|---|---|---|---|
| structural_output_success_rate | — | 0 | 300 | ge 0.99 | 否 | 待测 |  |
| category_accuracy | — | 0 | 300 | ge 0.9 | 否 | 待测 |  |
| brand_exact_match | — | 0 | 300 | — | 否 | 待测 |  |
| model_exact_match | — | 0 | 300 | — | 否 | 待测 |  |
| attribute_macro_f1 | — | 0 | 300 | — | 否 | 待测 |  |
| expected_calibration_error | — | 0 | 300 | — | 否 | 待测 |  |
| intent_field_macro_f1 | — | 0 | 300 | ge 0.92 | 否 | 待测 |  |
| clear_operation_accuracy | — | 0 | 300 | — | 否 | 待测 |  |
| conflict_detection_recall | — | 0 | 300 | — | 否 | 待测 |  |
| sku_recall_at_5 | — | 0 | 150 | — | 否 | 待测 |  |
| sku_recall_at_10 | — | 0 | 150 | — | 否 | 待测 |  |
| sku_recall_at_20 | — | 0 | 150 | ge 0.9 | 否 | 待测 |  |
| spu_recall_at_20 | — | 0 | 150 | — | 否 | 待测 |  |
| mrr_at_10 | — | 0 | 150 | — | 否 | 待测 |  |
| hard_filter_satisfaction_rate | — | 0 | 150 | eq 1 | 是 | 待测 |  |
| zero_result_rate | — | 0 | 150 | — | 否 | 待测 |  |
| same_item_pairwise_precision | 1 | 600 | 0 | ge 0.98 | 是 | ✅ |  |
| same_item_pairwise_recall | 0.82 | 600 | 0 | — | 否 | — |  |
| same_item_pairwise_f1 | 0.901099 | 600 | 0 | — | 否 | — |  |
| false_comparison_rate | 0 | 600 | 0 | le 0.01 | 是 | ✅ |  |
| sku_split_accuracy | 1 | 450 | 150 | ge 0.97 | 否 | ✅ |  |
| ndcg_at_5 | 0.977459 | 90 | 0 | — | 否 | — |  |
| ndcg_at_10 | 0.977459 | 90 | 0 | — | 否 | — |  |
| constraint_satisfaction_rate | 1 | 456 | 0 | — | 否 | — |  |
| top1_price_correct | 1 | 30 | 60 | — | 否 | — |  |
| explanation_factual_consistency_rate | 1 | 223 | 0 | eq 1 | 是 | ✅ | 模板解释按构造一致（内容仅来自证据）；模型文本由严格校验器 live 校验 |
| explanation_template_self_verify_rate | 0 | 223 | 0 | — | 否 | — | 严格校验器对排名序号与标题数字存在误报，仅作参考 |
| task_success_rate | — | 0 | 120 | ge 0.85 | 否 | 待测 |  |
| clarification_appropriateness | — | 0 | 120 | — | 否 | 待测 |  |
| correction_success_rate | — | 0 | 120 | — | 否 | 待测 |  |
| vlm_avoided_after_correction_rate | — | 0 | 120 | eq 1 | 否 | 待测 |  |
| fallback_rate | — | 0 | 120 | — | 否 | 待测 |  |
| avg_model_calls_per_turn | — | 0 | 120 | — | 否 | 待测 |  |
| multi_turn_state_exact | — | 0 | 120 | — | 否 | 待测 |  |
| latency_p50_ms | — | 0 | 120 | — | 否 | 待测 |  |
| latency_p95_ms | — | 0 | 120 | — | 否 | 待测 |  |

## 门禁

阻断指标无未达标项。

### 阻断指标待测（需 live 数据补齐）
- hard_filter_satisfaction_rate：未测量
