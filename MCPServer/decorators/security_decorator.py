"""
高危操作拦截装饰器模块

提供统一的安全检查功能，包含：
- 操作风险等级评估（低危/中危/高危/严重）
- 根据配置的策略自动拦截、要求确认或仅记录日志
- 所有拦截事件发送实时告警通知

配置项由 config.py 统一管理，支持通过 security_config.yaml 自定义。
"""

import functools
import inspect
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

from .logging_decorator import operation_logger, debug_logger
from .operation_log_handler import format_timestamp
from config import (
    SECURITY_ENABLED,
    CONFIRM_EXPIRE_SECONDS,
    RISK_LEVEL_MAPPING,
    SECURITY_ACTIONS,
    RISK_LEVEL_MAP,
    MAX_MCP_BODY_SIZE,
    MCP_BODY_SIZE_CHECK_ENABLED,
)

from .alert_handler import send_alert


# 风险等级定义
class RiskLevel:
    LOW = "低危"
    MEDIUM = "中危"
    HIGH = "高危"
    CRITICAL = "严重"

    @classmethod
    def from_string(cls, level: str) -> str:
        """将配置字符串（如 "high"）转换为中文风险等级（如 "高危"）"""
        return RISK_LEVEL_MAP.get(level.lower(), cls.MEDIUM)


# 高危命令关键词（用于 sendCommand 安全检查）
HIGH_RISK_COMMANDS = [
    # 原有 cmd/Linux 命令
    "del", "rm", "shutdown", "reboot", "poweroff", "halt", "init",
    "format", "mkfs", "dd", "fdisk", "kill", "pkill", "taskkill",
    "mv /", "chmod 777 /", "rmdir", "rd /s", "rm -rf",
    "shutdown -s", "shutdown -r", "restart-computer", "stop-computer",
    # PowerShell 高危命令
    "remove-item", "ri ", "rm -recurse",
    "restart-computer -force", "stop-computer -force",
    "format-volume", "clear-disk", "remove-volume",
    # wmic 高危命令
    "wmic process call terminate", "wmic os where",
    "wmic delete", "wmic format",
]


# 确认状态缓存：{(user, operation_key): (confirmed_at, confirmed)}
_confirm_cache: dict[tuple[str, str], tuple[datetime, bool]] = {}

# 确认有效期（秒）- 从配置读取
CONFIRM_EXPIRE_SECONDS = CONFIRM_EXPIRE_SECONDS


class SecurityCheckError(Exception):
    """安全检查异常"""

    def __init__(self, risk_level: str, operation: str, reason: str):
        self.risk_level = risk_level
        self.operation = operation
        self.reason = reason
        super().__init__(
            f"[{risk_level}] 操作被拦截: {operation} - {reason}"
        )


class ConfirmationRequired(Exception):
    """需要确认的高危操作异常"""

    def __init__(self, risk_level: str, operation: str, reason: str, confirm_id: str):
        self.risk_level = risk_level
        self.operation = operation
        self.reason = reason
        self.confirm_id = confirm_id
        super().__init__(
            f"[{risk_level}] 操作需要确认: {operation} - {reason} (confirm_id: {confirm_id})"
        )


def _contains_high_risk_keyword(command: str, keyword: str) -> bool:
    """
    使用单词边界匹配检查命令是否包含高危关键词，避免子串误匹配。

    对于包含空格的多词关键词（如 "rm -rf"），使用子串匹配；
    对于单个词的关键词（如 "rm", "dd"），使用 \\b 单词边界正则匹配。
    """
    if " " in keyword:
        return keyword in command
    pattern = re.compile(r'\b' + re.escape(keyword) + r'\b')
    return bool(pattern.search(command))


def _assess_risk(func_name: str, params: dict) -> tuple[str, str]:
    """
    评估操作风险等级，根据配置的 risk_level_mapping 映射

    返回：(risk_level, reason)
    """
    func_name_lower = func_name.lower()

    # 特殊处理 sendCommand 工具
    if func_name_lower == "sendcommand":
        return _assess_command_risk(params)

    # 检查是否为 Redfish 请求，根据 HTTP 方法映射风险等级
    method = params.get("method", "").upper()
    level_key = RISK_LEVEL_MAPPING.get(method, RISK_LEVEL_MAPPING.get("default", "medium"))
    risk_level = RiskLevel.from_string(level_key)

    # 生成风险原因描述
    reason_map = {
        "低危": f"Redfish {method} 操作为只读查询",
        "中危": f"Redfish {method} 操作风险未知，默认为中危",
        "高危": f"Redfish {method} 操作可能修改设备配置",
        "严重": f"Redfish {method} 操作可能导致数据丢失",
    }
    reason = reason_map.get(risk_level, f"Redfish {method} 操作风险未知")

    return risk_level, reason


