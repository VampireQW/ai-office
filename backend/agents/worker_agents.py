"""
WorkerAgent — 执行层 Agent（PM / UI / Frontend / Backend / QA）
UI 和 Frontend 输出可演示的 HTML 文件
"""
import asyncio
import os
import re
from typing import Dict, Optional
from models import AgentRole, AgentStatus, Message, MessageType
from agents.base_agent import BaseAgent
from skills.workflow_manager import WorkflowManager


LAST_ARTIFACT: Optional[Dict] = None
VISION_CONTEXT_INSTRUCTION = (
    "If the task includes visual image inputs, inspect the images directly and "
    "use their visible layout, colors, text, and structure as primary context."
)
USER_REQUIREMENTS_INSTRUCTION = """
Execution contract:
- The user's original requirement is the highest-priority source of truth.
- Routing labels, workflow stage names, and short summaries are only helper context.
- If an AIky employee task packet is provided, read the "用户原始要求" section first and preserve its constraints, files, images, output type, and wording.
- Do not infer that the user wants to modify a previous artifact unless the task explicitly says so.
"""
SCREENSHOT_TO_HTML_INSTRUCTION = """
The user is asking to recreate a screenshot as HTML. Treat the attached image as
the primary specification, not as a loose inspiration.

Recreation rules:
- Match the screenshot's major regions, proportions, spacing, colors, typography,
  navigation, sidebars, cards, tables, buttons, and visible text as closely as
  possible.
- Preserve the screenshot's information architecture: if it has a top nav, left
  tree, central preview, and right resource panel, reproduce those exact regions.
- Do not replace the screenshot with a generic landing page, dashboard, or new
  visual style.
- Use CSS to create faithful shapes and dense UI structure. Use inline SVG,
  gradients, simple generated thumbnails, or CSS blocks only when the screenshot
  contains visual placeholders/images that cannot be embedded.
- Keep the implementation compact enough to finish in one response: use reusable
  CSS classes, concise mock data, no long comments, and vanilla JavaScript only
  when interaction is necessary.
- Output a single complete self-contained HTML document. No markdown fences and
  no explanation outside the HTML.
"""
VISUAL_REFERENCE_HTML_INSTRUCTION = """
The user is asking to use the attached image as a visual reference, not to copy
it exactly.

Reference rules:
- Extract the image's visual language: color mood, density, component style,
  hierarchy, spacing rhythm, typography feel, and interaction patterns.
- Adapt those traits to the user's requested product or page instead of
  duplicating the screenshot's exact layout or content.
- Do not perform pixel-level recreation unless the user explicitly asks for
  "recreate", "clone", "pixel-perfect", "复刻", "还原", "像素级", or "一模一样".
- Keep the implementation compact enough to finish in one response: use reusable
  CSS classes, concise mock data, no long comments, and vanilla JavaScript only
  when interaction is necessary.
- Output a single complete self-contained HTML document. No markdown fences and
  no explanation outside the HTML.
"""
RECREATE_BASE_CSS = """
html,body{margin:0;width:100%;min-height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",Arial,sans-serif;background:#f3f5f7;color:#1f2933}
*{box-sizing:border-box}
.pixel-replica{width:1365px;min-height:768px;margin:0 auto;display:grid;grid-template-columns:260px 1fr 318px;grid-template-rows:52px minmax(716px,auto);background:#f3f5f7;overflow:hidden}
.top-nav{grid-column:1/4;grid-row:1;min-width:0}
.left-panel{grid-column:1;grid-row:2;min-width:0;overflow:hidden}
.main-panel{grid-column:2;grid-row:2;min-width:0;overflow:hidden}
.right-panel{grid-column:3;grid-row:2;min-width:0;overflow:hidden}
.floating-tools{position:fixed;right:20px;bottom:20px;z-index:20}
@media(max-width:1365px){body{overflow-x:auto}.pixel-replica{margin:0}}
"""


def remember_artifact(metadata: Dict):
    global LAST_ARTIFACT
    LAST_ARTIFACT = dict(metadata)


def get_last_artifact() -> Optional[Dict]:
    if LAST_ARTIFACT:
        return dict(LAST_ARTIFACT)

    workspace_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workspace")
    latest = None
    walk_iter = os.walk(workspace_dir) if os.path.exists(workspace_dir) else []
    for root, _, files in walk_iter:
        for filename in files:
            if not filename.lower().endswith((".html", ".md", ".txt")):
                continue
            path = os.path.join(root, filename)
            mtime = os.path.getmtime(path)
            if not latest or mtime > latest["mtime"]:
                agent_id = "fe_01"
                if filename.startswith("UI_Demo"):
                    agent_id = "ui_01"
                elif filename.startswith("PRD"):
                    agent_id = "pm_01"
                elif filename.startswith("Backend"):
                    agent_id = "be_01"
                elif filename.startswith("TestCases"):
                    agent_id = "qa_01"
                latest = {
                    "mtime": mtime,
                    "filename": filename,
                    "folder": root,
                    "agent_id": agent_id,
                    "type": "html" if filename.lower().endswith(".html") else "text",
                }
    if latest:
        latest.pop("mtime", None)
        return latest
    return None


