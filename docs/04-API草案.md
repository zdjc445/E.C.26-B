# API 草案

## 概述

服务端提供 RESTful JSON API。基础路径为 `http://localhost:8080`。

当前阶段围绕聊天式 Mock Agent 闭环实现以下接口：

```text
GET /api/health
POST /api/images/upload
POST /api/chat/sessions
POST /api/chat/sessions/{sessionId}/messages
```

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

响应示例：

```json
{
  "status": "ok",
  "app": "shopping-agent",
  "stage": "skeleton",
  "aiProvider": "mock",
  "timestamp": "2026-06-06T12:00:00+08:00"
}
```

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

约束：

- 文件保存到项目根目录 `uploads/`
- `imageId` 使用 UUID
- 上传元数据当前使用内存结构
- 空文件或缺失文件返回错误响应

## 创建聊天会话

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

首轮普通消息响应：

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
          {
            "optionId": "lowest_price",
            "label": "价格最低"
          },
          {
            "optionId": "official_store",
            "label": "官方店铺"
          },
          {
            "optionId": "fast_delivery",
            "label": "配送更快"
          }
        ]
      }
    ]
  }
}
```

点击追问选项后的响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "replyId": "uuid",
    "replyType": "recommendation",
    "text": "根据你的偏好，我给出以下推荐。",
    "cards": [
      {
        "cardType": "recommendation",
        "title": "推荐购买",
        "productName": "Mock 商品",
        "platform": "Mock 平台-mock",
        "price": 199.00,
        "reason": "符合你选择的偏好，适合作为当前演示推荐。"
      }
    ]
  }
}
```

## 后续迭代计划 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录，返回 access token |
| POST | `/api/recognition` | 真实图片识别 |
| POST | `/api/search-tasks` | 创建商品搜索任务 |
| GET | `/api/search-tasks/{id}` | 查询搜索结果 |
| POST | `/api/comparisons` | 对选定商品发起比价 |
| POST | `/api/recommendations` | 请求完整 Agent 推荐 |
| GET | `/api/ecommerce/status` | 查询电商 API 配置状态 |

## 当前阶段状态

当前阶段 API 服务于聊天式 Mock Agent 闭环。真实 AI、真实电商 API、认证和数据库能力均为后续迭代。
