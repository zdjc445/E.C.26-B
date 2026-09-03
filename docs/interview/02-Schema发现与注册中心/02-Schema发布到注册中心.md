# Schema 发布到注册中心

## 生成可执行的平台映射

阶段一发现的 Schema 草案只说明多个平台字段具有相同语义，例如：

```jsonc
{
  "canonical_key": "switch_type",
  "type": "enum",
  "role": "variant",
  "source_candidate_ids": ["C001", "C002"],
  "enum_mapping": {
    "青轴": "blue",
    "茶轴": "brown",
    "红轴": "red"
  }
}
```

这还不能直接用于后续 Offer 转换，因为程序还不知道：

- 什么商品应该使用这套 Schema。
- 原始值需要经过什么转换才能写入统一字段。

因此，Schema 发布与注册体系按四部分组织：

| 数据 | 作用 | 连接方式 |
|---|---|---|
| `schema_route` | 根据平台、原平台类目和结构指纹找到逻辑 Schema | 通过 `schema_id` 连接整体信息 |
| `schema_search_index` | category 精确路由未命中时，根据商品标题 BM25 召回 Top-K Schema | 通过 `schema_id + schema_version` 连接不可变版本 |
| `schema_definition / schema_version` | 保存统一品类、字段、类型、role 和不可变版本 | 通过 `schema_id + version` 唯一确定 |
| `field_binding` | 从平台原始路径提取值，并转换成统一字段和值 | 通过 `route_id + binding_version` 连接，并声明兼容的 Schema 版本 |


### 1. 生成独立的 Schema 路由信息

类目绑定负责回答“这条 Offer 应该使用哪套 Schema”：

```jsonc
{
  "schema_routes": [
    {
      "route_id": "route_tb_500100",
      "platform": "taobao",
      "source_category_id": "500100",
      "schema_id": "product.mechanical_keyboard",
      "source_schema_fingerprint": "sha256:mock_tb_keyboard_fields",
      "status": "ACTIVE",
      "active_binding_version": 1
    },
    {
      "route_id": "route_pdd_600100",
      "platform": "pinduoduo",
      "source_category_id": "600100",
      "schema_id": "product.mechanical_keyboard",
      "source_schema_fingerprint": "sha256:mock_pdd_keyboard_fields",
      "status": "ACTIVE",
      "active_binding_version": 1
    }
  ]
}
```

其中：

- `platform + source_category_id` 用于精确召回，结构指纹用于检查兼容性。
- 路由只指向 `schema_id`；新 Offer 再从 `schema_definition.active_version` 取得当前版本。
- 两个平台可以指向同一个 `schema_id`，新增平台路由时不需要改写 Schema 定义。

### 2. 生成独立的 Schema BM25 搜索索引

`schema_route` 负责 `platform + category_id` 精确查询。没有精准路由时，需要使用商品标题检索
`schema_search_index`，召回少量 Top-K ACTIVE Schema。搜索索引由已发布 Schema 生成，是可以重建的
派生数据，不属于不可变字段契约本身。

```jsonc
{
  "document_id": "product.mechanical_keyboard@1",
  "schema_id": "product.mechanical_keyboard",
  "schema_version": 1,
  "schema_status": "ACTIVE",
  "category_name": "机械键盘",
  "category_aliases": ["机械式键盘", "游戏机械键盘"],
  "attribute_names": ["品牌", "型号", "轴体", "轴体类型", "连接方式", "连接类型"],
  "representative_terms": ["青轴", "茶轴", "红轴", "蓝牙", "USB-C", "84键"],
  "search_text": "机械键盘 机械式键盘 游戏机械键盘 品牌 型号 轴体 轴体类型 青轴 茶轴 红轴 连接方式 连接类型 蓝牙 USB-C 84键",
  "analyzer_version": "schema_zh_en_v1",
  "source_schema_hash": "sha256:mock_schema_definition_v1_hash",
  "indexed_at": "2026-09-03T12:00:30+08:00"
}
```

其中：

