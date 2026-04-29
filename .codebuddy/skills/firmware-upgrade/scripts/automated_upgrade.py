#!/usr/bin/env python3
"""
BMC固件升级 - 完全自动化工具

使用MCPServer的工具实现固件升级的完全自动化：
1. 从FTP下载固件到PC代理
2. 启动TFTP服务器
3. 通过Redfish SimpleUpdate接口使用TFTP协议上传固件
4. 监控升级进度

配置来源：.codebuddy/rules/SystemTest.mdc
"""

import requests
import json
import time
import sys
import os
import re

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
LOCAL_FIRMWARE_DIR = r"C:\firmware_upgrade"


def read_systemtest_config():
    """从SystemTest.mdc读取固件升级配置"""
    # 获取项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 向上四级到项目根目录
    project_root = os.path.normpath(os.path.join(current_dir, '..', '..', '..', '..'))
    config_path = os.path.join(project_root, '.codebuddy', 'rules', 'SystemTest.mdc')

    print(f"当前目录: {current_dir}")
    print(f"项目根目录: {project_root}")
    print(f"配置文件路径: {config_path}")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析固件文件路径
        firmware_path_match = re.search(r'固件文件路径：([^\n]+)', content)
        if firmware_path_match:
            firmware_path = firmware_path_match.group(1).strip()
            # 从路径中提取文件名
            filename = os.path.basename(firmware_path)
            return firmware_path, filename
        else:
            print("错误：无法从SystemTest.mdc中解析固件文件路径")
            return None, None
    except Exception as e:
        print(f"错误：读取SystemTest.mdc失败 - {e}")
        return None, None


# 从SystemTest.mdc读取固件配置
FTP_FIRMWARE_PATH, LOCAL_FIRMWARE_NAME = read_systemtest_config()

if not FTP_FIRMWARE_PATH or not LOCAL_FIRMWARE_NAME:
    print("错误：无法获取固件配置，请检查SystemTest.mdc文件")
    sys.exit(1)


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


