"""
OrchestratorAgent — AIky 编排器
分析用户意图，协调各 Agent 执行工作流
支持五种意图：
  - TASK: 正式工作任务（调研、竞品分析、PRD、开发…）
  - QA: 用户只是问问题/咨询，安排合适员工回答
  - STAGE_CONTROL: 继续/跳过/回退到某个工作阶段
  - COMMAND: 暂停/取消等控制指令
  - CHAT: 简单闲聊（兜底）
"""
import asyncio
import json
import os
import re
from typing import Dict, Any, Optional
from models import AgentRole, AgentStatus, Message, MessageType, Task, TaskIntent, TaskScope
from agents.base_agent import BaseAgent
from context_loader import build_context
from agents.worker_agents import get_last_artifact, read_artifact_content


# 范围 → 包含的阶段列表
STAGE_SEQUENCE = ["research", "competitive", "planning", "architecture", "execution", "testing"]

SCOPE_STAGES = {
    TaskScope.RESEARCH:    ["research"],
    TaskScope.COMPETITIVE: ["competitive"],
    TaskScope.ANALYSIS:    ["research", "competitive"],
    TaskScope.PLANNING:    ["research", "competitive", "planning"],
    TaskScope.FULL:        ["research", "competitive", "planning", "architecture", "execution", "testing"],
}

SCOPE_LABELS = {
    TaskScope.RESEARCH:    "仅市场调研",
    TaskScope.COMPETITIVE: "仅竞品分析",
    TaskScope.ANALYSIS:    "调研 + 竞品分析",
    TaskScope.PLANNING:    "调研 + 竞品 + PRD",
    TaskScope.FULL:        "完整流程",
}

# Agent 专长映射：用于问答路由
AGENT_EXPERTISE = {
    "ceo_01":  {"name": "CEO Steve",  "domains": ["市场趋势", "商业模式", "战略决策", "融资", "市场分析", "商业", "行业", "投资"]},
    "cto_01":  {"name": "CTO Elon",   "domains": ["技术架构", "选型", "性能", "安全", "技术栈", "后端架构", "部署", "数据库", "算法"]},
    "pm_01":   {"name": "PM Emma",    "domains": ["需求分析", "用户体验", "产品设计", "PRD", "功能规划", "用户故事", "产品"]},
    "ui_01":   {"name": "UI Alex",    "domains": ["界面设计", "交互", "视觉", "配色", "布局", "UI", "UX", "设计规范"]},
    "fe_01":   {"name": "FE Lucas",   "domains": ["前端开发", "Vue", "React", "CSS", "JavaScript", "HTML", "响应式", "组件"]},
    "be_01":   {"name": "BE David",   "domains": ["后端开发", "API", "Python", "Node", "微服务", "数据库", "服务器"]},
    "qa_01":   {"name": "QA Sarah",   "domains": ["测试", "质量保证", "自动化测试", "Bug", "测试用例", "性能测试"]},
}

DIRECT_AGENT_ALIASES = {
    "aiky": "aiky_main",
    "brain": "aiky_main",
    "steve": "ceo_01",
    "ceo": "ceo_01",
    "emma": "pm_01",
    "pm": "pm_01",
    "product": "pm_01",
    "elon": "cto_01",
    "cto": "cto_01",
    "alex": "ui_01",
    "ui": "ui_01",
    "ux": "ui_01",
    "lucas": "fe_01",
    "fe": "fe_01",
    "frontend": "fe_01",
    "front": "fe_01",
    "david": "be_01",
    "be": "be_01",
    "backend": "be_01",
    "sarah": "qa_01",
    "qa": "qa_01",
    "test": "qa_01",
}

DIRECT_ARTIFACT_KEYWORDS = [
    "生成页面", "做页面", "实现页面", "开发页面", "写页面", "html", "demo", "原型",
    "prd", "需求文档", "测试用例", "接口文档", "api 文档", "api文档", "架构文档",
    "设计方案", "ui", "ui设计", "界面设计", "视觉设计", "重新设计", "设计一下",
    "产出文档", "保存成文档",
]

REVISION_KEYWORDS = [
    "修改", "改一下", "调整", "优化", "重做", "重新", "修复", "修一下",
    "不行", "不对", "有问题", "空白", "打不开", "打开是空白", "上一个",
    "刚才", "这个页面", "这个产物", "继续改", "再改",
]

DERIVATIVE_ARTIFACT_KEYWORDS = [
    "写测试用例", "测试用例", "生成测试", "qa", "测试点", "验收用例",
    "检查", "审查", "评审", "review", "分析", "总结", "说明文档",
    "写prd", "prd", "需求文档", "产品方案", "用户故事", "验收标准",
    "设计方案", "ui方案", "视觉方案", "原型", "交互方案", "界面方案",
    "写页面", "生成页面", "做页面", "实现页面", "前端", "html", "demo",
    "接口文档", "api文档", "api 文档", "后端方案", "数据库设计", "服务设计",
    "架构文档", "架构方案", "技术方案", "技术选型",
    "市场分析", "调研", "竞品", "竞品分析", "商业分析",
    "基于上一个", "基于上次", "基于刚才", "根据上一个", "根据上次",
]

DERIVATIVE_AGENT_RULES = [
    ("qa_01", ["测试", "qa", "用例", "验收", "bug", "缺陷", "质量"]),
    ("ceo_01", ["市场", "市场分析", "调研", "竞品", "竞品分析", "商业", "商业分析", "战略", "行业", "增长"]),
    ("cto_01", ["架构", "技术方案", "技术选型", "性能", "安全", "部署", "扩展"]),
    ("be_01", ["后端", "接口", "api", "数据库", "服务", "权限", "表结构", "接口文档"]),
    ("pm_01", ["prd", "需求", "产品", "用户故事", "验收标准", "产品方案"]),
    ("ui_01", ["ui", "ux", "视觉", "设计", "原型", "界面", "交互方案", "设计方案", "配色"]),
    ("fe_01", ["前端", "html", "页面", "demo", "组件", "交互实现", "vue", "react", "css", "javascript"]),
]

MODIFICATION_KEYWORDS = [
    "修改", "改一下", "调整", "优化", "重做", "重新", "修复", "修一下",
    "不行", "不对", "有问题", "空白", "打不开", "打开是空白",
    "继续改", "再改", "替换", "覆盖",
]

PREVIOUS_ARTIFACT_KEYWORDS = [
    "上一个", "上次", "刚才", "上一份", "上一个输出物", "上一个产物",
    "这个页面", "这个产物", "当前页面", "当前产物",
]

