# 第一阶段：真实评测闭环 Provisional 基准执行方案

## 1. 目标与交付定义

本阶段把现有 22 条种子样例扩展为基于真实商品 Offer 的大规模评测工具链，覆盖数据采集、脱敏、Agent 预标注、数据集生成、泄漏检查、离线评测和完整 live runner。

本阶段交付物的可信等级固定为 `provisional`，不是正式冻结基准，原因如下：

- 商品 Offer 来自真实、公开可访问的商品详情页或明确授权的导出数据。
- 商品身份和 SKU 标签由 Agent 根据来源证据生成，没有独立人工复核。
- 当前环境没有 Ark、Embedding、Milvus 和 Checkpoint 配置，不执行真实 live 模型评测。
- 报告可以计算候选门禁结果，但不得用于发布门禁，不得生成 `frozen_eval_report`。

完成标准：

- 生成 1,000 条通过契约校验的脱敏 Offer。
- 覆盖 `headphone`、`sneaker`、`hair_dryer` 三个现有 taxonomy 品类。
- 生成六类评测数据集、标签目录、资产清单和可追溯 manifest。
- 完成全部数据验证、离线确定性评测和 Fake 端口 live runner 测试。
- 所有真实模型指标在缺少配置时明确标记为 `pending`，不得生成伪造的 `recorded`。

## 2. 范围与非目标

### 2.1 本阶段范围

- 真实商品页采集与结构化抽取。
- 原始页面、图片和结构化 Offer 的本地证据留存。
- 脱敏 Offer 快照与 Agent 标签生成。
- development/holdout 按 SPU 隔离拆分。
- 六类数据集生成和严格校验。
- `shijiajing-eval --live` 补全到六类评测路径。
- 评测报告可信等级和发布门禁资格控制。
- 数据生成、校验、评测命令和测试文档。

### 2.2 非目标

- 不升级同款匹配算法、排序公式或 Prompt。
- 不接入新的图像 Embedding Provider。
- 不把 Agent 标签描述为人工标注或正式 Gold Standard。
- 不修复已删除 `examples/` 与 `tests/unit/test_examples.py` 的历史不一致；该问题单独处理。
- 不在缺少真实环境配置时调用 Ark 或 Milvus。

## 3. 目录与版本规范

新增目录：

```text
evals/
├── private/provisional_v1/             # 本地原始证据，禁止提交
│   ├── sources.jsonl                   # 明确的采集 URL 清单
│   ├── raw/pages/                      # 原始 HTML/JSON 响应
│   ├── raw/images/                     # 原始图片
│   ├── captures.jsonl                  # 采集状态和内容哈希
│   └── asset_map.jsonl                 # asset_id 到本地路径的映射
└── datasets/provisional/v1/            # 脱敏后提交
    ├── manifest.json
    ├── offers_snapshot.jsonl
    ├── offer_labels.jsonl
    ├── asset_inventory.jsonl
    ├── recognition_dataset.jsonl
    ├── intent_dataset.jsonl
    ├── retrieval_dataset.jsonl
    ├── same_item_pairs.jsonl
    ├── ranking_dataset.jsonl
    ├── workflow_dataset.jsonl
    └── README.md
```

实施时在 `.gitignore` 中加入：

```gitignore
/evals/private/
```

版本固定值：

- `dataset_id`: `shijiajing-provisional-real-v1`
- `dataset_schema_version`: `1.0`
- `trust_level`: `provisional`
- `label_method`: `agent_only`
- `gate_eligible`: `false`
- `taxonomy_version`: 从实际加载的 taxonomy 文件读取，禁止硬编码或猜测。

## 4. 数据规模与分布

### 4.1 Offer 和 SPU

| 品类 | Offer 数 | Gold SPU 数 | 图片资产数 |
|---|---:|---:|---:|
| `headphone` | 340 | 70 | 100 |
| `sneaker` | 340 | 70 | 100 |
| `hair_dryer` | 320 | 60 | 100 |
| 合计 | 1,000 | 200 | 300 |

约束：

- 每个 Gold SPU 至少包含 3 条 Offer。
- 每个 Gold SPU 至少覆盖 2 个不同平台或来源域。
- 每个品类至少覆盖 2 个现有平台 ID。
- 任一平台在单个品类中的 Offer 占比不得超过 60%。
- 价格、评分、销量、运费、优惠等源页面没有提供的字段必须保持 `null`，不得推断。
- 同一 Offer 通过 `platform + source_product_id` 去重；`source_product_id` 缺失时使用规范化 URL 的 HMAC 标识去重。

