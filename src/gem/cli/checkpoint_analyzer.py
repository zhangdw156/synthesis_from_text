"""分析 checkpoint 文件（SQLite .db）：成功/失败数量、各阶段失败分布、重试次数分布等。

命令行用法（在项目根下）::

    uv run python -m gem.cli.checkpoint_analyzer syn_data/checkpoint.db
    uv run python -m gem.cli.checkpoint_analyzer syn_data/checkpoint.db --json
    uv run python -m gem.cli.checkpoint_analyzer --help
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any


class CheckpointAnalyzer:
    """分析 GEM 实验的 checkpoint 结果（仅 SQLite .db）。

    表：success_ids (data_id)、failed_info (data_id, stage, retry_count)。
    """

    def __init__(
        self, path: str | Path | None = None, data: dict[str, Any] | None = None
    ) -> None:
        """从 .db 文件或已有字典加载。

        Args:
            path: checkpoint.db 路径；与 data 二选一。
            data: 已解析的 checkpoint 字典（success_ids、failed_info）；与 path 二选一。
        """
        if path is not None and data is not None:
            raise ValueError("path 与 data 只能指定其一")

        self._success_ids: set[str] = set()
        self._failed_info: dict[str, dict[str, Any]] = {}

        if path is not None:
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(f"checkpoint 文件不存在: {path}")
            if path.suffix.lower() != ".db":
                raise ValueError("仅支持 .db 文件 (SQLite)")
            self._load_from_db(path)
        elif data is not None:
            self._load_from_dict(data)

    def _load_from_db(self, path: Path) -> None:
        """从 SQLite 数据库加载 checkpoint 数据"""
        try:
            conn = sqlite3.connect(str(path))
            cursor = conn.cursor()

            # 加载成功 ID
            cursor.execute("SELECT data_id FROM success_ids")
            self._success_ids = {row[0] for row in cursor.fetchall()}

            # 加载失败信息（包含重试次数）
            cursor.execute("SELECT data_id, stage, retry_count FROM failed_info")
            self._failed_info = {
                row[0]: {"stage": row[1], "retry_count": row[2]}
                for row in cursor.fetchall()
            }

            conn.close()
        except sqlite3.Error as e:
            raise RuntimeError(f"读取数据库失败: {e}") from e

    def _load_from_dict(self, data: dict[str, Any]) -> None:
        """从字典加载：success_ids、failed_info（每项为 {stage, retry_count}）。"""
        self._success_ids = set(data.get("success_ids", []))
        for data_id, info in (data.get("failed_info") or {}).items():
            if isinstance(info, dict):
                self._failed_info[data_id] = {
                    "stage": info.get("stage", "unknown"),
                    "retry_count": info.get("retry_count", 0),
                }

    @property
    def success_ids(self) -> set[str]:
        """已成功处理的 data_id 集合。"""
        return self._success_ids

    @property
    def failed_info(self) -> dict[str, dict[str, Any]]:
        """失败 data_id -> {stage: 失败阶段, retry_count: 重试次数}。"""
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

    def failed_by_stage(self) -> dict[str, int]:
        """按阶段统计失败数：{ 阶段名: 失败数 }，按失败数降序。"""
        stage_values = [
            info["stage"]
            for info in self._failed_info.values()
            if info["stage"] is not None
        ]
        counts = Counter(stage_values)
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def failed_by_retry_count(self) -> dict[int, int]:
        """按重试次数统计失败数：{ 重试次数: 失败数 }，按重试次数升序。"""
        retry_values = [info["retry_count"] for info in self._failed_info.values()]
        counts = Counter(retry_values)
        return dict(sorted(counts.items()))

    def summary(self) -> dict[str, Any]:
        """汇总：成功数、失败数、各阶段失败数、重试次数分布等。"""
        return {
            "total_success": self.total_success,
            "total_failed": self.total_failed,
            "total_processed": self.total_processed,
            "failed_by_stage": self.failed_by_stage(),
            "failed_by_retry_count": self.failed_by_retry_count(),
            # 计算失败数据的平均重试次数
            "avg_retry_count_for_failed": (
                sum(info["retry_count"] for info in self._failed_info.values())
                / self.total_failed
                if self.total_failed > 0
                else 0
            ),
        }

    def __repr__(self) -> str:
        return (
            f"CheckpointAnalyzer(success={self.total_success}, failed={self.total_failed}, "
            f"by_stage={self.failed_by_stage()}, by_retry={self.failed_by_retry_count()})"
        )


def _main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "用法: python -m gem.cli.checkpoint_analyzer <checkpoint.db> [--json]",
            file=sys.stderr,
        )
        print(
            "参数: checkpoint.db (SQLite 断点文件)",
            file=sys.stderr,
        )
        print(
            "示例: python -m gem.cli.checkpoint_analyzer syn_data/checkpoint.db",
            file=sys.stderr,
        )
        sys.exit(0 if "--help" in argv or "-h" in argv else 1)

    path = argv[0]
    output_json = "--json" in argv

    try:
        analyzer = CheckpointAnalyzer(path=path)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    if output_json:
        print(json.dumps(analyzer.summary(), ensure_ascii=False, indent=2))
    else:
        s = analyzer.summary()
        print("Checkpoint 分析结果")
        print("=" * 60)
        print(f"  成功条数: {s['total_success']}")
        print(f"  失败条数: {s['total_failed']}")
        print(f"  已处理合计: {s['total_processed']}")
        if s["total_failed"] > 0:
            print(f"  失败数据平均重试次数: {s['avg_retry_count_for_failed']:.2f}")
        print("\n  各阶段失败数:")
        for stage, count in s["failed_by_stage"].items():
            percentage = (
                (count / s["total_failed"]) * 100 if s["total_failed"] > 0 else 0
            )
            print(f"    {stage:<20}: {count:>5} ({percentage:>5.3f}%)")
        print("\n  失败数据重试次数分布:")
        for retry_count, count in s["failed_by_retry_count"].items():
            percentage = (
                (count / s["total_failed"]) * 100 if s["total_failed"] > 0 else 0
            )
            print(f"    重试 {retry_count:>2} 次: {count:>5} ({percentage:>5.3f}%)")
        print("=" * 60)


if __name__ == "__main__":
    _main()
