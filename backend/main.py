"""
AI办公室 Multi-Agent System — 主入口
FastAPI + WebSocket 实时协作平台
"""
import os
import json
import asyncio
import logging
import threading
import time
import webbrowser
import re
from typing import List, Dict
from contextlib import asynccontextmanager
from datetime import datetime
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.encoders import jsonable_encoder

from models import AgentState, SystemState, Message, Task, AgentRole, AgentStatus, MessageType
from agents.orchestrator import OrchestratorAgent
from agents.worker_agents import WorkerAgent
from agents.ceo_agent import CEOAgent
from agents.cto_agent import CTOAgent
from agents.base_agent import set_broadcast_callback
from office_registry import load_office_registry, get_agent_profile, get_agent_skills

# 加载环境变量
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
HISTORY_DIR = os.path.join(PROJECT_ROOT, "history")
os.makedirs(HISTORY_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("AIky")

# --- 全局状态 ---
system_state = SystemState()
agent_instances: Dict[str, object] = {}
agent_loop_tasks: Dict[str, asyncio.Task] = {}
running_task_jobs: Dict[str, asyncio.Task] = {}
browser_opened = False


# --- WebSocket 连接管理 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active_connections:
            try:
                json_data = jsonable_encoder(message)
                await conn.send_json(json_data)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.active_connections.remove(conn)


manager = ConnectionManager()


AIKY_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, "..", "AIky"))


def _agent_learning_text(agent_id: str, profile: dict) -> str:
    parts = [
        agent_id,
        profile.get("name", ""),
        profile.get("title", ""),
        profile.get("department", ""),
        profile.get("mission", ""),
        " ".join(profile.get("skills", [])),
        " ".join(profile.get("primary_workflows", [])),
        " ".join(profile.get("support_workflows", [])),
        " ".join((profile.get("evolution") or {}).get("focus", [])),
    ]
    return " ".join(parts).lower()


def route_learning_target(content: str) -> dict:
    """Route a learning note to the most relevant employee using registry keywords."""
    registry = system_state.office or load_office_registry()
    text = (content or "").lower()
    agents = registry.get("agents", {})

    keyword_boosts = {
        "pm_01": ["prd", "需求", "产品", "用户", "验收", "ac", "fr", "框架图", "故事"],
        "ceo_01": ["市场", "竞品", "商业", "战略", "行业", "增长", "go/no-go", "调研"],
        "cto_01": ["架构", "技术", "选型", "数据库", "api", "安全", "性能", "扩展"],
        "ui_01": ["ui", "ux", "界面", "视觉", "交互", "设计", "原型", "布局"],
        "fe_01": ["前端", "vue", "react", "html", "css", "javascript", "交互实现", "响应式"],
        "be_01": ["后端", "接口", "服务", "python", "node", "数据库", "权限", "api"],
        "qa_01": ["测试", "qa", "bug", "缺陷", "用例", "覆盖率", "验收", "回归"],
    }

    best = {"agent_id": "aiky_main", "score": 0, "matched": []}
    for agent_id, profile in agents.items():
        haystack = _agent_learning_text(agent_id, profile)
        score = 0
        matched = []
        for token in re.split(r"[\s,，。；;:：/、()（）\[\]【】]+", text):
            if token and len(token) > 1 and token in haystack:
                score += 1
                matched.append(token)
        for keyword in keyword_boosts.get(agent_id, []):
            if keyword.lower() in text:
                score += 3
                matched.append(keyword)
        if score > best["score"]:
            best = {"agent_id": agent_id, "score": score, "matched": matched[:8]}

    if best["score"] == 0:
        best = {"agent_id": "aiky_main", "score": 1, "matched": ["general"]}
    return best


