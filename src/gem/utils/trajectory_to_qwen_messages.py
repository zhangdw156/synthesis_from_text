"""将 GEM 合成轨迹转为 Qwen3 微调用的 messages 格式。

不替换原始 system_prompt，仅在其后追加 tools 块；conversation 转为 user/assistant 轮次，
assistant 的 tool_calls 转为 <tool_call>...</tool_call>，tool 角色转为带 <tool_response> 的 user 消息。

命令行用法（在项目根下，任选其一）::

    uv run trajectory-to-qwen-messages syn_data/final_trajectories.jsonl syn_data/messages.jsonl
    uv run python -m gem.utils.trajectory_to_qwen_messages syn_data/final_trajectories.jsonl syn_data/messages.jsonl

不要用 ``uv run src/gem/utils/trajectory_to_qwen_messages.py ...``，参数可能未传入。
可选: ``--max-samples N``、``--no-truncate``。
"""

from __future__ import annotations

import json
import sys
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


def _main() -> None:
    """命令行入口：输入为数据合成后的 JSONL，输出为 OpenAI messages 格式的 JSONL。"""
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "用法: python -m gem.utils.trajectory_to_qwen_messages <合成轨迹.jsonl> <输出messages.jsonl> [--max-samples N] [--no-truncate]",
            file=sys.stderr,
        )
        print(
            "示例: python -m gem.utils.trajectory_to_qwen_messages syn_data/final_trajectories.jsonl out/messages.jsonl",
            file=sys.stderr,
        )
        sys.exit(0 if "--help" in argv or "-h" in argv else 1)
    if len(argv) < 2:
        print("请提供两个参数：输入 JSONL 与输出 JSONL 路径", file=sys.stderr)
        sys.exit(1)
    input_path = Path(argv[0])
    output_path = Path(argv[1])
    max_samples = -1
    truncate = True
    i = 2
    while i < len(argv):
        if argv[i] == "--max-samples" and i + 1 < len(argv):
            try:
                max_samples = int(argv[i + 1])
            except ValueError:
                print(f"无效 --max-samples: {argv[i+1]}", file=sys.stderr)
                sys.exit(1)
            i += 2
            continue
        if argv[i] == "--no-truncate":
            truncate = False
            i += 1
            continue
        i += 1
    if not input_path.exists():
        print(f"输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)
    converter = TrajectoryToQwenMessages(truncate_at_last_tool_call=truncate)
    try:
        count = converter.convert_jsonl(input_path, output_path, max_samples=max_samples)
    except OSError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"已写入 {count} 条到 {output_path}")


if __name__ == "__main__":
    _main()
