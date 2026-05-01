---
description: 代码实现 - 可交付的1.0版本，非演示DEMO
---

# 💻 代码实现工作流

## ⚠️ 核心定位

> **这不是"代码DEMO"，这是可交付的 1.0 版本。**
> 代码实现阶段的产出物必须达到可以直接演示给用户/领导/投资人的标准，
> 具备丰富真实的演示数据和完整的分支交互流程。

## 🧠 AIky 集成

> 开始前，先阅读以下 AIky 知识：
> - `AIky/identity.md` — 统一身份档案；重点读取"三位一体"、"质量优先"、"细节控"、"场景回归法"
>
> **代码标准（AIky Standard）**：
> - **流程完整（Completeness）**：核心路径必须闭环，分支流程有实际交互，不能留"坑"
> - **数据丰富（Rich Data）**：演示数据多且真实（至少一屏半列表），模拟真实使用场景
> - **视觉品质（Premium）**：现代设计、微动画、响应式，体现专业感
> - **四态完备（4-States）**：loading / success / empty / error 全覆盖

## 技术选型

### 默认技术栈
- **前端**: HTML5 + CSS3 + JavaScript（纯前端，无需构建工具）
- **样式**: 现代 CSS（CSS Variables + Flexbox/Grid + 动画）
- **图标**: FontAwesome 6 / Material Icons（CDN）
- **字体**: Google Fonts（Inter / Noto Sans SC）
- **图表**: ECharts（如需数据可视化）
- **框架**: Vue 3 CDN 版（如需响应式数据绑定）

### 设计系统强制规范
```css
:root {
  /* 品牌色 - 根据项目调整 */
  --primary: #6366f1;
  --primary-hover: #4f46e5;
  --primary-light: rgba(99, 102, 241, 0.1);

  /* 语义色 */
  --success: #10b981;
  --warning: #f59e0b;
  --error: #ef4444;
  --info: #3b82f6;

  /* 中性色 */
  --bg-primary: #ffffff;
  --bg-secondary: #f8fafc;
  --bg-tertiary: #f1f5f9;
  --text-primary: #0f172a;
  --text-secondary: #64748b;
  --text-tertiary: #94a3b8;
  --border: #e2e8f0;
  --divider: #f1f5f9;

  /* 间距系统 (4px base) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;

  /* 圆角 */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-full: 9999px;

  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.12);
  --shadow-xl: 0 16px 48px rgba(0,0,0,0.16);

  /* 动画 */
  --transition-fast: 150ms ease;
  --transition-normal: 250ms ease;
  --transition-slow: 350ms ease;
}
```

## 执行步骤

### 1. 读取 SDD 输入
基于 PRD 文档（`3-PRD.md`）、架构设计（`4-架构设计.md`）和开发任务文档（`5-开发任务.md`），确认：
- **规格基线**: PRD 状态为 Frozen，记录 SPEC 版本
- **任务清单**: 读取所有 P0/P1 `TASK-*`
- **追踪关系**: 确认每个 TASK 关联 `FR/AC/NFR/DATA`
- **变更约束**: 不实现未进入 PRD 或任务文档的隐性需求

如发现任务缺少规格来源、验收标准或实现文件，先返回 `/pe-tasks` 修正。

### 1.1 禁止隐性需求红线

开发过程中如发现任何未进入 `3-PRD.md` 或 `5-开发任务.md` 的需求：
- 立即停止实现该需求
- 记录为 `CHANGE-*`
- 使用 `/pe-change` 做影响分析
- Accepted 后回到 `/pe-tasks` 更新任务
- Rejected 或 Deferred 的需求不得进入代码

不允许为了“顺手完善”直接增加新功能、新页面、新规则或新数据字段。

### 2. 分析需求与流程梳理
基于 SDD 任务和 PRD，梳理：
- **页面清单**: 列出所有需要开发的页面/视图
- **核心流程**: 画出用户操作流程图
- **分支流程**: 列出所有需要处理的分支和异常
- **数据规格**: 确认每个页面的演示数据需求

### 3. 创建项目结构
// turbo
```
独立项目/[项目名]/6-代码实现/
├── index.html          # 入口页面（SPA 单页应用）
├── css/
│   └── style.css       # 设计系统 + 页面样式
├── js/
│   └── app.js          # 应用逻辑 + 路由 + 数据
└── assets/
    └── images/         # 图片资源（用 generate_image 生成）
```

### 4. 设计系统实现（style.css）
按以下顺序构建样式：
1. **CSS Reset & Variables**: 上述设计系统变量
2. **Base Styles**: body、typography、links
3. **Layout Components**: header、sidebar、main、footer
4. **UI Components**: button、card、form、modal、toast、table、badge、tag
5. **State Styles**: `.loading`、`.empty`、`.error`
6. **Utilities**: `.flex`、`.grid`、`.hidden`、`.truncate`
7. **Animations**: `@keyframes` 定义 + transition 类
8. **Responsive**: `@media` 断点（mobile: 768px、tablet: 1024px）

### 5. 演示数据准备（app.js 内置）
**这是区别于 DEMO 的关键步骤。** 数据要求：

#### 4.1 数据量标准
| 数据类型 | 最低数量 | 说明 |
|---------|---------|------|
| 列表数据 | 20+ 条 | 保证一屏半以上，筛选后仍有结果 |
| 下拉选项 | 5+ 项 | 覆盖常见选择 |
| 图表数据 | 12+ 数据点 | 至少展示趋势变化 |
| 搜索结果 | 准备 3 组 | 有结果 / 少量结果 / 无结果 |

