# 离线评测与发布门禁

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
| `memory_dataset.jsonl` | `MemorySample` | owner 隔离、覆盖、显式 directive、forget 后状态夹具 |
| `multi_agent_dataset.jsonl` | `MultiAgentSample` | 子图输出、汇合状态与最终业务结果夹具 |
| `interrupt_dataset.jsonl` | `InterruptSample` | 四类 interrupt 恢复节点与副作用基线夹具 |
| `cache_dataset.jsonl` | `CacheSample` | 版本向量、hit/miss、调用次数与结果摘要夹具 |
| `retrieval_strategy_dataset.jsonl` | `RetrievalStrategySample` | weighted、RRF、weighted+rerank 三组策略对比 |

`memory`、`multi_agent`、`interrupt`、`cache` 四类是工程不变量夹具，不参与商品质量
指标和发布门禁；它们由严格行模型加载，供专项回归执行器及契约测试使用。
`retrieval_strategy` 是独立的策略比较夹具。

`shijiajing-eval --no-gate` 会额外生成 `engineering_eval_report.{json,md}` 和
`retrieval_strategy_comparison.{json,md}`。前者执行四类工程夹具，并输出 §15.7 六项固定
不变量的样本数、违规数和证据来源；后者使用生产 `WeightedScoreFusion`、
`ReciprocalRankFusion`、`CandidateRelevanceReranker` 运行三组比较。两者都不改变商品质量
门禁或生产默认策略；固定不变量报告没有样本时显示为待测，不会计为通过。

**数据诚实性（方案 §3.2 非目标与 §16 数据扩展）**：仓库内数据集是 CI 回归种子样例，**不是**正式冻结
评测集——商品、价格、平台均为样例数据，平台标识按真实数据契约使用 ID
（taobao/jd/pinduoduo）。正式冻结评测需要真实商品快照与真实模型输出
（用 `--live --output-datasets-dir` 生成并人工复核后入库）。

### 1.1 Phase 1 provisional 数据集（`evals/datasets/provisional/v1`）

Phase 1（docs/plans/phase1_provisional_evaluation_plan.md）在种子之外新增
provisional 数据集构建工具链，数据位于 `evals/datasets/provisional/v1/`
（含 manifest.json 与六类数据集 + `offer_labels.jsonl` Gold 目录）：

| 数据集 | 行数 | 覆盖 |
|---|---:|---|
| recognition | 300 | 每品类 100（本地模拟主图，`image_domain=listing_image`） |
| intent | 300 | 每品类 100（新增/修改/清空/冲突/偏好取消） |
| retrieval | 150 | 每品类 50（文本/硬过滤/零结果/近型号干扰） |
| same_item | 600 | 200 同 SKU + 100 同 SPU 不同 SKU + 300 难负例 |
| ranking | 90 | 每品类 30（价格/评分/官方店/缺失数据） |
| workflow | 120 | 每品类 40（文本/图片/多轮澄清/修正/降级） |

> **来源声明**：本环境无法匿名采集淘宝/拼多多，京东仅已知商品 ID 详情页可匿名
> 访问且搜索/列表被反爬拦截；用户授权**确定性模拟生成器**产出数据集
> （2026-08-21），`dataset_id=shijiajing-provisional-sim-v1`，sources 使用保留域名
> example.com，manifest.known_limitations 如实记录。晋级 frozen 需满足计划 §16。

## 2. 评测方式

```bash
# 离线（默认）：对 recorded 冻结输出运行真实领域代码
uv run shijiajing-eval
# 等价：uv run shijiajing-eval --datasets-dir src/shijiajing_agent/data/eval --report-dir reports

# provisional 数据集：必须配合 --no-gate（默认退出码 1，不可作为发布门禁）
uv run shijiajing-eval --datasets-dir evals/datasets/provisional/v1 \
  --report-dir reports/provisional/v1 --no-gate

# 实时：通过 facade + 检索适配器实际运行（需要完整 SHIJIAJING_* 配置）
uv run shijiajing-eval --live --assets-dir evals/private/provisional_v1/raw/images \
  --output-datasets-dir <out>

# 冻结报告（仅 frozen + 人工仲裁标签数据；门禁通过才写入）
uv run shijiajing-eval --frozen

# 只出报告不看门禁退出码
uv run shijiajing-eval --no-gate

# 记录确定性 Retrieval 组件的本机延迟基线（不参与发布门禁）
uv run shijiajing-benchmark --report-dir reports --warmup 5 --iterations 30

# 正式数据的显式 p95 延迟门禁；数据目录和阈值都必须显式提供
uv run shijiajing-benchmark \
  --source formal \
  --datasets-dir evals/datasets/frozen/v1 \
  --gate-strategy weighted \
  --max-p95-ms 100 \
  --report-dir reports/frozen/v1
```

