# 意图理解与 Query Expansion — 图片内容

## 图 1：统一理解主链路

- 标题：从用户表达，到结构化意图，再到可执行查询
- 布局：从左到右的一条主链路，分成“理解 → 落地 → 执行”三个阶段；阶段之间用明确箭头连接
- 输入：
  - 本轮表达：用户文本 / 图片识别摘要 / 显式选择
  - 当前上下文：活跃商品主题 / 已生效条件 / 近期对话
- 阶段一，结构化理解（图 2 展开）：
  1. 判断“用户最终要完成什么” → `TaskIntent`
  2. 判断“本轮如何延续或修改任务” → `DialogueAction`
  3. 抽取“本轮具体新增、替换或删除了什么” → `IntentPatch`
  4. 同时标出待解析指代；一句话有多个先后目标时，生成有依赖关系的步骤
- 阶段二，确定性落地（图 3 上半区展开）：
  1. 把“这个”“第二款”等指代绑定到会话中真实存在的商品、候选或主题
  2. 校验意图、步骤和字段操作，再把 Patch 与历史条件、图片结果和用户修正合并
  3. 得到统一理解：明确的业务目标 + 已解析对象 + 最终生效约束
  4. 指代无法唯一绑定或硬条件冲突 → 追问用户，不进入后续执行
- 阶段三，生成查询并路由（图 3 下半区展开）：
  1. 用已解析对象和最终约束生成一条完整基础查询；价格、平台等继续作为独立硬过滤
  2. 搜索 / 推荐 → 受控扩写后检索
  3. 比较 / 解释 → 证据充分则直接执行，证据不足只补对应缺口
  4. 识别 / 通用问答 / 任务控制 → 进入各自的直接路径，不做无关扩写
- 右侧输出：将统一理解交给 MainAgent，进入对应执行路径

## 图 2：固定意图体系

- 标题：三个正交维度：要完成什么 × 本轮怎么变 × 具体变了什么
- 布局：左、中、右三组卡片；顶部放公式 `User Turn → TaskIntent + DialogueAction + IntentPatch`
- 左栏，业务意图 `TaskIntent`：
  - `product_search` 查找满足条件的商品；例：「找 2000 元内的降噪耳机」
  - `product_compare` 比较明确对象；例：「对比刚才前两款」
  - `product_identify` 识别商品身份；例：「图里是什么型号」
  - `product_recommend` 根据用途和偏好作选择；例：「哪个更适合通勤」
  - `product_explain` 解释结果或差异；例：「第二款为什么更贵」
  - `general_qa` 回答独立知识问题；例：「主动降噪是什么原理」
  - `task_control` 控制任务状态；例：「取消这次比较」
- 中栏，对话动作 `DialogueAction`，按状态迁移分组：
  - 创建：`start`
  - 延续：`continue` / `select` / `confirm`
  - 修改：`refine` / `replace` / `remove` / `correct`
  - 否定与结束：`reject` / `reset` / `cancel`
- 右栏，增量 `IntentPatch`，只记录本轮明确变化：
  - 商品目标：品类 / 品牌 / 型号 / 动态属性 / 关键词 / 排除词
  - 交易约束：价格区间 / 平台 / 颜色 / 最低评分
  - 偏好排序：`sort_by` / `preferences` / `cancelled_preferences`
  - 状态操作：`clear_fields`
  - 记忆候选：`memory_directives`，只是候选，不是写入授权

## 图 3：指代消解与受控扩写

- 标题：引用只绑定真实对象，扩写绝不改变硬约束
- 布局：上下两条实例链路；上半区展示“指代如何落到当前候选”，下半区展示“状态如何变成安全检索查询”
- 背景：纯白色不透明背景，不使用透明底或棋盘格
- 上半区，候选指代实例：
  1. 当前候选：① iPhone 15 Pro 128GB　② iPhone 15 Pro 256GB　③ iPhone 15 Pro 512GB
  2. 用户：「第二款为什么更贵？」
  3. 理解结果：目标是解释价格差异；待解析指代是“第二款”
  4. 引用范围：只在产生“第一款、第二款、第三款”的当前候选列表中查找，不跨到其他历史列表
  5. 绑定结果：“第二款”唯一对应 iPhone 15 Pro 256GB，将该商品作为本轮解释对象
  6. 后续动作：价格、规格和来源证据充分 → 直接解释；缺少关键证据 → 只补查对应缺口
  7. 失败分支：候选列表不存在、顺序已失效或出现多个匹配 → 先追问用户，不猜测对象
- 下半区，跨轮改写与扩写实例：
  1. 历史有效状态：iPhone 15 Pro / 256GB / 预算 ≤ 7000 / 京东
  2. 本轮：「这个要黑色的」
  3. 指代绑定当前主题；`IntentPatch = { colors:[黑色] }`
  4. `ConstraintMerger` 产出 `constraints_version = 8`
  5. Query Rewrite 生成唯一基础查询：`iPhone 15 Pro 256GB 黑色`
  6. 独立硬过滤：`price <= 7000`、`platform = jd`
  7. Query Expansion 最多增加两个高价值变体：`苹果 15 Pro 256G 黑色`、`iPhone 15 Pro 256GB Black Titanium`
  8. 每个查询共享同一份硬过滤和 `constraints_version = 8`，再编译到 Dense / Sparse 等物理通道
- 右侧放意图路由小表：
  - 必须扩写：`product_search`
  - 通常扩写：`product_recommend`
  - 按证据缺口决定：`product_compare` / `product_explain`
  - 通常不扩写：`product_identify`
  - 独立路径：`general_qa` / `task_control`

## 图 4：四类完整执行实例

- 标题：从一句话到可审计动作：四个实例
- 布局：四栏并列，每栏 = 请求与上下文 → 结构化理解 → 本地验证与合并 → 执行路径

- 例 1：新搜索
  - 请求：「找索尼 XM5，2000 以内，只看京东」
  - 理解：`product_search + start`
  - Patch：`brand=Sony / model=WH-1000XM5 / max_price=2000 / platforms=[jd]`
  - 合并：创建新主题和约束版本
  - 执行：生成 base → 最多两个扩写 → 检索与比较

- 例 2：跨轮条件替换
  - 历史：Sony WH-1000XM5 / 黑色 / 预算 ≤ 2000 / 淘宝
  - 请求：「把预算改成 1500，只看京东」
  - 理解：`product_search + replace`
  - Patch：`max_price=1500 / platforms=[jd]`，未提及字段不复制进 Patch
  - 合并：保留品牌、型号和颜色；预算替换为 1500；平台替换为京东；约束版本递增
  - 执行：只重新执行受影响的改写、检索和比较

- 例 3：指代解释
  - 上下文：候选列表 v4 中第二款为 `group:g2`
  - 请求：「第二款为什么更贵？」
  - 理解：`product_explain + continue`，引用 span 为「第二款」
  - 解析：`第二款 → group:g2 / version=4`
  - 执行：价格、规格和来源证据齐全 → 直接解释；单一缺口 → `supplement_search`；多步取证 → `delegate_research`

- 例 4：有依赖的多意图
  - 请求：「找一下 XM5，再和刚才的 QC Ultra 比较」
  - 主意图：`primary_intent = product_compare`
  - Step 1：`s1 / product_search / model=WH-1000XM5 / depends_on=[]`
  - Step 2：`s2 / product_compare / target=已解析的 QC Ultra group_id / depends_on=[s1]`
  - 执行：先完成或复用 XM5 候选，再对两个确定目标补齐同口径证据并比较
