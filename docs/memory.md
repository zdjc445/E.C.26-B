# 记忆模块完整设计

> 文档状态：目标设计（Target Design）
>
> 适用范围：native workflow、受控 Multi-Agent、SQLite/PostgreSQL Memory adapter
>
> 实施原则：本文定义目标行为、迁移顺序和验收门禁，不代表当前代码已经全部满足。

## 1. 设计结论

系统采用三层上下文模型，但三层的职责必须严格区分：

| 层次 | 事实源 | 生命周期 | 作用 |
|---|---|---|---|
| 本轮执行状态 | `AgentState` | 单 turn；Checkpoint 支持中断恢复 | 保存识别、意图、候选、任务状态和副作用控制，不作为用户画像 |
| 会话上下文 | `effective_constraints` + bounded `recent_turns` | 同一 `session_id` | 延续当前购物任务、解析指代和修正，不跨 session |
| 长期用户记忆 | `MemoryPort` | 跨 session，按 owner/scope 持久化 | 保存用户明确要求记住的偏好，并以可审计、可覆盖、可遗忘的方式参与后续请求 |

`recent_turns` 不能只写入 Checkpoint 而没有消费者；长期 Memory 也不能只是可存取的数据库表。
完整记忆能力必须打通以下闭环：

```text
用户明确表达记忆意图
  → Intent 提出 directive candidate
  → 确定性策略验证显式触发、键、值、作用域和 apply_mode
  → 生成稳定 mutation
  → 可选 HITL 授权
  → 事务提交
  → 新 session 按当前品类召回
  → 按模式应用到约束、排序或负向偏好
  → 记录实际应用结果并进入端到端评测
```

## 2. 目标与非目标

### 2.1 目标

- 普通购物条件与长期记忆写入严格分离；“预算 1000 元”只影响当前任务，只有“以后买耳机预算记为 1000 元”等明确表达才产生长期变更。
- 当前轮显式输入永远优先于会话历史和长期记忆。
- 品类记忆只能作用于相同品类，不能因上一轮品类残留而跨品类污染。
- `CONSTRAINT_DEFAULT`、`RANKING_PRIOR`、`NEGATIVE_PREFERENCE` 有不同且可测试的业务语义。
- SQLite 与 PostgreSQL 在隔离、幂等、覆盖、遗忘、并发和失败语义上保持一致。
- HITL 恢复、请求重放和任务重试不能重复提交 mutation。
- 不在日志、Trace、Event 或 Prompt 记录中泄露 owner、记忆值或原始用户文本。

### 2.2 非目标

- 不允许模型根据浏览行为、点击、图片或普通对话自动构造用户画像。
- 不保存完整聊天记录、模型思维链、图片内容、支付信息、地址或其他敏感自由文本。
- 不用长期记忆直接生成硬过滤，除非该记录的 `apply_mode` 明确为 `CONSTRAINT_DEFAULT` 且字段白名单允许。
- 不把 Checkpoint 当作跨用户长期记忆数据库。
- 不以 SQLite 单连接实现宣称生产级多实例扩展；生产多实例使用 PostgreSQL。

## 3. 核心不变量

以下规则属于发布阻断条件：

1. owner A 的任何长期记忆不能被 owner B 读取、修改、确认或删除。
2. 当前品类为 B 时，`category:A` 的记录不得进入 `MemoryApplication`。
3. 没有显式记忆触发语句时，`pending_memory_mutations` 必须为空。
4. 同一 `mutation_id` 重放只能产生一次业务副作用；相同 ID 不同 payload 必须报冲突。
5. 当前轮用户值、用户修正和已锁定会话值不能被长期记忆覆盖。
6. `RANKING_PRIOR` 不得进入硬过滤；`NEGATIVE_PREFERENCE` 默认不得造成零结果。
7. HITL 拒绝后不得提交；批准后的重复 resume 不得重复提交。
8. recall/commit 失败时不能向用户声称“已记住”或“已忘记”。
9. `FORGET` 后记录不再参与 recall；物理清除必须使用独立的 `PURGE_OWNER` 管理流程。
10. 新 turn 不得复用上一轮候选、响应、pending mutation 或本轮 Memory 应用结果。