#### 4.2 数据真实性标准
- ✅ 使用真实中文姓名（张三→张明远、李静雯、王建国...）
- ✅ 使用合理数值（金额、分数、百分比在正常范围内）
- ✅ 使用合理时间序列（连续日期、工作日分布）
- ✅ 包含多种状态数据（已完成/进行中/待处理/已取消）
- ❌ 禁止使用 test1、test2、示例数据1 等假数据
- ❌ 禁止所有数据都是相同状态

#### 4.3 场景覆盖
每组数据需覆盖以下业务场景：
- **正常场景**: 标准业务数据
- **新用户场景**: 空数据/首次使用引导
- **高频用户场景**: 大量数据、多状态混合
- **边界场景**: 极长文本、极大数值、特殊字符

### 6. 页面开发
按 `5-开发任务.md` 中的 TASK 顺序逐一开发：
- 实现页面布局和视觉效果
- 接入演示数据
- 实现交互逻辑和状态管理
- 每完成一个 TASK，在追踪矩阵中将状态更新为 `Implemented`

### 7. 分支交互实现
**所有交互路径必须可走通**，具体要求：

#### 6.1 必备交互
| 交互类型 | 要求 | 示例 |
|---------|----- |------|
| 页面导航 | 所有菜单/tab 可切换，有选中态 | 侧边栏高亮 |
| 表单提交 | 有校验、loading、成功/失败反馈 | Toast 提示 |
| 列表操作 | 增删改查完整闭环 | 编辑弹窗 |
| 确认操作 | 危险操作有二次确认 | "确定删除？" |
| 搜索筛选 | 实时过滤，无结果有空态 | 空态插图 |
| 分页/加载 | 数据量大时有分页或加载更多 | 页码/按钮 |

#### 6.2 状态管理（四态）
每个数据展示区域必须实现：
```
┌─────────────────────────────────┐
│  Loading 态：骨架屏/Spinner      │
│  Success 态：正常数据展示         │
│  Empty 态：空态插图 + 引导操作    │
│  Error 态：错误提示 + 重试按钮    │
└─────────────────────────────────┘
```

#### 6.3 微交互清单
- [ ] 按钮 hover/active 状态变化
- [ ] 列表项 hover 高亮
- [ ] Modal 弹出/关闭动画（fade + scale）
- [ ] Toast 通知自动消失（3s）
- [ ] 表单 focus 样式 + 校验反馈
- [ ] 页面切换过渡动画
- [ ] 数字变化动画（如统计数字）
- [ ] 骨架屏闪烁动画

### 8. 视觉品质提升（Premium 标准）
- 🎨 渐变色彩：主要 CTA 使用渐变按钮
- 🪟 玻璃拟态：卡片/弹窗使用 backdrop-filter
- 💫 微动画：所有可交互元素有 transition
- 📐 对齐精确：间距使用设计系统变量，禁止 magic number
- 🖼️ 图片资源：使用 generate_image 工具生成所需图片，不用 placeholder

### 9. 响应式适配
确保在以下尺寸下可用：
- **Desktop**: 1200px+（主要开发尺寸）
- **Tablet**: 768px-1199px（布局调整）
- **Mobile**: < 768px（重排布局）

### 10. 运行与调试
// turbo
使用本地服务器启动并验证：
```bash
python -m http.server 3000 -d "独立项目/[项目名]/6-代码实现/"
```

### 11. SDD 实现追踪更新

更新 `5-开发任务.md` 的追踪矩阵：
- 已实现的任务标记为 `Implemented`
- 填入实际实现文件
- 未实现任务标记为 `Blocked` 并说明原因
- 如发现新需求，暂停实现，使用 `/pe-change` 走变更流程

### 12. 全流程演示录制
使用 browser_subagent 访问并录制完整操作演示：
- 演示所有核心流程
- 展示分支交互（正常 + 异常）
- 截图关键页面

## 产出物
- `6-代码实现/` - 完整可运行的 1.0 版本代码
- `demo-recording.webp` - 操作演示录像

## 代码质量规范
1. **语义化 HTML**: 使用合适的 HTML5 标签（header/nav/main/section/article/footer）
2. **CSS 变量**: 统一使用设计令牌，禁止 hardcode 颜色/间距
3. **模块化 JS**: 数据层 / 视图层 / 交互层分离
4. **注释规范**: 每个主要函数/数据块有注释说明
5. **无控制台报错**: 生产级代码标准

## 自检清单（发布前必查）

- [ ] 所有页面/视图可正常访问
- [ ] 所有按钮/链接可点击且有反馈
- [ ] 所有 P0/P1 TASK 已实现或有 Blocked 说明
- [ ] 每个已实现 TASK 能追踪到 FR/AC 和实现文件
- [ ] 没有未登记的隐性需求进入代码
- [ ] 列表数据 ≥ 20 条
- [ ] 搜索/筛选功能正常
- [ ] 表单提交有校验和反馈
- [ ] 危险操作有二次确认
- [ ] 四态（loading/success/empty/error）均可触发
- [ ] 无 JavaScript 控制台报错
- [ ] 响应式在 768px 下可用
- [ ] 视觉效果达到 Premium 标准

## 下一步
代码实现完成后，使用 `/pe-testing` 进入测试用例阶段