def read_artifact_content(artifact: Dict) -> str:
    folder = artifact.get("folder") if artifact else ""
    filename = artifact.get("filename") if artifact else ""
    if not folder or not filename:
        return ""
    path = os.path.join(folder, filename)
    if not os.path.exists(path) or not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


# 角色配置映射
ROLE_CONFIG = {
    AgentRole.PRODUCT_MANAGER: {
        "workflow": "4-pe-prd",
        "prefix": "PRD",
        "ext": ".md",
        "start_msg": "收到，老大，我来整理需求和 PRD。",
        "done_msg": "老大，我完成了 PRD 文档。",
    },
    AgentRole.UI_DESIGNER: {
        "workflow": None,
        "prefix": "UI_Demo",
        "ext": ".html",
        "start_msg": "收到，老大，我来做界面方案。",
        "done_msg": "老大，我完成了 UI 演示页面。",
        "fallback_prompt": """You are a Senior UI/UX Designer who outputs production-ready HTML demos.

Your task: Create a COMPLETE, self-contained HTML file that serves as a high-fidelity UI demo.

Requirements:
1. Output a SINGLE complete HTML file with embedded CSS and minimal JS
2. Use modern design: clean layout, proper spacing, shadows, rounded corners
3. Include responsive design (works on mobile and desktop)
4. Use Chinese text for all UI labels and content
5. Add realistic placeholder data and content
6. Use CSS variables for theming, gradients for visual appeal
7. Include hover effects and transitions for interactivity
8. Use system fonts or Google Fonts via CDN
9. You can use Font Awesome CDN for icons

CRITICAL: Output ONLY the HTML code. Start with <!DOCTYPE html> and end with </html>.
Do NOT wrap in markdown code blocks. Do NOT add any explanation outside the HTML.""",
    },
    AgentRole.FRONTEND_DEV: {
        "workflow": "7-pe-code",
        "prefix": "Frontend_Demo",
        "ext": ".html",
        "start_msg": "收到，老大，我来实现前端。",
        "done_msg": "老大，我完成了前端演示页面。",
        "system_override": """You are a Senior Frontend Developer who outputs production-ready HTML demos.

Your task: Create a COMPLETE, self-contained HTML file with full interactivity.

Requirements:
1. Output a SINGLE complete HTML file with embedded CSS and JavaScript
2. Implement real UI interactions: form validation, state management, animations
3. Use Vue 3 CDN or vanilla JS for interactivity
4. Include responsive design
5. Use Chinese text for all UI content
6. Add realistic mock data
7. Make it look professional and polished
8. Include transitions, loading states, and error handling in the UI

CRITICAL: Output ONLY the HTML code. Start with <!DOCTYPE html> and end with </html>.
Do NOT wrap in markdown code blocks. Do NOT add any explanation outside the HTML.""",
    },
    AgentRole.BACKEND_DEV: {
        "workflow": "7-pe-code",
        "prefix": "Backend_API",
        "ext": ".md",
        "start_msg": "收到，老大，我来梳理后端和接口。",
        "done_msg": "老大，我完成了后端 API 设计文档。",
    },
    AgentRole.QA_ENGINEER: {
        "workflow": "8-pe-testing",
        "prefix": "TestCases",
        "ext": ".md",
        "start_msg": "收到，老大，我来检查质量和测试点。",
        "done_msg": "老大，我完成了测试用例。",
    },
}

PRD_KEYWORDS = [
    "prd", "产品需求文档", "需求文档", "写需求", "写一份需求", "产品方案",
]

ROLE_WORKFLOW_KEYWORDS = {
    AgentRole.PRODUCT_MANAGER: PRD_KEYWORDS,
    AgentRole.UI_DESIGNER: [
        "ui设计", "ui 设计", "界面设计", "页面设计", "原型", "视觉设计", "交互设计", "设计稿", "设计方案",
    ],
    AgentRole.FRONTEND_DEV: [
        "前端", "实现页面", "生成页面", "写页面", "做页面", "做个页面", "做一个页面",
        "生成html", "生成 html", "写html", "写 html", "做html", "做 html",
        "一个html", "一个 html", "html页面", "html 页面", "前端页面", "demo", "组件", "交互实现", "代码实现",
    ],
    AgentRole.BACKEND_DEV: [
        "后端", "写接口文档", "生成接口文档", "写api文档", "写 api 文档",
        "生成api文档", "生成 api 文档", "设计接口", "接口设计",
        "数据库设计", "数据模型", "服务设计", "权限设计", "表结构",
    ],
    AgentRole.QA_ENGINEER: [
        "测试用例", "验收标准", "验收用例", "测试方案", "质量检查点", "回归测试", "冒烟测试",
    ],
}

