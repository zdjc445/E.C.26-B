# 实现 taxonomy 同款匹配与 SKU 拆分链路

请在 `/app` 中完成独立商品匹配领域层的三个模块：

```text
/app/src/product_matching/normalization.py
/app/src/product_matching/same_item.py
/app/src/product_matching/sku.py
```

任务是主项目 `TaxonomyNormalizer → SameItemMatcher → SkuSplitter` 链路的标准库自包含版本。
`models.py`、`taxonomy.py` 和 `data/taxonomy.json` 已提供，不得修改其公开类型、字段、函数、
数据或规则。`taxonomy.json` 使用项目同款的 `schema_version`、`taxonomy_version`、
`categories`、`unit_rules`、`common_brand_aliases` 顶层结构，由 `load_taxonomy()` 从任务包内部
读取。不得添加第三方依赖，不得访问网络，也不得读取任务目录外的项目文件。

## 1. TaxonomyNormalizer

### Offer 标准化

`normalize_offer(offer)` 必须：

1. 使用 `Taxonomy.resolve_category()` 解析 `category_id` 或品类别名；未知品类输出 `None`，
   不得猜测。
2. 使用 `Taxonomy.normalize_brand()` 执行显式品牌别名映射。未知且长度至少为 2 的品牌保留
   原值；单字符或空品牌输出 `None`。原始品牌非空但结果为空时记录失败 `"brand"`。
3. 使用 `Taxonomy.normalize_model()` 将 `-`、`_`、`/`、`·` 和连续空白统一为一个空格；
   品类规则要求时转为大写。原始型号非空但结果为空时记录失败 `"model"`。
4. 分别标准化 `identity_attributes` 与 `variant_attributes`，不得合并两个字典。
5. 属性标准化失败时不得把该属性写入规范结果，并分别记录
   `"identity:<key>"` 或 `"variant:<key>"`。
6. 不得修改传入的 `Offer` 或属性映射；`recall_score` 初始化为 `0.0`。

### 属性标准化

所有属性值先执行 Unicode NFKC、首尾去空白、连续空白折叠。空值返回 `None`。

只支持以下项目规则中的单位换算：

- `L`、`l`、`升` → `L`
- `毫升`、`ml`、`ML` → 乘以 `0.001` 后输出 `L`
- `W`、`w`、`瓦` → `W`
- `kW`、`kw`、`KW`、`千瓦` → 乘以 `1000` 后输出 `W`
- `h`、`H`、`小时` → `h`

数字使用稳定的通用格式，例如 `500毫升 → 0.5L`、`1.6kW → 1600W`。

若当前品类为该属性声明了 enum：

- 按 taxonomy 中的顺序检查候选值；
- 候选值与输入完全相等、候选值包含输入或输入包含候选值时，返回候选值；
- 无候选值匹配时返回 `None`。

没有 enum 的属性返回完成文本与单位处理后的值。

### 识别结果与辅助函数

- `normalize_recognition()` 使用相同的品类、品牌、型号和属性规则；无法解析的值输出
  `None` 或不进入结果属性字典。
- `model_equivalent()` 对两侧执行 NFKC、去首尾空白、全局大写，并将型号分隔符统一为
  一个空格后严格比较；空型号永不等价。
- `title_token_similarity()` 对 NFKC 小写文本按非单词字符切分，删除长度小于 2 的 token，
  返回 `|交集| / sqrt(|左集合| × |右集合|)`；任一集合为空时返回 `0.0`。

## 2. SameItemMatcher

### 候选对生成

`generate_candidates()` 按输入索引顺序输出 `(i, j)`，其中 `i < j`。每一对按以下顺序判断：

1. 双方规范品类均非空且不同：拒绝。
2. 双方非空 `same_item_key` 完全一致：接受为候选。
3. 双方规范品牌均非空且不同：拒绝。
4. 双方规范型号均非空且不同：拒绝。
5. 双方规范品类相同，并且双方规范品牌都存在时，标题相似度至少为 `0.85` 才接受。
6. 其他情况拒绝。禁止用缺失品牌的一侧与有品牌的一侧组成候选。

### 成对判定

`judge_pair()` 必须先收集硬冲突：

