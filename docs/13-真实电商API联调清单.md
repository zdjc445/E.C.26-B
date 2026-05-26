# 真实电商 API 联调清单

本文档用于拿到拼多多/京东开放平台凭证后，按固定步骤验证 `official_api` 数据源是否真正连通。不要把真实密钥写入仓库。

## 1. 配置环境变量

可参考仓库根目录 `.env.example`。至少配置一个平台：

```powershell
$env:ECOMMERCE_API_ENABLED="true"

$env:PDD_API_ENABLED="true"
$env:PDD_CLIENT_ID="<pdd client id>"
$env:PDD_CLIENT_SECRET="<pdd client secret>"
$env:PDD_PID="<optional promotion pid>"
$env:PDD_CUSTOM_PARAMETERS="<optional tracking json>"
```

或：

```powershell
$env:ECOMMERCE_API_ENABLED="true"

$env:JD_API_ENABLED="true"
$env:JD_APP_KEY="<jd app key>"
$env:JD_APP_SECRET="<jd app secret>"
$env:JD_ACCESS_TOKEN="<jd access token if required>"
$env:JD_PARAM_JSON_NAME="360buy_param_json"
$env:JD_SITE_ID="<optional site id>"
$env:JD_POSITION_ID="<optional position id>"
```

也可以把 `.env.example` 复制为仓库根目录 `.env` 后填写真实凭证，live smoke 脚本会自动读取该文件；真实 `.env` 不要提交。
复制模板后必须替换占位值；后端和 smoke 脚本会把 `...`、`<...>`、`your-*`、`replace-*` 等值视为未配置。
`PDD_PID`、`PDD_CUSTOM_PARAMETERS`、`JD_SITE_ID`、`JD_POSITION_ID` 为可选推广位/归因参数，配置后会随官方搜索请求透传，未配置时不会影响普通搜索联调。
拼多多返回缺少 `goods_id` 但包含 `goods_sign` 时，后端会使用 `goods_sign` 生成稳定商品 ID，并把它保留到商品属性和 URL 中。
`JD_PARAM_JSON_NAME` 默认为京东 JOS 公共参数字段 `360buy_param_json`，通常不需要修改；只有对接兼容网关时才建议覆盖。京东响应会兼容 `_response` 与部分平台历史上出现过的 `_responce` 包装字段；价格展示会优先使用 `lowestCouponPrice` / `lowestPrice` 这类到手价字段，并识别 `owner=g` 这类自营标记。

## 2. 启动服务

```powershell
cd backend
mvn -DskipTests clean package
java -jar target/shopping-agent-0.1.0.jar
```

## 3. 检查配置状态

```http
GET http://localhost:8080/api/ecommerce/status
```

验收点：

- `enabled=true`
- 至少一个平台 `configured=true`
- `missingConfig=[]`
- 响应不包含任何密钥值

## 4. 运行按平台诊断

登录后请求：

```http
GET http://localhost:8080/api/ecommerce/diagnostics?query=吹风机&pageSize=3&platforms=pdd&maxPrice=500.00&withCoupon=true&officialOnly=true&sortBy=price_asc
Authorization: Bearer <accessToken>
```

验收点：

- 目标平台 `success=true`
- `itemCount > 0`
- `sampleTitles` 有真实商品标题
- `durationMs > 0`
- 失败时查看 `errorCode` 和 `errorMessage`
- 可选筛选/排序参数：`minPrice`、`maxPrice`、`withCoupon`、`officialOnly`、`selfOperatedOnly`、`sortBy`

## 4.1 官方 API 筛选下推

`POST /api/search-tasks` 使用 `sourceType=official_api` 时，会优先把部分业务筛选转换成平台官方参数，减少无效结果；`GET /api/ecommerce/diagnostics` 也支持同名查询参数，方便联调时直接验证筛选下推：

- 拼多多：`minPrice` / `maxPrice`、`withCoupon`、`officialOnly`、`sortBy=price_asc` / `sales_desc`
- 京东：`minPrice` / `maxPrice`、`withCoupon`、`selfOperatedOnly`、`sortBy=price_asc` / `sales_desc` / `rating_desc`

