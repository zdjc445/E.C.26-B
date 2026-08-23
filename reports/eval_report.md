# 识价镜 Agent 离线评测报告

- 生成时间：2026-08-22T09:01:22+00:00
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
| recognition | 4 | 3 | 9ab33e6c2ad99dd8 |
| intent | 4 | 3 | 17035fd6a72bb7a4 |
| retrieval | 3 | 2 | 7dc92fb58b421cb3 |
| same_item | 5 | 0 | 76598cb0905895aa |
| ranking | 3 | 0 | d8f656321db5f261 |
| workflow | 3 | 3 | f0490463afb0ce47 |
| memory | 2 | 0 | c3dcc40cb06f420e |
| multi_agent | 2 | 0 | ec3f0b5807d7862b |
| interrupt | 4 | 0 | 28ff5c7c21ea9b4b |
| cache | 2 | 0 | a7b7ffa6a82d569b |
| retrieval_strategy | 2 | 0 | 777a7411e0305316 |

## 指标

| 指标 | 值 | n | 待测 | 阈值 | 阻断 | 状态 | 备注 |
|---|---|---|---|---|---|---|---|
| structural_output_success_rate | 1 | 3 | 1 | ge 0.99 | 否 | ✅ |  |
| category_accuracy | 1 | 3 | 1 | ge 0.9 | 否 | ✅ |  |
| brand_exact_match | 0.666667 | 3 | 1 | — | 否 | — |  |
| model_exact_match | 0.666667 | 3 | 1 | — | 否 | — |  |
| attribute_macro_f1 | 0.888889 | 3 | 1 | — | 否 | — |  |
| expected_calibration_error | 0.296667 | 3 | 1 | — | 否 | — |  |
| intent_field_macro_f1 | 1 | 3 | 1 | ge 0.92 | 否 | ✅ |  |
| clear_operation_accuracy | 1 | 3 | 1 | — | 否 | — |  |
| conflict_detection_recall | 1 | 1 | 2 | — | 否 | — |  |
| sku_recall_at_5 | 1 | 2 | 1 | — | 否 | — |  |
| sku_recall_at_10 | 1 | 2 | 1 | — | 否 | — |  |
| sku_recall_at_20 | 1 | 2 | 1 | ge 0.9 | 否 | ✅ |  |
| spu_recall_at_20 | 1 | 2 | 1 | — | 否 | — |  |
| mrr_at_10 | 1 | 2 | 1 | — | 否 | — |  |
| hard_filter_satisfaction_rate | 1 | 2 | 1 | eq 1 | 是 | ✅ |  |
| zero_result_rate | 0 | 2 | 1 | — | 否 | — |  |
| same_item_pairwise_precision | 1 | 5 | 0 | ge 0.98 | 是 | ✅ |  |
| same_item_pairwise_recall | 1 | 5 | 0 | — | 否 | — |  |
| same_item_pairwise_f1 | 1 | 5 | 0 | — | 否 | — |  |
| false_comparison_rate | 0 | 5 | 0 | le 0.01 | 是 | ✅ |  |
| sku_split_accuracy | 1 | 2 | 3 | ge 0.97 | 否 | ✅ |  |
| ndcg_at_5 | 1 | 3 | 0 | — | 否 | — |  |
| ndcg_at_10 | 1 | 3 | 0 | — | 否 | — |  |
| constraint_satisfaction_rate | 1 | 8 | 0 | — | 否 | — |  |
| top1_price_correct | 1 | 2 | 1 | — | 否 | — |  |
| explanation_factual_consistency_rate | 1 | 7 | 0 | eq 1 | 是 | ✅ | 模板解释按构造一致（内容仅来自证据）；模型文本由严格校验器 live 校验 |
| explanation_template_self_verify_rate | 0 | 7 | 0 | — | 否 | — | 严格校验器对排名序号与标题数字存在误报，仅作参考 |
| task_success_rate | 1 | 3 | 0 | ge 0.85 | 否 | ✅ |  |
| clarification_appropriateness | 1 | 3 | 0 | — | 否 | — |  |
| correction_success_rate | 1 | 1 | 2 | — | 否 | — |  |
| vlm_avoided_after_correction_rate | 1 | 3 | 0 | eq 1 | 否 | ✅ |  |
| fallback_rate | 0 | 3 | 0 | — | 否 | — |  |
| avg_model_calls_per_turn | 2 | 3 | 0 | — | 否 | — |  |
| multi_turn_state_exact | 0.666667 | 3 | 0 | — | 否 | — |  |
| latency_p50_ms | 585 | 4 | 0 | — | 否 | — |  |
| latency_p95_ms | 850 | 4 | 0 | — | 否 | — |  |

## 门禁

阻断指标无未达标项。
