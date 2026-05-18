"""
输入参数校验装饰器模块

提供统一的输入参数校验功能，包含：
- 必填参数检查
- 参数类型检查
- 参数格式校验（IP 地址、URL 等）
- 参数值范围校验
- 字符串长度校验
- 内容关键字黑名单校验
"""

import functools
import json
import re
from typing import Any, Callable

from .logging_decorator import debug_logger
from config import (
    PARAM_VALIDATION_ENABLED,
    PARAM_MAX_LENGTH,
    PARAM_BLOCKED_KEYWORDS,
)


class ValidationError(Exception):
    """参数校验异常"""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"参数校验失败: {field} - {reason}")


# IP 地址正则
IPV4_PATTERN = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)

# HTTP 方法
VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# URL 路径正则
URL_PATH_PATTERN = re.compile(r"^/[^\s]*$")


def _validate_ip(value: str, field_name: str) -> None:
    """校验 IP 地址格式"""
    if not value or not value.strip():
        raise ValidationError(field_name, "IP 地址不能为空")
    if not IPV4_PATTERN.match(value.strip()):
        raise ValidationError(field_name, f"IP 地址格式无效: {value}")


def _validate_method(value: str, field_name: str) -> None:
    """校验 HTTP 方法"""
    if not value or not value.strip():
        raise ValidationError(field_name, "HTTP 方法不能为空")
    if value.strip().upper() not in VALID_METHODS:
        raise ValidationError(
            field_name, f"不支持的 HTTP 方法: {value}，支持的方法: {", ".join(sorted(VALID_METHODS))}"
        )


def _validate_url_path(value: str, field_name: str) -> None:
    """校验 URL 路径"""
    if not value or not value.strip():
        raise ValidationError(field_name, "URL 路径不能为空")
    if not URL_PATH_PATTERN.match(value.strip()):
        raise ValidationError(field_name, f"URL 路径格式无效: {value}")


def _validate_not_empty(value: str, field_name: str) -> None:
    """校验非空字符串"""
    if not value or not value.strip():
        raise ValidationError(field_name, "不能为空")


def _check_string_length(value: str, field_name: str, tool_name: str) -> None:
    """校验字符串长度"""
    max_len = PARAM_MAX_LENGTH.get(field_name, PARAM_MAX_LENGTH.get("default", 1024))
    if len(value) > max_len:
        reason = f"参数长度 {len(value)} 超过限制 {max_len}"
        debug_logger.warning(
            f"[参数长度校验失败] tool={tool_name}, field={field_name}, "
            f"length={len(value)}, max={max_len}"
        )
        raise ValidationError(field_name, reason)


def _check_blocked_keywords(value: str, field_name: str, tool_name: str) -> None:
    """校验是否包含敏感关键字"""
    for keyword in PARAM_BLOCKED_KEYWORDS:
        if keyword in value:
            reason = f"参数包含敏感关键字: {keyword}"
            debug_logger.warning(
                f"[参数关键字校验失败] tool={tool_name}, field={field_name}, "
                f"matched_keyword={keyword}"
            )
            raise ValidationError(field_name, reason)


def validate_input(func: Callable) -> Callable:
    """
    输入参数校验装饰器

    根据函数参数名称自动推断校验规则：
    - 包含 "IP" 的参数：校验 IPv4 格式
    - 名为 "method" 的参数：校验 HTTP 方法
    - 名为 "URL" 的参数：校验 URL 路径格式
    - 名为 "User" 或包含 "user" 的参数：校验非空
    - 名为 "body" 的参数：允许为空（GET 请求）

    对所有字符串参数额外执行：
    - 长度校验（超过配置的最大长度则拦截）
    - 关键字黑名单校验（包含敏感关键字则拦截）
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        tool_name = func.__name__
        param_names = func.__code__.co_varnames[: func.__code__.co_argcount]
        all_params = {}
        for i, name in enumerate(param_names):
            if name == "ctx":
                continue
            if i < len(args):
                all_params[name] = args[i]
            elif name in kwargs:
                all_params[name] = kwargs[name]

        # 根据参数名称自动推断校验规则
        for name, value in all_params.items():
            name_lower = name.lower()

            # IP 地址校验
            if "ip" in name_lower:
                _validate_ip(str(value), name)

            # HTTP 方法校验
            if name_lower == "method":
                _validate_method(str(value), name)

            # URL 路径校验
            if name_lower == "url":
                _validate_url_path(str(value), name)

            # 用户名校验
            if "user" in name_lower and name_lower != "ctx":
                _validate_not_empty(str(value), name)

            # 密码校验（仅非空，不校验格式）
            if "pwd" in name_lower or "password" in name_lower:
                _validate_not_empty(str(value), name)

        # 字符串长度校验 + 关键字黑名单校验（对所有字符串参数）
        if PARAM_VALIDATION_ENABLED:
            for name, value in all_params.items():
                if not isinstance(value, str):
                    continue
                _check_string_length(value, name, tool_name)
                _check_blocked_keywords(value, name, tool_name)

        return await func(*args, **kwargs)

    return wrapper


__all__ = ["validate_input", "ValidationError"]