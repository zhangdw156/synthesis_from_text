"""标签标注步骤"""

from typing import Optional
import logging
from pathlib import Path

from gem.steps.base import PipelineStep
from gem.models.annotation import TagAnnotation
from gem.llm.client import LLMClient
from gem.parsers.tag_annotation import TagAnnotationParser

logger = logging.getLogger(__name__)


class TagAnnotationStep(PipelineStep[TagAnnotation]):
    """步骤1: 标签标注
    
    判断文本是否包含多步操作任务，并提取相关信息
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        prompt_path: str = "src/gem/prompts/tag_annotation.md"
    ):
        self.llm = llm_client
        self.parser = TagAnnotationParser()
        
        # 加载 prompt
        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        self.prompt_template = prompt_file.read_text(encoding='utf-8')
    
    @property
    def step_name(self) -> str:
        return "tag_annotation"
    
    def execute(self, text: str) -> Optional[TagAnnotation]:
        """执行标签标注
        
        Args:
            text: 原始文本
            
        Returns:
            成功: TagAnnotation 实例
            失败/非多步任务: None（中止流水线）
        """
        try:
            # 填充 prompt
            prompt = self.prompt_template.replace("{text}", text)
            
            # 调用 LLM
            response = self.llm.call(prompt)
            if not response:
                logger.warning("Tag annotation: LLM returned empty response")
                return None
            
            # 解析结果
            result = self.parser.parse(response)
            if not result:
                logger.warning("Tag annotation: Failed to parse response")
                return None
            
            # 关键：如果非多步任务，返回 None 中止流水线
            if not result.multi_step:
                logger.info("Tag annotation: Not a multi-step task, skipping")
                return None
            
            logger.info(f"Tag annotation: Found multi-step task - {result.summary}")
            return result
            
        except Exception as e:
            logger.error(f"Tag annotation step failed: {e}")
            return None