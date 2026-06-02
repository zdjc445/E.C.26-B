# API 接口设计

## 设计目标

本文档定义智能识物比价购物 AI APP 助手的后端 API 契约，用于支持前后端并行开发。

接口设计遵循以下原则：

- 职责清晰：图片、识别、搜索、比价、推荐、收藏分别由独立接口负责
- 可扩展：MVP 使用 mock 商品数据，接口保留后续接入官方 API 或授权样例数据适配器的字段
- 可追溯：搜索、比价和 Agent 推荐都通过 `searchTaskId` 串联
- 数据可信：前端不直接传完整商品价格数据，后端根据 ID 从可信数据源读取
- 用户隔离：用户私有数据全部从登录态解析当前用户，不允许请求体传入 `userId`

## 通用规范

### Base URL

```text
/api
```

### 鉴权规则

除注册、登录、刷新 Token、退出登录接口外，其他接口默认需要登录。

业务接口请求头：

```http
Authorization: Bearer <accessToken>
```

后端必须从 access token 中解析当前用户，不能依赖前端传入用户 ID。

登录态约定：

- access token 用于访问业务接口，建议有效期 2 小时
- refresh token 用于换取新的 access token，建议有效期 14 天
- refresh token 只在服务端保存哈希，退出登录时作废
- 密码只允许传输到注册和登录接口，任何响应都不能返回密码或密码哈希

### 响应结构

所有接口统一返回：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

失败响应：

```json
{
  "code": 40102,
  "message": "access token expired",
  "data": null
}
```

### 分页结构

列表接口统一使用查询参数：

```http
?page=1&pageSize=20
```

列表响应统一为：

```json
{
  "items": [],
  "page": 1,
  "pageSize": 20,
  "total": 0
}
```

### 字段约定

| 类型 | 约定 |
| --- | --- |
| JSON 字段 | 小驼峰，例如 `productId`、`platformProductId` |
| ID | 数字类型，对齐数据库 `bigint` |
| 金额 | `{ "amount": "199.00", "currency": "CNY" }` |
| 时间 | ISO 8601 字符串，例如 `2026-05-20T18:00:00+08:00` |
| 平台编码 | `jd`、`taobao`、`pdd`、`tmall`、`other` |
| 数据来源 | `mock`、`official_api`、`sample_dataset` |
| 排序方式 | `comprehensive`、`price_asc`、`sales_desc`、`rating_desc` |

### 建议卡片结构

识别结果和搜索任务可以返回 `suggestionCards`，用于驱动前端下一步操作：

```json
{
  "cardId": "low-price",
  "type": "filter",
  "title": "查看同款低价",
  "payload": {
    "sortBy": "price_asc"
  },
  "priority": 10
}
```

`type` 可取 `filter`、`sort`、`price_history`、`similar`、`official`。前端点击后按 `payload` 创建搜索或调用追加筛选接口。

## 错误码

| code | 场景 |
| --- | --- |
| 0 | 成功 |
| 40000 | 请求参数错误 |
| 40101 | 未登录或缺少 access token |
| 40102 | access token 无效或过期 |
| 40103 | refresh token 无效或过期 |
| 40301 | 当前用户无权访问该资源 |
| 40401 | 图片不存在 |
| 40402 | 识别记录不存在 |
| 40403 | 搜索任务不存在 |
| 40404 | 商品不存在 |
| 40405 | 平台商品不存在 |
| 40406 | 收藏记录不存在 |
| 40407 | 价格提醒不存在 |
| 40408 | 推荐记录不存在 |
| 40901 | 用户名已存在 |
| 40902 | 商品已收藏 |
| 40903 | 价格提醒已存在 |
| 42201 | 用户名或密码格式不合法 |
| 42202 | 图片格式或大小不合法 |
| 42203 | 平台参数不合法 |
| 50001 | 图片上传失败 |
| 50002 | 商品识别失败 |
| 50003 | 商品搜索失败 |
| 50004 | 比价失败 |
| 50005 | Agent 推荐失败 |