## 4. 总体流程

### 4.1 Workflow 目标拓扑

```text
START
  → validate_input
  → load_session
  → prepare_subject
  ├─ recognition
  └─ intent（约束 patch + 未授权 memory directive candidates）
  → join_understanding
  → merge_current_turn_context      # 不应用长期 Memory，先解析当前品类
  → build_memory_query              # 只使用当前已解析品类
  → recall_memory
  → resolve_memory_application      # scope 去重 + apply_mode 分流
  → apply_constraint_defaults
  → validate_constraints
  → retrieve / compare / rank        # 显式接收 ranking priors / negative preferences
  → build_response
  → prepare_memory_mutations
  → [memory_confirmation]
  → commit_memory
  → append_turn_summary
  → END
```

关键顺序：

- 当前品类必须在 recall 之前解析完成。
- recall 不能读取上一轮 `effective_constraints.category_id` 作为当前品类。
- mutation 可以在 Intent 阶段提出，但只能在业务响应构建后、授权检查通过后提交。
- 用户当前轮明确表达的预算、平台等仍应参与本轮检索；长期写入是否成功不能改变本轮已解析意图。

### 4.2 Multi-Agent 目标拓扑

Supervisor 的 DAG 使用同一领域策略，不允许 MemoryAgent 自行构造空查询：

```text
Recognition ─┐
             ├→ UnderstandingMerge → MemoryRecall → Retrieval → Explanation
Intent ──────┘                                  └→ MemoryPrepare
Explanation + MemoryPrepare → BuildResponse → [MemoryConfirmation] → MemoryCommit
```

- `MemoryRecall` 输入必须包含确定性合并后的 `category_id` 和显式 `MemoryQuery`。
- `MemoryPrepare` 只接收已经通过显式触发校验的 directives。
- `MemoryCommit` 的授权由 Supervisor 在确认决策后生成，不能由 Planner 预填一个非空字符串代替。
- shadow 模式跳过 Memory commit，且不得复用生产授权。

## 5. 第一层：本轮执行状态

`AgentState` 是工作流执行状态，不等同于用户记忆。它包含：

- 当前请求、识别结果、意图 patch、有效约束；
- 检索查询、候选、SPU/SKU、排序和解释；
- 任务结果、重试计数、interrupt、resume 历史；
- 本轮 `memory_context`、`memory_application` 和 `pending_memory_mutations`。

新 turn 必须重置：

- `intent_patch`、`memory_context`、`memory_application`、`pending_memory_mutations`；
- 查询、候选、匹配、排序、解释、响应；
- 本轮错误、事件、retry、interrupt 和 Agent task 结果。

同一 turn 的 Checkpoint 恢复可以恢复上述字段；跨 turn 只能保留会话事实源，不能把本轮候选或 mutation 当作历史继续执行。

## 6. 第二层：会话上下文

### 6.1 权威状态

`effective_constraints` 是同一购物任务内的权威会话状态，负责延续预算、平台、品类和筛选条件。
`recent_turns` 是有界的结构化上下文，只用于：

- 解析“刚才那个”“上一款”“还是按之前预算”等指代；
- 支持撤销、修正和澄清恢复；
- 防止终态摘要重复追加；
- 为解释提供最近选择的 group ID，而不是复制完整结果。

约束合并不能从 `recent_turns` 重放全部历史；它仍以 `effective_constraints` 为事实源。

### 6.2 `ConversationTurnSummary` 目标字段

```text
request_id / turn_id / subject_id
category_id
constraint_delta             # 白名单结构化字段，不含自由文本
selected_group_ids
completion_reason
memory_effects               # mutation_id + operation + status，不含 value
user_text_sha256 / user_text_length
created_at
```

