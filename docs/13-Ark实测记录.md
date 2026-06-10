# Ark 实测记录

## 测试目标

本记录用于说明当前项目在 `AI_PROVIDER=ark` 下的真实 AI 链路表现，重点覆盖图片识别、识别结果进入商品推荐、多轮追加筛选、失败回退和已修复问题。

当前商品数据默认来自 `mock-data/mock-data.json`，由 `CompositeProductSourceProvider` 生成四平台 Mock 报价。Ark 只参与图片识别、购物意图结构化解析、查询拆解和推荐解释改写。

## 测试环境与配置

- 后端：Spring Boot，端口 `8080`
- Flutter：Android 真机 USB 调试
- 真机访问后端：`adb reverse tcp:8080 tcp:8080`
- API Base URL：`http://127.0.0.1:8080`
- `AI_PROVIDER=ark`
- `ARK_API_KEY`：本地环境变量配置，不写入仓库
- `ARK_ENDPOINT_ID`：本地环境变量配置，不写入仓库
- `ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3`
- `AUTH_ENABLED=false`
- `ecommerceProvider=mock-data`
- `chatHistoryStore=memory`
- `voiceProvider=mock`

健康检查期望：

```text
GET /api/health
```

关键字段：

```text
status=ok
aiProvider=ark
ecommerceProvider=mock-data
chatHistoryStore=memory
authEnabled=false
```

## 实测用例记录

| 用例 | 操作 | 期望结果 |
|------|------|----------|
| 健康检查 | 启动后端后访问 `/api/health` | 返回 `status=ok`，`aiProvider=ark`，商品源为 `mock-data` |
| 图片上传 | App 选择或拍摄商品图 | `/api/images/upload` 成功返回 `imageId` |
| Ark 图片识别 | 上传头戴式耳机图片后发送 | 返回 `recognition` 卡片，`aiProvider=ark`，`fallbackUsed=false` |
| 耳机细分品类归一 | Ark 返回 `头戴式蓝牙耳机` 或类似细分词 | 后端通过 taxonomy 归一到标准品类 `耳机` |
| 识别后追加筛选 | 在同一会话输入 `只看300以内的黑色款` | 商品列表继承识别品类 `耳机`，叠加预算和颜色条件 |
| Ark 回退 | 移除 Ark 配置或使用无效配置后重试 | 识别链路回退 Mock，返回稳定卡片并携带回退提示 |

## 已修复问题

### `Invalid base64 image_url`

实测上传头戴式耳机图片时，Ark 曾返回：

```text
Invalid base64 image_url
```

原因是上传文件的声明类型可能是 `application/octet-stream`，拼接 `data:` URL 后不符合 Ark 对图片 MIME 类型的要求。

修复方式：

- `ArkRecognitionProvider.normalizeContentType()` 优先读取文件头 magic bytes。
- JPEG、PNG、WebP 会归一为合法图片类型。
- 文件头无法识别时，仅接受 `image/jpeg`、`image/png`、`image/webp`。
- 仍无法判断时默认使用 `image/jpeg`。

### 细分品类导致推荐错误

实测时 Ark 可能返回 `头戴式蓝牙耳机` 这类细分品类。旧逻辑只识别标准品类，无法命中后会落到默认品类，进而推荐运动鞋。

修复方式：

- 新增 `mock-data/category-taxonomy.json` 维护标准品类、别名和属性 schema。
- `CategoryResolver` 在文本解析、Ark 识别结果、多轮上下文合并和动态建议生成前统一归一。
- `头戴式蓝牙耳机`、`真无线蓝牙耳机` 等词会归一为 `耳机`。

## 当前边界

- 商品结果使用本地 `mock-data` 生成 Mock 报价，不调用京东、淘宝、天猫、拼多多真实接口。
- 商品卡 `去看看` 只展示平台跳转说明，不打开真实电商页面。
- 收藏使用现有 demo 用户和内存/当前配置的收藏仓库，未做跨设备账号体系验收。
- Ark 失败不会中断演示，会通过 fallback 返回 Mock 或规则结果。
- 本文档不记录密钥，不提交临时截图。
