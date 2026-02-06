"""轨迹模型"""

from typing import Any

from pydantic import BaseModel

from gem.models.dialogue import Message


class ToolDefinition(BaseModel):
    """工具定义"""
    name: str
    description: str
    parameters: dict[str, Any]


class Trajectory(BaseModel):
    """完整轨迹（轨迹优化步骤的输出）"""
    toolsets: list[ToolDefinition]
    system_prompt: str
    conversation: list[Message]