- 不保存原始 `user_text`。
- 不保存模型原始输出和 Prompt。
- `recent_turns` 同时受 `RECENT_TURNS_LIMIT` 和序列化字节上限约束。
- Intent 输入只接收最小投影；模型仍只能输出当前轮 patch，禁止复制历史约束。
- 规则解析失败时，最近摘要不能被当作长期写入证据。

### 6.3 会话终止

- 新 `session_id` 不继承 `effective_constraints` 或 `recent_turns`。
- 长期 Memory 是否启用不影响会话上下文。
- 用户主动“开始新的商品”时保留 recent 摘要用于指代，但按现有 subject 规则重置不再适用的商品约束。

## 7. 第三层：长期用户记忆

### 7.1 数据边界

长期 Memory 只允许以下信息：

| `memory_key` | 合法值 | 允许的 `apply_mode` |
|---|---|---|
| `max_price` / `min_price` / `min_rating` | 有限非负数字；评分 `0..5` | `CONSTRAINT_DEFAULT` |
| `platforms` / `colors` | 规范化非空字符串列表 | `CONSTRAINT_DEFAULT` 或 `RANKING_PRIOR` |
| `sort_by` | `SortBy` 枚举 | `CONSTRAINT_DEFAULT` |
| `preferences` | `Preference` 枚举列表，最多 10 项 | `RANKING_PRIOR` |
| `negative_terms` | 规范化非空字符串列表 | `NEGATIVE_PREFERENCE` |

键和值通过白名单只是第一步；键与 `apply_mode` 的组合也必须通过矩阵校验。

### 7.2 写入必须来自明确表达

支持的意图类别：

- UPSERT：`记住我以后买耳机预算不超过 1000 元`。
- FORGET：`忘掉我的耳机预算`、`以后不要记这个平台偏好`。
- CLEAR_OWNER：`清空我保存的所有购物偏好`。

反例：

- `预算 1000 元`：只修改当前轮约束。
- `给我看看京东的`：只修改当前轮平台。
- 从点击、排序选择或模型推断出的“似乎喜欢低价”：不得写入。

Intent 模型输出的 directive 只是 candidate。确定性策略必须使用当前原文再次验证显式触发词、操作、字段和值；无法验证时丢弃 candidate，并保留普通意图 patch。

### 7.3 Intent 输出契约

Intent Prompt 必须列出 `memory_directives` 的完整 JSON 结构、枚举和值域，并明确：

- 没有“记住、以后默认、忘掉、清空偏好”等显式表达时必须输出空数组；
- 普通约束不得转换为长期 directive；
- 模型不得生成 taxonomy 之外的 category scope；
- 模型不得输出自由键或敏感字段。

规则降级解析器至少覆盖 UPSERT/FORGET/CLEAR_OWNER 的固定显式表达。模型路径和规则路径使用同一 `validate_directive()`，不能只有测试代码可以手工构造合法 directive。

### 7.4 作用域解析

长期记忆只支持：

- `global`：用户明确表达“所有商品、以后都、全局默认”。
- `category:<category_id>`：用户明确提到品类，或在当前品类明确后表达“以后买这类商品时”。

规则：

1. 显式 category 优先于当前 subject。
2. 没有全局语义时不得自动扩大到 `global`。
3. 无法确定 category 且没有明确 global 语义时，发起澄清或不写入。
4. `CLEAR_OWNER` 只能使用 `global`，且不能携带 key/value/apply_mode。
5. scope 在服务端解析并通过 taxonomy 校验；不能信任模型或客户端直接提供的任意字符串。

## 8. 召回与应用

### 8.1 查询构造

`build_memory_query()` 的输入必须是当前轮初步合并后的 `base_constraints`：

```text
scope_keys = ["global"]
if current_category_id is not None:
    scope_keys.prepend(f"category:{current_category_id}")
```

禁止：

- 使用上一轮品类构造当前查询；
- 在 Multi-Agent 中用 `{}` 构造固定 global 查询；
- 召回后不检查 record scope 就直接应用。

### 8.2 确定性优先级

同一字段的优先级为：

