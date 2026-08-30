# Phase 1 真实评测闭环 Provisional 基准执行完成报告

执行日期：2026-08-21

## 1. 交付概述

按 `docs/plans/phase1_provisional_evaluation_plan.md` §14 执行顺序完成全部 12 步：

1. ✅ 新增评测契约：`SourceSpec`、`CaptureRecord`、`GoldLabelDraft`、
   `OfferGoldLabel`、`EvalAssetRef`、`EvalSampleMeta`、`AssetInventoryEntry`、
   `AssetMapEntry`、`AssetBinding`、`OfferSourceMap`、`DatasetManifest`
   （`src/shijiajing_agent/eval_data.py`，全部 `extra="forbid"`）；六类样本模型
   新增可选 `meta`/`asset`/`recorded` 字段（种子数据向后兼容），
   `WorkflowSample` 新增 `expected_sku_ids`/`expected_final_constraints`，
   `WorkflowRecorded` 新增 `sku_ids`/`final_constraints`。
2. ✅ `shijiajing-build-eval` CLI 五个子命令（`src/shijiajing_agent/tools/build_eval.py`）：
   `simulate` / `collect` / `prepare` / `generate` / `validate`，注册到 pyproject。
3. ✅ 私有证据目录 `evals/private/provisional_v1/`（已加入 `.gitignore`）与提交目录
   `evals/datasets/provisional/v1/`。
4. ✅ 1,000 条 Offer 数据集（数据来源见 §2 适配说明）。
5. ✅ Agent Gold catalog（1,000 标签）、六类数据集与 manifest（§4.2 计数完全一致）。
6. ✅ `validate` 全部 §9 校验通过（退出 0）。
7. ✅ 六类 live runner（`src/shijiajing_agent/evals_live.py`）：recognition/intent/
   retrieval/same-item/ranking/workflow + 端口计数包装器 + `run_manifest.json`。
8. ✅ 报告可信等级与门禁语义（§11）：`trust_level` / `label_method` /
   `metric_gate_passed` / `release_gate_eligible` / `release_gate_passed` /
   `pending_reasons`；provisional 默认退出 1、`--no-gate` 退出 0、
   `--frozen` 退出 2 且不写 frozen report。
9. ✅ `shijiajing-index-products --dry-run` 免外部配置，输出行数/合法/非法/品类分布/
   平台分布/空关键字段比例。
10. ✅ 测试：新增 `tests/unit/test_eval_data.py`、`tests/unit/test_build_eval.py`、
    `tests/contract/test_eval_live.py`；更新 `tests/unit/test_eval_cli.py`
    （provisional 门禁语义）；全部 278 项通过（排除已知 examples 文件）。
11. ✅ 更新 `docs/evaluation.md` 与数据集 README。
12. ✅ 验收命令全部运行并记录（见 §3）。

## 2. 数据来源适配（用户授权，必须阅读）

**环境约束（2026-08-21 实测）**：

- 仅京东移动详情页 `item.m.jd.com` 可匿名访问，且内嵌结构化 JSON
  （`window._itemOnly.item` 数据契约；无价格字段）。
- 京东搜索/列表页、淘宝/天猫/拼多多详情页、Bing/百度/搜狗/WebSearch 均被
  反爬拦截或登录墙；计划 §5.2 明确禁止绕过。
- 无法自动发现 1,000 个商品 URL，无法满足"每品类 ≥2 个平台 ID"（§4.1）。

**用户决定**（AskUserQuestion 答复）："你来模拟数据集，不需要完全真实"。

据此实现 `shijiajing-build-eval simulate`：确定性模拟生成器
（`src/shijiajing_agent/eval_simulate.py`，相同 `dataset_id + as-of` 输出字节一致），
产出与真实采集同构的证据（sources/captures/证据 JSON/32x32 模拟主图 PNG），
后续 `prepare → generate → validate` 走与真实数据完全相同的代码路径。

**诚实性保障**：

