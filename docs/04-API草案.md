# API 草案

## 概述

服务端提供 RESTful JSON API。基础路径为 `http://localhost:8080`。

当前已实现接口：

```text
GET    /api/health
POST   /api/images/upload
POST   /api/chat/sessions
GET    /api/chat/sessions
POST   /api/chat/sessions/{sessionId}/messages
GET    /api/chat/sessions/{sessionId}/messages
PATCH  /api/chat/sessions/{sessionId}
DELETE /api/chat/sessions/{sessionId}
POST   /api/recognition
PATCH  /api/recognition/{recognitionId}/attributes
GET    /api/ecommerce/status
```

当前没有独立商品搜索 API。商品推荐通过聊天消息接口返回。

## 统一响应格式

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

错误响应：

```json
{
  "code": 40001,
  "message": "error description",
  "data": null
}
```

## 健康检查

```text
GET /api/health
```

返回服务状态、应用名、阶段和 AI Provider。

## 图片上传

```text
POST /api/images/upload
```

请求：

- `multipart/form-data`
- 文件字段名固定为 `file`

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "imageId": "uuid",
    "fileName": "stored-file-name",
    "contentType": "image/jpeg",
    "size": 12345
  }
}
```

## 聊天会话

### 创建会话

```text
POST /api/chat/sessions
```

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "sessionId": "uuid",
    "createdAt": "ISO-8601"
  }
}
```

### 获取会话列表

```text
GET /api/chat/sessions
```

返回会话摘要列表，按更新时间倒序。

### 获取历史消息

```text
GET /api/chat/sessions/{sessionId}/messages
```

assistant 消息包含 `agentReply`，用于恢复卡片。

### 重命名会话

```text
PATCH /api/chat/sessions/{sessionId}
```

请求体：

```json
{
  "title": "白色运动鞋推荐"
}
```

### 删除会话

```text
DELETE /api/chat/sessions/{sessionId}
```

## 发送聊天消息

```text
POST /api/chat/sessions/{sessionId}/messages
```

请求体：

```json
{
  "text": "用户输入",
  "imageIds": ["uuid"],
  "selectedOptionIds": ["lowest_price"],
  "profile": {
    "preferredPlatforms": ["京东"],
    "inferredBrands": ["Sony"],
    "inferredPriceMin": 200,
    "inferredPriceMax": 500
  }
}
```

请求要求：

- `text`
- `imageIds`
- `selectedOptionIds`
- `profile`（可选，前端个性化推荐画像）

`text`、`imageIds`、`selectedOptionIds` 三者至少有一个有效内容。

### replyType

| replyType | 说明 |
|----------|------|
| clarification | 需要用户补充偏好 |
| recognition | 旧版图片识别结果与追问 |
| product_recommendation | 商品分组与动态建议 |

### cardType

| cardType | 说明 |
|----------|------|
| clarification | 动态建议卡 |
| recognition | 旧版图片识别结果卡 |
| product_group_list | 同款商品分组卡，当前主商品卡 |

### 动态建议卡的 options

依赖识别 category（运动鞋 / 耳机 / 吹风机 / 背包 / 智能手表）动态生成：

| optionId | 说明 |
|----------|------|
| lowest_price | 查看同款低价 |
| official_store | 只看官方旗舰店 |
| fast_delivery | 配送更快 |
| style_similar | 相似风格推荐（运动鞋） |
| filter_color | 筛选颜色/品牌/尺码（运动鞋） |
| noise_cancel | 降噪款优先（耳机） |
| high_rating | 好评率优先（耳机） |
| high_power | 大功率优先（吹风机） |
| portable | 便携折叠款（吹风机） |
| large_capacity | 大容量款（背包） |
| business | 商务款（背包） |
| long_battery | 长续航款（智能手表） |
| sports | 运动款（智能手表） |
| filter_same_brand | 只看 {品牌}（识别到品牌时） |
| price_history | 查看历史价格走势 |

### 商品推荐响应示例

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "replyId": "uuid",
    "replyType": "product_recommendation",
    "text": "找到 3 组匹配商品，你更看重哪一点？",
    "cards": [
      {
        "cardType": "product_group_list",
        "title": "匹配商品",
        "filterSummary": ["品类：耳机", "预算≤300元", "颜色：黑色", "品牌：索尼"],
        "groups": [
          {
            "groupId": "索尼|耳机",
            "displayTitle": "Sony WH-1000XM5 头戴式降噪耳机",
            "category": "耳机",
            "brand": "索尼",
            "bestPrice": 299.0,
            "platformCount": 2,
            "matchLevel": "strict",
            "priceRange": {"min": 299.0, "max": 329.0},
            "thumbnailUrl": "https://example.com/headphone.jpg",
            "platforms": [
              {
                "productId": "headphone-001_京东",
                "platform": "京东-mock",
                "title": "Sony WH-1000XM5 头戴式降噪耳机",
                "price": 299.0,
                "originalPrice": 399.0,
                "shopName": "索尼自营旗舰店",
                "imageUrl": "https://example.com/headphone.jpg",
                "rating": 4.9,
                "sales": 23000,
                "tags": ["京东物流", "正品保障"],
                "score": 7.5,
                "brand": "索尼",
                "priceHistory": [399.0, 379.0, 349.0, 319.0, 299.0],
                "matchedPreferences": ["low_price", "high_rating", "budget_match"],
                "specs": [
                  {"label": "品类", "value": "耳机"},
                  {"label": "店铺", "value": "索尼自营旗舰店"}
                ]
              }
            ]
          }
        ],
        "emptyReason": null
      },
      {
        "cardType": "clarification",
        "title": "你更看重哪一点？",
        "options": [
          {"optionId": "lowest_price", "label": "查看同款低价"},
          {"optionId": "official_store", "label": "只看官方旗舰店"},
          {"optionId": "fast_delivery", "label": "配送更快"},
          {"optionId": "price_history", "label": "查看历史价格走势"}
        ]
      }
    ]
  }
}
```

`product_group_list.filterSummary` 为当前生效筛选条件摘要。前端用于展示 `当前条件：...`，字段缺失或为空数组时不展示该行。

新增字段：

- 商品分组卡：`groups`、`priceRange`、`platformCount`、`matchLevel`、`emptyReason`
- 平台报价：`brand`、`priceHistory`、`matchedPreferences`、`specs`
- 图片识别元数据：图片识别路径下 `product_group_list` 可携带 `imageId`、`category`、`brand`、`model`、`keywords`、`attributes`、`confidence`、`aiProvider`、`fallbackUsed`、`recognitionId`

## 图片识别

```text
POST /api/recognition
```

请求体：

```json
{
  "imageId": "uuid"
}
```

返回结构化识别结果：

- `recognitionId`
- `imageId`
- `category`
- `brand`
- `model`
- `keywords`
- `attributes`
- `confidence`
- `aiProvider`
- `fallbackUsed`
- `explanation`

## 识别结果修正

```text
PATCH /api/recognition/{recognitionId}/attributes
```

请求体：

```json
{
  "category": "耳机",
  "brand": "用户修正品牌",
  "model": "用户修正型号",
  "attributes": {
    "color": "黑色"
  }
}
```

## 后续计划 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/search-tasks` | 独立商品搜索任务 |
| POST | `/api/comparisons` | 独立比价任务 |
| POST | `/api/recommendations` | 完整 Agent 推荐任务 |
| GET | `/api/ecommerce/status` | 固定 Mock 商品源状态 |
