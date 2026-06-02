# AI 购物决策助手前端设计改进 Prompt

## 背景与产品定位

这是一个 AI 驱动的购物决策工具，核心功能包括：商品图像识别、跨平台比价、Agent 决策打分、价格走势分析。技术栈为 Web（HTML/CSS/JS）+ Flutter App 双端并行，目标用户是有一定消费决策诉求的普通用户。

---

## 当前设计问题清单

### 问题一：品牌色分裂，无视觉焦点

- **现状**：Web 端 `--accent` 定义为 `#111827`（接近纯黑），Flutter 端 `_accent` 为 `#4F46E5`（靛蓝），两端核心色不一致。Web 端 primary button 与正文、brand mark 几乎同色，页面失去视觉层级，用户眼睛找不到落点。
- **要求**：统一双端 accent 为同一个具有辨识度的色彩（推荐靛蓝系 `#4F46E5` 或更有品牌感的定制色）。Web 端所有 `.primary` button、focus ring、active 状态全部切换到该色。确保页面中 CTA 元素在视觉上有清晰的"第一吸引力"。
- **涉及文件**：
  - `app/packages/core/lib/src/theme/app_theme.dart` — `_accent` 常量
  - `frontend/styles.css` — `:root { --accent }`, `button.primary`, `.brand-mark`

---

### 问题二：无个性，视觉语言趋同

- **现状**：灰白底 + 细线 border + 8px 圆角 + 轻 shadow 的组合方式过度通用，与市面上大量 SaaS dashboard 没有区分度。用户无法建立产品记忆点。
- **要求**：在现有功能性框架基础上，引入至少一个**强辨识度的视觉特征**，可以是：
  - 独特的品牌字体（标题级别使用非 Inter/system-ui 的字体）
  - 特定的图形语言（扫描线、AI 脉冲波形、信号点阵等与"AI识别"场景相关的视觉元素）
  - 带有方向感的色彩用法（如信号蓝的渐变作为重要区域的 accent 背景）
  - 可以参考 Linear、Raycast、Clerk 的审美方向：精致、有态度、不讨好所有人

---

### 问题三：信息密度过高，喘息空间不足

- **现状**：主要容器 padding `14px`，卡片间距 `10-12px`，顶栏 `14px`，整体偏紧。功能区多（识别/推荐/对比/决策/资产），内容堆叠后用户扫视疲惫。
- **要求**：
  - 主要内容区 section 间距提升至 `24px` 以上
  - 每个功能面板 padding 统一至 `18-20px`
  - 在识别结果、决策摘要等核心区域引入明确的**视觉分区**（不是更多卡片，而是用背景色区域或分割线区分"输入区"和"输出区"）
  - 左侧操作栏与右侧结果区之间的信息权重应该有明显区别，操作栏是辅助，结果区是主角
- **涉及文件**：
  - `frontend/styles.css` — `.workspace` gap, `.panel` padding, `.side-panel`
  - `app/packages/recognition/lib/src/presentation/screens/recognition_screen.dart` — `SingleChildScrollView` padding, section spacing

---

### 问题四：卡片体系无层级

- **现状**：全页面容器几乎都是同一配方（白色 + `#E5E7EB` border + `border-radius:8px`），用户无法快速判断"哪里是主要信息，哪里是辅助"。
- **要求**：建立三层容器语义：
  1. **主容器**（识别结果卡、决策摘要条）：带 border + 轻 shadow + 较大 padding，可考虑用 `border-left: 3-4px solid accent` 标记主内容
  2. **次容器**（属性详情、信号条区域）：仅用背景色区分（`panelSoft #F9FAFB`），不加 border
  3. **内联元素**（tag、chip、pill）：保持现有样式即可
  - 禁止在同一层级用同样样式的卡片并排展示超过 3 个，否则必须通过尺寸、颜色或位置进行差异化
- **涉及文件**：
  - `frontend/styles.css` — `.panel`, `.product-card`, `.suggestion-card`, `.brief-band`, `.recognition-box`, `.recommendation-box`, `.insight-box`
  - `app/packages/core/lib/src/theme/app_theme.dart` — `cardTheme`

---

### 问题五：Score Ring 被浪费

- **现状**：`score-ring`（`conic-gradient` 圆形评分）是全站唯一有强视觉记忆点的组件，但尺寸仅 76×76px，被塞在推荐卡右上角，被周围大量文字淹没。
- **要求**：
  - 将 Score Ring 放大至 `96-120px`，作为决策结果区的**视觉锚点**
  - 配合简单的数字变化动效（0 → 最终分数的 count-up 动画，约 600ms）
  - 决策动作标签（建议购买 / 建议观望 / 建议避开）与 Score Ring 并列，共同构成决策结果的视觉中心
  - Flutter 端同步实现同等尺寸和动效的 ScoreRing widget
- **涉及文件**：
  - `frontend/styles.css` — `.score-ring`, `.decision-hero`
  - `frontend/app.js` — 动画逻辑
  - Flutter 端需新建或扩展现有 widget

---

### 问题六：完全缺失动效