### 4.2 六类评测样本

| 数据集 | 行数 | 分布要求 |
|---|---:|---|
| recognition | 300 | 每品类 100；记录商品主图场景，不冒充用户实拍图 |
| intent | 300 | 每品类 100；覆盖新增、修改、清空、冲突和偏好取消 |
| retrieval | 150 | 每品类 50；覆盖文本、硬过滤、零结果和近型号干扰 |
| same_item | 600 | 200 同 SKU、100 同 SPU 不同 SKU、300 不同 SPU 难负例 |
| ranking | 90 | 每品类 30；覆盖价格、评分、销量、官方店和缺失数据 |
| workflow | 120 | 每品类 40；覆盖文本、图片、多轮澄清、修正和降级 |

### 4.3 数据拆分

- 拆分固定为 40% `development`、60% `holdout`。
- 使用 Gold SPU 作为最小拆分单元，同一 SPU 不得跨集合。
- 负样本对只能从同一个 split 内选择两个 SPU。
- retrieval、ranking、workflow 样本继承其目标 Gold SPU 的 split。
- 拆分算法使用稳定 SHA-256：输入为 `dataset_id + gold_spu_id`；禁止使用 Python 进程随机 hash。
- 数据校验必须输出 SPU 泄漏检查结果；发现一条泄漏即退出非零。

## 5. 数据来源与采集规则

### 5.1 `sources.jsonl` 契约

新增严格 Pydantic 模型 `SourceSpec`，字段固定为：

```json
{
  "source_id": "src:...",
  "url": "https://...",
  "platform": "jd",
  "category_id": "headphone",
  "official_identity_url": "https://...",
  "notes": null
}
```

字段语义：

- `source_id`: 本批数据内部唯一 ID。
- `url`: 商品详情页；只允许公网 `http/https`。
- `platform`: 精确使用页面对应的平台 ID，不转换大小写、不猜测别名。
- `category_id`: 必须精确存在于当前 taxonomy。
- `official_identity_url`: 品牌官方规格页；无法找到时为 `null`，不能伪造。
- `notes`: 只记录采集异常或身份判断线索。

### 5.2 采集器行为

新增命令：

```text
shijiajing-build-eval collect
  --sources evals/private/provisional_v1/sources.jsonl
  --workspace evals/private/provisional_v1
```

采集要求：

- 只访问 source manifest 中明确列出的 URL，不自动扩大域名或递归爬取。
- 禁止绕过登录、验证码、访问频率限制或 robots 限制。
- 校验初始 URL 和每次重定向后的目标，拒绝内网、回环、本地文件和非 HTTP 协议。
- 单个 HTML/JSON 响应上限 5 MiB，单张图片上限 10 MiB，单请求超时 15 秒。
- 优先用 JSON-LD/schema.org 结构化解析；页面无结构化字段时记录为 `manual_required`，不得用字符串猜字段路径。
- 每个采集结果写入 `captures.jsonl`，状态固定为 `ok`、`unavailable`、`manual_required` 或 `invalid`。
- 保存采集时间、HTTP 状态、最终 URL 的 HMAC、内容 SHA-256 和本地证据路径。
- 采集失败不得生成 Offer；继续补充 source manifest，直到满足数据规模。

## 6. 脱敏、Gold 标签与防泄漏

### 6.1 脱敏规则

新增命令：

```text
shijiajing-build-eval prepare
  --workspace evals/private/provisional_v1
  --out evals/datasets/provisional/v1
```

输出规则：

- 保留比价必需的标题、平台、价格、品牌、型号和商品属性。
- 删除 URL 查询参数、Cookie、账号、联系人、收货地和页面跟踪字段。
- `shop_id`、`source_product_id` 使用本地密钥执行 HMAC-SHA256；仓库只保存结果和 `key_id`，不保存密钥。
- `source_payload_ref` 固定写为 `sha256:<content_sha256>`，不得写原始 URL 或本地绝对路径。
- 图片二进制和原始页面不提交；`asset_inventory.jsonl` 只提交 `asset_id`、内容类型、SHA-256、宽高和来源内容哈希。
- 相同输入、相同 HMAC 密钥和相同 `--as-of` 时间必须产生字节一致的 JSONL；输出按 `id` 排序。

### 6.2 Gold 标签目录

新增 `OfferGoldLabel` 契约，字段固定为：