def append_learning_record(content: str, route: dict) -> dict:
    registry = system_state.office or load_office_registry()
    agent_id = route["agent_id"]
    profile = get_agent_profile(agent_id)
    if not profile and agent_id == registry.get("brain", {}).get("id"):
        profile = registry.get("brain", {})

    now = datetime.now()
    learning_dir = os.path.join(AIKY_ROOT, "learning")
    agent_dir = os.path.join(learning_dir, "agent-evolution")
    os.makedirs(agent_dir, exist_ok=True)

    display_name = profile.get("name", agent_id)
    title = profile.get("title", "")
    safe_agent = re.sub(r"[^a-zA-Z0-9_-]+", "_", agent_id)
    record_id = f"LEARN-{now.strftime('%Y%m%d-%H%M%S')}-{safe_agent}"

    record = f"""
## {record_id}
| 信息项 | 内容 |
|--------|------|
| 时间 | {now.strftime('%Y-%m-%d %H:%M:%S')} |
| 指派员工 | {display_name} ({title}) |
| 员工ID | {agent_id} |
| 匹配原因 | {', '.join(route.get('matched') or [])} |
| 状态 | Observation |

### 对话输入
{content.strip()}

### 后续建议
- 需要时使用 `/aiky-distill` 提炼为该员工的 `METHOD-CAND-*`
- 若多次出现同类反馈，再进入 `/aiky-benchmark` 或 `/aiky-retro`
"""

    agent_file = os.path.join(agent_dir, f"{safe_agent}.md")
    with open(agent_file, "a", encoding="utf-8") as f:
        f.write(record)

    feedback_log = os.path.join(learning_dir, "feedback-log.md")
    with open(feedback_log, "a", encoding="utf-8") as f:
        f.write(f"""
## FB-{now.strftime('%Y%m%d-%H%M%S')} 员工进化输入
| 信息项 | 内容 |
|--------|------|
| 场景 | Work Office 员工对话式学习 |
| 类型 | AgentLearning |
| 指派员工 | {display_name} ({agent_id}) |
| 初步归因 | AutoRoute |
| 处理建议 | Distill / Review / Benchmark |

### 原始反馈
{content.strip()}
""")

    return {
        "record_id": record_id,
        "agent_id": agent_id,
        "agent_name": display_name,
        "agent_title": title,
        "matched": route.get("matched", []),
        "path": agent_file,
    }


# --- 事件总线回调 ---
async def on_agent_event(event: dict):
    """Agent 产生事件时，统一通过 WebSocket 广播到前端"""
    # 如果是消息事件，同时存储到 system_state
    if event.get("type") == "new_message" and "data" in event:
        msg = Message(**event["data"])
        system_state.messages.append(msg)

    await manager.broadcast(event)

set_broadcast_callback(on_agent_event)


# --- 初始化 Agent ---
def init_system():
    registry = load_office_registry()
    system_state.office = registry

    # Orchestrator
    aiky = OrchestratorAgent()
    aiky.state.capability = get_agent_profile(aiky.state.id)
    system_state.agents[aiky.state.id] = aiky.state
    agent_instances[aiky.state.id] = aiky

    # C-Level
    steve = CEOAgent()
    steve.state.skills = get_agent_skills(steve.state.id, steve.state.skills)
    steve.state.capability = get_agent_profile(steve.state.id)
    system_state.agents[steve.state.id] = steve.state
    agent_instances[steve.state.id] = steve

    elon = CTOAgent()
    elon.state.skills = get_agent_skills(elon.state.id, elon.state.skills)
    elon.state.capability = get_agent_profile(elon.state.id)
    system_state.agents[elon.state.id] = elon.state
    agent_instances[elon.state.id] = elon

    # Workers
    workers = [
        ("pm_01", "Emma", AgentRole.PRODUCT_MANAGER, ["PRD", "Analysis"]),
        ("ui_01", "Alex", AgentRole.UI_DESIGNER, ["Figma", "Sketch"]),
        ("fe_01", "Lucas", AgentRole.FRONTEND_DEV, ["Vue", "React"]),
        ("be_01", "David", AgentRole.BACKEND_DEV, ["Python", "Node"]),
        ("qa_01", "Sarah", AgentRole.QA_ENGINEER, ["Selenium", "Jest"]),
    ]
    for uid, name, role, skills in workers:
        worker = WorkerAgent(uid, name, role, get_agent_skills(uid, skills))
        worker.state.capability = get_agent_profile(uid)
        system_state.agents[uid] = worker.state
        agent_instances[uid] = worker


init_system()


def drain_agent_queue(agent):
    queue = getattr(agent, "message_queue", None)
    if not queue:
        return
    while True:
        try:
            queue.get_nowait()
            queue.task_done()
        except asyncio.QueueEmpty:
            break


def restart_agent_loop(agent_id: str):
    old = agent_loop_tasks.get(agent_id)
    if old and not old.done():
        old.cancel()
    agent = agent_instances.get(agent_id)
    if agent:
        agent_loop_tasks[agent_id] = asyncio.create_task(agent.process_messages())


async def broadcast_chat(sender_id: str, content: str, msg_type: MessageType = MessageType.TEXT, metadata: dict = None):
    msg = Message(
        sender_id=sender_id,
        receiver_id="frontend",
        content=content,
        message_type=msg_type,
        metadata=metadata or {},
    )
    await on_agent_event({"type": "new_message", "data": msg.model_dump(mode="json")})
    return msg


