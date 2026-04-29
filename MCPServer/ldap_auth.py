"""
LDAP认证模块

提供基于公司LDAP的用户认证功能：
- 支持LDAP用户绑定认证
- 支持用户搜索和验证
- 与现有认证系统无缝集成

配置项由 config.py 统一管理，支持通过 security_config.yaml 自定义。
"""

from ldap3 import Server, Connection, ALL, SUBTREE
import logging
from typing import Optional, Tuple

from config import (
    LDAP_ENABLED,
    LDAP_SERVER_URI,
    LDAP_BIND_DN,
    LDAP_BIND_PASSWORD,
    LDAP_USER_SEARCH_BASE,
    LDAP_USER_SEARCH_FILTER,
)

logger = logging.getLogger(__name__)


class LDAPAuthError(Exception):
    """LDAP认证异常"""
    pass


class LDAPAuthenticator:
    """LDAP认证器"""

    def __init__(self):
        """初始化LDAP认证器"""
        if not LDAP_ENABLED:
            logger.warning("LDAP认证未启用")
            return

        self.server_uri = LDAP_SERVER_URI
        self.bind_dn = LDAP_BIND_DN
        self.bind_password = LDAP_BIND_PASSWORD
        self.search_base = LDAP_USER_SEARCH_BASE
        self.search_filter = LDAP_USER_SEARCH_FILTER

        logger.info(f"LDAP认证器已初始化，服务器: {self.server_uri}")

    def _get_ldap_connection(self) -> Connection:
        """
        获取LDAP连接

        返回:
            LDAP连接对象

        异常:
            LDAPAuthError: 连接失败时抛出
        """
        try:
            # 创建LDAP服务器对象
            server = Server(self.server_uri, get_info=ALL)

            # 创建连接并绑定
            conn = Connection(
                server,
                user=self.bind_dn,
                password=self.bind_password,
                auto_bind=True
            )

            logger.debug(f"成功连接到LDAP服务器: {self.server_uri}")
            return conn

        except Exception as e:
            logger.error(f"LDAP连接失败: {str(e)}")
            raise LDAPAuthError(f"无法连接到LDAP服务器: {str(e)}")

    def authenticate(self, username: str, password: str) -> Tuple[bool, str]:
        """
        验证用户名和密码

        Args:
            username: 用户名
            password: 密码

        返回:
            (is_valid, message) 元组
            - is_valid: 认证是否成功
            - message: 认证结果描述

        异常:
            LDAPAuthError: LDAP操作失败时抛出
        """
        if not LDAP_ENABLED:
            return False, "LDAP认证未启用"

        if not username or not password:
            return False, "用户名和密码不能为空"

        try:
            # 获取LDAP连接
            conn = self._get_ldap_connection()

            # 搜索用户DN
            search_filter = self.search_filter % {"user": username}
            conn.search(
                search_base=self.search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['cn', 'sAMAccountName']
            )

            if not conn.entries:
                logger.warning(f"LDAP中未找到用户: {username}")
                return False, "用户不存在"

            # 获取用户DN
            user_dn = conn.entries[0].entry_dn
            logger.debug(f"找到用户DN: {user_dn}")

            # 尝试用用户DN和密码绑定
            try:
                server = Server(self.server_uri)
                user_conn = Connection(
                    server,
                    user=user_dn,
                    password=password,
                    auto_bind=True
                )
                user_conn.unbind()

                logger.info(f"用户认证成功: {username}")
                return True, "认证成功"

            except Exception as e:
                logger.warning(f"用户密码错误: {username}, 错误: {str(e)}")
                return False, "密码错误"

        except LDAPAuthError as e:
            logger.error(f"LDAP认证异常: {str(e)}")
            return False, str(e)

        except Exception as e:
            logger.error(f"未知错误: {str(e)}")
            return False, f"认证失败: {str(e)}"

        finally:
            try:
                conn.unbind()
            except Exception:
                pass

    def get_user_info(self, username: str) -> Optional[dict]:
        """
        获取用户信息

        Args:
            username: 用户名

        返回:
            用户信息字典，包含用户属性；如果用户不存在返回None
        """
        if not LDAP_ENABLED:
            return None

        try:
            conn = self._get_ldap_connection()

            # 搜索用户
            search_filter = self.search_filter % {"user": username}
            conn.search(
                search_base=self.search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['dn', 'cn', 'mail', 'displayName', 'sAMAccountName']
            )

            if not conn.entries:
                return None

            # 解析用户信息
            entry = conn.entries[0]
            user_info = {
                "dn": str(entry.entry_dn),
                "username": str(entry.sAMAccountName) if entry.sAMAccountName else username,
                "cn": str(entry.cn) if entry.cn else "",
                "mail": str(entry.mail) if entry.mail else "",
                "displayName": str(entry.displayName) if entry.displayName else "",
            }

            return user_info

        except Exception as e:
            logger.error(f"获取用户信息失败: {str(e)}")
            return None

        finally:
            try:
                conn.unbind()
            except Exception:
                pass

    def test_connection(self) -> Tuple[bool, str]:
        """
        测试LDAP连接

        返回:
            (is_connected, message) 元组
            - is_connected: 连接是否成功
            - message: 测试结果描述
        """
        if not LDAP_ENABLED:
            return False, "LDAP认证未启用"

        try:
            conn = self._get_ldap_connection()
            conn.unbind()
            return True, "LDAP连接测试成功"
        except LDAPAuthError as e:
            return False, str(e)
        except Exception as e:
            return False, f"连接测试失败: {str(e)}"


# 全局LDAP认证器实例
_ldap_authenticator: Optional[LDAPAuthenticator] = None


def get_ldap_authenticator() -> Optional[LDAPAuthenticator]:
    """获取LDAP认证器实例（单例）"""
    global _ldap_authenticator
    if _ldap_authenticator is None and LDAP_ENABLED:
        _ldap_authenticator = LDAPAuthenticator()
    return _ldap_authenticator


def authenticate_with_ldap(username: str, password: str) -> Tuple[bool, str]:
    """
    使用LDAP认证用户

    Args:
        username: 用户名
        password: 密码

    返回:
        (is_valid, message) 元组
    """
    authenticator = get_ldap_authenticator()
    if not authenticator:
        return False, "LDAP认证不可用"

    return authenticator.authenticate(username, password)


__all__ = [
    "LDAPAuthError",
    "LDAPAuthenticator",
    "get_ldap_authenticator",
    "authenticate_with_ldap",
]
