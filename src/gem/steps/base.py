"""步骤基类"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)


class PipelineStep(ABC, Generic[T]):
    """流水线步骤的抽象基类
    
    所有数据处理步骤都应继承此类
    """
    
    @property
    @abstractmethod
    def step_name(self) -> str:
        """步骤名称"""
        pass
    
    @abstractmethod
    def execute(self, input_data: any) -> Optional[T]:
        """执行步骤
        
        Args:
            input_data: 输入数据
            
        Returns:
            成功: 解析后的模型实例
            失败: None（流水线将中止）
        """
        pass