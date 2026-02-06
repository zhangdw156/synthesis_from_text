"""轨迹生成步骤"""

from typing import Optional, Tuple
import logging
import json
from pathlib import Path

from gem.steps.base import PipelineStep
from gem.models.workflow import Workflow
from gem.models.dialogue import Dialogue
from gem.llm.client import LLMClient
from gem.parsers.dialogue import DialogueParser

logger = logging.getLogger(__name__)


class TrajectoryGenerationStep(PipelineStep[Dialogue]):
    """步骤3: 轨迹生成
    
    基于工作流生成多轮对话轨迹
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        prompt_path: str = "src/gem/prompts/trajectory_generation.md"
    ):
        self.llm = llm_client
        self.parser = DialogueParser()
        
        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        self.prompt_template = prompt_file.read_text(encoding='utf-8')
    
    @property
    def step_name(self) -> str:
        return "trajectory_generation"
    
    def execute(self, data: Tuple[Workflow, int]) -> Optional[Dialogue]:
        """执行轨迹生成
        
        Args:
            data: (workflow, workflow_index) 元组
            
        Returns:
            成功: Dialogue 实例
            失败: None
        """
        try:
            workflow, index = data
            
            # 准备工具集 JSON
            tools_str = json.dumps(workflow.tools, ensure_ascii=False)
            
            # 填充 prompt
            prompt = (
                self.prompt_template
                .replace("{candidate_tools}", tools_str)
                .replace("{current_task}", workflow.steps)
            )
            
            # 调用 LLM
            response = self.llm.call(prompt)
            if not response:
                logger.warning(f"Trajectory generation [{index}]: LLM returned empty response")
                return None
            
            # 解析结果
            dialogue = self.parser.parse(response)
            if not dialogue:
                logger.warning(f"Trajectory generation [{index}]: Failed to parse response")
                return None
            
            logger.info(f"Trajectory generation [{index}]: Generated {len(dialogue.conversation)} messages")
            return dialogue
            
        except Exception as e:
            logger.error(f"Trajectory generation step failed: {e}")
            return None