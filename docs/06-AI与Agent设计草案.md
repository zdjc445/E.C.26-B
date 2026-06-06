# AI 与 Agent 设计草案

## 概述

项目的 AI 与 Agent 能力分为两个阶段：

1. **当前阶段：** Mock Agent 根据固定规则返回追问卡片和推荐卡片
2. **后续阶段：** 引入真实 AI Provider，完成图片识别、自然语言理解和购买推荐

当前阶段不调用真实模型，不输出真实模型推理链。

## 当前 Mock Agent

```text
用户消息
  ├─ 包含 text
  ├─ 包含 imageIds
  └─ 包含 selectedOptionIds
        ↓
Mock Agent 判断输入状态
        ↓
信息不足：返回 clarification 卡片
信息足够：返回 recommendation 卡片
```

### 追问卡片

当用户首次发送文字或图片后，Mock Agent 返回固定追问：

```text
你更看重哪一点？
```

固定选项：

| optionId | label |
|----------|-------|
| lowest_price | 价格最低 |
| official_store | 官方店铺 |
| fast_delivery | 配送更快 |

### 推荐卡片

当用户点击追问选项后，Mock Agent 返回推荐卡片。当前推荐内容来自人工构造的 Mock 数据，展示字段包括：

- 商品名
- 平台，名称统一带 `-mock` 后缀
- 价格
- 推荐理由

## 后续 AI Provider 架构

```text
                    ┌─────────────────┐
                    │  AI Provider    │
                    │  Interface      │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
     ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
     │ Mock         │  │ Ark         │  │ Future       │
     │ Provider     │  │ Provider    │  │ Providers    │
     └──────────────┘  └──────────────┘  └──────────────┘
```

### 计划接口

- `AiRecognitionProvider`
  - 图片识别接口
  - 输入图片或图片 ID
  - 输出类目和属性
- `AiIntentProvider`
  - 自然语言意图解析接口
  - 输入用户文本和会话上下文
  - 输出筛选条件与追问建议
- `AiRecommendationProvider`
  - 购买推荐接口
  - 输入商品数据和用户偏好
  - 输出推荐结论与解释摘要

## Prompt 工程原则（后续）

- Prompt 模板化管理
- 使用 JSON 格式约束模型响应
- 非 JSON 响应进入规则兜底
- 对外只展示解释摘要，不展示内部推理链
- Mock Provider 保留为演示模式和降级能力

## 当前阶段状态

- Mock Agent：已实现固定追问卡片与推荐卡片
- Ark Provider：后续迭代
- 真实图片识别：后续迭代
- 真实自然语言理解：后续迭代
- 完整 Agent 推荐与证据摘要：后续迭代
