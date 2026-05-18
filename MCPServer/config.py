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


def _resolve_log_file(value: str | None, default_name: str = "mcp_debug.log") -> str:
    """解析日志文件路径，相对路径基于项目根目录"""
    if value is None:
        return os.path.join(_BASE_DIR, "logs", default_name)
    if os.path.isabs(value):
        return value
    return os.path.join(_BASE_DIR, value)


# ──────────────────────────────────────────────
# 调试日志配置（用于开发调试）
# ──────────────────────────────────────────────

# 调试日志记录级别
DEBUG_LOG_LEVEL = _LOG_LEVEL_MAP.get(
    _yaml_log.get("debug_log_level", "DEBUG").upper(), logging.DEBUG
)

# 调试日志文件路径
DEBUG_LOG_FILE = _resolve_log_file(_yaml_log.get("debug_log_file"), "mcp_debug.log")

# 调试日志单文件最大字节数（默认 10 MB）
DEBUG_MAX_BYTES = _yaml_log.get("debug_max_bytes", 10 * 1024 * 1024)

# 调试日志保留的备份文件数量
DEBUG_BACKUP_COUNT = _yaml_log.get("debug_backup_count", 5)

# 调试日志文件编码
DEBUG_LOG_ENCODING = _yaml_log.get("debug_log_encoding", "utf-8")

# 调试日志控制台级别
DEBUG_CONSOLE_LEVEL = _LOG_LEVEL_MAP.get(
    _yaml_log.get("debug_console_level", "DEBUG").upper(), logging.DEBUG
)

# 调试日志控制台格式（包含文件名和行号）
DEBUG_CONSOLE_FORMAT = _yaml_log.get(
    "debug_console_format", "[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d] %(name)s - %(message)s"
)
DEBUG_CONSOLE_DATE_FORMAT = _yaml_log.get("debug_console_date_format", "%Y-%m-%d %H:%M:%S")

# 调试日志文件级别
DEBUG_FILE_LEVEL = _LOG_LEVEL_MAP.get(
    _yaml_log.get("debug_file_level", "DEBUG").upper(), logging.DEBUG
)

# 调试日志文件格式（包含文件名和行号）
DEBUG_FILE_FORMAT = _yaml_log.get(
    "debug_file_format", "%(asctime)s | %(levelname)s | [%(filename)s:%(lineno)d] | %(name)s | %(message)s"
)
DEBUG_FILE_DATE_FORMAT = _yaml_log.get("debug_file_date_format", "%Y-%m-%d:%H:%M:%S")


# ──────────────────────────────────────────────
# 操作日志配置（用于审计，保留三个月）
# ──────────────────────────────────────────────

# 操作日志记录级别（建议使用 INFO）
OPERATION_LOG_LEVEL = _LOG_LEVEL_MAP.get(
    _yaml_log.get("operation_log_level", "INFO").upper(), logging.INFO
)

# 操作日志基础目录（按周分文件夹）
OPERATION_LOG_DIR = os.path.join(_BASE_DIR, "logs", "operation")

# 操作日志文件编码
OPERATION_LOG_ENCODING = _yaml_log.get("operation_log_encoding", "utf-8")

# 操作日志保留天数（默认 90 天，约三个月）
OPERATION_LOG_RETENTION_DAYS = _yaml_log.get("operation_log_retention_days", 90)

# 操作日志文件格式（JSON 格式，便于审计）
OPERATION_FILE_FORMAT = _yaml_log.get(
    "operation_file_format", "%(message)s"
)
OPERATION_FILE_DATE_FORMAT = _yaml_log.get("operation_file_date_format", "%Y-%m-%d:%H:%M:%S")


# ──────────────────────────────────────────────
# 兼容旧版本配置（已废弃，建议使用上面的新配置）
# ──────────────────────────────────────────────

# 日志记录级别（已废弃，使用 DEBUG_LOG_LEVEL 和 OPERATION_LOG_LEVEL）
LOG_LEVEL = DEBUG_LOG_LEVEL

# 日志文件路径（已废弃，使用 DEBUG_LOG_FILE）
LOG_FILE = DEBUG_LOG_FILE

# 单文件最大字节数（已废弃，使用 DEBUG_MAX_BYTES）
MAX_BYTES = DEBUG_MAX_BYTES

