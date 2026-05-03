# AI办公室员工技能一览

> 当前范围：个人生产力办公室系统。生活系统暂不纳入本阶段。

## 配置中心

员工能力、PE 工作流归属、产出物和进化策略统一维护在：

`config/office_registry.json`

后端启动时会读取该配置，并写入每个 Agent 的 `capability` 状态，供前端办公室面板可视化展示。

PE 工作流标准文件随仓库发布在：

`.agent/workflows/pe-workflows`

## 管理层

| 员工 | ID | 职位 | 专长领域 |
|------|-----|------|---------|
| AI助手/小K | aiky_main | 办公室助理 | 任务调度、规格守门、质量裁判、知识沉淀、员工进化审批 |
| Steve | ceo_01 | CEO | 市场趋势、商业模式、战略决策、市场分析、竞品分析 |
| Elon | cto_01 | CTO | 技术架构、技术选型、性能优化、安全、数据库、API |

## 执行层（Worker）

| 员工 | ID | 职位 | 专长领域 | 实际产出 |
|------|-----|------|---------|---------|
| Emma | pm_01 | 产品经理 | 需求分析、用户体验、产品设计、PRD、功能规划、用户故事 | `3-PRD.md` |
| Alex | ui_01 | UI 设计师 | 界面设计、交互、视觉、配色、布局、UI/UX、设计规范 | `.html` 可预览演示页 |
| Lucas | fe_01 | 前端工程师 | 前端开发、Vue、React、CSS、JavaScript、HTML、响应式、组件 | `6-代码实现/` |
| David | be_01 | 后端工程师 | 后端开发、API 设计、Python、Node、微服务、数据库、服务器 | `.md` API 设计文档 |
| Sarah | qa_01 | 测试工程师 | 测试、质量保证、自动化测试、Bug 追踪、测试用例、性能测试 | `7-测试用例.md` |

## PE 工作流对应关系

```
research（市场调研）
    → competitive（竞品分析）
        → planning（PRD）             ← Emma 负责，产出 3-PRD.md
            → architecture（架构设计） ← Elon 负责，产出 4-架构设计.md
                → tasks（任务拆解）    ← AI助手/小K 负责，产出 5-开发任务.md
                    → execution（开发实现） ← Alex / Lucas / David
                        → testing（测试验收） ← Sarah
                            → summary（项目总结） ← AI助手/小K
```

当前后端执行链路已覆盖 `research → competitive → planning → architecture → execution`。
`tasks / testing / summary` 已在办公室能力映射中注册，后续可继续拆成独立执行阶段。

## 员工进化机制

每个员工都拥有自己的进化焦点，但方法晋升必须经过 AI助手/小K：

```
员工对话/项目反馈
    → observation / hypothesis
        → METHOD-CAND
            → review / benchmark / retro
                → AI助手/小K approve
                    → promote 到员工能力库或 AI助手/小K 方法论
```

## 技能定义位置（开发参考）

| 内容 | 文件 |
|------|------|
| 员工能力注册表 | `config/office_registry.json` |
| 员工初始化与 capability 注入 | `backend/main.py` |
| 员工问答专长域（用于智能路由） | `backend/agents/orchestrator.py` 第 37–45 行 |
| 员工实际工作行为（workflow / prompt） | `backend/agents/worker_agents.py` `ROLE_CONFIG` |
| CEO 调研流程 | `backend/agents/ceo_agent.py` |
| CTO 架构流程 | `backend/agents/cto_agent.py` |
| 前端办公室档案面板 | `frontend/index.html` + `frontend/app.js` + `frontend/style.css` |
