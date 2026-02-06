"""LLM 客户端封装"""

from openai import OpenAI
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 客户端
    
    封装 OpenAI API 调用，支持本地 VLLM 部署
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        model_name: str = "Qwen3-8B",
        api_key: str = "dummy_key",
        temperature: float = 0.7,
        max_tokens: int = 40960,
        top_p: float = 0.95,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
    
    def call(self, prompt: str) -> Optional[str]:
        """调用 LLM
        
        Args:
            prompt: 输入提示词
            
        Returns:
            成功: 模型生成的文本
            失败: None
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
            )
            
            content = response.choices[0].message.content
            
            # 处理 Qwen3 的特殊输出格式（去除 think 标签）
            if "</think>" in content:
                content = content.rsplit("</think>", 1)[-1].lstrip()
            
            return content
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None