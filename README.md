# 智能识物比价购物 AI APP 助手

本项目实现面向购物决策的 AI Agent 演示应用：用户通过拍照或上传图片表达购物需求，系统完成商品识别、动态建议卡片、跨平台 mock 比价、自然语言追加筛选和带证据链的购买推荐。

## 当前可运行能力

- Web/PWA 演示端：登录、示例图/拍照上传、识别结果、数据源切换、建议卡片、推荐列表、追加筛选、比价、推荐理由
- Spring Boot 后端：JWT 鉴权、统一响应、全局异常处理、Ark 可选 AI Provider、mock 商品源、拼多多/京东官方 API 适配器、LLM refine + 规则兜底
- 契约资产：OpenAPI、Flyway schema、mock 商品/价格/评价数据
- 合规边界：不实现非授权数据抓取；默认使用 `mock` / `sample_dataset`，真实平台通过 `official_api` 调用授权开放平台 API

## 本地启动

环境要求：

```text
JDK 17
Maven 3.9+
Python 3 或任意静态文件服务器
```

后端：

```powershell
cd backend
mvn test
mvn -DskipTests clean package
java -jar target/shopping-agent-0.1.0.jar
```

前端：

```powershell
python -m http.server 5173 -d frontend
```

访问：

- Web 演示端：http://localhost:5173
- Swagger UI：http://localhost:8080/swagger-ui.html
- 健康检查：http://localhost:8080/api/health

默认后端使用内存运行态加载 `mock-data/`，不要求本机 PostgreSQL。需要验证 Flyway/PostgreSQL schema 和运行时快照落库时可启用 `postgres` profile，并配置 `POSTGRES_JDBC_URL`、`POSTGRES_USER`、`POSTGRES_PASSWORD`。

## 最小验收路径

1. 打开 Web 演示端，注册或登录。
2. 点击“示例图”，再点击“上传并识别”。
3. 查看识别结果和建议卡片。
4. 点击“只看官方旗舰店”或输入：

```text
1000 元以内的黑色款，要评价 4.8 分以上，只看官方
```

5. 切换“低价 / 销量 / 好评”排序。
6. 勾选 2-4 个商品，点击“生成比价”，查看平台最低价、均价、商品数和商品对比表。
7. 点击“收藏”体验个性化入口，再点击“生成推荐”，查看推荐理由、风险和 evidence。

## AI Provider 配置

默认使用 mock provider，保证离线演示稳定。启用 Ark 时只通过环境变量配置，密钥不写入仓库：

```powershell
$env:AI_PROVIDER="ark"
$env:ARK_API_KEY="..."
$env:ARK_ENDPOINT_ID="..."
$env:ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
```

Ark 未配置、返回非 JSON 或调用失败时，图片识别会回退到 mock，追加筛选会回退到规则解析，接口响应会带上 provider/fallback 状态。

## 真实电商 API 配置

默认仍使用 mock 数据源。启用真实平台数据时，后端通过 `official_api` 数据源调用已授权的开放平台 API，当前已实现拼多多多多进宝商品搜索和京东联盟商品查询适配器。密钥只通过环境变量配置：

```powershell
$env:ECOMMERCE_API_ENABLED="true"

# 拼多多开放平台 / 多多进宝
$env:PDD_API_ENABLED="true"
$env:PDD_CLIENT_ID="..."
$env:PDD_CLIENT_SECRET="..."

# 京东宙斯 / 京东联盟
$env:JD_API_ENABLED="true"
$env:JD_APP_KEY="..."
$env:JD_APP_SECRET="..."
$env:JD_ACCESS_TOKEN="..."
```

启动后可在 Web 演示端右上角“数据源”选择“官方 API”，或在 `POST /api/search-tasks` 中传入 `"sourceType": "official_api"`。未配置平台密钥时，后端会返回明确的 `official_api not configured` 错误，不会执行网页抓取。

可先访问 `GET /api/ecommerce/status` 检查后端是否启用真实电商 API，以及拼多多/京东适配器是否已配置。该接口会返回缺失的环境变量名，方便联调，但不会返回任何密钥。登录后也可以在 Web 演示端点击“诊断”，或直接请求 `GET /api/ecommerce/diagnostics?query=吹风机&pageSize=3&platforms=pdd`，让后端对已配置的平台发起一次小页量真实查询并返回每个平台的成功状态、耗时、商品数量和示例标题。`platforms` 可选，支持 `pdd`、`jd`。如果平台用 HTTP 200 返回权限、签名或应用配置错误，后端也会识别为失败并给出平台 `errorCode` 与安全错误摘要。

拿到真实平台密钥后，可以运行一次 live smoke test 验证线上链路：

```powershell
$env:ECOMMERCE_LIVE_TEST="true"
$env:ECOMMERCE_LIVE_QUERY="吹风机"
mvn -Dtest=LiveOfficialApiSmokeTests test
```

也可以直接使用仓库脚本，它会先检查至少一个真实平台是否配置好：

```powershell
.\scripts\run-live-ecommerce-smoke.ps1 -Query "吹风机"
```

如果只验证单个平台，可传入平台过滤：

```powershell
.\scripts\run-live-ecommerce-smoke.ps1 -Query "吹风机" -Platforms "pdd"
```

该测试默认不会运行；脚本会自动加载仓库根目录的 `.env`，在本地检测密钥后显式设置 `ECOMMERCE_LIVE_TEST=true`。运行时会先请求 `GET /api/ecommerce/diagnostics` 验证平台诊断，再通过 `POST /api/search-tasks` 验证 `official_api` 搜索结果。
脚本会把平台开关按布尔值校验，`PDD_API_ENABLED` / `JD_API_ENABLED` 需要设置为 `true`、`1`、`yes` 或 `on`；`-Platforms` 仅支持 `pdd`、`jd`。
如果密钥放在其他本地文件，可以追加 `-EnvFile "D:\path\to\ecommerce.env"`。

完整联调步骤见 [真实电商 API 联调清单](docs/13-真实电商API联调清单.md)。仓库根目录提供 `.env.example` 作为变量模板；真实 `.env` 已被 `.gitignore` 忽略。

## 文档导航

- [文档目录](docs/README.md)
- [赛事方要求记录](docs/00-比赛要求.md)
- [需求分析](docs/01-需求分析.md)
- [系统架构](docs/02-系统架构.md)
- [Agent 设计](docs/03-Agent设计.md)
- [API 接口设计](docs/04-API接口设计.md)
- [OpenAPI 契约](docs/openapi.yaml)
- [数据库设计](docs/05-数据库设计.md)
- [开发计划](docs/06-开发计划.md)
- [测试方案](docs/07-测试方案.md)
- [演示说明](docs/08-演示说明.md)
- [用户认证与数据隔离](docs/09-用户认证与数据隔离.md)
- [项目分工说明](docs/10-项目分工说明.md)
- [AI 使用总结](docs/11-AI使用总结.md)
- [最终交付清单](docs/12-最终交付清单.md)
- [真实电商 API 联调清单](docs/13-真实电商API联调清单.md)

## 工程结构

```text
backend/     Spring Boot API 服务
frontend/    Web/PWA 演示端
docs/        需求、架构、API、数据库、测试和演示文档
mock-data/   商品、平台商品、价格历史、评价摘要和识别样例
uploads/     本地上传文件目录，真实图片不提交
```
