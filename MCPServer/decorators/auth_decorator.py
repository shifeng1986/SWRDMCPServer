"""
用户认证模块

认证完全由连接级别的 Basic Auth 中间件（ConnectionAuthMiddleware）处理。
本模块仅提供 auth_required 装饰器作为兼容性占位，实际认证逻辑已移至中间件层。
"""

import functools
import json
from typing import Callable

from config import AUTH_ENABLED

from .logging_decorator import operation_logger as logger
from .operation_log_handler import format_timestamp


# ──────────────────────────────────────────────
# Tool 认证装饰器
# ──────────────────────────────────────────────

def auth_required(func: Callable) -> Callable:
    """
    Tool 认证装饰器（兼容性占位）

    认证已由连接级别的 ConnectionAuthMiddleware 中间件处理，
    此装饰器仅保留用于兼容性，实际不做任何 Token 验证。
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 认证未启用，直接放行
        if not AUTH_ENABLED:
            return await func(*args, **kwargs)

        # 连接级别已认证，直接放行
        logger.debug(
            json.dumps(
                {
                    "timestamp": format_timestamp(),
                    "event": "tool_auth_skipped",
                    "tool": func.__name__,
                    "reason": "连接级别 Basic Auth 已认证",
                },
                ensure_ascii=False,
            )
        )
        return await func(*args, **kwargs)

    return wrapper


# ──────────────────────────────────────────────
# 导出
# ──────────────────────────────────────────────

__all__ = [
    "auth_required",
]