用户访问不属于自己的图片、搜索任务、收藏或价格提醒时，默认返回对应 `404xx` 错误，避免暴露其他用户资源是否存在。

## 用户认证

### 用户注册

```http
POST /api/auth/register
```

请求：

```json
{
  "username": "alice",
  "password": "password123",
  "nickname": "Alice"
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "jwt_access_token",
    "refreshToken": "refresh_token",
    "expiresIn": 7200,
    "user": {
      "id": 1,
      "username": "alice",
      "nickname": "Alice",
      "avatarUrl": null,
      "status": "active"
    }
  }
}
```

可能错误码：`40901`、`42201`。

### 用户登录

```http
POST /api/auth/login
```

请求：

```json
{
  "username": "alice",
  "password": "password123"
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "jwt_access_token",
    "refreshToken": "refresh_token",
    "expiresIn": 7200,
    "user": {
      "id": 1,
      "username": "alice",
      "nickname": "Alice",
      "avatarUrl": null,
      "status": "active"
    }
  }
}
```

可能错误码：`40101`、`42201`。

### 刷新 Token

```http
POST /api/auth/refresh
```

请求：

```json
{
  "refreshToken": "refresh_token"
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "accessToken": "new_jwt_access_token",
    "refreshToken": "new_refresh_token",
    "expiresIn": 7200
  }
}
```

说明：

- refresh token 过期、被撤销或不存在时返回 `40103`
- 刷新成功后轮换 refresh token，旧 refresh token 立即失效

可能错误码：`40103`。

### 退出登录

```http
POST /api/auth/logout
```

请求：

```json
{
  "refreshToken": "refresh_token"
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": null
}
```

说明：

- 后端根据 refresh token 哈希查找并撤销会话
- 客户端收到成功响应后清理本地 token

可能错误码：`40103`。

### 当前用户

```http
GET /api/auth/me
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "username": "alice",
    "nickname": "Alice",
    "avatarUrl": null,
    "status": "active"
  }
}
```

可能错误码：`40101`、`40102`。

## 图片接口

### 上传图片

```http
POST /api/images
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是 | 商品图片 |
| scene | string | 否 | 图片用途，默认 `recognition` |

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "imageId": 1001,
    "imageUrl": "https://cdn.example.com/images/1001.jpg",
    "contentType": "image/jpeg",
    "size": 245760,
    "createdAt": "2026-05-20T18:00:00+08:00"
  }
}
```

可能错误码：`40101`、`40102`、`42202`、`50001`。

### 查询图片列表

```http
GET /api/images?page=1&pageSize=20
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "imageId": 1001,
        "imageUrl": "https://cdn.example.com/images/1001.jpg",
        "contentType": "image/jpeg",
        "createdAt": "2026-05-20T18:00:00+08:00"
      }
    ],
    "page": 1,
    "pageSize": 20,
    "total": 1
  }
}
```

可能错误码：`40101`、`40102`。

### 删除图片

```http
DELETE /api/images/{imageId}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": null
}
```

说明：

- 只能删除当前用户上传的图片
- 如果图片已被搜索任务引用，MVP 阶段只删除用户侧可见记录，不强制删除历史任务快照

可能错误码：`40101`、`40102`、`40401`。

## 商品识别接口

### 创建识别任务

```http
POST /api/recognitions
```

请求：

```json
{
  "imageId": 1001
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "recognitionId": 2001,
    "imageId": 1001,
    "category": "吹风机",
    "brand": "未知",
    "model": null,
    "keywords": ["吹风机", "低噪音", "宿舍"],
    "attributes": {
      "color": "白色",
      "shape": "手持式"
    },
    "confidence": 0.86,
    "aiProvider": "mock",
    "fallbackUsed": false,
    "explanation": "使用 mock/sample_dataset 识别样例生成结构化识物结果。",
    "notices": [],
    "status": "succeeded",
    "createdAt": "2026-05-20T18:01:00+08:00"
  }
}
```

说明：

- `confidence < 0.6` 时前端应提示用户补充关键词或重新上传图片
- 识别结果归属于当前用户，不允许跨用户读取