- **现状**：仅有 toast 的 `opacity transition` 和 button 的 `120ms ease`，AI 处理过程无任何动态反馈，状态切换生硬。
- **要求**：补充以下关键动效，均要求 CSS-only 或最小 JS 实现，不引入额外动效库：
  1. **识别加载态**：扫描线从上到下循环扫过图片预览区，`2s linear infinite`
  2. **Demo 步骤推进**：每个步骤从 idle→active 时，左侧圆点用 `scale(1) + pulse` 动效，active→done 时用 `checkmark` 短动画
  3. **Score Ring 出现**：页面首次渲染决策结果时，ring 从 0 到目标值的动画，用 `@property` + CSS 变量动画实现
  4. **结果卡片进场**：产品卡片列表首次渲染时，`staggered fade-in + translateY(8px→0)`，每张卡间隔 `60ms`
  5. **Flutter 端**：识别加载时给 `_ScanCorner` 添加旋转/闪烁动效，传递"正在扫描"的感知
- **涉及文件**：
  - `frontend/styles.css` — 新增 `@keyframes`
  - `frontend/app.js` — staggered进场逻辑
  - `app/packages/recognition/lib/src/presentation/screens/recognition_screen.dart` — `_ScanCorner` 动画

---

### 问题七：Sparkline 图表太简陋

- **现状**：价格走势图仅是一条 SVG `polyline`，无填充、无端点、无坐标标注、无 hover 交互，与"价格历史分析"的功能定位不符。
- **要求**：
  - 在 polyline 下方添加 `linearGradient` 渐变填充（顶部 signal 色半透明 → 底部透明）
  - 在最低价和当前价位置添加突出的端点 dot（`r=3`，填充 accent 色）
  - 添加最低价/最高价的价格标注（SVG `text` 元素，靠近对应端点）
  - hover 时显示该时间点的具体价格 tooltip（JS 实现即可）
  - 整体尺寸从当前 `height: 86px` 提升到至少 `120px`，给图表更充分的展示空间
- **涉及文件**：
  - `frontend/app.js` — `renderSparkline()` 函数
  - `frontend/styles.css` — `.sparkline`

---

### 问题八：响应式中间态缺失

- **现状**：只有 `900px` 和 `520px` 两个断点，平板横屏（768-900px）和小笔记本（1024-1280px）体验没有针对性处理，`top-bar` 六列硬编码宽度在中等屏幕直接挤压。
- **要求**：
  - 补充 `@media (max-width: 1280px)` 断点，`top-bar` 在此宽度折叠为两行
  - `768px` 新增断点，侧边栏收起为抽屉，主内容区全宽
  - `top-bar` 的 6 列 grid 改为 `grid-template-columns: repeat(auto-fit, minmax(110px, 1fr))`，适应不同宽度
- **涉及文件**：
  - `frontend/styles.css` — 响应式断点区域

---

### 问题九：Flutter 端 `dispose` 写法有隐患

- **现状**：`dispose()` 中调用 `ref.read(recognitionProvider.notifier).reset()`，在 widget 销毁阶段操作 Riverpod provider 可能触发 "Cannot use ref after disposed" 警告。
- **要求**：将 reset 逻辑移至 `deactivate()` 或通过 `addPostFrameCallback` 在合适时机执行；或在 notifier 自身实现 `dispose` 时的自动 reset，避免在 widget dispose 阶段访问 ref。
- **涉及文件**：
  - `app/packages/recognition/lib/src/presentation/screens/recognition_screen.dart` — `dispose()`

---

### 问题十：Flutter 主题字体未落地

- **现状**：`buildAppTheme()` 中没有配置 `fontFamily`，实际渲染使用系统默认字体，与 Web 端 `Inter, Microsoft YaHei` 的字体体验存在落差。
- **要求**：
  - 在 `pubspec.yaml` 中声明目标字体（建议中文产品使用 `Source Han Sans` / `LXGW WenKai` 等有品质感的中文字体，英文标题搭配 `DM Sans` 或 `Syne`）
  - 在 `buildAppTheme()` 的 `ThemeData` 中设置 `fontFamily`
  - Web 端与 Flutter 端字体选型需保持视觉一致，至少英文部分使用同一字体
- **涉及文件**：
  - `app/packages/core/lib/src/theme/app_theme.dart` — `ThemeData`
  - `app/pubspec.yaml` — 字体声明
  - `frontend/styles.css` — `font-family`

---

## 设计改进优先级

| 优先级 | 问题 | 理由 |
|--------|------|------|
| P0 | 统一双端 accent 色（问题一） | 影响全局视觉一致性 |
| P0 | 补充核心动效（问题六） | AI 产品无动效等于没有产品感 |
| P1 | Score Ring 放大为视觉锚点（问题五） | 唯一记忆点，需要放大价值 |
| P1 | Sparkline 图表升级（问题七） | 核心功能配套的可视化太弱 |
| P1 | 卡片层级体系重建（问题四） | 影响信息扫视效率 |
| P2 | 引入品牌视觉特征（问题二） | 影响长期产品辨识度 |
| P2 | 间距与喘息空间（问题三） | 影响整体阅读体验 |
| P2 | 响应式补全（问题八） | 影响多端可用性 |
| P3 | Flutter dispose 写法（问题九） | 代码健壮性，非视觉问题 |
| P3 | Flutter 字体配置（问题十） | 完善度问题 |

---

## 设计改进执行约束

1. 不引入新的 UI 框架或组件库，在现有 CSS 变量体系上扩展
2. 动效全部使用 CSS transition / animation，不引入 GSAP 等动效库
3. Flutter 端动效使用 `AnimationController` + `Tween`，不引入第三方动效包
4. 字体变更需在中文环境下验证渲染效果（避免中文字重/字形异常）
5. 所有颜色修改需同步更新 `styles.css` 的 CSS 变量和 `app_theme.dart` 的颜色常量，保持双端语义一致
