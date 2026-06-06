# 数据与 Mock 策略

## 概述

当前阶段使用少量人工构造数据支撑聊天式 AI 识别与多平台 Mock 推荐演示。Mock 数据只用于本地开发、接口联调、自动化测试和页面验收，不代表真实平台商品、真实价格、真实库存或真实用户数据。

## Mock 商品范围

当前内置三类商品：

| 类别 | 平台数量 | 每个平台商品数 | 说明 |
|------|----------|----------------|------|
| 运动鞋 | 3 | 2 | 默认购物品类 |
| 耳机 | 3 | 2 | 支持文字需求和识别 category 继承 |
| 吹风机 | 3 | 2 | 支持文字需求直接推荐 |

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

### 推荐评分

`RecommendationScorer` 根据以下规则生成分数和理由：

- 价格最低偏好
- 官方店铺 / 自营偏好
- 配送更快偏好
- 高评分
- 高销量
- 预算上限

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
- 商品卡、比价卡、识别卡和追问卡恢复

默认使用内存仓库。Postgres 落地仍为后续迭代。

## 约束

- Mock 数据均为人工构造示例。
- 不包含真实用户数据。
- 不包含爬取数据。
- 不包含真实密钥、Token 或个人信息。
- 不把 Mock 数据描述为真实平台数据。
- 真实平台接口接入后，Mock 数据仍作为演示模式和降级数据。