可能错误码：`40101`、`40102`、`40401`、`50002`。

### 查询识别结果

```http
GET /api/recognitions/{recognitionId}
```

响应字段与创建识别任务一致。

可能错误码：`40101`、`40102`、`40402`。

### 修正识别属性

```http
PATCH /api/recognitions/{recognitionId}/attributes
```

请求：

```json
{
  "brand": "LumaCare",
  "attributes": {
    "color": "深蓝色",
    "shape": "手持式"
  }
}
```

响应字段与查询识别结果一致。后端只允许修正当前用户自己的识别记录，修正后会重新生成建议卡片。

可能错误码：`40101`、`40102`、`40402`、`40000`。

## 搜索任务接口

### 创建搜索任务

```http
POST /api/search-tasks
```

请求：

```json
{
  "recognitionId": 2001,
  "query": "500 元以内，适合宿舍用，噪音小一点",
  "platforms": ["jd", "taobao", "pdd"],
  "sourceType": "mock",
  "filters": {
    "minPrice": {
      "amount": "0.00",
      "currency": "CNY"
    },
    "maxPrice": {
      "amount": "500.00",
      "currency": "CNY"
    },
    "brandWhitelist": [],
    "brandBlacklist": ["杂牌"],
    "sortBy": "comprehensive"
  }
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "searchTaskId": 3001,
    "status": "succeeded",
    "sourceType": "mock",
    "items": [
      {
        "platformProductId": 5001,
        "productId": 4001,
        "platform": "jd",
        "title": "某品牌低噪音宿舍吹风机",
        "imageUrl": "https://cdn.example.com/products/5001.jpg",
        "price": {
          "amount": "199.00",
          "currency": "CNY"
        },
        "originalPrice": {
          "amount": "259.00",
          "currency": "CNY"
        },
        "url": "https://example.com/item/5001",
        "matchScore": 0.91,
        "matchReasons": ["同类目：吹风机", "满足价格上限 ¥500.00", "官方旗舰店渠道"],
        "sourceType": "mock",
        "updatedAt": "2026-05-20T18:02:00+08:00"
      }
    ],
    "createdAt": "2026-05-20T18:02:00+08:00"
  }
}
```

说明：

- `recognitionId` 和 `query` 至少提供一个
- MVP 阶段 `sourceType` 默认使用 `mock`
- 后续接入官方 API 或授权样例数据时，保持响应结构不变，只调整数据适配层

可能错误码：`40101`、`40102`、`40402`、`42203`、`50003`。

### 查询搜索任务详情

```http
GET /api/search-tasks/{searchTaskId}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "searchTaskId": 3001,
    "status": "succeeded",
    "query": "500 元以内，适合宿舍用，噪音小一点",
    "sourceType": "mock",
    "recognition": {
      "recognitionId": 2001,
      "category": "吹风机",
      "brand": "未知",
      "keywords": ["吹风机", "低噪音", "宿舍"],
      "confidence": 0.86
    },
    "items": [
      {
        "platformProductId": 5001,
        "productId": 4001,
        "platform": "jd",
        "title": "某品牌低噪音宿舍吹风机",
        "price": {
          "amount": "199.00",
          "currency": "CNY"
        },
        "matchScore": 0.91,
        "matchReasons": ["同类目：吹风机", "官方旗舰店渠道"],
        "sourceType": "mock"
      }
    ],
    "createdAt": "2026-05-20T18:02:00+08:00"
  }
}
```

可能错误码：`40101`、`40102`、`40403`。

### 查询搜索历史

```http
GET /api/search-tasks?page=1&pageSize=20
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "searchTaskId": 3001,
        "query": "500 元以内，适合宿舍用，噪音小一点",
        "status": "succeeded",
        "sourceType": "mock",
        "resultCount": 12,
        "createdAt": "2026-05-20T18:02:00+08:00"
      }
    ],
    "page": 1,
    "pageSize": 20,
    "total": 1
  }
}
```

可能错误码：`40101`、`40102`。

### 自然语言追加筛选

```http
POST /api/search-tasks/{searchTaskId}/refine
```

