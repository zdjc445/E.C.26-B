# 架构说明

识价镜 Agent 保留旧的可恢复 Workflow 作为基线，同时提供一个可回滚的主 Agent runtime。
新 runtime 由一个主 Agent 维护购物目标，普通检索/比较通过共享服务完成；只有复杂且有可补证
能力的缺口才按需启动一个受限 subagent。默认 `execution_mode=workflow`，不会因为升级自动
切换生产引擎。

## 1. 分层

```text
src/shijiajing_agent/
├── contracts.py       跨层 Pydantic 契约
├── state.py           SupervisorState 与任务结果 reducer
├── facade.py          幂等、会话串行、超时和 Supervisor 生命周期
├── multi_agent/       Planner、Supervisor、Agent registry、任务派发与 Checkpoint
│   └── agents/
│       ├── recognition.py   图片识别与修正
│       ├── intent.py        意图和购物约束抽取
│       ├── retrieval.py     召回、归一化、同款、SKU 与排序
│       ├── explanation.py   证据约束解释
│       └── memory.py        长期记忆召回与受控写入
├── agent_runtime/     主 Agent observe → decide → act 循环与按需 subagent
│   └── subagents/
│       ├── research.py       复杂检索缺口补查
│       └── verification.py   可选详情证据核验
├── domain/            约束、归一化、同款、SKU、排序和证据等纯领域逻辑
├── ports/             外部能力 Protocol
├── adapters/          Ark、检索、Memory、Cache、Event、Trace 等端口实现
├── prompts/           带版本的模型 Prompt
├── tools/             评测、索引、运维和发布 CLI
└── data/              taxonomy 与评测种子数据
```

依赖方向为 `multi_agent/agent_runtime → services + domain + ports`、`adapters → ports + domain`；
`domain` 不依赖适配器。主 Agent 只提出动作，运行时负责权限、预算、版本、证据、Checkpoint
与副作用授权；subagent 只能取得冻结约束和有限证据，不能直接修改主状态或长期记忆。

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

### 2.1 新主 Agent runtime

```text
请求/恢复 → 准备会话上下文 → 主 Agent 观察
                         ↓ 一个动作
              ActionGuard + 预算 + 版本校验
                 ├─ 普通服务工具
                 ├─ Research（仅复杂检索缺口）
                 ├─ Verification（仅有详情端口）
                 ├─ HITL / answer / no_results
                 └─ 确定性降级
                         ↓
                 结果校验 → Checkpoint → 下一轮观察
```

`main` 模式只开放普通工具，作为单 Agent 对照组；`main_with_subagents` 才开放按需委派。
一次请求始终只有一个主 Agent，V1 同时最多运行一个 subagent；不另设第二个 LLM Supervisor。
`MainAction`、`SubagentTask/Result` 使用独立严格契约，商品文本和 subagent 输出均按不可信数据处理。

## 3. 状态与恢复

- `request_id` 通过 Request Ledger 保证结果幂等。
- Facade 对同一 `session_id` 串行执行。
- Supervisor 与每个任务使用独立 Checkpoint namespace；重放时跳过已完成任务。
- HITL 中断保存活动计划和任务结果，`resume` 校验中断信息后继续执行。
- Checkpoint serializer 在写入前移除用户全文、图片内容和自由 metadata。
- 新 runtime 使用 `agent-runtime-v1/{session}/{request}/main`，子任务约定使用
  `.../subagents/{task_id}`，会话上下文另存为 `.../{session}/session`。
- 会话快照保存规范约束、商品主题、识别摘要和有限结构化轮次摘要；不会用长期 Memory
  代替会话上下文。活动 interrupt 完成后清理 active marker。

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
| `AgentDecisionPort` | Ark 严格 JSON 适配器或 Fake | 主 Agent 每轮选择一个动作 |
| `SubagentDecisionPort` | Ark 严格 JSON 适配器或 Fake | 受限 Research/Verification 动作 |
| `OfferDetailPort` | 可选离线/生产详情实现 | 核验补充证据；未装配时能力关闭 |

模型或检索降级必须返回明确状态，不得把规则、模板或本地词法结果伪装成原服务结果。

## 5. 相关文档

- [Multi-Agent 执行](multi_agent.md)
- [主 Agent 与按需 subagent 设计及实施记录](plans/main_agent_on_demand_subagents_design.md)
- [数据契约](contracts.md)
- [商品归一化](product_canonicalization.md)
- [配置](configuration.md)
- [评测](evaluation.md)
- [故障排查](troubleshooting.md)
