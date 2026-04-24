# BMC固件升级 - 完全自动化使用指南

## 概述

本文档说明如何使用MCPServer新增的固件升级工具实现BMC设备的完全自动化固件升级。

## 新增的MCP工具

### 1. firmwareDownload - 固件下载

从FTP服务器下载固件到PC代理。

**参数：**
- `pcIP`: PC代理的IP地址
- `ftpServer`: FTP服务器地址
- `ftpUser`: FTP用户名
- `ftpPassword`: FTP密码
- `firmwarePath`: 固件文件路径
- `localDir`: 本地保存目录（默认：C:\firmware_upgrade）
- `localFilename`: 本地文件名（默认：firmware.bin）
- `token`: 认证Token
- `userName`: IDE用户名
- `ctx`: MCP上下文

**返回：**
```json
{
  "returncode": 0,
  "stdout": "...",
  "stderr": "...",
  "local_path": "C:\\firmware_upgrade\\HDM3_3.05_signed.bin",
  "file_size": 12345678,
  "success": true
}
```

### 2. firmwareUpload - 固件上传

通过HTTP上传固件到BMC设备。

**参数：**
- `pcIP`: PC代理的IP地址
- `deviceIP`: BMC设备IP地址
- `deviceUser`: 设备用户名
- `DevicePwd`: 设备密码
- `localPath`: 固件文件本地路径
- `preserve`: 配置保留策略（默认：Retain）
  - `Retain`: 配置保留
  - `Restore`: 配置覆盖
  - `ForceRestore`: 强制覆盖
- `rebootMode`: 重启模式（默认：Auto）
  - `Auto`: 立即重启
  - `Manual`: 手动重启
- `token`: 认证Token
- `userName`: IDE用户名
- `ctx`: MCP上下文

**返回：**
```json
{
  "returncode": 0,
  "stdout": "...",
  "stderr": "...",
  "success": true
}
```

### 3. firmwareStatus - 升级状态查询

查询固件升级状态。

**参数：**
- `pcIP`: PC代理的IP地址
- `deviceIP`: BMC设备IP地址
- `deviceUser`: 设备用户名
- `DevicePwd`: 设备密码
- `token`: 认证Token
- `userName`: IDE用户名
- `ctx`: MCP上下文

**返回：**
```json
{
  "Oem": {
    "Public": {
      "UpgradeState": "Upgrading",
      "UpgradeProgress": 50,
      "UpgradeMessage": "正在升级..."
    }
  }
}
```

**升级状态说明：**
- `null`: 无升级任务
- `Upgrading`: 升级中
- `Success`: 升级成功
- `Failed`: 升级失败

## 使用方式

### 方式1：使用自动化脚本（推荐）

运行完全自动化脚本：

```bash
cd .codebuddy/skills/firmware-upgrade/scripts
python automated_upgrade.py
```

脚本会自动执行：
1. 获取认证token
2. 从FTP下载固件
3. 上传固件到BMC
4. 监控升级进度

### 方式2：手动调用MCP工具

#### 步骤1：获取认证token

```python
result = authenticate(
    username="admin",
    password="admin123",
    ctx=context
)
token = result["token"]
```

#### 步骤2：下载固件

```python
result = firmwareDownload(
    pcIP="10.41.112.148",
    ftpServer="10.141.228.15",
    ftpUser="ftp-CCSPLSmart1",
    ftpPassword="X2HWrK",
    firmwarePath="/data-out/w33199/0427/HDM3_3.05_signed.bin",
    localDir="C:\\firmware_upgrade",
    localFilename="HDM3_3.05_signed.bin",
    token=token,
    userName="w33199",
    ctx=context
)
```

#### 步骤3：上传固件

```python
result = firmwareUpload(
    pcIP="10.41.112.148",
    deviceIP="192.168.49.71",
    deviceUser="admin",
    DevicePwd="Password@_",
    localPath="C:\\firmware_upgrade\\HDM3_3.05_signed.bin",
    preserve="Retain",
    rebootMode="Auto",
    token=token,
    userName="w33199",
    ctx=context
)
```

#### 步骤4：监控升级状态