```text
当前轮用户显式输入/修正
  > 已锁定会话约束
  > 当前图片/当前任务已经明确的值
  > category 级长期默认
  > global 长期默认
  > 空值
```

- category 与 global 同 key 同时存在时，category 永远优先，与 `updated_at` 无关。
- 只有目标字段为 `None` 时才能应用 `CONSTRAINT_DEFAULT`。
- 长期默认写入 `ConstraintSource.MEMORY_EXPLICIT`，但 `locked_by_user=false`，允许当前轮用户覆盖。
- 召回 limit 在 scope 去重后应用，不能因为按更新时间截断而丢失 category 优先记录。

### 8.3 模式分流

领域层生成类型化的 `MemoryApplication`：

```text
constraint_defaults
ranking_priors
negative_preferences
applied_memory_ids
ignored_records[{memory_id, reason_code}]
```

三种模式的行为：

- `CONSTRAINT_DEFAULT`：只填充空约束；可以影响查询和硬过滤，但不能覆盖当前用户值。
- `RANKING_PRIOR`：不修改 `ShoppingConstraints` 和 `HardFilters`；只进入确定性 reranker 的加分项。
- `NEGATIVE_PREFERENCE`：只进入软惩罚项；默认不能剔除全部候选。需要硬排除时，用户必须在当前轮明确提出。

`build_ranking_priors()` 必须有生产调用方；禁止保留未接入执行链的死接口。

### 8.4 排序接口

Retrieval/Ranking 输入增加类型化字段：

```text
ranking_context.memory_priors
ranking_context.memory_negative_terms
ranking_context.applied_memory_ids
```

排序必须记录每个 prior 是否命中候选，但 Event/Trace 只输出数量和规则版本，不输出具体用户值。

## 9. Mutation、授权与生命周期

### 9.1 稳定标识

- `memory_id = sha256(owner | scope_key | memory_key)`。
- `mutation_id = sha256(owner | session_id | request_id | directive_index | operation | scope_key | memory_key)`。
- canonical payload 单独计算 `payload_hash`；同 mutation ID 不同 payload 必须报 `MemoryConflictError`。
- mutation ID 不使用随机 UUID，保证 checkpoint replay 和任务重试稳定。

### 9.2 状态机

```text
candidate
  → validated
  → pending_confirmation | authorized
  → committed | rejected | failed
```

- candidate/validated 不产生数据库副作用。
- reject 清空 pending mutation，并把拒绝结果写入会话摘要。
- failed 不得写成功 notice；同一稳定 mutation 可以安全重试。
- committed 后才能追加 `memory_committed` / `memory_forgotten` 事件。

### 9.3 HITL

- `SHIJIAJING_MEMORY_CONFIRMATION_REQUIRED=true` 时，UPSERT/FORGET/CLEAR_OWNER 都需要确认。
- `CLEAR_OWNER` 始终需要确认，即使普通 UPSERT 的二次确认被关闭。
- confirmation 应位于业务响应已经构建、Memory commit 尚未发生的位置；恢复后复用已完成任务，不重新识别、检索或解释。
- interrupt payload 展示规范化变更 diff；Checkpoint 可以保存该结构，但日志和 Event 不输出 value。
- Supervisor 在 approve 后生成与 `interrupt_id + mutation_ids + payload_hashes` 绑定的授权；Planner 不能预先生成授权。
- MemoryAgent 必须校验授权与当前 pending mutations 完全匹配。

## 10. 持久化与事务

### 10.1 `user_memory`

目标唯一键为 `(memory_owner_id, scope_key, memory_key)`，字段包括：

```text
memory_id, memory_owner_id, memory_key, scope_key
value_json, apply_mode, confidence, status
source_session_id, source_request_id
version, created_at, updated_at, expires_at
```

- UPSERT 覆盖值并递增 version。
- FORGET 把 status 改为 `forgotten` 并递增 version。
- recall 只返回 active 且未过期记录。
- `expires_at` 未设置时长期有效；后续如启用 TTL，必须由白名单策略产生，模型不能自由指定。

