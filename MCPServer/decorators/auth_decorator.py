"""
用户认证模块

提供基于用户名/密码 + 临时 Token 的双重认证功能：
- 中间件层：支持 Basic Auth（用户名/密码）和 Bearer Token 两种认证方式
- Tool 层：通过 auth_required 装饰器验证临时 Token 的有效性

认证流程：
1. MCP Client 在连接配置中设置用户名/密码（Basic Auth）或服务端 Token
2. 中间件验证通过后放行请求
3. AI Agent 调用 authenticate 工具，传入 username/password，获取临时 Token
4. 后续 tool 调用携带 token 参数，Server 通过 auth_required 装饰器验证有效性
5. Token 过期后需重新认证

配置项由 config.py 统一管理，支持通过 security_config.yaml 自定义。
"""

import functools
import json
import logging
import secrets
import time
import base64
from typing import Any, Callable, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import (
    AUTH_ENABLED,
    AUTH_USERS,
    AUTH_TOKEN,
    AUTH_TOKEN_EXPIRE_SECONDS,
)

from .logging_decorator import logger


# ──────────────────────────────────────────────
# Token 管理
# ──────────────────────────────────────────────

# 有效 Token 缓存：{token: {"user": str, "expires_at": float}}
_token_cache: dict[str, dict[str, Any]] = {}


def _generate_token() -> str:
    """生成随机 Token"""
    return secrets.token_urlsafe(32)


def _get_server_token() -> str:
    """获取服务端 Token，优先使用配置文件中的固定 Token，否则生成随机 Token"""
    if AUTH_TOKEN:
        return AUTH_TOKEN
    return _generate_token()


# 服务端持有的 Token（用于中间件验证）
_server_token: Optional[str] = None


def get_server_token() -> str:
    """获取服务端 Token（单例）"""
    global _server_token
    if _server_token is None:
        _server_token = _get_server_token()
    return _server_token


def _is_valid_token(token: str) -> bool:
    """验证 Token 是否有效（用于中间件层验证）"""
    if not token:
        return False

    # 检查是否为服务端 Token（备用机制）
    if token == get_server_token():
        return True

    # 检查是否为用户登录生成的 Token
    if token in _token_cache:
        token_info = _token_cache[token]
        if token_info["expires_at"] > time.time():
            return True
        else:
            # Token 已过期，清理缓存
            del _token_cache[token]

    return False


def _validate_tool_token(token: str) -> tuple[bool, str, Optional[str]]:
    """
    验证 tool 调用中的 Token 有效性

    返回：(is_valid, message, username)
    - is_valid: Token 是否有效
    - message: 验证结果描述
    - username: 关联的用户名（仅当 Token 有效时返回）
    """
    if not AUTH_ENABLED:
        return True, "认证未启用", None

    if not token:
        return False, "Token 不能为空，请先调用 authenticate 工具获取 Token", None

    # 检查是否为用户登录生成的 Token
    if token in _token_cache:
        token_info = _token_cache[token]
        if token_info["expires_at"] > time.time():
            return True, "Token 有效", token_info["user"]
        else:
            # Token 已过期，清理缓存
            del _token_cache[token]
            return False, "Token 已过期，请重新调用 authenticate 工具获取 Token", None

    # 检查是否为服务端 Token（备用机制，允许配置的固定 Token 直接访问）
    if token == get_server_token():
        return True, "Token 有效（服务端 Token）", "server"

    return False, "Token 无效，请先调用 authenticate 工具获取有效 Token", None