- `dataset_id = shijiajing-provisional-sim-v1`（计划固定值带 real 后缀，如实改为 sim）。
- sources URL 使用保留域名 `example.com`（RFC 2606），notes 声明模拟来源。
- `manifest.known_limitations` 与数据集 README 明确声明模拟来源、无人工复核、
  `gate_eligible=false`。
- `label_source=agent`（生成器按构造标注）；`image_domain=listing_image`。
- 所有指标如实呈现：same_item/ranking 为领域代码确定性计算（precision 1.0、
  false_comparison 0.0、sku_split 1.0、ndcg 0.977）；recognition/intent/retrieval/
  workflow 因无真实模型配置保持 `pending`，报告列出缺失配置。

## 3. 验收命令结果（§15）

| 命令 | 结果 |
|---|---|
| `shijiajing-build-eval validate --datasets-dir evals/datasets/provisional/v1 --assets-dir evals/private/provisional_v1/raw/images` | ✅ 退出 0，全部 §9 校验通过 |
| `shijiajing-index-products evals/datasets/provisional/v1/offers_snapshot.jsonl --dry-run` | ✅ 退出 0；解析 1,000 行、非法 0；品类 headphone 340/sneaker 340/hair_dryer 320；平台 jd 336/taobao 331/pinduoduo 333；空关键字段 price 3.6%、sku_key 100% |
| `shijiajing-eval --datasets-dir evals/datasets/provisional/v1 --report-dir reports/provisional/v1 --no-gate` | ✅ 退出 0；`release_gate_eligible=false`、`metric_gate_passed=true`、25 项指标 pending |
| `shijiajing-eval`（provisional 默认） | 退出 1，打印"不可作为发布门禁" ✅ |
| `shijiajing-eval --frozen`（provisional） | 退出 2，不写 frozen report ✅ |
| `pytest -q --ignore=tests/unit/test_examples.py` | ✅ 278 passed, 4 deselected |
| `ruff check src tests` | ✅ 0 错误 |
| `pyright` | 120 错误 = 与基线 HEAD 完全一致（见 §4） |

数据规模：Offer 1,000（headphone 340 / sneaker 340 / hair_dryer 320）、
Gold SPU 200（70/70/60）、图片资产 300、六类样本 300/300/150/600/90/120，
与 §4.1/§4.2 完全一致。

## 4. 已知偏差与既有问题

1. **数据来源**：模拟数据替代真实采集（用户授权，见 §2）——这是对计划的唯一
   实质性偏离，其余全部按计划执行。
2. **`dataset_id`**：`shijiajing-provisional-sim-v1` 而非计划的
   `shijiajing-provisional-real-v1`（如实标注来源，§3 固定值在计划内）。
3. **pyright 基线**：`pyright` 在当前 HEAD（未含本阶段改动）即有 120 个
   既有错误（pymilvus/structlog/psycopg 类型解析与 graph.py），本阶段新增文件
   贡献 0 个新错误；"pyright 0 错误"的验收项需先修复基线，建议单独任务处理。
4. **`--freeze-dir`**：保留为 `--output-datasets-dir` 的 deprecated 兼容别名
   （§10），两者同时出现返回配置错误 2。
5. **same-item recall 0.82**：同 SPU 不同 SKU 对因变体属性差异大被领域匹配器
   判为 review（诚实行为，非数据错误；precision 1.0、false comparison 0.0）。
6. 已知 `tests/unit/test_examples.py` 收集错误不属于本阶段（计划 §2.2、§13.4）。

## 5. 晋级 frozen 的前置条件（计划 §16，本阶段未执行）

- 两名人工标注者独立复核全部 holdout 标签 + 第三名仲裁；
- 提供真实 Ark/Milvus/Checkpoint 配置完成 live run，所有阻断指标达到阈值；
- 数据来源切换为真实商品页采集或授权导出，重新计算全部文件摘要；
- manifest 更新为 `trust_level=frozen`、`label_method=adjudicated`、
  `gate_eligible=true`；冻结后 holdout 不可再修改。
