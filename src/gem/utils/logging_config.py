"""统一日志配置，供 GEM 与实验使用。

在实验中使用::

    from gem import setup_logging
    setup_logging(level="INFO", log_file=None)
    # 或从 Hydra 配置:
    setup_logging(**cfg.logging)
"""

import logging
from pathlib import Path
from typing import Any

DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    format: str | None = None,
    **kwargs: Any,
) -> None:
    """配置进程的 root logging。

    当不传 log_file 时，仅添加控制台 handler，不替换已有 handler（保留 Hydra 等配置的 file handler）。
    当传 log_file 时，用 basicConfig(force=True) 重置为仅控制台 + 该文件。

    Args:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR）。
        log_file: 若设置，同时写入该文件（UTF-8），并重置 handlers。
        format: 日志格式串；None 使用 DEFAULT_FORMAT。
        **kwargs: 忽略；便于直接传入 Hydra cfg.logging。
    """
    fmt = format if format else DEFAULT_FORMAT
    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    root = logging.getLogger()

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers = [
            logging.StreamHandler(),
            logging.FileHandler(path, encoding="utf-8"),
        ]
        for h in handlers:
            h.setLevel(log_level)
            h.setFormatter(logging.Formatter(fmt))
        logging.basicConfig(level=log_level, format=fmt, handlers=handlers, force=True)
        return

    # 仅控制台：不 force，只添加 StreamHandler，保留 Hydra 的 file handler
    root.setLevel(log_level)
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(logging.Formatter(fmt))
    root.addHandler(console)
