"""将 GEM 合成轨迹转为 Qwen3 微调用的 messages 格式。

不替换原始 system_prompt，仅在其后追加 tools 块；conversation 转为 user/assistant 轮次，
assistant 的 tool_calls 转为 <tool_call>...</tool_call>，tool 角色转为带 <tool_response> 的 user 消息。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Qwen 工具块前后缀（与参考实现一致）
TOOLS_HEADER = "\n\n# Tools\nYou may call one or more functions... <tools>"
TOOLS_FOOTER = "\n</tools>\n\nFor each function call, return a json object within <tool_call></tool_call> tags."


def _build_tools_content(toolsets: list[dict[str, Any]]) -> str:
    """从 toolsets 列表拼出 Qwen 格式的 tools 文本。"""
    if not toolsets:
        return ""
    try:
        parts = [TOOLS_HEADER]
        for t in toolsets:
            if isinstance(t, dict):
                parts.append("\n" + json.dumps(t, ensure_ascii=False))
        parts.append(TOOLS_FOOTER)
        return "".join(parts)
    except (TypeError, ValueError):
        return ""


def _assistant_content_to_qwen(msg: dict[str, Any]) -> str:
    """将一条 assistant 消息转为 Qwen 的 content：含 <tool_call> 或纯文本。"""
    content = (msg.get("content") or "").strip()
    # 去掉 </think>...</think> 段（若有）
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[-1].strip()
    tool_calls = msg.get("tool_calls")
    if tool_calls and isinstance(tool_calls, list):
        parts = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name", "")
                args = tc.get("arguments", {})
                if isinstance(args, dict):
                    args_str = json.dumps(args, ensure_ascii=False)
                else:
                    args_str = json.dumps({}) if not isinstance(args, str) else args
                parts.append(
                    f'<tool_call>\n{{"name": "{name}", "arguments": {args_str}}}\n</tool_call>'
                )
            else:
                continue
        if parts:
            return "\n".join(parts)
    return content


def _tool_content_to_qwen(msg: dict[str, Any]) -> str:
    """将 tool 角色的 content 包装为 <tool_response>。"""
    content = msg.get("content") or ""
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    elif not isinstance(content, str):
        content = str(content)
    return f"<tool_response>\n{content.strip()}\n</tool_response>"


class TrajectoryToQwenMessages:
    """将 GEM 轨迹（toolsets + system_prompt + conversation）转为 Qwen3 微调用 messages 列表。

    不替换原始 system_prompt，仅在其后追加 tools 块。
    """

    def __init__(self, truncate_at_last_tool_call: bool = True) -> None:
        """Args:
        truncate_at_last_tool_call: 若为 True，只保留到最后一条含 <tool_call> 的 assistant 消息。
        """
        self.truncate_at_last_tool_call = truncate_at_last_tool_call

    def convert_trajectory(self, trajectory: dict[str, Any]) -> list[dict[str, str]]:
        """将单条轨迹转为 messages 列表（每项为 {role, content}）。

        Args:
            trajectory: 含 toolsets、system_prompt、conversation 的字典。

        Returns:
            messages 列表；无效或空则返回 []。
        """
        toolsets = trajectory.get("toolsets") or []
        system_prompt = (trajectory.get("system_prompt") or "").strip()
        conversation = trajectory.get("conversation") or []
        if not isinstance(conversation, list):
            return []

        tools_text = _build_tools_content(toolsets)
        system_content = system_prompt + tools_text
        messages = [{"role": "system", "content": system_content}]

        for turn in conversation:
            if not isinstance(turn, dict):
                continue
            role = (turn.get("role") or "").strip().lower()
            if role == "user":
                content = (turn.get("content") or "").strip()
                messages.append({"role": "user", "content": content})
            elif role == "assistant":
                content = _assistant_content_to_qwen(turn)
                if content:
                    messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                content = _tool_content_to_qwen(turn)
                messages.append({"role": "user", "content": content})

        if self.truncate_at_last_tool_call:
            messages = self._truncate_at_last_tool_call(messages)
        return messages

    def _truncate_at_last_tool_call(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """保留到最后一条含 <tool_call> 的 assistant 消息（含该条）。"""
        if not messages:
            return []
        last_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant" and "<tool_call>" in (
                messages[i].get("content") or ""
            ):
                last_idx = i
                break
        if last_idx >= 0:
            return messages[: last_idx + 1]
        return messages

    def convert_record(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """将一条 JSONL 记录（含 data_id、trajectory）转为 {data_id, messages}。

        若 trajectory 无效或 messages 为空，返回 None。
        """
        trajectory = record.get("trajectory") if isinstance(record, dict) else None
        if not trajectory:
            return None
        messages = self.convert_trajectory(trajectory)
        if not messages:
            return None
        data_id = record.get("data_id", "")
        return {"data_id": data_id, "messages": messages}

    def convert_jsonl(
        self,
        input_path: str | Path,
        output_path: str | Path,
        max_samples: int = -1,
        *,
        encoding: str = "utf-8",
    ) -> int:
        """从轨迹 JSONL 读入，写出 Qwen messages JSONL。

        Args:
            input_path: 输入 JSONL，每行 {"data_id", "trajectory"}。
            output_path: 输出 JSONL，每行 {"data_id", "messages"}。
            max_samples: 最多转换条数，<=0 表示全部。
            encoding: 文件编码。

        Returns:
            成功写出的条数。
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with (
            open(input_path, encoding=encoding) as fin,
            open(output_path, "w", encoding=encoding) as fout,
        ):
            for i, line in enumerate(fin):
                if max_samples > 0 and count >= max_samples:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                out = self.convert_record(record)
                if out is None:
                    continue
                fout.write(json.dumps(out, ensure_ascii=False) + "\n")
                count += 1
        return count
