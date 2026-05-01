"""
CTOAgent — 负责技术架构设计
"""
from models import AgentRole, AgentStatus, MessageType
from agents.base_agent import BaseAgent
from skills.workflow_manager import WorkflowManager


class CTOAgent(BaseAgent):
    def __init__(self, agent_id: str = "cto_01", name: str = "Elon"):
        super().__init__(agent_id, name, AgentRole.CTO, ["Architecture", "Tech Stack", "Database Design"])

    async def create_architecture(self, task_description: str, task_folder: str, prd_content: str = ""):
        """设计技术架构"""
        await self.update_status(AgentStatus.THINKING, "设计系统架构...")
        await self.send_chat_message("收到，老大，我来梳理技术架构、技术栈和数据库。")

        arch_prompt = WorkflowManager.get_role_prompt(self.state.name, "5-pe-architecture")

        context = f"Request: {task_description}\n"
        if prd_content:
            context += f"\nBased on PRD:\n{prd_content[:2000]}"

        try:
            arch_content = await self.think(context, arch_prompt)
        except RuntimeError as e:
            await self.send_chat_message(f"老大，我这次架构设计没跑通：{e}")
            await self.update_status(AgentStatus.IDLE)
            raise

        self._save_artifact("4-Architecture_Design.md", arch_content, task_folder)

        await self.send_chat_message(
            "老大，我完成了架构设计文档。",
            MessageType.ARTIFACT,
            {"filename": "4-Architecture_Design.md", "folder": task_folder}
        )

        await self.update_status(AgentStatus.IDLE)