请求：

```json
{
  "text": "1000 元以内的黑色款，要评价 4.8 分以上，只看官方",
  "sortBy": "rating_desc"
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "searchTaskId": 3001,
    "text": "1000 元以内的黑色款，要评价 4.8 分以上，只看官方",
    "filters": {
      "maxPrice": "1000.00",
      "color": "黑色",
      "minRating": 4.8,
      "officialOnly": true,
      "sortBy": "rating_desc"
    },
    "items": [],
    "suggestionCards": [],
    "platformStats": [],
    "aiProvider": "rule",
    "fallbackUsed": false,
    "notices": []
  }
}
```

说明：

- 默认使用规则解析兜底；配置 Ark 后优先由 LLM 输出结构化 filters，并对字段做白名单校验。
- 解析失败时保留原搜索条件并返回空 `filters`，不让主链路中断。
- `items` 使用增强商品卡片字段，包括 `tags`、`salesVolume`、`rating`、`isOfficial`、`isSelfOperated`、`matchReasons`。

可能错误码：`40101`、`40102`、`40403`、`40000`。

## 商品接口

### 查询标准商品详情

```http
GET /api/products/{productId}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "productId": 4001,
    "name": "低噪音宿舍吹风机",
    "category": "吹风机",
    "brand": "某品牌",
    "model": "HD-001",
    "attributes": {
      "power": "1600W",
      "noiseLevel": "低噪音"
    },
    "createdAt": "2026-05-20T18:02:00+08:00"
  }
}
```

可能错误码：`40101`、`40102`、`40404`。

### 查询平台商品详情

```http
GET /api/platform-products/{platformProductId}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "platformProductId": 5001,
    "productId": 4001,
    "platform": "jd",
    "title": "某品牌低噪音宿舍吹风机",
    "imageUrl": "https://cdn.example.com/products/5001.jpg",
    "price": {
      "amount": "199.00",
      "currency": "CNY"
    },
    "originalPrice": {
      "amount": "259.00",
      "currency": "CNY"
    },
    "url": "https://example.com/item/5001",
    "shopName": "某品牌官方旗舰店",
    "sourceType": "mock",
    "updatedAt": "2026-05-20T18:02:00+08:00"
  }
}
```

可能错误码：`40101`、`40102`、`40405`。

### 查询平台商品历史价格

```http
GET /api/platform-products/{platformProductId}/price-history?days=90
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "platformProductId": 5001,
    "days": 90,
    "currentPrice": {
      "amount": "199.00",
      "currency": "CNY"
    },
    "lowestPrice": {
      "amount": "189.00",
      "currency": "CNY"
    },
    "highestPrice": {
      "amount": "259.00",
      "currency": "CNY"
    },
    "trend": "low",
    "points": [
      {
        "recordedAt": "2026-05-01T00:00:00+08:00",
        "price": {
          "amount": "229.00",
          "currency": "CNY"
        }
      },
      {
        "recordedAt": "2026-05-20T00:00:00+08:00",
        "price": {
          "amount": "199.00",
          "currency": "CNY"
        }
      }
    ]
  }
}
```

说明：

- `trend` 可取 `low`、`normal`、`high`、`unknown`
- 没有历史价格时返回空 `points`，`trend` 为 `unknown`

可能错误码：`40101`、`40102`、`40405`。

### 查询评价摘要

```http
GET /api/platform-products/{platformProductId}/review-summary
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "platformProductId": 5001,
    "rating": 4.7,
    "reviewCount": 1280,
    "positiveTags": ["风力大", "噪音低", "适合宿舍"],
    "riskTags": ["物流较慢"],
    "riskScore": 0.18,
    "summary": "整体评价较好，主要风险集中在物流时效。"
  }
}
```

可能错误码：`40101`、`40102`、`40405`。

## 比价接口

### 创建比价

```http
POST /api/comparisons
```

请求：

