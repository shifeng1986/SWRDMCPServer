#!/usr/bin/env python3
"""
BMC固件升级示例脚本

演示如何使用firmware_upgrade技能进行固件升级
"""

import requests
import json
import time
import sys
import os

# 添加skill路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from firmware_upgrade import (
    FirmwareUpgradeController,
    load_system_test_config,
    firmware_get_inventory,
    firmware_start_upgrade,
    firmware_get_status,
    firmware_parse_status,
    firmware_is_complete,
    firmware_is_success
)

# MCP服务器配置
MCP_SERVER = "http://localhost:8000"

# 从SystemTest.mdc加载配置
config = load_system_test_config()
PC_IP = config["pc_ip"]
DEVICE_IP = config["device_ip"]
DEVICE_USER = config["device_user"]
DEVICE_PWD = config["device_password"]

# 获取认证token
def get_auth_token():
    """获取认证token"""
    url = f"{MCP_SERVER}/mcp/authenticate"
    payload = {
        "username": "admin",
        "password": "admin123"
    }
    response = requests.post(url, json=payload, timeout=10)
    data = response.json()
    return data.get("token")

def send_redfish(method, url, body, token):
    """发送Redfish请求"""
    api_url = f"{MCP_SERVER}/mcp/sendRedfish"
    payload = {
        "pcIP": PC_IP,
        "deviceIP": DEVICE_IP,
        "deviceUser": DEVICE_USER,
        "DevicePwd": DEVICE_PWD,
        "method": method,
        "URL": url,
        "body": body,
        "token": token,
        "userName": "w33199"
    }
    response = requests.post(api_url, json=payload, timeout=60)
    return response.json()

def print_step(step_num, description):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"[步骤 {step_num}] {description}")
    print('='*60)

def main():
    """主函数"""
    print("="*60)
    print("BMC固件升级示例")
    print("="*60)

    # 获取认证token
    print("\n[准备] 获取认证token...")
    try:
        token = get_auth_token()
        if not token:
            print("错误：无法获取认证token")
            return
        print(f"认证token: {token[:20]}...")
    except Exception as e:
        print(f"错误：获取认证token失败 - {e}")
        return

    # 步骤1：查询当前固件版本
    print_step(1, "查询当前固件版本")
    try:
        req = firmware_get_inventory(DEVICE_IP, DEVICE_USER, DEVICE_PWD)
        response = send_redfish(req["method"], req["URL"], req["body"], token)
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)[:500]}...")
    except Exception as e:
        print(f"错误：查询固件版本失败 - {e}")
        return

    # 步骤2：查询升级服务状态
    print_step(2, "查询升级服务状态")
    try:
        req = firmware_get_status(DEVICE_IP, DEVICE_USER, DEVICE_PWD)
        response = send_redfish(req["method"], req["URL"], req["body"], token)

        # 解析响应
        try:
            response_data = json.loads(response)
            print(f"服务启用: {response_data.get('ServiceEnabled', 'Unknown')}")
            print(f"最大镜像大小: {response_data.get('MaxImageSizeBytes', 'Unknown')} bytes")

            oem = response_data.get("Oem", {})
            public = oem.get("Public", {})
            upgrade_state = public.get("UpgradeState")

            if upgrade_state:
                print(f"当前升级状态: {upgrade_state}")
                if upgrade_state != "Success" and upgrade_state != "Failed" and upgrade_state is not None:
                    print("警告：设备正在升级中，请等待完成后再进行新升级")
                    return
        except Exception as e:
            print(f"警告：解析响应失败 - {e}")
    except Exception as e:
        print(f"错误：查询升级服务状态失败 - {e}")
        return

    # 步骤3：发起固件升级
    print_step(3, "发起固件升级")
    print(f"固件文件: ftp://{FirmwareUpgradeController.FTP_USERNAME}:***@{FirmwareUpgradeController.FTP_SERVER}{FirmwareUpgradeController.FTP_FIRMWARE_PATH}")
    print(f"配置保留: Retain")
    print(f"重启模式: Auto")

    try:
        req = firmware_start_upgrade(
            DEVICE_IP,
            DEVICE_USER,
            DEVICE_PWD,
            protocol="ftp",
            preserve="Retain",
            reboot_mode="Auto",
            backup=False
        )
        response = send_redfish(req["method"], req["URL"], req["body"], token)
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)[:500]}...")

        # 解析任务ID
        try:
            response_data = json.loads(response)
            members = response_data.get("Members", [])
            if members:
                task_id = members[0].get("@odata.id", "").split("/")[-1]
                print(f"任务ID: {task_id}")
        except Exception as e:
            print(f"警告：解析任务ID失败 - {e}")
    except Exception as e:
        print(f"错误：发起固件升级失败 - {e}")
        return

    # 步骤4：监控升级进度
    print_step(4, "监控升级进度")
    print("提示：升级过程可能需要较长时间，请耐心等待...")
    print("      设备将在升级完成后自动重启")

    check_interval = 30  # 每30秒检查一次
    timeout = 1800  # 30分钟超时
    elapsed = 0

    while elapsed < timeout:
        try:
            req = firmware_get_status(DEVICE_IP, DEVICE_USER, DEVICE_PWD)
            response = send_redfish(req["method"], req["URL"], req["body"], token)

            # 解析升级状态
            try:
                status_info = firmware_parse_status(response)
                upgrade_state = status_info.get("upgrade_state")
                upgrade_progress = status_info.get("upgrade_progress")

                print(f"\n[{elapsed}秒] 升级状态: {upgrade_state}")
                if upgrade_progress:
                    print(f"        进度: {upgrade_progress}%")

                # 检查是否完成
                if firmware_is_complete(response):
                    print("\n" + "="*60)
                    if firmware_is_success(response):
                        print("✅ 固件升级成功！")
                    else:
                        print("❌ 固件升级失败！")
                    print("="*60)
                    return
            except Exception as e:
                print(f"警告：解析状态失败 - {e}")

        except Exception as e:
            print(f"警告：查询状态失败 - {e}")

        # 等待下一次检查
        time.sleep(check_interval)
        elapsed += check_interval

    # 超时
    print("\n" + "="*60)
    print("⚠️  升级超时，请手动检查设备状态")
    print("="*60)

if __name__ == "__main__":
    main()