def firmware_download():
    """下载固件到PC代理"""
    print("正在调用PC代理下载固件...")
    api_url = f"http://{PC_IP}:8888/firmware/download"
    payload = {
        "ftpServer": FTP_SERVER,
        "ftpUser": FTP_USER,
        "ftpPassword": FTP_PASSWORD,
        "firmwarePath": FTP_FIRMWARE_PATH,
        "localDir": LOCAL_FIRMWARE_DIR,
        "localFilename": LOCAL_FIRMWARE_NAME
    }

    try:
        response = requests.post(api_url, json=payload, timeout=300)
        result = response.json()
        print(f"下载结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    except Exception as e:
        print(f"错误：下载固件失败 - {e}")
        return {"error": str(e)}


def start_tftp_server():
    """启动TFTP服务器"""
    print("正在启动TFTP服务器...")
    api_url = f"http://{PC_IP}:8888/tftp/start"
    local_firmware_path = os.path.join(LOCAL_FIRMWARE_DIR, LOCAL_FIRMWARE_NAME)
    payload = {
        "localPath": local_firmware_path,
        "tftpFilename": LOCAL_FIRMWARE_NAME
    }

    try:
        response = requests.post(api_url, json=payload, timeout=60)
        result = response.json()
        print(f"TFTP服务器启动结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    except Exception as e:
        print(f"错误：启动TFTP服务器失败 - {e}")
        return {"error": str(e)}


def stop_tftp_server():
    """停止TFTP服务器"""
    print("正在停止TFTP服务器...")
    api_url = f"http://{PC_IP}:8888/tftp/stop"

    try:
        response = requests.post(api_url, timeout=30)
        result = response.json()
        print(f"TFTP服务器停止结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    except Exception as e:
        print(f"警告：停止TFTP服务器失败 - {e}")
        return {"error": str(e)}


def firmware_upgrade_via_tftp():
    """通过TFTP协议进行固件升级"""
    print("正在通过Redfish SimpleUpdate接口发起固件升级...")
    api_url = f"http://{PC_IP}:8888/redfish"
    
    # 构建TFTP URI（使用PC代理的设备网IP）
    tftp_uri = f"tftp://192.168.33.199/{LOCAL_FIRMWARE_NAME}"
    
    # 构建Redfish请求体
    redfish_body = {
        "deviceIP": DEVICE_IP,
        "deviceUser": DEVICE_USER,
        "devicePwd": DEVICE_PWD,
        "method": "POST",
        "url": "/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate",
        "body": json.dumps({
            "ImageURI": tftp_uri,
            "Oem": {
                "Public": {
                    "Preserve": "Retain",
                    "RebootMode": "Auto"
                }
            }
        })
    }

    try:
        response = requests.post(api_url, json=redfish_body, timeout=120)
        result = response.json()
        print(f"升级请求结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    except Exception as e:
        print(f"错误：发起升级请求失败 - {e}")
        return {"error": str(e)}


def firmware_status():
    """查询升级状态"""
    api_url = f"http://{PC_IP}:8888/redfish"
    payload = {
        "deviceIP": DEVICE_IP,
        "deviceUser": DEVICE_USER,
        "devicePwd": DEVICE_PWD,
        "method": "GET",
        "url": "/redfish/v1/UpdateService",
        "body": ""
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
    print("BMC固件升级 - 完全自动化工具 (TFTP协议)")
    print("="*80)
    print(f"\n配置信息:")
    print(f"  PC代理: {PC_IP}")
    print(f"  BMC设备: {DEVICE_IP}")
    print(f"  FTP服务器: {FTP_SERVER}")
    print(f"  固件路径: {FTP_FIRMWARE_PATH}")
    print(f"  本地文件: {LOCAL_FIRMWARE_NAME}")

    # 步骤1：下载固件
    print("\n" + "="*80)
    print("[步骤1] 从FTP下载固件到PC代理")
    print("="*80)
    result = firmware_download()

    if "error" in result or not result.get("success", False):
        print("错误：固件下载失败")
        return 1

    local_firmware_path = result.get("local_path", "")
    file_size = result.get("file_size", 0)
    print(f"固件下载成功")
    print(f"  本地路径: {local_firmware_path}")
    print(f"  文件大小: {file_size} bytes ({file_size/1024/1024:.2f} MB)")

    if file_size == 0:
        print("错误：下载的文件大小为0")
        return 1

    # 步骤2：启动TFTP服务器
    print("\n" + "="*80)
    print("[步骤2] 启动TFTP服务器")
    print("="*80)
    result = start_tftp_server()

    if "error" in result or not result.get("success", False):
        print("错误：启动TFTP服务器失败")
        return 1

    print("TFTP服务器启动成功")
    print(f"  TFTP地址: tftp://192.168.33.199/{LOCAL_FIRMWARE_NAME}")

    # 步骤3：通过TFTP协议进行固件升级
    print("\n" + "="*80)
    print("[步骤3] 通过Redfish SimpleUpdate接口发起固件升级")
    print("="*80)
    result = firmware_upgrade_via_tftp()

    if "error" in result:
        print(f"错误：发起升级请求失败 - {result.get('error')}")
        # 停止TFTP服务器
        stop_tftp_server()
        return 1

    # 检查响应状态码
    status_code = result.get("status_code", 0)
    if status_code not in [200, 202]:
        print(f"错误：升级请求返回错误状态码 {status_code}")
        print(f"响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
        # 停止TFTP服务器
        stop_tftp_server()
        return 1

    print("固件升级请求已成功发送")

    # 步骤4：监控升级进度
    print("\n" + "="*80)
    print("[步骤4] 监控升级进度")
    print("="*80)
    print("升级可能需要较长时间，请耐心等待...\n")

    check_interval = 30  # 每30秒检查一次
    timeout = 1800       # 30分钟超时
    elapsed = 0

    while elapsed < timeout:
        print(f"[{elapsed}秒] 查询升级状态...")
        result = firmware_status()

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
                        print("固件升级成功！")
                    elif upgrade_state == "Failed":
                        print("固件升级失败！")
                    else:
                        print("固件升级完成！")
                    print("="*80)
                    # 停止TFTP服务器
                    stop_tftp_server()
                    return 0
        else:
            print(f"         警告：查询状态失败 - {result.get('error')}")

        time.sleep(check_interval)
        elapsed += check_interval

    print("\n" + "="*80)
    print("警告：升级超时")
    print("="*80)
    # 停止TFTP服务器
    stop_tftp_server()
    return 1


if __name__ == "__main__":
    sys.exit(main())
