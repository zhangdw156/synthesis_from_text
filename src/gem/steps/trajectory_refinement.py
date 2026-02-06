"""轨迹优化步骤"""

import json
import logging
from pathlib import Path

from gem.llm.client import LLMClient
from gem.models.dialogue import Dialogue
from gem.models.trajectory import Trajectory
from gem.models.workflow import Workflow
from gem.parsers.trajectory import TrajectoryParser
from gem.steps.base import PipelineStep

logger = logging.getLogger(__name__)


class TrajectoryRefinementStep(PipelineStep[Trajectory]):
    """步骤4: 轨迹优化

    优化生成的轨迹，增加复杂性和自然性
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_path: str = "src/gem/prompts/trajectory_refinement.md"
    ):
        self.llm = llm_client
        self.parser = TrajectoryParser()

        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        self.prompt_template = prompt_file.read_text(encoding='utf-8')

    @property
    def step_name(self) -> str:
        return "trajectory_refinement"

    def execute(self, data: tuple[Workflow, Dialogue]) -> Trajectory | None:
        """执行轨迹优化

        Args:
            data: (workflow, dialogue) 元组

        Returns:
            成功: Trajectory 实例
            失败: None
        """
        try:
            workflow, dialogue = data

            # 准备输入
            tools_str = json.dumps(workflow.tools, ensure_ascii=False)
            dialogue_str = json.dumps(dialogue.model_dump(), ensure_ascii=False)

            # 填充 prompt
            prompt = (
                self.prompt_template
                .replace("{tools}", tools_str)
                .replace("{our_traj}", dialogue_str)
            )

            # 调用 LLM
            response = self.llm.call(prompt)
            if not response:
                logger.warning("Trajectory refinement: LLM returned empty response")
                return None

            # 解析结果
            trajectory = self.parser.parse(response)
            if not trajectory:
                logger.warning("Trajectory refinement: Failed to parse response")
                return None

            logger.info(f"Trajectory refinement: Refined to {len(trajectory.conversation)} messages")
            return trajectory

        except Exception as e:
            logger.error(f"Trajectory refinement step failed: {e}")
            return None
