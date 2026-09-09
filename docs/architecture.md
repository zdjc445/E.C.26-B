# 架构说明

生产只有一条执行链：`AgentFacade → MainAgentRuntime`。主 Agent 维护当前购物目标，
普通请求可以不委派；只有检索缺口或详情争议满足准入条件时，才在同一个 runtime 内启动
受限 Research/Verification subagent。

## 1. 分层

```text
src/shijiajing_agent/
├── contracts.py       公共请求、商品、约束、记忆和响应契约
├── agent_runtime/     主 Agent observe → decide → act、子 Agent、预算和 checkpoint
├── services/          识别、意图、检索、比较、证据、回答和记忆服务
├── domain/            约束、动态 Schema、同款、SKU、排序和过滤等纯逻辑
├── ports/             模型、检索、存储和可观测性 Protocol
├── adapters/          Ark、Milvus/本地快照、百炼 Reranker、Memory、Cache、Event、Trace
├── prompts/           带版本的模型 Prompt
└── tools/             评测、索引、运维和发布 CLI
```

`domain` 不依赖适配器；`services` 组合端口和领域逻辑；`agent_runtime` 是规范状态的唯一
写入者。模型只能提出严格动作或 proposal，不能直接创建商品组、修改硬约束或写长期记忆。

## 2. 执行结构

```text
请求/恢复 → 准备识别、意图和记忆上下文 → 主 Agent 观察
                                      ↓ 一个动作
                         权限 + 版本 + 预算校验
             ┌────────────────────────┼──────────────────────┐
             │                        │                      │
        检索/比较                 Research                Verification
        证据读取                  按需补查                 详情核验（可选）
             └────────────────────────┼──────────────────────┘
                                      ↓
                       结果/证据校验 → checkpoint → 再观察
                                      ↓
                           追问 / 回答 / 无结果
```

固定动作目录位于 `agent_runtime/contracts.py`，包括检索比较、补查、证据读取、两种委派、
追问、回答和无结果结束。补查和 Research 共享当前约束版本、查询指纹、检索预算和召回池；
不允许递归委派或自由网络搜索。

商品处理的固定顺序是：原始 Offer 保真 → 单一 raw search text → 有界混合召回 → 固定 RRF Top 200
→ 云端 Reranker → 商品多样性窗口 Top 60 → 动态局部 Schema/通用基线 → 需求三态资格校验
→ 同款 Complete-Link → SKU 拆分 → 价格排序 → 证据回答。
未满足硬要求或证据未知的候选不会进入确认推荐。

## 3. 状态、版本与恢复

- `MainRuntimeState` 是当前 turn 的规范状态；`RuntimeSessionSnapshot` 保存有界会话摘要。
- `constraints_version`、`evidence_version` 和索引 manifest 身份绑定动作、查询和子结果。
- `AgentRuntimeUsage` 区分逻辑 `retrieval_calls`、物理 `db_search_attempts`、`embedding_calls` 和
  `reranker_requests`；批量动作执行前预留剩余额度，结算后按真实用量释放。
- 当前请求和会话使用 `agent-runtime-v2` namespace。已提交动作/查询可复用；旧 Supervisor/DAG
  checkpoint 不转换为新状态，无法匹配的新恢复请求必须重新开始会话。
- Checkpoint 写入前脱敏；不保存用户全文、图片 data URL、Prompt、模型原始响应或自由 metadata。

## 4. 外部端口

| 端口 | 主要实现 | 用途 |
|---|---|---|
| `VisionModelPort` / `IntentModelPort` | Ark | 识别和意图 patch |
| `QueryRewritePort` | Ark | 一次生成有界查询计划 |
| `AgentDecisionPort` / `SubagentDecisionPort` | Ark 或 Fake | 主/子 Agent 严格动作 |
| `ProductRetrievalPort` | Milvus / 本地快照 | 混合召回与明确降级 |
| `RerankerPort` | 阿里云百炼 / 开发 Fake | RRF 后全量候选精排与 RRF 回退 |
| `DynamicSchemaInductionPort` | Ark | 请求级局部 Schema |
| `MemoryPort` / `RequestLedgerPort` | SQLite / PostgreSQL | 记忆与幂等 |
| `TraceSinkPort` / `MetricsPort` | structlog / OTLP / Prometheus | 诊断与计量 |

详情核验需要实际装配 `OfferDetailPort`；没有该端口时不会暴露 Verification 动作，也不会
把 Research 结果伪装成详情核验。

## 5. 相关文档

- [主/子 Agent 收敛方案](plans/subagent_only_architecture_design.md)
- [SKU Offer 与按需补召回](plans/sku_offer_rag_on_demand_retrieval_design.md)
- [索引迁移与验收](operations/rag_migration.md)
- [数据契约](contracts.md)
- [配置](configuration.md)
- [评测](evaluation.md)