def _assess_command_risk(params: dict) -> tuple[str, str]:
    """
    评估 sendCommand 命令的风险等级

    根据 commandType 和命令内容动态评估风险：
    - ftp_download: 低危
    - serial: 低危
    - ssh: 低危（含高危命令时升级为严重）
    - tftp_server: 低危
    - shell: 高危~严重（取决于命令内容）
    """
    command_type = params.get("commandType", "").lower()
    params_str = params.get("params", "{}")

    # 尝试解析 params JSON
    try:
        params_dict = json.loads(params_str) if isinstance(params_str, str) else params_str
    except (json.JSONDecodeError, TypeError):
        params_dict = {}

    command = params_dict.get("command", "").lower()

    # 根据命令类型评估风险
    type_risk_map = {
        "ftp_download": ("低危", "FTP 文件下载操作"),
        "serial": ("低危", "串口连接操作可能影响设备通信"),
        "ssh": ("低危", "SSH 远程连接可执行任意命令"),
        "tftp_server": ("低危", "TFTP 文件传输服务操作"),
        "shell": ("高危", "Shell 命令执行操作"),
    }

    risk_level, reason = type_risk_map.get(command_type, ("中危", f"未知命令类型: {command_type}"))

    # 对 shell 类型，检查是否包含高危命令关键词
    if command_type == "shell" and command:
        for high_risk_cmd in HIGH_RISK_COMMANDS:
            if _contains_high_risk_keyword(command, high_risk_cmd):
                risk_level = RiskLevel.CRITICAL
                reason = f"Shell 命令包含高危操作关键词 '{high_risk_cmd}'"
                break

    # 对 ssh 类型，检查远程命令是否包含高危关键词
    if command_type == "ssh" and command:
        for high_risk_cmd in HIGH_RISK_COMMANDS:
            if _contains_high_risk_keyword(command, high_risk_cmd):
                risk_level = RiskLevel.CRITICAL
                reason = f"SSH 远程命令包含高危操作关键词 '{high_risk_cmd}'"
                break

    return risk_level, reason


def _check_confirm_cache(user: str, operation_key: str) -> bool:
    """检查确认缓存是否有效"""
    cache_key = (user, operation_key)
    if cache_key in _confirm_cache:
        confirmed_at, confirmed = _confirm_cache[cache_key]
        if confirmed:
            elapsed = (datetime.now(timezone.utc) - confirmed_at).total_seconds()
            if elapsed < CONFIRM_EXPIRE_SECONDS:
                return True
            else:
                del _confirm_cache[cache_key]
    return False


def confirm_operation(confirm_id: str, user: str, operation_key: str) -> None:
    """确认高危操作"""
    cache_key = (user, operation_key)
    _confirm_cache[cache_key] = (datetime.now(timezone.utc), True)
    operation_logger.info(
        json.dumps(
            {
                "timestamp": format_timestamp(),
                "event": "operation_confirmed",
                "confirm_id": confirm_id,
                "user": user,
                "operation_key": operation_key,
            },
            ensure_ascii=False,
        )
    )
    debug_logger.info(f"[操作确认] confirm_id={confirm_id}, user={user}, operation_key={operation_key}")


def _get_action(risk_level: str) -> str:
    """获取指定风险等级的处理策略"""
    # 将中文风险等级转换为配置键
    reverse_map = {v: k for k, v in RISK_LEVEL_MAP.items()}
    level_key = reverse_map.get(risk_level, "medium")
    return SECURITY_ACTIONS.get(level_key, "log")


