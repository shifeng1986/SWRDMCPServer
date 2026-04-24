---
name: SWRDMCPServer UserGuide
description: SWRDMCPServer使用技能。指导AI Agent正确使用MCP Server的认证流程和工具调用规范。触发词：MCP调用、Redfish、IPMI、浏览器控制、BMC操作。
metadata:
  version: "0.0.1"
---

# SWRDMCPServer 使用技能

## 概述
此技能指导 AI Agent 正确使用 SWRDMCPServer 的认证流程和工具调用规范。SWRDMCPServer 提供了 Redfish、IPMI 和浏览器控制等工具，所有工具调用都需要通过 Token 认证。

## 认证流程（必须遵守）

### 第一步：获取临时 Token
在调用任何业务工具之前，**必须先调用 `authenticate` 工具获取临时 Token**。

用户名和密码信息从 `mcp.json` 配置中获取。`mcp.json` 中的 `Authorization` 头使用 Basic Auth 格式：
```
Authorization: Basic <base64(username:password)>
```

**从 mcp.json 获取用户名和密码的方法**：
1. 读取 mcp.json 中 `headers.Authorization` 字段，格式为 `Basic <base64字符串>`
2. 将 `Basic ` 后面的 base64 字符串解码，得到 `username:password`
3. 用解码后的用户名和密码调用 `authenticate` 工具

示例：mcp.json 中配置 `"Authorization": "Basic YWRtaW46YWRtaW4xMjM="`
```
解码 YWRtaW46YWRtaW4xMjM= → admin:admin123
→ 用户名: admin, 密码: admin123
```

调用 authenticate：
```
调用 authenticate(username="admin", password="admin123")
```

返回示例：
```json
{
  "status": "success",
  "message": "认证成功",
  "token": "xxxxxxxxxx",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**重要**：从返回结果中提取 `token` 字段的值，后续所有工具调用都需要传入此 Token。

### 第二步：使用 Token 调用业务工具
所有业务工具都有一个 `token` 参数，必须传入第一步获取的临时 Token。

**正确示例**：
```
调用 sendRedfish(
  pcIP="192.168.49.70",
  deviceIP="192.168.49.71",
  deviceUser="admin",
  DevicePwd="Password@_,
  method="GET",
  URL="/redfish/v1",
  body="",
  token="xxxxxxxxxx"   ← 传入 authenticate 返回的 Token
)
```

**错误示例**（不传 Token 或传空字符串）：
```
调用 sendRedfish(
  ...,
  token=""   ← 错误！会导致认证失败
)
```

### 第三步：Token 过期处理
临时 Token 有效期为 3600 秒（1小时）。如果工具返回认证失败信息：
```json
{"error": "认证失败", "message": "Token 已过期，请重新调用 authenticate 工具获取 Token"}
```
则需要重新执行第一步获取新的 Token。

### 第四步：注销 Token（可选）
操作完成后，可调用 `logout` 工具注销 Token：
```
调用 logout(token="xxxxxxxxxx")
```

## 可用工具列表

### 认证工具（无需 Token）
| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `authenticate` | 用户认证，获取临时 Token | username, password |
| `logout` | 注销 Token | token |

### 业务工具（需要 Token）
| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `sendRedfish` | 发送 Redfish 请求 | pcIP, deviceIP, deviceUser, DevicePwd, method, URL, body, token |
| `sendIPMI` | 发送 IPMI 命令 | pcIP, deviceIP, deviceUser, DevicePwd, command, token |
| `browserOpen` | 打开浏览器 | pcIP, sessionId, headless, token |
| `browserRun` | 执行浏览器操作 | pcIP, sessionId, actions, token |
| `browserScreenshot` | 截取浏览器截图 | pcIP, sessionId, fullPage, token |
| `browserClose` | 关闭浏览器 | pcIP, sessionId, token |

## 参数说明

### 公共参数
- **pcIP**: PC 代理的 IP 地址（运行代理服务的机器）
- **deviceIP**: 目标设备的 IP 地址（BMC 地址）
- **deviceUser**: 设备登录用户名
- **DevicePwd**: 设备登录密码
- **token**: 认证 Token（通过 authenticate 工具获取）
- **userName**: IDE 系统登录用户名（可选，自动从 Token 关联）

### sendRedfish 特有参数
- **method**: HTTP 方法（GET/POST/PUT/PATCH/DELETE）
- **URL**: Redfish 路径（如 /redfish/v1）
- **body**: 请求体（GET 请求传空字符串）

### sendIPMI 特有参数
- **command**: ipmitool 命令（如 "mc info", "sensor list", "power status"）

### 浏览器工具特有参数
- **sessionId**: 浏览器会话 ID
- **headless**: 是否无头模式（True/False）
- **actions**: 操作 JSON 数组
- **fullPage**: 是否全页截图（True/False）

## 质量要求

1. **必须先认证**：每次对话首次调用业务工具前，必须先调用 `authenticate` 获取 Token
2. **Token 必须传递**：所有业务工具调用必须传入有效的 `token` 参数
3. **Token 过期处理**：遇到 Token 过期错误时，自动重新认证
4. **不要硬编码 Token**：Token 是临时生成的，每次认证都会变化
5. **密码脱敏**：在日志或输出中不要明文显示密码
6. **错误处理**：如果工具返回 `{"error": "认证失败"}` 类型的错误，优先检查 Token 是否有效
7. **userName 参数**：如果 IDE 系统登录用户名已知，应传入 `userName` 参数；如果未传，系统会自动从 Token 关联用户名