```json
{
  "searchTaskId": 3001,
  "platformProductIds": [5001, 5002, 5003]
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "comparisonId": 6001,
    "searchTaskId": 3001,
    "lowestPlatformProductId": 5001,
    "lowestPrice": {
      "amount": "199.00",
      "currency": "CNY"
    },
    "platformStats": [
      {
        "platform": "jd",
        "lowestPrice": {
          "amount": "199.00",
          "currency": "CNY"
        },
        "averagePrice": {
          "amount": "249.00",
          "currency": "CNY"
        },
        "productCount": 2
      }
    ],
    "items": [
      {
        "platformProductId": 5001,
        "platform": "jd",
        "title": "某品牌低噪音宿舍吹风机",
        "price": {
          "amount": "199.00",
          "currency": "CNY"
        },
        "matchScore": 0.91,
        "matchReasons": ["同类目：吹风机", "官方旗舰店渠道"],
        "sourceType": "mock",
        "updatedAt": "2026-05-20T18:02:00+08:00"
      }
    ],
    "createdAt": "2026-05-20T18:03:00+08:00"
  }
}
```

说明：

- `platformProductIds` 必须来自当前用户可访问的 `searchTaskId` 搜索结果
- 候选为空时返回 `40000`

可能错误码：`40101`、`40102`、`40403`、`40405`、`50004`。

## Agent 推荐接口

### 创建购物推荐

```http
POST /api/agent/recommendations
```

请求：

```json
{
  "searchTaskId": 3001,
  "userQuery": "500 元以内，适合宿舍用，噪音小一点，售后靠谱",
  "candidateIds": [5001, 5002, 5003]
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
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
    "decisionScore": 86,
    "decisionSignals": [
      {
        "key": "match",
        "label": "意图匹配",
        "score": 91,
        "explanation": "标题、类目、属性和自然语言筛选的综合匹配度。"
      },
      {
        "key": "price",
        "label": "价格位置",
        "score": 84,
        "explanation": "当前价相对 90 天历史低点/高点的位置，越接近低点越高。"
      }
    ],
    "decisionTrace": [
      {
        "key": "intent",
        "label": "识别意图",
        "status": "done",
        "confidence": 92,
        "observation": "识别为 吹风机，品牌 LumaCare，模型 HD-2026。"
      },
      {
        "key": "market",
        "label": "价格时机",
        "status": "done",
        "confidence": 84,
        "observation": "当前价 199.00 CNY，90 天低点 189.00 CNY，趋势 接近低位。"
      }
    ],
    "candidateAnalyses": [
      {
        "platformProductId": 5001,
        "platform": "jd",
        "title": "某品牌低噪音宿舍吹风机",
        "price": {
          "amount": "199.00",
          "currency": "CNY"
        },
        "rank": 1,
        "decisionScore": 86,
        "verdict": "winner",
        "strengths": ["意图匹配高", "接近 90 天价格低位"],
        "weaknesses": ["暂无明显短板"]
      }
    ],
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
      },
      {
        "type": "match",
        "platformProductId": 5001,
        "content": "匹配分 0.91"
      },
      {
        "type": "review",
        "platformProductId": 5001,
        "content": "评价风险分 0.18"
      }
    ],
    "createdAt": "2026-05-20T18:04:00+08:00"
  }
}
```

说明：

- `candidateIds` 是平台商品 ID，只能引用当前搜索任务内的候选商品
- Agent 必须从后端数据库或工具结果读取商品、价格、历史价格和评价摘要
- Agent 输出必须包含 `evidence`，不能只返回自然语言结论
- `decisionScore` 是后端基于 `decisionSignals` 加权计算的 0-100 决策分，前端只负责展示，不自行编造
- `decisionSignals` 固定覆盖 `match`、`price`、`reputation`、`channel`、`risk` 五类信号，便于答辩解释推荐依据
- `decisionTrace` 固定覆盖 `intent`、`constraints`、`retrieval`、`market`、`risk`、`decision` 六步，展示 Agent 从识别、筛选、召回到最终建议的服务端决策轨迹
- `candidateAnalyses` 是后端对每个候选商品按同一套决策分排序后生成的胜因/败因矩阵，`verdict` 可取 `winner`、`runner_up`、`watch`、`rejected`
- `suggestion` 可取 `buy`、`wait`、`avoid`、`compare`

