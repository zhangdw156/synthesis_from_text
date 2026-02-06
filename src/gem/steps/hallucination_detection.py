"""幻觉检测步骤"""

from typing import Optional
import logging
from pathlib import Path

from gem.steps.base import PipelineStep
from gem.models.trajectory import Trajectory
from gem.models.evaluation import EvaluationResult
from gem.llm.client import LLMClient
from gem.parsers.evaluation import EvaluationParser

logger = logging.getLogger(__name__)


class HallucinationDetectionStep(PipelineStep[Trajectory]):
    """步骤5: 幻觉检测
    
    评估轨迹质量，过滤有幻觉的数据
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        prompt_path: str = "src/gem/prompts/hallucination_detection.md"
    ):
        self.llm = llm_client
        self.parser = EvaluationParser()
        
        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        self.prompt_template = prompt_file.read_text(encoding='utf-8')
    
    @property
    def step_name(self) -> str:
        return "hallucination_detection"
    
    def execute(self, trajectory: Trajectory) -> Optional[Trajectory]:
        """执行幻觉检测
        
        Args:
            trajectory: 待评估的轨迹
            
        Returns:
            成功(无幻觉): 原 Trajectory 实例
            失败(有幻觉): None
        """
        try:
            # 填充 prompt
            prompt = self.prompt_template.replace(
                "{trajectory}",
                trajectory.model_dump_json()
            )
            
            # 调用 LLM
            response = self.llm.call(prompt)
            if not response:
                logger.warning("Hallucination detection: LLM returned empty response")
                return None
            
            # 解析结果
            evaluation = self.parser.parse(response)
            if not evaluation:
                logger.warning("Hallucination detection: Failed to parse response")
                return None
            
            # 检查是否通过所有评估
            if not evaluation.is_valid():
                logger.info(
                    f"Hallucination detected: R1={evaluation.R1}, "
                    f"R2={evaluation.R2}, R3={evaluation.R3}"
                )
                return None
            
            logger.info("Hallucination detection: Passed all checks")
            return trajectory
            
        except Exception as e:
            logger.error(f"Hallucination detection step failed: {e}")
            return None