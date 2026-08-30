# 架构说明

识价镜 Agent 是一个可恢复的层级式 Multi-Agent：Supervisor 生成并校验类型化任务 DAG，
再调度 Recognition、Intent、Retrieval、Explanation、Memory 五类 Specialist Agent。

## 1. 分层

```text
src/shijiajing_agent/
├── contracts.py       跨层 Pydantic 契约
├── state.py           SupervisorState 与任务结果 reducer
├── facade.py          幂等、会话串行、超时和 Supervisor 生命周期
├── multi_agent/       Planner、Supervisor、Agent registry、任务派发与 Checkpoint
├── domain/            约束、归一化、同款、SKU、排序和证据等纯领域逻辑
├── ports/             外部能力 Protocol
├── adapters/          Ark、检索、Memory、Cache、Event、Trace 等端口实现
├── prompts/           带版本的模型 Prompt
├── tools/             评测、索引、运维和发布 CLI
└── data/              taxonomy 与评测种子数据
```

依赖方向为 `multi_agent → domain + ports`、`adapters → ports + domain`；`domain` 不依赖
适配器。Specialist Agent 只能取得任务私有输入，不能直接修改 `SupervisorState`。

## 2. 执行结构

```text
请求 → Supervisor 创建并校验 ExecutionPlan
     ├→ Recognition Agent ─┐
     ├→ Intent Agent ──────┼→ Retrieval Agent → Explanation Agent
     └→ Memory Agent ──────┘                         │
                       Supervisor 汇合类型化结果 ←───┘
                                      ↓
                                  最终响应 / HITL
```

- `DeterministicPlanner` 提供确定性基线计划；模型 Planner 只能提出 allowlist 内的结构化建议。
- `PlanValidator` 校验任务类型、DAG、预算与依赖；非法建议回退到确定性计划。
- Supervisor 只派发依赖已完成的 ready tasks，并按 barrier 汇合结果。
- Retrieval Agent 内部复用确定性归一化、同款匹配、SKU 拆分、价格聚合和排序算法。
- Memory commit 必须获得 Supervisor 对当前 mutation 集合的显式授权。

## 3. 状态与恢复

- `request_id` 通过 Request Ledger 保证结果幂等。
- Facade 对同一 `session_id` 串行执行。
- Supervisor 与每个任务使用独立 Checkpoint namespace；重放时跳过已完成任务。
- HITL 中断保存活动计划和任务结果，`resume` 校验中断信息后继续执行。
- Checkpoint serializer 在写入前移除用户全文、图片内容和自由 metadata。

## 4. 外部端口

| 端口 | 主要实现 | 用途 |
|---|---|---|
| `VisionModelPort` | `ArkVisionModel` | 图片识别 |
| `IntentModelPort` | `ArkIntentModel` | 意图提取 |
| `QueryRewritePort` | `ArkQueryRewrite` | 查询改写 |
| `ExplanationModelPort` | `ArkExplanationModel` | 证据约束解释 |
| `ProductRetrievalPort` | Milvus / 本地词法适配器 | 商品召回 |
| `MemoryPort` | SQLite / PostgreSQL | 长期记忆 |
| `RequestLedgerPort` | SQLite / PostgreSQL | 请求结果幂等 |
| `TraceSinkPort` / `MetricsPort` | Structlog / OpenTelemetry / Prometheus | 可观测性 |

模型或检索降级必须返回明确状态，不得把规则、模板或本地词法结果伪装成原服务结果。

## 5. 相关文档

- [Multi-Agent 执行](multi_agent.md)
- [数据契约](contracts.md)
- [商品归一化](product_canonicalization.md)
- [配置](configuration.md)
- [评测](evaluation.md)
- [故障排查](troubleshooting.md)
