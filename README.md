# 智能识物比价购物 AI APP 助手

本项目计划实现一个面向购物决策的 AI Agent 应用：用户可以通过拍照或自然语言描述表达购物需求，系统完成商品识别、跨平台比价、历史价格趋势分析、评价风险判断与个性化推荐。

## 项目定位

本项目不只做“搜索商品”，而是做“购物决策助手”：

- 识别用户拍摄或描述的商品
- 跨平台搜索候选商品
- 判断同款或相似款
- 比较候选商品价格
- 分析历史价格趋势
- 基于自然语言需求给出带证据链的推荐理由

## 核心流程

MVP 阶段围绕 API 契约中的主链路实现：

```text
imageId -> recognitionId -> searchTaskId -> comparisonId -> recommendationId
```

第一版使用 mock 商品数据完成稳定演示，不直接做真实电商爬虫。后续可以通过 `sourceType` 扩展到官方 API 或合规采集适配器。

## 技术栈

```text
前端：Flutter + Dart + Dio + Riverpod + fl_chart
后端：Spring Boot 4 + Java 21
鉴权：Spring Security + JWT
数据库：PostgreSQL + Flyway
API 文档：springdoc-openapi / OpenAPI
图片存储：本地 uploads/ 目录
商品数据：MockProductSourceProvider
AI 识别：MockRecognitionProvider
Agent 推荐：RuleBasedRecommendationService
```

## 文档导航

- [文档目录](docs/README.md)
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

## 当前阶段

当前处于项目启动阶段，优先完成需求边界、系统架构、技术选型和 MVP 功能闭环设计。

## 工程契约资产

- `docs/openapi.yaml`：机器可读 API 契约
- `backend/src/main/resources/db/migration/V1__init_schema.sql`：Flyway 初始数据库 schema
- `mock-data/`：MVP mock 商品、价格历史、评价摘要和识别样例
- `uploads/`：本地图片上传目录占位，真实图片不提交
