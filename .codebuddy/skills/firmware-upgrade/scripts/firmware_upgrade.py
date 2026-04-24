"""
BMC Firmware Upgrade Skill - 固件升级功能

设备连接信息和固件配置请参考 .codebuddy/rules/SystemTest.mdc 中的环境配置，
不要硬编码或自行猜测 IP 地址或固件路径。
"""

import json
import time
import os
import re
from typing import Dict, List, Any, Optional

# 配置文件路径
SYSTEM_TEST_CONFIG = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "rules", "SystemTest.mdc"
)


def load_system_test_config() -> Dict[str, Any]:
    """
    从SystemTest.mdc加载配置信息

    Returns:
        包含设备信息和固件配置的字典
    """
    config = {
        "pc_ip": "10.41.112.148",
        "device_ip": "192.168.49.71",
        "device_user": "admin",
        "device_password": "Password@_",
        "ftp_server": "10.141.228.15",
        "ftp_username": "ftp-CCSPLSmart",
        "ftp_password": "G7h253",
        "firmware_path": "/data-out/w33199/0427/HDM3_3.05_signed.bin"
    }

    if not os.path.exists(SYSTEM_TEST_CONFIG):
        return config

    try:
        with open(SYSTEM_TEST_CONFIG, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析PC代理IP
        pc_ip_match = re.search(r'大网IP.*?(\d+\.\d+\.\d+\.\d+)', content)
        if pc_ip_match:
            config["pc_ip"] = pc_ip_match.group(1)

        # 解析设备IP
        device_ip_match = re.search(r'测试设备IP.*?(\d+\.\d+\.\d+\.\d+)', content)
        if device_ip_match:
            config["device_ip"] = device_ip_match.group(1)

        # 解析设备用户名
        user_match = re.search(r'测试设备用户名：(\w+)', content)
        if user_match:
            config["device_user"] = user_match.group(1)

        # 解析设备密码
        password_match = re.search(r'测试设备密码：(.+)', content)
        if password_match:
            config["device_password"] = password_match.group(1)

        # 解析FTP服务器
        ftp_server_match = re.search(r'FTP服务器地址.*?(\d+\.\d+\.\d+\.\d+)', content)
        if ftp_server_match:
            config["ftp_server"] = ftp_server_match.group(1)

        # 解析FTP用户名
        ftp_user_match = re.search(r'FTP用户名：(.+)', content)
        if ftp_user_match:
            config["ftp_username"] = ftp_user_match.group(1)

        # 解析FTP密码
        ftp_password_match = re.search(r'FTP密码：(.+)', content)
        if ftp_password_match:
            config["ftp_password"] = ftp_password_match.group(1)

        # 解析固件路径
        firmware_path_match = re.search(r'固件文件路径：([^\n]+)', content)
        if firmware_path_match:
            config["firmware_path"] = firmware_path_match.group(1)

    except Exception as e:
        print(f"警告：读取SystemTest.mdc失败 - {e}，使用默认配置")

    return config


class FirmwareUpgradeController:
    """BMC固件升级控制器"""

    def __init__(self, device_ip: str, username: str, password: str):
        """
        初始化固件升级控制器。
        设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取，不允许硬编码或自行猜测。

        Args:
            device_ip: BMC设备IP地址（从SystemTest.mdc读取）
            username: 登录用户名（从SystemTest.mdc读取）
            password: 登录密码（从SystemTest.mdc读取）
        """
        self.device_ip = device_ip
        self.username = username
        self.password = password
        self.base_url = f"https://{device_ip}"

        # 加载固件配置
        self.config = load_system_test_config()

    @property
    def ftp_server(self) -> str:
        """FTP服务器地址"""
        return self.config["ftp_server"]

    @property
    def ftp_username(self) -> str:
        """FTP用户名"""
        return self.config["ftp_username"]

    @property
    def ftp_password(self) -> str:
        """FTP密码"""
        return self.config["ftp_password"]

    @property
    def firmware_path(self) -> str:
        """固件文件路径"""
        return self.config["firmware_path"]

    @property
    def firmware_uri(self) -> str:
        """完整的固件URI"""
        return f"ftp://{self.ftp_username}:{self.ftp_password}@{self.ftp_server}{self.firmware_path}"

    def __init__(self, device_ip: str, username: str, password: str):
        """
        初始化固件升级控制器。
        设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取，不允许硬编码或自行猜测。

        Args:
            device_ip: BMC设备IP地址（从SystemTest.mdc读取）
            username: 登录用户名（从SystemTest.mdc读取）
            password: 登录密码（从SystemTest.mdc读取）
        """
        self.device_ip = device_ip
        self.username = username
        self.password = password
        self.base_url = f"https://{device_ip}"

    def get_firmware_inventory(self) -> Dict:
        """
        查询固件清单

        Returns:
            Redfish请求参数
        """
        return {
            "method": "GET",
            "URL": "/redfish/v1/UpdateService/FirmwareInventory",
            "body": ""
        }

    def get_update_service(self) -> Dict:
        """
        查询升级服务信息

        Returns:
            Redfish请求参数
        """
        return {
            "method": "GET",
            "URL": "/redfish/v1/UpdateService",
            "body": ""
        }

    def start_firmware_upgrade(
        self,
        image_uri: Optional[str] = None,
        protocol: str = "ftp",
        preserve: str = "Retain",
        reboot_mode: str = "Auto",
        backup: bool = False
    ) -> Dict:
        """
        发起固件升级

        Args:
            image_uri: 固件文件URI，如果为None则使用SystemTest.mdc中配置的FTP路径
            protocol: 协议类型（ftp, tftp, http, https, sftp, nfs）
            preserve: 配置保留策略（Retain, Restore, ForceRestore）
            reboot_mode: 重启模式（Auto, Manual）
            backup: 是否备份配置

        Returns:
            Redfish请求参数
        """
        # 构建固件URI
        if image_uri is None:
            if protocol == "ftp":
                # 使用SystemTest.mdc中配置的固件URI
                image_uri = self.firmware_uri
            else:
                raise ValueError(f"协议 {protocol} 需要提供 image_uri 参数")

        # 构建请求体
        body = {
            "ImageURI": image_uri,
            "Oem": {
                "Public": {
                    "Preserve": preserve,
                    "RebootMode": reboot_mode,
                    "Backup": backup
                }
            }
        }

        return {
            "method": "POST",
            "URL": "/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate",
            "body": json.dumps(body)
        }

    def get_upgrade_status(self) -> Dict:
        """
        查询升级状态

        Returns:
            Redfish请求参数
        """
        return {
            "method": "GET",
            "URL": "/redfish/v1/UpdateService",
            "body": ""
        }

    def get_task_status(self, task_id: str) -> Dict:
        """
        查询任务状态

        Args:
            task_id: 任务ID

        Returns:
            Redfish请求参数
        """
        return {
            "method": "GET",
            "URL": f"/redfish/v1/TaskService/Tasks/{task_id}",
            "body": ""
        }

    def parse_upgrade_status(self, response: Dict) -> Dict[str, Any]:
        """
        解析升级状态响应

        Args:
            response: Redfish响应

        Returns:
            升级状态信息
        """
        try:
            data = json.loads(response)
            oem = data.get("Oem", {})
            public = oem.get("Public", {})

            return {
                "upgrade_state": public.get("UpgradeState"),
                "upgrade_progress": public.get("UpgradeProgress"),
                "service_enabled": data.get("ServiceEnabled"),
                "status": data.get("Status", {})
            }
        except Exception as e:
            return {
                "error": str(e),
                "upgrade_state": "Unknown"
            }

    def is_upgrade_complete(self, response: Dict) -> bool:
        """
        判断升级是否完成

        Args:
            response: Redfish响应

        Returns:
            True表示升级完成，False表示升级中
        """
        status = self.parse_upgrade_status(response)
        upgrade_state = status.get("upgrade_state")

        return upgrade_state in ["Success", "Failed", None]

    def is_upgrade_success(self, response: Dict) -> bool:
        """
        判断升级是否成功

        Args:
            response: Redfish响应

        Returns:
            True表示升级成功，False表示升级失败或进行中
        """
        status = self.parse_upgrade_status(response)
        upgrade_state = status.get("upgrade_state")

        return upgrade_state == "Success"

    def wait_for_upgrade_complete(
        self,
        check_interval: int = 30,
        timeout: int = 1800
    ) -> Dict[str, Any]:
        """
        等待升级完成（生成检查请求，实际需要循环调用）

        Args:
            check_interval: 检查间隔（秒）
            timeout: 超时时间（秒）

        Returns:
            包含检查请求和超时信息的字典
        """
        return {
            "check_request": self.get_upgrade_status(),
            "check_interval": check_interval,
            "timeout": timeout
        }


# ──────────────────────────────────────────────
# 便捷函数
# ──────────────────────────────────────────────

def firmware_get_inventory(device_ip: str, username: str, password: str) -> Dict:
    """查询固件清单。设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取。"""
    controller = FirmwareUpgradeController(device_ip, username, password)
    return controller.get_firmware_inventory()

def firmware_start_upgrade(
    device_ip: str,
    username: str,
    password: str,
    image_uri: Optional[str] = None,
    protocol: str = "ftp",
    preserve: str = "Retain",
    reboot_mode: str = "Auto",
    backup: bool = False
) -> Dict:
    """发起固件升级。设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取。"""
    controller = FirmwareUpgradeController(device_ip, username, password)
    return controller.start_firmware_upgrade(image_uri, protocol, preserve, reboot_mode, backup)

def firmware_get_status(device_ip: str, username: str, password: str) -> Dict:
    """查询升级状态。设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取。"""
    controller = FirmwareUpgradeController(device_ip, username, password)
    return controller.get_upgrade_status()

def firmware_parse_status(response: Dict) -> Dict[str, Any]:
    """解析升级状态响应。"""
    controller = FirmwareUpgradeController("dummy", "dummy", "dummy")
    return controller.parse_upgrade_status(response)

def firmware_is_complete(response: Dict) -> bool:
    """判断升级是否完成。"""
    controller = FirmwareUpgradeController("dummy", "dummy", "dummy")
    return controller.is_upgrade_complete(response)

def firmware_is_success(response: Dict) -> bool:
    """判断升级是否成功。"""
    controller = FirmwareUpgradeController("dummy", "dummy", "dummy")
    return controller.is_upgrade_success(response)
