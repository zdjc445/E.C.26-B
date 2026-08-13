# 离线评测（§22）

## 1. 数据集

仓库内置种子数据集位于 `src/shijiajing_agent/data/eval/`，每行一个 JSON 对象
（`extra="forbid"` 严格校验，多余字段直接报错）：

| 文件 | 行模型 | 评测内容 |
|---|---|---|
| `recognition_dataset.jsonl` | `RecognitionSample` | 识别准确率、ECE、属性 F1 |
| `intent_dataset.jsonl` | `IntentSample` | 意图字段 Macro-F1、清空操作、冲突检测 |
| `retrieval_dataset.jsonl` | `RetrievalSample` | SKU/SPU Recall@k、MRR、硬过滤满足率 |
| `same_item_pairs.jsonl` | `SameItemSample` | 成对同款 P/R/F1、false comparison、SKU 拆分 |
| `ranking_dataset.jsonl` | `RankingSample` | NDCG、约束满足、Top1 价格正确 |
| `workflow_dataset.jsonl` | `WorkflowSample` | 任务成功率、澄清、修正免 VLM、状态一致性、延迟 |

**数据诚实性（§25）**：仓库内数据集是 CI 回归种子样例，**不是** §22.3 正式冻结
评测集——商品、价格、平台均为样例数据，平台标识按真实数据契约使用 ID
（taobao/jd/pinduoduo）。正式冻结评测需要真实商品快照与真实模型输出
（用 `--live --freeze-dir` 生成并人工复核后入库）。

## 2. 评测方式

```bash
# 离线（默认）：对 recorded 冻结输出运行真实领域代码
uv run shijiajing-eval
# 等价：uv run shijiajing-eval --datasets-dir src/shijiajing_agent/data/eval --report-dir reports

# 实时：通过 facade + 检索适配器实际运行（需要完整 SHIJIAJING_* 配置）
uv run shijiajing-eval --live --freeze-dir src/shijiajing_agent/data/eval

# 冻结报告（门禁通过才写入）
uv run shijiajing-eval --frozen

# 只出报告不看门禁退出码
uv run shijiajing-eval --no-gate
```

- **offline**：使用行内 `recorded` 字段（冻结的上游模型/适配器输出）；下游
  同款匹配、SKU 拆分、排序、硬过滤、解释事实一致性全部运行**真实领域代码**。
- **live**：实时调用真实模型与检索，写回 `recorded`（`--freeze-dir` 落盘副本）。
- 报告输出 `reports/eval_report.{json,md}`；`--frozen` 另写 `frozen_eval_report.md`。
- 退出码：0 达标 / 1 阻断指标失败 / 2 配置或数据集错误。
- 需要模型调用次数插桩的指标（`vlm_avoided_after_correction`、`model_calls_per_turn`
  等）在离线模式如实标注 `pending`，注明需 live 数据补齐。

## 3. 指标与阈值（§22.3）

| 指标 | 阈值 | 阻断 |
|---|---|---|
| structural_output_success_rate | ≥ 0.99 | 否 |
| category_accuracy | ≥ 0.90 | 否 |
| intent_field_macro_f1 | ≥ 0.92 | 否 |
| sku_recall_at_20 | ≥ 0.90 | 否 |
| same_item_pairwise_precision | ≥ 0.98 | **是** |
| false_comparison_rate | ≤ 0.01 | **是** |
| sku_split_accuracy | ≥ 0.97 | 否 |
| hard_filter_satisfaction_rate | = 1.0 | **是** |
| explanation_factual_consistency_rate | = 1.0 | **是** |
| vlm_avoided_after_correction_rate | = 1.0 | 否 |
| task_success_rate | ≥ 0.85 | 否 |

未测量（`pending`）的阻断指标使门禁**不通过**——不得用未测量掩盖失败；
`--no-gate` 只用于临时观察。

## 4. 解释事实一致性（§15.5）

- 模板解释（模型失败降级）只引用证据字段，**按构造一致**，节点置
  `explanation_verified=False`；离线评测将其计为一致并附说明。
- 模型文本解释需 live 校验；`FactualConsistencyChecker` 检查所有数字
  （价格区间用 `–` 分隔）与平台别名是否存在于证据。
- 种子排名数据全部使用模板解释（7 组），模型文本解释数为 0——报告如实呈现。

## 5. 冻结流程

1. 用真实数据运行 `--live --freeze-dir <dir>`，人工复核 `recorded` 与标注。
2. 提交数据集（git 记录内容摘要，`dataset_digest` 记入报告）。
3. 运行 `--frozen`，阻断指标全过 → `reports/frozen_eval_report.md` 为发布依据。
4. 数据集变更后必须重新冻结（摘要不同即不可混用）。
