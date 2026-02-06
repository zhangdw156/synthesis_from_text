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

    Args:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR）。
        log_file: 若设置，同时写入该文件（UTF-8），目录不存在会创建。
        format: 日志格式串；None 使用 DEFAULT_FORMAT。
        **kwargs: 忽略；便于直接传入 Hydra cfg.logging。
    """
    fmt = format if format else DEFAULT_FORMAT
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, (level or "INFO").upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
        force=True,
    )