def with_high_risk_check(func: Callable) -> Callable:
    """
    高危操作检查装饰器（最外层装饰器）

    在执行核心逻辑前：
    1. 检查安全检查是否使能
    2. 调用安全检查模块评估操作风险等级
    3. 根据配置的策略（block/confirm/log/allow）处理
    4. 满足条件的拦截事件发送实时告警通知
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 安全检查未使能，直接放行
        if not SECURITY_ENABLED:
            return await func(*args, **kwargs)

        request_id = str(uuid.uuid4())
        tool_name = func.__name__

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

        # 提取参数：使用 inspect.unwrap 穿透装饰器链获取原始函数签名
        original_func = inspect.unwrap(func)
        param_names = list(inspect.signature(original_func).parameters.keys())
        all_params = {}
        for i, name in enumerate(param_names):
            if name == "ctx":
                continue
            if i < len(args):
                all_params[name] = args[i]
            elif name in kwargs:
                all_params[name] = kwargs[name]

        # 检查请求体大小（仅当 tool 有 body 参数时）
        if MCP_BODY_SIZE_CHECK_ENABLED and "body" in all_params:
            body = all_params["body"]
            if isinstance(body, str) and len(body) > MAX_MCP_BODY_SIZE:
                body_size = len(body)
                operation_key = f"{tool_name}:body_size_exceeded"
                reason = f"请求体大小 {body_size} 字节超过限制 {MAX_MCP_BODY_SIZE} 字节"
                send_alert("高危", operation_key, reason, user, request_id)
                operation_logger.warning(
                    json.dumps(
                        {
                            "timestamp": format_timestamp(),
                            "event": "request_body_too_large",
                            "request_id": request_id,
                            "tool_name": tool_name,
                            "user": user,
                            "body_size_bytes": body_size,
                            "max_allowed_bytes": MAX_MCP_BODY_SIZE,
                            "action": "blocked",
                        },
                        ensure_ascii=False,
                    )
                )
                debug_logger.warning(
                    f"[请求体过大] tool={tool_name}, user={user}, size={body_size}B, "
                    f"max={MAX_MCP_BODY_SIZE}B"
                )
                raise SecurityCheckError("高危", operation_key, reason)

        # 评估风险等级
        risk_level, reason = _assess_risk(tool_name, all_params)

        # 构建操作唯一标识（用于确认缓存和日志）
        if tool_name.lower() == "sendcommand":
            # sendCommand 使用 commandType 和命令内容构建有意义的标识
            cmd_type = all_params.get("commandType", "unknown")
            params_str = all_params.get("params", "{}")
            try:
                params_dict = json.loads(params_str) if isinstance(params_str, str) else params_str
            except (json.JSONDecodeError, TypeError):
                params_dict = {}
            cmd_content = params_dict.get("command", "")
            operation_key = f"{tool_name}:{cmd_type}:{cmd_content}"
        else:
            method = all_params.get("method", "unknown")
            url = all_params.get("URL", "unknown")
            device_ip = all_params.get("deviceIP", "unknown")
            operation_key = f"{tool_name}:{method}:{device_ip}:{url}"

        # 根据配置的策略处理
        action = _get_action(risk_level)

        if action == "block":
            # 直接拦截
            send_alert(risk_level, operation_key, reason, user, request_id)
            raise SecurityCheckError(risk_level, operation_key, reason)

        if action == "confirm":
            # 需要确认
            if not _check_confirm_cache(user, operation_key):
                send_alert(risk_level, operation_key, reason, user, request_id)
                confirm_id = str(uuid.uuid4())
                raise ConfirmationRequired(
                    risk_level, operation_key, reason, confirm_id
                )

        if action == "log":
            # 仅记录日志，允许执行
            log_method = operation_logger.warning if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else operation_logger.info
            log_method(
                json.dumps(
                    {
                        "timestamp": format_timestamp(),
                        "event": f"{risk_level}_operation",
                        "request_id": request_id,
                        "risk_level": risk_level,
                        "operation": operation_key,
                        "reason": reason,
                        "user": user,
                        "action": "logged_and_proceed",
                    },
                    ensure_ascii=False,
                )
            )

        # action == "allow" 或其他：直接放行

        return await func(*args, **kwargs)

    return wrapper


# 导出
__all__ = [
    "with_high_risk_check",
    "SecurityCheckError",
    "ConfirmationRequired",
    "RiskLevel",
    "confirm_operation",
]
