# 数据与 Mock 策略

## 概述

当前阶段使用极少量自造示例数据。后续迭代将扩展为完整演示数据集，并逐步接入真实电商 API。

## 数据目录

```text
mock-data/
├── README.md                    # Mock 数据说明
├── recognition-samples.json     # 识别结果示例
├── products.json                # 模拟商品数据
└── platform-products.json       # 模拟多平台同款商品
```

## Mock 数据用途

### recognition-samples.json

AI 识别结果的示例输出，包含：
- 商品类目
- 关键属性（颜色、品牌、款式等）
- 置信度

用于后续开发识别功能时的 API 联调与测试。

### products.json

模拟商品数据，每条包含：
- 商品 ID、名称、价格
- 来源平台
- 商品描述与标签

用于后续搜索结果展示与比价功能的开发调试。

### platform-products.json

同一商品在不同平台的对应商品，包含：
- 原始商品 ID
- 各平台商品 ID、价格、链接

用于后续跨平台比价功能的开发调试。

## 数据扩展计划

- 第二阶段：扩充至 50+ 商品，覆盖多种类目
- 第三阶段：接入真实电商 API，Mock 数据降级为 fallback
- 最终：Mock 数据作为演示模式的默认数据集

## 约束

- 所有 Mock 数据均为人工构造的示例，不涉及真实用户数据
- 不包含任何形式的爬取数据
- 不包含真实密钥、Token 或个人信息
