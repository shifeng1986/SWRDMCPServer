# Firmware Upgrade Skill

BMC设备固件升级技能，支持通过Redfish或IPMI命令对H3C BMC设备进行固件升级。

## 功能特性

- ✅ 支持Redfish接口进行固件升级
- ✅ 支持FTP、TFTP、HTTP、HTTPS、SFTP、NFS等多种协议
- ✅ 实时查询升级进度和状态
- ✅ 自动监控升级过程
- ✅ 配置保留和备份选项
- ✅ 自动/手动重启模式选择

## 文件结构

```
firmware-upgrade/
├── SKILL.md              # 技能说明文档
├── README.md             # 使用说明
└── scripts/
    ├── firmware_upgrade.py   # 核心实现
    └── example_upgrade.py    # 使用示例
```

## 快速开始

### 1. 查询当前固件版本

```python
from firmware_upgrade import firmware_get_inventory

req = firmware_get_inventory(
    device_ip="192.168.49.71",
    username="admin",
    password="Password@_"
)

# 通过MCP发送请求
response = sendRedfish(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    method=req["method"],
    URL=req["URL"],
    body=req["body"],
    token="your_token",
    userName="w33199"
)
```

### 2. 发起固件升级

```python
from firmware_upgrade import firmware_start_upgrade

# 使用默认FTP服务器
req = firmware_start_upgrade(
    device_ip="192.168.49.71",
    username="admin",
    password="Password@_",
    protocol="ftp",
    preserve="Retain",  # 配置保留
    reboot_mode="Auto",  # 自动重启
    backup=False  # 不备份
)

# 发送升级请求
response = sendRedfish(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    method=req["method"],
    URL=req["URL"],
    body=req["body"],
    token="your_token",
    userName="w33199"
)
```

### 3. 监控升级进度

```python
from firmware_upgrade import (
    firmware_get_status,
    firmware_parse_status,
    firmware_is_complete,
    firmware_is_success
)

import time

while True:
    # 查询升级状态
    req = firmware_get_status(device_ip, username, password)
    response = sendRedfish(...)

    # 解析状态
    status_info = firmware_parse_status(response)
    print(f"升级状态: {status_info['upgrade_state']}")

    # 检查是否完成
    if firmware_is_complete(response):
        if firmware_is_success(response):
            print("升级成功！")
        else:
            print("升级失败！")
        break

    time.sleep(30)  # 每30秒检查一次
```

## 完整示例

运行示例脚本：

```bash
cd .codebuddy/skills/firmware-upgrade/scripts
python example_upgrade.py
```

## 参数说明

### 固件升级参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `image_uri` | str | None | 固件文件URI，为None时使用默认FTP路径 |
| `protocol` | str | "ftp" | 协议类型：ftp, tftp, http, https, sftp, nfs |
| `preserve` | str | "Retain" | 配置保留策略：Retain(保留), Restore(覆盖), ForceRestore(强制覆盖) |
| `reboot_mode` | str | "Auto" | 重启模式：Auto(自动), Manual(手动) |
| `backup` | bool | False | 是否备份配置 |

### 升级状态

| 状态 | 说明 |
|------|------|
| `null` | 无升级任务 |
| `Upgrading` | 升级中 |
| `Success` | 升级成功 |
| `Failed` | 升级失败 |

## FTP服务器配置

固件升级配置从 `.codebuddy/rules/SystemTest.mdc` 读取，包括：
- FTP服务器地址
- FTP用户名和密码
- 固件文件路径

**SystemTest.mdc配置示例：**
```markdown
## 固件升级配置
- FTP服务器地址：10.141.228.15
- FTP用户名：ftp-CCSPLSmart
- FTP密码：G7h253
- 固件文件路径：/data-out/w33199/0427/HDM3_3.05_signed.bin
```

**使用配置：**
```python
from firmware_upgrade import load_system_test_config

# 加载配置
config = load_system_test_config()

# 访问配置
print(f"FTP服务器: {config['ftp_server']}")
print(f"固件路径: {config['firmware_path']}")

# 使用FirmwareUpgradeController会自动加载配置
controller = FirmwareUpgradeController(device_ip, username, password)
print(f"固件URI: {controller.firmware_uri}")
```

## 注意事项

### 升级前
1. ✅ 确认固件文件已上传到FTP服务器
2. ✅ 确认设备网络连接正常
3. ✅ 确认设备有足够的电源供应
4. ✅ 建议备份重要配置

### 升级中
1. ⚠️ 不要断电
2. ⚠️ 不要重启设备
3. ⚠️ 耐心等待升级完成
4. ⚠️ 升级时间可能较长

### 升级后
1. ✅ 验证固件版本
2. ✅ 检查设备功能
3. ✅ 查看升级日志

## 系统锁定

固件升级会触发以下系统锁定：
- 固件版本锁定
- BIOS配置锁定（BIOS升级时）
- BMC配置锁定（BMC升级时）

## MCP工具调用

### sendRedfish工具

```python
sendRedfish(
    pcIP="10.41.112.148",        # PC代理IP
    deviceIP="192.168.49.71",    # 设备IP
    deviceUser="admin",          # 设备用户名
    DevicePwd="Password@_",      # 设备密码
    method="POST",               # HTTP方法
    URL="/redfish/v1/...",      # Redfish路径
    body='{"key":"value"}',      # 请求体
    token="your_token",          # 认证token
    userName="w33199"            # 操作用户名
)
```

### sendIPMI工具

```python
sendIPMI(
    pcIP="10.41.112.148",        # PC代理IP
    deviceIP="192.168.49.71",    # 设备IP
    deviceUser="admin",          # 设备用户名
    DevicePwd="Password@_",      # 设备密码
    command="raw 0x32 0xXX ...", # IPMI命令
    token="your_token",          # 认证token
    userName="w33199"            # 操作用户名
)
```

## 故障排查

### 问题1：无法连接FTP服务器
- 检查PC代理是否可以访问FTP服务器
- 检查FTP账号密码是否正确
- 检查固件文件路径是否正确

### 问题2：升级失败
- 检查固件文件是否完整
- 检查固件版本是否兼容
- 查看升级日志获取错误信息

### 问题3：升级卡住
- 检查网络连接是否稳定
- 增加超时时间
- 手动重启设备后重试

## 参考文档

- [H3C HDM2&HDM3 Redfish参考手册](../system-test/references/H3C%20HDM2&HDM3%20Redfish%E5%8F%82%E8%80%83%E6%89%8B%E5%86%8C.md)
- [H3C HDM3 IPMI基础命令参考手册](../system-test/references/H3C%20HDM3%20IPMI%E5%9F%BA%E7%A1%80%E5%91%BD%E4%BB%A4%E5%8F%82%E8%80%83%E6%89%8B%E5%86%8C.md)

## 许可证

本技能遵循项目许可证。
