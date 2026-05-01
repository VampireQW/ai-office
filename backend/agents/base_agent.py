"""
BaseAgent — 所有 Agent 的基类
提供消息队列、状态管理、LLM 调用、事件广播能力
"""
import asyncio
from typing import List, Optional, Callable, Awaitable
from models import AgentState, AgentRole, AgentStatus, Message, MessageType


# 全局事件总线：Agent 产生的事件通过此回调广播到 WebSocket
_broadcast_callback: Optional[Callable[[dict], Awaitable[None]]] = None


def set_broadcast_callback(callback: Callable[[dict], Awaitable[None]]):
    global _broadcast_callback
    _broadcast_callback = callback


async def broadcast_event(event: dict):
    if _broadcast_callback:
        await _broadcast_callback(event)


class BaseAgent:
    def __init__(self, agent_id: str, name: str, role: AgentRole, skills: List[str] = None):
        self.state = AgentState(
            id=agent_id,
            name=name,
            role=role,
            skills=skills or []
        )
        self.message_queue: asyncio.Queue = asyncio.Queue()

    async def receive_message(self, message: Message):
        await self.message_queue.put(message)

    async def update_status(self, status: AgentStatus, action: str = ""):
        self.state.status = status
        self.state.current_action = action
        # 广播状态变化
        await broadcast_event({
            "type": "agent_status",
            "agent_id": self.state.id,
            "agent_name": self.state.name,
            "status": status.value,
            "action": action
        })

    async def send_chat_message(self, content: str, msg_type: MessageType = MessageType.TEXT, metadata: dict = None):
        """向前端广播一条聊天消息"""
        msg = Message(
            sender_id=self.state.id,
            receiver_id="frontend",
            content=content,
            message_type=msg_type,
            metadata=metadata or {}
        )
        await broadcast_event({
            "type": "new_message",
            "data": msg.model_dump(mode="json")
        })
        return msg

    async def think(self, user_input: str, system_prompt: str = None, max_retries: int = 2) -> str:
        """调用 LLM 生成响应，自动重试，失败时抛出 RuntimeError"""
        await self.update_status(AgentStatus.THINKING, "思考中...")

        if not system_prompt:
            system_prompt = f"You are {self.state.name}, a {self.state.role.value}. Act professionally."

        from llm.glm_client import llm_client

        last_error = None
        for attempt in range(1, max_retries + 1):
            response = await llm_client.generate(system_prompt, user_input)
            if not response.startswith("Error:"):
                await self.update_status(AgentStatus.WORKING)
                return response
            last_error = response
            if attempt < max_retries:
                print(f"[{self.state.name}] LLM attempt {attempt} failed: {response}, retrying...")
                await self.send_chat_message(f"有点卡住了，我再试一次（{attempt}/{max_retries}）。")

        # 所有重试用尽
        raise RuntimeError(f"LLM 调用失败: {last_error}")

    async def think_stream(self, user_input: str, system_prompt: str = None, max_retries: int = 1) -> str:
        """流式调用 LLM，适合长 HTML 等大段输出。"""
        await self.update_status(AgentStatus.THINKING, "流式生成中...")

        if not system_prompt:
            system_prompt = f"You are {self.state.name}, a {self.state.role.value}. Act professionally."

        from llm.glm_client import llm_client

        last_error = None
        for attempt in range(1, max_retries + 1):
            response = await llm_client.generate_stream(system_prompt, user_input)
            if response and not response.startswith("Error:"):
                await self.update_status(AgentStatus.WORKING)
                return response
            last_error = response
            if attempt < max_retries:
                await self.send_chat_message(f"流式生成有点卡住了，我再试一次（{attempt}/{max_retries}）。")

        raise RuntimeError(f"LLM 流式调用失败: {last_error}")

    async def process_messages(self):
        """消息处理主循环"""
        while True:
            message = await self.message_queue.get()
            try:
                await self.handle_message(message)
            except Exception as e:
                print(f"[{self.state.name}] Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self.message_queue.task_done()

    async def handle_message(self, message: Message):
        """子类重写此方法处理消息"""
        pass

    def _save_artifact(self, filename: str, content: str, folder_path: str) -> Optional[str]:
        """保存产出物到指定目录，返回文件路径"""
        import os
        if not folder_path:
            print(f"[{self.state.name}] Error: No folder path specified")
            return None

        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        file_path = os.path.join(folder_path, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[{self.state.name}] Saved: {filename}")
        return file_path
