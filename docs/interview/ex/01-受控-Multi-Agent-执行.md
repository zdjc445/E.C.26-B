# 主 Agent 与按需 Subagent 执行

> 本文讲解当前实现。旧的固定 Workflow、Supervisor 和任务 DAG 仅作为历史背景，不是当前入口。

## 1. 核心执行循环

```text
MainAgent observe → propose one typed action → runtime guard
       ↑                                      ↓
       └──── result/evidence/version check ← tool or subagent
```

生产只有 `AgentFacade → MainAgentRuntime` 一条链。主 Agent 每轮只能从有限动作目录中选择一个
动作：检索比较、补充检索、证据读取、Research/Verification 委派、追问、回答或无结果结束。
运行时负责权限、硬约束、版本、证据、预算、幂等和 checkpoint；模型不能直接调用任意函数、访问
URL 或修改规范状态。

## 2. 为什么称为 Multi-Agent

这里的 Multi-Agent 指主 Agent 与按需子 Agent 的协作，不是预先派发一张任务 DAG：

| 角色 | 输入边界 | 输出边界 |
|---|---|---|
| MainAgent | 规范约束、候选摘要、证据摘要、剩余预算 | 提议一个严格动作 |
| ResearchSubagent | 冻结约束、明确缺口、有限候选/证据、子预算 | 候选、证据引用和未解决问题 |
| VerificationSubagent | 指定候选、争议字段和可用详情端口 | 逐字段核验结果 |

Research 与 Verification 都是单层、受预算限制的子循环；子 Agent 没有完整会话、长期记忆库或
主状态写权限。普通明确型号请求零次委派是正常轨迹，不需要为了体现“多 Agent”强制启动子任务。

## 3. 委派准入与恢复

委派前必须同时满足：存在可描述的缺口、实际依赖已装配、候选/证据和约束版本匹配、父级预算
可以覆盖子预算。子结果先按不可信输入处理，父 runtime 重新校验事实证据和确定性比较结果；
详情端口不存在时，Verification 动作不会进入动作目录。

Checkpoint 使用 `agent-runtime-v2/{session}/{request}/main` namespace，保存动作记录、查询
fingerprint、候选、证据、版本和用量。已提交结果可复用；未提交只读子任务只能在未消耗的预算
内有限重跑，不能因为恢复而重置预算或重复提交 Memory mutation。active interrupt 消费后清理
session marker。

## 4. 失败语义

- 主模型输出非法：有限修复后转为明确失败或使用已验证结果，不启动另一套引擎。
- 检索不可用：返回显式降级/不可用状态；本地 BM25 不声称执行了向量检索。
- 子 Agent 超时、无进展或证据不足：返回结构化终态，由主 Agent 决定回答、追问或结束。
- 预算耗尽：保留已验证结果，禁止通过重复 runtime 或额外查询绕过限制。

## 5. 口播示例

> 对于“索尼 XM5，预算 2000 元以内，黑色”这类请求，首轮检索通常已经足够，因此主 Agent
> 直接回答且委派数为 0。如果首轮候选不足，但存在明确的型号别名或未覆盖查询词，主 Agent 可以
> 提出一次有界 `supplement_search`，也可以在缺口足够复杂时委派 Research。若两个候选的容量
> 明确冲突，确定性 SKU 逻辑直接拆分；只有详情端口能补充争议字段时才委派 Verification。

## 6. 代码位置

- 门面：`src/shijiajing_agent/facade.py:55`
- 动作契约：`src/shijiajing_agent/agent_runtime/contracts.py:20`
- 委派准入：`src/shijiajing_agent/agent_runtime/policy.py:33`
- 主循环：`src/shijiajing_agent/agent_runtime/runtime.py:100`
- checkpoint namespace：`src/shijiajing_agent/agent_runtime/checkpoint.py:37`
