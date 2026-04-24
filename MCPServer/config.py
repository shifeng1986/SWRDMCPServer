"""
配置模块

集中管理所有配置项，包括：
- 日志配置（级别、路径、大小、格式等）
- 安全配置（高危检查开关、风险等级映射、拦截策略等）
- 告警配置（告警开关、最低等级、通知渠道等）

优先从 YAML 配置文件加载，若文件不存在则使用默认值。
"""

import os
import logging

# 项目根目录
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_yaml_config(filename: str) -> dict:
    """从指定 YAML 文件加载配置，文件不存在则返回空字典"""
    yaml_path = os.path.join(_BASE_DIR, filename)
    if not os.path.isfile(yaml_path):
        return {}
    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        print(f"[警告] pyyaml 未安装，无法加载配置文件: {yaml_path}，将使用默认值")
        return {}


# ──────────────────────────────────────────────
# 日志配置
# ──────────────────────────────────────────────

_LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_yaml_log = _load_yaml_config("config.yaml")


def _resolve_log_file(value: str | None) -> str:
    """解析日志文件路径，相对路径基于项目根目录"""
    if value is None:
        return os.path.join(_BASE_DIR, "logs", "mcp_operation.log")
    if os.path.isabs(value):
        return value
    return os.path.join(_BASE_DIR, value)


# 日志记录级别
LOG_LEVEL = _LOG_LEVEL_MAP.get(
    _yaml_log.get("log_level", "DEBUG").upper(), logging.DEBUG
)

# 日志文件路径
LOG_FILE = _resolve_log_file(_yaml_log.get("log_file"))

# 单文件最大字节数（默认 10 MB）
MAX_BYTES = _yaml_log.get("max_bytes", 10 * 1024 * 1024)

# 保留的备份文件数量
BACKUP_COUNT = _yaml_log.get("backup_count", 30)

# 日志文件编码
LOG_ENCODING = _yaml_log.get("log_encoding", "utf-8")

# 控制台日志级别
CONSOLE_LEVEL = _LOG_LEVEL_MAP.get(
    _yaml_log.get("console_level", "DEBUG").upper(), logging.DEBUG
)

# 控制台日志格式
CONSOLE_FORMAT = _yaml_log.get(
    "console_format", "[%(asctime)s] %(levelname)s %(name)s - %(message)s"
)
CONSOLE_DATE_FORMAT = _yaml_log.get("console_date_format", "%Y-%m-%d %H:%M:%S")

# 文件日志级别
FILE_LEVEL = _LOG_LEVEL_MAP.get(
    _yaml_log.get("file_level", "DEBUG").upper(), logging.DEBUG
)

# 文件日志格式
FILE_FORMAT = _yaml_log.get(
    "file_format", "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
FILE_DATE_FORMAT = _yaml_log.get("file_date_format", "%Y-%m-%d:%H:%M:%S")


# ──────────────────────────────────────────────
# 安全配置
# ──────────────────────────────────────────────

_yaml_sec = _load_yaml_config("security_config.yaml")

# 安全等级字符串映射
RISK_LEVEL_MAP = {
    "low": "低危",
    "medium": "中危",
    "high": "高危",
    "critical": "严重",
}

# 处理策略映射
ACTION_MAP = {
    "block": "block",
    "confirm": "confirm",
    "log": "log",
    "allow": "allow",
}

# 告警最低等级的优先级（用于比较）
ALERT_LEVEL_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}

# 是否使能高危检查（全局开关）
SECURITY_ENABLED = _yaml_sec.get("enabled", True)

# 确认有效期（秒）
CONFIRM_EXPIRE_SECONDS = _yaml_sec.get("confirm_expire_seconds", 300)

# 操作风险等级映射：HTTP 方法 -> 风险等级
_default_risk_mapping = {
    "GET": "low",
    "POST": "high",
    "PATCH": "high",
    "PUT": "high",
    "DELETE": "critical",
    "default": "medium",
}
RISK_LEVEL_MAPPING = _yaml_sec.get("risk_level_mapping", _default_risk_mapping)

# 各风险等级的处理策略
_default_actions = {
    "critical": "block",
    "high": "confirm",
    "medium": "log",
    "low": "log",
}
SECURITY_ACTIONS = _yaml_sec.get("actions", _default_actions)

# 告警配置
_yaml_alert = _load_yaml_config("alert_config.yaml")
ALERT_ENABLED = _yaml_alert.get("enabled", True)
ALERT_MINIMUM_LEVEL = _yaml_alert.get("minimum_level", "high")
ALERT_CHANNELS = _yaml_alert.get("channels", {})


# ──────────────────────────────────────────────
# 用户认证配置
# ──────────────────────────────────────────────

_yaml_auth = _yaml_sec.get("auth", {})

# 是否启用用户认证
AUTH_ENABLED = _yaml_auth.get("enabled", False)

# 服务端固定 Token（为空则自动生成）
AUTH_TOKEN = _yaml_auth.get("token", "")

# 用户名/密码列表
AUTH_USERS = _yaml_auth.get("users", {})

# 用户登录 Token 有效期（秒）
AUTH_TOKEN_EXPIRE_SECONDS = _yaml_auth.get("token_expire_seconds", 3600)
