"""标签标注模型"""

from pydantic import BaseModel


class TagAnnotation(BaseModel):
    """标签标注结果

    用于标记文本是否包含多步操作任务
    """
    multi_step: bool  # 是否多步任务
    summary: str      # 任务摘要
    domain: str       # 领域（支持多值逗号分隔）
    platform: str     # 平台（operator, computer, phone, machine, other）
    task: str         # 任务类别