async def reset_all_agents(action: str = ""):
    for agent_id, agent in agent_instances.items():
        drain_agent_queue(agent)
        await agent.update_status(AgentStatus.IDLE, action)
        restart_agent_loop(agent_id)


async def stop_task_runtime(task_id: str = None, reason: str = "用户手动停止"):
    target_ids = [task_id] if task_id else list(running_task_jobs.keys())
    cancelled = []
    for tid in target_ids:
        job = running_task_jobs.pop(tid, None)
        if job and not job.done():
            job.cancel()
            cancelled.append(tid)

    for tid, task in system_state.tasks.items():
        if task_id and tid != task_id:
            continue
        if task.status in ("pending", "in_progress", "waiting_for_confirm", "paused"):
            task.status = "stopped"
            task.analysis_result = f"🛑 已停止：{reason}"

    aiky_agent = agent_instances.get("aiky_main")
    if aiky_agent:
        if task_id:
            aiky_agent.active_tasks.pop(task_id, None)
        else:
            aiky_agent.active_tasks.clear()

    await reset_all_agents()
    return cancelled


def is_stop_command(text: str) -> bool:
    clean = (text or "").strip().lower().strip("。！!.~～")
    return clean in {"停止", "暂停", "取消", "终止", "stop", "pause", "cancel", "halt"}


def persist_user_message(content: str, message_id: str = None):
    content = (content or "").strip()
    if not content:
        return None
    if message_id and any(m.id == message_id for m in system_state.messages):
        return None
    msg = Message(
        id=message_id or f"user_{int(time.time() * 1000)}",
        sender_id="user",
        receiver_id="aiky_main",
        content=content,
        message_type=MessageType.TEXT,
    )
    system_state.messages.append(msg)
    return msg


def open_browser_if_enabled():
    """Open the frontend after the server process has started."""
    global browser_opened
    enabled = os.getenv("AIKY_AUTO_OPEN_BROWSER", "").lower() in ("1", "true", "yes", "on")
    if not enabled or browser_opened:
        return

    browser_opened = True
    url = os.getenv("AIKY_AUTO_OPEN_URL", f"http://localhost:{SERVER_PORT}")

    def open_browser():
        time.sleep(1.5)
        ok = webbrowser.open(url, new=2)
        if ok:
            logger.info(f"Browser opened: {url}")
        else:
            logger.warning(f"Could not open browser automatically: {url}")

    threading.Thread(target=open_browser, daemon=True).start()