- **offline**：使用行内 `recorded` 字段（冻结的上游模型/适配器输出）；下游
  同款匹配、SKU 拆分、排序、硬过滤、解释事实一致性全部运行**真实领域代码**。
- **live**：实时调用真实模型与检索，写回 `recorded`（`--output-datasets-dir`
  落盘副本；输出目录必须不存在，写入 staging 完成后才提交；`--freeze-dir` 为
  deprecated 兼容别名，两者同时出现返回配置错误 2）。
- live 六类路径：recognition 解析本地 asset → data URL → VLM；intent
  重放历史约束合并；retrieval 通过 `offer_labels.jsonl` Gold catalog 映射
  Offer → Gold SPU/SKU；same-item 与生产共用 `default_same_item_matcher` 工厂；
  ranking 运行生产 GroupRanker 并保存真实解释文本；workflow 记录每轮延迟、
  模型/VLM 调用次数、fallback、最终约束与 Gold SKU。
- live 输出目录写入 `run_manifest.json`（模型、Prompt、taxonomy、索引、参数、
  commit）。
- 报告输出 `reports/eval_report.{json,md}`；`--frozen` 另写 `frozen_eval_report.md`。
- `shijiajing-benchmark` 输出 `reports/benchmark_report.{json,md}`，记录 weighted、RRF、
  weighted+rerank 的 p50/p95/p99、运行参数和 Python/平台信息。默认 source 是
  `seed_offline`，禁止附带性能阈值；只有显式 `source=formal`、数据目录和
  `max-p95-ms` 才会执行门禁。formal 目录还必须有 `manifest.json`，且满足
  `trust_level=frozen`、`label_method=adjudicated`、`gate_eligible=true`、冻结摘要校验和
  `retrieval_strategy_dataset.jsonl` 非空且策略行 `meta.label_source=adjudicated`。门禁失败
  写出失败报告并返回退出码 1，配置缺失返回 2。
  该门禁只覆盖 benchmark 中的确定性 Retrieval 组件，不等同于端到端线上延迟。
- CLI 内部的固定配置和报告边界分别使用 `Settings` 与 `BenchmarkReport`；数据集加载仍保留
  `dict[str, list[Any]]`，因为十一类数据集使用不同的严格行模型，不能把异构载荷误标为单一行类型。
- 退出码：0 达标 / 1 阻断指标失败或 provisional 默认 / 2 配置或数据集错误。
- live 适配器或 runtime 执行异常统一返回 2，并保留 staging 清理语义，不冒泡 traceback 作为 CLI 协议。
- 需要模型调用次数插桩的指标（`vlm_avoided_after_correction`、`model_calls_per_turn`
  等）在离线模式如实标注 `pending`，注明需 live 数据补齐。

## 2.1 可信等级与发布门禁

报告新增字段：

- `trust_level`：provisional / frozen（provisional 数据集或种子默认 provisional）。
- `label_method`：agent_only / human / adjudicated。
- `metric_gate_passed`：只表示已测阻断指标是否达到当前阈值。
- `release_gate_eligible`：仅当 manifest 同时为 `trust_level=frozen`、
  `label_method=adjudicated`、`gate_eligible=true` 时才为 true。
- `release_gate_passed = metric_gate_passed and release_gate_eligible`。
- `pending_reasons`：缺少 live 配置时的精确缺失项列表。
- `eval_report.json` 的 `schema_version` 当前为 `1.0`；报告必须包含十一类数据集摘要和
  完整指标行。每个带阈值的指标保存 `op`、`value`、`blocking` 元数据，发布门禁会按代码中
  的阈值重新计算 `passed`、阻断列表和 gate 派生字段，不接受只填写布尔结果的简化报告。
- `release_gate_passed` 只有在全部阻断指标的 `passed` 均为 `true` 且
  `release_gate_eligible=true` 时才为 true；`metric_gate_passed` 仅表示已测量阻断指标达标，
  不把 pending 视为发布通过。

CLI 语义：

- provisional 数据默认退出码 1，明确打印"不可作为发布门禁"。
- provisional 配合 `--no-gate`：成功生成报告返回 0。
- provisional 或非 `adjudicated` 数据使用 `--frozen`：返回配置错误 2，不写 frozen report；
  frozen 数据的任一阻断指标失败或未测量时也不写 frozen report，并返回 1。
- 每次使用 `--frozen` 都会先使目标目录中已有的 `frozen_eval_report.md` 失效；
  只有完整通过数据集校验和阻断门禁后才先写同目录临时文件、再原子替换生成，
  失败运行不会留下可误用的旧报告或半截冻结报告。
- 每次评测也会先清除本次 CLI 生成的 `eval_report.*`、`engineering_eval_report.*` 和
  `retrieval_strategy_comparison.*`，随后把本次报告全部写入同目录 staging 后提交；
  当新数据集缺少可选策略数据时，不会继续保留旧的策略对比报告。