NEW_CONTEXT_PATTERNS = [
    r"\[\[AIKY_IMAGE:",
    r"###\s*上下文\s+\d+:\s*image",
    r"以下图片将作为视觉输入",
    r"(?:读取|打开|查看|基于|参考).{0,12}(?:图片|图像|截图|文件)",
    r"(?:[a-zA-Z]:\\|/)[^\s，。；;]+?\.(?:png|jpe?g|webp|gif|bmp|svg|html?|md|txt|pdf)",
]

# 阶段名称映射
STAGE_NAMES = {
    "research": "市场调研",
    "competitive": "竞品分析",
    "planning": "PRD",
    "architecture": "架构设计",
    "execution": "开发实现",
    "testing": "测试验收",
}

ROLE_ACCEPTANCE_MESSAGES = {
    AgentRole.AIKY_MAIN: "收到，老大，我来统筹。",
    AgentRole.CEO: "收到，老大，我来判断市场和商业面。",
    AgentRole.PRODUCT_MANAGER: "收到，老大，我来整理需求和 PRD。",
    AgentRole.CTO: "收到，老大，我来梳理技术方案。",
    AgentRole.UI_DESIGNER: "收到，老大，我来做界面方案。",
    AgentRole.FRONTEND_DEV: "收到，老大，我来实现前端。",
    AgentRole.BACKEND_DEV: "收到，老大，我来梳理后端和接口。",
    AgentRole.QA_ENGINEER: "收到，老大，我来检查质量和测试点。",
}

START_STAGE_ALIASES = {
    "调研": "research",
    "市场调研": "research",
    "research": "research",
    "竞品": "competitive",
    "竞品分析": "competitive",
    "competitive": "competitive",
    "prd": "planning",
    "PRD": "planning",
    "需求": "planning",
    "产品规划": "planning",
    "planning": "planning",
    "架构": "architecture",
    "架构设计": "architecture",
    "architecture": "architecture",
    "代码": "execution",
    "开发": "execution",
    "实现": "execution",
    "代码实现": "execution",
    "开发实现": "execution",
    "execution": "execution",
    "测试": "testing",
    "测试验收": "testing",
    "qa": "testing",
    "QA": "testing",
    "testing": "testing",
}

CUSTOM_STAGE_MARKERS = [
    "指定阶段", "自定义阶段", "几个阶段", "只跑", "仅跑", "只做", "仅做",
    "只执行", "仅执行", "不用所有阶段", "不要完整跑", "不完整跑",
    "不用完整跑", "阶段：", "阶段:",
]

# LLM 意图识别系统提示词
INTENT_SYSTEM_PROMPT = """你是 AI助手/小K 的意图识别模块。根据用户输入，判断其真实意图。

## 上下文信息
{context}

## 输出要求
请以 JSON 格式输出，不要包含其他内容：

### 意图类型（intent）：
- "task": 用户要求执行一项正式的工作任务（如"帮我做个调研"、"分析一下教育市场"、"做一个登录页"）
- "qa": 用户只是在问问题、咨询、请教（如"什么是微服务？"、"Vue和React哪个好？"、"这个项目用什么技术栈比较好？"、"你觉得怎么样？"）
- "stage_control": 用户想继续、跳过或回退到某个工作阶段（如"继续"、"下一步"、"跳过竞品分析"、"回到调研阶段"、"直接开发"）
- "command": 用户想暂停、停止或取消当前工作（如"暂停"、"停止"、"取消"）

### 对于 task 意图，还需要判断 scope：
- "research": 仅做市场调研
- "competitive": 仅做竞品分析
- "analysis": 调研 + 竞品分析
- "planning": 调研 + 竞品 + PRD
- "full": 完整流程

### 对于 qa 意图，还需要判断 best_agent（最适合回答的人）：
- "ceo_01": 市场/商业/战略相关
- "cto_01": 技术架构/选型/性能相关
- "pm_01": 产品需求/用户体验相关
- "ui_01": 界面设计/交互/视觉相关
- "fe_01": 前端开发相关
- "be_01": 后端开发相关
- "qa_01": 测试/质量相关
- "aiky_main": 通用问题/无法归类

### 对于 stage_control 意图，还需要判断：
- "action": "continue"(继续下一步) | "skip_to"(跳到指定阶段) | "go_back"(回退到指定阶段)
- "target_stage": 目标阶段名（research/competitive/planning/architecture/execution/testing），如果是continue则留空

## JSON 格式示例
{{"intent": "task", "scope": "research"}}
{{"intent": "qa", "best_agent": "cto_01", "question_summary": "关于技术选型的咨询"}}
{{"intent": "stage_control", "action": "continue", "target_stage": ""}}
{{"intent": "stage_control", "action": "skip_to", "target_stage": "execution"}}
{{"intent": "command"}}
"""


