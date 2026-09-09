# RAG 设计 — 图片内容

## 图 1：端到端 RAG 主链路

- 标题：从原始 SKU Offer 到可验证推荐
- 布局：横向流水线，分成「入库」「召回」「评估」「决策」四个色块
- 入库链路：
  1. 平台实际 SKU + 卖家报价
  2. 保留原字段名、原值、scope、来源和版本
  3. 确定性生成唯一 `search_text`
  4. `search_text` ── `text-embedding-v4` ──→ Dense 索引
  5. `search_text` ── 中英文分词 + 倒排统计（TF / DF / 文档长度）──→ BM25 词法索引
- 召回链路：
  1. 用户需求 + 冻结约束
  2. 原查询 ── `DeepSeek-V4-Flash` ──→ 至多 2 条有界语义扩展
  3. 多查询 ── `text-embedding-v4` Dense + BM25 词法检索 ──→ 混合召回
  4. RRF 融合为召回池 Top 100
  5. Top 100 ── `qwen3-rerank` ──→ 精排；失败则完整回退 RRF 顺序
- 评估链路：多样性选择 Top 40 → 动态局部 Schema → 字段和值归一化 → 硬要求三态校验 `satisfied / conflict / unknown` → 同款、SKU、价格比较
- 决策链路：
  - 结果足够 → 带证据回答
  - 需求含糊 → 追问用户
  - 有明确单步查询 → 直接补召回
  - 需要多步调查 → 委派 ResearchSubagent

## 图 2：多查询混合召回与 RRF

- 标题：多种说法负责找全，固定融合负责去重
- 左侧输入示例：用户需求「iPhone 15 Pro 256GB 国行版」
- 中间三条查询卡：
  - Q1：`iPhone 15 Pro 256GB 国行`
  - Q2：`Apple iPhone 15 Pro 256G 中国大陆版`
  - Q3：`苹果15Pro 256GB 大陆行货`
- 每条查询分别进入两个通道：
  - Dense 语义召回：`text-embedding-v4` 生成查询向量 → 向量相似度 TopK
  - BM25 词法召回：查询分词 → 命中倒排索引 → 按词频、逆文档频率和文档长度归一化打分 → TopK
- 两个通道分别保留有序名次和健康状态；BM25 不需要神经网络模型
- 融合面板：
  - 同一 Offer 在同一通道只取所有查询中的最佳名次
  - 同分时按 `offer_id` 稳定排序
- 右侧输出：去重命中池 → RRF Top 100 → Reranker 一次性精排 → 多样性 Top 40

## 图 3：Reranker 精排

- 标题：RRF 负责找全，Reranker 负责把更相关的 iPhone 排到前面
- 左侧输入：
  - Query：原始需求「iPhone 15 Pro 256GB 国行版」+ 冻结语义要求；不分别使用三条扩展查询重复精排
  - Documents：RRF Top 100，每个 Offer 只出现一次
  - 单条 Document 白名单：标题、原始类目、来源明确的品牌 / 型号、SKU 级原始属性及 scope
- 排序示意：与 iPhone 型号、容量和版本要求更相关的候选向前，不完整或不匹配的候选向后
- 输出校验：Offer ID 必须全部来自本次输入且唯一，分数必须是有限数值，不能缺失候选或返回未知 ID
- 成功路径：相关性分数降序 → 同分按 RRF 名次和 `offer_id` → 商品多样性选择 Top 40
- 失败路径：超时、限流或响应非法 → 整批放弃精排，完整回退 RRF 顺序；禁止把半批模型结果和半批 RRF 结果拼接

## 图 4：动态 Schema 与 iPhone 容量语义

- 标题：先召回原始字段，再在请求内理解字段和值
- 顶部：用户硬要求「iPhone 15 Pro 256GB」；局部概念卡「机身存储容量 = 256GB」
- 中部四张候选卡，展示“来源原文 → 局部语义 → 资格结果”：
  - A：`机身容量: 256GB` → 当前 iPhone SKU 的存储容量 → `satisfied`
  - B：`storage: 256G`，上下文为当前 iPhone SKU → 证据和 scope 校验后可映射 → `satisfied`
  - C：`赠送 iCloud 云存储: 256GB`，机身容量缺失 → 云存储不能证明机身容量 → `unknown`
  - D：`storage: 128GB` → 与 256GB 硬要求冲突 → `conflict`
- 底部资格门禁：
  - `satisfied` → 可进入同款、SKU 和价格比较
  - `unknown` → 只进入待核实调查池，不进入确认最低价组
  - `conflict` → 排除
