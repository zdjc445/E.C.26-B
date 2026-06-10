# Mock 数据说明

本目录保存当前交付阶段使用的本地演示数据。

## 文件

| 文件 | 用途 |
|------|------|
| `mock-data.json` | 商品基础目录，供 `CompositeProductSourceProvider` 读取 |
| `category-taxonomy.json` | 标准品类、别名和属性 schema，供 `CategoryResolver` 归一品类 |

## 商品目录

`mock-data.json` 当前包含 26 个基础商品。

| 品类 | 基础商品数 |
|------|------------|
| 运动鞋 | 12 |
| 耳机 | 6 |
| 吹风机 | 4 |
| 背包 | 4 |

基础商品字段：

- `productId`
- `category`
- `title`
- `brand`
- `imageUrl`
- `platforms`
- `basePrice`

后端运行时会基于基础商品生成 `京东-mock`、`淘宝-mock`、`天猫-mock`、`拼多多-mock` 四个平台报价。

## 边界

- 数据只用于演示、测试和本地联调。
- 不代表真实平台商品、价格、库存或评价。
- 不包含真实用户数据、密钥或平台接口凭证。
