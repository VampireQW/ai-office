"""
AI办公室数据模型
"""
from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class AgentRole(str, Enum):
    BOSS = "boss"
    CEO = "ceo"
    CTO = "cto"
    AIKY_MAIN = "aiky_main"
    PRODUCT_MANAGER = "product_manager"
    UI_DESIGNER = "ui_designer"
    FRONTEND_DEV = "frontend_dev"
    BACKEND_DEV = "backend_dev"
    QA_ENGINEER = "qa_engineer"


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    WAITING = "waiting"
    SPEAKING = "speaking"


class MessageType(str, Enum):
    TEXT = "text"
    COMMAND = "command"
    ARTIFACT = "artifact"
    SYSTEM = "system"
    STAGE = "stage"


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str
    receiver_id: str = ""
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    message_type: MessageType = MessageType.TEXT
    metadata: Dict[str, Any] = {}


class TaskIntent(str, Enum):
    TASK = "task"              # 正式工作任务
    COMMAND = "command"        # 控制指令（暂停/取消）
    CHAT = "chat"              # 闲聊（已弃用，合并到 QA）
    QA = "qa"                  # 问答咨询：用户只是想问问题
    STAGE_CONTROL = "stage_control"  # 阶段控制：继续/跳过/回退到某阶段


class TaskScope(str, Enum):
    RESEARCH = "research"           # 仅市场调研
    COMPETITIVE = "competitive"     # 仅竞品分析
    ANALYSIS = "analysis"           # 调研 + 竞品分析
    PLANNING = "planning"           # 调研 + 竞品 + PRD
    FULL = "full"                   # 完整流程（调研→PRD→架构→开发→测试）


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    status: str = "pending"
    assigned_to: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    parent_task_id: Optional[str] = None
    subtasks: List["Task"] = []
    artifacts: List[Dict[str, Any]] = []
    folder_path: Optional[str] = None

    # Intent & Scope
    intent: TaskIntent = TaskIntent.TASK
    scope: TaskScope = TaskScope.FULL
    approval_stage: str = "none"
    selected_stages: List[str] = Field(default_factory=list)

    # HITL Fields
    confirmation_required: bool = False
    proposed_plan: Optional[str] = None
    analysis_result: Optional[str] = None


class AgentState(BaseModel):
    id: str
    name: str
    role: AgentRole
    status: AgentStatus = AgentStatus.IDLE
    current_task_id: Optional[str] = None
    current_action: str = ""
    skills: List[str] = []
    current_folder: Optional[str] = None
    capability: Dict[str, Any] = Field(default_factory=dict)


class SystemState(BaseModel):
    agents: Dict[str, AgentState] = {}
    tasks: Dict[str, Task] = {}
    messages: List[Message] = []
    office: Dict[str, Any] = Field(default_factory=dict)