GENERAL_INTENT_KEYWORDS = [
    "总结", "概括", "归纳", "提炼", "摘要", "要点", "分析一下", "看一下", "读一下",
    "读取", "解释", "聊聊", "评价", "review", "summary", "summarize",
]

CREATE_INTENT_KEYWORDS = [
    "生成", "创建", "设计", "实现", "开发", "写", "做", "做个", "做一个", "输出",
    "create", "generate", "build", "implement",
]

GENERAL_TASK_SYSTEM_PROMPT = """You are a practical assistant completing a direct user request.

Rules:
- Follow the user's original request first.
- If the user asks for a summary, summarize the provided webpage, file, image, text, or context.
- If the user asks a chat-style question, answer directly.
- Do not turn the request into a PRD, PE workflow, market research report, test case document, or implementation plan unless the user explicitly asks for that format.
- If context cannot be read, say that clearly and work only from what is available.

Output in Chinese. Keep it useful, concise, and structured when structure helps."""


def _is_role_workflow_task(role: AgentRole, task_description: str) -> bool:
    lower = (task_description or "").lower()
    has_general_intent = any(keyword.lower() in lower for keyword in GENERAL_INTENT_KEYWORDS)
    has_create_intent = any(keyword.lower() in lower for keyword in CREATE_INTENT_KEYWORDS)
    if has_general_intent and not has_create_intent:
        return False
    return any(keyword.lower() in lower for keyword in ROLE_WORKFLOW_KEYWORDS.get(role, []))


def _effective_config(role: AgentRole, task_description: str) -> Dict:
    config = dict(ROLE_CONFIG.get(role, {}))
    if role in ROLE_CONFIG and not _is_role_workflow_task(role, task_description):
        config.update({
            "workflow": None,
            "system_override": GENERAL_TASK_SYSTEM_PROMPT,
            "prefix": "Result",
            "ext": ".md",
            "start_msg": "收到，我来处理。",
            "done_msg": "我搞定了。",
        })
    return config


def _infer_artifact_label(role: AgentRole, filename: str, task_description: str, ext: str) -> str:
    text = f"{filename} {task_description}".lower()

    if filename.lower().startswith("result"):
        return "结果"
    if role == AgentRole.FRONTEND_DEV:
        return "前端演示页面" if ext == ".html" else "前端实现文档"
    if role == AgentRole.UI_DESIGNER:
        return "UI 演示页面" if ext == ".html" else "界面方案"
    if role == AgentRole.PRODUCT_MANAGER:
        return "PRD 文档"
    if role == AgentRole.BACKEND_DEV:
        return "后端 API 设计文档"
    if role == AgentRole.QA_ENGINEER:
        return "测试用例"
    if "prd" in text or "需求文档" in text:
        return "PRD 文档"
    if "测试" in task_description:
        return "测试用例"
    if ext == ".html":
        return "演示页面"
    if ext == ".md":
        return "文档"
    return "产出物"


def _done_message(role: AgentRole, filename: str, task_description: str, ext: str) -> str:
    if filename.lower().startswith("result"):
        return "我搞定了。"
    label = _infer_artifact_label(role, filename, task_description, ext)
    return f"我完成了 {label}。"