搜索请求显式指定 `platforms` 时，所有指定官方平台都必须已配置且调用成功；如果其中一个平台失败，后端会返回错误，避免把部分平台结果误当成完整真实接入。
价格筛选支持 `"500.00"` 这样的字符串，也支持 `{ "amount": "500.00", "currency": "CNY" }` 这样的金额对象。平台返回后，后端仍会按统一规则做一次最终过滤。

## 5. 跑 live smoke test

脚本默认读取仓库根目录 `.env`，也可以用 `-EnvFile` 指定其他本地凭证文件。脚本会严格校验平台启用开关，`PDD_API_ENABLED` / `JD_API_ENABLED` 需要设置为 `true`、`1`、`yes` 或 `on`。`-Platforms` 仅支持 `pdd`、`jd`；显式指定多个平台时，每个目标平台的诊断都必须成功。`-SortBy` 仅支持 `comprehensive`、`price_asc`、`sales_desc`、`rating_desc`，默认 `price_asc`。

```powershell
.\scripts\run-live-ecommerce-smoke.ps1 -Query "吹风机" -Platforms "pdd"
```

带筛选下推的拼多多验收：

```powershell
.\scripts\run-live-ecommerce-smoke.ps1 -Query "吹风机" -Platforms "pdd" -MaxPrice "500.00" -WithCoupon -OfficialOnly -SortBy "price_asc"
```

京东单平台：

```powershell
.\scripts\run-live-ecommerce-smoke.ps1 -Query "吹风机" -Platforms "jd"
```

带筛选下推的京东验收：

```powershell
.\scripts\run-live-ecommerce-smoke.ps1 -Query "耳机" -Platforms "jd" -MinPrice "100.00" -MaxPrice "500.00" -WithCoupon -SelfOperatedOnly -SortBy "rating_desc"
```

验收点：

- `LiveOfficialApiSmokeTests` 未跳过
- 诊断接口至少一个目标平台 `success=true`
- 如果 `-Platforms` 指定了一个或多个平台，所有指定平台都必须 `success=true`
- 返回至少 1 个 `sourceType=official_api` 商品
- 商品包含平台、标题、URL 和大于 0 的价格
- 使用筛选/排序参数时，live smoke 会同时把参数传给诊断接口和搜索接口
- 通过后生成 `backend/target/live-ecommerce-smoke-report.json` 脱敏验收报告；可用 `-ReportPath` 或 `ECOMMERCE_LIVE_REPORT_PATH` 指定其他输出位置，相对路径按仓库根目录解析，报告不包含密钥、Token、签名或原始请求参数

## 6. 前端验证

1. 打开 Web 演示端并登录。
2. 数据源选择“官方 API”。
3. 平台选择“拼多多”或“京东”。
4. 点击“诊断”，确认目标平台通过；如果已经执行过搜索或精炼，前端会把当前已解析的价格、优惠、官方/自营筛选一并传给诊断接口。
5. 上传示例图或商品图，确认结果列表来自 `official_api`。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `not_configured` | 查看 `missingConfig`，补齐环境变量并重启后端 |
| `errorCode` 有值 | 按平台开放平台文档排查应用权限、签名、IP 白名单、推广位或接口授权 |
| `http_4xx` / `http_5xx` | 平台网关返回非 2xx；先看 `errorMessage` 里的 HTTP 状态和已脱敏平台响应摘要 |
| `timeout` / `network_error` | 检查本机网络、代理、平台域名解析和 `ECOMMERCE_API_TIMEOUT_SECONDS` |
| `invalid_url` | 检查 `PDD_API_BASE_URL` / `JD_API_BASE_URL` 是否是完整 `https://...` 地址 |
| `itemCount=0` 且 `success=true` | 换一个更常见的 `query`，或检查平台账号是否有该接口的数据权限 |
| 只想测一个平台 | 使用 `platforms=pdd` / `platforms=jd`，或 smoke 脚本的 `-Platforms` 参数 |
| 前端提示缺配置 | 先看 `/api/ecommerce/status`，确认后端进程是否读取了最新环境变量 |

## 完成标准

真实接入完成需要同时满足：

- 至少一个真实平台的诊断 `success=true`
- live smoke test 返回真实商品
- Web 端使用“官方 API”数据源能展示真实商品
- 所有密钥只存在环境变量或本地密钥管理器中，未进入 Git
