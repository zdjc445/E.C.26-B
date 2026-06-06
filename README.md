# AI 拍照识物与智能比价购物助手

本项目是面向 C 端消费者的聊天式购物 Agent。用户进入 APP 后，可在首页对话框中输入需求、添加商品图片，Agent 通过追问卡片明确偏好，并在信息足够后给出推荐卡片。

**当前阶段：聊天式 Mock Agent 闭环阶段。**

## 技术栈

- **客户端：** Flutter (Android)
- **服务端：** Java + Spring Boot
- **构建工具：** Maven (后端) / Flutter CLI (客户端)
- **交互形态：** 聊天首页 + 追问卡片 + 推荐卡片

## 当前阶段能力边界

当前阶段实现可演示的 Mock 闭环，不接入真实外部服务：

- 已完成 Spring Boot 最小可启动服务
- 已完成 `GET /api/health` 健康检查
- 已完成 `POST /api/images/upload` 图片上传
- 已完成 `POST /api/chat/sessions` 创建聊天会话
- 已完成 `POST /api/chat/sessions/{sessionId}/messages` 发送聊天消息
- 已完成 Flutter 聊天式首页、底部输入框、追问卡片、推荐卡片
- 语音按钮当前作为占位能力，后续接入真实语音识别
- 真实 AI 识别、真实电商 API、用户认证、数据库、收藏、价格提醒均为后续迭代

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

访问：

- 健康检查：http://localhost:8080/api/health

### Flutter 客户端

```powershell
cd app
C:\flutter\flutter\bin\flutter.bat pub get
C:\flutter\flutter\bin\flutter.bat run -d emulator-5554 --dart-define=EC26B_API_BASE_URL=http://10.0.2.2:8080
```

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