# 保留的备份文件数量（已废弃，使用 DEBUG_BACKUP_COUNT）
BACKUP_COUNT = DEBUG_BACKUP_COUNT

# 日志文件编码（已废弃，使用 DEBUG_LOG_ENCODING）
LOG_ENCODING = DEBUG_LOG_ENCODING

# 控制台日志级别（已废弃，使用 DEBUG_CONSOLE_LEVEL）
CONSOLE_LEVEL = DEBUG_CONSOLE_LEVEL

# 控制台日志格式（已废弃，使用 DEBUG_CONSOLE_FORMAT）
CONSOLE_FORMAT = DEBUG_CONSOLE_FORMAT
CONSOLE_DATE_FORMAT = DEBUG_CONSOLE_DATE_FORMAT

# 文件日志级别（已废弃，使用 DEBUG_FILE_LEVEL）
FILE_LEVEL = DEBUG_FILE_LEVEL

# 文件日志格式（已废弃，使用 DEBUG_FILE_FORMAT）
FILE_FORMAT = DEBUG_FILE_FORMAT
FILE_DATE_FORMAT = DEBUG_FILE_DATE_FORMAT


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
# MCP 请求体大小限制配置
# ──────────────────────────────────────────────

# MCP 请求体最大字节数（默认 1KB = 1024 字节）
MAX_MCP_BODY_SIZE = _yaml_sec.get("max_mcp_body_size", 1024)

# 是否启用 MCP 请求体大小检查
MCP_BODY_SIZE_CHECK_ENABLED = _yaml_sec.get("mcp_body_size_check_enabled", True)


# ──────────────────────────────────────────────
# 参数校验配置
# ──────────────────────────────────────────────

_yaml_param = _yaml_sec.get("parameter_validation", {})

# 是否启用参数校验
PARAM_VALIDATION_ENABLED = _yaml_param.get("enabled", True)

# 字符串参数最大长度配置
PARAM_MAX_LENGTH = _yaml_param.get("max_length", {"default": 1024})

# 敏感关键字黑名单
PARAM_BLOCKED_KEYWORDS = _yaml_param.get("blocked_keywords", [])


# ──────────────────────────────────────────────
# 用户认证配置
# ──────────────────────────────────────────────

_yaml_auth = _yaml_sec.get("auth", {})

# 是否启用用户认证
AUTH_ENABLED = _yaml_auth.get("enabled", False)

# 用户名/密码列表（本地认证备用）
AUTH_USERS = _yaml_auth.get("users", {})

# 认证缓存有效期（秒）
AUTH_CACHE_TTL = _yaml_auth.get("cache_ttl", 3600)

# 认证缓存最大条目数
AUTH_CACHE_MAX_SIZE = _yaml_auth.get("cache_max_size", 1000)


# ──────────────────────────────────────────────
# LDAP认证配置
# ──────────────────────────────────────────────

_yaml_ldap = _yaml_auth.get("ldap", {})

# 是否启用LDAP认证
LDAP_ENABLED = _yaml_ldap.get("enabled", False)

# LDAP服务器URI
LDAP_SERVER_URI = _yaml_ldap.get("server_uri", "ldap://127.0.0.1:389")

# LDAP绑定DN（用于搜索用户）
LDAP_BIND_DN = _yaml_ldap.get("bind_dn", "")

# LDAP绑定密码
LDAP_BIND_PASSWORD = _yaml_ldap.get("bind_password", "")

# LDAP用户搜索基础DN
LDAP_USER_SEARCH_BASE = _yaml_ldap.get("user_search_base", "")

# LDAP用户搜索过滤器
LDAP_USER_SEARCH_FILTER = _yaml_ldap.get("user_search_filter", "(sAMAccountName=%(user)s)")


# ──────────────────────────────────────────────
# LDAP部门访问控制配置
# ──────────────────────────────────────────────

_yaml_ldap_dept = _yaml_ldap.get("department_access_control", {})

# 是否启用LDAP部门访问控制
LDAP_DEPT_ACCESS_CONTROL_ENABLED = _yaml_ldap_dept.get("enabled", False)

# 允许访问的部门列表
LDAP_ALLOWED_DEPARTMENTS = _yaml_ldap_dept.get("allowed_departments", [])

# 是否使用精确匹配
LDAP_DEPT_EXACT_MATCH = _yaml_ldap_dept.get("exact_match", False)