# --- 后台循环 ---
async def state_broadcast_loop():
    """定期广播系统全量状态"""
    while True:
        try:
            await manager.broadcast({
                "type": "state_update",
                "data": system_state.model_dump(mode="json")
            })
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化所有 Agent 消息循环"""
    bg_tasks = []
    bg_tasks.append(asyncio.create_task(state_broadcast_loop()))

    logger.info("Starting agent message loops...")
    for agent_id, agent in agent_instances.items():
        loop_task = asyncio.create_task(agent.process_messages())
        agent_loop_tasks[agent_id] = loop_task
        bg_tasks.append(loop_task)
        logger.info(f"  ✓ {agent.state.name} ({agent.state.role.value})")

    logger.info(f"{'=' * 50}")
    logger.info(f"  AI办公室 Running on Port {SERVER_PORT}")
    logger.info(f"  Open: http://localhost:{SERVER_PORT}")
    logger.info(f"{'=' * 50}")
    open_browser_if_enabled()

    yield

    for t in bg_tasks:
        t.cancel()


app = FastAPI(title="AI办公室 Multi-Agent System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- REST API ---

@app.get("/api/system/state")
async def get_system_state():
    return system_state


@app.get("/api/office/registry")
async def get_office_registry():
    return system_state.office or load_office_registry()


@app.post("/api/evolution/learn")
async def agent_evolution_learn(payload: dict):
    content = (payload.get("content") or "").strip()
    if not content:
        return JSONResponse(status_code=400, content={"error": "content is required"})
    persist_user_message(content, payload.get("message_id"))

    route = route_learning_target(content)
    result = append_learning_record(content, route)

    agent = agent_instances.get(result["agent_id"])
    if agent:
        await agent.update_status(AgentStatus.THINKING, "吸收进化输入")
        await agent.send_chat_message(
            f"收到，老大，我记下来了。\n\n"
            f"记录编号：`{result['record_id']}`，后面我会把它放进方法提炼和复盘里。"
        )
        await agent.update_status(AgentStatus.IDLE, "")

    return result


@app.post("/api/tasks/create")
async def create_task(task_request: dict):
    description = (task_request.get("description") or "").strip()
    persist_user_message(description, task_request.get("message_id"))
    if is_stop_command(description):
        cancelled = await stop_task_runtime(reason="收到停止指令")
        await broadcast_chat("aiky_main", "🛑 已收到停止指令，当前工作已停止，员工已复位。")
        return {"status": "stopped", "cancelled_jobs": cancelled}

    task_id = str(len(system_state.tasks) + 1)
    new_task = Task(
        id=task_id,
        title=task_request.get("title", "Untitled"),
        description=description,
        status="pending",
        assigned_to="aiky_main"
    )
    system_state.tasks[task_id] = new_task

    aiky_agent = agent_instances.get("aiky_main")
    if aiky_agent:
        # 同步系统中等待确认的任务到 orchestrator 的 active_tasks
        for tid, t in system_state.tasks.items():
            if t.status in ("waiting_for_confirm", "in_progress") and tid not in aiky_agent.active_tasks:
                aiky_agent.active_tasks[tid] = t

        async def run_and_save():
            try:
                await aiky_agent.assign_task(new_task, agent_instances)
                save_conversation_history(task_id)
            except asyncio.CancelledError:
                new_task.status = "stopped"
                new_task.analysis_result = "🛑 任务已被用户手动停止。"
                raise
            finally:
                running_task_jobs.pop(task_id, None)

        running_task_jobs[task_id] = asyncio.create_task(run_and_save())

    return {"status": "success", "task_id": task_id}


@app.post("/api/tasks/{task_id}/approve")
async def approve_task(task_id: str):
    if task_id not in system_state.tasks:
        return JSONResponse({"status": "error", "message": "Task not found"}, status_code=404)

    task = system_state.tasks[task_id]
    if task.status != "waiting_for_confirm":
        return JSONResponse({"status": "error", "message": "Task not awaiting confirmation"}, status_code=400)

    aiky_agent = agent_instances.get("aiky_main")
    if aiky_agent:
        async def run_continue():
            try:
                await aiky_agent.continue_task(task, agent_instances)
                save_conversation_history(task_id)
            except asyncio.CancelledError:
                task.status = "stopped"
                task.analysis_result = "🛑 任务已被用户手动停止。"
                raise
            finally:
                running_task_jobs.pop(task_id, None)

        running_task_jobs[task_id] = asyncio.create_task(run_continue())

    return {"status": "success", "message": "Approved. Continuing workflow."}


@app.post("/api/tasks/{task_id}/reject")
async def reject_task(task_id: str):
    if task_id not in system_state.tasks:
        return JSONResponse({"status": "error", "message": "Task not found"}, status_code=404)

    task = system_state.tasks[task_id]
    task.status = "failed"
    job = running_task_jobs.pop(task_id, None)
    if job and not job.done():
        job.cancel()
    return {"status": "success", "message": "Task rejected."}


@app.post("/api/tasks/{task_id}/stop")
async def stop_task(task_id: str):
    if task_id not in system_state.tasks:
        return JSONResponse({"status": "error", "message": "Task not found"}, status_code=404)

    cancelled = await stop_task_runtime(task_id)
    await broadcast_chat("aiky_main", "🛑 已停止当前任务，所有员工已复位为空闲。")
    return {"status": "success", "task_id": task_id, "cancelled_jobs": cancelled}


@app.post("/api/tasks/stop-active")
async def stop_active_tasks():
    cancelled = await stop_task_runtime()
    await broadcast_chat("aiky_main", "🛑 已停止所有当前工作，员工状态已复位。")
    return {"status": "success", "cancelled_jobs": cancelled}


@app.get("/api/artifacts/{task_id}/{filename}")
async def get_artifact(task_id: str, filename: str):
    """读取指定任务的产出物内容"""
    workspace_dir = os.path.join(PROJECT_ROOT, "workspace")

    # 查找匹配的目录（task_id 可能是前缀）
    target_dir = None
    if os.path.exists(workspace_dir):
        for d in os.listdir(workspace_dir):
            if d.startswith(task_id) and os.path.isdir(os.path.join(workspace_dir, d)):
                target_dir = os.path.join(workspace_dir, d)
                break

    if not target_dir:
        return JSONResponse({"error": "Task folder not found"}, status_code=404)

    file_path = os.path.join(target_dir, filename)
    if not os.path.exists(file_path):
        return JSONResponse({"error": "File not found"}, status_code=404)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    return {"filename": filename, "content": content}


@app.get("/api/workspace/files")
async def list_workspace_files():
    workspace_dir = os.path.join(PROJECT_ROOT, "workspace")
    if not os.path.exists(workspace_dir):
        return []

    result = []
    for name in sorted(os.listdir(workspace_dir), reverse=True):
        full_path = os.path.join(workspace_dir, name)
        if os.path.isdir(full_path):
            files = [f for f in os.listdir(full_path) if os.path.isfile(os.path.join(full_path, f))]
            result.append({"name": name, "type": "folder", "files": files})
        elif os.path.isfile(full_path):
            result.append({"name": name, "type": "file", "size": os.path.getsize(full_path)})

    return result


@app.get("/api/workspace/read/{filepath:path}")
async def read_workspace_file(filepath: str):
    """通用文件读取"""
    workspace_dir = os.path.join(PROJECT_ROOT, "workspace")
    full_path = os.path.normpath(os.path.join(workspace_dir, filepath))

    # 防止路径穿越
    if not full_path.startswith(os.path.normpath(workspace_dir)):
        return JSONResponse({"error": "Access denied"}, status_code=403)

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        return JSONResponse({"error": "File not found"}, status_code=404)

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    return {"path": filepath, "content": content}


@app.get("/api/workspace/preview/{filepath:path}")
async def preview_html_file(filepath: str):
    """直接返回 HTML 文件内容用于 iframe 预览"""
    from fastapi.responses import HTMLResponse

    workspace_dir = os.path.join(PROJECT_ROOT, "workspace")
    full_path = os.path.normpath(os.path.join(workspace_dir, filepath))

    if not full_path.startswith(os.path.normpath(workspace_dir)):
        return JSONResponse({"error": "Access denied"}, status_code=403)

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        return JSONResponse({"error": "File not found"}, status_code=404)

    if not full_path.endswith(".html"):
        return JSONResponse({"error": "Not an HTML file"}, status_code=400)

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    return HTMLResponse(content=content)


# --- WebSocket ---

# --- History API ---

def save_conversation_history(task_id: str = None):
    """保存当前对话到历史记录JSON文件"""
    try:
        msgs = [m.model_dump(mode="json") for m in system_state.messages]
        if not msgs:
            return

        tasks_data = {}
        for tid, t in system_state.tasks.items():
            tasks_data[tid] = t.model_dump(mode="json")

        # 用第一个任务的标题作为对话标题
        title = "未命名对话"
        for t in system_state.tasks.values():
            if t.title and t.title != "Untitled":
                title = t.title
                break

        conv_id = task_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        history_data = {
            "id": conv_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "message_count": len(msgs),
            "task_count": len(tasks_data),
            "messages": msgs,
            "tasks": tasks_data,
        }

        file_path = os.path.join(HISTORY_DIR, f"{conv_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved conversation history: {conv_id}")
    except Exception as e:
        logger.error(f"Failed to save history: {e}")


@app.get("/api/history")
async def list_history():
    """列出所有历史对话（摘要信息）"""
    histories = []
    if not os.path.exists(HISTORY_DIR):
        return histories

    for fname in sorted(os.listdir(HISTORY_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(HISTORY_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            histories.append({
                "id": data.get("id", fname.replace(".json", "")),
                "title": data.get("title", "未命名"),
                "created_at": data.get("created_at", ""),
                "message_count": data.get("message_count", 0),
                "task_count": data.get("task_count", 0),
            })
        except Exception:
            continue

    return histories


@app.get("/api/history/{conv_id}")
async def get_history(conv_id: str):
    """获取指定历史对话的完整内容"""
    fpath = os.path.join(HISTORY_DIR, f"{conv_id}.json")
    if not os.path.exists(fpath):
        return JSONResponse({"error": "History not found"}, status_code=404)

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@app.delete("/api/history/{conv_id}")
async def delete_history(conv_id: str):
    """删除指定历史对话"""
    fpath = os.path.join(HISTORY_DIR, f"{conv_id}.json")
    if not os.path.exists(fpath):
        return JSONResponse({"error": "History not found"}, status_code=404)
    os.remove(fpath)
    return {"status": "success"}


@app.post("/api/history/save")
async def save_current():
    """手动保存当前对话"""
    save_conversation_history()
    return {"status": "success"}


@app.post("/api/conversation/new")
async def new_conversation():
    """开始新对话：保存当前 → 清空状态"""
    if system_state.messages:
        save_conversation_history()
    system_state.messages.clear()
    system_state.tasks.clear()
    # 重置所有 Agent 状态
    for agent_id, agent in agent_instances.items():
        agent.state.status = AgentStatus.IDLE
        agent.state.current_action = ""
    return {"status": "success"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# --- 静态文件（必须最后注册） ---

FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

if os.path.exists(os.path.join(FRONTEND_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
