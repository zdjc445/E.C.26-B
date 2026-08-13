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
- `workflow_dataset.jsonl`：完整多轮轨迹 + 期望结果。
