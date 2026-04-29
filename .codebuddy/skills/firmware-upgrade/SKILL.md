---
name: firmware-upgrade
description: BMC设备固件升级技能。支持通过Redfish对H3C BMC设备进行固件升级，支持从FTP/TFTP/HTTP/HTTPS/SFTP等协议上传固件。触发词：固件升级、firmware upgrade、升级固件、update firmware。
metadata:
  version: "0.0.1"
---

# Firmware Upgrade Skill

BMC设备固件升级技能。此技能利用SWRDMCPServer控制PC代理对H3C BMC设备进行固件升级。

## 功能

- **Redfish固件升级** - 通过Redfish API进行固件升级
- **多协议支持** - 支持FTP、TFTP、HTTP、HTTPS、SFTP等协议，优先使用tftp
- **升级状态查询** - 实时查询升级进度和状态
- **固件清单查询** - 查看当前固件版本和可用升级包

## 工作流程

### 网络架构说明

**重要：BMC设备网络隔离**

```
┌─────────────────────────────────────────────────────────┐
│                    大网 (10.41.x.x)                      │
│                                                          │
│  ┌──────────────┐         ┌──────────────┐              │
│  │ FTP服务器    │         │ PC代理       │              │
│  │ 10.141.228.15│         │ 10.41.112.148│              │
│  └──────────────┘         └──────┬───────┘              │
│                                  │                       │
└──────────────────────────────────┼───────────────────────┘
                                   │ 网络隔离
                                   │
┌──────────────────────────────────┼───────────────────────┐
│                                  │                       │
│                           ┌──────▼───────┐              │
│                           │ PC代理       │              │
│                           │ 192.168.33.199│             │
│                           └──────┬───────┘              │
│                                  │                       │
│                         小网 (192.168.x.x)              │
│                                  │                       │
│                           ┌──────▼───────┐              │
│                           │ BMC设备      │              │
│                           │ 192.168.49.71│              │
│                           └──────────────┘              │
└─────────────────────────────────────────────────────────┘

❌ BMC设备无法访问FTP服务器 (10.141.228.15)
✅ BMC设备只能访问小网中的PC代理 (192.168.33.199)
✅ PC代理可以访问大网和小网，作为网关
```

### TFTP固件升级流程（推荐）

由于BMC设备无法直接访问大网的FTP服务器，必须使用TFTP方式进行固件升级。

#### 步骤1：查询当前固件版本
```bash
curl -X POST http://{pc_ip}:8888/redfish \
  -H "Content-Type: application/json" \
  -d '{
    "deviceIP":"{device_ip}",
    "deviceUser":"{device_user}",
    "devicePwd":"{device_pwd}",
    "method":"GET",
    "url":"/redfish/v1/UpdateService/FirmwareInventory/BMC",
    "body":""
  }'
```

#### 步骤2：从FTP服务器下载固件到PC本地
```bash
curl -X POST http://{pc_ip}:8888/firmware/download \
  -H "Content-Type: application/json" \
  -d '{
    "ftpServer":"{ftp_server}",
    "ftpUser":"{ftp_user}",
    "ftpPassword":"{ftp_password}",
    "firmwarePath":"{firmware_path}",
    "localDir":"C:\\firmware_upgrade",
    "localFilename":"{firmware_filename}"
  }'
```

**传输路径：** FTP服务器（大网）→ PC代理本地

#### 步骤3：启动TFTP服务器
```bash
curl -X POST http://{pc_ip}:8888/firmware/tftp/start \
  -H "Content-Type: application/json" \
  -d '{}'
```

**作用：** 在PC代理上启动TFTP服务器，监听设备网IP (192.168.33.199:69)

#### 步骤4：通过TFTP发起固件升级
```bash
curl -X POST http://{pc_ip}:8888/redfish \
  -H "Content-Type: application/json" \
  -d '{
    "deviceIP":"{device_ip}",
    "deviceUser":"{device_user}",
    "devicePwd":"{device_pwd}",
    "method":"POST",
    "url":"/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate",
    "body":"{\"ImageURI\":\"tftp://192.168.33.199/{firmware_filename}\",\"Oem\":{\"Public\":{\"Preserve\":\"Retain\",\"RebootMode\":\"Auto\"}}}"
  }'
```

