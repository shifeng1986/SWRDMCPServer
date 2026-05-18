"""
连接级别认证中间件

在MCP Client连接到MCP Server时进行Basic Auth认证验证。
支持basic_only和dual两种认证模式。
"""

import base64
import json
from typing import Callable, Optional, Dict, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import (
    AUTH_ENABLED,
    AUTH_USERS,
    AUTH_CACHE_TTL,
    AUTH_CACHE_MAX_SIZE,
    LDAP_ENABLED,
    LDAP_DEPT_ACCESS_CONTROL_ENABLED,
    LDAP_ALLOWED_DEPARTMENTS,
    LDAP_DEPT_EXACT_MATCH,
)
from ldap_auth import authenticate_with_ldap

# 使用新的日志记录器
from decorators.operation_log_handler import setup_operation_logger, setup_debug_logger, format_timestamp

operation_logger = setup_operation_logger()
debug_logger = setup_debug_logger()


class ConnectionAuthMiddleware(BaseHTTPMiddleware):
    """
    连接级别认证中间件

    在MCP Client连接到MCP Server时（初次握手阶段）进行Basic Auth认证验证。
    如果认证失败，直接返回401错误，拒绝连接。

    优化：使用缓存机制避免重复认证。
    """

    # 类级别的认证缓存：{auth_header: (username, timestamp)}
    _auth_cache: Dict[str, Tuple[str, float]] = {}

    # 缓存有效期（秒），从配置读取
    CACHE_TTL = AUTH_CACHE_TTL

    # 最大缓存条目数（防止内存泄漏），从配置读取
    MAX_CACHE_SIZE = AUTH_CACHE_MAX_SIZE

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 如果认证未启用，直接放行
        if not AUTH_ENABLED:
            return await call_next(request)

        # 检查请求头中的Authorization
        auth_header = request.headers.get("Authorization", "")
        client_ip = request.client.host if request.client else ""

        if not auth_header:
            operation_logger.warning(
                json.dumps(
                    {
                        "timestamp": format_timestamp(),
                        "event": "connection_auth_failed",
                        "reason": "缺少Authorization请求头",
                        "client_ip": client_ip,
                        "path": request.url.path,
                    },
                    ensure_ascii=False,
                )
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "认证失败",
                    "message": "缺少Authorization请求头，请提供Basic Auth凭据",
                },
            )

        # 解析Authorization头
        if not auth_header.startswith("Basic "):
            operation_logger.warning(
                json.dumps(
                    {
                        "timestamp": format_timestamp(),
                        "event": "connection_auth_failed",
                        "reason": "Authorization头格式错误，必须为Basic Auth",
                        "client_ip": client_ip,
                        "path": request.url.path,
                    },
                    ensure_ascii=False,
                )
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "认证失败",
                    "message": "Authorization头格式错误，必须为Basic Auth格式",
                },
            )

        # 检查缓存
        current_time = __import__("time").time()
        if auth_header in self._auth_cache:
            username, timestamp = self._auth_cache[auth_header]
            # 检查缓存是否过期
            if current_time - timestamp < self.CACHE_TTL:
                # 缓存命中，直接使用缓存结果
                debug_logger.debug(f"[缓存命中] user={username}, client_ip={client_ip}, path={request.url.path}")
                request.state.authenticated_user = username
                return await call_next(request)
            else:
                # 缓存过期，删除旧缓存
                debug_logger.debug(f"[缓存已过期] user={username}, client_ip={client_ip}, path={request.url.path}")
                del self._auth_cache[auth_header]

        # 缓存未命中或已过期，进行认证验证
        # 提取Base64编码部分
        base64_encoded = auth_header.replace("Basic ", "")

        try:
            # Base64解码
            decoded = base64.b64decode(base64_encoded).decode("utf-8")

            # 分割用户名和密码
            if ":" not in decoded:
                raise ValueError("解码后的格式错误，缺少冒号分隔符："+decoded)

            username, password = decoded.split(":", 1)

            # 验证用户名和密码（返回值可以是bool或错误信息字符串）
            auth_result = await self._authenticate_user(username, password, request)

            if auth_result is False:
                operation_logger.warning(
                    json.dumps(
                        {
                            "timestamp": format_timestamp(),
                            "event": "connection_auth_failed",
                            "reason": "用户名或密码错误",
                            "username": username,
                            "client_ip": client_ip,
                            "path": request.url.path,
                        },
                        ensure_ascii=False,
                    )
                )
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "认证失败",
                        "message": "用户名或密码错误",
                    },
                )

            # 如果返回的是字符串，说明是部门访问被拒绝的错误信息
            if isinstance(auth_result, str):
                operation_logger.warning(
                    json.dumps(
                        {
                            "timestamp": format_timestamp(),
                            "event": "connection_auth_failed",
                            "reason": auth_result,
                            "username": username,
                            "client_ip": client_ip,
                            "path": request.url.path,
                        },
                        ensure_ascii=False,
                    )
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "访问被拒绝",
                        "message": auth_result,
                    },
                )

            # 认证成功，记录日志（包含部门信息）
            auth_log = {
                "timestamp": format_timestamp(),
                "event": "connection_auth_success",
                "username": username,
                "department": getattr(request.state, "department", ""),# 从 request.state 中读取部门信息（由 _authenticate_user 设置）
                "client_ip": client_ip,
                "path": request.url.path,
            }

            operation_logger.info(json.dumps(auth_log, ensure_ascii=False))

            # 检查缓存大小，如果超过限制，先清理过期条目
            if len(self._auth_cache) >= self.MAX_CACHE_SIZE:
                # 清理过期条目
                expired_keys = [
                    key for key, (_, timestamp) in self._auth_cache.items()
                    if current_time - timestamp >= self.CACHE_TTL
                ]
                for key in expired_keys:
                    del self._auth_cache[key]

                # 如果清理后仍然超过限制，删除最旧的条目
                if len(self._auth_cache) >= self.MAX_CACHE_SIZE:
                    # 按时间戳排序，删除最旧的10%条目
                    sorted_items = sorted(
                        self._auth_cache.items(),
                        key=lambda x: x[1][1]  # 按timestamp排序
                    )
                    # 删除最旧的10%条目
                    delete_count = max(1, len(sorted_items) // 10)
                    for i in range(delete_count):
                        del self._auth_cache[sorted_items[i][0]]

                    debug_logger.info(
                        f"[缓存清理] 删除了 {delete_count} 个旧缓存条目，剩余 {len(self._auth_cache)} 个"
                    )

            # 将认证结果存入缓存
            self._auth_cache[auth_header] = (username, current_time)

            # 将用户信息添加到请求状态中，供后续使用
            request.state.authenticated_user = username

            # 继续处理请求
            return await call_next(request)

        except Exception as e:
            operation_logger.error(
                json.dumps(
                    {
                        "timestamp": format_timestamp(),
                        "event": "connection_auth_error",
                        "error": str(e),
                        "path": request.url.path,
                    },
                    ensure_ascii=False,
                )
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "认证失败",
                    "message": f"认证处理失败: {str(e)}",
                },
            )

    async def _authenticate_user(self, username: str, password: str, request: Request) -> bool | str:
        """
        验证用户名和密码

        优先使用LDAP认证，失败则使用本地认证

        返回:
            True: 认证成功
            False: 认证失败
            str: 部门访问被拒绝的错误信息
        """
        # 优先尝试LDAP认证
        if LDAP_ENABLED:
            try:
                is_valid, message = authenticate_with_ldap(username, password)
                if is_valid:
                    # 获取LDAP用户详细信息
                    try:
                        from ldap_auth import get_ldap_authenticator
                        authenticator = get_ldap_authenticator()
                        user_info = authenticator.get_user_info(username)

                        # 打印用户详细信息
                        if user_info:
                            debug_logger.debug(f"[LDAP用户信息] user={username}, department={user_info.get('department', '')}")

                            # 部门访问控制检查
                            if LDAP_DEPT_ACCESS_CONTROL_ENABLED:
                                # 获取用户部门信息
                                user_department = user_info.get("department", "")
                                user_ou = user_info.get("ou", "")

                                # 优先使用 department，如果为空则使用 ou
                                dept_to_check = user_department if user_department else user_ou

                                request.state.department = dept_to_check

                                debug_logger.debug(f"[部门访问检查] user={username}, department={dept_to_check}")

                                # 检查部门是否在允许列表中
                                if not dept_to_check:
                                    debug_logger.warning(f"[部门访问拒绝] 用户没有部门信息 - user={username}")
                                    return "您的账号没有部门信息，无法访问此系统"

                                # 检查部门访问权限
                                access_allowed = False
                                if LDAP_DEPT_EXACT_MATCH:
                                    # 精确匹配
                                    access_allowed = dept_to_check in LDAP_ALLOWED_DEPARTMENTS
                                else:
                                    # 模糊匹配（包含即可）
                                    # 要么用户部门是允许部门的子部门；要么允许部门是用户部门的子部门；两者皆可
                                    access_allowed = any(
                                        allowed_dept in dept_to_check or dept_to_check in allowed_dept
                                        for allowed_dept in LDAP_ALLOWED_DEPARTMENTS
                                    )

                                if not access_allowed:
                                    debug_logger.warning(f"[部门访问拒绝] 部门不在允许列表中 - user={username}, department={dept_to_check}")
                                    return f"您的部门「{dept_to_check}」不在允许访问列表中，无法访问此系统"

                                debug_logger.info(f"[部门访问允许] user={username}, department={dept_to_check}")

                    except Exception as e:
                        # 获取用户信息失败不影响认证流程（除非启用了部门访问控制）
                        if LDAP_DEPT_ACCESS_CONTROL_ENABLED:
                            debug_logger.error(f"[获取用户信息失败] user={username}, error={str(e)}", exc_info=True)
                            # 启用了部门访问控制时，获取用户信息失败则拒绝访问
                            return False
                        else:
                            debug_logger.debug(f"[获取用户信息失败] user={username}, error={str(e)}")

                    debug_logger.info(f"[用户认证成功] user={username}, auth_type=ldap")
                    return True
                else:
                    debug_logger.warning(f"[LDAP认证失败] user={username}, reason={message}")
                    # LDAP认证失败，继续尝试本地认证
            except Exception as e:
                debug_logger.error(f"[LDAP认证错误] user={username}, error={str(e)}", exc_info=True)
                # LDAP认证出错，继续尝试本地认证

        # 本地认证（备用）
        if username in AUTH_USERS and AUTH_USERS[username] == password:
            debug_logger.info(f"[用户认证成功] user={username}, auth_type=local")
            return True

        debug_logger.warning(f"[认证失败] user={username}")
        return False

    @classmethod
    def clear_expired_cache(cls):
        """
        清理过期的认证缓存

        定期调用此方法可以清理过期的缓存条目，避免内存泄漏
        """
        current_time = __import__("time").time()
        expired_keys = [
            key for key, (_, timestamp) in cls._auth_cache.items()
            if current_time - timestamp >= cls.CACHE_TTL
        ]

        for key in expired_keys:
            del cls._auth_cache[key]

        if expired_keys:
            debug_logger.info(f"[缓存清理] 清理了 {len(expired_keys)} 个过期缓存，剩余 {len(cls._auth_cache)} 个")

    @classmethod
    def get_cache_stats(cls) -> dict:
        """
        获取缓存统计信息

        Returns:
            dict: 包含缓存统计信息的字典
        """
        current_time = __import__("time").time()

        # 统计活跃和过期的缓存条目
        active_count = 0
        expired_count = 0
        username_counts = {}

        for auth_header, (username, timestamp) in cls._auth_cache.items():
            if current_time - timestamp >= cls.CACHE_TTL:
                expired_count += 1
            else:
                active_count += 1
                # 统计每个用户的缓存条目数
                username_counts[username] = username_counts.get(username, 0) + 1

        return {
            "total_count": len(cls._auth_cache),
            "active_count": active_count,
            "expired_count": expired_count,
            "max_cache_size": cls.MAX_CACHE_SIZE,
            "cache_ttl_seconds": cls.CACHE_TTL,
            "username_counts": username_counts,
            "usage_percentage": round(len(cls._auth_cache) / cls.MAX_CACHE_SIZE * 100, 2),
        }


__all__ = ["ConnectionAuthMiddleware"]