class OrchestratorAgent(BaseAgent):
    def __init__(self, agent_id: str = "aiky_main", name: str = "AI助手/小K"):
        super().__init__(agent_id, name, AgentRole.AIKY_MAIN, ["management", "planning", "Senior PM"])
        self.active_tasks: Dict[str, Task] = {}

    async def handle_message(self, message: Message):
        print(f"[Orchestrator] Received from {message.sender_id}: {message.content[:50]}...")

    async def analyze_intent(self, user_input: str, current_task: Optional[Task] = None) -> Dict[str, Any]:
        """使用 LLM 智能分析用户意图"""

        # 先尝试快速规则匹配（减少不必要的 LLM 调用）
        quick_result = self._quick_intent_check(user_input, current_task)
        if quick_result:
            return quick_result

        # 需要 LLM 分析时才显示"正在理解"
        await self.send_chat_message("我先理解一下你的意思。")

        # 构建上下文信息
        context_parts = []
        if current_task and current_task.status == "waiting_for_confirm":
            stages = self._get_task_stages(current_task)
            stage_idx = stages.index(current_task.approval_stage) if current_task.approval_stage in stages else -1
            context_parts.append(f"当前有进行中的任务：「{current_task.title}」")
            context_parts.append(f"当前阶段：{STAGE_NAMES.get(current_task.approval_stage, current_task.approval_stage)}")
            context_parts.append(f"任务状态：等待用户审批确认")
            remaining = [STAGE_NAMES.get(s, s) for s in stages[stage_idx+1:]] if stage_idx >= 0 else []
            if remaining:
                context_parts.append(f"后续阶段：{' → '.join(remaining)}")
        elif current_task and current_task.status in ("pending", "in_progress"):
            context_parts.append(f"当前有进行中的任务：「{current_task.title}」，状态：{current_task.status}")
        else:
            context_parts.append("当前没有进行中的任务")

        context = "\n".join(context_parts) if context_parts else "无特殊上下文"

        # LLM 智能分析
        prompt = INTENT_SYSTEM_PROMPT.format(context=context)
        try:
            response = await self.think(user_input, prompt)
            result = self._parse_intent_response(response)
            if result:
                return result
        except Exception as e:
            print(f"[Orchestrator] LLM intent analysis failed: {e}, falling back to rules")

        # LLM 失败时的兜底规则匹配
        return self._fallback_intent(user_input, current_task)

    def _quick_intent_check(self, user_input: str, current_task: Optional[Task]) -> Optional[Dict[str, Any]]:
        """快速规则匹配，对明确意图直接返回，避免 LLM 调用"""
        lower = user_input.lower().strip()
        clean = lower.strip("。！!.~～")

        # 控制命令：非常明确的停止/取消
        stop_words = ["stop", "pause", "halt", "cancel", "暂停", "停止", "取消"]
        if lower in stop_words or (len(lower) < 6 and any(w == lower for w in stop_words)):
            return {"intent": TaskIntent.COMMAND, "scope": TaskScope.FULL}

        # 简单问候/闲聊：秒回，不走 LLM
        greetings = ["你好", "hello", "hi", "hey", "嗨", "哈喽", "在吗", "在不在",
                     "早上好", "下午好", "晚上好", "早", "good morning", "good afternoon",
                     "你好啊", "嘿", "哈啰", "hello!", "hi!", "你好!", "nihao"]
        if clean in greetings or lower in greetings:
            return {
                "intent": TaskIntent.QA,
                "best_agent": "aiky_main",
                "question_summary": "打招呼",
                "scope": TaskScope.FULL,
                "_greeting": True,  # 标记为问候，assign_task 中直接回复
            }

        # 极短输入且无实质内容 → 当闲聊处理
        trivial_words = ["哦", "噢", "嗯嗯", "好吧", "知道了", "了解", "明白",
                         "谢谢", "感谢", "thanks", "thx", "ok", "好的", "收到"]
        if clean in trivial_words:
            return {
                "intent": TaskIntent.QA,
                "best_agent": "aiky_main",
                "question_summary": "简单回应",
                "scope": TaskScope.FULL,
                "_greeting": True,
            }

        # 阶段控制：明确的"继续"/"下一步"（有等待审批的任务时）
        if current_task and current_task.status == "waiting_for_confirm":
            continue_words = ["继续", "下一步", "好的", "ok", "yes", "确认", "通过", "批准",
                              "可以", "没问题", "go", "next", "approve", "好", "行", "嗯", "对"]
            if clean in continue_words:
                return {
                    "intent": TaskIntent.STAGE_CONTROL,
                    "action": "continue",
                    "target_stage": ""
                }

        return None  # 无法快速判断，需要 LLM

    def _parse_intent_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 返回的 JSON 意图"""
        try:
            # 尝试从响应中提取 JSON
            text = response.strip()
            # 处理 markdown 代码块包裹
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    text = text[start:end]
            elif text.startswith("{"):
                pass
            else:
                # 尝试找到 JSON 部分
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    text = text[start:end]

            data = json.loads(text)
            intent_str = data.get("intent", "task")

            if intent_str == "task":
                scope_str = data.get("scope", "full")
                scope_map = {s.value: s for s in TaskScope}
                scope = scope_map.get(scope_str, TaskScope.FULL)
                return {"intent": TaskIntent.TASK, "scope": scope}

            elif intent_str == "qa":
                return {
                    "intent": TaskIntent.QA,
                    "best_agent": data.get("best_agent", "aiky_main"),
                    "question_summary": data.get("question_summary", ""),
                    "scope": TaskScope.FULL,
                }

            elif intent_str == "stage_control":
                return {
                    "intent": TaskIntent.STAGE_CONTROL,
                    "action": data.get("action", "continue"),
                    "target_stage": data.get("target_stage", ""),
                    "scope": TaskScope.FULL,
                }

            elif intent_str == "command":
                return {"intent": TaskIntent.COMMAND, "scope": TaskScope.FULL}

            else:
                return {"intent": TaskIntent.TASK, "scope": TaskScope.FULL}

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[Orchestrator] Failed to parse intent JSON: {e}")
            return None

    def _fallback_intent(self, user_input: str, current_task: Optional[Task]) -> Dict[str, Any]:
        """LLM 失败时的兜底关键词匹配"""
        lower = user_input.lower()

        # 问号结尾 → 可能是问答
        if user_input.rstrip().endswith(("?", "？")) and len(user_input) < 100:
            return {"intent": TaskIntent.QA, "best_agent": "aiky_main", "question_summary": user_input, "scope": TaskScope.FULL}

        # 关键词匹配工作范围
        scope_keywords = [
            (TaskScope.COMPETITIVE, ["竞品分析", "竞品", "competitive", "竞争分析", "竞争对手"], []),
            (TaskScope.RESEARCH, ["调研", "市场调研", "research", "市场分析", "行业分析"], ["竞品", "开发", "实现"]),
            (TaskScope.ANALYSIS, ["分析", "analysis"], ["开发", "实现", "设计", "写", "code"]),
            (TaskScope.PLANNING, ["需求", "prd", "规划", "产品设计", "需求文档"], []),
        ]

        for scope, must_match, must_not in scope_keywords:
            has_match = any(w in lower for w in must_match)
            has_exclude = any(w in lower for w in must_not) if must_not else False
            if has_match and not has_exclude:
                return {"intent": TaskIntent.TASK, "scope": scope}

        return {"intent": TaskIntent.TASK, "scope": TaskScope.FULL}

    def _parse_direct_agent_mention(self, user_input: str) -> Optional[Dict[str, str]]:
        """Parse @employee direct assignment such as @sarah / @lucas."""
        pattern = re.compile(r"(^|[\s,，])[@＠]([a-zA-Z][\w-]*|[\u4e00-\u9fff]+)", re.IGNORECASE)
        match = pattern.search(user_input or "")
        if not match:
            return None

        alias = match.group(2).strip().lower()
        agent_id = DIRECT_AGENT_ALIASES.get(alias)
        if not agent_id:
            return None

        cleaned = pattern.sub(lambda m: m.group(1), user_input, count=1).strip()
        cleaned = re.sub(r"^[,，、:：\s]+", "", cleaned).strip()
        return {"agent_id": agent_id, "alias": alias, "content": cleaned or user_input.strip()}

    def _is_direct_artifact_task(self, content: str) -> bool:
        lower = (content or "").lower()
        return any(keyword in lower for keyword in DIRECT_ARTIFACT_KEYWORDS)

    def _mentions_previous_artifact(self, content: str) -> bool:
        lower = (content or "").lower()
        return any(keyword in lower for keyword in PREVIOUS_ARTIFACT_KEYWORDS)

    def _has_new_external_context(self, content: str) -> bool:
        text = content or ""
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in NEW_CONTEXT_PATTERNS)

    def _is_new_context_artifact_task(self, content: str) -> bool:
        lower = (content or "").lower()
        if not self._has_new_external_context(content) or self._mentions_previous_artifact(content):
            return False
        creation_intent = [
            "生成", "做", "实现", "设计", "重新设计", "复刻", "还原", "参考", "html",
            "页面", "ui", "原型", "测试用例", "prd", "文档", "方案",
        ]
        return any(keyword in lower for keyword in creation_intent)

    def _is_revision_request(self, content: str) -> bool:
        lower = (content or "").lower()
        if self._is_derivative_artifact_request(content):
            return False
        if self._is_new_context_artifact_task(content):
            return False
        return any(keyword.lower() in lower for keyword in REVISION_KEYWORDS)

    def _is_derivative_artifact_request(self, content: str) -> bool:
        lower = (content or "").lower()
        mentions_previous = self._mentions_previous_artifact(content)
        has_derivative = any(keyword.lower() in lower for keyword in DERIVATIVE_ARTIFACT_KEYWORDS)
        has_modify = any(keyword.lower() in lower for keyword in MODIFICATION_KEYWORDS)
        return mentions_previous and has_derivative and not has_modify

    def _select_derivative_agent(self, content: str, artifact: Dict[str, Any], preferred_agent_id: str = "") -> str:
        if preferred_agent_id and preferred_agent_id != "aiky_main":
            return preferred_agent_id

        lower = (content or "").lower()
        best = {"score": 0, "agent_id": ""}
        for agent_id, keywords in DERIVATIVE_AGENT_RULES:
            score = sum(3 for keyword in keywords if keyword.lower() in lower)
            domains = AGENT_EXPERTISE.get(agent_id, {}).get("domains", [])
            score += sum(1 for domain in domains if str(domain).lower() in lower)
            if score > best["score"]:
                best = {"score": score, "agent_id": agent_id}

        if best["agent_id"]:
            return best["agent_id"]

        return artifact.get("agent_id") or "fe_01"

    def _with_previous_artifact_context(self, content: str, artifact: Dict[str, Any]) -> str:
        artifact_content = read_artifact_content(artifact)
        if not artifact_content:
            return content
        max_chars = 50000
        if len(artifact_content) > max_chars:
            artifact_content = (
                artifact_content[: max_chars // 2]
                + "\n\n...[上一个产物内容过长，系统已截断中间部分]...\n\n"
                + artifact_content[-max_chars // 2:]
            )
        return f"""{content}

