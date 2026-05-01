"""
CEOAgent — 负责市场调研和竞品分析
采用多步调研流程：分步执行 → 进度汇报 → 质量校验 → 合成报告
"""
import asyncio
from models import AgentRole, AgentStatus, MessageType
from agents.base_agent import BaseAgent
from skills.workflow_manager import WorkflowManager


class CEOAgent(BaseAgent):
    def __init__(self, agent_id: str = "ceo_01", name: str = "Steve"):
        super().__init__(agent_id, name, AgentRole.CEO, ["Market Research", "Competitive Analysis", "Strategy"])

    # ═══════════════════════════════════════════════════════
    #  市场调研 — 多步流程
    # ═══════════════════════════════════════════════════════

    async def perform_research(self, task_description: str, task_folder: str):
        """多步市场调研：分5个阶段逐步深入，最后合成完整报告"""
        await self.update_status(AgentStatus.THINKING, "市场调研中...")
        await self.send_chat_message("收到，老大，我先做市场调研。")

        sections = {}  # 存储各阶段产出

        # ── 阶段 1/5：明确调研目标 & 市场规模分析 ──
        await self.send_chat_message("我先明确调研目标，再看市场规模。")
        await self.update_status(AgentStatus.THINKING, "分析市场规模...")
        try:
            sections["market"] = await self.think(
                f"""请对以下产品方向进行深入的市场规模分析：

{task_description}

请按以下结构详细输出（每个部分至少200字）：

## 一、执行摘要
- 一句话总结产品方向
- 核心市场机会判断
- 市场时机评估

## 二、市场分析
### 2.1 市场规模
- TAM（总可及市场）：全球/全国市场规模估算，引用具体数据
- SAM（可服务市场）：实际可触达的细分市场
- SOM（可获得市场）：短期内可争取的市场份额
- 给出具体金额或用户量级的数字估算

### 2.2 市场趋势
- 行业增长率和发展阶段（萌芽/成长/成熟/衰退）
- 3-5个关键驱动因素
- 技术变革对市场的影响
- 未来3年市场走向预判

### 2.3 政策环境
- 相关行业政策和监管要求
- 政策利好和潜在风险
- 合规成本评估

注意：
- 必须给出具体数字和量化分析，不要泛泛而谈
- 输出结论要明确，不用"可能""也许""推测"等模糊词
- 用中文输出""",
                self._research_system_prompt("市场规模分析专家")
            )
        except RuntimeError as e:
            await self._research_failed("市场规模分析", e)
            raise

        self._save_artifact("1-1-市场规模分析.md", sections["market"], task_folder)
        await self.send_chat_message("老大，市场规模这一块我看完了。")

        # ── 阶段 2/5：用户画像构建 ──
        await self.send_chat_message("我接着梳理用户画像。")
        await self.update_status(AgentStatus.THINKING, "构建用户画像...")
        try:
            sections["users"] = await self.think(
                f"""基于以下产品方向，构建详细的目标用户画像：

产品方向：{task_description}

请构建2-3个核心用户角色（Persona），每个角色包含：

## 三、用户研究

### 3.1 目标用户画像

**角色 1：[角色名称]**
- 人口统计：年龄、性别、职业、收入水平、教育程度、所在城市
- 一句话描述：用一句话概括这个用户
- 典型一天：描述用户的日常场景
- 核心痛点：列出3-5个具体痛点（不是泛泛而谈，要具体到场景）
- 现有解决方案：用户目前怎么解决这些问题
- 付费意愿：愿意为什么功能/效果付费，能接受什么价位
- 设备/渠道偏好：用什么设备、在哪里获取信息

（为每个角色都提供以上详细信息）

### 3.2 用户场景分析
列出5-8个核心使用场景，每个场景包含：
- 场景名称
- 触发条件（什么时候会用）
- 用户目标（想达成什么）
- 当前痛点（现有方案的不足）
- 理想体验（产品应该怎么做）

注意：
- 用户画像要具体、有画面感，不要空泛
- 区分 Want（表面诉求）和 Need（底层需求）
- 用中文输出""",
                self._research_system_prompt("用户研究专家")
            )
        except RuntimeError as e:
            await self._research_failed("用户画像构建", e)
            raise

        self._save_artifact("1-2-用户画像.md", sections["users"], task_folder)
        await self.send_chat_message("老大，用户画像我整理好了。")

        # ── 阶段 3/5：需求分析 ──
        await self.send_chat_message("我继续判断需求优先级。")
        await self.update_status(AgentStatus.THINKING, "分析需求优先级...")
        try:
            sections["demands"] = await self.think(
                f"""基于以下产品方向和用户信息，进行详细的需求分析：

产品方向：{task_description}

已有的用户研究摘要：
{sections['users'][:2000]}

请按以下结构输出：

### 3.3 需求优先级矩阵

使用"广度 × 频度 × 强度"三维评估框架对需求进行分级：

**评估维度说明：**
- 广度：受影响用户的比例（高>60% / 中30-60% / 低<30%）
- 频度：需求发生的频率（高=每天 / 中=每周 / 低=每月）
- 强度：需求不被满足时的痛苦程度（高=无法忍受 / 中=不方便 / 低=小困扰）

| 需求 | 广度 | 频度 | 强度 | 总分 | 优先级 |
|------|------|------|------|------|--------|
（列出10-15个具体需求，按总分排序）

**核心需求（Must-have）— 不满足则产品无价值：**
- 列出3-5个，说明为什么是必须的

**期望需求（Should-have）— 满足则显著提升体验：**
- 列出3-5个，说明对体验的提升

**兴奋需求（Nice-to-have）— 超出预期的创新点：**
- 列出2-3个，说明创新价值

**需求之间的依赖关系：**
- 哪些需求必须先做
- 哪些需求可以并行
- MVP 最小可行产品应该包含什么

用中文输出""",
                self._research_system_prompt("产品需求分析专家")
            )
        except RuntimeError as e:
            await self._research_failed("需求分析", e)
            raise

        self._save_artifact("1-3-需求分析.md", sections["demands"], task_folder)
        await self.send_chat_message("老大，需求优先级我排好了。")

        # ── 阶段 4/5：技术可行性预研 ──
        await self.send_chat_message("我再补一轮技术可行性预判。")
        await self.update_status(AgentStatus.THINKING, "评估技术可行性...")
        try:
            sections["tech"] = await self.think(
                f"""基于以下产品方向，进行技术可行性预研：

产品方向：{task_description}

核心需求摘要：
{sections['demands'][:1500]}

请按以下结构详细输出：

## 四、技术可行性

### 4.1 技术路线
- 推荐的整体技术架构方案（前端/后端/数据库/AI模型等）
- 为什么选择这个技术栈（优势对比）
- 核心功能的技术实现路径
  - 功能A → 实现方案 → 技术难度（⭐~⭐⭐⭐⭐⭐）
  - 功能B → 实现方案 → 技术难度
  - ...

### 4.2 开源/第三方方案
列出可以直接使用的开源项目和第三方服务：
| 功能模块 | 推荐方案 | 类型 | 成本 | 成熟度 |
|----------|----------|------|------|--------|
（列出5-10个具体方案）

### 4.3 风险评估
| 风险项 | 影响程度 | 发生概率 | 缓解方案 |
|--------|----------|----------|----------|
（列出5个以上技术风险）

### 4.4 开发资源估算
- 团队规模建议
- 开发周期预估（MVP / V1.0 / V2.0）
- 基础设施成本估算（服务器、API调用等月度费用）

用中文输出""",
                self._research_system_prompt("技术架构评估专家")
            )
        except RuntimeError as e:
            await self._research_failed("技术可行性预研", e)
            raise

        self._save_artifact("1-4-技术可行性.md", sections["tech"], task_folder)
        await self.send_chat_message("老大，技术可行性我初步判断完了。")

        # ── 阶段 5/5：合成最终调研报告 ──
        await self.send_chat_message("我开始把结论合成市场调研报告。")
        await self.update_status(AgentStatus.WORKING, "合成最终报告...")

        # 拼接所有章节内容
        combined_content = f"""# {task_description} — 市场调研报告

{sections['market']}

{sections['users']}

{sections['demands']}

{sections['tech']}
"""

        # 生成结论
        try:
            conclusion = await self.think(
                f"""基于以下市场调研的所有分析结果，撰写最终结论和建议：

{combined_content[:6000]}

请输出：

## 五、结论与建议

### 5.1 核心发现
用3-5个要点总结最重要的发现（每个要点2-3句话）

### 5.2 产品方向建议
- 推荐的产品定位（一句话）
- 核心差异化策略
- 目标用户优先级（先打哪个群体）
- 商业模式建议
- MVP 功能范围建议

### 5.3 Go/No-Go 决策依据

**Go 的理由：**
1. ...
2. ...
3. ...

**风险和挑战：**
1. ...
2. ...
3. ...

**最终建议：** [Go / Conditional Go / No-Go]
理由说明（3-5句话）

### 5.4 下一步行动项
列出5个按优先级排序的下一步行动

用中文输出""",
                self._research_system_prompt("战略分析专家")
            )
        except RuntimeError as e:
            await self._research_failed("合成报告", e)
            raise

        # 组装最终报告
        final_report = combined_content + "\n\n" + conclusion

        # 质量校验
        quality_ok, quality_msg = self._validate_report_quality(final_report)
        if not quality_ok:
            await self.send_chat_message(f"老大，我检查到报告还差一点：{quality_msg}。我补一下。")
            # 尝试补充不足的部分
            try:
                supplement = await self.think(
                    f"""以下调研报告存在不足：{quality_msg}

请针对不足之处进行补充，要求内容详实、有数据支撑：

产品方向：{task_description}

当前报告摘要：
{final_report[:3000]}

请直接输出补充内容。""",
                    self._research_system_prompt("调研质量审核专家")
                )
                final_report += f"\n\n## 六、补充分析\n\n{supplement}"
            except RuntimeError:
                pass  # 补充失败不影响主流程

        self._save_artifact("1-Market_Research.md", final_report, task_folder)
        await self.send_chat_message(
            "老大，我完成了市场调研报告。",
            MessageType.ARTIFACT,
            {"filename": "1-Market_Research.md", "folder": task_folder}
        )
        await self.update_status(AgentStatus.IDLE)

    # ═══════════════════════════════════════════════════════
    #  竞品分析 — 多步流程
    # ═══════════════════════════════════════════════════════

    async def perform_competitive(self, task_description: str, task_folder: str):
        """多步竞品分析：识别竞品 → 逐个分析 → 对比矩阵 → 差异化策略"""
        await self.update_status(AgentStatus.THINKING, "竞品分析中...")
        await self.send_chat_message("收到，老大，我开始做竞品分析。")

        sections = {}

        # ── 阶段 1/3：识别竞品 & 逐个深度分析 ──
        await self.send_chat_message("我先识别核心竞品，并做第一轮拆解。")
        await self.update_status(AgentStatus.THINKING, "识别竞品...")
        try:
            sections["competitors"] = await self.think(
                f"""请对以下产品方向进行全面的竞品识别和深度分析：

{task_description}

要求：

## 一、竞品概览

### 1.1 竞品识别
列出以下三类竞品（共至少5-8个产品）：
- **直接竞品**（3个以上）：功能定位相同的产品
- **间接竞品**（2个以上）：解决相同需求但方式不同的产品
- **标杆产品**（1-2个）：值得学习的跨行业产品

### 1.2 竞品深度分析
对每个竞品，提供：

**[竞品名称]**
- 公司背景：公司名、成立时间、融资情况、团队规模
- 产品定位：一句话描述
- 核心功能：列出5-8个主要功能
- 目标用户：主要服务谁
- 商业模式：怎么赚钱
- 定价策略：具体价格区间
- 市场表现：用户量/下载量/营收（如有数据）
- 核心优势：2-3个突出优势
- 明显短板：2-3个不足
- 用户评价：用户最常提到的好评和差评

请提供详实的分析，每个竞品至少200字。
用中文输出""",
                self._research_system_prompt("竞品分析专家")
            )
        except RuntimeError as e:
            await self._research_failed("竞品识别", e)
            raise

        self._save_artifact("2-1-竞品深度分析.md", sections["competitors"], task_folder)
        await self.send_chat_message("老大，核心竞品我拆完了。")

        # ── 阶段 2/3：功能对比矩阵 & SWOT ──
        await self.send_chat_message("我继续做功能对比和 SWOT。")
        await self.update_status(AgentStatus.THINKING, "对比分析...")
        try:
            sections["comparison"] = await self.think(
                f"""基于以下竞品分析结果，创建功能对比矩阵和SWOT分析：

产品方向：{task_description}

竞品分析摘要：
{sections['competitors'][:3000]}

请输出：

## 二、竞品对比

### 2.1 功能对比矩阵
| 功能维度 | 我们的产品 | 竞品A | 竞品B | 竞品C | 竞品D |
|----------|-----------|-------|-------|-------|-------|
（列出15-20个功能维度，用 ✅/❌/🔶 标注支持程度）

### 2.2 定价对比
| 产品 | 免费版 | 基础版 | 专业版 | 企业版 |
|------|--------|--------|--------|--------|
（对比各竞品的定价策略）

### 2.3 SWOT 分析（针对我们的产品机会）
**Strengths（优势）：** 我们可以做到但竞品做不到/做不好的
**Weaknesses（劣势）：** 竞品已经做得很好而我们需要追赶的
**Opportunities（机会）：** 市场上还没有被满足的需求
**Threats（威胁）：** 潜在的竞争风险和市场变化

### 2.4 竞品评分雷达图数据
| 维度 | 竞品A | 竞品B | 竞品C | 我们目标 |
|------|-------|-------|-------|----------|
| 功能完整度 | | | | |
| 用户体验 | | | | |
| 技术创新 | | | | |
| 定价竞争力 | | | | |
| 市场占有率 | | | | |
| 品牌认知度 | | | | |
（1-10分评分）

用中文输出""",
                self._research_system_prompt("竞品对比分析专家")
            )
        except RuntimeError as e:
            await self._research_failed("对比分析", e)
            raise

        self._save_artifact("2-2-竞品对比.md", sections["comparison"], task_folder)
        await self.send_chat_message("老大，功能对比矩阵我做好了。")

        # ── 阶段 3/3：差异化策略 & 合成报告 ──
        await self.send_chat_message("我开始收束差异化策略和建议。")
        await self.update_status(AgentStatus.WORKING, "制定差异化策略...")
        try:
            sections["strategy"] = await self.think(
                f"""基于竞品分析和对比结果，提出差异化竞争策略：

产品方向：{task_description}

对比分析摘要：
{sections['comparison'][:2500]}

请输出：

## 三、差异化策略

### 3.1 市场定位建议
- 推荐的差异化定位（一句话）
- 为什么选择这个定位
- 与竞品的核心区隔

### 3.2 功能差异化策略
列出5个差异化功能方向：
1. **[功能方向]** — 描述 + 为什么竞品没做/做不好 + 用户价值
2. ...

### 3.3 商业模式创新
- 定价策略建议
- 增长策略建议
- 获客渠道建议

### 3.4 竞争壁垒构建
- 短期壁垒（0-6个月）
- 中期壁垒（6-18个月）
- 长期壁垒（18个月+）

## 四、总结与建议
### 4.1 Top 5 关键洞察
### 4.2 推荐行动计划

用中文输出""",
                self._research_system_prompt("商业策略专家")
            )
        except RuntimeError as e:
            await self._research_failed("差异化策略", e)
            raise

        # 合成最终竞品分析报告
        final_report = f"""# {task_description} — 竞品分析报告

{sections['competitors']}

{sections['comparison']}

{sections['strategy']}
"""

        self._save_artifact("2-Competitive_Analysis.md", final_report, task_folder)
        await self.send_chat_message(
            "老大，我完成了竞品分析报告。",
            MessageType.ARTIFACT,
            {"filename": "2-Competitive_Analysis.md", "folder": task_folder}
        )
        await self.update_status(AgentStatus.IDLE)

    async def perform_analysis(self, task_description: str, task_folder: str):
        """执行市场调研 + 竞品分析"""
        await self.perform_research(task_description, task_folder)
        await self.perform_competitive(task_description, task_folder)

    # ═══════════════════════════════════════════════════════
    #  内部辅助方法
    # ═══════════════════════════════════════════════════════

    def _research_system_prompt(self, expert_role: str) -> str:
        """生成调研专家的系统提示词"""
        return f"""你是一位资深的{expert_role}，拥有丰富的行业调研经验。

你的分析必须遵循以下原则：
1. **数据驱动**：尽可能给出具体数字、百分比、金额，不说空话
2. **结论明确**：不用"可能""也许""推测"等模糊词，直接给出判断
3. **逻辑严谨**：每个结论都要有论据支撑
4. **实操导向**：分析结果必须能指导实际决策
5. **深度优先**：宁可少覆盖几个点，也要每个点分析透彻

你区分用户的 Want（表面诉求）和 Need（底层需求），
用"广度 × 频度 × 强度"框架评估需求价值。

输出要求：
- 使用中文
- 结构清晰，使用 Markdown 格式
- 每个章节内容充实，至少200字
- 多用表格、列表等结构化形式呈现数据"""

    async def _research_failed(self, stage_name: str, error: Exception):
        """处理调研阶段失败"""
        await self.send_chat_message(f"老大，我在{stage_name}阶段卡住了：{error}")
        await self.update_status(AgentStatus.IDLE)

    def _validate_report_quality(self, report: str) -> tuple:
        """校验报告质量"""
        issues = []

        # 检查总体长度
        if len(report) < 3000:
            issues.append("报告内容过短，缺乏深度分析")

        # 检查关键章节是否存在
        required_sections = ["市场分析", "用户", "需求", "技术", "结论"]
        for section in required_sections:
            if section not in report:
                issues.append(f"缺少「{section}」相关章节")

        # 检查是否有数据支撑
        has_numbers = any(c.isdigit() for c in report)
        if not has_numbers:
            issues.append("报告缺少数字数据支撑")

        # 检查是否有表格
        if "|" not in report:
            issues.append("报告缺少对比表格")

        if issues:
            return False, "；".join(issues)
        return True, "质量合格"
