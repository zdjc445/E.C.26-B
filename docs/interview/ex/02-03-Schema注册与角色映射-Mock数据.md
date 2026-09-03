# Schema 注册与角色映射：展示用 Mock

> 全部是模拟数据，用于说明生产化目标设计；不是官方完整响应，也不是当前代码契约。
> 商品、ID、SKU 关系与发布结果均为假设。完整数据见 [JSON 文件](../assets/02-03-schema-role-mock.json)。

```text
原始字段与元数据 → 字段/元数据映射 → 发布 Schema → 新 Offer 按 Schema 归一化
```

## 1. 原始输入：商品值和属性定义分开

淘宝风格的简化结构：

```json
{
  "platform": "taobao",
  "category_id": "demo_tb_mechanical_keyboard",
  "attribute_definitions": [
    {"name": "轴体", "is_sale_prop": true, "is_key_prop": false},
    {"name": "连接方式", "is_sale_prop": false}
  ],
  "sample_offer": {
    "offer_id": "demo_offer_A",
    "title": "Keychron K2 84键 青轴",
    "attributes": {"轴体": "青轴", "连接方式": "蓝牙/有线"}
  }
}
```

另一个平台的样本用 `switch_type=茶轴`、`connection=dual mode`。它未提供销售属性标记，保留未知；完整 JSON 另有模拟子 SKU，提供规格维度的观察证据。

## 2. 两类映射：字段名称和元数据名称

```json
{
  "platform": "taobao",
  "mapping_version": "demo_v1",
  "field_mapping": {
    "轴体": "switch_type",
    "连接方式": "connection_mode"
  },
  "metadata_mapping": {
    "is_sale_prop": "sales_attribute",
    "is_key_prop": "key_attribute"
  },
  "missing_metadata_value": null
}
```

这里先统一名称，不直接判定 role。元数据缺失保留 `null`；`is_sale_prop` 是字段定义的标记，不是商品的属性值。

## 3. 注册记录：保留原始标记，发布统一角色

下面只展开轴体字段。`source_binding` 指向平台来源，`attribute` 是统一定义：

```json
{
  "concept_id": "mechanical_keyboard",
  "schema_version": "demo_v3",
  "status": "ACTIVE",
  "attribute": {
    "canonical_key": "switch_type",
    "aliases": ["轴体", "switch_type", "轴选择"],
    "value_kind": "string",
    "role": "variant",
    "role_basis": "销售属性或有效 SKU 维度证据，且已验证适用范围"
  },
  "source_binding": {
    "platform": "taobao",
    "category_id": "demo_tb_mechanical_keyboard",
    "source_field": "轴体",
    "canonical_key": "switch_type",
    "source_metadata": {"is_sale_prop": true, "is_key_prop": false},
    "normalized_metadata": {"sales_attribute": true, "key_attribute": false}
  }
}
```

`ACTIVE` 假设额外窗口验证与审核已完成，A/B 两条样本本身不够。完整 JSON 的样本 D 提供“轴选择”和“连接技术”的新增别名证据，D 先于下面的 C 出现。

连接方式在本样例中保守设为 descriptive，原因是身份/规格证据不足；不能使用 `is_sale_prop=false → descriptive` 的直接转换，也不能把它推广到所有机械键盘。

## 4. 第二阶段输入：新 Offer + 候选 Schema

这是单条 Offer 的精简请求视图；完整 JSON 包含批次 ID 和每条 Offer 的候选引用。C 的宽泛 category 无精确绑定，按标题和字段别名补召回。

```json
{
  "offer": {
    "offer_id": "demo_offer_C",
    "platform": "taobao",
    "category": "电脑外设",
    "title": "Keychron K2 红轴 双模",
    "attributes": {"轴选择": "红轴", "连接技术": "Bluetooth / Wired"}
  },
  "candidate_schemas": [
    {
      "concept_id": "mechanical_keyboard",
      "schema_version": "demo_v3",
      "attributes": {
        "switch_type": {"aliases": ["轴体", "switch_type", "轴选择"], "role": "variant"},
        "connection_mode": {"aliases": ["连接方式", "connection", "连接技术"], "role": "descriptive"}
      }
    }
  ]
}
```

Top-K 是最多 K 个候选。本例两平台来源都指向同一个统一 Schema，去重后只传一个；有歧义时列表可放多个。每条 Offer 必须选定一个版本，或者返回 `NO_MATCH`。

## 5. 模型输出值，服务端按注册角色分桶

模型不重新决定 role，字段值必须有 C 自己的证据：

```json
{
  "offer_id": "demo_offer_C",
  "decision": "MATCH",
  "selected_schema": "mechanical_keyboard@demo_v3",
  "fields": [
    {
      "canonical_key": "switch_type", "value": "红轴",
      "evidence": {"offer_id": "demo_offer_C", "field_path": "attributes.轴选择", "raw_value": "红轴"}
    },
    {
      "canonical_key": "connection_mode", "value": "蓝牙/有线",
      "evidence": {"offer_id": "demo_offer_C", "field_path": "attributes.连接技术", "raw_value": "Bluetooth / Wired"}
    }
  ]
}
```

服务端校验候选版本、字段白名单和原文证据，再查注册角色得到：

```json
{
  "offer_id": "demo_offer_C",
  "concept_id": "mechanical_keyboard",
  "schema_version": "demo_v3",
  "normalized_variant": {"switch_type": "红轴"},
  "normalized_descriptive": {"connection_mode": "蓝牙/有线"},
  "comparison_status": "NOT_EVALUATED"
}
```

展示视图省略了最终记录里的 `field_evidence`，完整 JSON 有保留。本例只演示动态字段，未执行品牌型号处理、同款判定或完整 SKU 比较。

## 配套口播

> 我先把平台属性定义和值分开，把 is_sale_prop 归一化为 sales_attribute，同时保留原始标记。字段映射和角色经过验证后注册为固定版本。新商品出现“轴选择=红轴”时，模型按候选 Schema 提取值和原文证据，服务端查到 switch_type 的角色是 variant，再写入对应属性桶。

字段含义参考：[淘宝类目属性接口](https://developer.alibaba.com/doc2/apiDetail.htm?apiId=121)、[Amazon 变体家族说明](https://developer-docs.amazon/sp-api/docs/building-listings-management-workflows-guide#configure-variation-families)。平台形状已简化，未假定 Amazon 机械键盘支持某个具体 variation theme。
