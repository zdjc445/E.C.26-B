# 数据与样例策略

## 概述

当前阶段默认使用公开样例商品数据支撑聊天式 AI 识别与多平台推荐演示。

- 默认商品目录文件：`backend/src/main/resources/data/public-product-offers.json`
- 默认商品源模式：`public-dataset-platforms`
- 数据来源记录：`jason1966/PromptCloudHQ_flipkart-products`，原始文件名 `flipkart_com-ecommerce_sample.csv`
- 可切换本地商品目录：`mock-data/mock-data.json`
- 品类 taxonomy：`mock-data/category-taxonomy.json`
- 后端商品源：`CompositeProductSourceProvider`
- 商品源状态名：`public-dataset-platforms`

这些数据只用于本地开发、接口联调、自动化测试和页面验收。公开样例商品保留原始标题、图片和链接；平台报价由系统生成，不代表真实平台价格、库存、评价、店铺或配送服务。

## 商品范围

`public-product-offers.json` 当前收录公开样例商品，覆盖当前演示需要的标准品类。系统按标准品类检索，并在运行时扩展为平台报价。

本地 `mock-data/mock-data.json` 仍保留为可切换演示源，当前包含 26 个基础商品，覆盖运动鞋、耳机、吹风机、背包 4 个品类和 24 个品牌。

## 数据结构

`public-product-offers.json` 的基础商品字段：

- `productId`
- `category`
- `title`
- `platform`
- `price`
- `originalPrice`
- `shopName`
- `imageUrl`
- `productUrl`
- `rating`
- `sales`
- `brand`
- `tags`
- `sourceCategory`
- `rawRating`

运行时由 `PublicDatasetProductSourceProvider` 基于公开样例商品生成平台报价。平台报价会补齐或保留：

- `platform`
- `price`
- `originalPrice`
- `shopName`
- `rating`
- `sales`
- `tags`
- `priceHistory`
- `sameItemKey`
- `matchedPreferences`

`sameItemKey` 使用公开样例商品的原始 `productId`，用于把同一商品的不同平台报价聚合为同款商品分组。

## 平台样例报价

当前平台名称固定为：

- `京东-mock`
- `淘宝-mock`
- `天猫-mock`
- `拼多多-mock`

平台展示亮点由 `ProductSearchResults.highlight()` 生成：

| 平台 | 亮点 |
|------|------|
| 京东-mock | 自营保障，物流快 |
| 拼多多-mock | 价格优势明显 |
| 淘宝-mock | 品类丰富，选择多 |
| 天猫-mock | 品牌旗舰，正品保障 |

## 商品检索链路

默认商品源读取公开样例文件，并按平台生成样例报价。旧的本地 `mock-data` 商品源可通过 `PRODUCT_SOURCE_MODE=mock-data` 切换。

运行链路如下：

```text
ProductSearchQuery
  → ArkQueryDecomposer / QueryRewriter
  → CategoryResolver 归一品类
  → PublicDatasetProductSourceProvider 读取公开样例商品
  → public-dataset-platforms 生成四平台报价
  → RecommendationScorer 规则评分
  → ProductSearchResults 聚合平台统计
  → MockAgent 生成 ProductGroup 同款分组
```

过滤顺序：

1. 品类
2. 品牌
3. 平台
4. 预算上限
5. 最低评分

排序字段：

- `recommended`
- `price_asc`
- `price_desc`
- `sales_desc`
- `rating_desc`

## 轻量品类 taxonomy

`mock-data/category-taxonomy.json` 维护标准品类、别名和属性 schema。后端 `CategoryResolver` 在文本解析、Ark 识别结果、多轮上下文合并和动态建议卡生成前统一做品类归一。

当前归一示例：

- `头戴式蓝牙耳机` / `真无线蓝牙耳机` → `耳机`
- `跑鞋` → `运动鞋`
- `电吹风` → `吹风机`
- `双肩包` → `背包`
- `运动手表` → `智能手表`

注意：taxonomy 中保留 `智能手表`，用于识别归一和动态建议；是否返回商品取决于当前商品源是否包含对应公开样例商品。

## 推荐评分与重排

`RecommendationScorer` 根据以下因素生成分数和理由：

- 价格最低偏好
- 官方店铺 / 自营偏好
- 配送更快偏好
- 高评分
- 高销量
- 预算上限
- 品牌命中
- 最低评分门槛

同时记录命中的偏好 key 到 `matchedPreferences`：

- `low_price`
- `official_store`
- `fast_delivery`
- `high_rating`
- `high_sales`
- `budget_match`
- `brand_match`
- `min_rating_met`

`ResultReRanker` 在规则评分基础上叠加文本相关性、用户画像匹配和多样性约束，避免前几组结果被单一品牌或单一平台占满。

## 推荐解释

`RecommendationExplainer` 基于商品结果和用户偏好生成：

- 综合分
- 决策信号：意图匹配、价格、店铺信誉、渠道可信、风险
- 证据摘要：预算、颜色、品牌、平台、最低评分、排序方式、当前推荐价格
- 风险提示：样例数据声明、配送时效
- 商品胜因/不足

`AI_PROVIDER=ark` 时，`ArkRecommendationExplainer` 可改写面向用户的解释文本；Ark 不可用时回退规则解释。Ark 改写不改变商品 ID、平台、价格、商品名、排序和数值分数。

## 文档与演示数据目录

```text
backend/src/main/resources/data/
└── public-product-offers.json

mock-data/
├── README.md
├── category-taxonomy.json
└── mock-data.json
```

## 约束

- 公开样例商品只用于演示和测试。
- 平台报价由系统生成。
- 不包含真实用户数据。
- 仓库不包含自行爬取脚本。
- 不包含真实密钥、Token 或个人信息。
- 不把样例报价描述为真实平台数据。
- 真实平台接口不在当前交付范围；当前商品搜索不调用真实电商接口。
