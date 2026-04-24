#!/usr/bin/env python3
"""
BMC固件升级 - 完全自动化工具

使用MCPServer的新工具实现固件升级的完全自动化：
1. 从FTP下载固件到PC代理
2. 上传固件到BMC设备
3. 监控升级进度

配置来源：.codebuddy/rules/SystemTest.mdc
"""

import requests
import json
import time
import sys
import os

# 添加MCPServer路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCPServer'))

# MCP服务器配置
MCP_SERVER = "http://localhost:8000"

# 从SystemTest.mdc读取的配置
PC_IP = "10.41.112.148"
DEVICE_IP = "192.168.49.71"
DEVICE_USER = "admin"
DEVICE_PWD = "Password@_"
FTP_SERVER = "10.141.228.15"
FTP_USER = "ftp-CCSPLSmart1"
FTP_PASSWORD = "X2HWrK"
FTP_FIRMWARE_PATH = "/data-out/w33199/0427/HDM3_3.05_signed.bin"
LOCAL_FIRMWARE_DIR = "C:\\firmware_upgrade"
LOCAL_FIRMWARE_NAME = "HDM3_3.05_signed.bin"


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


def firmware_download(token):
    """下载固件到PC代理"""
    print("正在调用 firmwareDownload 工具...")
    api_url = f"{MCP_SERVER}/mcp/firmwareDownload"
    payload = {
        "pcIP": PC_IP,
        "ftpServer": FTP_SERVER,
        "ftpUser": FTP_USER,
        "ftpPassword": FTP_PASSWORD,
        "firmwarePath": FTP_FIRMWARE_PATH,
        "token": token,
        "userName": "w33199",
        "localDir": LOCAL_FIRMWARE_DIR,
        "localFilename": LOCAL_FIRMWARE_NAME
    }

    try:
        response = requests.post(api_url, json=payload, timeout=300)
        result = response.json()
        print(f"下载结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    except Exception as e:
        return {"error": str(e)}


def firmware_upload(local_path, token):
    """上传固件到BMC"""
    print(f"正在调用 firmwareUpload 工具，上传 {local_path}...")
    api_url = f"{MCP_SERVER}/mcp/firmwareUpload"
    payload = {
        "pcIP": PC_IP,
        "deviceIP": DEVICE_IP,
        "deviceUser": DEVICE_USER,
        "DevicePwd": DEVICE_PWD,
        "localPath": local_path,
        "token": token,
        "userName": "w33199",
        "preserve": "Retain",
        "rebootMode": "Auto"
    }

    try:
        response = requests.post(api_url, json=payload, timeout=300)
        result = response.json()
        print(f"上传结果: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}...")
        return result
    except Exception as e:
        return {"error": str(e)}


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
        result = response.json()
        return result
    except Exception as e:
        return {"error": str(e)}


def parse_upgrade_status(status_json):
    """解析升级状态"""
    try:
        # 尝试解析Redfish响应
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
        print(f"警告：解析状态失败 - {e}")
        return None


def main():
    """主函数 - 完全自动化固件升级流程"""
    print("="*80)
    print("BMC固件升级 - 完全自动化工具")
    print("="*80)
    print(f"\n配置信息:")
    print(f"  PC代理: {PC_IP}")
    print(f"  BMC设备: {DEVICE_IP}")
    print(f"  FTP服务器: {FTP_SERVER}")
    print(f"  固件路径: {FTP_FIRMWARE_PATH}")

    # 步骤0：获取认证token
    print("\n" + "="*80)
    print("[步骤0] 获取认证token...")
    print("="*80)
    token = get_auth_token()
    if not token:
        print("❌ 错误：无法获取认证token")
        return 1

    print("✅ 认证成功")

    # 步骤1：下载固件
    print("\n" + "="*80)
    print("[步骤1] 从FTP下载固件到PC代理")
    print("="*80)
    result = firmware_download(token)

    if "error" in result or not result.get("success", False):
        print("❌ 固件下载失败")
        return 1

    local_firmware_path = result.get("local_path", "")
    file_size = result.get("file_size", 0)
    print(f"✅ 固件下载成功")
    print(f"   本地路径: {local_firmware_path}")
    print(f"   文件大小: {file_size} bytes ({file_size/1024/1024:.2f} MB)")

    if file_size == 0:
        print("❌ 错误：下载的文件大小为0")
        return 1

    # 步骤2：上传固件到BMC
    print("\n" + "="*80)
    print("[步骤2] 上传固件到BMC（配置保留，自动重启）")
    print("="*80)
    result = firmware_upload(local_firmware_path, token)

    if "error" in result or not result.get("success", False):
        print("❌ 固件上传失败")
        return 1

    print("✅ 固件上传成功，升级已启动")

    # 步骤3：监控升级进度
    print("\n" + "="*80)
    print("[步骤3] 监控升级进度")
    print("="*80)
    print("升级可能需要较长时间，请耐心等待...\n")

    check_interval = 30  # 每30秒检查一次
    timeout = 1800       # 30分钟超时
    elapsed = 0

    while elapsed < timeout:
        print(f"[{elapsed}秒] 查询升级状态...")
        result = firmware_status(token)

        if "error" not in result:
            status_info = parse_upgrade_status(result)
            if status_info:
                upgrade_state = status_info["state"]
                upgrade_progress = status_info["progress"]
                upgrade_message = status_info["message"]

                status_text = f"升级状态: {upgrade_state}"
                if upgrade_progress is not None:
                    status_text += f", 进度: {upgrade_progress}%"
                if upgrade_message:
                    status_text += f", 消息: {upgrade_message}"

                print(f"         {status_text}")

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
            print(f"         警告：查询状态失败 - {result.get('error')}")

        time.sleep(check_interval)
        elapsed += check_interval

    print("\n" + "="*80)
    print("⚠️  升级超时")
    print("="*80)
    return 1


if __name__ == "__main__":
    sys.exit(main())
