# 主 Agent 与按需 Subagent

当前实现只有 `AgentFacade → MainAgentRuntime` 一条编排路径。这里保留文件名以承接历史
“Multi-Agent”概念，但不再存在 Workflow、Supervisor、任务 DAG 或 Planner 运行时。

## 1. 角色与边界

| 角色 | 职责 | 可见范围 |
|---|---|---|
| MainAgent | 维护购物目标，选择检索、补查、证据、委派、追问或回答 | 当前规范约束、候选摘要、证据摘要、预算 |
| ResearchSubagent | 对明确的检索缺口执行有限多步调查 | 冻结约束、有限候选/证据和子预算 |
| VerificationSubagent | 在详情端口存在时核验候选争议字段 | 指定候选、字段和允许证据 |

子 Agent 不获得完整会话、长期画像库或主状态写权限；最多保持单层父子关系。普通明确请求
零次委派是正常轨迹，不构成另一种运行模式。

## 2. 动作循环

```text
MainAgent observe → propose one typed action → runtime guard
       ↑                                      ↓
       └──── result/evidence/version check ← tool or subagent
```

动作契约在 `agent_runtime/contracts.py`：检索比较、`supplement_search`、证据读取、Research/
Verification 委派、追问、回答和无结果结束。主模型不能提出任意函数、URL、授权令牌或新的
硬条件。

## 3. 委派准入

- 必须存在可描述的缺口，且委派能力已由实际依赖装配；
- 约束版本、证据版本、候选 ID 和查询指纹必须与当前状态一致；
- 父级预算必须能覆盖子预算，Research 与直接补查共享检索额度；
- 子结果先作为不可信输入验证，事实必须绑定已登记证据，确定性比较服务重新计算可比性；
- 无详情端口时不暴露 Verification，也不把 Research 结果伪装成详情核验。

## 4. 状态、恢复与故障

`MainRuntimeState` 是唯一规范状态写入者。Checkpoint 使用 `agent-runtime-v2` namespace，
保存动作状态、查询指纹、候选池、证据、版本和用量；子 Agent 没有独立逐步 checkpoint。

已提交结果可重放复用；未提交只读子任务最多在剩余预算内重跑，不能重置父级用量。主模型、
子模型、检索或证据失败时，runtime 保留已验证结果，或以明确的失败/降级/待追问终态结束，
不重新启动另一套引擎。

## 5. 测试口径

测试通过 Fake Decision Port 覆盖普通零委派、直接补查、多步 Research、详情能力缺失、版本
过期、伪造证据、预算耗尽、HITL resume、请求幂等和 Memory 授权。真实模型/平台数据的质量、
延迟和成本仍需按 [评测说明](evaluation.md) 单独执行；Fake 不能证明线上召回效果。