```python
while True:
    result = firmwareStatus(
        pcIP="10.41.112.148",
        deviceIP="192.168.49.71",
        deviceUser="admin",
        DevicePwd="Password@_",
        token=token,
        userName="w33199",
        ctx=context
    )

    # 解析状态
    data = json.loads(result)
    state = data.get("Oem", {}).get("Public", {}).get("UpgradeState")
    progress = data.get("Oem", {}).get("Public", {}).get("UpgradeProgress")

    print(f"状态: {state}, 进度: {progress}%")

    if state in ["Success", "Failed", None]:
        break

    time.sleep(30)
```

## 配置说明

所有配置从 `.codebuddy/rules/SystemTest.mdc` 读取：

```markdown
## 固件升级配置
- FTP服务器地址：10.141.228.15
- FTP用户名：ftp-CCSPLSmart1
- FTP密码：X2HWrK
- 固件文件路径：/data-out/w33199/0427/HDM3_3.05_signed.bin
- 完整固件URI：ftp://ftp-CCSPLSmart1:X2HWrK@10.141.228.15/data-out/w33199/0427/HDM3_3.05_signed.bin
```

## 工作流程

```
┌─────────────┐
│ MCP Server  │
│  (localhost)│
└──────┬──────┘
       │ HTTP POST
       │ /mcp/firmwareDownload
       ▼
┌─────────────┐
│ PC Proxy    │
│ 10.41.112.148│
│  :8888      │
└──────┬──────┘
       │ FTP Download
       ▼
┌─────────────┐
│ FTP Server  │
│ 10.141.228.15│
└─────────────┘
       │
       │ HTTP POST
       │ /mcp/firmwareUpload
       ▼
┌─────────────┐
│ PC Proxy    │
│ 10.41.112.148│
│  :8888      │
└──────┬──────┘
       │ HTTP Upload
       ▼
┌─────────────┐
│ BMC Device  │
│ 192.168.49.71│
└─────────────┘
```

## 优势

✅ **完全自动化** - 无需手动操作
✅ **统一管理** - 通过MCP统一管理所有操作
✅ **CI/CD集成** - 可集成到CI/CD流程
✅ **批量升级** - 支持批量升级多台设备
✅ **状态监控** - 实时监控升级进度
✅ **错误处理** - 完善的错误处理机制

## 注意事项

### 安全性
- ⚠️ FTP密码和BMC凭据需要妥善保管
- ⚠️ 建议使用加密传输
- ⚠️ 定期更新密码

### 升级前准备
1. ✅ 确认固件文件已上传到FTP服务器
2. ✅ 确认设备网络连接正常
3. ✅ 确认设备有足够的电源供应
4. ✅ 建议在升级前备份重要配置

### 升级过程
1. ⚠️ 升级过程中不要断电
2. ⚠️ 升级过程中不要重启设备
3. ⚠️ 升级时间可能较长，请耐心等待
4. ⚠️ 升级完成后设备会自动重启（Auto模式）

### 升级后验证
1. ✅ 查询固件版本确认升级成功
2. ✅ 检查设备功能是否正常
3. ✅ 查看升级日志确认无错误

## 故障排查

### 下载失败
- 检查FTP服务器地址和端口
- 检查FTP用户名和密码
- 检查固件文件路径是否正确
- 检查PC代理是否能访问FTP服务器

### 上传失败
- 检查BMC设备IP地址
- 检查BMC用户名和密码
- 检查本地固件文件是否存在
- 检查PC代理是否能访问BMC设备

### 升级失败
- 检查固件文件是否完整
- 检查固件版本是否兼容
- 查看升级日志获取详细错误信息

## 技术支持

如遇到问题，请查看：
1. MCPServer日志：`MCPServer/logs/mcp_operation.log`
2. PC代理日志：控制台输出
3. BMC设备日志：通过Web UI或Redfish查看

## 更新日志

### v1.0 (2026-04-27)
- ✅ 添加 firmwareDownload 工具
- ✅ 添加 firmwareUpload 工具
- ✅ 添加 firmwareStatus 工具
- ✅ 创建自动化脚本 automated_upgrade.py
- ✅ 完全自动化固件升级流程
