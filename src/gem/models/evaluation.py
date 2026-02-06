"""评估模型"""

from pydantic import BaseModel, Field, field_validator


class EvaluationResult(BaseModel):
    """幻觉检测结果"""
    R1: int = Field(description="工具调用幻觉得分 (0 或 1)")
    R2: int = Field(description="能力幻觉得分 (0 或 1)")
    R3: int = Field(description="上下文幻觉得分 (0 或 1)")

    @field_validator('R1', 'R2', 'R3')
    @classmethod
    def check_binary(cls, v: int) -> int:
        """确保得分只能是 0 或 1"""
        if v not in (0, 1):
            raise ValueError("Score must be 0 or 1")
        return v

    def is_valid(self) -> bool:
        """检查是否通过所有评估（无幻觉）"""
        return self.R1 == 1 and self.R2 == 1 and self.R3 == 1