**传输路径：** PC代理 TFTP服务器 → BMC设备

**实际执行的Redfish请求：**
```json
{
  "ImageURI": "tftp://192.168.33.199/HDM3_3.05.01_FTC_signed.bin",
  "Oem": {
    "Public": {
      "Preserve": "Retain",
      "RebootMode": "Auto"
    }
  }
}
```

#### 步骤5：查询升级状态
```bash
curl -X POST http://{pc_ip}:8888/redfish \
  -H "Content-Type: application/json" \
  -d '{
    "deviceIP":"{device_ip}",
    "deviceUser":"{device_user}",
    "devicePwd":"{device_pwd}",
    "method":"GET",
    "url":"/redfish/v1/UpdateService",
    "body":""
  }'
```

查看`Oem.Public.UpgradeState`字段：
- `null`: 无升级任务
- `Upgrading`: 升级中
- `Success`: 升级成功
- `Failed`: 升级失败

#### 步骤6：验证升级结果
```bash
curl -X POST http://{pc_ip}:8888/redfish \
  -H "Content-Type: application/json" \
  -d '{
    "deviceIP":"{device_ip}",
    "deviceUser":"{device_user}",
    "devicePwd":"{device_pwd}",
    "method":"GET",
    "url":"/redfish/v1/UpdateService/FirmwareInventory/BMC",
    "body":""
  }'
```

### Redfish固件升级（直接方式）

**注意：** 由于网络隔离，BMC设备无法直接访问大网的FTP服务器，以下方式仅在网络允许的情况下使用。

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

### TFTP固件升级完整流程

```python
# 配置参数（从SystemTest.mdc读取）
pc_ip = "10.41.112.148"  # PC代理大网IP
pc_ip_device = "192.168.33.199"  # PC代理设备网IP
device_ip = "192.168.49.71"  # BMC设备IP
device_user = "admin"
device_pwd = "Password@_"
ftp_server = "10.141.228.15"
ftp_user = "ftp-CCSPLSmart1"
ftp_password = "X2HWrK"
firmware_path = "/data-out/w33199/0428/HDM3_3.05.01_FTC_signed.bin"
firmware_filename = "HDM3_3.05.01_FTC_signed.bin"

# 步骤1：查询当前固件版本
result = sendRedfish(
    pcIP=pc_ip,
    deviceIP=device_ip,
    deviceUser=device_user,
    DevicePwd=device_pwd,
    method="GET",
    URL="/redfish/v1/UpdateService/FirmwareInventory/BMC",
    body="",
    token="your_token",
    userName="w33199"
)
print(f"当前固件版本: {result['Version']}")

# 步骤2：从FTP服务器下载固件到PC本地
result = requests.post(
    f"http://{pc_ip}:8888/firmware/download",
    json={
        "ftpServer": ftp_server,
        "ftpUser": ftp_user,
        "ftpPassword": ftp_password,
        "firmwarePath": firmware_path,
        "localDir": "C:\\firmware_upgrade",
        "localFilename": firmware_filename
    }
)
print(f"固件下载: {result.json()['success']}")

# 步骤3：启动TFTP服务器
result = requests.post(
    f"http://{pc_ip}:8888/firmware/tftp/start",
    json={}
)
print(f"TFTP服务器: {result.json()['message']}")

# 步骤4：通过TFTP发起固件升级
result = sendRedfish(
    pcIP=pc_ip,
    deviceIP=device_ip,
    deviceUser=device_user,
    DevicePwd=device_pwd,
    method="POST",
    URL="/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate",
    body=f'{{"ImageURI":"tftp://{pc_ip_device}/{firmware_filename}","Oem":{{"Public":{{"Preserve":"Retain","RebootMode":"Auto"}}}}}}',
    token="your_token",
    userName="w33199"
)
print(f"升级请求: {result}")

# 步骤5：查询升级状态
while True:
    result = sendRedfish(
        pcIP=pc_ip,
        deviceIP=device_ip,
        deviceUser=device_user,
        DevicePwd=device_pwd,
        method="GET",
        URL="/redfish/v1/UpdateService",
        body="",
        token="your_token",
        userName="w33199"
    )
    state = result.get("Oem", {}).get("Public", {}).get("UpgradeState")
    if state == "Success":
        print("✓ 升级成功")
        break
    elif state == "Failed":
        print("✗ 升级失败")
        break
    elif state == "Upgrading":
        print("升级进行中...")
    time.sleep(10)

# 步骤6：验证升级结果
result = sendRedfish(
    pcIP=pc_ip,
    deviceIP=device_ip,
    deviceUser=device_user,
    DevicePwd=device_pwd,
    method="GET",
    URL="/redfish/v1/UpdateService/FirmwareInventory/BMC",
    body="",
    token="your_token",
    userName="w33199"
)
print(f"升级后固件版本: {result['Version']}")
```