---
以下是用户提到的上一个产物，请把它作为输入材料，不要直接修改原文件，除非用户明确要求修改/覆盖：
你需要根据自己的岗位职责生成一个新的产出物。

文件名：{artifact.get('filename', '')}
文件类型：{artifact.get('type', '')}

```{ 'html' if artifact.get('type') == 'html' else 'text' }
{artifact_content}
```"""

    async def _handle_artifact_revision(self, task: Task, available_agents: Dict[str, "BaseAgent"], content: str) -> bool:
        artifact = get_last_artifact()
        if not artifact or not self._is_revision_request(content):
            return False

        agent_id = artifact.get("agent_id") or "fe_01"
        agent = available_agents.get(agent_id)
        if not agent or not hasattr(agent, "revise_artifact"):
            return False

        task.status = "in_progress"
        task.assigned_to = agent_id
        await self.send_chat_message(
            f"老大，我会基于上一个产物 `{artifact.get('filename', '')}` 继续改，交回给 **{agent.state.name}**。"
        )
        await agent.revise_artifact(content, artifact)
        task.status = "completed"
        await self.update_status(AgentStatus.IDLE)
        return True

    async def _handle_artifact_derivative(self, task: Task, available_agents: Dict[str, "BaseAgent"], content: str) -> bool:
        artifact = get_last_artifact()
        if not artifact or not self._is_derivative_artifact_request(content):
            return False

        agent_id = self._select_derivative_agent(content, artifact)
        agent = available_agents.get(agent_id)
        if not agent or not hasattr(agent, "perform_work"):
            return False

        task.status = "in_progress"
        task.assigned_to = agent_id
        self._ensure_task_workspace(task)
        agent.state.current_folder = task.folder_path
        await self.send_chat_message(
            f"老大，我会让 **{agent.state.name}** 基于上一个产物 `{artifact.get('filename', '')}` 生成新的输出，不会修改原文件。"
        )
        await agent.perform_work(self._with_previous_artifact_context(content, artifact))
        task.status = "completed"
        await self.update_status(AgentStatus.IDLE)
        return True

    def _parse_start_stage(self, user_input: str) -> Optional[str]:
        text = user_input or ""
        aliases = sorted(START_STAGE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
        for alias, stage in aliases:
            alias_re = re.escape(alias)
            patterns = [
                rf"(?:直接从|从|由|自|跳到|进入)\s*{alias_re}\s*(?:阶段|开始|做起|执行)?",
                rf"跳过.+?从\s*{alias_re}\s*(?:阶段|开始|做起|执行)?",
            ]
            if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
                return stage
        return None

    def _parse_requested_stages(self, user_input: str) -> Optional[list]:
        text = user_input or ""
        lower = text.lower()
        has_marker = any(marker.lower() in lower for marker in CUSTOM_STAGE_MARKERS)
        has_stage_list = re.search(r"(?:跑|做|执行).{0,20}(?:和|、|,|，).{0,20}(?:阶段|prd|PRD|架构|测试|开发|竞品|调研)", text)
        if not has_marker and not has_stage_list:
            return None

        segments = re.split(r"[。；;\n]", text)
        stage_segments = []
        for segment in segments:
            segment_lower = segment.lower()
            starts = [
                idx for marker in CUSTOM_STAGE_MARKERS
                if (idx := segment_lower.find(marker.lower())) >= 0
            ]
            list_match = re.search(r"(?:跑|做|执行).{0,20}(?:和|、|,|，).{0,20}(?:阶段|prd|PRD|架构|测试|开发|竞品|调研)", segment)
            if list_match:
                starts.append(list_match.start())
            if starts:
                snippet = segment[min(starts):]
                snippet = re.split(r"(?:读取|基于文件|file\s*:|https?://)", snippet, maxsplit=1, flags=re.IGNORECASE)[0]
                stage_segments.append(snippet)
        stage_text = " ".join(stage_segments)
        if not stage_text.strip():
            return None

        found = set()
        aliases = sorted(START_STAGE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
        for alias, stage in aliases:
            alias_re = re.escape(alias)
            if re.search(alias_re, stage_text, flags=re.IGNORECASE):
                found.add(stage)

        stages = [stage for stage in STAGE_SEQUENCE if stage in found]
        return stages or None

    def _get_task_stages(self, task: Task) -> list:
        return task.selected_stages or SCOPE_STAGES.get(task.scope, [])

    async def _load_external_context(self, text: str) -> str:
        context = await asyncio.to_thread(build_context, text)
        if context.get("summary"):
            details = context["summary"]
            image_count = len([item for item in context.get("items", []) if item.get("kind") == "image"])
            failed = context.get("failed", [])
            if image_count:
                try:
                    from llm.glm_client import LLMClient
                    details += f"\n视觉输入将发送给模型：{LLMClient._load_config().get('model', '未配置')}"
                except Exception:
                    pass
            if failed and not context.get("items"):
                details += "\n" + "\n".join(
                    f"- {item.get('source', '')}：{item.get('error', '')}"
                    for item in failed[:3]
                )
                await self.send_chat_message(f"📚 老大，材料这次没读成功。\n{details}")
            else:
                await self.send_chat_message(f"📚 老大，我已经把材料读进来了。\n{details}")
        return context.get("text") or text

    def _ensure_task_workspace(self, task: Task) -> str:
        workspace_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workspace")
        safe_title = "".join([
            c if c.isalnum() or c in "一二三四五六七八九十" or '\u4e00' <= c <= '\u9fff' else "_"
            for c in task.title[:20]
        ])
        task.folder_path = os.path.join(workspace_dir, f"{task.id}_{safe_title}")
        if not os.path.exists(task.folder_path):
            os.makedirs(task.folder_path)
        return task.folder_path

    def _employee_task_packet(self, task: Task, stage_goal: str, employee_instruction: str = "", source_text: str = "") -> str:
        """Build a lossless task packet for employees.

        Intent rules decide routing only. The employee should still see the
        user's original requirement and any loaded context as the source of truth.
        """
        original = source_text or task.description
        stage_label = STAGE_NAMES.get(task.approval_stage or "", task.approval_stage or "直派任务")
        extra = f"\n\n### 当前员工补充指令\n{employee_instruction.strip()}" if employee_instruction.strip() else ""
        return f"""# AI助手/小K 员工任务包

