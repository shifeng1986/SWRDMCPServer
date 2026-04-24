#!/usr/bin/env python3
"""
BMC固件升级 - 智能监控工具

优化升级监控策略，减少不必要的查询：
- 前2分钟：每60秒检查一次（快速验证升级是否启动）
- 2-10分钟：每120秒检查一次（正常监控）
- 10分钟后：每180秒检查一次（降低查询频率）
- 只在状态或进度变化时打印信息
"""

import requests
import json
import time
import sys

# MCP服务器配置
MCP_SERVER = "http://localhost:8000"

# 从SystemTest.mdc读取的配置
PC_IP = "10.41.112.148"
DEVICE_IP = "192.168.49.71"
DEVICE_USER = "admin"
DEVICE_PWD = "Password@_"


def get_auth_token(username="admin", password="admin123"):
    """获取认证token"""
    url = f"{MCP_SERVER}/auth/token"
    payload = {
        "username": username,
        "password": password
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if data.get("status") == "success":
            return data.get("token")
        return None
    except Exception as e:
        print(f"错误：获取认证token失败 - {e}")
        return None


def firmware_status(token):
    """查询升级状态"""
    api_url = f"{MCP_SERVER}/mcp/firmwareStatus"
    payload = {
        "pcIP": PC_IP,
        "deviceIP": DEVICE_IP,
        "deviceUser": DEVICE_USER,
        "DevicePwd": DEVICE_PWD,
        "token": token,
        "userName": "w33199"
    }

    try:
        response = requests.post(api_url, json=payload, timeout=60)
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def parse_upgrade_status(status_json):
    """解析升级状态"""
    try:
        if isinstance(status_json, dict):
            data = status_json
        else:
            data = json.loads(status_json)

        # 查找Oem.Public.UpgradeState字段
        oem = data.get("Oem", {})
        public = oem.get("Public", {})
        upgrade_state = public.get("UpgradeState")
        upgrade_progress = public.get("UpgradeProgress")
        upgrade_message = public.get("UpgradeMessage", "")

        return {
            "state": upgrade_state,
            "progress": upgrade_progress,
            "message": upgrade_message
        }
    except Exception as e:
        return None


def main():
    """主函数 - 智能监控升级进度"""
    print("="*80)
    print("BMC固件升级 - 智能监控工具")
    print("="*80)

    # 获取认证token
    print("\n获取认证token...")
    token = get_auth_token()
    if not token:
        print("❌ 错误：无法获取认证token")
        return 1

    print("✅ 认证成功")

    # 智能监控策略
    print("\n" + "="*80)
    print("开始智能监控升级进度")
    print("="*80)
    print("监控策略：")
    print("  - 前2分钟：每60秒检查一次")
    print("  - 2-10分钟：每120秒检查一次")
    print("  - 10分钟后：每180秒检查一次")
    print("  - 只在状态或进度变化时打印信息")
    print("  - 超时时间：30分钟\n")

    timeout = 1800  # 30分钟超时
    elapsed = 0
    last_state = None
    last_progress = None

    while elapsed < timeout:
        # 确定当前检查间隔
        if elapsed < 120:
            check_interval = 60   # 前2分钟：每60秒
        elif elapsed < 600:
            check_interval = 120  # 2-10分钟：每120秒
        else:
            check_interval = 180  # 10分钟后：每180秒

        result = firmware_status(token)

        if "error" not in result:
            status_info = parse_upgrade_status(result)
            if status_info:
                upgrade_state = status_info["state"]
                upgrade_progress = status_info["progress"]
                upgrade_message = status_info["message"]

                # 只在状态或进度变化时打印信息
                if (upgrade_state != last_state or 
                    (upgrade_progress is not None and upgrade_progress != last_progress)):
                    
                    status_text = f"[{elapsed}秒] 升级状态: {upgrade_state}"
                    if upgrade_progress is not None:
                        status_text += f", 进度: {upgrade_progress}%"
                    if upgrade_message:
                        status_text += f", 消息: {upgrade_message}"

                    print(status_text)

                    # 更新上次状态
                    last_state = upgrade_state
                    last_progress = upgrade_progress

                # 检查是否完成
                if upgrade_state in ["Success", "Failed", None]:
                    print("\n" + "="*80)
                    if upgrade_state == "Success":
                        print("✅ 固件升级成功！")
                    elif upgrade_state == "Failed":
                        print("❌ 固件升级失败！")
                    else:
                        print("✅ 固件升级完成！")
                    print("="*80)
                    return 0
        else:
            print(f"[{elapsed}秒] 警告：查询状态失败 - {result.get('error')}")

        # 等待下一次检查
        print(f"等待 {check_interval} 秒后检查进度...")
        time.sleep(check_interval)
        elapsed += check_interval

    print("\n" + "="*80)
    print("⚠️  升级超时")
    print("="*80)
    return 1


if __name__ == "__main__":
    sys.exit(main())
