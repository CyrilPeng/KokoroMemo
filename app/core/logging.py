"""日志初始化。"""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """配置根日志输出格式。"""
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        stream=sys.stdout,
    )
    # 降低噪声较多的依赖日志级别。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