### 使用sendRedfish工具

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

### 示例1：TFTP固件升级（推荐）
```python
import requests
import time
import json

# 配置参数
pc_ip = "10.41.112.148"
pc_ip_device = "192.168.33.199"
device_ip = "192.168.49.71"
device_user = "admin"
device_pwd = "Password@_"
ftp_server = "10.141.228.15"
ftp_user = "ftp-CCSPLSmart1"
ftp_password = "X2HWrK"
firmware_path = "/data-out/w33199/0428/HDM3_3.05.01_FTC_signed.bin"
firmware_filename = "HDM3_3.05.01_FTC_signed.bin"

# 步骤1：查询当前固件版本
print("步骤1：查询当前固件版本")
result = sendRedfish(
    pcIP=pc_ip,
    deviceIP=device_ip,
    deviceUser=device_user,
    DevicePwd=device_pwd,
    method="GET",
    URL="/redfish/v1/UpdateService/FirmwareInventory/BMC",
    body="",
    token="your_token",
    userName="w33199"
)
current_version = json.loads(result.get("body", "{}")).get("Version", "Unknown")
print(f"当前固件版本: {current_version}")

# 步骤2：从FTP服务器下载固件到PC本地
print("\n步骤2：从FTP服务器下载固件到PC本地")
download_result = requests.post(
    f"http://{pc_ip}:8888/firmware/download",
    json={
        "ftpServer": ftp_server,
        "ftpUser": ftp_user,
        "ftpPassword": ftp_password,
        "firmwarePath": firmware_path,
        "localDir": "C:\\firmware_upgrade",
        "localFilename": firmware_filename
    }
)
download_data = download_result.json()
if download_data.get("success"):
    print(f"✓ 固件下载成功: {download_data['local_path']}")
    print(f"  文件大小: {download_data['file_size'] / 1024 / 1024:.2f} MB")
else:
    print(f"✗ 固件下载失败: {download_data.get('error')}")
    exit(1)

# 步骤3：启动TFTP服务器
print("\n步骤3：启动TFTP服务器")
tftp_result = requests.post(
    f"http://{pc_ip}:8888/firmware/tftp/start",
    json={}
)
tftp_data = tftp_result.json()
if tftp_data.get("ok"):
    print(f"✓ TFTP服务器启动成功")
    print(f"  监听地址: {pc_ip_device}:69")
    print(f"  工作目录: C:\\firmware_upgrade")
else:
    print(f"✗ TFTP服务器启动失败: {tftp_data.get('error')}")
    exit(1)

# 步骤4：通过TFTP发起固件升级
print("\n步骤4：通过TFTP发起固件升级")
upgrade_result = sendRedfish(
    pcIP=pc_ip,
    deviceIP=device_ip,
    deviceUser=device_user,
    DevicePwd=device_pwd,
    method="POST",
    URL="/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate",
    body=f'{{"ImageURI":"tftp://{pc_ip_device}/{firmware_filename}","Oem":{{"Public":{{"Preserve":"Retain","RebootMode":"Auto"}}}}}}',
    token="your_token",
    userName="w33199"
)
upgrade_data = json.loads(upgrade_result.get("body", "{}"))
if upgrade_result.get("status_code") == 200 or upgrade_data.get("error"):
    print(f"✓ 升级请求已发送")
    print(f"  固件URI: tftp://{pc_ip_device}/{firmware_filename}")
    print(f"  配置保留: Retain")
    print(f"  重启模式: Auto")
else:
    print(f"✗ 升级请求失败: {upgrade_data}")
    exit(1)

# 步骤5：查询升级状态
print("\n步骤5：查询升级状态")
max_wait_minutes = 30
start_time = time.time()
while time.time() - start_time < max_wait_minutes * 60:
    result = sendRedfish(
        pcIP=pc_ip,
        deviceIP=device_ip,
        deviceUser=device_user,
        DevicePwd=device_pwd,
        method="GET",
        URL="/redfish/v1/UpdateService",
        body="",
        token="your_token",
        userName="w33199"
    )
    update_data = json.loads(result.get("body", "{}"))
    state = update_data.get("Oem", {}).get("Public", {}).get("UpgradeState")
    
    if state == "Success":
        print("✓ 升级成功!")
        break
    elif state == "Failed":
        print("✗ 升级失败!")
        exit(1)
    elif state == "Upgrading":
        print(f"升级进行中... (已运行 {int(time.time() - start_time)} 秒)")
    elif state is None:
        print("等待升级开始...")
    
    time.sleep(10)

# 步骤6：验证升级结果
print("\n步骤6：验证升级结果")
print("等待设备重启...")
time.sleep(180)  # 等待3分钟

result = sendRedfish(
    pcIP=pc_ip,
    deviceIP=device_ip,
    deviceUser=device_user,
    DevicePwd=device_pwd,
    method="GET",
    URL="/redfish/v1/UpdateService/FirmwareInventory/BMC",
    body="",
    token="your_token",
    userName="w33199"
)
new_version = json.loads(result.get("body", "{}")).get("Version", "Unknown")
print(f"升级后固件版本: {new_version}")

if new_version != current_version:
    print(f"\n✓ 固件升级成功!")
    print(f"  升级前: {current_version}")
    print(f"  升级后: {new_version}")
else:
    print(f"\n✗ 固件版本未变化")
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

### 网络架构限制
1. **BMC设备网络隔离**：BMC设备只能访问小网（192.168.x.x），无法访问大网（10.41.x.x）
2. **必须使用TFTP**：由于网络隔离，必须通过PC代理作为网关，使用TFTP方式传输固件
3. **PC代理角色**：PC代理同时拥有大网和设备网IP，作为网关连接两个网络

### TFTP升级注意事项
1. **固件下载**：必须先将固件从FTP服务器（大网）下载到PC代理本地
2. **TFTP服务器**：在PC代理上启动TFTP服务器，监听设备网IP（192.168.33.199:69）
3. **固件传输**：BMC设备通过TFTP从PC代理下载固件
4. **TFTP服务器时机**：TFTP服务器需要在升级过程中保持运行，直到固件上传完成（约60%进度）

### 升级前准备
1. 确认固件文件已上传到FTP服务器
2. 确认PC代理可以访问FTP服务器
3. 确认BMC设备可以访问PC代理的设备网IP
4. 确认设备有足够的电源供应
5. 建议在升级前备份重要配置

### 升级过程
1. 升级过程中不要断电
2. 升级过程中不要重启设备
3. 升级时间可能较长（通常10-30分钟），请耐心等待
4. 升级完成后设备会自动重启（Auto模式）或需要手动重启（Manual模式）
5. TFTP服务器在固件上传完成后（约60%进度）可以停止

### 升级后验证
1. 等待设备重启完成（通常3-5分钟）
2. 查询固件版本确认升级成功
3. 检查设备功能是否正常
4. 查看升级日志确认无错误

### 系统锁定
固件升级会触发系统锁定：
- 固件版本锁定
- BIOS配置锁定（BIOS升级时）
- BMC配置锁定（BMC升级时）

### 错误处理
1. **"Upgrade is in progress"**：表示已有升级任务在进行，请等待当前任务完成
2. **TFTP连接失败**：检查PC代理的TFTP服务器是否正常运行
3. **固件下载失败**：检查FTP服务器连接和凭据
4. **升级失败**：查看设备日志，确认固件文件完整性

## 依赖

- MCP服务器连接（SWRDMCPServer）
- PC代理服务（端口8888）
- FTP服务器访问权限
- 设备管理权限

## 参考文档

- H3C HDM2&HDM3 Redfish参考手册