def _authenticate_user(username: str, password: str) -> Optional[str]:
    """验证用户名/密码，成功则返回新生成的 Token"""
    # 优先尝试LDAP认证
    from config import LDAP_ENABLED
    if LDAP_ENABLED:
        try:
            from ldap_auth import authenticate_with_ldap
            is_valid, message = authenticate_with_ldap(username, password)
            if is_valid:
                token = _generate_token()
                _token_cache[token] = {
                    "user": username,
                    "expires_at": time.time() + AUTH_TOKEN_EXPIRE_SECONDS,
                }
                logger.info(
                    json.dumps(
                        {
                            "timestamp": time.time(),
                            "event": "user_authenticated",
                            "user": username,
                            "auth_type": "ldap",
                            "action": "login_success",
                        },
                        ensure_ascii=False,
                    )
                )
                return token
            else:
                logger.warning(
                    json.dumps(
                        {
                            "timestamp": time.time(),
                            "event": "ldap_authentication_failed",
                            "user": username,
                            "reason": message,
                            "action": "login_failed",
                        },
                        ensure_ascii=False,
                    )
                )
                # LDAP认证失败，继续尝试本地认证
        except Exception as e:
            logger.error(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "event": "ldap_authentication_error",
                        "user": username,
                        "error": str(e),
                        "action": "login_error",
                    },
                    ensure_ascii=False,
                )
            )
            # LDAP认证出错，继续尝试本地认证

    # 本地认证（备用）
    if username in AUTH_USERS and AUTH_USERS[username] == password:
        token = _generate_token()
        _token_cache[token] = {
            "user": username,
            "expires_at": time.time() + AUTH_TOKEN_EXPIRE_SECONDS,
        }
        logger.info(
            json.dumps(
                {
                    "timestamp": time.time(),
                    "event": "user_authenticated",
                    "user": username,
                    "auth_type": "local",
                    "action": "login_success",
                },
                ensure_ascii=False,
            )
        )
        return token

    logger.warning(
        json.dumps(
            {
                "timestamp": time.time(),
                "event": "authentication_failed",
                "user": username,
                "action": "login_failed",
            },
            ensure_ascii=False,
        )
    )
    return None


def _revoke_token(token: str) -> bool:
    """撤销 Token"""
    if token in _token_cache:
        del _token_cache[token]
        return True
    return False


# ──────────────────────────────────────────────
# Tool 认证装饰器
# ──────────────────────────────────────────────

