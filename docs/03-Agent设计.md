# Agent 设计

## Agent 定位

本项目中的 Agent 是购物决策 Agent。它不直接相信前端传入的完整商品、价格或评价数据，而是通过 `searchTaskId` 和候选商品 ID，从后端可信数据中读取证据，再生成购买建议。

Agent 对应 API：

```http
POST /api/agent/recommendations
```

## Agent 输入

前端请求只允许传入：

```json
{
  "searchTaskId": 3001,
  "userQuery": "500 元以内，适合宿舍用，噪音小一点，售后靠谱",
  "candidateIds": [5001, 5002, 5003]
}
```

后端从登录态解析当前用户，并校验：

- `searchTaskId` 属于当前用户
- `candidateIds` 都来自该搜索任务的候选结果
- 商品、价格、历史价格和评价摘要从后端数据库或工具结果读取

## Agent 可用上下文

| 数据 | 来源 | 用途 |
| --- | --- | --- |
| 用户需求 | `userQuery` | 提取预算、场景、品牌偏好、风险偏好 |
| 识别结果 | `recognitions` | 理解目标商品类别、品牌、型号、关键词 |
| 搜索结果 | `search_task_items` | 获取候选平台商品和 `match_score` |
| 平台商品 | `platform_products` | 获取标题、平台、价格、店铺和来源 |
| 历史价格 | `price_records` | 判断当前价格高低 |
| 评价摘要 | `review_summaries` | 判断售后、物流、质量等风险 |
| 用户行为 | `favorites`、`price_alerts` | 当前已用于演示用户资产沉淀，后续可进一步做个性化推荐 |

## Agent 工具

| 工具 | 作用 |
| --- | --- |
| search_task_reader | 读取当前用户的搜索任务和候选结果 |
| product_context_reader | 读取标准商品、平台商品和匹配分 |
| price_history_tool | 查询平台商品历史价格和趋势 |
| review_summary_tool | 查询评价摘要和风险标签 |
| price_compare_tool | 比较候选商品价格 |
| recommendation_writer | 保存推荐结果和证据链 |

## 决策流程

```text
校验 searchTaskId 和 candidateIds
  -> 解析 userQuery 中的购物约束
  -> 读取候选商品、匹配分、价格、历史价格和评价摘要
  -> 过滤明显不符合需求的商品
  -> 按匹配分、价格、趋势、风险综合排序
  -> 生成 suggestion、reasons、risks 和 evidence
  -> 保存 recommendationId 和推荐快照
```

## 输出格式

Agent 输出必须对齐 `/api/agent/recommendations`：

```json
{
  "recommendationId": 7001,
  "searchTaskId": 3001,
  "suggestion": "buy",
  "recommendedPlatformProduct": {
    "platformProductId": 5001,
    "platform": "jd",
    "title": "某品牌低噪音宿舍吹风机",
    "price": {
      "amount": "199.00",
      "currency": "CNY"
    },
    "matchScore": 0.91
  },
  "reasons": [
    "同款匹配度较高",
    "当前价格低于候选商品平均价",
    "评价风险主要集中在物流而非质量"
  ],
  "risks": [
    "历史最低价为 189 元，当前不是绝对最低价"
  ],
  "evidence": [
    {
      "type": "price",
      "platformProductId": 5001,
      "content": "当前价 199.00 CNY，为候选商品最低价"
    }
  ]
}
```

`suggestion` 可取：

- `buy`：建议购买
- `wait`：建议等待降价
- `avoid`：不建议购买
- `compare`：需要继续比较

## 证据链规则

- 每条推荐理由必须至少能关联到一类证据：匹配分、当前价格、历史价格、评价摘要、用户约束
- `evidence.type` 可取 `price`、`history`、`match`、`review`、`constraint`
- 不允许编造平台价格、历史价格、评价数量或风险标签
- 数据缺失时必须明确风险，例如“暂无历史价格，趋势判断为 unknown”
- 低置信度识别结果必须提醒用户补充关键词或重新上传图片

## 数据隔离

- Agent 只能读取当前用户授权范围内的 `searchTaskId`、`candidateIds`、收藏、价格提醒和推荐记录
- Agent 可以读取公共商品库、平台商品库、价格记录和评价摘要
- Agent 不允许跨用户读取图片、识别记录、搜索任务、推荐记录或用户行为数据
