# Mock 数据说明

本文档说明项目中用于演示和测试的本地模拟数据。比赛允许在缺乏合规 API 或数据来源时使用 mock 数据；本项目默认使用 mock 数据完成“识别 -> 检索 -> 比价 -> 推荐”的主链路，不使用爬虫或未授权采集。

## 使用结论

| 问题 | 结论 |
| --- | --- |
| 商品价格数据是否必须接真实平台 | 不必须，mock 价格数据可以满足比赛主链路演示 |
| 平台最低价和均价是否可以由 mock 计算 | 可以，由 `platform-products.json` 中同类平台商品价格聚合得到 |
| 历史价格走势是否可以 mock | 可以，由 `price-history.json` 提供固定时间点价格 |
| 是否允许后续接真实 API | 可以，但必须使用合法授权的官方开放平台 API |
| 是否允许爬虫 | 不允许 |

## 数据文件

| 文件 | 用途 | 关键字段 |
| --- | --- | --- |
| `mock-data/products.json` | 商品主数据，描述抽象商品 | `productId`、`name`、`category`、`brand`、`model`、`attributes` |
| `mock-data/platform-products.json` | 平台商品数据，支撑推荐列表、排序、比价和平台统计 | `platformProductId`、`productId`、`platform`、`title`、`price`、`shopName`、`tags`、`salesVolume`、`rating`、`isOfficial`、`isSelfOperated` |
| `mock-data/price-history.json` | 历史价格数据，支撑历史价格走势和推荐 evidence | `platformProductId`、`points.recordedAt`、`points.price` |
| `mock-data/review-summaries.json` | 评价摘要数据，支撑风险提示和推荐理由 | `rating`、`reviewCount`、`positiveTags`、`riskTags`、`riskScore`、`summary` |
| `mock-data/recognitions.json` | 识别样例数据，支撑 mock AI 识别结果 | `mockImageName`、`category`、`brand`、`model`、`keywords`、`attributes`、`confidence` |

## 覆盖类目

当前 mock 数据覆盖以下商品类目：

- 吹风机
- 耳机
- 手机
- 键盘
- 水杯
- 运动鞋
- 护肤品

Web/PWA 演示端的“演示场景”会生成与 `mock-data/recognitions.json` 中 `mockImageName` 对应的示例图片文件名，因此可直接演示上述多类目的 mock 识别、召回、比价、商品洞察和 Agent 推荐链路。

识别样例中的品牌和型号与 `products.json` 对齐，例如耳机场景会识别为 `Auralis ANC-20`，吹风机场景会识别为 `LumaCare HD-001`。这样证据报告中的“识别意图”轨迹可以展示完整的商品身份，而不是只展示类目。

耳机场景专门保留 3 个可比较候选：官方标准价、京东自营高确定性和拼多多官方补贴低价款。该组合用于展示“价格更低但售后风险更高”“价格略高但履约更稳”等胜因/败因矩阵，而不是只返回单一商品。

## 价格数据说明

`platform-products.json` 中的 `price` 是当前平台商品价，`originalPrice` 是原价或划线价。比价功能会基于候选商品计算：

- 各平台最低价
- 各平台平均价
- 各平台商品数
- 多商品横向对比表

`price-history.json` 中的价格点用于展示 90 天历史价格走势，并辅助 Agent 判断当前价格是否接近历史低位。所有价格均为模拟数据，仅用于功能演示和测试，不代表真实商品实时价格。

## 合规边界

当前 mock 数据遵循以下边界：

- 商品名称、品牌和店铺名均使用虚构品牌命名，避免冒充真实商品或真实店铺。
- 商品 URL 使用 `example.com` 示例地址，不导向真实购买页。
- 图片 URL 仅作为演示图片占位；如最终提交材料需要完全离线可复现，可后续替换为本地图片资源。
- 不包含真实用户数据、真实订单数据、真实评价明细或任何平台私密数据。
- 不通过爬虫生成，不作为真实价格承诺。

## 与官方 API 的关系

项目同时保留 `official_api` 数据源扩展口，并已实现拼多多和京东官方 API 适配器。它们属于工程扩展和加分项，不是默认演示依赖。

推荐交付口径：

```text
本项目默认使用 mock 商品库和 mock 价格数据完成比赛主链路演示，数据用于功能闭环验证，不来自非法采集。系统保留 official_api 数据源扩展口，已实现拼多多/京东官方开放平台适配器；如具备合法授权凭证，可切换到官方 API 联调。正式演示不依赖爬虫或未授权数据。
```
