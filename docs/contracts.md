# 数据契约

公共数据模型位于 `src/shijiajing_agent/contracts.py`；主/子 Agent 内部动作位于
`src/shijiajing_agent/agent_runtime/contracts.py`；RAG 查询和索引身份位于
`src/shijiajing_agent/rag_contracts.py`。Pydantic 模型默认 `extra="forbid"`，未知字段不能
跨越模型、运行时或持久化边界。

## 1. 请求与响应

- `AgentRequest`：文本、图片或识别修正至少提供一种，并携带稳定的 `session_id`、`request_id`。
- `AgentResponse`：返回状态、识别结果、有效约束、比价组和 notices。
- `AgentExecutionContext`：携带可信 Memory owner 与执行上下文；owner 不能由用户输入指定。
- `AgentInterrupt` / `AgentResume`：按中断类型使用独立 payload，恢复前校验 session、turn、
  constraints/evidence 版本和中断身份。

## 2. 商品、约束与 RAG

- `ShoppingConstraints`：当前购物目标的规范事实；用户明确约束优先，来源、置信度和锁定状态
  保留，未知开放属性不能因缺少静态 taxonomy ID 被丢弃。
- `Offer`：索引与比较的最小商品报价单元，保留 `RawAttribute`、作用范围、来源版本、
  `record_kind` 和 `price_basis`。商品概要不能伪装成真实 SKU 报价。
- `RetrievalCandidate` / `NormalizedCandidate` / `SkuGroup` / `RankedGroup`：召回、动态归一化、
  同款聚类、SKU 拆分和排序结果。
- `PreparedQuery`：服务端重建 hard filters，并绑定 `constraints_version`、图片哈希、查询
  指纹和 `index_manifest_id`；补查文本不能再次触发 query rewrite。
- `AgentRuntimeUsage`：区分逻辑 `retrieval_calls`、物理 `db_search_attempts`、
  `embedding_calls` 与模型/token 用量。
- `IndexManifest`：声明快照、文本生成、tokenizer、embedding、维度、距离和有效行数；
  `manifest_id` 是发布身份。

用户硬约束始终进入检索后资格校验。检索前可下推的过滤仍必须在候选上复核；`unknown` 不等于
满足，未满足硬要求的 Offer 不能进入确认推荐或最低价聚合。

## 3. 主/子 Agent 动作

`MainAction` 是带 discriminator 的有限联合：

- `search_and_compare`、`supplement_search`、`inspect_evidence`；
- `delegate_research`、`delegate_verification`；
- `ask_user`、`answer`、`finish_no_results`。

主模型只提出动作参数。运行时补齐并校验权限、版本、硬约束、证据、预算、索引身份和结果
引用；不能传入任意函数、URL、授权令牌或新的硬条件。

`SubagentTask` 接收冻结约束、有限候选/证据引用、明确目标和子预算。`SubagentResult` 的
每个事实必须引用已登记的 `evidence_id`；父 runtime 重新检查后才可归并，子 Agent 不能写
主状态或长期 Memory。

## 4. 状态、幂等与恢复

- `MainRuntimeState` 是当前 turn 的规范状态，`RuntimeSessionSnapshot` 保存有界会话摘要；
  当前请求和会话使用 `agent-runtime-v2` namespace。
- `constraints_version` 变化后，旧查询、旧子结果和旧证据不能直接归并。
- `ActionRecord` 记录动作 fingerprint、状态、版本、结果引用、预留/结算用量和错误码。
- Request Ledger 使用 `(session_id, request_id)` 幂等；不同响应不能静默覆盖同一键。
- 已提交查询/动作恢复后可复用；执行中断且未提交的只读动作只允许在剩余预算内有限重跑。
- 旧 Supervisor/DAG checkpoint 不转换为主 runtime；无法匹配的新恢复请求必须明确要求新会话。

## 5. 持久化安全

- Checkpoint、Event Store、Trace 和 Cache 只保存白名单字段、ID、哈希、版本、计数、状态和
  降级标记；不保存用户全文、图片 data URL、Prompt、密钥、模型原始响应或隐藏推理过程。
- serializer 只允许显式契约类型；来源文本中的指令不改变工具权限。
- Memory commit 需要 runtime 绑定的 mutation 集合、payload hash 和用户确认；恢复重放必须幂等。

## 6. 固定错误语义

模型或外部服务异常可以触发明确的 fallback，但不能把降级结果标记为原服务成功；全通道不可用
与真实空结果分开。不可恢复的动作以 `FAILED` 结束，并保留已验证结果和可操作 notice。
