# 排障指南

## 1. 启动失败：缺少必要配置

示例与 `shijiajing-eval --live` 打印 `缺少必要配置：SHIJIAJING_XXX, ...` 后退出码 2；
`make_deps` 抛 `ValueError("缺少必要配置：...")`。

处理：复制根目录 `.env.example` 为 `.env`（或 export 环境变量），逐项补齐缺失项。
外部资源（Key/模型 ID/Milvus 地址/路径）没有代码默认值——缺失即失败是设计行为
（方案 §13），不是 bug。

常见组合：

- 只想用本地词法降级跑通：补 `SHIJIAJING_TAXONOMY_PATH`（或使用包内置）
  + `SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH` + 模型三件套（Key/BaseURL/Text 模型）+ checkpoint DSN。
- 完整检索：再补 `SHIJIAJING_MILVUS_URI/TOKEN/COLLECTION` 与 `SHIJIAJING_EMBEDDING_MODEL`。

## 2. 检索问题

| 现象 | 原因与处理 |
|---|---|
| 响应 notice 含"本地词法降级" | Milvus 不可用（超时/连接失败/TLS/网络），已自动降级；检查 `MILVUS_URI` 可达性，`RETRIEVAL_TIMEOUT_SECONDS` 是否过短 |
| `本地商品快照不可用` | `LOCAL_PRODUCT_SNAPSHOT_PATH` 路径不存在或解析失败；确认 JSONL 每行是合法 Offer（`python -c "import json;[json.loads(l) for l in open(p,encoding='utf-8')]"`） |
| 检索结果为空但快照有数据 | 硬过滤过严（预算/平台/评分约束无命中属正常）；观察 `fallback_used` 与 trace 中的过滤条件 |
| 初始化/索引报"集合已存在" | `shijiajing-init-milvus --drop` 显式重建（会丢数据，谨慎）；索引用 `shijiajing-index-products` 重灌 |

## 3. 模型输出问题

| 现象 | 处理 |
|---|---|
| 结构化输出校验失败后自动重试 | 属于正常修复循环（`MAX_MODEL_REPAIRS=2`）；次数耗尽 → 规则/模板降级，响应 notice 标注 |
| 意图解析结果不对 | 确认用的是文本模型而非 VLM；检查 `SHIJIAJING_ARK_TEXT_MODEL` 是否支持 JSON 输出 |
| 解释数字与证据不符 | `FactualConsistencyChecker` 会拒发并触发重试；降级为模板解释并标记 `explanation_verified=False` |
| 响应 FAILED + 模型错误 | 检查 trace（structlog）中的模型调用事件与 HTTP 错误；确认 Key/模型 ID 有效、配额未超限 |

## 4. 会话/Checkpoint 问题

| 现象 | 处理 |
|---|---|
| `SessionConflictError` | 同会话并发请求冲突；幂等重放一次后仍冲突，说明确有并发，应用层应串行 |
| `CheckpointUnavailableError` | `CHECKPOINT_DSN` 不可写（sqlite 目录不存在 / postgres 不可达）；运行 preflight 检查连接和 DDL |
| HITL 恢复状态丢失 | `start/resume` 必须使用相同 `session_id`，并确认活动 Supervisor namespace 仍存在 |
| 数据库文件被多个进程写 | sqlite 适合单实例开发；生产用 postgres 后端 |

## 5. 修正不生效

- `RecognitionCorrection.recognition_id` 必须等于当前会话**最新**识别结果 ID；
用旧轮次的 ID 会被拒绝。
- 修正轮不携带图片，`text` 可为空；修正只更新显式提供的字段。
- 验证：正常时 trace 中修正轮 **没有** `recognize_image` 调用（修正后不调 VLM）。

## 6. 输出乱码（Windows 控制台）

Windows 默认 GBK 控制台打印 ✅/中文会报 `UnicodeEncodeError`。CLI 已自动
reconfigure 为 UTF-8；若重定向或旧终端仍乱码：

```bash
# PowerShell
$env:PYTHONIOENCODING="utf-8"
# CMD
set PYTHONIOENCODING=utf-8
```

## 7. 评测门禁不通过

- 看 `reports/eval_report.md`：区分"未达标"与"未测量（pending）"；阻断指标
  pending 也判不通过。
- 数据集变更（商品/价格/标注）后需重新 `--frozen`；旧冻结报告摘要对不上即失效。
- 种子数据集无法通过 → 检查 `same_item_pairs` 是否与领域判定一致
  （标题相似度/属性冲突决定判定，见 docs/evaluation.md）。

## 8. 观察手段

- trace：`SHIJIAJING_TRACE_BACKEND=structlog`，事件含 request_id、节点、耗时、
  降级标记；日志不含密钥与隐藏思维链（方案 §11.3）。
- OpenTelemetry：将 `SHIJIAJING_TRACE_BACKEND` 设为 `opentelemetry`，并填写
  `SHIJIAJING_TRACE_DSN`；导出失败不阻断业务，但会增加 `trace_sink_failure_total`。
- 指标：`PrometheusMetrics` 暴露模型调用/检索降级/修复/延迟计数。
- 测试：`uv run pytest -q`（离线单测）；`-m integration` 需要真实外部资源。

## 9. 二期存储与回滚

- 持久化检查：`uv run shijiajing-preflight --storage-only --json`。
- 事件修复：先运行 `uv run shijiajing-repair-events --dry-run`，确认缺失集合后才允许
  `--apply`；事件追加失败不回滚 Request Ledger 或 Memory 已成功的事务。
- 部署回滚前必须确认没有 `active_interrupt`；存在中断时先 resume 或人工确认清理。
- SQLite 备份、PostgreSQL dump/restore 和完整回滚顺序见
  [operations_phase2.md](operations_phase2.md)。
