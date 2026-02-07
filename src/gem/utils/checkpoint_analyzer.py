"""分析 checkpoint.json：成功/失败数量、各阶段失败分布等。

命令行用法（在项目根下）::

    uv run python -m gem.utils.checkpoint_analyzer syn_data/checkpoint.json
    uv run python -m gem.utils.checkpoint_analyzer syn_data/checkpoint.json --json
    uv run python -m gem.utils.checkpoint_analyzer --help
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


class CheckpointAnalyzer:
    """分析 GEM 实验的 checkpoint.json 结果。

    支持格式：success_ids、failed_info；兼容旧版仅有 failed_ids 的 checkpoint。
    """

    def __init__(
        self, path: str | Path | None = None, data: dict[str, Any] | None = None
    ) -> None:
        """从文件或已有字典加载。

        Args:
            path: checkpoint.json 路径；与 data 二选一。
            data: 已解析的 checkpoint 字典；与 path 二选一。
        """
        if path is not None and data is not None:
            raise ValueError("path 与 data 只能指定其一")
        if path is not None:
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(f"checkpoint 文件不存在: {path}")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        if data is None:
            data = {}
        self._data = data
        success_ids = data.get("success_ids", [])
        failed_info = dict(data.get("failed_info", {}))
        self._success_ids: set[str] = set(success_ids)
        self._failed_info: dict[str, str] = failed_info

    @property
    def success_ids(self) -> set[str]:
        """已成功处理的 data_id 集合。"""
        return self._success_ids

    @property
    def failed_info(self) -> dict[str, str]:
        """失败 data_id -> 失败阶段名。"""
        return self._failed_info

    @property
    def total_success(self) -> int:
        """成功条数。"""
        return len(self._success_ids)

    @property
    def total_failed(self) -> int:
        """失败条数。"""
        return len(self._failed_info)

    @property
    def total_processed(self) -> int:
        """已处理条数（成功 + 失败）。"""
        return self.total_success + self.total_failed

    from collections import Counter

    def failed_by_stage(self) -> dict[str, int]:
        """按阶段统计失败数：{ 阶段名: 失败数 }，按失败数降序。"""
        # 定义你要提取的目标 key（替换成你实际需要的 key 名称，比如 'stage'）
        target_key = "stage"

        # 1. 遍历所有失败信息的 value（每个 value 是 dict），提取目标 key 对应的 value
        # 2. 使用 get 方法避免 KeyError，若没有目标 key 则跳过（也可设默认值如 '未知阶段'）
        stage_values = [
            failed_dict.get(target_key)
            for failed_dict in self._failed_info.values()
            if failed_dict.get(target_key) is not None  # 过滤掉无目标 key 的情况
        ]

        # 统计各阶段的失败数
        counts = dict(Counter(stage_values))

        # 按失败数降序排列并转回字典
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def summary(self) -> dict[str, Any]:
        """汇总：成功数、失败数、各阶段失败数等，便于打印或写报告。"""
        by_stage = self.failed_by_stage()
        return {
            "total_success": self.total_success,
            "total_failed": self.total_failed,
            "total_processed": self.total_processed,
            "failed_by_stage": by_stage,
        }

    def __repr__(self) -> str:
        return (
            f"CheckpointAnalyzer(success={self.total_success}, failed={self.total_failed}, "
            f"by_stage={self.failed_by_stage()})"
        )


def _main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "用法: python -m gem.utils.checkpoint_analyzer <checkpoint.json> [--json]",
            file=sys.stderr,
        )
        print(
            "示例: python -m gem.utils.checkpoint_analyzer syn_data/checkpoint.json",
            file=sys.stderr,
        )
        sys.exit(0 if "--help" in argv or "-h" in argv else 1)
    path = argv[0]
    output_json = "--json" in argv
    try:
        analyzer = CheckpointAnalyzer(path=path)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    if output_json:
        print(json.dumps(analyzer.summary(), ensure_ascii=False, indent=2))
    else:
        s = analyzer.summary()
        print("Checkpoint 分析结果")
        print("=" * 40)
        print(f"  成功: {s['total_success']}")
        print(f"  失败: {s['total_failed']}")
        print(f"  已处理合计: {s['total_processed']}")
        print("  各阶段失败数:")
        for stage, count in s["failed_by_stage"].items():
            print(f"    {stage}: {count}")
        print("=" * 40)


if __name__ == "__main__":
    _main()
