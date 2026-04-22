"""
操作日志装饰器模块

提供统一的操作日志记录功能，包含：
- 操作时间戳、工具名称、用户标识
- 输入参数（敏感信息脱敏）、操作结果摘要
- 执行耗时、状态、请求唯一标识

日志输出到文件和控制台两个通道，配置项由 config.py 统一管理。
"""

import functools
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable
from logging.handlers import RotatingFileHandler

from config import (
    LOG_LEVEL,
    LOG_FILE,
    MAX_BYTES,
    BACKUP_COUNT,
    LOG_ENCODING,
    CONSOLE_FORMAT,
    CONSOLE_DATE_FORMAT,
    FILE_FORMAT,
    FILE_DATE_FORMAT,
    CONSOLE_LEVEL,
    FILE_LEVEL,
)


# 敏感参数关键词列表
SENSITIVE_KEYWORDS = [
    "password", "pwd", "secret", "token", "apikey", "api_key",
    "auth", "credential", "private_key", "access_key",
]

# 脱敏后的占位符
SENSITIVE_MASK = "******"


def _sanitize_parameters(params: dict) -> dict:
    """对敏感参数进行脱敏处理"""
    sanitized = {}
    for key, value in params.items():
        key_lower = key.lower()
        if any(keyword in key_lower for keyword in SENSITIVE_KEYWORDS):
            sanitized[key] = SENSITIVE_MASK
        else:
            sanitized[key] = value
    return sanitized


def _setup_logger() -> logging.Logger:
    """设置日志记录器，同时输出到控制台和文件，配置项由 config.py 统一管理"""
    logger = logging.getLogger("mcp_operation")
    if logger.handlers:
        return logger

    logger.setLevel(LOG_LEVEL)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(CONSOLE_LEVEL)
    console_fmt = logging.Formatter(CONSOLE_FORMAT, datefmt=CONSOLE_DATE_FORMAT)
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # 文件处理器 - 按大小轮转
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding=LOG_ENCODING,
    )
    file_handler.setLevel(FILE_LEVEL)
    file_fmt = logging.Formatter(FILE_FORMAT, datefmt=FILE_DATE_FORMAT)
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger


logger = _setup_logger()


def with_operation_log(func: Callable) -> Callable:
    """
    操作日志装饰器

    自动记录以下信息：
    - timestamp：操作时间戳（ISO 格式）
    - tool_name：工具名称
    - user：操作用户标识
    - parameters：输入参数（敏感信息脱敏）
    - result：操作结果摘要
    - duration_ms：执行耗时（毫秒）
    - status：执行状态（success/failed/blocked）
    - request_id：请求唯一标识（用于链路追踪）
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        request_id = str(uuid.uuid4())
        tool_name = func.__name__
        timestamp = datetime.now(timezone.utc).isoformat()

        # 提取用户标识：优先从 userName 参数获取，其次从 Context 中获取
        user = "unknown"
        # 优先从 userName 参数获取
        userName = kwargs.get("userName", "")
        if userName:
            user = userName
        else:
            ctx = kwargs.get("ctx") or (args[-1] if args else None)
            if ctx and hasattr(ctx, "client_id"):
                user = ctx.client_id or "unknown"

        # 提取并脱敏参数
        param_names = func.__code__.co_varnames[: func.__code__.co_argcount]
        all_params = {}
        for i, name in enumerate(param_names):
            if name == "ctx":
                continue
            if i < len(args):
                all_params[name] = args[i]
            elif name in kwargs:
                all_params[name] = kwargs[name]
        sanitized_params = _sanitize_parameters(all_params)

        # 记录请求开始
        logger.info(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "user": user,
                    "event": "request_start",
                    "parameters": sanitized_params,
                },
                ensure_ascii=False,
            )
        )

        start_time = datetime.now(timezone.utc)
        status = "success"
        result_summary = ""

        try:
            result = await func(*args, **kwargs)
            # 结果摘要：截取前 200 字符
            result_str = str(result)
            result_summary = result_str[:200] + ("..." if len(result_str) > 200 else "")
            return result
        except Exception as e:
            status = "failed"
            result_summary = str(e)
            # 错误日志：记录完整异常堆栈、参数值、用户和上下文
            logger.error(
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "request_id": request_id,
                        "tool_name": tool_name,
                        "user": user,
                        "event": "request_error",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "parameters": sanitized_params,
                        "suggestion": "请检查参数是否正确，或联系管理员",
                    },
                    ensure_ascii=False,
                ),
                exc_info=True,
            )
            raise
        finally:
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # 记录请求完成
            log_entry = {
                "timestamp": end_time.isoformat(),
                "request_id": request_id,
                "tool_name": tool_name,
                "user": user,
                "event": "request_end",
                "duration_ms": duration_ms,
                "status": status,
                "result": result_summary,
            }
            if status == "success":
                logger.info(json.dumps(log_entry, ensure_ascii=False))
            elif status == "failed":
                logger.warning(json.dumps(log_entry, ensure_ascii=False))
            elif status == "blocked":
                logger.critical(json.dumps(log_entry, ensure_ascii=False))

    return wrapper


__all__ = ["with_operation_log", "logger"]
