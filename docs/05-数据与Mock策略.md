# 数据与 Mock 策略

## 概述

当前阶段使用少量人工构造数据支撑聊天式 Mock Agent 演示。Mock 数据只用于本地开发、接口联调和页面验收，不代表真实平台商品、真实价格或真实用户数据。

## 数据目录

```text
mock-data/
├── README.md                       # Mock 数据说明
├── chat-agent-scenarios.json       # 聊天式 Agent 演示流程
├── recognition-samples.json        # 后续识别结果示例
├── products.json                   # 演示商品数据
└── platform-products.json          # 演示平台商品数据
```

## 当前阶段使用方式

### chat-agent-scenarios.json

用于描述当前聊天闭环的演示数据，包含：

- 用户输入示例
- 追问选项
- 推荐卡片
- Mock 回复文本

### products.json

用于推荐卡片展示的演示商品，包含：

- 商品 ID
- 商品名
- 平台
- 价格
- 标签
- 推荐理由

当前直接把 Mock 数据视为不同平台来源展示，`platform` 字段统一带 `-mock` 后缀。

### platform-products.json

用于后续比价能力的演示数据，当前仅作为文档和联调参考。

### recognition-samples.json

用于后续真实图片识别接口的输出参考，当前不代表已接入真实 AI。

## 数据扩展计划

- 第二阶段：扩充聊天场景、商品类型与追问选项
- 第三阶段：引入真实电商 API，Mock 数据作为演示模式和降级数据
- 最终：Mock 数据作为本地演示与测试夹具

## 约束

- 所有 Mock 数据均为人工构造的示例
- 不包含真实用户数据
- 不包含爬取数据
- 不包含真实密钥、Token 或个人信息
- 不把 Mock 数据描述为真实平台数据
