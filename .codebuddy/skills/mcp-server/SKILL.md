---
name: SWRDMCPServer UserGuide
description: SWRDMCPServer使用技能。指导AI Agent正确使用MCP Server的认证流程和工具调用规范。触发词：MCP调用、Redfish、IPMI、浏览器控制、BMC操作。
metadata:
  version: "0.2.0"
---

# SWRDMCPServer 使用技能

## 概述
此技能指导 AI Agent 正确使用 SWRDMCPServer 的认证流程和工具调用规范。SWRDMCPServer 提供了 Redfish、IPMI、浏览器控制和远程命令执行等工具。

## 认证机制

SWRDMCPServer 使用**连接级别 Basic Auth** 进行认证。MCP Client 在连接时需在 HTTP 请求头中携带 `Authorization: Basic <base64(username:password)>`。

**MCP Client 配置示例**（如 `mcp.json`）：
```json
{
  "mcpServers": {
    "SWRDMCPServer": {
      "transport": {
        "type": "streamable-http",
        "url": "http://10.41.6.8:8000/mcp",
        "headers": {
          "Authorization": "Basic YWRtaW46YWRtaW4xMjM="
        }
      }
    }
  }
}
```

**Base64 编码方式**：
```
username:password → Base64 编码 → YWRtaW46YWRtaW4xMjM=
```

**认证流程**：
1. MCP Client 发起连接时携带 `Authorization` 请求头
2. 服务器中间件 `ConnectionAuthMiddleware` 拦截请求，解码并验证凭据
3. 验证通过后，将用户名注入 `request.state.authenticated_user`，后续工具可读取
4. 验证结果会缓存（默认 3600 秒），避免重复认证

**认证优先级**：
1. 优先使用 **LDAP 认证**（如果启用了 LDAP）
2. LDAP 失败则回退到**本地用户列表**（`security_config.yaml` 中的 `auth.users`）

**LDAP 部门访问控制**（可选）：
- 可配置允许访问的部门列表
- 支持精确匹配和模糊匹配
- 部门不在允许列表中的用户将被拒绝访问（返回 403）

## 可用工具列表

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `sendRedfish` | 发送 Redfish 请求 | pcIP, deviceIP, deviceUser, DevicePwd, method, URL, body |
| `sendIPMI` | 发送 IPMI 命令 | pcIP, deviceIP, deviceUser, DevicePwd, command |
| `browserOpen` | 打开浏览器 | pcIP, sessionId, headless |
| `browserRun` | 执行浏览器操作 | pcIP, sessionId, actions |
| `browserScreenshot` | 截取浏览器截图 | pcIP, sessionId, fullPage |
| `browserClose` | 关闭浏览器 | pcIP, sessionId |
| `sendCommand` | 在 PC 代理上执行本地命令 | pcIP, commandType, params |

## 参数说明

### 公共参数
- **pcIP**: PC 代理的 IP 地址（运行代理服务的机器）
- **deviceIP**: 目标设备的 IP 地址（BMC 地址）
- **deviceUser**: 设备登录用户名
- **DevicePwd**: 设备登录密码

### sendRedfish 特有参数
- **method**: HTTP 方法（GET/POST/PUT/PATCH/DELETE）
- **URL**: Redfish 路径（如 /redfish/v1）
- **body**: 请求体（GET 请求传空字符串）
- **ctx**: MCP 上下文对象（自动传入，无需手动处理）

### sendIPMI 特有参数
- **command**: ipmitool 命令（如 "mc info", "sensor list", "power status"）
- **ctx**: MCP 上下文对象（自动传入，无需手动处理）

### 浏览器工具特有参数
- **sessionId**: 浏览器会话 ID
- **headless**: 是否无头模式（True/False）
- **actions**: 操作 JSON 数组（字符串类型，如 `'[{"type":"goto","url":"http://..."}]'`）
- **options**: 可选配置 JSON（字符串类型，默认为空字符串）
- **fullPage**: 是否全页截图（True/False）

### sendCommand 特有参数
- **commandType**: 命令类型，支持以下值：
  - `ftp_download`: 从 FTP 服务器下载文件到 PC 代理
  - `serial`: 连接设备串口（通过串口交换机）
  - `ssh`: SSH 连接到设备并执行命令
  - `tftp_server`: 启动/停止 TFTP 服务器
  - `shell`: 在 PC 代理上执行 shell 命令
- **params**: JSON 字符串，包含该命令类型所需的参数