- `category_name` 和 `category_aliases` 表示商品主体及常见叫法。
- `attribute_names` 来自统一字段名称和经过验证的平台字段别名。
- `representative_terms` 只保留少量高区分度规格词，不能把原始商品标题全部拼进去。
- `search_text` 使用固定的中英文分词器建立 BM25 倒排索引。
- `source_schema_hash` 用于检查索引文档是否仍与对应 Schema 版本一致。

发布新 Schema 版本时，先生成新的 `document_id` 并完成 BM25 建索引，再将它标记为可检索；旧版本
退出 ACTIVE 后从查询过滤条件中排除。BM25 索引失败时仍可保留 Schema 定义，但该版本不能进入标题
模糊召回。

#### BM25 建索引和查询过程

Schema 发布时，将品类名、别名、属性名和少量代表词组成 `schema_search_document.search_text`，
再使用固定的中英文分词器建立倒排索引：

```text
Schema 发布
→ 生成 schema_search_document
→ 拼接 search_text
→ 中文和英文分词
→ 建立“关键词 → Schema 文档”的倒排索引
→ 保存词频、文档频率和文档长度
```

例如，倒排索引会保存“机械键盘”出现在哪些 Schema 文档中，而不是保存预先计算好的查询分数。
新 Offer 到来时，标题必须使用同一个分词器处理，再由 BM25 实时计算候选相关性：

```text
新 Offer 查询
→ 商品标题分词
→ 查询每个词对应的 ACTIVE Schema 文档
→ BM25 根据词频、词的稀有程度和文档长度计算相关性
→ 过滤低于最低门槛的候选
→ 返回 Top-K Schema
```

因此，`schema_search_document` 是建索引的输入，倒排索引是 BM25 引擎内部生成的检索结构，
`bm25_score` 则是在每次新 Offer 查询时计算的排序分数。

### 3. 生成原始字段到统一字段的绑定

字段绑定负责回答“从哪里取值，以及怎样转换”：

```jsonc
{
  "field_bindings": [
    {
      "route_id": "route_tb_500100",
      "binding_version": 1,
      "schema_id": "product.mechanical_keyboard",
      "schema_version": 1,
      "platform": "taobao",
      "source_category_id": "500100",
      "source_field": "轴体",
      "source_path": "skus.sku[].properties[pid=900102]",
      "source_candidate_id": "C001",
      "canonical_key": "switch_type",
      "target_type": "enum",
      "transform": {
        "type": "enum_map",
        "mapping": {
          "青轴": "blue",
          "茶轴": "brown",
          "红轴": "red"
        }
      }
    },
    {
      "route_id": "route_pdd_600100",
      "binding_version": 1,
      "schema_id": "product.mechanical_keyboard",
      "schema_version": 1,
      "platform": "pinduoduo",
      "source_category_id": "600100",
      "source_field": "轴体类型",
      "source_path": "sku_list[].spec[parent_id=980201].spec_name",
      "source_candidate_id": "C002",
      "canonical_key": "switch_type",
      "target_type": "enum",
      "transform": {
        "type": "enum_map",
        "mapping": {
          "青轴": "blue",
          "茶轴": "brown",
          "红轴": "red"
        }
      }
    }
  ]
}
```


常见转换规则包括：

| transform | 示例 |
|---|---|
| `trim_string` | `" K2 " → "K2"` |
| `enum_map` | `"青轴" → "blue"` |
| `unit_convert` | `41900 分 → 419.00 元` |
| `token_map` | `"蓝牙+USB-C" → ["bluetooth", "usb_c"]` |
| `status_map` | `is_onsale=1 → "onsale"` |

### 4. 对生成结果做确定性检查

平台映射写入注册中心前，服务端至少检查：

1. 每个 `field_binding` 都能追溯到真实的 `candidate_id` 和原始路径。
2. `canonical_key` 必须存在于本次 Schema 草案中。
3. `target_type` 必须与 Schema 字段类型一致。
4. 枚举映射左侧的原始值必须在候选样本中出现过。
5. 同一个平台原始路径不能同时映射到两个语义冲突的统一字段。
6. 使用样本执行转换后，结果必须通过类型和允许值校验。

