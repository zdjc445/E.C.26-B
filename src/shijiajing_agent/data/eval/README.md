# 评测数据集（方案 §22.1）

本目录是 **CI 回归种子集**，不是第 22.3 节正式冻结评测集：

- 商品、价格、平台均为**样例数据**，仅用于评测管线与领域逻辑回归，不代表任何
  真实平台的商品或价格。
- `recorded` 字段是冻结的上游输出（模型/检索）；offline 评测用它驱动下游
  领域逻辑。带 `recorded: null` 的行标记"待 live 评测补齐"。
- 正式冻结评测需要真实商品快照与模型输出：用 `shijiajing-eval --live --freeze-dir`
  在真实环境产出后替换本目录（或指向新目录）。

文件格式：每行一个 JSON 对象，行模型见 `src/shijiajing_agent/evals.py`。

- `recognition_dataset.jsonl`：图片/文本 + 品类、品牌、型号、属性标注。
- `intent_dataset.jsonl`：文本 + 期望 patch、清空字段、冲突标签。
- `retrieval_dataset.jsonl`：查询 + 硬过滤 + 相关 SPU/SKU 集合。
- `same_item_pairs.jsonl`：Offer 对 + 同 SPU/SKU 标签 + 冲突原因。
- `ranking_dataset.jsonl`：查询 + 候选组 + 人工偏好顺序。
- `end_to_end_dataset.jsonl`：完整多轮轨迹 + 期望结果。
- `memory_dataset.jsonl`：owner、session 序列、显式 directive、覆盖与 forget 后状态。
- `multi_agent_dataset.jsonl`：子图输入/输出、汇合状态与最终业务结果。
- `interrupt_dataset.jsonl`：四类 interrupt 的恢复节点与副作用计数。
- `cache_dataset.jsonl`：完整版本向量、版本变化后的 hit/miss、模型调用次数与结果摘要。
- `retrieval_strategy_dataset.jsonl`：三种召回策略共享候选集和通道排序的比较夹具。

本目录中的 `retrieval_strategy_dataset.jsonl` 只是 CI seed。正式延迟门禁要求将同一正式
数据批次的策略比较夹具纳入冻结目录，行级 `meta.label_source` 必须为 `adjudicated`，
且 `gold_spu_by_offer_id`/`gold_sku_by_offer_id` 必须覆盖每个候选，
并随 `manifest.files` 做摘要校验；不能把本目录或其他 seed 目录直接声明为 `source=formal`。

前四类工程夹具只验证确定性工程不变量，不用于证明线上用户偏好或商品质量；其
执行结果另写 `engineering_eval_report`，包含四类工程夹具和六项固定不变量的独立结果；不会
回填 `recorded`，也不会让离线商品评测报告增加质量指标。
