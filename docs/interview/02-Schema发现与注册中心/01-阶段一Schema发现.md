# 阶段一：Schema 发现

本阶段产出带来源证据的 `SchemaDraft`。草案如何校验并成为正式版本，见
[Schema 发布到注册中心](./02-Schema发布到注册中心.md)。

## 淘宝：原始商品数据与属性元数据（模拟数据）

商品字段与类目属性接口返回的元数据合并展示；`item_props` 是平台属性定义，供阶段一参考。

```jsonc
{
  "num_iid": 51000001, // 淘宝商品 ID，用于关联该商品下的多个 SKU
  "cid": 500100, // 淘宝原平台类目 ID，用于查询类目模板和召回 Schema
  "title": "Keychron K2 84键机械键盘 蓝牙/USB-C双模 青轴/茶轴/红轴",
  "price": "399.00",
  "express_fee": "0.00", // 快递费用
  "freight_payer": "seller", // seller=卖家承担运费；buyer=买家承担
  "approve_status": "onsale", // onsale=出售中；instock=库中，不等于有库存
  "modified": "2026-09-03 10:00:00", // 平台商品最后修改时间
  "props": "20000:900001;900101:900002;900103:900003", // 本商品的属性值 ID 组合，格式为 pid:vid
  "props_name": "20000:900001:品牌:Keychron;900101:900002:型号:K2;900103:900003:连接方式:蓝牙+USB-C", // 对应的属性名和值，格式为 pid:vid:属性名:属性值


  "skus": {
    "sku": [ // 平台商品下的可购买规格；每个 SKU 有独立的价格和库存
      {
        "sku_id": 91000001, // 原平台 SKU ID，不是跨平台统一 ID
        "properties": "900102:900004", // 关联下方“轴体=青轴”的属性定义
        "price": "399.00", // 青轴款价格，人民币元；尚不能据此认定最终到手价
        "quantity": 12 // 青轴款库存
      },
      {
        "sku_id": 91000002,
        "properties": "900102:900005", // 轴体=茶轴
        "price": "419.00",
        "quantity": 8
      },
      {
        "sku_id": 91000003,
        "properties": "900102:900006", // 轴体=红轴
        "price": "399.00",
        "quantity": 10
      }
    ]
  },
  "item_props": {
    "item_prop": [ // 类目属性定义的节选；枚举值说明取值含义，商品选值见 props / skus
      {
        "pid": 20000, // 平台属性 ID
        "name": "品牌", // 平台属性名称
        "is_key_prop": true, // 关键属性标记，作为 identity 的候选依据
        "is_sale_prop": false, // 非销售属性；false 不直接等于 descriptive
        "prop_values": {
          "prop_value": [
            {"vid": 900001, "name": "Keychron"} // vid=属性值 ID；name=属性值名称
          ]
        }
      },
      {
        "pid": 900101,
        "name": "型号",
        "is_key_prop": true,
        "is_sale_prop": false,
        "prop_values": {
          "prop_value": [
            {"vid": 900002, "name": "K2"}
          ]
        }
      },
      {
        "pid": 900102,
        "name": "轴体",
        "is_key_prop": false,
        "is_sale_prop": true, // 销售属性标记；本例各 SKU 的轴体取值不同，支持 variant 判断
        "is_enum_prop": true, // 枚举属性
        "multi": false, // 单个 SKU 的该属性不允许多选
        "prop_values": {
          "prop_value": [
            {"vid": 900004, "name": "青轴"},
            {"vid": 900005, "name": "茶轴"},
            {"vid": 900006, "name": "红轴"}
          ]
        }
      },
      {
        "pid": 900103,
        "name": "连接方式",
        "is_sale_prop": false, // 源元数据未提供 is_key_prop，不自行补成 false
        "prop_values": {
          "prop_value": [
            {"vid": 900003, "name": "蓝牙+USB-C"}
          ]
        }
      }
    ]
  }
}
```