- 非空规范品类不同：`"category"`
- 非空规范品牌不同：`"brand"`
- 非空规范型号不同：`"model"`
- identity 属性在双方都存在且非空但值不同：`"identity:<key>"`

存在任何硬冲突时立即返回 `score=0.0`、`verdict="different"`。

无硬冲突时计算以下维度：

| 维度 | 基础权重 | 取值 |
|---|---:|---|
| `title` | 0.35 | 注入的标题相似度 |
| `identity` | 0.30 | 双方共有 identity 键中值相等的比例；没有共有键时缺失 |
| `image` | 0.25 | 注入的图片相似度；未提供或返回 `None` 时缺失 |
| `source_key` | 0.10 | 双方非空 `same_item_key` 相等时为 1，否则缺失 |

缺失维度不参与，剩余权重重新归一化：

```text
score = Σ(weight × value) / Σ(present weights)
```

- `score >= accept_threshold`：`"same"`，默认阈值 `0.82`
- `score >= review_threshold`：`"review"`，默认阈值 `0.68`
- 其余：`"different"`

### complete-link 聚类

`cluster(candidates, pairs)` 从每个候选各自成簇开始。只有当两个簇之间的每一对成员都满足
以下任一条件时才能合并：

- `judge_pair()` 结论为 `"same"`；
- 两侧具有完全相同的非空权威 `same_item_key`。

按簇索引从小到大重复扫描，每次合并后从头重新扫描，直到没有变化。返回每个簇内排序后的
输入索引。禁止因为 `A≈B`、`B≈C` 就传递合并 `A` 与 `C`。

## 3. SkuSplitter

`split_spu(spu_members, spu_id)` 必须：

1. 空输入返回空列表。
2. 使用首个成员的规范品类，从 taxonomy 读取关键 `variant_attributes`。
3. 对关键属性名排序，生成 `key=value|key=value` 形式的 `sku_signature`。
4. 关键 variant 属性齐全且签名相同的 Offer 进入同组。
5. 缺少任一关键 variant 属性的 Offer 必须各自单独成组，`sku_signature=None`，列出
   `missing_sku_attributes`，加入风险 `"关键销售属性缺失，未与其他报价直接合并"`，并把
   组置信度乘以 `0.9`。
6. taxonomy 未声明关键 variant 属性时使用空签名 `""`，所有成员进入同组。

组置信度是成员 `recall_score` 的平均值并限制在 `[0, 1]`，最终保留 4 位小数。

### 报价去重与价格

每组先按 `(platform, shop_id or "", source_product_id or "")` 去重；键相同时保留
`source_updated_at` 字符串字典序最新的报价。

仅对 `price` 非空的报价计算：

```text
payable_price = price - coupon_amount + shipping_fee
```

缺失优惠券或运费时不参与对应加减。输出最低、最高、平均应付价、最低价 Offer ID，以及
有价格报价的平台数量。没有价格时这些价格字段为 `None`，`platform_count=0`。

`price_freshness` 只统计可解析的 `source_updated_at`：按距当前 UTC 时间的天数计算
`max(0, 1 - age_days / 30)`，取平均并保留 4 位小数；没有有效时间时为 `None`。
不含时区信息的 ISO 时间按 UTC 处理。即使组内没有价格，只要存在有效时间也必须计算
`price_freshness`。

### 稳定 ID

- `sku_signature` 非 `None` 时，SKU 组后缀是
  `sha256((signature or "single").encode()).hexdigest()[:10]`。
- 缺少关键 variant 属性的单例组使用
  `sha256(f"single:{offer_id}".encode()).hexdigest()[:10]`，其中 `offer_id` 是该组唯一成员的
  Offer ID，确保同一 SPU 中的多个单例组具有不同 ID。
- `group_id = f"{spu_id}:{suffix}"`。
- `spu_id_for()` 对排序后的 `offer_id` 列表执行
  `sha256(json.dumps(ids, ensure_ascii=False).encode()).hexdigest()[:12]`，返回
  `"spu:<digest>"`。

## 验收

验证器覆盖 taxonomy 别名、单位换算、enum 失败、identity/variant 分离、候选剪枝、硬冲突、
缺失维度权重重算、review/accept 阈值、complete-link 防传递合并、权威键旁路、SKU 签名、
缺失属性隔离、报价去重、应付价聚合和稳定 ID。
