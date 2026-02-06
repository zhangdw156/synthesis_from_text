"""工作流发现步骤"""

import logging
from pathlib import Path

from gem.llm.client import LLMClient
from gem.models.annotation import TagAnnotation
from gem.models.workflow import Workflow
from gem.parsers.workflow import WorkflowParser
from gem.steps.base import PipelineStep

logger = logging.getLogger(__name__)


class WorkflowDiscoveryStep(PipelineStep[list[Workflow]]):
    """步骤2: 工作流与工具发现

    从文本中提取工作流和工具定义
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_path: str = "src/gem/prompts/workflow_and_tool_discovery.md",
    ):
        self.llm = llm_client
        self.parser = WorkflowParser()

        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        self.prompt_template = prompt_file.read_text(encoding="utf-8")

    @property
    def step_name(self) -> str:
        return "workflow_discovery"

    def execute(self, annotation: TagAnnotation) -> list[Workflow] | None:
        """执行工作流发现

        Args:
            annotation: 标签标注结果（包含原始文本信息）

        Returns:
            成功: Workflow 列表
            失败: None（中止流水线）
        """
        try:
            # 获取原始文本（从 annotation 的上下文中）
            # 注意：这里需要一个方式传递原始文本
            # 修改设计：直接传入原始文本
            if not hasattr(annotation, "_raw_text"):
                logger.error("Workflow discovery: Missing raw text")
                return None

            text = annotation._raw_text

            # 填充 prompt
            prompt = self.prompt_template.replace("{text}", text)

            # 调用 LLM
            response = self.llm.call(prompt)
            if not response:
                logger.warning("Workflow discovery: LLM returned empty response")
                return None

            # 解析结果
            workflows = self.parser.parse(response)

            # 过滤空结果
            workflows = [w for w in workflows if w.steps or w.tools]

            if not workflows:
                logger.warning("Workflow discovery: No valid workflows found")
                return None

            logger.info(f"Workflow discovery: Found {len(workflows)} workflows")
            return workflows

        except Exception as e:
            logger.error(f"Workflow discovery step failed: {e}")
            return None

    def execute_with_text(self, text: str) -> list[Workflow] | None:
        """使用原始文本执行工作流发现（备用方法）"""
        try:
            prompt = self.prompt_template.replace("{text}", text)
            response = self.llm.call(prompt)
            if not response:
                return None

            workflows = self.parser.parse(response)
            workflows = [w for w in workflows if w.steps or w.tools]

            if not workflows:
                return None

            return workflows

        except Exception as e:
            logger.error(f"Workflow discovery step failed: {e}")
            return None