商品字段参考[淘宝商品接口](https://developer.alibaba.com/docs/api.htm?apiId=24625&source=search)，示例仅保留相关字段。

## 拼多多：原始商品数据（模拟数据）

下面展示与淘宝相近的 Keychron K2 商品。属性、规格、价格和库存均填入模拟值；属性及规格 ID 只在本平台内使用。

```jsonc
{
  "goods_id": 52000001, // 拼多多商品 ID，用于关联该商品下的多个 SKU
  "cat_id": 600100, // 拼多多原平台类目 ID，用于查询类目模板和召回 Schema
  "goods_name": "Keychron K2机械键盘 84键 无线蓝牙/Type-C有线 青轴茶轴红轴可选", // 商品名称，对应淘宝 title 的语义
  "goods_desc": "Keychron K2，支持蓝牙与Type-C有线连接，可选青轴、茶轴、红轴。", // 商品描述，保留来源文本
  "market_price": 45900, // 参考价，单位为人民币分，即459元；不能当作实际售价
  "customer_num": 2, // 拼团人数，本例为2人团；拼单价需结合拼团条件使用
  "cost_template_id": 880002, // 运费模板ID，不是运费金额；具体运费需结合模板和收货地址
  "shipment_limit_second": 172800, // 承诺发货时间，单位为秒，本例为48小时
  "is_pre_sale": 0, // 是否预售：0=非预售，1=预售
  "goods_property_list": [ // 商品属性的实际选值；属性名称需关联类目属性模板，下面用注释说明
    {
      "ref_pid": 310, // 引用属性ID，本例表示“品牌”
      "template_pid": 980001, // 类目模板中的属性ID，用于关联平台属性定义
      "vid": 810001, // 属性值ID
      "vvalue": "Keychron" // 属性的实际文本值
    },
    {
      "ref_pid": 980102, // 本例表示“产品型号”
      "template_pid": 980002,
      "vid": 810002,
      "vvalue": "K2"
    },
    {
      "ref_pid": 980103, // 本例表示“连接类型”
      "template_pid": 980003,
      "vid": 810003,
      "vvalue": "无线蓝牙/Type-C有线" // 与淘宝“蓝牙+USB-C”的表达不同
    }
  ],



  "sku_list": [ // 商品下的可购买规格，各自记录规格组合、价格和库存
    {
      "sku_id": 92000001, // 拼多多平台SKU ID，不与淘宝SKU ID直接比较
      "is_onsale": 1, // SKU上架状态：1=上架，0=下架
      "price": 41900, // 单买价，单位为人民币分，即419元
      "multi_price": 38900, // 拼单价，单位为人民币分，即389元；不是优惠券金额
      "quantity": 22, // 当前SKU库存
      "spec": [ // SKU选中的销售规格；结构本身可作为 variant 的候选证据
        {
          "parent_id": 980201, // 规格维度ID
          "parent_name": "轴体类型", // 规格维度名称，对应淘宝的“轴体”
          "spec_id": 820001, // 该维度下的具体规格ID
          "spec_name": "青轴" // 当前SKU选中的规格值
        }
      ]
    },
    {
      "sku_id": 92000002,
      "is_onsale": 1,
      "price": 43900, // 单买价439元
      "multi_price": 40900, // 拼单价409元
      "quantity": 10,
      "spec": [
        {
          "parent_id": 980201,
          "parent_name": "轴体类型",
          "spec_id": 820002,
          "spec_name": "茶轴"
        }
      ]
    },
    {
      "sku_id": 92000003,
      "is_onsale": 1,
      "price": 41900,
      "multi_price": 38900,
      "quantity": 14,
      "spec": [
        {
          "parent_id": 980201,
          "parent_name": "轴体类型",
          "spec_id": 820003,
          "spec_name": "红轴"
        }
      ]
    }
  ]
}
```

字段示例参考[第三方服务的拼多多商品明细文档](https://doc.fw199.com/docs/h7b/pdd-goods-detail-get)，用于结构演示；尚未逐项核验当前官方接口版本。

## 阶段一需要解决的核心问题

### 如何将不同平台的字段统一成可比较、可检索的标准字段？

例如，淘宝的 `title` 和拼多多的 `goods_name` 都表示商品名称；淘宝通过 `pid:vid` 关联“轴体=青轴”，
拼多多通过 `sku_list[].spec[]` 中的 `parent_name="轴体类型"` 和 `spec_name="青轴"` 表达相近含义。
另外，淘宝 SKU 的 `price="399.00"` 以元计价，拼多多 SKU 的 `price=41900` 以分计价，需统一单位；
拼多多的 `price` 与 `multi_price` 分别对应单买和拼单条件，比较时也要保留条件差异。



#### 按照“基本数据 + 动态属性”转换后的单条 Offer


首先由Schema注册中心获得空的Schema

```jsonc
{
  "schema_version": 1,
  "basic_data": {
    "source_platform": "string",
    "source_category_id": "string",
    "source_product_id": "string",
    "source_sku_id": "string",
    "product_name": "string",
    "brand": "string",
    "prices": "array",
    "shipping_fee": "object",
    "listing_status": "string"
  },
  "dynamic_attributes": {}, // 已经被当前 Schema 接纳的品类属性
  "unmapped_attributes": [] // 暂未映射的原始属性，作为新动态字段的候选来源
}
```

接下来不能直接让 LLM 自由填写 `dynamic_attributes`。系统先通过平台适配器读取原始结构，生成
带有来源和值的 `unmapped_attributes`，再由 LLM 合并语义相同的候选字段并分析 role 证据。

##### 1. 提取固定字段并记录已消费路径

每个平台维护一份固定字段映射表，优先通过确定性代码填写 `basic_data`：

| 统一字段 | 淘宝原始路径 | 拼多多原始路径 |
|---|---|---|
| `source_category_id` | `cid` | `cat_id` |
| `source_product_id` | `num_iid` | `goods_id` |
| `product_name` | `title` | `goods_name` |
| `brand` | `props_name[品牌]` | `goods_property_list[品牌].vvalue` |
| `prices` | `skus.sku[].price` | `sku_list[].price`、`multi_price` |
| `shipping_fee` | `express_fee` | 根据运费接口获得；本例原始数据只有模板 ID |
| `listing_status` | `approve_status` | `sku_list[].is_onsale` |

被这些规则消费过的原始路径会放入 `consumed_paths`，后续不再作为动态属性候选。例如品牌已经进入
`basic_data`，就不能再次出现在 `dynamic_attributes`。

##### 2. 平台适配器填写 `unmapped_attributes` 和 role 证据

平台适配器只解析平台结构，不负责确定最终统一字段名和 role。它把没有被 `basic_data` 消费的
结构化商品属性写入当前 Offer 的 `unmapped_attributes`：

- 淘宝适配器解析 `props_name` 得到 `pid、vid、属性名、属性值`，再用 `pid` 关联
  `item_props.item_prop[]` 中的 `is_key_prop`、`is_sale_prop` 等元数据；同时解析
  `skus.sku[].properties`，检查属性是否出现在 SKU 中以及是否在不同 SKU 间变化。
- 拼多多适配器解析 `goods_property_list[]` 中的商品级属性；真实字段名缺失时通过
  `template_pid/ref_pid` 查询类目属性模板。然后解析 `sku_list[].spec[]`，统计相同
  `parent_id` 下有哪些 `spec_name`，判断它是否形成 SKU 规格维度。

离线任务再按照品类汇总多条 Offer 的 `unmapped_attributes`，形成用于候选选择的 `unmapped_pool`。
使用前面的两份原始数据，可以生成以下中间结果：

```jsonc
{
  "category": "mechanical_keyboard",
  "unmapped_pool": [ // 来源是各条 Offer 的 unmapped_attributes，不是最终动态字段
    {
      "candidate_id": "C003", // 本批候选属性的稳定 ID
      "source_platform": "taobao",
      "source_path": "props_name[型号]",
      "source_field": "型号",
      "raw_value": "K2",
      "role_evidence": {
        "is_key_prop": true, // 平台认为它是关键属性，支持 identity 判断
        "is_sale_prop": false,
        "appears_in_sku": false
      }
    },
    {
      "candidate_id": "C004",
      "source_platform": "pinduoduo",
      "source_path": "goods_property_list[ref_pid=980102].vvalue",
      "source_field": "产品型号", // 由 ref_pid 关联类目属性模板得到
      "raw_value": "K2",
      "role_evidence": {
        "is_product_level_property": true,
        "same_across_skus": true
      }
    },
    {
      "candidate_id": "C001",
      "source_platform": "taobao",
      "source_path": "item_props[pid=900102] + skus.sku[].properties",
      "source_field": "轴体",
      "raw_values": ["青轴", "茶轴", "红轴"],
      "role_evidence": {
        "is_sale_prop": true,
        "appears_in_sku": true,
        "varies_between_skus": true // 强 variant 证据
      }
    },
    {
      "candidate_id": "C002",
      "source_platform": "pinduoduo",
      "source_path": "sku_list[].spec[parent_id=980201]",
      "source_field": "轴体类型",
      "raw_values": ["青轴", "茶轴", "红轴"],
      "role_evidence": {
        "appears_in_sku_spec": true,
        "varies_between_skus": true // 强 variant 证据
      }
    },
    {
      "candidate_id": "C005",
      "source_platform": "taobao",
      "source_path": "props_name[连接方式]",
      "source_field": "连接方式",
      "raw_value": "蓝牙+USB-C",
      "role_evidence": {
        "appears_in_sku": false
      }
    },
    {
      "candidate_id": "C006",
      "source_platform": "pinduoduo",
      "source_path": "goods_property_list[ref_pid=980103].vvalue",
      "source_field": "连接类型",
      "raw_value": "无线蓝牙/Type-C有线",
      "role_evidence": {
        "is_product_level_property": true,
        "same_across_skus": true
      }
    }
  ]
}
```

这里的 `role_evidence` 只是证据。例如 `is_key_prop=true` 只能说明字段是 `identity` 候选，
`is_sale_prop=true` 或位于 SKU 规格中也只是 `variant` 候选；最终 role 还需要结合多条同品类
Offer 的覆盖率、SKU 内变化情况和字段语义确定。

##### 3. 使用候选 ID 限制 LLM 的输出范围

给 `unmapped_pool` 中的每个候选属性分配稳定 ID。以轴体字段为例，发送给 LLM 的候选子集为：

```jsonc
[
  {
    "candidate_id": "C001",
    "source_platform": "taobao",
    "source_field": "轴体",
    "values": ["青轴", "茶轴", "红轴"],
    "role_evidence": {
      "is_sale_prop": true,
      "varies_between_skus": true
    }
  },
  {
    "candidate_id": "C002",
    "source_platform": "pinduoduo",
    "source_field": "轴体类型",
    "values": ["青轴", "茶轴", "红轴"],
    "role_evidence": {
      "appears_in_sku_spec": true,
      "varies_between_skus": true
    }
  }
]
```

要求 LLM 输出的每个动态字段必须通过 `source_candidate_ids` 引用输入候选：

```jsonc
{
  "canonical_key": "switch_type",
  "source_candidate_ids": ["C001", "C002"],
  "type": "enum",
  "proposed_role": "variant",
  "enum_mapping": {
    "青轴": "blue",
    "茶轴": "brown",
    "红轴": "red"
  },
  "confidence": 0.96
}
```

服务端检查 `source_candidate_ids` 是否全部属于本次输入，并验证枚举映射中的每个原始值是否真实存在。
没有引用候选 ID、引用越界或生成无来源值的字段直接拒绝，继续保留在 `unmapped_pool` 中。

##### 4. 使用统计信息判断候选属性是否可用

LLM 合并同义字段后，再根据`source_candidate_ids` 汇总统计量，判断合并结果能否进入动态 Schema 候选名单。不能只使用原始
出现次数，因为不同平台的采样量可能差异很大，需要计算归一化指标：

```text
offer_coverage = 出现该属性的 Offer 数 / 当前品类 Offer 总数
type_consistency = 符合目标类型的值数 / 该属性全部值数
sku_variation_rate = 该属性在 SKU 间变化的商品数 / 多 SKU 商品数
platform_support = 支持该语义属性的平台数 / 当前接入平台数
```

例如，将更多机械键盘样本加入候选池后，`C001` 和 `C002` 合并结果的统计信息可能是：

```jsonc
{
  "canonical_key": "switch_type",
  "source_candidate_ids": ["C001", "C002"],
  "statistics": {
    "sample_offer_count": 200, // 当前批次机械键盘 Offer 总数
    "present_offer_count": 178, // 其中178条出现了轴体字段
    "offer_coverage": 0.89,
    "type_consistency": 0.98,
    "multi_sku_product_count": 80,
    "varies_between_skus_count": 72,
    "sku_variation_rate": 0.90,
    "supported_platform_count": 2
  },
  "role_evidence": {
    "taobao_is_sale_prop": true,
    "pinduoduo_appears_in_sku_spec": true
  },
  "candidate_score": 0.93,
  "decision": "ACCEPT_AS_CANDIDATE" // 进入动态 Schema 候选名单，尚未直接发布
}
```

候选分数可以按验证集调参，例如：

```text
candidate_score =
    offer_coverage       × 0.30
  + type_consistency     × 0.20
  + role_evidence_score  × 0.30
  + platform_support     × 0.10
  + retrieval_value      × 0.10
```

统计节点输出三种结果：

| decision | 含义 |
|---|---|
| `ACCEPT_AS_CANDIDATE` | 覆盖率、类型和 role 证据满足门槛，进入动态 Schema 草案 |
| `WAIT_MORE_SAMPLES` | 当前证据不足，继续留在 `unmapped_pool` 中积累样本 |
| `REJECT` | 属于噪声、技术字段、重复字段或无法可靠归一化，不进入 Schema |


##### 5. 结合平台信号和统计结果确认字段 role

只对上一步判定为 `ACCEPT_AS_CANDIDATE` 的字段确认 role。优先使用电商平台原始结构提供的信号，
LLM 负责合并同义字段并提出 `proposed_role`，规则服务核验原始路径和统计数据后给出最终 role：

| role | 平台信号与统计条件 | 处理方式 |
|---|---|---|
| `variant` | 淘宝 `is_sale_prop=true`，或字段位于 `skus.sku[].properties`、拼多多 `sku_list[].spec[]`；并且在同一商品的不同 SKU 间实际发生变化 | 用于同一 SPU 内区分 SKU |
| `identity` | 淘宝 `is_key_prop=true` 或字段属于商品级属性；同一商品的各 SKU 取值稳定，并且能区分不同商品 | 与品牌等字段组合，用于判断 SPU |
| `descriptive` | 不决定 SKU，也不足以区分 SPU，但对检索、过滤或展示有价值 | 只参与软检索与展示 |

平台标记不能脱离实际数据直接使用。例如，只有 `is_sale_prop=true`、但字段没有进入 SKU 组合或在
不同 SKU 间从不变化时，不能确认成 `variant`。价格、库存、运费和促销即使随 SKU 变化，也属于
交易信息，不参与 role 判断。

规则服务可以按以下顺序确认：

1. 校验 `source_candidate_ids`、原始路径和平台标记确实存在。
2. 排除价格、库存、运费、促销等交易字段。
3. 满足“SKU 结构证据 + SKU 间变化”时确认 `variant`。
4. 满足“SKU 间稳定 + 跨商品有区分度 + 关键属性或身份语义”时确认 `identity`。
5. 只具有检索价值时确认 `descriptive`；证据冲突或不足时返回 `WAIT_MORE_SAMPLES`，不写入正式 Schema。

例如，`C001` 和 `C002` 都来自平台的 SKU 规格结构，并且轴体在同一商品的多个 SKU 间发生变化，
因此规则服务可以确认 `switch_type` 的 role：

```jsonc
{
  "canonical_key": "switch_type",
  "source_candidate_ids": ["C001", "C002"],
  "proposed_role": "variant", // LLM 根据字段语义提出的建议
  "role_evidence": {
    "taobao_is_sale_prop": true,
    "pinduoduo_appears_in_sku_spec": true,
    "sku_variation_rate": 0.90
  },
  "final_role": "variant", // 规则服务根据平台证据和统计结果确认
  "role_decision": "CONFIRMED"
}
```

`model` 在同一商品的 SKU 间保持一致，并能与品牌组合区分 SPU，因此确认成 `identity`；
`connection_type` 在当前机械键盘样本中不形成 SKU 规格，只用于检索和展示，因此确认成 `descriptive`。
role 的结论只在当前品类和 Schema 版本内有效，后续规则变化时发布新版本，不能直接覆盖旧版本。

##### 6. 汇总通过约束、统计和 role 判断的动态 Schema 草案

LLM 以 `unmapped_pool` 为主要输入，同时携带平台类目、商品标题和必要的原文上下文用于消歧，并合并
同义字段。每个输出字段必须给出原始路径和 role 证据；约束检查、统计筛选和 role 确认都通过后，
整理为完整草案：

```jsonc
{
  "dynamic_attribute_candidates": [
    {
      "canonical_key": "model",
      "source_candidate_ids": ["C003", "C004"],
      "type": "string",
      "role": "identity",
      "source_aliases": ["型号", "产品型号"],
      "evidence_paths": [
        "taobao:props_name[型号]",
        "pinduoduo:goods_property_list[ref_pid=980102].vvalue"
      ]
    },
    {
      "canonical_key": "switch_type",
      "source_candidate_ids": ["C001", "C002"],
      "type": "enum",
      "role": "variant",
      "source_aliases": ["轴体", "轴体类型"],
      "enum_mapping": {
        "青轴": "blue",
        "茶轴": "brown",
        "红轴": "red"
      },
      "evidence_paths": [
        "taobao:item_props[pid=900102] + skus.sku[].properties",
        "pinduoduo:sku_list[].spec[parent_id=980201]"
      ]
    },
    {
      "canonical_key": "connection_type",
      "source_candidate_ids": ["C005", "C006"],
      "type": "array<string>",
      "role": "descriptive",
      "source_aliases": ["连接方式", "连接类型"],
      "evidence_paths": [
        "taobao:props_name[连接方式]",
        "pinduoduo:goods_property_list[ref_pid=980103].vvalue"
      ]
    }
  ]
}
```



### 2. 确定 role 后的单条 Offer 转换结果

淘宝青轴 Offer 转换结果：

```jsonc
{
  "schema_id": "product.mechanical_keyboard",
  "schema_version": 1, // 本条数据采用的统一 Schema 版本
  "basic_data": { // 所有品类都使用的固定字段
    "source_platform": "taobao",
    "source_category_id": "500100",
    "source_product_id": "51000001", // 同一商品下的三个 SKU 共用该 ID
    "source_sku_id": "91000001", // 保留原平台 SKU ID，便于追溯原始数据
    "product_name": "Keychron K2 84键机械键盘 蓝牙/USB-C双模 青轴/茶轴/红轴",
    "brand": "Keychron", // 品牌属于跨品类通用字段，放在 basic_data
    "prices": [
      {
        "amount": 399.00, // 原始 price="399.00" 已转换为数值
        "currency": "CNY",
        "price_type": "single"
      }
    ],
    "shipping_fee": {
      "amount": 0.00,
      "currency": "CNY"
    },
    "listing_status": "onsale"
  },
  "dynamic_attributes": { // 该 Offer 的品类动态属性，由 LLM 按已发现的字段语义转换
    "model": "K2",
    "connection_type": ["bluetooth", "usb_c"],
    "switch_type": "blue" // 原始“轴体=青轴”转换成统一枚举值
  },
  "unmapped_attributes": [] // 本例候选属性均已映射；存在未知字段时在这里保留原字段名、值和来源路径
}
```

拼多多青轴 Offer 转换结果：

```jsonc
{
  "schema_id": "product.mechanical_keyboard",
  "schema_version": 1,
  "basic_data": {
    "source_platform": "pinduoduo",
    "source_category_id": "600100",
    "source_product_id": "52000001",
    "source_sku_id": "92000001",
    "product_name": "Keychron K2机械键盘 84键 无线蓝牙/Type-C有线 青轴茶轴红轴可选",
    "brand": "Keychron", // 与淘宝使用相同的固定字段名
    "prices": [
      {
        "amount": 419.00, // 原始 price=41900 分，转换为419元
        "currency": "CNY",
        "price_type": "single"
      },
      {
        "amount": 389.00, // 原始 multi_price=38900 分，转换为389元
        "currency": "CNY",
        "price_type": "group",
        "group_size": 2 // 该价格需要2人成团
      }
    ],
    "shipping_fee": {
      "amount": 0.00,
      "currency": "CNY"
    },
    "listing_status": "onsale"
  },
  "dynamic_attributes": {
    "model": "K2",
    "connection_type": ["bluetooth", "usb_c"],
    "switch_type": "blue" // 原始“轴体类型=青轴”转换成统一枚举值
  },
  "unmapped_attributes": [] // 未进入当前 Schema 的原始属性留在这里，供后续版本发现
}
```

因此，原来的茶轴和红轴 SKU 也会分别生成自己的标准 Offer，而不会被合并到上面两条结果中。
不同平台的单条 Offer 都将 `brand` 保存在 `basic_data`，动态属性也使用相同的 `canonical_key`，从而能够进行
跨平台检索和比较。字段类型、role 和平台映射关系保存在 Schema 注册中心，不在每条 Offer 中重复保存。
