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
  "selectedOptionIds": ["lowest_price"]
}
```

请求要求：

- `text`
- `imageIds`
- `selectedOptionIds`

三者至少有一个有效内容。

### replyType

| replyType | 说明 |
|----------|------|
| clarification | 需要用户补充偏好 |
| recognition | 图片识别结果与追问 |
| product_recommendation | 商品列表、比价与推荐 |

### cardType

| cardType | 说明 |
|----------|------|
| clarification | 追问选项卡 |
| recognition | 图片识别结果卡 |
| product_list | 多平台商品列表卡 |
| comparison | 平台比价卡 |
| recommendation | 推荐购买卡 |

### 追问响应示例

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "replyId": "uuid",
    "replyType": "clarification",
    "text": "我已经收到你的需求。你更看重哪一点？",
    "cards": [
      {
        "cardType": "clarification",
        "title": "你更看重哪一点？",
        "options": [
          {"optionId": "lowest_price", "label": "价格最低"},
          {"optionId": "official_store", "label": "官方店铺"},
          {"optionId": "fast_delivery", "label": "配送更快"}
        ]
      }
    ]
  }
}
```

### 商品推荐响应示例

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "replyId": "uuid",
    "replyType": "product_recommendation",
    "text": "我按你的偏好整理了几个平台的选择。",
    "cards": [
      {
        "cardType": "product_list",
        "title": "多平台商品结果",
        "products": []
      },
      {
        "cardType": "comparison",
        "title": "平台比价",
        "platformStats": {}
      },
      {
        "cardType": "recommendation",
        "title": "推荐购买",
        "productName": "Mock 商品",
        "platform": "京东-mock",
        "price": 199.0,
        "reason": "价格、店铺和匹配度综合更适合当前需求。"
      }
    ]
  }
}
```

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
| GET | `/api/ecommerce/status` | 真实电商 API 配置状态 |
