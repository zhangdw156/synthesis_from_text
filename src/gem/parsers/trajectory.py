"""轨迹解析器"""

import json
import re

from gem.models.dialogue import Message, ToolCall
from gem.models.trajectory import ToolDefinition, Trajectory
from gem.parsers.dialogue import DialogueParser


class TrajectoryParser:
    """解析完整轨迹（包含工具集）"""

    def __init__(self):
        self.dialogue_parser = DialogueParser()

    def parse(self, response: str) -> Trajectory | None:
        """从 LLM 输出解析轨迹

        Args:
            response: LLM 原始输出

        Returns:
            成功: Trajectory 实例
            失败: None
        """
        try:
            # 提取工具集
            toolsets_match = re.search(r'<toolsets>(.*?)</toolsets>', response, re.DOTALL)
            toolsets_data = []
            if toolsets_match:
                try:
                    toolsets_data = json.loads(toolsets_match.group(1).strip())
                except json.JSONDecodeError:
                    pass

            # 提取 system prompt
            system_match = re.search(r'<system>(.*?)</system>', response, re.DOTALL)
            system_prompt = system_match.group(1).strip() if system_match else ""

            # 提取对话历史
            tags_pattern = re.compile(r'<(user|assistant|tool)>(.*?)</\1>', re.DOTALL)
            all_turns = tags_pattern.findall(response)

            conversation = []
            for role, content in all_turns:
                content = content.strip()
                tool_calls = None

                if role == 'assistant':
                    tool_calls = self._extract_tool_calls(content)
                    content = re.sub(r'<func>.*?</func>', '', content, flags=re.DOTALL).strip()

                conversation.append(Message(
                    role=role,
                    content=content,
                    tool_calls=tool_calls
                ))

            toolsets = []
            for t in toolsets_data:
                if not isinstance(t, dict):
                    continue
                try:
                    toolsets.append(ToolDefinition(**t))
                except (TypeError, ValueError):
                    continue
            return Trajectory(
                toolsets=toolsets,
                system_prompt=system_prompt,
                conversation=conversation
            )

        except Exception:
            return None

    def _extract_tool_calls(self, content: str) -> list[ToolCall] | None:
        """提取工具调用"""
        tool_calls = []
        func_pattern = re.compile(r'<func>(.*?)</func>', re.DOTALL)
        funcs = func_pattern.findall(content)

        for f_json in funcs:
            try:
                clean_json = re.sub(r'[\x00-\x1F\x7F]', '', f_json.strip())
                f_data = json.loads(clean_json)
                tool_calls.append(ToolCall(
                    name=f_data.get("name", ""),
                    arguments=f_data.get("arguments", {})
                ))
            except json.JSONDecodeError:
                continue

        return tool_calls if tool_calls else None