```json
{
  "offer_id": "off:...",
  "gold_spu_id": "gspu:...",
  "gold_sku_id": "gsku:...",
  "category_id": "headphone",
  "identity_attributes": {},
  "variant_attributes": {},
  "evidence_refs": ["sha256:..."],
  "label_source": "agent",
  "label_rationale": "...",
  "split": "development"
}
```

标签规则：

- `gold_spu_id` 和 `gold_sku_id` 只存在于 `offer_labels.jsonl` 和评测期映射中。
- 不得把 Gold SPU 写入 `Offer.same_item_key`。
- 不得把 Gold SKU 写入 `Offer.sku_key`。
- 来源页面真实提供的 `same_item_key` 或 `sku_key` 可以保留，但必须在 evidence 中说明来源。
- Agent 只能依据页面证据、官方型号和明确身份/变体属性标注；不允许依据被测算法输出反向生成 Gold 标签。
- 所有标签 `label_source` 固定为 `agent`，manifest 中 `gate_eligible=false`。

## 7. 新增评测契约

在评测模块新增以下类型，全部使用 `extra="forbid"`：

### 7.1 `EvalAssetRef`

```text
asset_id: str
content_type: ImageContentType
sha256: str
```

真实数据的 `RecognitionSample` 使用 `asset` 字段，不在提交数据中保存图片 URL。live 运行时通过 `--assets-dir` 和本地 `asset_map.jsonl` 解析为内存 data URL。生产 `ImageRef` 契约保持不变。

### 7.2 `EvalSampleMeta`

```text
dataset_version: str
split: Literal["development", "holdout"]
category_id: str
subject_ids: list[str]
source_refs: list[str]
label_source: Literal["agent", "human", "adjudicated"]
```

六类样本模型新增可选 `meta` 字段，以保持种子数据向后兼容；provisional 数据校验器要求该字段必填。

### 7.3 `DatasetManifest`

必须包含：

- `dataset_id`
- `dataset_schema_version`
- `dataset_version`
- `taxonomy_version`
- `trust_level`
- `label_method`
- `gate_eligible`
- `created_at`
- `as_of`
- `categories`
- `counts_by_file`
- `counts_by_split`
- `counts_by_platform`
- `offer_count`
- `spu_count`
- `asset_count`
- `files`，值为每个提交文件的 SHA-256
- `known_limitations`

manifest 自身不进入 `files` 哈希映射，避免自引用。

### 7.4 Workflow 和 Retrieval Gold 映射

- provisional retrieval 的 expected SPU/SKU ID 使用 `offer_labels.jsonl` 中的 Gold ID。
- live retrieval 返回 Offer 后，通过 `offer_id -> Gold ID` 映射计算召回，不读取 Offer 内的 Gold 字段。
- `WorkflowSample` 新增 `expected_sku_ids` 和 `expected_final_constraints`。
- `WorkflowRecorded` 新增 `sku_ids`；旧的 `group_ids` 保留用于种子数据兼容。
- provisional `state_exact` 必须同时比较最终状态、Gold SKU 集合、澄清状态和有效约束，不能只比较运行时 `group_id`。

## 8. 数据集生成器

新增命令：

```text
shijiajing-build-eval generate
  --snapshot evals/datasets/provisional/v1/offers_snapshot.jsonl
  --labels evals/datasets/provisional/v1/offer_labels.jsonl
  --assets evals/datasets/provisional/v1/asset_inventory.jsonl
  --out evals/datasets/provisional/v1
  --as-of <ISO-8601 UTC>
```

生成规则：

- recognition 从 300 个本地图片资产生成；manifest 标明 `image_domain=listing_image`。
- intent 和 workflow 的用户文本由 Agent 生成，`scenario_source=agent_generated`，不得描述为真实用户日志。
- same-item 难负例优先选择同品类、同品牌、型号相近但身份属性冲突的 Offer。
- same-SKU 正样本必须跨平台；同 SPU 不同 SKU 样本至少一个 variant attribute 不同。
- retrieval query 必须包含纯文本、硬品牌/型号、预算、平台、评分和零结果案例。
- ranking group 从 Gold SKU 分组构建，价格计算复用生产 `SkuSplitter`，不得复制另一套公式。
- workflow request 的 `session_id` 和 `request_id` 由 `dataset_id + sample_id + turn_index` 稳定生成。
- 生成器不得写 `recorded`；真实或本地运行器负责填充。

## 9. 数据验证器

新增命令：

```text
shijiajing-build-eval validate
  --datasets-dir evals/datasets/provisional/v1
  --assets-dir evals/private/provisional_v1/raw/images
```