可能错误码：`40101`、`40102`、`40403`、`40405`、`50005`。

### 查询推荐记录

```http
GET /api/agent/recommendations/{recommendationId}
```

响应字段与创建购物推荐一致。

可能错误码：`40101`、`40102`、`40408`。

### 导出推荐证据报告

```http
GET /api/agent/recommendations/{recommendationId}/report
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "recommendationId": 7001,
    "searchTaskId": 3001,
    "title": "购物决策证据报告 #7001",
    "summary": "建议购买：Auralis ANC-20 京东自营降噪耳机黑色，决策分 91，来源搜索任务 3001，候选 3 个。",
    "markdown": "# 购物决策证据报告 #7001\n\n> 建议购买：...\n\n## 五类决策信号\n...",
    "generatedAt": "2026-05-31T23:52:00+08:00"
  }
}
```

说明：

- 报告内容由后端根据已保存推荐记录、搜索任务、决策信号、轨迹、候选矩阵和 evidence 生成
- `markdown` 适合复制到答辩材料、评审说明或问题复盘中
- 报告不重新调用 LLM，不新增商品事实，只导出服务端已有证据

可能错误码：`40101`、`40102`、`40408`。

## 收藏接口

### 创建收藏

```http
POST /api/favorites
```

请求：

```json
{
  "platformProductId": 5001,
  "note": "等降价到 180 元以内"
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "favoriteId": 8001,
    "platformProductId": 5001,
    "note": "等降价到 180 元以内",
    "createdAt": "2026-05-20T18:05:00+08:00"
  }
}
```

说明：

- 收藏数据只归属于当前登录用户
- 重复收藏返回 `40902`

可能错误码：`40101`、`40102`、`40405`、`40902`。

### 查询收藏列表

```http
GET /api/favorites?page=1&pageSize=20
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "favoriteId": 8001,
        "platformProductId": 5001,
        "platform": "jd",
        "title": "某品牌低噪音宿舍吹风机",
        "price": {
          "amount": "199.00",
          "currency": "CNY"
        },
        "note": "等降价到 180 元以内",
        "createdAt": "2026-05-20T18:05:00+08:00"
      }
    ],
    "page": 1,
    "pageSize": 20,
    "total": 1
  }
}
```

可能错误码：`40101`、`40102`。

### 删除收藏

```http
DELETE /api/favorites/{favoriteId}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": null
}
```

可能错误码：`40101`、`40102`、`40406`。

## 价格提醒接口

价格提醒已作为用户资产沉淀能力接入 Web/PWA 演示端和后端接口。当前实现支持创建、查询和启停目标价提醒；长周期调度通知仍作为后续扩展。

### 创建价格提醒

```http
POST /api/price-alerts
```

请求：

```json
{
  "platformProductId": 5001,
  "targetPrice": {
    "amount": "180.00",
    "currency": "CNY"
  },
  "enabled": true
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "priceAlertId": 9001,
    "platformProductId": 5001,
    "targetPrice": {
      "amount": "180.00",
      "currency": "CNY"
    },
    "enabled": true,
    "createdAt": "2026-05-20T18:06:00+08:00"
  }
}
```

可能错误码：`40101`、`40102`、`40405`、`40903`。

### 查询价格提醒列表

```http
GET /api/price-alerts?page=1&pageSize=20
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "priceAlertId": 9001,
        "platformProductId": 5001,
        "title": "某品牌低噪音宿舍吹风机",
        "currentPrice": {
          "amount": "199.00",
          "currency": "CNY"
        },
        "targetPrice": {
          "amount": "180.00",
          "currency": "CNY"
        },
        "enabled": true,
        "createdAt": "2026-05-20T18:06:00+08:00"
      }
    ],
    "page": 1,
    "pageSize": 20,
    "total": 1
  }
}
```

可能错误码：`40101`、`40102`。

### 更新价格提醒

```http
PATCH /api/price-alerts/{priceAlertId}
```

