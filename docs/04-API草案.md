# API 草案

## 概述

服务端提供 RESTful JSON API。基础路径为 `http://localhost:8080`。

本阶段仅实现 `GET /api/health`。以下为后续迭代的计划 API。

## 当前已实现

### 健康检查

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

## 后续迭代计划 API

### 认证模块

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录，返回 access token |
| POST | `/api/auth/refresh` | 刷新 access token |

### 图片模块

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/images/upload` | 上传商品图片 |
| GET | `/api/images/{id}` | 获取上传的图片 |

### 识别模块

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/recognition` | 对已上传图片发起识别 |
| GET | `/api/recognition/{id}` | 查询识别结果与建议卡片 |

### 搜索模块

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/search-tasks` | 创建商品搜索任务 |
| GET | `/api/search-tasks/{id}` | 查询搜索结果 |

### 比价模块

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/comparisons` | 对选定商品发起比价 |

### 推荐模块

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/recommendations` | 对候选商品请求 Agent 推荐 |

### 电商状态

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ecommerce/status` | 查询电商 API 配置状态 |

## 统一响应格式（计划）

```json
{
  "code": 0,
  "message": "success",
  "data": { }
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

## 认证方案（计划）

- 使用 Bearer Token 鉴权
- 除注册/登录外，所有 API 需携带 `Authorization: Bearer <token>`
- Token 有效期 2 小时，支持 refresh

## 当前阶段状态

除 `GET /api/health` 外，以上所有端点均为设计草案，尚未实现。