**各命令类型的 params 格式**：

`ftp_download`:
```json
{"ftpServer":"10.141.228.15","ftpUser":"user","ftpPassword":"pass","remotePath":"/path/firmware.bin","localPath":"C:\\firmware\\firmware.bin"}
```

`serial`:
```json
{"host":"192.168.0.200","port":3004,"baud":115200,"action":"open"}
```

`ssh`:
```json
{"host":"192.168.88.222","port":22,"user":"admin","password":"pass","command":"mc info","timeout":30}
```

`tftp_server`:
```json
{"action":"start","port":69,"dir":"C:\\firmware_upgrade"}
```

`shell`:
```json
{"command":"dir /b C:\\firmware","timeout":30}
```

## browserRun 支持的操作类型

`actions` 参数为 JSON 数组字符串，支持以下操作：

| 操作类型 | 说明 | 示例 |
|----------|------|------|
| `goto` | 导航到 URL | `{"type":"goto","url":"http://..."}` |
| `click` | 点击元素 | `{"type":"click","selector":"#btn"}` |
| `fill` | 填写输入框 | `{"type":"fill","selector":"#input","text":"value"}` |
| `press` | 按键 | `{"type":"press","selector":"#input","key":"Enter"}` |
| `wait_for_selector` | 等待元素出现 | `{"type":"wait_for_selector","selector":"#elem"}` |
| `wait_for_load_state` | 等待页面加载 | `{"type":"wait_for_load_state","state":"networkidle"}` |
| `get_text` | 获取元素文本（非截图） | `{"type":"get_text","selector":"#elem"}` |
| `get_html` | 获取元素 HTML（非截图） | `{"type":"get_html","selector":"#elem"}` |
| `get_attribute` | 获取属性（非截图） | `{"type":"get_attribute","selector":"#elem","attribute":"href"}` |
| `eval` | 执行 JS（非截图） | `{"type":"eval","expression":"()=>document.title"}` |
| `get_all_links` | 获取所有链接（非截图） | `{"type":"get_all_links"}` |
| `get_all_inputs` | 获取所有输入框（非截图） | `{"type":"get_all_inputs"}` |
| `get_all_buttons` | 获取所有按钮（非截图） | `{"type":"get_all_buttons"}` |
| `get_page_info` | 获取页面信息（非截图） | `{"type":"get_page_info"}` |
| `query_selector_all` | 查询多个元素（非截图） | `{"type":"query_selector_all","selector":"li"}` |

**示例**：
```
调用 browserRun(
  pcIP="10.41.6.8",
  sessionId="my-session",
  actions='[{"type":"goto","url":"http://192.168.88.222"},{"type":"get_page_info"}]'
)
```

## 质量要求

1. **无需手动认证**：认证由连接级别 Basic Auth 自动处理，无需调用任何认证工具
2. **密码脱敏**：在日志或输出中不要明文显示密码
3. **错误处理**：如果工具返回 `{"error": "认证失败"}` 类型的错误，检查连接级别认证配置是否正确
4. **actions 参数**：`browserRun` 的 `actions` 参数是字符串类型，需传入 JSON 数组的字符串表示
5. **params 参数**：`sendCommand` 的 `params` 参数是字符串类型，需传入 JSON 字符串

## 常见问题

### Q: 如何配置认证？
A: 在 MCP Client 的 HTTP 请求头中添加 `Authorization: Basic <base64(username:password)>`。例如 `Authorization: Basic YWRtaW46YWRtaW4xMjM=`。

### Q: 认证失败怎么办？
A: 检查以下几点：
1. `Authorization` 请求头是否正确配置
2. Base64 编码是否正确（格式为 `username:password` 的 Base64）
3. 用户名和密码是否正确
4. LDAP 服务器是否可用（如果启用了 LDAP 认证）
5. 部门访问控制是否阻止了访问（检查 LDAP 部门配置）

### Q: 如何获取用户名和密码？
A: 从 MCP Client 配置文件（如 `mcp.json`）的 `headers` 字段中获取。`Authorization` 值为 `Basic <base64(username:password)>`，解码即可得到用户名和密码。

### Q: 固件升级怎么操作？
A: 使用 `sendCommand` 工具，`commandType` 设为 `ftp_download`，在 `params` 中指定 FTP 服务器信息和固件路径。然后可通过 `sendIPMI` 或 `sendRedfish` 触发 BMC 固件升级。
