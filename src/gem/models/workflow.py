"""工作流模型"""

import re

from pydantic import BaseModel, field_validator


class Workflow(BaseModel):
    """工作流定义

    包含任务描述、执行步骤、执行图、动作和工具定义
    """
    description: str
    steps: str
    execution_graph: str
    actions: list[dict]
    tools: list[dict]

    @field_validator('steps')
    @classmethod
    def fix_newlines(cls, v: str) -> str:
        """清理步骤中的换行符"""
        v = v.replace('\\n', '\n')
        return re.sub(r'\n\s*\n', '\n', v).strip()
