# 数据与 Mock 策略

## 概述

当前阶段使用人工构造数据支撑聊天式 AI 识别与多平台 Mock 推荐演示。Mock 数据只用于本地开发、接口联调、自动化测试和页面验收，不代表真实平台商品、真实价格、真实库存或真实用户数据。

详细字段说明与品牌覆盖见 [../mock-data/README.md](../mock-data/README.md)。

## Mock 商品范围

当前内置 5 类商品，总计 60 个：

| 类别 | 平台数量 | 每个平台商品数 | 说明 |
|------|----------|----------------|------|
| 运动鞋 | 3 | 4 | 默认购物品类，覆盖低价/中档/高档 |
| 耳机 | 3 | 4 | 支持文字需求和识别 category 继承 |
| 吹风机 | 3 | 4 | 支持文字需求直接推荐 |
| 背包 | 3 | 4 | 新增品类，覆盖运动/商务/学院风 |
| 智能手表 | 3 | 4 | 新增品类，覆盖运动/商务/时尚 |

每个品类刻意制造差异，覆盖：
- 低价款（支持预算筛选）
- 官方/自营款（支持 official_store 偏好）
- 高评分款（支持 highRating 偏好）
- 高销量款（支持 highSales 偏好）
- 不同颜色（支持颜色筛选）
- 不同品牌（支持品牌筛选）
- 有明显短板的商品（rating < 4.5 或非官方渠道，供推荐解释生成不足分析）

价格分布覆盖低/中/高三档，预算筛选有层次。覆盖 11 个常见品牌：耐克、阿迪达斯、新百伦、李宁、索尼、森海塞尔、小米、华为、苹果、戴森、飞利浦、松下。

平台名称固定为：

- `京东-mock`
- `拼多多-mock`
- `淘宝-mock`

## 当前数据来源

### 后端内存 Mock 商品

商品数据由 `MockProductSourceProvider` 提供，字段包括：

- `productId`
- `title`
- `platform`
- `price`
- `originalPrice`
- `shopName`
- `imageUrl`
- `productUrl`
- `rating`
- `sales`
- `tags`
- `reasons`
- `score`
- `brand`（新增）
- `priceHistory`（新增，5 点近期价格走势）
- `matchedPreferences`（新增，由 `RecommendationScorer` 评分时填充）

### 推荐评分

`MockProductSourceProvider` 先生成当前品类下三平台商品，再按预算、颜色、品牌、平台、最低评分依次过滤，最后按 sortBy 排序。

`RecommendationScorer` 根据以下规则生成分数和理由：

- 价格最低偏好
- 官方店铺 / 自营偏好
- 配送更快偏好
- 高评分
- 高销量
- 预算上限
- 品牌命中
- 最低评分门槛

同时记录命中的偏好 key 到 `matchedPreferences`：
- `low_price` / `official_store` / `fast_delivery`
- `high_rating` / `high_sales`
- `budget_match` / `brand_match` / `min_rating_met`

### 推荐解释

`RecommendationExplainer` 基于商品结果和用户偏好生成：

- 综合分（加权：意图匹配 25% + 价格 25% + 信誉 20% + 渠道 15% + 风险 15%）
- 决策信号：意图匹配、价格、店铺信誉、渠道可信、风险
- 证据摘要：预算、颜色、品牌、平台、最低评分、排序方式、当前推荐价格
- 风险提示：Mock 数据声明、配送时效
- 商品胜因/不足

`AI_PROVIDER=ark` 时，`ArkRecommendationExplainer` 可改写面向用户的解释文本；Ark 不可用时回退规则解释。Ark 改写不改变商品 ID、平台、价格、商品名、排序和数值分数。

### 平台比价统计

`MockProductSourceProvider` 输出 `PlatformStats`：

- `platform`：平台名
- `lowestPrice`：当前过滤后最低价
- `averagePrice`：当前过滤后均价（新增）
- `productCount`：商品数
- `highlight`：平台亮点

### 文档与演示数据目录

```text
mock-data/
├── README.md
├── chat-agent-scenarios.json
├── recognition-samples.json
├── products.json
└── platform-products.json
```

这些文件用于说明和演示，不作为当前后端运行时的唯一数据来源。

## 图片识别数据

识别结果来自两类 Provider：

- Mock Provider：返回稳定演示结果。
- Ark Provider：通过环境变量配置后调用真实 AI；调用失败时回退 Mock。

识别结果保存到内存 `RecognitionStore`，支持用户修正类别、品牌、型号和属性。

## 历史数据

聊天历史当前支持：

- 会话列表
- 消息恢复
- assistant 消息中的完整 `agentReply`
- 商品卡、比价卡、识别卡、动态建议卡和推荐卡恢复

默认使用内存仓库。Postgres 落地仍为后续迭代（`PostgresChatHistoryRepository` 类已埋桩）。

## 约束

- Mock 数据均为人工构造示例。
- 不包含真实用户数据。
- 不包含爬取数据。
- 不包含真实密钥、Token 或个人信息。
- 不把 Mock 数据描述为真实平台数据。
- 真实平台接口接入后，Mock 数据仍作为演示模式和降级数据。
