# product-matching

需要实现：

- `src/product_matching/normalization.py`
- `src/product_matching/same_item.py`
- `src/product_matching/sku.py`

`models.py`、`taxonomy.py` 与 `src/product_matching/data/taxonomy.json` 是任务预置契约，
不得修改。JSON 使用项目同款 schema，但文件随任务独立交付；运行时不会访问任务目录外的
项目文件。精确行为以 Harbor 任务的 `instruction.md` 为准，只允许使用 Python 标准库。
