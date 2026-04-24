---
name: firmware-upgrade
description: BMC设备固件升级技能。支持通过Redfish或IPMI命令对H3C BMC设备进行固件升级，支持从FTP/TFTP/HTTP/HTTPS/SFTP等协议下载固件文件。触发词：固件升级、firmware upgrade、升级固件、update firmware。
metadata:
  version: "0.0.1"
---

# Firmware Upgrade Skill

BMC设备固件升级技能。支持通过Redfish或IPMI命令对H3C BMC设备进行固件升级。

## 功能

- **Redfish固件升级** - 通过Redfish API进行固件升级
- **IPMI固件升级** - 通过IPMI命令进行固件升级
- **多协议支持** - 支持FTP、TFTP、HTTP、HTTPS、SFTP等协议
- **升级状态查询** - 实时查询升级进度和状态
- **固件清单查询** - 查看当前固件版本和可用升级包

## 工作流程

### Redfish固件升级

#### 1. 查询升级服务信息
```
GET https://{device_ip}/redfish/v1/UpdateService
```

#### 2. 发起固件升级
使用`UpdateService.SimpleUpdate`接口：

**支持的协议格式：**
- HTTP/HTTPS: `http://IP/image.bin` 或 `https://IP/image.bin`
- TFTP: `tftp://IP/image.bin`
- FTP: `ftp://username:password@IP/image.bin`
- SFTP: `sftp://username:password@IP/image.bin`
- NFS: `nfs://IP/path/image.bin`

**请求示例：**
```json
POST https://{device_ip}/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate

{
  "ImageURI": "ftp://ftp-CCSPLSmart:G7h253@10.141.228.15/data-out/w33199/0427/HDM3_3.05_signed.bin",
  "Oem": {
    "Public": {
      "Preserve": "Retain",
      "RebootMode": "Auto"
    }
  }
}
```

**参数说明：**
- `ImageURI`: 固件文件URI（必需）
- `Oem.Public.Preserve`: 配置保留策略
  - `Retain`: 配置保留（默认）
  - `Restore`: 配置覆盖
  - `ForceRestore`: 强制覆盖
- `Oem.Public.RebootMode`: 重启模式
  - `Auto`: 立即重启（默认）
  - `Manual`: 手动重启
- `Oem.Public.Backup`: 是否备份配置
  - `true`: 备份
  - `false`: 不备份
- `Oem.Public.UpgradeType`: 升级类型（BIOS相关）
  - `all`: 更新BIOS+ME
  - `bios`: 仅更新BIOS
  - `me`: 仅更新ME

#### 3. 查询升级状态
```
GET https://{device_ip}/redfish/v1/UpdateService
```

查看`Oem.Public.UpgradeState`字段：
- `null`: 无升级任务
- `Upgrading`: 升级中
- `Success`: 升级成功
- `Failed`: 升级失败

#### 4. 查询任务详情
```
GET https://{device_ip}/redfish/v1/TaskService/Tasks/{task_id}
```

### IPMI固件升级

使用IPMI命令进行固件升级：

```bash
# 通过PC代理发送IPMI命令
ipmitool -H {device_ip} -U {username} -P {password} raw 0x32 0xXX ...
```

**注意：** IPMI固件升级命令较为复杂，建议优先使用Redfish接口。

## 配置

### 设备连接信息
从 `.codebuddy/rules/SystemTest.mdc` 读取设备连接信息，不允许硬编码IP地址。

### 固件升级配置
从 `.codebuddy/rules/SystemTest.mdc` 读取固件升级配置，包括：
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
- 完整固件URI：ftp://ftp-CCSPLSmart:G7h253@10.141.228.15/data-out/w33199/0427/HDM3_3.05_signed.bin
```

### PC代理配置
从 `.codebuddy/rules/SystemTest.mdc` 读取PC代理配置：
- PC代理IP：`10.41.112.148`
- PC代理端口：`8888`
- PC代理可以访问FTP服务器

## MCP工具调用

### 使用sendRedfish工具
```python
# 查询升级服务
sendRedfish(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    method="GET",
    URL="/redfish/v1/UpdateService",
    body="",
    token="your_token",
    userName="w33199"
)

# 发起固件升级
sendRedfish(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    method="POST",
    URL="/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate",
    body='{"ImageURI":"ftp://ftp-CCSPLSmart:G7h253@10.141.228.15/data-out/w33199/0427/HDM3_3.05_signed.bin","Oem":{"Public":{"Preserve":"Retain","RebootMode":"Auto"}}}',
    token="your_token",
    userName="w33199"
)
```

### 使用sendIPMI工具
```python
sendIPMI(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    command="raw 0x32 0xXX ...",
    token="your_token",
    userName="w33199"
)
```

## 使用示例

### 示例1：Redfish固件升级
```python
# 1. 查询当前固件版本
result = sendRedfish(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    method="GET",
    URL="/redfish/v1/UpdateService/FirmwareInventory",
    body="",
    token="your_token",
    userName="w33199"
)

# 2. 发起固件升级
result = sendRedfish(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    method="POST",
    URL="/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate",
    body='{"ImageURI":"ftp://ftp-CCSPLSmart:G7h253@10.141.228.15/data-out/w33199/0427/HDM3_3.05_signed.bin","Oem":{"Public":{"Preserve":"Retain","RebootMode":"Auto"}}}',
    token="your_token",
    userName="w33199"
)

# 3. 查询升级状态
while True:
    result = sendRedfish(
        pcIP="10.41.112.148",
        deviceIP="192.168.49.71",
        deviceUser="admin",
        DevicePwd="Password@_",
        method="GET",
        URL="/redfish/v1/UpdateService",
        body="",
        token="your_token",
        userName="w33199"
    )
    state = result.get("Oem", {}).get("Public", {}).get("UpgradeState")
    if state == "Success":
        print("升级成功")
        break
    elif state == "Failed":
        print("升级失败")
        break
    time.sleep(10)
```

### 示例2：查询固件清单
```python
result = sendRedfish(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    method="GET",
    URL="/redfish/v1/UpdateService/FirmwareInventory",
    body="",
    token="your_token",
    userName="w33199"
)
```

## 重要注意事项

### 升级前准备
1. 确认固件文件已上传到FTP服务器
2. 确认设备网络连接正常
3. 确认设备有足够的电源供应
4. 建议在升级前备份重要配置

### 升级过程
1. 升级过程中不要断电
2. 升级过程中不要重启设备
3. 升级时间可能较长，请耐心等待
4. 升级完成后设备会自动重启（Auto模式）或需要手动重启（Manual模式）

### 升级后验证
1. 查询固件版本确认升级成功
2. 检查设备功能是否正常
3. 查看升级日志确认无错误

### 系统锁定
固件升级会触发系统锁定：
- 固件版本锁定
- BIOS配置锁定（BIOS升级时）
- BMC配置锁定（BMC升级时）

## 依赖

- MCP服务器连接（SWRDMCPServer）
- PC代理服务（端口8888）
- FTP服务器访问权限
- 设备管理权限

## 参考文档

- H3C HDM2&HDM3 Redfish参考手册
- H3C HDM3 IPMI基础命令参考手册
