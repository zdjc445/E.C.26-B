# 识价镜

识价镜是面向 C 端消费者的聊天式购物 Agent。用户进入 APP 后，可以在首页对话框中输入购物需求、添加商品图片，Agent 通过识别、追问、同款分组、平台报价和推荐解释辅助用户完成购买决策。

**当前阶段：聊天式 AI 识别 + 公开样例商品检索 + 多平台样例比价 + 7 维度自然语言筛选 + 同款分组 + 动态建议卡 + 收藏 + 价格提醒 + 语音转写。**

## 技术栈

- **客户端：** Flutter Android
- **服务端：** Java 21 + Spring Boot 3.4
- **构建工具：** Maven / Flutter CLI
- **交互形态：** 聊天首页 + 图片识别 + 动态建议卡 + 同款商品分组卡 + 平台报价明细
- **AI Provider：** Mock / Ark，Ark 不可用时自动回退 Mock

## 当前已实现能力

- Spring Boot 服务与 `GET /api/health`
- 手机 USB 调试下的核心演示闭环
- 图片上传：`POST /api/images/upload`
- 聊天会话创建、列表、历史读取、重命名、删除
- 简易认证：注册、登录、当前用户查询
- 聊天消息发送：文字需求、图片需求、追问选项
- 图片识别：`POST /api/recognition`
- 识别结果修正：`PATCH /api/recognition/{recognitionId}/attributes`
- Flutter 聊天首页、历史入口、个人页入口、底部输入栏
- 拍照/相册选择、图片上传和本地预览
- 识别结果卡片、识别修正面板
- 规则/Ark 购物意图解析，Ark 不可用时回退规则解析
- 轻量 taxonomy 检索归一：把 `头戴式蓝牙耳机`、`真无线蓝牙耳机` 等细分词归一为标准品类
- 多轮自然语言追加筛选：品类、预算、颜色、品牌、平台、排序、最低评分跨轮合并
- 本地商品检索链路：查询拆解、规则扩展、本地向量/BM25 混合检索、多因子重排
- 推荐解释增强：综合分、决策信号、证据摘要、风险提示、商品胜因/不足
- 默认公开商品源：`backend/src/main/resources/data/public-product-offers.json`
- 243 个基础商品，覆盖运动鞋 59 个、耳机 75 个、吹风机 17 个、背包 92 个
- 商品图片保留公开数据集中的外部 HTTP 链接
- 运行时生成 `京东-mock`、`淘宝-mock`、`天猫-mock`、`拼多多-mock` 四个平台演示报价
- 同款商品分组卡：展示跨平台价格区间、最低价、评价/销量、平台报价明细
- 商品详情页：购买判断、评价概览、平台比价、精选评论、价格提醒和收藏入口
- 商品卡显示品牌徽章、偏好命中徽章、价格走势 sparkline
- 动态建议卡：根据识别 category 生成差异化的 6 个建议入口
- 超预算时的空商品和空比价占位
- 历史会话恢复完整 `agentReply` 卡片
- 收藏商品：`POST /api/favorites`、`GET /api/favorites`、`DELETE /api/favorites/{productId}`
- 价格提醒：`POST /api/price-alerts`、`GET /api/price-alerts`、`POST /api/price-alerts/check`
- 语音转写：`POST /api/voice/transcribe`，默认 Mock，可切换 Provider

## 当前边界

- 真实 AI 识别需要配置 Ark 环境变量后实测；未配置或调用失败时回退 Mock。
- Ark 购物意图解析和推荐解释改写需要配置 Ark 环境变量；未配置或调用失败时回退规则解析与规则解释。
- 商品搜索和比价默认读取公开样例商品数据，不调用真实电商接口；平台价格、店铺和价格历史由代码生成，不代表真实平台商品、价格、库存或评价。
- 公开样例数据的销量全部为 0，35 条商品评分非 0，73 条商品原始品牌为空，因此销量、评分和品牌相关功能只用于验证功能链路，不用于证明推荐效果。
- 公开资源由 `scripts/build_public_product_offers.py` 从来源 CSV 确定性生成；来源页面当前将许可证标记为 `unknown`，正式发布前需要再次确认数据使用权限。
- 认证、收藏、价格提醒和聊天历史支持内存 / Postgres 仓库切换，演示环境默认可用内存仓库。
- 真实语音识别仍为后续迭代，当前默认返回 Mock 转写。
- Agent 输出结构化解释摘要，不输出真实模型推理链。

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
java -jar target/price-lens-0.1.0.jar
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

- 后端测试：142 tests，0 failures，0 errors
- Flutter analyze：0 error / 0 warning，33 条 info
- Flutter test：41 tests（37 个 widget 测试 + 4 个模型解析测试），全部通过

## 自然语言筛选示例

| 输入 | 命中字段 |
|------|----------|
| `300以内的耳机` | maxPrice=300, keyword=耳机 |
| `耐克的运动鞋` | brand=耐克, keyword=运动鞋 |
| `只看京东的耳机` | platforms=[京东-mock], keyword=耳机 |
| `只看天猫的耳机` | platforms=[天猫-mock], keyword=耳机 |
| `按价格从低到高排序` | sortBy=price_asc |
| `销量优先` | sortBy=sales_desc |
| `4.8分以上` | minRating=4.8 |
| `推荐耳机` → `只看300以内的黑色款` | 多轮合并 keyword=耳机, maxPrice=300, color=黑色 |
| `戴森吹风机便宜一点` | brand=戴森, keyword=吹风机, lowestPrice=true |

## 文档导航

| 文档 | 说明 |
|------|------|
| [docs/README.md](docs/README.md) | 文档目录 |
| [docs/00-比赛要求.md](docs/00-比赛要求.md) | 赛事官方要求 |
| [docs/01-项目范围与阶段计划.md](docs/01-项目范围与阶段计划.md) | 项目范围与阶段计划 |
| [docs/02-系统架构方案.md](docs/02-系统架构方案.md) | 系统架构方案 |
| [docs/03-核心流程设计.md](docs/03-核心流程设计.md) | 核心流程设计 |
| [docs/04-API设计.md](docs/04-API设计.md) | API 设计 |
| [docs/05-数据与Mock策略.md](docs/05-数据与Mock策略.md) | 数据与 Mock 策略 |
| [docs/06-AI与Agent设计草案.md](docs/06-AI与Agent设计草案.md) | AI 与 Agent 设计草案 |
| [docs/07-测试与验收计划.md](docs/07-测试与验收计划.md) | 测试与验收计划 |
| [docs/08-后续迭代清单.md](docs/08-后续迭代清单.md) | 后续迭代清单 |
| [docs/09-演示脚本.md](docs/09-演示脚本.md) | 演示脚本与最小验证用例集 |
| [docs/10-AI使用总结.md](docs/10-AI使用总结.md) | AI 编排、Prompt 设计与 AI Coding 心得 |
| [docs/11-项目分工说明.md](docs/11-项目分工说明.md) | 团队成员模块责任划分 |
| [docs/12-答辩材料.md](docs/12-答辩材料.md) | 30 分钟答辩速查与问答口径 |
| [docs/14-提交模板填报草稿.md](docs/14-提交模板填报草稿.md) | 最终提交模板填报草稿 |

## 工程结构

```text
backend/     Spring Boot API 服务
app/         Flutter Android 客户端
docs/        项目文档
mock-data/   开发用模拟数据
scripts/     辅助脚本
uploads/     本地上传文件目录
```