任何一项失败都必须退出非零：

- 所有 JSONL 通过对应 Pydantic 契约，禁止额外字段。
- 文件行数和第 4 节规定完全一致。
- Offer ID、sample ID、source ID、asset ID 全局唯一。
- 每个 sample 的 source ref 都能在 manifest 或 capture catalog 中解析。
- 每个图片 SHA-256 与本地文件一致。
- Gold SPU 不跨 split。
- same-item 标签满足 `same_sku => same_spu`。
- same-SKU 对的 Gold SKU 相同；同 SPU 不同 SKU 对的 Gold SPU 相同且 Gold SKU 不同。
- 数据集中不存在 Gold 标签泄漏到 `Offer.same_item_key` 或 `Offer.sku_key`。
- 所有 expected SPU/SKU ID 都存在于 Gold 标签目录。
- 所有分类和属性键精确存在于当前 taxonomy。
- manifest 统计、实际统计和文件 SHA-256 完全一致。
- provisional manifest 必须为 `gate_eligible=false`。

## 10. Live runner 补全

当前 live runner 只执行 workflow 和 retrieval。本阶段补全为：

- recognition：解析本地 asset，调用 `VisionModelPort.recognize`，写入 `recorded`。
- intent：调用 `IntentModelPort.extract_intent`；需要历史时顺序重放历史 patch 和约束合并，写入冲突观察字段。
- retrieval：执行真实 retrieval port，并通过 Gold catalog 映射 Offer ID 到 Gold SPU/SKU。
- same-item：运行与生产节点相同的 matcher factory，不使用评测专用 `_bigram_jaccard` 替代生产相似度。
- ranking：运行生产 `GroupRanker`；需要解释时调用 explanation port 并保存真实解释文本。
- workflow：执行 facade，记录每轮延迟、VLM 调用、模型调用次数、fallback、最终约束和 Gold SKU。

实施约束：

- 抽取统一的默认 SameItemMatcher 工厂，生产节点和评测共同调用；本阶段不改变评分公式。
- 使用 evaluation-only 端口包装器计数，不修改生产响应协议。
- 每个 workflow sample 使用独立 session，并为每次运行增加 run ID，防止旧 Checkpoint 命中。
- `recorded` 只来自真实端口执行或明确标识的本地 baseline；不得从 expected 字段复制。
- live 输出目录新增 `run_manifest.json`，记录模型、Prompt、taxonomy、索引、参数和代码 commit。

CLI 保留现有参数并新增：

```text
shijiajing-eval
  --datasets-dir <dir>
  --assets-dir <private-assets-dir>
  --live
  --output-datasets-dir <dir>
```

`--freeze-dir` 保留为 `--output-datasets-dir` 的兼容别名，并在帮助文本中标为 deprecated；两者同时出现时返回配置错误。

## 11. 可信等级与报告语义

评测报告新增：

```text
trust_level
label_method
metric_gate_passed
release_gate_eligible
release_gate_passed
pending_reasons
```

计算规则：

- `metric_gate_passed`：只表示已测指标是否达到当前阈值。
- `release_gate_eligible`：只有 manifest 为 `frozen` 且标签为独立人工仲裁时才为 true。
- `release_gate_passed = metric_gate_passed and release_gate_eligible`。
- provisional 数据默认 CLI 退出码为 1，明确打印“不可作为发布门禁”。
- provisional 配合 `--no-gate` 时，成功生成报告返回 0。
- provisional 使用 `--frozen` 时返回配置错误码 2，不写 frozen report。
- 缺少真实配置时，recognition、intent、live retrieval 和 workflow 指标保持 `pending`，报告列出精确缺失配置名。

## 12. 本地与索引工具调整

- `shijiajing-index-products --dry-run` 不得要求 Ark、Milvus、Checkpoint 和 Trace 配置，只要求 snapshot 与 taxonomy 可读。
- 非 dry-run 路径继续执行当前完整配置校验。
- dry-run 必须输出总行数、合法行数、非法行数、品类分布、平台分布和空关键字段比例。
- provisional snapshot 能通过 dry-run，但本阶段不执行真实 Milvus upsert。

## 13. 测试计划

### 13.1 单元测试

- 新增 manifest、sample meta、asset ref、Gold label 的合法与非法样例。
- HMAC 脱敏确定性和不泄漏原值。
- SPU 稳定拆分、跨 split 泄漏拒绝、负样本同 split 约束。
- source URL 与重定向目标的公网校验。
- 采集大小、超时、无 JSON-LD 和非法内容处理。
- Agent 标签不得进入 Offer Gold 字段。
- provisional 门禁资格计算。

