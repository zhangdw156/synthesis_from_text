"""统一日志配置，供 GEM 与实验使用。

仅配置控制台日志（使用 Rich 美化输出）；文件日志由 Hydra job_logging 负责。

在实验中使用::

    from gem import setup_logging
    setup_logging(level="INFO")
    # 或从 Hydra 配置:
    setup_logging(**cfg.logging)
"""

import logging
from typing import Any

from rich.logging import RichHandler


def setup_logging(
    level: str = "INFO",
    format: str | None = None,
    **kwargs: Any,
) -> None:
    """配置进程的 root logging（仅控制台，Rich 美化）。

    只添加 RichHandler，不替换已有 handler，保留 Hydra 的 file handler。
    输出带颜色、级别高亮、异常时使用 Rich  traceback。

    Args:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR）。
        format: 保留参数以兼容 cfg.logging，Rich 使用自带布局。
        **kwargs: 忽略；便于直接传入 Hydra cfg.logging。
    """
    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)
    # 移除 Hydra 等已加的控制台 StreamHandler，避免同一条日志打两遍（一遍 Hydra 格式、一遍 Rich）
    # 只移除写 stdout/stderr 的 handler；保留 FileHandler（Hydra job_logging 的 file handler 继承自 StreamHandler，不能按 StreamHandler 一刀切移除）
    for h in root.handlers[:]:
        if isinstance(h, logging.FileHandler):
            continue
        if isinstance(h, logging.StreamHandler) and not isinstance(h, RichHandler):
            root.removeHandler(h)
    handler = RichHandler(
        level=log_level,
        show_time=True,
        show_level=True,
        show_path=False,
        rich_tracebacks=True,
    )
    root.addHandler(handler)

    # 屏蔽 httpx/httpcore 的 HTTP 请求 INFO 日志，避免控制台和日志文件刷屏
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
