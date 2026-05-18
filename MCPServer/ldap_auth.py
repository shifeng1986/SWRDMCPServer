"""
LDAP认证模块

提供基于公司LDAP的用户认证功能：
- 支持LDAP用户绑定认证
- 支持用户搜索和验证
- 与现有认证系统无缝集成

配置项由 config.py 统一管理，支持通过 security_config.yaml 自定义。
"""

from ldap3 import Server, Connection, ALL, SUBTREE
from typing import Optional, Tuple

from config import (
    LDAP_ENABLED,
    LDAP_SERVER_URI,
    LDAP_BIND_DN,
    LDAP_BIND_PASSWORD,
    LDAP_USER_SEARCH_BASE,
    LDAP_USER_SEARCH_FILTER,
)

# 使用新的日志记录器
from decorators.operation_log_handler import setup_operation_logger, setup_debug_logger

operation_logger = setup_operation_logger()
debug_logger = setup_debug_logger()


class LDAPAuthError(Exception):
    """LDAP认证异常"""
    pass


class LDAPAuthenticator:
    """LDAP认证器"""

    def __init__(self):
        """初始化LDAP认证器"""
        if not LDAP_ENABLED:
            operation_logger.warning("LDAP认证未启用")
            return

        self.server_uri = LDAP_SERVER_URI
        self.bind_dn = LDAP_BIND_DN
        self.bind_password = LDAP_BIND_PASSWORD
        self.search_base = LDAP_USER_SEARCH_BASE
        self.search_filter = LDAP_USER_SEARCH_FILTER

        debug_logger.info(f"LDAP认证器初始化 - server={self.server_uri}")

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

            debug_logger.debug(f"成功连接到LDAP服务器: {self.server_uri}")
            return conn

        except Exception as e:
            operation_logger.error(f"LDAP连接失败: {str(e)}")
            debug_logger.error(f"LDAP连接失败 - server={self.server_uri}, error={str(e)}", exc_info=True)
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
                debug_logger.warning(f"[LDAP用户未找到] username={username}")
                return False, "用户不存在"

            # 获取用户DN
            user_dn = conn.entries[0].entry_dn
            debug_logger.debug(f"找到用户DN: {user_dn}")

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

                debug_logger.info(f"[用户认证成功] username={username}")
                return True, "认证成功"

            except Exception as e:
                debug_logger.warning(f"[用户密码错误] username={username}, error={str(e)}")
                return False, "密码错误"

        except LDAPAuthError as e:
            debug_logger.error(f"[LDAP认证异常] error={str(e)}", exc_info=True)
            return False, str(e)

        except Exception as e:
            debug_logger.error(f"[未知错误] error={str(e)}", exc_info=True)
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

            # 搜索用户，包含部门相关属性
            search_filter = self.search_filter % {"user": username}
            conn.search(
                search_base=self.search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['cn', 'mail', 'displayName', 'sAMAccountName',
                          'title', 'department', 'departmentNumber', 'company',
                          'ou', 'physicalDeliveryOfficeName', 'l', 'st', 'co',
                          'telephoneNumber', 'mobile', 'postalCode', 'streetAddress',
                          'description', 'manager', 'employeeNumber', 'employeeType',
                          'division', 'businessCategory', 'extensionAttribute1',
                          'extensionAttribute2', 'extensionAttribute3', 'extensionAttribute4',
                          'extensionAttribute5', 'extensionAttribute6', 'extensionAttribute7',
                          'extensionAttribute8', 'extensionAttribute9', 'extensionAttribute10']
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
                "title": str(entry.title) if hasattr(entry, 'title') and entry.title else "",
                "department": str(entry.department) if hasattr(entry, 'department') and entry.department else "",
                "departmentNumber": str(entry.departmentNumber) if hasattr(entry, 'departmentNumber') and entry.departmentNumber else "",
                "company": str(entry.company) if hasattr(entry, 'company') and entry.company else "",
                "ou": str(entry.ou) if hasattr(entry, 'ou') and entry.ou else "",
                "physicalDeliveryOfficeName": str(entry.physicalDeliveryOfficeName) if hasattr(entry, 'physicalDeliveryOfficeName') and entry.physicalDeliveryOfficeName else "",
                "location": str(entry.l) if hasattr(entry, 'l') and entry.l else "",
                "state": str(entry.st) if hasattr(entry, 'st') and entry.st else "",
                "country": str(entry.co) if hasattr(entry, 'co') and entry.co else "",
                "telephoneNumber": str(entry.telephoneNumber) if hasattr(entry, 'telephoneNumber') and entry.telephoneNumber else "",
                "mobile": str(entry.mobile) if hasattr(entry, 'mobile') and entry.mobile else "",
                "postalCode": str(entry.postalCode) if hasattr(entry, 'postalCode') and entry.postalCode else "",
                "streetAddress": str(entry.streetAddress) if hasattr(entry, 'streetAddress') and entry.streetAddress else "",
                "description": str(entry.description) if hasattr(entry, 'description') and entry.description else "",
                "manager": str(entry.manager) if hasattr(entry, 'manager') and entry.manager else "",
                "employeeNumber": str(entry.employeeNumber) if hasattr(entry, 'employeeNumber') and entry.employeeNumber else "",
                "employeeType": str(entry.employeeType) if hasattr(entry, 'employeeType') and entry.employeeType else "",
                "division": str(entry.division) if hasattr(entry, 'division') and entry.division else "",
                "businessCategory": str(entry.businessCategory) if hasattr(entry, 'businessCategory') and entry.businessCategory else "",
                "extensionAttribute1": str(entry.extensionAttribute1) if hasattr(entry, 'extensionAttribute1') and entry.extensionAttribute1 else "",
                "extensionAttribute2": str(entry.extensionAttribute2) if hasattr(entry, 'extensionAttribute2') and entry.extensionAttribute2 else "",
                "extensionAttribute3": str(entry.extensionAttribute3) if hasattr(entry, 'extensionAttribute3') and entry.extensionAttribute3 else "",
                "extensionAttribute4": str(entry.extensionAttribute4) if hasattr(entry, 'extensionAttribute4') and entry.extensionAttribute4 else "",
                "extensionAttribute5": str(entry.extensionAttribute5) if hasattr(entry, 'extensionAttribute5') and entry.extensionAttribute5 else "",
                "extensionAttribute6": str(entry.extensionAttribute6) if hasattr(entry, 'extensionAttribute6') and entry.extensionAttribute6 else "",
                "extensionAttribute7": str(entry.extensionAttribute7) if hasattr(entry, 'extensionAttribute7') and entry.extensionAttribute7 else "",
                "extensionAttribute8": str(entry.extensionAttribute8) if hasattr(entry, 'extensionAttribute8') and entry.extensionAttribute8 else "",
                "extensionAttribute9": str(entry.extensionAttribute9) if hasattr(entry, 'extensionAttribute9') and entry.extensionAttribute9 else "",
                "extensionAttribute10": str(entry.extensionAttribute10) if hasattr(entry, 'extensionAttribute10') and entry.extensionAttribute10 else "",
            }

            # 打印用户详细信息到日志（调试日志）
            debug_logger.info(
                f"LDAP用户信息 - 用户名: {username}, "
                f"显示名: {user_info['displayName']}, "
                f"部门: {user_info['department']}, "
                f"部门编号: {user_info['departmentNumber']}, "
                f"公司: {user_info['company']}, "
                f"职位: {user_info['title']}, "
                f"邮箱: {user_info['mail']}, "
                f"OU: {user_info['ou']}, "
                f"办公地点: {user_info['physicalDeliveryOfficeName']}, "
                f"位置: {user_info['location']}, "
                f"省/州: {user_info['state']}, "
                f"国家: {user_info['country']}, "
                f"电话: {user_info['telephoneNumber']}, "
                f"手机: {user_info['mobile']}, "
                f"员工编号: {user_info['employeeNumber']}, "
                f"员工类型: {user_info['employeeType']}, "
                f"部门: {user_info['division']}, "
                f"业务类别: {user_info['businessCategory']}, "
                f"DN: {user_info['dn']}"
            )
            debug_logger.debug(f"[LDAP用户信息] username={username}, department={user_info['department']}, displayName={user_info['displayName']}")

            return user_info

        except Exception as e:
            operation_logger.error(f"获取用户信息失败: {str(e)}")
            debug_logger.error(f"[获取用户信息失败] username={username}, error={str(e)}", exc_info=True)
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