### 用户原始要求（最高优先级）
{original}

### 当前阶段/路由
{stage_label}

### 当前员工目标
{stage_goal}
{extra}

### 执行要求
- 必须完整理解并遵循“用户原始要求”，不要只根据阶段名、枚举意图或简短摘要执行。
- 如果“当前员工目标”和“用户原始要求”有冲突，以用户原始要求为准。
- 如果用户提供了文件、图片、网页或上一个产物上下文，必须把这些材料作为输入依据。
- 只输出你这个岗位应交付的产物或结论，不要解释编排过程。"""

    async def _handle_direct_assignment(self, task: Task, available_agents: Dict[str, "BaseAgent"], direct: Dict[str, str]):
        agent_id = direct["agent_id"]
        agent = available_agents.get(agent_id)
        if not agent:
            await self.send_chat_message(f"老大，我没找到 @{direct['alias']} 这个员工，暂时没法直派。")
            task.status = "failed"
            await self.update_status(AgentStatus.IDLE)
            return

        content = direct.get("content") or task.description
        task.assigned_to = agent_id
        task.status = "in_progress"

        await self.send_chat_message(
            f"📌 老大，我把这件事交给 **{agent.state.name}** 直接处理。\n"
            f"来源：@{direct['alias']}，不会进入 PE 自动阶段分派。"
        )

        try:
            artifact = get_last_artifact()
            if agent_id != "aiky_main" and artifact and self._is_derivative_artifact_request(content) and hasattr(agent, "perform_work"):
                target_agent_id = self._select_derivative_agent(content, artifact, preferred_agent_id=agent_id)
                if target_agent_id != agent_id and target_agent_id in available_agents:
                    agent_id = target_agent_id
                    agent = available_agents[agent_id]
                await self.send_chat_message(
                    f"老大，我会让 **{agent.state.name}** 基于上一个产物 `{artifact.get('filename', '')}` 生成新的输出，不会修改原文件。"
                )
                self._ensure_task_workspace(task)
                agent.state.current_folder = task.folder_path
                await agent.perform_work(self._with_previous_artifact_context(content, artifact))
            elif agent_id != "aiky_main" and hasattr(agent, "perform_work") and (
                self._is_direct_artifact_task(content) or self._is_new_context_artifact_task(content)
            ):
                self._ensure_task_workspace(task)
                agent.state.current_folder = task.folder_path
                await agent.perform_work(
                    self._employee_task_packet(
                        task,
                        "完成用户通过 @ 指派的产物任务。",
                        "这是直派任务，不要因为历史产物存在就自动修改上一个文件，除非用户明确说修改上一个产物。",
                        source_text=content,
                    )
                )
            elif agent_id != "aiky_main" and artifact and self._is_revision_request(content) and hasattr(agent, "revise_artifact"):
                await self.send_chat_message(
                    f"老大，我会让 **{agent.state.name}** 直接修改上一个产物 `{artifact.get('filename', '')}`。"
                )
                await agent.revise_artifact(content, artifact)
            else:
                await agent.update_status(AgentStatus.THINKING, "处理直派任务")
                await agent.send_chat_message(
                    ROLE_ACCEPTANCE_MESSAGES.get(agent.state.role, "收到，老大，我来处理。")
                )
                domains = AGENT_EXPERTISE.get(agent_id, {}).get("domains", ["通用协作"])
                direct_prompt = f"""你是 {agent.state.name}，职位是 {agent.state.role.value}。
这是用户通过 @{direct['alias']} 明确指派给你的任务，请你直接完成，不要改派给其他员工。

