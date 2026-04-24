#!/usr/bin/env python3
"""
测试配置读取功能

验证从SystemTest.mdc读取配置是否正常
"""

import sys
import os

# 添加skill路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from firmware_upgrade import (
    load_system_test_config,
    FirmwareUpgradeController
)

def test_load_config():
    """测试配置加载"""
    print("="*60)
    print("测试配置加载")
    print("="*60)

    # 加载配置
    config = load_system_test_config()

    print("\n[配置信息]")
    print(f"PC代理IP: {config['pc_ip']}")
    print(f"设备IP: {config['device_ip']}")
    print(f"设备用户名: {config['device_user']}")
    print(f"设备密码: {config['device_password']}")
    print(f"FTP服务器: {config['ftp_server']}")
    print(f"FTP用户名: {config['ftp_username']}")
    print(f"FTP密码: {config['ftp_password']}")
    print(f"固件路径: {config['firmware_path']}")

    return config

def test_controller():
    """测试控制器"""
    print("\n" + "="*60)
    print("测试FirmwareUpgradeController")
    print("="*60)

    config = load_system_test_config()
    controller = FirmwareUpgradeController(
        config['device_ip'],
        config['device_user'],
        config['device_password']
    )

    print("\n[控制器属性]")
    print(f"设备IP: {controller.device_ip}")
    print(f"基础URL: {controller.base_url}")
    print(f"FTP服务器: {controller.ftp_server}")
    print(f"FTP用户名: {controller.ftp_username}")
    print(f"固件路径: {controller.firmware_path}")
    print(f"固件URI: {controller.firmware_uri}")

    return controller

def test_upgrade_request():
    """测试升级请求生成"""
    print("\n" + "="*60)
    print("测试升级请求生成")
    print("="*60)

    config = load_system_test_config()
    controller = FirmwareUpgradeController(
        config['device_ip'],
        config['device_user'],
        config['device_password']
    )

    # 生成升级请求
    req = controller.start_firmware_upgrade()

    print("\n[升级请求]")
    print(f"方法: {req['method']}")
    print(f"URL: {req['URL']}")
    print(f"请求体: {req['body'][:200]}...")

    return req

def main():
    """主函数"""
    print("\n" + "="*60)
    print("BMC固件升级 - 配置测试")
    print("="*60)

    try:
        # 测试配置加载
        config = test_load_config()

        # 测试控制器
        controller = test_controller()

        # 测试升级请求
        req = test_upgrade_request()

        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60)

    except Exception as e:
        print("\n" + "="*60)
        print(f"❌ 测试失败: {e}")
        print("="*60)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