检查通过后，注册中心保存以下关系：

```text
平台类目
→ schema_route.route_id + schema_id
→ schema_definition.active_version
→ field_binding(route_id + active_binding_version)
→ 校验其 schema_id + schema_version
→ canonical_key + transform
```

例如，新的拼多多 Offer 到来后，执行过程为：

```text
pinduoduo + category 600100
→ product.mechanical_keyboard@v1
→ sku_list[].spec[parent_id=980201].spec_name
→ 原始值“青轴”
→ enum_map
→ dynamic_attributes.switch_type = "blue"
```

因此，生成可执行平台映射的本质是：**把 LLM 发现的语义对应关系，转换成由平台适配器和规则服务
可以重复执行的确定性规则。**后续同类 Offer 命中该 Schema 后，可以直接执行这些映射，无需再次让
LLM 判断字段名称和枚举值。

## 生成不可变版本

可执行平台映射生成并检查通过后，需要将本次 Schema 的统一字段定义固化为一个不可变版本。
不可变指的是：`schema_id + version` 对应的字段、类型、role 和约束一旦写入就不能修改；
后续发生任何变化都必须生成新版本。

### 1. 固化完整 Schema 快照

一个版本必须保存完整的统一字段定义，不能只保存相对上一版本的差异，否则旧 Offer 无法独立还原
当时的字段语义。路由和平台字段映射分别保存在独立记录中，不再嵌入 `definition`：

```jsonc
{
  "schema_id": "product.mechanical_keyboard",
  "version": 1,
  "parent_version": null, // 第一次发布没有上一版本
  "definition": {
    "canonical_category_id": "mechanical_keyboard",
    "base_schema_version": 1,
    "dynamic_attributes": [
      {
        "canonical_key": "switch_type",
        "type": "enum",
        "role": "variant",
        "required": false,
        "allowed_values": ["blue", "brown", "red"]
      }
    ]
  },
  "provenance": {
    "discovery_batch_id": "discover_20260903_001",
    "candidate_ids": ["C001", "C002"]
  },
  "content_hash": "sha256:mock_schema_v1_content_hash",
  "created_at": "2026-09-03T12:00:00+08:00"
}
```

这里的 `definition` 是统一字段契约的完整快照。即使以后候选统计发生变化，
`product.mechanical_keyboard@v1` 仍然保持原来的字段语义；平台转换过程由对应版本的独立
`field_binding` 记录及其 `binding_version` 复现。

### 2. 计算内容哈希并分配版本号

版本生成流程为：

1. 对 `definition` 中的对象键、字段列表和映射表进行稳定排序。
2. 序列化成规范 JSON，避免空格或字段顺序不同导致哈希变化。
3. 计算 `content_hash`。
4. 查询同一 `schema_id` 的最新版本。
5. 如果哈希与最新版本相同，直接返回已有版本，不重复创建。
6. 如果内容发生变化，创建 `latest_version + 1`。

例如：

```text
注册中心不存在 product.mechanical_keyboard
→ 创建 product.mechanical_keyboard@v1

最新版本是 v1，并且新 definition 的 content_hash 与 v1 相同
→ 仍然返回 v1

最新版本是 v1，但新增字段或修改映射导致 content_hash 改变
→ 创建 product.mechanical_keyboard@v2，v1 保持不变
```

## 完整的注册中心数据结构

下面是机械键盘 Schema 注册完成后的聚合展示。实际存储时，事实数据可以拆成 `schema_route`、
`schema_definition / schema_version` 和 `field_binding`；`schema_search_index` 由这些数据生成并写入
BM25 检索引擎。

