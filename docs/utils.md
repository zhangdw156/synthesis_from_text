# GEM 工具包

`src/gem/utils` 提供日志配置、checkpoint 分析、轨迹转 Qwen 微调格式等工具。

## logging_config — 日志配置

**`setup_logging(level=..., log_file=..., format=..., **kwargs)`**

统一配置进程的 root logging，供 GEM 与实验使用。实验里通常从 Hydra 配置传入：`setup_logging(**cfg.logging)`。

```python
from gem import setup_logging
setup_logging(level="INFO", log_file="logs/app.log")
# 或
setup_logging(**cfg.logging)
```

## checkpoint_analyzer — Checkpoint 分析

**`CheckpointAnalyzer(path=...)` / `CheckpointAnalyzer(data=...)`**

解析 GEM 实验的 `checkpoint.json`（含 `success_ids`、`failed_stages`），统计成功/失败条数及各阶段失败分布。

- **属性**：`total_success`、`total_failed`、`total_processed`、`success_ids`、`failed_stages`
- **方法**：`failed_by_stage()`（按阶段失败数）、`summary()`（汇总字典）

**命令行**（在项目根下）：

```bash
uv run python -m gem.utils.checkpoint_analyzer syn_data/checkpoint.json
uv run python -m gem.utils.checkpoint_analyzer syn_data/checkpoint.json --json
uv run python -m gem.utils.checkpoint_analyzer --help
```

## trajectory_to_qwen_messages — 轨迹转 Qwen messages

**`TrajectoryToQwenMessages(truncate_at_last_tool_call=True)`**

将 GEM 合成轨迹（`toolsets` + `system_prompt` + `conversation`）转为 Qwen3 微调用的 messages 格式。不替换原始 system 提示词，仅在其后追加 tools 块；assistant 的 tool_calls 转为 `<tool_call>...</tool_call>`，tool 角色转为带 `<tool_response>` 的 user 消息。

- **`convert_trajectory(trajectory)`**：单条轨迹 dict → messages 列表
- **`convert_record(record)`**：单条 JSONL 记录（含 `data_id`、`trajectory`）→ `{data_id, messages}` 或 None
- **`convert_jsonl(input_path, output_path, max_samples=-1)`**：轨迹 JSONL → Qwen messages JSONL

```python
from gem import TrajectoryToQwenMessages

converter = TrajectoryToQwenMessages(truncate_at_last_tool_call=True)
messages = converter.convert_trajectory(trajectory_dict)
# 或整份 JSONL
converter.convert_jsonl("syn_data/final_trajectories.jsonl", "out/qwen_messages.jsonl")
```