请求：

```json
{
  "targetPrice": {
    "amount": "175.00",
    "currency": "CNY"
  },
  "enabled": false
}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "priceAlertId": 9001,
    "targetPrice": {
      "amount": "175.00",
      "currency": "CNY"
    },
    "enabled": false,
    "updatedAt": "2026-05-20T18:07:00+08:00"
  }
}
```

可能错误码：`40101`、`40102`、`40407`。

### 删除价格提醒

```http
DELETE /api/price-alerts/{priceAlertId}
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": null
}
```

可能错误码：`40101`、`40102`、`40407`。

## 数据源策略

默认使用 `mock` 数据源实现稳定闭环：

```text
上传图片
  -> 创建识别任务
  -> 创建搜索任务
  -> 返回 mock 平台商品候选
  -> 创建比价
  -> Agent 基于后端可信候选数据生成推荐
```

已增加 `official_api` 适配器，支持通过服务端配置调用拼多多/京东官方开放平台 API；也可继续保留 `sample_dataset` 适配器。前端 API 契约保持不变：

- `sourceType` 标记数据来源
- 平台商品统一归一化为 `platformProduct` 结构
- 价格历史统一写入 `price_records`
- Agent 只读取后端已归一化的数据，不直接相信前端传入的价格
- 真实平台密钥和签名逻辑只在服务端，前端不保存 `appKey`、`secret` 或 `accessToken`

### 电商 API 状态

```http
GET /api/ecommerce/status
```

响应示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "enabled": true,
    "hasConfiguredClient": true,
    "providers": [
      {
        "platform": "拼多多",
        "enabled": true,
        "configured": true,
        "requiredConfig": ["ECOMMERCE_API_ENABLED", "PDD_API_ENABLED", "PDD_CLIENT_ID", "PDD_CLIENT_SECRET"],
        "missingConfig": []
      },
      {
        "platform": "京东",
        "enabled": false,
        "configured": false,
        "requiredConfig": ["ECOMMERCE_API_ENABLED", "JD_API_ENABLED", "JD_APP_KEY", "JD_APP_SECRET"],
        "missingConfig": ["JD_API_ENABLED", "JD_APP_KEY", "JD_APP_SECRET"]
      }
    ]
  }
}
```

该接口只返回配置状态和缺失配置项名称，不返回密钥、Token 或签名参数。

### 电商 API 调用诊断

```http
GET /api/ecommerce/diagnostics?query=吹风机&pageSize=3&platforms=pdd&maxPrice=500.00&withCoupon=true
Authorization: Bearer <accessToken>
```

响应示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "query": "吹风机",
    "checkedAt": "2026-05-24T12:00:00+08:00",
    "providers": [
      {
        "platform": "拼多多",
        "configured": true,
        "success": true,
        "status": "ok",
        "itemCount": 3,
        "durationMs": 420,
        "sampleTitles": ["高速负离子吹风机"],
        "errorCode": "",
        "errorMessage": "",
        "missingConfig": []
      },
      {
        "platform": "京东",
        "configured": false,
        "success": false,
        "status": "not_configured",
        "itemCount": 0,
        "durationMs": 0,
        "sampleTitles": [],
        "errorCode": "",
        "errorMessage": "missing config: JD_API_ENABLED, JD_APP_KEY, JD_APP_SECRET",
        "missingConfig": ["JD_API_ENABLED", "JD_APP_KEY", "JD_APP_SECRET"]
      }
    ]
  }
}
```

`platforms` 可选，支持 `pdd`、`jd`，可重复传参或用逗号分隔。诊断接口也支持 `minPrice`、`maxPrice`、`withCoupon`、`officialOnly`、`selfOperatedOnly` 查询参数，用于验证官方 API 筛选下推。该接口会真实请求已配置的平台 API，建议只在联调或运维检查时使用；响应不包含密钥、Token、签名参数或原始请求体。如果平台用 HTTP 200 返回业务错误，例如权限、签名、应用配置错误，后端会将该平台诊断为 `failed`，并返回平台 `errorCode` 与安全错误摘要。
