"""
操作日志装饰器模块

提供统一的操作日志记录功能，包含：
- 操作时间戳、工具名称、用户标识
- 输入参数（敏感信息脱敏）、操作结果摘要
- 执行耗时、状态、请求唯一标识

日志分类：
- 操作日志：记录每个 tool 调用的完整信息，用于审计，保留三个月
- 调试日志：记录调试信息，用于开发排查问题

操作日志输出到文件（按天生成，按周归档），调试日志输出到文件和控制台。
"""

import functools
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from .operation_log_handler import setup_operation_logger, setup_debug_logger


def _sanitize_parameters(params: dict) -> dict:
    """返回原始参数，不做脱敏处理（完整记录用于审计）"""
    return params


# 初始化日志记录器
operation_logger = setup_operation_logger()
debug_logger = setup_debug_logger()


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
    
    日志分类：
    - 操作日志：记录到 operation_logger，用于审计
    - 调试日志：记录到 debug_logger，用于开发调试
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        request_id = str(uuid.uuid4())
        tool_name = func.__name__
        timestamp = datetime.now(timezone.utc).isoformat()

        # 提取用户标识：优先从中间件认证获取，其次从 Context 中获取
        user = "unknown"
        auth_source = "none"  # 记录用户信息来源
        
        # 1. 尝试从中间件认证获取用户信息（basic_only模式）
        ctx = kwargs.get("ctx") or (args[-1] if args else None)
        if ctx:
            try:
                # 尝试从 request.state 中获取中间件认证的用户信息
                if hasattr(ctx, "request_context") and ctx.request_context:
                    request = getattr(ctx.request_context, "request", None)
                    if request and hasattr(request, "state"):
                        authenticated_user = getattr(request.state, "authenticated_user", None)
                        if authenticated_user:
                            user = authenticated_user
                            auth_source = "middleware"
            except Exception:
                pass  # 忽略异常，使用备用方案
        
        # 2. 如果没有中间件认证信息，从 userName 参数获取（兼容旧版）
        if user == "unknown":
            userName = kwargs.get("userName", "")
            if userName:
                user = userName
                auth_source = "parameter"
        
        # 3. 如果仍然没有，从 Context 的 client_id 获取
        if user == "unknown" and ctx:
            if hasattr(ctx, "client_id"):
                user = ctx.client_id or "unknown"
                auth_source = "context"
        
        # 安全检查：如果无法获取用户信息，拒绝执行并记录安全日志
        if user == "unknown" or not user:
            # 记录安全警告日志（操作日志）
            operation_logger.warning(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "request_id": request_id,
                        "tool_name": tool_name,
                        "user": "unknown",
                        "event": "security_violation",
                        "reason": "无法获取用户信息，拒绝执行tool",
                        "auth_source": auth_source,
                        "suggestion": "请检查中间件认证是否正常工作",
                    },
                    ensure_ascii=False,
                )
            )
            # 记录调试日志
            debug_logger.warning(
                f"[安全违规] 用户信息缺失 - tool={tool_name}, request_id={request_id}, auth_source={auth_source}"
            )
            return json.dumps(
                {
                    "error": "认证失败",
                    "message": "无法获取用户信息，请确保已通过中间件认证",
                    "security": "user_identification_required"
                },
                ensure_ascii=False,
            )

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

        # 记录请求开始（操作日志 - 用于审计）
        operation_logger.info(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "user": user,
                    "auth_source": auth_source,
                    "event": "request_start",
                    "parameters": sanitized_params,
                },
                ensure_ascii=False,
            )
        )
        
        # 记录调试日志
        debug_logger.debug(
            f"[请求开始] tool={tool_name}, user={user}, request_id={request_id}, params={sanitized_params}"
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
            # 错误日志：记录完整异常堆栈、参数值、用户和上下文（操作日志）
            operation_logger.error(
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
            # 记录调试日志
            debug_logger.error(
                f"[请求错误] tool={tool_name}, user={user}, request_id={request_id}, error={str(e)}",
                exc_info=True
            )
            raise
        finally:
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # 记录请求完成（操作日志 - 用于审计）
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
            operation_log_level = operation_logger.info
            if status == "success":
                operation_log_level = operation_logger.info
            elif status == "failed":
                operation_log_level = operation_logger.warning
            elif status == "blocked":
                operation_log_level = operation_logger.critical
            
            operation_log_level(json.dumps(log_entry, ensure_ascii=False))
            
            # 记录调试日志
            debug_log_level = debug_logger.debug
            if status == "success":
                debug_log_level = debug_logger.debug
            elif status == "failed":
                debug_log_level = debug_logger.warning
            elif status == "blocked":
                debug_log_level = debug_logger.error
            
            debug_log_level(
                f"[请求完成] tool={tool_name}, user={user}, request_id={request_id}, "
                f"status={status}, duration_ms={duration_ms}, result={result_summary}"
            )

    return wrapper


__all__ = ["with_operation_log", "operation_logger", "debug_logger"]
