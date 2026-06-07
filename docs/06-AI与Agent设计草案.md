# AI 与 Agent 设计草案

## 概述

当前项目已具备 Mock/Ark 图片识别路径、规则/Ark 购物意图解析路径、规则/Ark 推荐解释路径、多轮自然语言追加筛选、多平台 Mock 商品推荐和聊天式 Agent 卡片输出。AI 与 Agent 设计遵循两个原则：

- 对外展示结构化结果和解释摘要，不展示真实模型推理链。
- 外部服务不可用时保持 Mock 降级，保证演示闭环可运行。

详细的 Prompt 设计、AI Coding 实践参考 [10-AI使用总结.md](10-AI使用总结.md)。

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
- Prompt 要求 `category` 优先输出标准品类；细分词进入 `attributes.subCategory`。后端仍通过 `CategoryResolver` 做最终归一。
- 包含 `normalizeContentType` 把错误声明的 `application/octet-stream` 通过头字节修正为 `image/jpeg` 或 `image/png`。

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

- 默认使用规则解析，支持预算上限、颜色、官方/旗舰/自营、配送、低价、好评、销量倾向、品牌、平台、排序方式、最低评分共 11 项字段。
- `AI_PROVIDER=ark` 时优先使用 Ark 意图解析；Ark Prompt 同样覆盖上述 11 项字段。
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
图片：生成 recognition + 动态建议卡（含 6 个差异化选项）
文字购物意图：解析品类/预算/颜色/品牌/平台/排序/最低评分/偏好，生成 product_recommendation
追加筛选：合并当前文本、历史文本和识别卡 category，跨轮累积偏好
选项：继承最近文本预算 + 最近识别 category，并合并选项偏好
        ↓
CategoryResolver 通过 mock-data/category-taxonomy.json 归一标准品类
        ↓
MockProductSourceProvider 生成 5 品类 × 3 平台 × 4 商品
        ↓
按预算、颜色、品牌、平台、最低评分过滤；按 sortBy 排序
        ↓
RecommendationScorer 评分并记录 matchedPreferences
        ↓
RecommendationExplainer / ArkRecommendationExplainer 生成解释
        ↓
输出 product_list + comparison + recommendation
        ↓
product_list 携带 filterSummary，前端显式展示当前生效条件
```

## 当前卡片类型

| cardType | 说明 |
|----------|------|
| clarification | 动态建议卡，按识别 category 生成差异化选项 |
| recognition | 图片识别结果 |
| product_list | 多平台商品列表（含当前条件摘要、品牌徽章、偏好命中徽章、价格走势 sparkline） |
| comparison | 平台比价（含最低价、均价、平台亮点） |
| recommendation | 推荐购买（含综合分、五维决策信号、证据摘要、风险提示、商品对比、Provider 状态） |

## 当前 Agent 解释

当前解释为结构化摘要：

- 命中价格偏好时添加价格理由。
- 命中官方/自营时添加渠道理由。
- 命中配送偏好时添加物流理由。
- 高评分、高销量会增加评分理由。
- 预算过滤影响最终商品集合。
- 颜色过滤会收窄商品集合，并进入证据摘要。
- 品牌、平台、排序方式、最低评分各自进入证据摘要。

## 多轮上下文合并

`MockAgent.mergeContext` 在同一会话中合并用户后续追加的短句筛选条件，例如 `只看300以内的黑色款`、`120以内`、`官方店铺优先`、`只看京东的4.8分以上`。

合并规则：

- **品类：** 当前文本明确品类 > 历史文本明确品类 > 历史识别卡 category > 默认运动鞋；所有入口先经过 `CategoryResolver` 归一为标准品类。
- **数值字段（maxPrice/color/brand/平台/排序/最低评分）：** 使用最近一次明确值，当前文本可覆盖历史值。
- **偏好布尔（officialStore/fastDelivery/lowestPrice/highRating/highSales）：** 跨轮累积。
- `ProductSearchQuery` 当前包含 `keyword`、`preferences`、`maxPrice`、`color`、`brand`、`platforms`、`sortBy`、`minRating`。
- `MockProductSourceProvider` 在预算过滤后依次进行颜色、品牌、平台、最低评分过滤，最后按 sortBy 排序。

## 品类归一与 RAG 扩展

`CategoryResolver` 当前使用本地 taxonomy JSON 做轻量检索，维护标准品类、别名和属性 schema。它覆盖规则文本解析、Ark 文本意图解析、Ark 图片识别 category、多轮上下文和动态建议卡。

当前示例：

- `头戴式蓝牙耳机` / `真无线蓝牙耳机` → `耳机`
- `跑鞋` → `运动鞋`
- `电吹风` → `吹风机`
- `双肩包` → `背包`
- `运动手表` → `智能手表`

真实上线时可把本地 taxonomy 检索替换为 RAG：标准品类、别名和属性 schema 建索引，先召回 TopK，再由 AI 在受限集合中选择标准 `categoryId`。

## 已完成推荐解释增强

当前推荐卡已输出以下结构化解释字段：

- `decisionScore`：综合分。
- `decisionSignals`：意图匹配、价格、店铺信誉、渠道可信、风险。
- `evidence`：预算、颜色、品牌、平台、最低评分、排序方式、价格等证据摘要。
- `risks`：Mock 数据、配送时效等风险提示。
- `productAnalyses`：商品胜因/不足和排序分数。
- `intentProvider` / `intentFallbackUsed`：意图解析来源。
- `explanationProvider` / `explanationFallbackUsed`：解释生成来源。
- `notices`：Ark 回退和用户修正等提示。

## 自然语言筛选支持矩阵

| 维度 | 支持表达示例 |
|------|--------------|
| 预算 | `300以内`、`300以下`、`不超过300`、`预算300` |
| 颜色 | 深蓝色、黑色、白色、蓝色、银色、红色、绿色、粉色、灰色 |
| 官方/自营 | `官方店铺`、`旗舰店`、`自营`、`只看官方` |
| 配送 | `配送快`、`物流快`、`尽快到` |
| 低价 | `低价`、`便宜`、`价格低`、`价格最低` |
| 高评分 | `评分高`、`好评`、`评价高` |
| 高销量 | `销量高`、`爆款`、`热销` |
| 品牌 | 11 个常见品牌：耐克/阿迪达斯/李宁/安踏/新百伦/索尼/森海塞尔/小米/华为/苹果/戴森/飞利浦/松下，含中英文 |
| 平台 | `京东`/`拼多多`/`淘宝`/`天猫`/JD/PDD 等 |
| 排序方式 | `价格从低到高`、`价格升序`、`价格从高到低`、`销量优先`、`好评率最高`、`综合推荐` |
| 最低评分 | `评分4.8以上`、`4.5星以上`、`4.5分起` |

## 未完成能力

- 真实平台价格、库存、评价和店铺校验不进入当前交付范围
- 完整 Agent 决策记录持久化或导出
- 真实 Ark 图片识别批量实测记录与截图
- 真实语音识别