### 13.2 Contract 测试

- 采集器使用录制 HTTP 响应，CI 禁止访问真实网络。
- asset resolver 校验 SHA-256 后构建 data URL。
- 六类 live runner 使用 Fake 端口全部写出正确 recorded。
- retrieval 和 workflow 通过外部 Gold catalog 映射，不依赖 `same_item_key`。
- SameItemMatcher 生产节点和评测使用同一工厂与相同参数。
- run manifest 包含精确的模型、Prompt、taxonomy 和 commit 标识。

### 13.3 CLI 测试

- 缺数据目录、缺 asset、manifest 不一致返回 2。
- provisional `--frozen` 返回 2 且不生成报告。
- provisional `--no-gate` 成功生成报告返回 0。
- 无 live 配置时列出精确缺失项，不写伪 recorded。
- `index-products --dry-run` 在无外部配置环境可运行。
- 两个输出参数同时出现时返回 2。

### 13.4 回归测试

- 现有 seed 数据不要求 `meta`，离线评测结果保持兼容。
- 现有领域、contract 和 workflow 测试不得回归。
- 已知 `examples` 收集错误不属于本阶段；验证命令明确排除该文件。

## 14. 执行顺序

1. 新增评测契约、manifest 和兼容加载逻辑。
2. 实现 collect/prepare/generate/validate 四个子命令及项目脚本入口。
3. 实现私有证据目录和提交目录，补 `.gitignore`。
4. 收集并清洗 1,000 条 Offer，数据不足时不得降低数量门禁。
5. 生成 Agent Gold catalog、六类数据集和 manifest。
6. 运行 validate，修复所有泄漏、计数和契约问题。
7. 补全六类 live runner、端口计数包装器和 run manifest。
8. 更新报告可信等级与门禁语义。
9. 调整 index dry-run 配置要求。
10. 增加单元、contract、CLI 和回归测试。
11. 更新 `docs/evaluation.md` 和数据集 README。
12. 运行验收命令并记录结果。

## 15. 验收命令

```powershell
uv run shijiajing-build-eval validate `
  --datasets-dir evals/datasets/provisional/v1 `
  --assets-dir evals/private/provisional_v1/raw/images

uv run shijiajing-index-products `
  evals/datasets/provisional/v1/offers_snapshot.jsonl `
  --dry-run

uv run shijiajing-eval `
  --datasets-dir evals/datasets/provisional/v1 `
  --report-dir reports/provisional/v1 `
  --no-gate

uv run pytest -q --ignore=tests/unit/test_examples.py
uv run ruff check src tests
uv run pyright
```

验收结果必须满足：

- 数据验证命令退出 0。
- Offer、SPU、图片和六类样本计数与第 4 节完全一致。
- 索引 dry-run 解析 1,000 条 Offer，非法记录数为 0。
- provisional 报告生成成功并明确显示 `release_gate_eligible=false`。
- 缺少 live 配置的指标显示 `pending`，没有伪造 recorded。
- 排除已知 examples 问题后测试全部通过。
- Ruff 和 Pyright 均为 0 错误。

## 16. 外部依赖与后续晋级条件

当前环境没有以下配置，执行 Agent 不得假设存在：

- `SHIJIAJING_ARK_API_KEY`
- `SHIJIAJING_ARK_BASE_URL`
- `SHIJIAJING_ARK_VISION_MODEL`
- `SHIJIAJING_ARK_TEXT_MODEL`
- `SHIJIAJING_EMBEDDING_MODEL`
- `SHIJIAJING_MILVUS_URI`
- `SHIJIAJING_MILVUS_TOKEN`
- `SHIJIAJING_MILVUS_COLLECTION`
- `SHIJIAJING_CHECKPOINT_BACKEND`
- `SHIJIAJING_CHECKPOINT_DSN`

后续从 provisional 晋级 frozen 必须同时满足：

- 两名人工标注者独立复核全部 holdout 标签。
- 冲突标签由第三名人工仲裁。
- 原始证据和标签变更全部重新计算文件摘要。
- 提供真实 Ark/Milvus/Checkpoint 配置并完成 live run。
- 所有阻断指标已测量且达到阈值。
- manifest 更新为 `trust_level=frozen`、`label_method=adjudicated`、`gate_eligible=true`。
- 冻结后不再修改 holdout；任何修改必须生成新 dataset version。