```jsonc
{
  "schema_routes": [ // 第一部分：路由信息，负责找到 schema_id
    {
      "route_id": "route_tb_500100",
      "platform": "taobao",
      "source_category_id": "500100",
      "source_schema_fingerprint": "sha256:mock_tb_keyboard_fields",
      "schema_id": "product.mechanical_keyboard",
      "status": "ACTIVE",
      "priority": 100,
      "active_binding_version": 1
    },
    {
      "route_id": "route_pdd_600100",
      "platform": "pinduoduo",
      "source_category_id": "600100",
      "source_schema_fingerprint": "sha256:mock_pdd_keyboard_fields",
      "schema_id": "product.mechanical_keyboard",
      "status": "ACTIVE",
      "priority": 100,
      "active_binding_version": 1
    }
  ],

  "schema_search_documents": [ // 第二部分：标题 BM25 模糊召回索引
    {
      "document_id": "product.mechanical_keyboard@1",
      "schema_id": "product.mechanical_keyboard",
      "schema_version": 1,
      "schema_status": "ACTIVE",
      "category_name": "机械键盘",
      "category_aliases": ["机械式键盘", "游戏机械键盘"],
      "attribute_names": ["品牌", "型号", "轴体", "轴体类型", "连接方式", "连接类型"],
      "representative_terms": ["青轴", "茶轴", "红轴", "蓝牙", "USB-C", "84键"],
      "search_text": "机械键盘 机械式键盘 游戏机械键盘 品牌 型号 轴体 轴体类型 青轴 茶轴 红轴 连接方式 连接类型 蓝牙 USB-C 84键",
      "analyzer_version": "schema_zh_en_v1",
      "source_schema_hash": "sha256:mock_schema_definition_v1_hash",
      "indexed_at": "2026-09-03T12:00:30+08:00"
    }
  ],

  "schema": { // 第三部分：Schema 整体信息
    "schema_definition": {
      "schema_id": "product.mechanical_keyboard",
      "canonical_category_id": "mechanical_keyboard",
      "active_version": 1,
      "latest_version": 1,
      "updated_at": "2026-09-03T12:01:00+08:00"
    },

    "schema_version": { // schema_id + version 唯一确定一个不可变字段契约
      "schema_id": "product.mechanical_keyboard",
      "version": 1,
      "parent_version": null,
      "definition": {
        "base_schema_ref": {
          "schema_id": "offer.basic",
          "version": 1
        },
        "dynamic_attributes": [
          {
            "canonical_key": "model",
            "type": "string",
            "role": "identity",
            "required": false
          },
          {
            "canonical_key": "switch_type",
            "type": "enum",
            "role": "variant",
            "required": false,
            "allowed_values": ["blue", "brown", "red"]
          },
          {
            "canonical_key": "connection_type",
            "type": "array<string>",
            "role": "descriptive",
            "required": false,
            "allowed_values": ["bluetooth", "usb_c"]
          }
        ]
      },
      "provenance": {
        "discovery_batch_id": "discover_20260903_001",
        "candidate_ids": ["C001", "C002", "C003", "C004", "C005", "C006"],
        "validation_report_id": "validate_20260903_001"
      },
      "content_hash": "sha256:mock_schema_definition_v1_hash",
      "created_at": "2026-09-03T12:00:00+08:00"
    }
  },

  "field_binding_records": [ // 第四部分：不同平台的可执行字段映射
    {
      "route_id": "route_tb_500100",
      "binding_version": 1,
      "schema_id": "product.mechanical_keyboard",
      "schema_version": 1,
      "platform": "taobao",
      "source_category_id": "500100",
      "bindings": [
        {
          "source_field": "型号",
          "source_path": "props_name[pid=900101]",
          "source_candidate_id": "C003",
          "canonical_key": "model",
          "target_type": "string",
          "transform": {"type": "trim_string"}
        },
        {
          "source_field": "轴体",
          "source_path": "skus.sku[].properties[pid=900102]",
          "source_candidate_id": "C001",
          "canonical_key": "switch_type",
          "target_type": "enum",
          "transform": {
            "type": "enum_map",
            "mapping": {"青轴": "blue", "茶轴": "brown", "红轴": "red"}
          }
        },
        {
          "source_field": "连接方式",
          "source_path": "props_name[pid=900103]",
          "source_candidate_id": "C005",
          "canonical_key": "connection_type",
          "target_type": "array<string>",
          "transform": {
            "type": "token_map",
            "split_pattern": "[+/]",
            "mapping": {"蓝牙": "bluetooth", "USB-C": "usb_c"}
          }
        }
      ]
    },
    {
      "route_id": "route_pdd_600100",
      "binding_version": 1,
      "schema_id": "product.mechanical_keyboard",
      "schema_version": 1,
      "platform": "pinduoduo",
      "source_category_id": "600100",
      "bindings": [
        {
          "source_field": "产品型号",
          "source_path": "goods_property_list[ref_pid=980102].vvalue",
          "source_candidate_id": "C004",
          "canonical_key": "model",
          "target_type": "string",
          "transform": {"type": "trim_string"}
        },
        {
          "source_field": "轴体类型",
          "source_path": "sku_list[].spec[parent_id=980201].spec_name",
          "source_candidate_id": "C002",
          "canonical_key": "switch_type",
          "target_type": "enum",
          "transform": {
            "type": "enum_map",
            "mapping": {"青轴": "blue", "茶轴": "brown", "红轴": "red"}
          }
        },
        {
          "source_field": "连接类型",
          "source_path": "goods_property_list[ref_pid=980103].vvalue",
          "source_candidate_id": "C006",
          "canonical_key": "connection_type",
          "target_type": "array<string>",
          "transform": {
            "type": "token_map",
            "split_pattern": "/",
            "mapping": {"无线蓝牙": "bluetooth", "Type-C有线": "usb_c"}
          }
        }
      ]
    }
  ]
}
```

