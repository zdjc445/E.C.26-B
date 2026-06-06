# AI 与 Agent 设计草案

## 概述

当前项目已具备 Mock/Ark 图片识别路径、规则/Ark 购物意图解析路径、规则/Ark 推荐解释路径、多轮自然语言追加筛选、多平台 Mock 商品推荐和聊天式 Agent 卡片输出。AI 与 Agent 设计遵循两个原则：

- 对外展示结构化结果和解释摘要，不展示真实模型推理链。
- 外部服务不可用时保持 Mock 降级，保证演示闭环可运行。

## 当前 AI Provider

### 图片识别 Provider

```text
AiRecognitionProvider
  ├─ MockRecognitionProvider
  ├─ ArkRecognitionProvider
  └─ FallbackRecognitionProvider
```

### MockRecognitionProvider

- 默认 Provider。
- 返回稳定识别结果，适合本地演示和测试。

### ArkRecognitionProvider

- 通过 Ark Chat Completions 接口调用视觉模型。
- 输入图片 bytes、content type 和文件名。
- 输出固定结构：
  - `category`
  - `brand`
  - `model`
  - `keywords`
  - `attributes`
  - `confidence`
  - `explanation`

### FallbackRecognitionProvider

- `AI_PROVIDER=ark` 时启用。
- Ark 配置缺失或调用失败时回退 Mock。
- 返回结果中通过 `fallbackUsed` 标记回退状态。

### 购物意图解析 Provider

```text
ShoppingIntentParser
  ├─ RuleBasedShoppingIntentParser
  ├─ ArkShoppingIntentParser
  └─ FallbackShoppingIntentParser
```

- 默认使用规则解析，支持预算上限、部分颜色、官方/旗舰/自营、配送、低价、好评、销量倾向。
- `AI_PROVIDER=ark` 时优先使用 Ark 意图解析。
- Ark 未配置、调用失败或返回需要澄清时回退规则解析。
- 返回结果中通过 `intentProvider` 和 `intentFallbackUsed` 标记解析来源。

### 推荐解释 Provider

```text
RecommendationExplainer
  └─ ArkRecommendationExplainer
```

- 规则解释器生成综合分、决策信号、证据摘要、风险提示和商品胜因/不足。
- `AI_PROVIDER=ark` 时，Ark 只改写面向用户的解释文本。
- Ark 不允许改写 `productId`、平台、价格、商品名、排序和数值分数。
- 返回结果中通过 `explanationProvider` 和 `explanationFallbackUsed` 标记解释来源。

## 配置

```powershell
$env:AI_PROVIDER="mock"
```

```powershell
$env:AI_PROVIDER="ark"
$env:ARK_API_KEY="你的 Ark API Key"
$env:ARK_ENDPOINT_ID="你的 Ark Endpoint ID"
$env:ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
```

## 当前 Agent 流程

```text
用户消息
  ├─ text
  ├─ imageIds
  └─ selectedOptionIds
        ↓
MockAgent 读取会话上下文
        ↓
图片：生成 recognition + clarification
文字购物意图：解析品类、预算、颜色和偏好，生成 product_recommendation
追加筛选：合并当前文本、历史文本和识别卡 category
选项：继承最近用户文本预算和最近识别 category，并合并选项偏好
        ↓
MockProductSourceProvider 生成三平台商品
        ↓
按预算和颜色过滤
        ↓
RecommendationScorer 排序
        ↓
RecommendationExplainer / ArkRecommendationExplainer 生成解释
        ↓
输出 product_list + comparison + recommendation
```

## 当前卡片类型

| cardType | 说明 |
|----------|------|
| clarification | 用户偏好追问 |
| recognition | 图片识别结果 |
| product_list | 多平台商品列表 |
| comparison | 平台比价 |
| recommendation | 推荐购买 |

## 当前 Agent 解释

当前解释为结构化摘要：

- 命中价格偏好时添加价格理由。
- 命中官方/自营时添加渠道理由。
- 命中配送偏好时添加物流理由。
- 高评分、高销量会增加评分理由。
- 预算过滤影响最终商品集合。
- 颜色过滤会收窄商品集合，并进入证据摘要。

## 多轮上下文合并

当前 Agent 会在同一会话中合并用户后续追加的短句筛选条件，例如 `只看300以内的黑色款`、`120以内`、`官方店铺优先`。

合并规则：

- 品类优先级：当前文本明确品类 > 历史文本明确品类 > 历史识别卡 category > 默认运动鞋。
- `maxPrice` 和 `color` 使用最近一次明确值，当前文本可覆盖历史值。
- `official_store`、`fast_delivery`、`lowest_price`、高评分和高销量偏好跨轮累积。
- `ProductSearchQuery` 当前包含 `keyword`、`preferences`、`maxPrice`、`color`。
- `MockProductSourceProvider` 在预算过滤后进行颜色过滤，颜色匹配商品 `title` 或 `tags`。

## 已完成推荐解释增强

当前推荐卡已输出以下结构化解释字段：

- `decisionScore`：综合分。
- `decisionSignals`：意图匹配、价格、店铺信誉、渠道可信、风险。
- `evidence`：预算、颜色、价格等证据摘要。
- `risks`：Mock 数据、配送时效等风险提示。
- `productAnalyses`：商品胜因/不足和排序分数。
- `intentProvider` / `intentFallbackUsed`：意图解析来源。
- `explanationProvider` / `explanationFallbackUsed`：解释生成来源。
- `notices`：Ark 回退和用户修正等提示。

## 自然语言筛选增强方向

当前已落地轻量自然语言筛选闭环：

- 预算上限
- 颜色
- 官方店铺 / 自营
- 配送更快
- 低价倾向
- 高评分倾向
- 高销量倾向
- 追加筛选条件

后续可继续增强规则或 AI 解析能力，将更多自然语言转为筛选条件：

- 品牌
- 最低评分
- 排序方式
- 指定平台

当前阶段已实现与聊天推荐闭环相关的轻量规则解析和上下文合并。后续增强重点是品牌、指定平台、排序方式、数值评分阈值和筛选状态展示。

## 未完成能力

- 真实电商 API 查询
- 真实平台价格、库存、评价和店铺校验
- 完整 Agent 决策记录持久化或导出
- 真实 Ark 图片识别批量实测记录与截图
- 真实语音识别