### 10.2 `memory_mutation`

mutation ledger 保存：

```text
mutation_id, memory_owner_id, operation, payload_hash, applied_at
```

不长期保存完整 `payload_json`。幂等冲突通过 canonical `payload_hash` 判断，避免用户执行物理清除后仍在 ledger 残留原偏好值。

### 10.3 事务语义

每批 commit：

1. 在事务外完成契约与白名单验证。
2. 开启事务并获取 owner 级串行化锁。
3. 对每个 mutation 获取稳定幂等锁并检查 ledger。
4. 应用 user_memory 变更。
5. 写入 mutation ledger。
6. 原子提交。

SQLite 使用 `BEGIN IMMEDIATE` 和进程内锁；PostgreSQL 使用事务级 advisory lock 与唯一约束。事务开启后的任何异常都必须 rollback，不能只捕获数据库异常而遗漏 JSON/模型校验等异常。

### 10.4 遗忘与物理清除

- `FORGET`：软遗忘单个 key；保留版本和审计信息，但不再 recall。
- `CLEAR_OWNER`：软遗忘 owner 的全部 active records。
- `PURGE_OWNER`：独立的受信管理操作，物理删除 `user_memory` 和含值的历史记录；不得由 LLM directive 直接触发。

对外文档必须区分“停止召回”和“物理删除”，不能把软删除描述成数据已经彻底擦除。

## 11. Owner 隔离与安全边界

- `memory_owner_id` 只能由鉴权层根据已认证 principal 生成并放入 `AgentExecutionContext`。
- 普通请求 body、query、metadata、模型输出和 session_id 都不能决定 owner。
- 建议使用不可逆的稳定映射或 HMAC 后的 opaque owner ID，避免数据库暴露业务账号。
- recall/list/update/delete 的 SQL 必须全部带 owner 条件；不能先按 memory_id 查询再在应用层判断 owner。
- resume 必须校验 session、interrupt 和原始 execution context 的 owner 一致。
- 管理端 PURGE 使用独立权限和审计通道，不复用普通 Agent 调用权限。
- owner、记忆 value、用户原文和 directive evidence 不进入 Trace/Event 标签。

该设计提供应用层 owner 隔离；只有上游鉴权与 owner 绑定完成后，才能把它表述为完整的用户安全隔离。

## 12. 失败与降级

| 失败点 | 目标行为 |
|---|---|
| directive candidate 非法 | 拒绝长期写入；普通当前轮意图仍可继续 |
| recall 失败 | 清空 `memory_context/application`，继续当前请求并提示未应用历史偏好 |
| apply 发现 scope/mode 不匹配 | 忽略记录、增加固定 reason_code 与指标，不污染约束 |
| commit 失败 | 保留业务结果，不添加成功 notice；mutation 可幂等重试 |
| Event Store 失败 | 不回滚真实 Memory 事务；通过稳定 event id 修复 |
| Checkpoint/HITL 恢复失败 | 不猜测授权，不提交 Memory |
| owner 缺失或 Memory disabled | 使用 Disabled adapter，不读不写 |
| PostgreSQL 并发冲突 | 事务回滚；稳定 mutation 重试或返回明确冲突 |

Recall 是 miss-safe 能力，Commit 是 truth-sensitive 副作用；两者不能共用“失败就静默成功”的策略。

## 13. 可观测性

建议指标：

- `memory_directive_candidate_total{operation,key,result}`
- `memory_recall_total{status}` / `memory_recall_latency_seconds`
- `memory_record_recalled_total{scope_kind}`
- `memory_application_total{apply_mode,result,reason}`
- `memory_commit_total{operation,status}`
- `memory_replay_total{result}`
- `memory_conflict_total{kind}`
- `memory_confirmation_total{decision}`
- `memory_cross_scope_rejection_total`

Event payload 只允许：

- mutation ID、operation、状态；
- recall/application 数量；
- 固定失败码、策略版本和 apply mode；
- 不包含 owner、scope 的具体 category、memory key 对应 value、用户文本或 Prompt。

