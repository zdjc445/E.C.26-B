# AI 与 Agent 设计草案

## 概述

项目的 AI 能力分为两个层面：

1. **AI 识别层：** 使用 VLM（视觉语言模型）对商品图片进行类目识别与属性提取
2. **Agent 编排层：** 使用 LLM 进行意图理解、筛选条件解析与购买决策推荐

## AI Provider 架构

```text
                    ┌─────────────────┐
                    │  AI Provider    │
                    │  (Interface)    │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
     ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
     │ Mock         │  │ Ark         │  │ Future       │
     │ Provider     │  │ Provider    │  │ Providers    │
     └──────────────┘  └──────────────┘  └──────────────┘
```

### AI Provider 接口（计划）

- `AiRecognitionProvider` — 图片识别接口
  - `recognize(image)` → `RecognitionResult`
- `AiRefineProvider` — 自然语言筛选解析接口
  - `parseFilter(text, context)` → `FilterConditions`

### Mock Provider（当前阶段默认）

- 返回预定义的占位识别结果
- 离线可用，保证骨架阶段开发调试不受 AI 服务影响

### Ark Provider（后续迭代）

- 调用火山引擎 Ark API
- 模型：Doubao-Seed-2.0-lite
- 需配置 `ARK_API_KEY` 和 `ARK_ENDPOINT_ID`
- 调用失败时自动 fallback 到 Mock

## Agent 设计（后续迭代）

### 决策流程

```text
候选商品列表 → 多维评分 → 决策矩阵 → 推荐输出
                        ↓
                  决策轨迹 + 候选胜因/败因
```

### 评分维度

- 价格竞争力
- 平台可靠性（自营/官方旗舰店）
- 用户评价
- 与用户筛选条件匹配度

### 输出格式

- 推荐结论（首选 / 备选）
- 决策信号（价格优势、平台可靠等）
- 决策轨迹（关键决策步骤）
- 候选矩阵（各商品多维度得分对比）
- 证据链（支撑推荐结论的具体数据点）

## Prompt 工程原则（计划）

- 系统 Prompt 设计保证结构化输出
- 使用 JSON 格式约束响应
- 非 JSON 响应自动 fallback 到规则引擎
- Prompt 模板化管理，便于迭代与 A/B 测试

## 当前阶段状态

- AI Provider 接口与 Mock 实现：后续迭代
- Ark Provider 集成：后续迭代
- Agent 决策引擎：后续迭代
- Prompt 模板：后续迭代
