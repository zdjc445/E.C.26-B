# Harbor Task: taxonomy-product-matching

这是一个独立、自包含的 Harbor 软件工程任务。参评 Agent 需要在 Python 标准库范围内实现
`TaxonomyNormalizer → SameItemMatcher → SkuSplitter` 商品匹配链路，包括 taxonomy 驱动的
标准化、同款候选与评分、complete-link 聚类、SKU 拆分、报价去重和价格聚合。

## 任务结构

```text
taxonomy-product-matching/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile
│   └── starter/
├── solution/
│   ├── solve.sh
│   └── product_matching/
└── tests/
    ├── test.sh
    └── test_product_matching.py
```

- `instruction.md`：参评 Agent 的完整题面和验收规则。
- `environment/starter/`：构建到 `/app` 的初始工程；三个目标模块保留待实现接口。
- `solution/solve.sh`：Oracle 使用的标准解安装脚本。
- `tests/test.sh`：验证器入口，成功写入 `/logs/verifier/reward.txt` 的值为 `1`，失败写入 `0`。

## 运行约束

- 目标环境：Linux、Python 3.12。
- 运行时禁止网络访问。
- 只允许使用 Python 标准库，不安装第三方依赖。
- 任务自带 `models.py`、`taxonomy.py` 和 `data/taxonomy.json`，运行时不读取任务目录外文件。
- 资源限制：1 CPU、1024 MB 内存、2048 MB 存储。

## Harbor 验证

在任务目录中运行：

```bash
harbor run -p . -a "<agent>" -m "<model>"
```

Oracle 与基线验证：

```bash
harbor run -p . -a oracle
harbor run -p . -a nop
```

预期结果：Oracle 获得 `reward=1`，未实现 starter 的 nop 基线获得 `reward=0`。当前验证器包含
62 个单元测试，覆盖题面列出的 taxonomy 别名、单位换算、enum、候选剪枝、硬冲突、缺失维度
权重重算、阈值、complete-link、SKU 签名、缺失属性隔离、报价去重、价格聚合和稳定 ID。

`task.toml` 声明了 `network_mode = "no-network"`。Harbor 0.21.0 的 Windows Docker provider
不能执行该网络策略；在 Windows 主机上请通过 WSL/Linux 环境运行，或使用支持
`no-network` 的 Harbor provider。Windows 终端读取中文文件时可先设置 `PYTHONUTF8=1`。