## 14. 测试与评测

### 14.1 单元测试

- 普通条件不产生 directive；显式“记住/忘记/清空”正确产生候选。
- Prompt 和规则解析器覆盖同一记忆命令集合。
- key/value/apply_mode 矩阵拒绝非法组合。
- category 优先于 global，当前用户值优先于 Memory。
- 切换品类时旧 category 记录不得应用。
- ranking prior 不进入硬过滤；negative preference 不造成默认零结果。
- bounded recent turns 确实进入指代解析，但不被重放为约束或长期写入。

### 14.2 Adapter contract

SQLite/PostgreSQL 使用同一 contract：

- owner 隔离；
- UPSERT 覆盖与 version 递增；
- FORGET/CLEAR_OWNER 后 recall 为空；
- replay 无重复副作用；
- 相同 mutation ID 不同 payload 报冲突；
- 16 路并发 replay 只有一次变更；
- 事务中任意异常都会 rollback；
- PURGE 后不残留 value payload。

### 14.3 Workflow 端到端用例

至少覆盖：

1. `预算 1000 元`：当前轮生效，长期记录为 0。
2. `记住以后买耳机预算 1000 元`：产生 category directive，确认后只提交一次。
3. 新 session 搜索耳机：召回并填充预算。
4. 新 session 搜索手机：耳机预算不召回、不应用。
5. 当前轮输入预算 1500：覆盖长期默认但不自动改写长期记录。
6. `优先官方店`：只影响排序，不成为硬过滤。
7. `不喜欢翻新`：作为软负向偏好，不得默认清空候选。
8. FORGET 后新 session 不再应用。
9. HITL reject、重复 approve resume、进程中断恢复均无重复 commit。
10. recall/commit/Event Store 分别故障时，用户提示与真实事务一致。
11. workflow 与 Multi-Agent 对同一输入产生相同的 MemoryApplication 和持久化结果。

### 14.4 数据集与发布门禁

现有 `memory_dataset.jsonl` 主要验证手工 directive 和 adapter 不变量，不能作为自然语言端到端证据。目标数据集增加：

- 原始用户表达和是否应产生 directive 的标签；
- 期望 operation/key/value/scope/apply_mode；
- 多 session 序列和当前 category；
- 期望应用结果、排序影响、忽略原因；
- negative samples：普通预算、平台和偏好表达不能误写长期 Memory。

发布门禁：

- `cross_user_memory_leakage_count = 0`
- `cross_category_memory_leakage_count = 0`
- `implicit_memory_write_count = 0`
- `replay_duplicate_side_effect_count = 0`
- `memory_hard_filter_violation_count = 0`
- 所有关键端到端样本必须执行真实 parser → policy → adapter → recall → apply 链路，禁止测试直接注入最终 mutation 代替用户输入。

## 15. 配置

保留：

- `SHIJIAJING_MEMORY_ENABLED`
- `SHIJIAJING_MEMORY_RECALL_ENABLED`
- `SHIJIAJING_MEMORY_COMMIT_ENABLED`
- `SHIJIAJING_MEMORY_BACKEND` / `SHIJIAJING_MEMORY_DSN`
- `SHIJIAJING_MEMORY_RECALL_LIMIT`
- `SHIJIAJING_MEMORY_CONFIRMATION_REQUIRED`
- `SHIJIAJING_RECENT_TURNS_LIMIT`

新增或明确：

- `SHIJIAJING_RECENT_TURNS_MAX_BYTES`：会话摘要序列化上限。
- `SHIJIAJING_MEMORY_PURGE_ENABLED`：只允许受信管理入口使用。
- `SHIJIAJING_MEMORY_MUTATION_LEDGER_RETENTION_DAYS`：仅适用于无 value 的 hash ledger；不得短于 Request Ledger 的请求幂等窗口。

约束：

- commit enabled 必须同时启用 recall。
- backend disabled 时不得把 Memory 声称为已启用。
- 客户端不能覆盖部署级 recall/commit/purge 开关。
- workflow 与 Multi-Agent 必须共同遵守 confirmation 配置。