你的专业领域：{', '.join(domains)}

要求：
- 用中文回答
- 先完成用户明确要求，再补充必要判断
- 如果系统上下文里有网页、文件正文或图片视觉输入，优先基于上下文回答；如果读取失败，不要假装已经读到
- 不要启动 PE 流程，不要输出“市场调研/竞品分析”等阶段说明，除非用户明确要求"""

                answer = await agent.think(content, direct_prompt)
                await agent.send_chat_message(answer)
                await agent.update_status(AgentStatus.IDLE)

            task.status = "completed"
            await self.update_status(AgentStatus.IDLE)
        except Exception as e:
            task.status = "failed"
            await agent.send_chat_message(f"老大，我这次直派任务没跑通：{str(e)}")
            await agent.update_status(AgentStatus.IDLE)
            await self.update_status(AgentStatus.IDLE)

    async def assign_task(self, task: Task, available_agents: Dict[str, "BaseAgent"]):
        """接收用户指令，智能路由到对应处理流程"""
        await self.update_status(AgentStatus.THINKING, "分析用户意图")
        original_description = task.description

        # 查找当前是否有等待确认的任务（用于阶段控制）
        current_active_task = None
        from models import Task as TaskModel
        # 从全局系统状态中查找（通过 available_agents 反向获取）
        # 注意：这里 task 是新创建的，但可能有旧的等待确认任务
        for existing_task in self.active_tasks.values():
            if existing_task.status == "waiting_for_confirm":
                current_active_task = existing_task
                break

        direct = self._parse_direct_agent_mention(original_description)
        if direct:
            direct["content"] = await self._load_external_context(direct["content"])
            await self._handle_direct_assignment(task, available_agents, direct)
            return

        if await self._handle_artifact_derivative(task, available_agents, original_description):
            return

        if self._is_revision_request(original_description):
            revision_description = await self._load_external_context(original_description)
            if await self._handle_artifact_revision(task, available_agents, revision_description):
                return

        requested_stages = self._parse_requested_stages(original_description)
        start_stage = self._parse_start_stage(original_description)
        task.description = await self._load_external_context(original_description)

        # LLM 智能意图分析
        analysis = await self.analyze_intent(original_description, current_active_task)
        task.intent = analysis.get("intent", TaskIntent.TASK)

        # ========= 问答意图 =========
        if task.intent == TaskIntent.QA:
            await self._handle_qa(task, available_agents, analysis)
            return

        # ========= 阶段控制意图 =========
        if task.intent == TaskIntent.STAGE_CONTROL:
            await self._handle_stage_control(task, available_agents, analysis, current_active_task)
            return

        # ========= 控制命令 =========
        if task.intent == TaskIntent.COMMAND:
            await self.send_chat_message("🛑 收到控制指令，已暂停当前工作。")
            task.status = "completed"
            # 如果有进行中的任务也标记暂停
            for t in self.active_tasks.values():
                if t.status in ("pending", "in_progress", "waiting_for_confirm"):
                    t.status = "paused"
            await self.update_status(AgentStatus.IDLE)
            return

        # ========= 正式工作任务 =========
        task.scope = analysis.get("scope", TaskScope.FULL)
        if requested_stages:
            task.selected_stages = requested_stages
            task.scope = TaskScope.FULL

        # 创建工作目录
        self._ensure_task_workspace(task)

        stages = self._get_task_stages(task)
        if start_stage and start_stage not in stages:
            task.scope = TaskScope.FULL
            if not requested_stages:
                stages = self._get_task_stages(task)
        label = "自定义阶段" if task.selected_stages else SCOPE_LABELS.get(task.scope, task.scope.value)
        start_index = stages.index(start_stage) if start_stage in stages else 0

        await self.send_chat_message(
            f"📋 老大，我把流程拆好了。\n"
            f"• 范围：{label}\n"
            f"• 起点：{STAGE_NAMES.get(stages[start_index], stages[start_index])}\n"
            f"• 阶段：{' → '.join([STAGE_NAMES.get(s, s) for s in stages[start_index:]])}"
        )

        # 记录活跃任务
        self.active_tasks[task.id] = task

        # 开始执行第一个阶段
        await self._run_next_stage(task, available_agents, stage_index=start_index)

    async def _handle_qa(self, task: Task, available_agents: Dict[str, "BaseAgent"], analysis: Dict):
        """处理问答意图：选择最合适的员工回答用户问题"""

        # 简单问候/闲聊：直接秒回，不调用 LLM
        if analysis.get("_greeting"):
            summary = analysis.get("question_summary", "")
            if summary == "打招呼":
                await self.send_chat_message("老大，我在。你直接说要做什么就行，我来安排。")
            else:
                await self.send_chat_message("收到，老大。")
            task.status = "completed"
            await self.update_status(AgentStatus.IDLE)
            return

        best_agent_id = analysis.get("best_agent", "aiky_main")
        question = task.description

        agent = available_agents.get(best_agent_id)
        if not agent or best_agent_id == "aiky_main":
            # AIky 自己回答
            agent = available_agents.get("aiky_main") or self
            agent_info = "AI助手/小K"
        else:
            agent_info = AGENT_EXPERTISE.get(best_agent_id, {}).get("name", agent.state.name)

        await self.send_chat_message(f"老大，这个问题我让 **{agent_info}** 来回答。")

        # 由选中的 Agent 调用 LLM 回答
        try:
            await agent.update_status(AgentStatus.THINKING, f"思考{analysis.get('question_summary', '问题')}")

            qa_prompt = f"""你是 {agent.state.name}，职位是 {agent.state.role.value}。
你的专业领域是：{', '.join(AGENT_EXPERTISE.get(best_agent_id, {}).get('domains', ['通用']))}。

