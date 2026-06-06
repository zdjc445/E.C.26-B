# AI 拍照识物与智能比价购物助手

本项目是面向 C 端消费者的聊天式购物 Agent。用户进入 APP 后，可以在首页对话框中输入购物需求、添加商品图片，Agent 通过识别、追问、比价和推荐卡片辅助用户完成购买决策。

**当前阶段：聊天式 AI 识别与多平台 Mock 推荐阶段。**

## 技术栈

- **客户端：** Flutter Android
- **服务端：** Java + Spring Boot
- **构建工具：** Maven / Flutter CLI
- **交互形态：** 聊天首页 + 图片识别 + 追问卡片 + 商品列表卡 + 比价卡 + 推荐卡
- **AI Provider：** Mock / Ark，Ark 不可用时回退 Mock

## 当前已实现能力

- Spring Boot 服务与 `GET /api/health`
- 手机 USB 调试下的核心演示闭环
- 图片上传：`POST /api/images/upload`
- 聊天会话创建、列表、历史读取、重命名、删除
- 聊天消息发送：文字需求、图片需求、追问选项
- 图片识别：`POST /api/recognition`
- 识别结果修正：`PATCH /api/recognition/{recognitionId}/attributes`
- Flutter 聊天首页、历史入口、个人页入口、底部输入栏
- 拍照/相册选择、图片上传和本地预览
- 识别结果卡片、识别修正面板
- 多平台 Mock 商品：`京东-mock`、`拼多多-mock`、`淘宝-mock`
- Mock 商品类别：运动鞋、耳机、吹风机
- 商品列表卡、平台比价卡、推荐购买卡
- 超预算时的空商品和空比价占位
- 历史会话恢复完整 `agentReply` 卡片

## 当前边界

- 真实 AI 识别需要配置 Ark 环境变量后实测；未配置或调用失败时回退 Mock。
- 商品搜索和比价当前使用人工构造的 Mock 数据，不代表真实平台数据。
- 真实电商 API、真实认证、Postgres 持久化、真实语音识别、收藏、价格提醒仍为后续迭代。
- Agent 目前输出解释摘要，不输出真实模型推理链。

## 本地启动

环境要求：

- JDK 21+
- Maven 3.9+
- Flutter SDK 3.22+

### 后端

```powershell
cd backend
mvn test
mvn -DskipTests clean package
java -jar target/shopping-agent-0.1.0.jar
```

健康检查：

```text
http://localhost:8080/api/health
```

### Ark AI 配置

默认使用 Mock Provider：

```powershell
$env:AI_PROVIDER="mock"
```

使用 Ark Provider：

```powershell
$env:AI_PROVIDER="ark"
$env:ARK_API_KEY="你的 Ark API Key"
$env:ARK_ENDPOINT_ID="你的 Ark Endpoint ID"
$env:ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
```

### Flutter 客户端

模拟器：

```powershell
cd app
C:\flutter\flutter\bin\flutter.bat pub get
C:\flutter\flutter\bin\flutter.bat run -d emulator-5554 --dart-define=EC26B_API_BASE_URL=http://10.0.2.2:8080
```

USB 真机调试时可先转发端口：

```powershell
adb reverse tcp:8080 tcp:8080
cd app
C:\flutter\flutter\bin\flutter.bat run -d 4917cba2 --dart-define=EC26B_API_BASE_URL=http://127.0.0.1:8080
```

## 验证命令

```powershell
cd backend
mvn test
```

```powershell
cd app
C:\flutter\flutter\bin\dart.bat analyze
C:\flutter\flutter\bin\flutter.bat test
```

当前记录：

- 后端测试：41 tests
- Flutter 测试：12 tests
- Flutter analyze：无 error/warning，仅 info

## 文档导航

| 文档 | 说明 |
|------|------|
| [docs/README.md](docs/README.md) | 文档目录 |
| [docs/00-比赛要求.md](docs/00-比赛要求.md) | 赛事官方要求 |
| [docs/01-项目范围与阶段计划.md](docs/01-项目范围与阶段计划.md) | 项目范围与阶段计划 |
| [docs/02-系统架构草案.md](docs/02-系统架构草案.md) | 系统架构草案 |
| [docs/03-核心流程设计.md](docs/03-核心流程设计.md) | 核心流程设计 |
| [docs/04-API草案.md](docs/04-API草案.md) | API 草案 |
| [docs/05-数据与Mock策略.md](docs/05-数据与Mock策略.md) | 数据与 Mock 策略 |
| [docs/06-AI与Agent设计草案.md](docs/06-AI与Agent设计草案.md) | AI 与 Agent 设计草案 |
| [docs/07-测试与验收计划.md](docs/07-测试与验收计划.md) | 测试与验收计划 |
| [docs/08-后续迭代清单.md](docs/08-后续迭代清单.md) | 后续迭代清单 |

## 工程结构

```text
backend/     Spring Boot API 服务
app/         Flutter Android 客户端
docs/        项目文档
mock-data/   开发用模拟数据
scripts/     辅助脚本
uploads/     本地上传文件目录
```