def auth_required(func: Callable) -> Callable:
    """
    Tool 认证装饰器

    在 tool 函数执行前验证 token 参数的有效性。
    仅当 AUTH_ENABLED 为 True 时生效。

    使用方式：在 tool 函数参数中添加 token: str 参数，
    装饰器会自动提取并验证该 Token。
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 认证未启用，直接放行
        if not AUTH_ENABLED:
            return await func(*args, **kwargs)

        # 提取 token 参数
        token = kwargs.get("token", "")
        if not token:
            # 尝试从位置参数提取
            param_names = func.__code__.co_varnames[: func.__code__.co_argcount]
            for i, name in enumerate(param_names):
                if name == "token" and i < len(args):
                    token = args[i]
                    break

        # 验证 Token
        is_valid, message, username = _validate_tool_token(token)
        if not is_valid:
            logger.warning(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "event": "tool_auth_failed",
                        "tool": func.__name__,
                        "reason": message,
                    },
                    ensure_ascii=False,
                )
            )
            return json.dumps(
                {"error": "认证失败", "message": message},
                ensure_ascii=False,
            )

        # Token 有效，将关联的用户名注入 kwargs（供后续装饰器使用）
        if username and username != "server":
            # 如果 userName 参数为空，自动填充认证用户名
            if not kwargs.get("userName"):
                kwargs["userName"] = username

        logger.info(
            json.dumps(
                {
                    "timestamp": time.time(),
                    "event": "tool_auth_success",
                    "tool": func.__name__,
                    "user": username or "unknown",
                },
                ensure_ascii=False,
            )
        )

        return await func(*args, **kwargs)

    return wrapper


# ──────────────────────────────────────────────
# 认证中间件
# ──────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    """
    认证中间件

    拦截所有 /mcp 请求，验证 Authorization 头，支持以下认证方式：
    - Basic Auth：Authorization: Basic <base64(username:password)>
    - Bearer Token：Authorization: Bearer <token>
    - 查询参数：?token=<token>（备用方式）

    仅当 AUTH_ENABLED 为 True 时生效。
    """

    async def dispatch(self, request: Request, call_next):
        # 认证未启用，直接放行
        if not AUTH_ENABLED:
            return await call_next(request)

        # 仅对 /mcp 路径进行认证，/auth 路径放行
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        # 从 Authorization 头提取认证信息
        auth_header = request.headers.get("Authorization", "")
        auth_valid = False
        auth_user = None

        if auth_header.startswith("Basic "):
            # Basic Auth：用户名/密码认证
            try:
                decoded = base64.b64decode(auth_header[6:].strip()).decode("utf-8")
                username, password = decoded.split(":", 1)
                if username in AUTH_USERS and AUTH_USERS[username] == password:
                    auth_valid = True
                    auth_user = username
                else:
                    auth_valid = False
            except Exception:
                auth_valid = False

        elif auth_header.startswith("Bearer "):
            # Bearer Token：临时 Token 或服务端 Token
            token = auth_header[7:].strip()
            auth_valid = _is_valid_token(token)
            if auth_valid and token in _token_cache:
                auth_user = _token_cache[token].get("user")

        elif auth_header.startswith("token "):
            # token 前缀（兼容）
            token = auth_header[6:].strip()
            auth_valid = _is_valid_token(token)
            if auth_valid and token in _token_cache:
                auth_user = _token_cache[token].get("user")
        else:
            # 尝试从查询参数获取（部分 MCP Client 不支持自定义 Header）
            token = request.query_params.get("token", "")
            if token and _is_valid_token(token):
                auth_valid = True
                if token in _token_cache:
                    auth_user = _token_cache[token].get("user")

        if not auth_valid:
            logger.warning(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "event": "auth_rejected",
                        "path": request.url.path,
                        "client": request.client.host if request.client else "unknown",
                        "action": "unauthorized_access",
                    },
                    ensure_ascii=False,
                )
            )
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "认证失败：无效的用户名/密码或 Token，请检查配置或调用 authenticate 工具获取 Token"},
            )

        # 认证通过，记录用户信息
        if auth_user:
            logger.info(
                json.dumps(
                    {
                        "timestamp": time.time(),
                        "event": "auth_passed",
                        "path": request.url.path,
                        "user": auth_user,
                        "client": request.client.host if request.client else "unknown",
                    },
                    ensure_ascii=False,
                )
            )

        # 继续处理请求
        return await call_next(request)


# ──────────────────────────────────────────────
# 认证异常
# ──────────────────────────────────────────────

class AuthenticationError(Exception):
    """认证失败异常"""
    pass


# ──────────────────────────────────────────────
# 认证路由（独立于 MCP，供 Client 获取 Token）
# ──────────────────────────────────────────────

async def token_endpoint(request: Request) -> JSONResponse:
    """
    Token 认证端点
    POST /auth/token
    请求体: {"username": "admin", "password": "admin123"}
    返回: {"token": "...", "token_type": "Bearer", "expires_in": 3600}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "message": "无效的请求体"},
        )

    username = body.get("username", "")
    password = body.get("password", "")

    if not username or not password:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "message": "用户名和密码不能为空"},
        )

    token = _authenticate_user(username, password)
    if token:
        return JSONResponse(
            status_code=200,
            content={
                "token": token,
                "token_type": "Bearer",
                "expires_in": AUTH_TOKEN_EXPIRE_SECONDS,
            },
        )
    else:
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "message": "用户名或密码错误"},
        )


# ──────────────────────────────────────────────
# 导出
# ──────────────────────────────────────────────

__all__ = [
    "AuthMiddleware",
    "AuthenticationError",
    "get_server_token",
    "_authenticate_user",
    "_revoke_token",
    "_validate_tool_token",
    "auth_required",
    "token_endpoint",
]