四部分的连接关系是：

```text
schema_route
  └─ schema_id
      → schema_definition
          └─ active_version
              → schema_version

schema_route.route_id
+ schema_route.active_binding_version
  → field_binding_record
      └─ schema_id + schema_version
          → schema_version

schema_search_document.schema_id
+ schema_search_document.schema_version
  → schema_version
```

新拼多多 Offer 的读取顺序为：

```text
1. pinduoduo + category_id=600100 + 结构指纹
   → 命中 route_pdd_600100

2. route 取得 schema_id=product.mechanical_keyboard、active_binding_version=1
   → schema_definition 取得 active_version=1

3. 加载 product.mechanical_keyboard@v1 的字段契约
   → 知道 switch_type 是 variant enum

4. 使用 route_pdd_600100 + binding_version=1
   → 加载拼多多 field_binding_record
   → 校验它适用于 product.mechanical_keyboard@v1
   → “轴体类型=青轴”转换为 switch_type="blue"

如果第 1 步没有精准路由：

5. 使用商品标题查询 schema_search_index
   → BM25 返回 Top-K schema_id + schema_version
   → 交给后续候选消歧
```

这样拆分以后：

- 新增一个平台类目路由时，只新增 `schema_route` 和对应 `field_binding_record`，不修改已有 Schema 定义。
- 修改统一字段、类型、role 或约束时，生成新的 `schema_version`。
- 修改某个平台的字段路径或转换规则时，生成新的 `binding_version`，再切换路由的
  `active_binding_version`，不能覆盖历史映射。
- 切换 Schema 的 `active_version` 前，必须确认所有 ACTIVE 路由的当前字段映射都兼容新版本。
- `schema_search_index` 是派生索引，可以根据 ACTIVE Schema 重建；它不作为 Schema 定义的事实源。

标准 Offer 保存本次实际使用的路由、映射和 Schema 版本引用：

```jsonc
{
  "route_id": "route_pdd_600100",
  "binding_version": 1,
  "schema_id": "product.mechanical_keyboard",
  "schema_version": 1
}
```

因此，即使路由规则或 ACTIVE Schema 后续发生变化，系统仍然可以找到该 Offer 当时使用的字段契约和平台转换规则。
