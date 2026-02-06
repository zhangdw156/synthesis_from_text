"""工作流解析器"""

import re
from typing import Any

import dirtyjson

from gem.models.workflow import Workflow


class WorkflowParser:
    """解析工作流定义"""

    def parse(self, response: str) -> list[Workflow]:
        """从 LLM 输出解析工作流列表

        Args:
            response: LLM 原始输出

        Returns:
            Workflow 列表，无匹配时返回空列表
        """
        workflows = []

        # 匹配所有 workflow 块
        workflow_pattern = re.compile(
            r"<workflow>(.*?)</workflow>", re.DOTALL | re.MULTILINE
        )
        workflow_blocks = workflow_pattern.findall(response)

        for block in workflow_blocks:
            workflow = self._parse_single_workflow(block)
            if workflow:
                workflows.append(workflow)

        return workflows

    def _parse_single_workflow(self, block: str) -> Workflow | None:
        """解析单个工作流块"""
        try:
            desc = self._extract_tag(block, "description")
            steps = self._extract_tag(block, "steps")
            exec_graph = self._extract_tag(block, "execution_graph")
            actions_str = self._extract_tag(block, "actions")
            tools_str = self._extract_tag(block, "tools")

            # 安全解析 JSON
            actions = self._safe_json_loads(actions_str, [])
            tools = self._safe_json_loads(tools_str, [])

            return Workflow(
                description=desc,
                steps=steps,
                execution_graph=exec_graph,
                actions=actions,
                tools=tools,
            )
        except Exception:
            return None

    def _extract_tag(self, text: str, tag: str, default: str = "") -> str:
        """提取 XML 标签内容"""
        pattern = re.compile(rf"<{tag}>(.*?)</{tag}>", re.DOTALL)
        match = pattern.search(text)
        return match.group(1).strip() if match else default

    def _safe_json_loads(self, json_str: str, default: Any = None) -> Any:
        """安全解析 JSON（使用 dirtyjson 提高容错性）"""
        if default is None:
            default = []
        if not json_str:
            return default
        try:
            return dirtyjson.loads(json_str)
        except Exception:
            return default
