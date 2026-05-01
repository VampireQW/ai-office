"""
WorkflowManager — 读取 PE Workflow 文件作为 Agent 的 System Prompt
"""
import os
import glob


# 内置后备提示词（workflow 文件找不到时使用）
FALLBACK_PROMPTS = {
    "2-pe-research": "Conduct thorough market research including: 1) Industry overview and trends, 2) Target user analysis, 3) Market size and growth potential, 4) Key opportunities and risks. Output a comprehensive research report in Chinese.",
    "3-pe-competitive": "Perform detailed competitive analysis including: 1) Identify top 3-5 competitors, 2) Feature comparison matrix, 3) Strengths and weaknesses analysis, 4) Differentiation opportunities. Output in Chinese.",
    "4-pe-prd": "Write an SDD Product Requirements Document (PRD) including: 1) Product overview, 2) REQ/FR/AC IDs, 3) Product framework diagram, 4) Functional and non-functional requirements, 5) Acceptance criteria. Output in Chinese.",
    "5-pe-architecture": "Design system architecture based on Frozen PRD including: 1) Information architecture, 2) Tech stack selection, 3) Data model, 4) API design, 5) Non-functional design. Output in Chinese.",
    "6-pe-tasks": "Break Frozen PRD and architecture into traceable SDD tasks. Map FR/AC/NFR/DATA to TASK and test coverage. Output in Chinese.",
    "7-pe-code": "Implement production-ready code according to SDD tasks with complete interactions, four states, realistic data, and no hidden requirements. Output in Chinese with code blocks when appropriate.",
    "8-pe-testing": "Create comprehensive SDD test cases mapped to FR/AC/NFR/TASK. P0 AC must be 100% covered. Output in Chinese.",
}


class WorkflowManager:
    WORKFLOW_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".agent", "workflows", "pe-workflows")
    )

    @staticmethod
    def get_workflow_content(filename_part: str) -> str:
        search_pattern = os.path.join(WorkflowManager.WORKFLOW_DIR, f"*{filename_part}*.md")
        files = glob.glob(search_pattern)

        if not files:
            # 使用内置后备提示词
            fallback = FALLBACK_PROMPTS.get(filename_part)
            if fallback:
                return fallback
            return f"Complete the assigned task professionally. Be thorough and output in Chinese."

        with open(files[0], "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def get_role_prompt(role_name: str, workflow_key: str) -> str:
        workflow_content = WorkflowManager.get_workflow_content(workflow_key)

        return f"""You are the {role_name} of the company.
Your work MUST strictly follow the standards defined in the following workflow document:

=== WORKFLOW STANDARD ===
{workflow_content}
=========================

Your output must adhere to the format, depth, and quality requirements specified above.
Output in Chinese (中文) by default unless the workflow specifies otherwise.
Do not deviate from this standard."""
