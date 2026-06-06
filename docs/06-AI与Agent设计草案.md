# AI 与 Agent 设计草案

## 概述

当前项目已具备 Mock/Ark 图片识别路径、多平台 Mock 商品推荐和聊天式 Agent 卡片输出。AI 与 Agent 设计遵循两个原则：

- 对外展示结构化结果和解释摘要，不展示真实模型推理链。
- 外部服务不可用时保持 Mock 降级，保证演示闭环可运行。

## 当前 AI Provider

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
文字购物意图：生成 product_recommendation
选项：继承最近用户文本预算和最近识别 category
        ↓
MockProductSourceProvider 生成三平台商品
        ↓
RecommendationScorer 排序
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

当前解释为轻量摘要：

- 命中价格偏好时添加价格理由。
- 命中官方/自营时添加渠道理由。
- 命中配送偏好时添加物流理由。
- 高评分、高销量会增加评分理由。
- 预算过滤影响最终商品集合。

## 下一阶段推荐解释增强

后续建议参考以下设计方向：

- 决策信号：
  - 意图匹配
  - 价格
  - 口碑
  - 渠道可信
  - 风险
- 输出增强：
  - 综合分
  - 推荐理由
  - 风险提示
  - 证据摘要
  - 商品胜因/不足
  - 多商品对比矩阵

## 自然语言筛选增强方向

后续可增强规则或 AI 解析能力，将自然语言转为筛选条件：

- 预算上限 / 下限
- 颜色
- 品牌
- 类别
- 最低评分
- 官方店铺
- 自营
- 排序方式
- 指定平台

当前阶段仅实现与聊天推荐闭环相关的轻量规则解析。

## 未完成能力

- 真实电商 API 查询
- 真实平台价格、库存、评价和店铺校验
- 完整 Agent 决策记录
- 独立自然语言意图 Provider
- 真实语音识别
