"""对话模型"""


from pydantic import BaseModel


class ToolCall(BaseModel):
    """工具调用"""
    name: str
    arguments: dict


class Message(BaseModel):
    """单条消息"""
    role: str  # 'user', 'assistant', 'tool'
    content: str
    tool_calls: list[ToolCall] | None = None


class Dialogue(BaseModel):
    """对话轨迹（轨迹生成步骤的输出）"""
    system_prompt: str
    conversation: list[Message]