def _extract_html(content: str) -> str:
    """从 LLM 输出中提取纯 HTML（去掉 markdown 代码块包裹）"""
    # 尝试提取 ```html ... ``` 中的内容
    match = re.search(r'```html?\s*\n([\s\S]*?)```', content)
    if match:
        return match.group(1).strip()

    # 尝试提取 ``` ... ``` 中 <!DOCTYPE 开头的内容
    match = re.search(r'```\s*\n(<!DOCTYPE[\s\S]*?</html>)\s*```', content, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 如果本身就是 HTML（以 <!DOCTYPE 或 <html 开头）
    stripped = content.strip()
    if stripped.lower().startswith('<!doctype') or stripped.lower().startswith('<html'):
        return stripped

    # 最后手段：找到 HTML 块
    match = re.search(r'(<!DOCTYPE[\s\S]*</html>)', content, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return content


def _strip_code_fence(content: str) -> str:
    text = (content or "").strip()
    text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _clean_css_chunk(content: str) -> str:
    text = _strip_code_fence(content)
    match = re.search(r"<style[^>]*>([\s\S]*?)</style>", text, flags=re.IGNORECASE)
    if match:
        text = match.group(1)
    return text.strip()


def _clean_html_fragment(content: str) -> str:
    text = _strip_code_fence(content)
    body = re.search(r"<body[^>]*>([\s\S]*?)</body>", text, flags=re.IGNORECASE)
    if body:
        text = body.group(1)
    text = re.sub(r"(?is)<!DOCTYPE[^>]*>", "", text)
    text = re.sub(r"(?is)</?html[^>]*>", "", text)
    text = re.sub(r"(?is)<head[^>]*>[\s\S]*?</head>", "", text)
    text = re.sub(r"(?is)<style[^>]*>[\s\S]*?</style>", "", text)
    text = re.sub(r"(?is)<script[^>]*>[\s\S]*?</script>", "", text)
    return text.strip()


def _clean_js_chunk(content: str) -> str:
    text = _strip_code_fence(content)
    match = re.search(r"<script[^>]*>([\s\S]*?)</script>", text, flags=re.IGNORECASE)
    if match:
        text = match.group(1)
    if re.search(r"^(无需|不需要|none|no js)", text.strip(), flags=re.IGNORECASE):
        return ""
    return text.strip()


def _looks_like_visible_html(content: str) -> bool:
    if not content or len(content.strip()) < 200:
        return False
    if not re.search(r"<html[\s\S]*?</html>", content, re.IGNORECASE):
        return False
    body = re.search(r"<body[^>]*>([\s\S]*?)</body>", content, re.IGNORECASE)
    if not body:
        return False
    visibleish = re.sub(r"(?is)<(script|style).*?</\1>", "", body.group(1))
    visibleish = re.sub(r"<[^>]+>", "", visibleish).strip()
    return len(visibleish) >= 20 or bool(re.search(r"<(div|main|section|nav|aside|header|canvas|svg)\b", body.group(1), re.IGNORECASE))


def _clean_html_continuation(content: str) -> str:
    continuation = (content or "").strip()
    continuation = re.sub(r"^```html?\s*", "", continuation, flags=re.IGNORECASE)
    continuation = re.sub(r"\s*```$", "", continuation)
    return continuation.strip()


def _is_probably_truncated_html(content: str) -> bool:
    if not content:
        return False
    lower = content.lower()
    return ("<!doctype" in lower or "<html" in lower) and "</html>" not in lower


def _strip_image_markers(content: str) -> str:
    return re.sub(
        r"\[\[AIKY_IMAGE:([^\]|]+)\|(data:image/[^;\]]+;base64,[A-Za-z0-9+/=\r\n]+)\]\]",
        r"[图片已在蓝图阶段发送给视觉模型：\1]",
        content or "",
        flags=re.IGNORECASE,
    )


def _artifact_title_seed(task_description: str) -> str:
    text = task_description or ""
    match = re.search(
        r"### 用户原始要求（最高优先级）\s*([\s\S]*?)(?:\n### 当前阶段/路由|\n### 当前员工目标|$)",
        text,
    )
    if match:
        text = match.group(1)
    text = re.sub(r"\[\[AIKY_IMAGE:[\s\S]*?\]\]", "图片", text)
    text = re.sub(r"---\s*\n以下图片将作为视觉输入发送给模型[\s\S]*", "", text)
    text = re.sub(r"### 上下文 \d+:[\s\S]*?(?=\n### |\Z)", "", text)
    return text.strip() or task_description


def _visual_intent_text(task_description: str) -> str:
    text = task_description or ""
    match = re.search(
        r"### 用户原始要求（最高优先级）\s*([\s\S]*?)(?:\n### 当前阶段/路由|\n### 当前员工目标|$)",
        text,
    )
    if match:
        text = match.group(1)

    # Keep the user's intent words, but remove file paths and injected context
    # so folder names like "新教育复刻" do not force screenshot recreation mode.
    text = re.sub(r"\[\[AIKY_IMAGE:[\s\S]*?\]\]", " 图片 ", text, flags=re.IGNORECASE)
    text = re.sub(r"### 上下文 \d+:[\s\S]*?(?=\n### |\Z)", " ", text)
    text = re.sub(r"---\s*\n以下图片将作为视觉输入发送给模型[\s\S]*", " ", text)
    text = re.sub(
        r"[A-Za-z]:\\[\s\S]*?\.(?:png|jpe?g|webp|gif|bmp|svg)",
        " 本地图片 ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"[A-Za-z]:\\[\s\S]*?\.(?:html?|md|txt|pdf)",
        " 本地文件 ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"/[^\s，。；;、]+?\.(?:png|jpe?g|webp|gif|bmp|svg)", " 本地图片 ", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s，。；;、]+", " 网页 ", text, flags=re.IGNORECASE)
    return text.strip()


def _visual_html_mode(task_description: str, ext: str) -> str:
    if ext != ".html" or "[[AIKY_IMAGE:" not in task_description:
        return "none"
    lower = _visual_intent_text(task_description).lower()
    recreate_keywords = [
        "复刻", "还原", "像素级", "像素级还原", "照着做", "完全照着",
        "一模一样", "原样", "按原图", "和图片一致", "跟图片一样",
        "复制", "拷贝",
        "recreate", "clone", "copy", "pixel-perfect", "pixel perfect",
    ]
    reference_keywords = [
        "重新设计", "重新设计一下", "设计一下ui", "设计一下 ui", "重新做ui", "重新做 ui",
        "参考", "借鉴", "按这个风格", "按照这个风格", "这个风格",
        "视觉风格", "风格类似", "类似风格", "同款风格", "参考视觉",
        "以这个为参考", "以此为参考", "提炼风格", "总结风格",
        "inspired", "reference", "style like", "redesign",
    ]
    # Redesign/reference wording should win over accidental recreate words
    # from titles or broad phrases.
    if any(keyword in lower for keyword in reference_keywords):
        return "reference"
    if any(keyword in lower for keyword in recreate_keywords):
        return "recreate"
    generic_visual_keywords = [
        "截图", "图片", "图", "界面图", "页面图", "image", "screenshot"
    ]
    if any(keyword in lower for keyword in generic_visual_keywords):
        return "general"
    return "none"


async def _build_visual_brief(agent: BaseAgent, task_description: str, visual_mode: str) -> str:
    return await _build_visual_brief_internal(
        agent,
        task_description,
        visual_mode,
        force=_should_preanalyze_visual(task_description, visual_mode),
    )


async def _build_visual_brief_internal(agent: BaseAgent, task_description: str, visual_mode: str, force: bool = False) -> str:
    if not force:
        return task_description
    if visual_mode not in ("recreate", "reference") or "[[AIKY_IMAGE:" not in task_description:
        return task_description

    if visual_mode == "recreate":
        brief_request = """请先观察用户提供的图片，输出用于 HTML 复刻的结构化视觉说明。
必须覆盖：整体尺寸比例、顶部/左侧/中间/右侧主要区域、颜色、间距、可见文字、组件类型、卡片/表格/按钮/导航、层级关系。
只描述图片中确实存在的内容，不要发散。"""
    else:
        brief_request = """请先观察用户提供的图片，输出用于 HTML 设计参考的结构化视觉说明。
必须覆盖：视觉风格、配色、密度、组件样式、版式节奏、字体气质、交互控件特点。
不要要求照搬图片布局，只提炼可迁移的视觉特征。"""

    brief_prompt = f"{task_description}\n\n---\n{brief_request}"
    try:
        await agent.send_chat_message("老大，我先把图片视觉结构拆一下，再开始生成页面。")
        visual_brief = await agent.think(
            brief_prompt,
            "你是严格的视觉截图分析助手。你必须根据图片本身输出结构化说明；如果没有收到图片，明确回答：没有收到图片。",
            max_retries=1,
        )
    except Exception as exc:
        await agent.send_chat_message(f"老大，图片视觉拆解没跑通，我会直接带图继续生成。原因：{str(exc)}")
        return task_description

    if "没有收到图片" in visual_brief:
        await agent.send_chat_message("老大，我这次没有收到图片视觉输入，先不假装看到了。你检查一下路径或重启后端再试。")
        raise RuntimeError("模型没有收到图片视觉输入")

    return f"""{task_description}

---
模型已基于图片提取出以下视觉说明。生成 HTML 时必须同时参考原始图片视觉输入和这份说明：

{visual_brief}
"""


async def _continue_truncated_html(
    agent: BaseAgent,
    partial_html: str,
    system_prompt: str,
    source_task: str = "",
) -> str:
    if not _is_probably_truncated_html(partial_html):
        return partial_html

    completed = partial_html.rstrip()
    for attempt in range(2):
        tail = completed[-5000:]
        await agent.send_chat_message(f"老大，HTML 输出被截断了，我续写第 {attempt + 1} 次。")
        source_context = ""
        if source_task:
            source_context = f"""原始任务背景如下。续写时必须继续满足这些要求；如果其中包含图片输入，请继续参考图片视觉信息。

{source_task}

---
"""
        continuation_prompt = f"""{source_context}下面是一份尚未完成的 HTML 文件尾部。请从最后一个字符之后继续输出，直到完整闭合 </html>。

要求：
- 只输出续写部分
- 不要重复已经给出的内容
- 不要解释
- 不要使用 markdown 代码块

HTML 文件尾部：
{tail}"""
        continuation = await agent.think(continuation_prompt, system_prompt, max_retries=1)
        continuation = _clean_html_continuation(continuation)
        if not continuation:
            break
        if continuation.lower().startswith("<!doctype") or continuation.lower().startswith("<html"):
            completed = continuation
        else:
            completed = f"{completed}\n{continuation}"
        if "</html>" in completed.lower():
            break
    return completed


async def _generate_recreate_html_stream(agent: BaseAgent, task_description: str, system_prompt: str) -> str:
    await agent.send_chat_message("老大，我会让视觉模型一次看完整图片，并用流式方式接收 HTML。")
    stream_prompt = f"""{task_description}

---
像素级复刻要求：
- 直接根据原始图片生成完整 HTML，不要泛化成新页面
- 尽量匹配截图的整体比例、三栏结构、顶部导航、文字密度、颜色、间距和控件
- 使用紧凑的原生 HTML/CSS/JS，避免外部框架，避免长注释
- 输出必须从 <!DOCTYPE html> 开始，到 </html> 结束
- 只输出 HTML，不要解释，不要 markdown 代码块"""
    return await agent.think_stream(stream_prompt, system_prompt, max_retries=1)


async def _generate_reference_html_stream(agent: BaseAgent, task_description: str, system_prompt: str) -> str:
    await agent.send_chat_message("老大，我会参考图片视觉风格重新设计 UI，并用流式方式接收 HTML。")
    stream_prompt = f"""{task_description}

---
视觉参考重设计要求：
- 图片只作为视觉参考：提炼色彩、密度、组件语言、层级、字体感觉和交互风格
- 不要照搬原图布局、内容和信息架构；根据用户目标重新组织 UI
- 如果用户要求“重新设计 UI”，要输出一个新的高保真 UI 方案，而不是截图复刻
- 使用完整自包含 HTML，CSS 和必要 JS 全部内联
- 输出必须从 <!DOCTYPE html> 开始，到 </html> 结束
- 只输出 HTML，不要解释，不要 markdown 代码块"""
    return await agent.think_stream(stream_prompt, system_prompt, max_retries=1)


async def _generate_recreate_html_in_chunks(agent: BaseAgent, task_description: str) -> str:
    await agent.send_chat_message("老大，我改用分块复刻：蓝图、CSS、顶部、左侧、主内容、右侧、交互分开生成。")
    chunk_system = """你是像素级截图复刻前端工程师。原始图片是最高优先级输入。
每一步只输出本轮要求的片段，不要输出解释，不要 markdown 代码块。
如果文字蓝图与原图冲突，以原图为准。保持实现紧凑，使用原生 HTML/CSS/JS，不使用外部框架。"""

    shared_context = f"""{task_description}

---
分块生成规则：
- 每个步骤都包含同一张原始图片视觉输入，请重新观察图片，不要只依赖文字蓝图。
- 目标是像素级接近截图，而不是重新设计。
- 使用统一外层 `.pixel-replica`。
- 主要区域约定为 `.top-nav`, `.left-panel`, `.main-panel`, `.right-panel`, `.floating-tools`；如截图没有某区域，可输出空片段。"""

    blueprint = await agent.think(
        f"""{shared_context}

第 1 步：输出复刻蓝图。只用简洁清单描述：
1. 截图宽高比例和整体背景
2. 顶部、左侧、中间、右侧、悬浮区的位置和大致尺寸
3. 主要颜色、字号、边框、阴影
4. 必须保留的可见文字和组件
不要输出 HTML/CSS。""",
        chunk_system,
        max_retries=1,
    )

    css = _clean_css_chunk(await agent.think(
        f"""{shared_context}

复刻蓝图：
{blueprint}

第 2 步：只输出 CSS。要求：
- CSS 必须覆盖 `.pixel-replica`, `.top-nav`, `.left-panel`, `.main-panel`, `.right-panel`, `.floating-tools`
- 使用截图里的颜色、密度、边框、间距、字体大小
- 适配 1365px 左右宽度，同时允许横向滚动来保持像素级布局
- 不要输出 <style> 标签，不要输出 HTML。""",
        chunk_system,
        max_retries=1,
    ))

    fragments = []
    fragment_specs = [
        ("顶部导航区域", ".top-nav", "顶部品牌、导航菜单、搜索/按钮/用户信息等"),
        ("左侧目录区域", ".left-panel", "左侧课程/菜单树、选中态、层级缩进等"),
        ("中间主内容区域", ".main-panel", "中间预览区、标题、标签、卡片、正文/图片占位等"),
        ("右侧资源区域", ".right-panel", "右侧快捷入口、资源列表、按钮、卡片等"),
        ("悬浮/补充区域", ".floating-tools", "截图中的悬浮按钮、底部工具、角标；没有则输出空字符串"),
    ]
    for title, class_name, scope in fragment_specs:
        fragment = _clean_html_fragment(await agent.think(
            f"""{shared_context}

复刻蓝图：
{blueprint}

已约定 CSS 类：`.pixel-replica`, `.top-nav`, `.left-panel`, `.main-panel`, `.right-panel`, `.floating-tools`

第 3 步分片：只输出「{title}」的 HTML 片段。
范围：{scope}
要求：
- 最外层必须使用 `{class_name}`，除非该区域在截图中不存在
- 保留截图可见文字；图片内容可用 CSS 色块/简洁 SVG/占位缩略图模拟
- 不要输出 <!DOCTYPE>、<html>、<head>、<body>、<style>、<script>。""",
            chunk_system,
            max_retries=1,
        ))
        fragments.append(fragment)

    js = _clean_js_chunk(await agent.think(
        f"""{shared_context}

复刻蓝图：
{blueprint}

第 4 步：只输出少量原生 JavaScript，用于标签切换、选中态或按钮反馈。
如果截图是静态页面且不需要交互，输出：无需JS
不要输出 <script> 标签。""",
        chunk_system,
        max_retries=1,
    ))

    body = "\n".join(fragment for fragment in fragments if fragment.strip())
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>截图复刻页面</title>
  <style>
{RECREATE_BASE_CSS}
{css}
  </style>
</head>
<body>
  <div class="pixel-replica">
{body}
  </div>
  <script>
{js}
  </script>
</body>
</html>"""
    return html


def _should_preanalyze_visual(task_description: str, visual_mode: str) -> bool:
    if visual_mode not in ("recreate", "reference") or "[[AIKY_IMAGE:" not in task_description:
        return False
    lower = task_description.lower()
    explicit_keywords = [
        "先分析", "先拆解", "视觉结构", "结构拆解", "分析图片", "拆一下",
        "先看看图", "提炼风格", "总结风格", "visual brief", "analyze first",
    ]
    return any(keyword in lower for keyword in explicit_keywords)


class WorkerAgent(BaseAgent):
    def __init__(self, agent_id: str, name: str, role: AgentRole, skills: list):
        super().__init__(agent_id, name, role, skills)

    async def handle_message(self, message: Message):
        if message.message_type == MessageType.COMMAND:
            await self.perform_work(message.content)

    async def perform_work(self, task_description: str):
        config = _effective_config(self.state.role, task_description)

        await self.update_status(AgentStatus.WORKING, task_description[:30])
        await self.send_chat_message(config.get("start_msg", "收到，老大，我来处理。"))

        try:
            # 构建 prompt
            ext = config.get("ext", ".md")
            if config.get("system_override"):
                system_prompt = config["system_override"]
            elif config.get("workflow"):
                system_prompt = WorkflowManager.get_role_prompt(self.state.name, config["workflow"])
            else:
                system_prompt = config.get("fallback_prompt", f"You are {self.state.name}, a {self.state.role.value}.")
            system_prompt = f"{system_prompt}\n\n{USER_REQUIREMENTS_INSTRUCTION}"
            if "[[AIKY_IMAGE:" in task_description:
                system_prompt = f"{system_prompt}\n\n{VISION_CONTEXT_INSTRUCTION}"
            visual_mode = _visual_html_mode(task_description, ext)
            if visual_mode == "recreate":
                system_prompt = f"{system_prompt}\n\n{SCREENSHOT_TO_HTML_INSTRUCTION}"
            elif visual_mode == "reference":
                system_prompt = f"{system_prompt}\n\n{VISUAL_REFERENCE_HTML_INSTRUCTION}"
            if visual_mode in ("recreate", "reference"):
                system_prompt = system_prompt.replace(
                    "Use Vue 3 CDN or vanilla JS for interactivity",
                    "Prefer compact vanilla JS only when interactivity is necessary; avoid external frameworks for screenshot recreation"
                )
            if ext == ".html" and visual_mode == "recreate":
                content = await _generate_recreate_html_stream(self, task_description, system_prompt)
            elif ext == ".html" and visual_mode == "reference":
                content = await _generate_reference_html_stream(self, task_description, system_prompt)
            else:
                task_description = await _build_visual_brief(self, task_description, visual_mode)
                content = await self.think(task_description, system_prompt)

            # 保存产出物
            target_folder = self.state.current_folder
            if not target_folder:
                workspace_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workspace")
                target_folder = workspace_dir

            prefix = config.get("prefix", "Artifact")
            title_seed = _artifact_title_seed(task_description)
            safe_title = "".join([c if c.isalnum() or '\u4e00' <= c <= '\u9fff' else "_" for c in title_seed[:15]])
            filename = f"{prefix}_{safe_title}{ext}"

            # HTML 文件需要提取纯 HTML
            if ext == ".html":
                content = _extract_html(content)
                content = await _continue_truncated_html(self, content, system_prompt, task_description)
                if not _looks_like_visible_html(content):
                    if visual_mode in ("recreate", "reference") and "[[AIKY_IMAGE:" in task_description:
                        await self.send_chat_message("老大，流式生成结果仍然无效。我切到分块兜底模式。")
                        if visual_mode == "recreate":
                            content = await _generate_recreate_html_in_chunks(self, task_description)
                        else:
                            brief_description = await _build_visual_brief_internal(
                                self,
                                task_description,
                                visual_mode,
                                force=True,
                            )
                            content = await self.think(brief_description, system_prompt, max_retries=1)
                        content = _extract_html(content)
                        content = await _continue_truncated_html(self, content, system_prompt, task_description)
                    if not _looks_like_visible_html(content):
                        raise RuntimeError("模型没有输出有效的 HTML 页面，已停止保存空白产物")

            self._save_artifact(filename, content, target_folder)

            # 通知完成
            metadata = {"filename": filename, "folder": target_folder, "agent_id": self.state.id}
            if ext == ".html":
                metadata["type"] = "html"
            remember_artifact(metadata)
            await self.send_chat_message(
                _done_message(self.state.role, filename, task_description, ext),
                MessageType.ARTIFACT,
                metadata
            )

        except Exception as e:
            error_text = str(e)
            if "AI Service Unavailable" in error_text or "Request timed out" in error_text:
                await self.send_chat_message(
                    f"老大，我这次调用模型没接住，可能是服务繁忙、网络波动，或上下文太长。"
                    f"\n\n原始错误：{error_text}"
                )
            else:
                await self.send_chat_message(f"老大，我执行时出错了：{error_text}")
            import traceback
            traceback.print_exc()

        await self.update_status(AgentStatus.IDLE)

    async def revise_artifact(self, feedback: str, artifact: Dict):
        config = ROLE_CONFIG.get(self.state.role, {})
        folder = artifact.get("folder")
        filename = artifact.get("filename")
        if not folder or not filename:
            await self.send_chat_message("老大，我没找到上一个产物的位置，没法直接修改。")
            return

        file_path = os.path.join(folder, filename)
        if not os.path.exists(file_path):
            await self.send_chat_message(f"老大，我找不到上一个产物文件：{filename}")
            return

        await self.update_status(AgentStatus.WORKING, "修改上一个产物")
        await self.send_chat_message(f"收到，老大，我直接修改上一个产物：`{filename}`。")

        with open(file_path, "r", encoding="utf-8") as f:
            current_content = f.read()

        ext = os.path.splitext(filename)[1].lower()
        if config.get("system_override"):
            system_prompt = config["system_override"]
        elif config.get("workflow"):
            system_prompt = WorkflowManager.get_role_prompt(self.state.name, config["workflow"])
        else:
            system_prompt = config.get("fallback_prompt", f"You are {self.state.name}, a {self.state.role.value}.")
        system_prompt = f"{system_prompt}\n\n{USER_REQUIREMENTS_INSTRUCTION}"
        if "[[AIKY_IMAGE:" in feedback:
            system_prompt = f"{system_prompt}\n\n{VISION_CONTEXT_INSTRUCTION}"
        visual_mode = _visual_html_mode(feedback, ext)
        if visual_mode == "recreate":
            system_prompt = f"{system_prompt}\n\n{SCREENSHOT_TO_HTML_INSTRUCTION}"
        elif visual_mode == "reference":
            system_prompt = f"{system_prompt}\n\n{VISUAL_REFERENCE_HTML_INSTRUCTION}"
        if visual_mode in ("recreate", "reference"):
            system_prompt = system_prompt.replace(
                "Use Vue 3 CDN or vanilla JS for interactivity",
                "Prefer compact vanilla JS only when interactivity is necessary; avoid external frameworks for screenshot recreation"
            )

        try:
            if ext == ".html" and visual_mode == "recreate":
                new_content = await _generate_recreate_html_stream(self, feedback, system_prompt)
            elif ext == ".html" and visual_mode == "reference":
                new_content = await _generate_reference_html_stream(self, feedback, system_prompt)
            else:
                feedback = await _build_visual_brief(self, feedback, visual_mode)

                revision_input = f"""用户要求修改上一个产物。

用户反馈：
{feedback}

当前文件名：{filename}

当前文件内容：
{current_content}

请基于用户反馈直接输出修改后的完整文件内容。不要解释，不要输出 diff。
如果是 HTML，必须输出完整 HTML，从 <!DOCTYPE html> 到 </html>。"""

                new_content = await self.think(revision_input, system_prompt)
            if ext == ".html":
                new_content = _extract_html(new_content)
                new_content = await _continue_truncated_html(self, new_content, system_prompt, feedback)
                if not _looks_like_visible_html(new_content):
                    if visual_mode in ("recreate", "reference") and "[[AIKY_IMAGE:" in feedback:
                        await self.send_chat_message("老大，流式修改结果仍然无效。我切到分块兜底模式。")
                        if visual_mode == "recreate":
                            new_content = await _generate_recreate_html_in_chunks(self, feedback)
                        else:
                            feedback = await _build_visual_brief_internal(self, feedback, visual_mode, force=True)
                            revision_input = f"""用户要求修改上一个产物。

用户反馈：
{feedback}

当前文件名：{filename}

当前文件内容：
{current_content}

请基于用户反馈直接输出修改后的完整文件内容。不要解释，不要输出 diff。
                        如果是 HTML，必须输出完整 HTML，从 <!DOCTYPE html> 到 </html>。"""
                            new_content = await self.think(revision_input, system_prompt, max_retries=1)
                        new_content = _extract_html(new_content)
                        new_content = await _continue_truncated_html(self, new_content, system_prompt, feedback)
                    if not _looks_like_visible_html(new_content):
                        raise RuntimeError("模型没有输出有效的 HTML 页面，已停止覆盖原产物")
            self._save_artifact(filename, new_content, folder)

            metadata = dict(artifact)
            metadata["agent_id"] = self.state.id
            if ext == ".html":
                metadata["type"] = "html"
            remember_artifact(metadata)
            await self.send_chat_message(
                f"老大，我已根据反馈修改了 { _infer_artifact_label(self.state.role, filename, feedback, ext) }。",
                MessageType.ARTIFACT,
                metadata
            )
        except Exception as e:
            await self.send_chat_message(f"老大，我修改上一个产物时出错了：{str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            await self.update_status(AgentStatus.IDLE)