## 16. 迁移与灰度

### 阶段 A：补齐写入入口

- 更新 Intent Prompt，加入 memory directive schema、正反例和显式触发规则。
- 扩展规则解析器。
- 增加自然语言到 candidate 的 contract 测试。
- feature flag 保持 commit disabled。

### 阶段 B：修正召回和应用顺序

- 拆分 `merge_current_turn_context` 与 Memory default 应用。
- workflow/Multi-Agent 都显式传入当前 category 的 `MemoryQuery`。
- 引入 `MemoryApplication`，接通 ranking/negative 模式。
- 增加跨品类和 apply mode 端到端测试。

### 阶段 C：会话上下文消费

- 精简 `ConversationTurnSummary`。
- 把 bounded recent context 接入指代解析和修正，不用于复制历史约束。
- 增加摘要大小、隐私和跨 turn 行为测试。

### 阶段 D：持久化与隐私迁移

- mutation ledger 从 payload JSON 迁移为 payload hash。
- 补齐所有异常 rollback。
- 增加 PURGE_OWNER 管理流程。
- 对旧记录执行 key/mode 兼容检查；非法组合进入 quarantine，不直接应用。

### 阶段 E：灰度发布

1. shadow 解析 candidates，不 recall、不 commit，观察误写率。
2. 开启 recall，仍关闭 commit，验证 scope 和应用结果。
3. 对测试 owner 开启 commit + confirmation。
4. PostgreSQL contract、端到端门禁和生产外部证据通过后扩大范围。

## 17. 实现映射

| 目标 | 主要文件 |
|---|---|
| Intent schema 与显式写入语义 | `contracts.py`、`prompts/intent.md`、`domain/intent_rules.py` |
| 当前品类初步合并与 recall 时序 | `graph.py`、`nodes/intent_nodes.py`、`nodes/memory_nodes.py` |
| scope、优先级与 apply mode | `domain/memory_policy.py` |
| 排序先验与负向偏好接入 | Retrieval/Ranking contracts、reranker、Multi-Agent task inputs |
| Multi-Agent query/授权 | `multi_agent/planner.py`、`multi_agent/supervisor.py`、`multi_agent/agents/specialists.py` |
| recent turns 消费 | `state.py`、`contracts.py`、Intent 输入与会话恢复节点 |
| SQLite/PostgreSQL 事务与 purge | `adapters/memory.py`、`ports/memory.py`、迁移工具 |
| 端到端证据 | `tests/contract/`、`tests/workflow/`、`data/eval/memory_dataset.jsonl`、评测执行器 |

## 18. 当前实现差距

在完成上述阶段前，必须如实记录以下差距：

- Intent Prompt 和规则解析器尚未可靠地产生自然语言 memory directives。
- workflow recall 发生在当前品类合并之前，存在使用上一轮品类的风险。
- Multi-Agent 的默认 recall query 只包含 global scope。
- `apply_mode` 尚未完整接入约束、排序和负向偏好三条执行路径。
- `recent_turns` 已持久化但尚未成为指代解析的有效输入。
- 现有 memory 测试主要验证 adapter 和手工 directive，缺少完整用户输入链路。
- FORGET/CLEAR_OWNER 是软遗忘，mutation ledger 仍需迁移为无 value 的 hash 记录。

只有阶段 A-D 的功能和端到端门禁完成后，项目才能把该能力描述为“完整三层记忆体系”。

## 19. 运维验证

SQLite/领域/工作流回归：

```powershell
uv run pytest -q tests/unit tests/workflow -k "memory or recent_turns"
```

PostgreSQL contract：

```powershell
$env:SHIJIAJING_TEST_POSTGRES_DSN="postgresql://..."
uv run pytest -q -m integration tests/contract/test_memory_adapters.py
```

没有 PostgreSQL DSN 时测试必须明确 skip，不能把 skip 计为 PostgreSQL 已验证。
