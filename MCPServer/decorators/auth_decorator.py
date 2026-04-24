"""
用户认证模块

提供基于 Token 的用户认证功能：
- MCP Server 启动时生成随机 Token，或从配置文件读取固定 Token
- 通过 Starlette 中间件拦截所有 /mcp 请求，验证 Authorization 头
- 提供 authenticate 工具供用户登录获取 Token
- 支持用户名/密码认证和 Token 认证两种方式

配置项由 config.py 统一管理，支持通过 security_config.yaml 自定义。
"""

import functools
import json
import logging
import secrets
import time
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
    """验证 Token 是否有效"""
    if not token:
        return False

    # 检查是否为服务端 Token
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


def _authenticate_user(username: str, password: str) -> Optional[str]:
    """验证用户名/密码，成功则返回新生成的 Token"""
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
# 认证中间件
# ──────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Token 认证中间件

    拦截所有 /mcp 请求，验证 Authorization 头中的 Token。
    仅当 AUTH_ENABLED 为 True 时生效。
    """

    async def dispatch(self, request: Request, call_next):
        # 认证未启用，直接放行
        if not AUTH_ENABLED:
            return await call_next(request)

        # 仅对 /mcp 路径进行认证，/auth 路径放行
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        # 从 Authorization 头提取 Token
        auth_header = request.headers.get("Authorization", "")
        token = None

        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif auth_header.startswith("token "):
            token = auth_header[6:].strip()
        else:
            # 尝试从查询参数获取（部分 MCP Client 不支持自定义 Header）
            token = request.query_params.get("token", "")

        if not token or not _is_valid_token(token):
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
                content={"error": "Unauthorized", "message": "无效或缺失的认证 Token，请先调用 authenticate 工具获取 Token"},
            )

        # Token 有效，继续处理请求
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
    "token_endpoint",
]