用户向你提出了一个问题，请用你的专业知识给出有价值的回答。
要求：
- 用中文回答
- 专业但易懂
- 如果问题超出你的专业范围，也尽力给出建议
- 回答要实用、有深度，不要泛泛而谈
- 适当使用 markdown 格式让回答更清晰"""

            answer = await agent.think(question, qa_prompt)
            await agent.send_chat_message(answer)
            await agent.update_status(AgentStatus.IDLE)

        except Exception as e:
            await agent.send_chat_message(f"老大，我回答时出错了：{str(e)}")
            await agent.update_status(AgentStatus.IDLE)

        task.status = "completed"
        await self.update_status(AgentStatus.IDLE)

    async def _handle_stage_control(self, task: Task, available_agents: Dict[str, "BaseAgent"],
                                     analysis: Dict, current_active_task: Optional[Task]):
        """处理阶段控制意图：继续/跳过/回退"""
        action = analysis.get("action", "continue")
        target_stage = analysis.get("target_stage", "")

        # 找到需要控制的任务
        target_task = current_active_task
        if not target_task:
            # 也看看新提交的这个 task 的 parent 或者最近的活跃任务
            for t in reversed(list(self.active_tasks.values())):
                if t.status in ("waiting_for_confirm", "in_progress", "paused"):
                    target_task = t
                    break

        if not target_task:
            await self.send_chat_message("老大，现在没有正在跑的任务。你直接把新需求发我就行。")
            task.status = "completed"
            await self.update_status(AgentStatus.IDLE)
            return

        stages = self._get_task_stages(target_task)

        if action == "continue":
            # 等同于审批通过，继续下一阶段
            if target_task.status == "waiting_for_confirm":
                current_stage = target_task.approval_stage
                if current_stage in stages:
                    next_index = stages.index(current_stage) + 1
                    if next_index < len(stages):
                        next_name = STAGE_NAMES.get(stages[next_index], stages[next_index])
                        await self.send_chat_message(f"收到，老大。我继续推进到 **{next_name}** 阶段。")
                        task.status = "completed"
                        await self._run_next_stage(target_task, available_agents, next_index)
                    else:
                        target_task.status = "completed"
                        target_task.approval_stage = "completed"
                        await self.send_chat_message("老大，所有阶段都完成了。")
                        task.status = "completed"
                        await self.update_status(AgentStatus.IDLE)
                else:
                    await self.send_chat_message("老大，我没定位到当前阶段。你再说一下想从哪一步继续。")
                    task.status = "completed"
                    await self.update_status(AgentStatus.IDLE)
            else:
                await self.send_chat_message("老大，当前任务不在等待确认状态，不用手动继续。")
                task.status = "completed"
                await self.update_status(AgentStatus.IDLE)

        elif action == "skip_to":
            # 跳到指定阶段
            if target_stage in stages:
                target_index = stages.index(target_stage)
                target_name = STAGE_NAMES.get(target_stage, target_stage)
                # 计算跳过的阶段
                current_idx = stages.index(target_task.approval_stage) if target_task.approval_stage in stages else 0
                skipped = [STAGE_NAMES.get(s, s) for s in stages[current_idx+1:target_index]]
                if skipped:
                    await self.send_chat_message(f"收到，老大。我跳过 {', '.join(skipped)}，直接进 **{target_name}**。")
                else:
                    await self.send_chat_message(f"收到，老大。我直接进 **{target_name}**。")
                task.status = "completed"
                await self._run_next_stage(target_task, available_agents, target_index)
            else:
                available = ", ".join([STAGE_NAMES.get(s, s) for s in stages])
                await self.send_chat_message(f"老大，我没找到「{target_stage}」这个阶段。现在可用阶段：{available}")
                task.status = "completed"
                await self.update_status(AgentStatus.IDLE)

        elif action == "go_back":
            # 回退到指定阶段
            if target_stage in stages:
                target_index = stages.index(target_stage)
                target_name = STAGE_NAMES.get(target_stage, target_stage)
                await self.send_chat_message(f"收到，老大。我回到 **{target_name}** 重新跑。")
                task.status = "completed"
                await self._run_next_stage(target_task, available_agents, target_index)
            else:
                available = ", ".join([STAGE_NAMES.get(s, s) for s in stages])
                await self.send_chat_message(f"老大，我没找到「{target_stage}」这个阶段。现在可用阶段：{available}")
                task.status = "completed"
                await self.update_status(AgentStatus.IDLE)

        else:
            await self.send_chat_message(f"老大，我没理解这个操作：{action}")
            task.status = "completed"
            await self.update_status(AgentStatus.IDLE)

    async def _run_next_stage(self, task: Task, available_agents: Dict[str, "BaseAgent"], stage_index: int):
        """按顺序执行工作流阶段"""
        stages = self._get_task_stages(task)
        if stage_index >= len(stages):
            # 全部完成
            task.status = "completed"
            task.approval_stage = "completed"
            if task.id in self.active_tasks:
                del self.active_tasks[task.id]
            await self.send_chat_message("老大，所有阶段都完成了，产出物也保存到工作区了。")
            await self.update_status(AgentStatus.IDLE, "任务完成")
            return

        stage = stages[stage_index]
        task.approval_stage = stage
        task.status = "in_progress"

        total = len(stages)
        current = stage_index + 1

        # 路由到具体阶段
        if stage == "research":
            await self._do_research(task, available_agents, current, total)
        elif stage == "competitive":
            await self._do_competitive(task, available_agents, current, total)
        elif stage == "planning":
            await self._do_planning(task, available_agents, current, total)
        elif stage == "architecture":
            await self._do_architecture(task, available_agents, current, total)
        elif stage == "execution":
            await self._do_execution(task, available_agents, current, total)
        elif stage == "testing":
            await self._do_testing(task, available_agents, current, total)

    async def _handle_stage_failure(self, task: Task, stage_name: str, error: str):
        """阶段执行失败时的处理"""
        task.status = "failed"
        task.analysis_result = f"老大，我在{stage_name}阶段卡住了。\n\n原因：{error}\n\n请检查 LLM 服务状态后重新发送任务。"
        await self.send_chat_message(f"老大，我在 **{stage_name}** 阶段卡住了。\n{error}\n\n请检查网络/API 状态后重新提交任务。")
        await self.update_status(AgentStatus.IDLE, "任务失败")

    async def _pause_for_approval(self, task: Task, stage: str, result_msg: str, next_hint: str):
        """HITL 暂停等待审批"""
        has_next = False
        stages = self._get_task_stages(task)
        idx = stages.index(stage) if stage in stages else -1
        has_next = idx < len(stages) - 1

        if has_next:
            task.status = "waiting_for_confirm"
            next_stage = stages[idx + 1]
            next_stage_name = STAGE_NAMES.get(next_stage, next_hint)
            task.analysis_result = f"老大，{result_msg}。\n\n你先看一下，确认后我就进入下一阶段：{next_stage_name}。\n你也可以直接说「继续」「跳过XX」，或者提出修改意见。"
            await self.send_chat_message(task.analysis_result)
            await self.update_status(AgentStatus.WAITING, "等待审批")
        else:
            # 最后一个阶段，直接完成
            task.status = "completed"
            task.approval_stage = "completed"
            if task.id in self.active_tasks:
                del self.active_tasks[task.id]
            await self.send_chat_message(f"老大，{result_msg}。\n\n任务全部完成了。")
            await self.update_status(AgentStatus.IDLE, "任务完成")

    async def _do_research(self, task, agents, current, total):
        await self.update_status(AgentStatus.WORKING, "协调 CEO 进行市场调研")
        await self.send_chat_message(f"🚀 **阶段 {current}/{total}：市场调研**\n老大，我让 Steve 先看市场。", MessageType.STAGE)

        ceo = agents.get("ceo_01")
        if ceo:
            try:
                await ceo.perform_research(
                    self._employee_task_packet(task, "围绕用户原始要求完成市场调研。"),
                    task.folder_path,
                )
            except RuntimeError as e:
                await self._handle_stage_failure(task, "市场调研", str(e))
                return

        await self._pause_for_approval(task, "research", "市场调研报告完成了", "竞品分析")

    async def _do_competitive(self, task, agents, current, total):
        await self.update_status(AgentStatus.WORKING, "协调 CEO 进行竞品分析")
        await self.send_chat_message(f"🚀 **阶段 {current}/{total}：竞品分析**\n老大，我让 Steve 做竞品分析。", MessageType.STAGE)

        ceo = agents.get("ceo_01")
        if ceo:
            try:
                await ceo.perform_competitive(
                    self._employee_task_packet(task, "围绕用户原始要求完成竞品分析。"),
                    task.folder_path,
                )
            except RuntimeError as e:
                await self._handle_stage_failure(task, "竞品分析", str(e))
                return

        await self._pause_for_approval(task, "competitive", "竞品分析报告完成了", "产品规划")

    async def _do_planning(self, task, agents, current, total):
        await self.update_status(AgentStatus.WORKING, "协调 PM 撰写 PRD")
        await self.send_chat_message(f"🚀 **阶段 {current}/{total}：产品规划**\n老大，我让 Emma 写 PRD。", MessageType.STAGE)

        emma = agents.get("pm_01")
        if emma:
            try:
                msg = Message(
                    sender_id=self.state.id,
                    receiver_id=emma.state.id,
                    content=self._employee_task_packet(task, "基于用户原始要求撰写 PRD/产品方案。"),
                    message_type=MessageType.COMMAND
                )
                emma.state.current_folder = task.folder_path
                await emma.handle_message(msg)
            except RuntimeError as e:
                await self._handle_stage_failure(task, "产品规划", str(e))
                return

        await self._pause_for_approval(task, "planning", "PRD 文档完成了", "架构设计")

    async def _do_architecture(self, task, agents, current, total):
        await self.update_status(AgentStatus.WORKING, "协调 CTO 设计架构")
        await self.send_chat_message(f"🚀 **阶段 {current}/{total}：架构设计**\n老大，我让 Elon 做技术方案。", MessageType.STAGE)

        cto = agents.get("cto_01")
        if cto:
            try:
                await cto.create_architecture(
                    self._employee_task_packet(task, "基于用户原始要求设计技术架构。"),
                    task.folder_path,
                )
            except RuntimeError as e:
                await self._handle_stage_failure(task, "架构设计", str(e))
                return

        await self._pause_for_approval(task, "architecture", "架构设计完成了", "开发实现")

    async def _do_execution(self, task, agents, current, total):
        await self.update_status(AgentStatus.WORKING, "协调工程团队开发")
        await self.send_chat_message(f"🚀 **阶段 {current}/{total}：开发实现**\n老大，我让 Alex、Lucas 和 David 做实现。", MessageType.STAGE)

        plan = [
            {"agent_id": "ui_01", "goal": "基于用户原始要求完成 UI/交互/视觉设计产物。"},
            {"agent_id": "fe_01", "goal": "基于用户原始要求完成前端实现或 HTML 演示产物。"},
            {"agent_id": "be_01", "goal": "基于用户原始要求完成后端/API/数据设计产物。"},
        ]

        for step in plan:
            agent_id = step["agent_id"]
            if agent_id in agents:
                worker = agents[agent_id]
                worker.state.current_folder = task.folder_path
                msg = Message(
                    sender_id=self.state.id,
                    receiver_id=agent_id,
                    content=self._employee_task_packet(task, step["goal"]),
                    message_type=MessageType.COMMAND
                )
                await worker.receive_message(msg)

        # 等待所有 worker 完成
        for step in plan:
            agent_id = step["agent_id"]
            if agent_id in agents:
                worker = agents[agent_id]
                try:
                    await asyncio.wait_for(worker.message_queue.join(), timeout=300)
                except asyncio.TimeoutError:
                    await self.send_chat_message(f"老大，{worker.state.name} 有点超时，我先继续往下推进。")

        await self._pause_for_approval(task, "execution", "开发实现完成了，产出物已保存到工作区", "测试验收")

    async def _do_testing(self, task, agents, current, total):
        await self.update_status(AgentStatus.WORKING, "协调 QA 进行测试验收")
        await self.send_chat_message(f"🚀 **阶段 {current}/{total}：测试验收**\n老大，我让 Sarah 做测试验收。", MessageType.STAGE)

        qa = agents.get("qa_01")
        if qa:
            try:
                qa.state.current_folder = task.folder_path
                await qa.perform_work(
                    self._employee_task_packet(task, "基于用户原始要求生成测试用例、验收标准和质量检查点。")
                )
            except RuntimeError as e:
                await self._handle_stage_failure(task, "测试验收", str(e))
                return

        await self._pause_for_approval(task, "testing", "测试验收完成了", "项目总结")

    async def continue_task(self, task: Task, available_agents: Dict[str, "BaseAgent"]):
        """用户审批通过后，推进到下一阶段"""
        stages = self._get_task_stages(task)
        current_stage = task.approval_stage

        if current_stage in stages:
            next_index = stages.index(current_stage) + 1
            if next_index < len(stages):
                await self.send_chat_message(f"收到，老大。{STAGE_NAMES.get(current_stage, current_stage)} 已确认，我推进到下一阶段。")
                await self._run_next_stage(task, available_agents, next_index)
            else:
                task.status = "completed"
                task.approval_stage = "completed"
                if task.id in self.active_tasks:
                    del self.active_tasks[task.id]
                await self.send_chat_message("老大，所有阶段都完成了。")
                await self.update_status(AgentStatus.IDLE)
        else:
            await self.send_chat_message(f"老大，我没识别到这个阶段：{current_stage}")