- 缺少真实配置时 recognition/intent/retrieval/workflow 指标保持 `pending`，
  报告列出精确缺失配置名（不写伪 recorded）。

## 3. 指标与阈值

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

## 4. 解释事实一致性

- 模板解释（模型失败降级）只引用证据字段，**按构造一致**，节点置
  `explanation_verified=False`；离线评测将其计为一致并附说明。
- 模型文本解释需 live 校验；`FactualConsistencyChecker` 检查所有数字
  （价格区间用 `–` 分隔）与平台别名是否存在于证据。
- 种子排名数据全部使用模板解释（7 组），模型文本解释数为 0——报告如实呈现。

## 5. 冻结流程

1. 用真实数据运行 `--live --output-datasets-dir <dir>`，人工复核 `recorded` 与标注；
   同时将经过同一批次审核的 `retrieval_strategy_dataset.jsonl` 放入该目录。该文件
   必须包含正式延迟比较所需的共享候选集、通道排序、期望 Gold ID、覆盖每个候选的
   `gold_spu_by_offer_id`/`gold_sku_by_offer_id` 映射，以及 `meta.label_source=adjudicated`；
   不能使用仓库 seed 文件代替。
    `--live` 会对该文件中的 query 重新执行 Retrieval Port，按真实候选分数重建通道顺序，
    但不会改写 expected Gold ID；任何真实候选缺少 `offer_labels.jsonl` 的 Gold 映射都会直接
    返回配置错误，禁止回退到 Offer 内部字段或旧夹具映射。
2. 生成包含 `record_id`、精确 `dataset_id`/`dataset_version`、`decision=approved`、
   `review_scope=all_rows`、至少两个不同 `adjudicator_ids` 和 `reviewed_at` 的仲裁记录。
3. 用 `shijiajing-build-eval freeze` 复制数据集；命令要求所有 Gold 标签和所有评测行
   的 `meta.label_source` 都是 `adjudicated`，拒绝覆盖已有输出目录，并将 manifest
   升级为 `trust_level=frozen`、`label_method=adjudicated`、`gate_eligible=true`；
   同时写入 `adjudication_record.json`，并把它和全部数据文件纳入 manifest SHA-256。
4. 提交冻结数据集（git 记录内容摘要，`dataset_digest` 记入报告），再运行 `--frozen`；
   CLI 会复核仲裁记录、manifest 文件摘要和完整阻断门禁；全部通过后
   `reports/frozen_eval_report.md` 才是发布依据。
5. 数据集变更后必须重新冻结（摘要不同即不可混用）。

## 6. provisional 数据集构建工具链（`shijiajing-build-eval`）

```bash
# 确定性模拟 workspace（本环境用户授权适配；真实采集时跳过此步）
uv run shijiajing-build-eval simulate --workspace evals/private/provisional_v1 --as-of <ISO>

# 采集（真实环境）：只访问 sources.jsonl 列出的公网 URL；JSON-LD 优先，
# 京东移动页内嵌 JSON 契约兜底；无结构化字段记为 manual_required
uv run shijiajing-build-eval collect --sources <sources.jsonl> --workspace evals/private/provisional_v1

# 脱敏 + Gold 标签：HMAC 掩码 shop_id/source_product_id、source_payload_ref=sha256、
# 稳定 SPU 拆分；相同输入+密钥+as-of 输出字节一致
uv run shijiajing-build-eval prepare --workspace evals/private/provisional_v1 \
  --out evals/datasets/provisional/v1 --as-of <ISO>

# 六类数据集 + manifest（生成器不写 recorded；正式门禁把已审核策略夹具显式带入）
uv run shijiajing-build-eval generate --snapshot ... --labels ... --assets ... \
  --asset-map ... --asset-bindings ... --offer-source-map ... --assets-dir ... \
  --retrieval-strategy <retrieval_strategy_dataset.jsonl> \
  --out evals/datasets/provisional/v1 --as-of <ISO>

# 全量校验：契约、计数、唯一性、泄漏、摘要、taxonomy、manifest 一致性
uv run shijiajing-build-eval validate --datasets-dir evals/datasets/provisional/v1 \
  --assets-dir evals/private/provisional_v1/raw/images

# 人工仲裁后冻结：输出目录必须不存在；只接受全量、双人独立仲裁记录
uv run shijiajing-build-eval freeze \
  --datasets-dir evals/datasets/provisional/v1 \
  --out evals/datasets/frozen/v1 \
  --adjudication-record evals/private/provisional_v1/adjudication.json \
  --assets-dir evals/private/provisional_v1/raw/images
```

目录约定：`evals/private/provisional_v1/`（本地原始证据，已加入
`.gitignore`，禁止提交）与 `evals/datasets/provisional/v1/`（脱敏后提交，
含 manifest.json、README.md 与全部数据文件 SHA-256）。
