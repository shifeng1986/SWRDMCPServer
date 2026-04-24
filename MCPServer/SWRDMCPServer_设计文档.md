# SWRDMCPServer 设计文档

> 版本：1.2 | 日期：2026-04-24 | 状态：更新（完善用户认证与 Token 认证描述）

---

## 目录

1. [总体设计思路](#1-总体设计思路)
2. [用户认证方案](#2-用户认证方案)
3. [数据流详解](#3-数据流详解)
4. [安全审计方案](#4-安全审计方案)
5. [附录：配置参考](#5-附录配置参考)
6. [附录：已知风险与改进建议](#6-已知风险与改进建议)

> **第 2 章节更新说明**：新增 2.6 认证日志事件、2.7 `/auth/token` HTTP 端点、2.8 认证配置等小节，完善用户认证与 Token 认证的描述。

---

## 1 总体设计思路

### 1.1 项目定位

SWRDMCPServer 是一个基于 MCP（Model Context Protocol）协议的智能服务器硬件管理代理服务。它作为 AI Agent / IDE 与物理服务器之间的中间层，将自然语言驱动的管理意图转化为标准的 Redfish / IPMI 操作，实现对服务器 BMC（Baseboard Management Controller）的远程管控。

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **代理转发** | MCP Server 不直接与目标设备通信，而是通过 PC 代理中转，实现网络隔离与职责分离 |
| **安全优先** | 四层装饰器防护（Token 认证 → 安全拦截 → 操作日志 → 输入校验），高危操作可被自动阻断 |
| **配置驱动** | 日志策略、安全策略、告警策略、认证策略均通过 YAML 配置文件管理，无需改代码即可调整 |
| **可观测性** | 全生命周期操作日志 + 多渠道安全告警，确保所有操作可追溯 |
| **认证管控** | 用户名/密码 + 临时 Token 双重认证，所有业务操作需通过 Token 验证 |

### 1.3 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AI Agent / IDE                                 │
│                    (MCP Client, SSE 传输)                               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ MCP Tool Call
                               │ (sendRedfish / sendIPMI / authenticate / logout)
                               │ Authorization: Basic <base64(user:pwd)>
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          SWRDMCPServer                                  │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     FastMCP (SSE 传输层)                         │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                               │                                         │
│                               ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    认证中间件层                                    │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │ AuthMiddleware (拦截 /mcp 路径)                             │  │  │
│  │  │  ├─ Basic Auth: 验证用户名/密码                             │  │  │
│  │  │  ├─ Bearer Token: 验证临时 Token 或服务端 Token             │  │  │
│  │  │  ├─ token 前缀: 兼容方式                                    │  │  │
│  │  │  └─ 查询参数: ?token=xxx (备用方式)                         │  │  │
│  │  │  ├─ 认证失败 → 401 Unauthorized                            │  │  │
│  │  └─ /auth 路径放行（无需认证）                              │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │ /auth/token 端点 (POST，无需认证)                          │  │  │
│  │  │  请求: {"username":"admin", "password":"admin123"}          │  │  │
│  │  │  响应: {"token":"xxx", "token_type":"Bearer", "expires_in":3600}  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                               │                                         │
│                               ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    装饰器防护层 (四层)                             │  │
│  │  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │  │
│  │  │ @auth_       │  │ @with_high_risk_│  │ @with_operation_│  │ @validate_input │  │  │
│  │  │ required     │→ │ check           │→ │ log             │→ │                 │  │  │
│  │  │ (Token 认证) │  │ (安全拦截)      │  │ (操作日志)      │  │ (输入校验)      │  │  │
│  │  └──────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                               │                                         │
│                               ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    核心业务层                                      │  │
│  │  ┌─────────────────────────┐  ┌─────────────────────────┐        │  │
│  │  │ sendRedfish()           │  │ sendIPMI()              │        │  │
│  │  │ Redfish HTTP 请求转发   │  │ IPMI 命令转发           │        │  │
│  │  └─────────────────────────┘  └─────────────────────────┘        │  │
│  │  ┌─────────────────────────┐  ┌─────────────────────────┐        │  │
│  │  │ authenticate()          │  │ logout()                │        │  │
│  │  │ 用户名/密码 → 临时Token │  │ 注销 Token              │        │  │
│  │  └─────────────────────────┘  └─────────────────────────┘        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                               │                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    基础设施层                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │  │
│  │  │ config.py    │  │ alert_       │  │ RotatingFile │  │ auth_        │  │  │
│  │  │ (配置管理)   │  │ handler.py   │  │ Handler      │  │ decorator.py │  │  │
│  │  │              │  │ (告警通知)   │  │ (日志轮转)   │  │ (认证管理)   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTP POST (JSON)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PC 代理                                        │
│                    (http://{pcIP}:8888)                                  │
│  ┌─────────────────────────┐  ┌─────────────────────────┐              │
│  │ /redfish → Redfish API  │  │ /ipmi → ipmitool 命令   │              │
│  └──────────┬──────────────┘  └──────────┬──────────────┘              │
└─────────────┼─────────────────────────────┼─────────────────────────────┘
              │                             │
              ▼                             ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│     目标设备 BMC        │  │     目标设备 BMC        │
│   (Redfish API)         │  │   (IPMI 接口)          │
└─────────────────────────┘  └─────────────────────────┘
```

### 1.4 模块职责矩阵

| 模块 | 文件 | 职责 |
|------|------|------|
| 主入口 | `main.py` | 创建 MCP Server，注册 `sendRedfish` / `sendIPMI` / `authenticate` / `logout` 等工具，注册认证中间件和 `/auth/token` 端点，处理请求转发 |
| 配置管理 | `config.py` | 加载 YAML 配置，导出全局常量（含认证配置），提供默认值兜底 |
| 用户认证 | `decorators/auth_decorator.py` | 用户名/密码认证、临时 Token 管理、认证中间件 `AuthMiddleware`、`@auth_required` 装饰器、`/auth/token` 端点、`authenticate` / `logout` 工具 |
| 安全拦截 | `decorators/security_decorator.py` | 风险评估、策略执行、确认缓存管理 |
| 操作日志 | `decorators/logging_decorator.py` | 全生命周期日志记录、敏感信息脱敏、日志轮转 |
| 输入校验 | `decorators/validation_decorator.py` | 参数格式自动推断与校验 |
| 预警通知 | `decorators/alert_handler.py` | 多渠道预警分发（邮件/钉钉/企微/Webhook） |
| 日志配置 | `config.yaml` | 日志级别、格式、轮转策略 |
| 安全与认证配置 | `security_config.yaml` | 风险等级映射、处理策略、确认有效期、认证开关、用户列表、Token 配置 |
| 预警配置 | `alert_config.yaml` | 预禁用开关、阈值、渠道配置 |

---

## 2 用户认证方案

### 2.1 认证架构总览

SWRDMCPServer 采用**用户名/密码 + 临时 Token**的双重认证机制，在两个层级分别验证：

- **中间件层（HTTP 传输层）**：`AuthMiddleware` 拦截所有 `/mcp` 请求，验证 `Authorization` 头
- **Tool 层（业务层）**：`@auth_required` 装饰器验证 `token` 参数的有效性

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户认证架构                                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    中间件层 (HTTP 传输层)                 │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │ AuthMiddleware                                      ││   │
│  │  │  ├─ Basic Auth: 验证用户名/密码                      ││   │
│  │  │  ├─ Bearer Token: 验证临时 Token 或服务端 Token      ││   │
│  │  │  ├─ token 前缀: 兼容方式，与 Bearer 等效            ││   │
│  │  │  └─ 查询参数: ?token=xxx (备用方式)                  ││   │
│  │  │                                                      ││   │
│  │  │ 认证失败 → 401 Unauthorized                         ││   │
│  │  │ 认证通过 → 放行请求                                  ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Tool 层 (业务层)                       │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │ @auth_required 装饰器                               ││   │
│  │  │  ├─ 提取 token 参数                                 ││   │
│  │  │  ├─ _validate_tool_token() 验证有效性               ││   │
│  │  │  │   ├─ 检查 Token 是否在 _token_cache 中           ││   │
│  │  │  │   ├─ 检查 Token 是否过期                         ││   │
│  │  │  │   └─ 检查是否为服务端 Token (备用)               ││   │
│  │  │  │                                                  ││   │
│  │  │  ├─ 认证失败 → 返回 {"error": "认证失败"}           ││   │
│  │  │  ├─ 认证通过 → 自动注入 userName                    ││   │
│  │  │  └─ AUTH_ENABLED == False → 直接放行                ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 认证流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 认证流程                                                        │
│                                                                 │
│  ① MCP Client 连接（mcp.json 配置 Basic Auth）
│     │   Authorization: Basic <base64(username:password)>
│     ▼
│  ② AuthMiddleware 验证用户名/密码 → 放行
│     │
│  ③ AI Agent 调用 authenticate(username, password)
│     │   → _authenticate_user() 验证用户名/密码
│     │   → 生成临时 Token，存入 _token_cache
│     │   → 返回 {"token": "xxx", "token_type": "Bearer", "expires_in": 3600}
│     ▼
│  ④ AI Agent 提取 Token，后续业务工具调用传入 token 参数
│     │   sendRedfish(..., token="xxx")
│     │   sendIPMI(..., token="xxx")
│     │   browserOpen(..., token="xxx")
│     ▼
│  ⑤ @auth_required 装饰器验证 Token
│     │   ├─ Token 有效 → 执行业务逻辑
│     │   ├─ Token 过期 → 返回 "Token 已过期，请重新认证"
│     │   └─ Token 无效 → 返回 "Token 无效"
│     ▼
│  ⑥ Token 过期后，重新执行 ③ 获取新 Token
│     │
│  ⑦ 操作完成，调用 logout(token) 注销 Token
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Token 管理机制

#### 2.3.1 Token 类型

| Token 类型 | 生成方式 | 存储位置 | 有效期 | 用途 |
|-----------|---------|---------|--------|------|
| 服务端 Token | 启动时生成或从配置读取 | `_server_token`（单例） | 永久 | MCP Client 连接认证（备用机制） |
| 临时 Token | `authenticate` 工具认证后生成 | `_token_cache`（内存字典） | 3600 秒（可配置） | 业务工具调用认证 |

#### 2.3.2 临时 Token 缓存结构

```
_token_cache: dict[str, dict[str, Any]]
├─ Key: token (随机字符串, secrets.token_urlsafe(32))
└─ Value:
   ├─ "user": str (关联的用户名)
   └─ "expires_at": float (过期时间戳, time.time() + AUTH_TOKEN_EXPIRE_SECONDS)
```

#### 2.3.3 Token 验证逻辑

```
_validate_tool_token(token) → (is_valid, message, username)

① AUTH_ENABLED == False? → (True, "认证未启用", None)
② token 为空? → (False, "Token 不能为空", None)
③ token 在 _token_cache 中?
   ├─ 未过期 → (True, "Token 有效", username)
   └─ 已过期 → 清理缓存 → (False, "Token 已过期", None)
④ token == 服务端 Token? → (True, "Token 有效（服务端 Token）", "server")
⑤ 其他 → (False, "Token 无效", None)
```

### 2.4 中间件认证方式

| 方式 | Authorization 头格式 | 说明 | 适用场景 |
|------|---------------------|------|----------|
| Basic Auth | `Basic <base64(username:password)>` | 用户名/密码认证 | mcp.json 连接配置（推荐） |
| Bearer Token | `Bearer <临时Token>` | `authenticate` 工具获取的临时 Token | 动态 Token 认证 |
| 服务端 Token | `Bearer <服务端Token>` | 配置文件中的固定 Token | 备用机制 |
| token 前缀 | `token <Token>` | 兼容方式，与 Bearer 等效 | 兼容场景 |
| 查询参数 | `?token=<token>` | 不支持自定义 Header 时的备用方式 | 兼容场景 |

### 2.5 认证数据流

```
AI Agent                    SWRDMCPServer
    │                           │
    │  ① authenticate(           │
    │    username="admin",       │
    │    password="admin123"     │
    │  )                        │
    │ ────────────────────────> │
    │                           │ _authenticate_user()
    │                           │ 验证: admin:admin123
    │                           │ 生成 Token: abc123...
    │                           │ 存入 _token_cache
    │                           │
    │ ② 返回:                   │
    │ {"status":"success",       │
    │  "token":"abc123...",       │
    │  "expires_in":3600}        │
    │ <──────────────────────── │
    │                           │
    │ ③ sendRedfish(             │
    │    ...                     │
    │    token="abc123..."       │
    │  )                        │
    │ ────────────────────────> │
    │                           │ @auth_required
    │                           │ _validate_tool_token()
    │                           │ Token 有效 → 注入 userName
    │                           │ @with_high_risk_check
    │                           │ @with_operation_log
    │                           │ @validate_input
    │                           │ 核心逻辑...
    │                           │
    │ ④ 返回操作结果           │
    │ <──────────────────────── │
    │                           │
    │ ⑤ logout(                 │
    │    token="abc123..."       │
    │  )                        │
    │ ────────────────────────> │
    │                           │ _revoke_token()
    │                           │ 从 _token_cache 删除
    │                           │
    │ ⑥ 返回: Token 已注销     │
    │ <──────────────────────── │
```

### 2.6 认证日志事件

认证模块在关键节点记录日志，确保认证行为可追溯：

| 事件 | 日志级别 | 触发时机 | 关键字段 |
|------|----------|----------|----------|
| `user_authenticated` | INFO | 用户通过 `authenticate` 工具认证成功 | `user`, `action=login_success` |
| `authentication_failed` | WARNING | 用户名/密码验证失败 | `user`, `action=login_failed` |
| `auth_rejected` | WARNING | 中间件层认证失败 | `path`, `client`, `action=unauthorized_access` |
| `auth_passed` | INFO | 中间件层认证通过 | `path`, `user`, `client` |
| `tool_auth_success` | INFO | `@auth_required` 装饰器验证成功 | `tool`, `user` |
| `tool_auth_failed` | WARNING | `@auth_required` 装饰器验证失败 | `tool`, `reason` |

**日志示例**：

```
# 用户认证成功
{"timestamp": 1713936000.0, "event": "user_authenticated", "user": "admin", "action": "login_success"}

# 中间件认证失败
{"timestamp": 1713936000.0, "event": "auth_rejected", "path": "/mcp", "client": "192.168.1.50", "action": "unauthorized_access"}

# Tool 认证失败
{"timestamp": 1713936000.0, "event": "tool_auth_failed", "tool": "sendRedfish", "reason": "Token 已过期，请重新调用 authenticate 工具获取 Token"}
```

### 2.7 `/auth/token` HTTP 端点

除 MCP 工具 `authenticate` 外，系统还提供独立的 HTTP 端点 `/auth/token`，用于获取临时 Token。该端点位于认证中间件之外，无需认证即可访问。

```
┌─────────────────────────────────────────────────────────────────┐
│ /auth/token 端点                                                │
│                                                                 │
│  路径: POST /auth/token                                        │
│  认证: 无需认证（/auth 路径已放行）                              │
│                                                                 │
│  请求体:                                                        │
│  {
│    "username": "admin",
│    "password": "admin123"
│  }
│                                                                 │
│  成功响应 (200):                                                │
│  {
│    "token": "abc123...",
│    "token_type": "Bearer",
│    "expires_in": 3600
│  }
│                                                                 │
│  失败响应 (400):                                                │
│  {
│    "error": "invalid_request",
│    "message": "用户名和密码不能为空"
│  }
│                                                                 │
│  失败响应 (401):                                                │
│  {
│    "error": "unauthorized",
│    "message": "用户名或密码错误"
│  }
└─────────────────────────────────────────────────────────────────┘
```

**与 `authenticate` 工具的区别**：

| 特性 | `authenticate` 工具 | `/auth/token` 端点 |
|------|---------------------|---------------------|
| 调用方式 | MCP Tool Call | HTTP POST |
| 认证要求 | 中间件层需通过认证 | 无需认证（/auth 路径放行） |
| 适用场景 | AI Agent 在 MCP 会话中获取 Token | 外部程序或脚本获取 Token |
| 响应格式 | `{"status":"success", "token":"...", "token_type":"Bearer", "expires_in":3600}` | `{"token":"...", "token_type":"Bearer", "expires_in":3600}` |

### 2.8 认证配置

认证配置位于 `security_config.yaml` 的 `auth` 节，由 `config.py` 加载并导出为全局常量：

```yaml
# security_config.yaml → auth 节
auth:
  # 是否启用用户认证（全局开关）
  # 启用后，所有 MCP 请求必须携带有效 Token
  enabled: true

  # 服务端固定 Token（用于 MCP Client 配置）
  # 若为空，则启动时自动生成随机 Token 并打印到控制台
  # 建议生产环境设置为固定值，便于 MCP Client 配置
  token: "swrd-mcp-server-token-2026"

  # 用户名/密码列表（用于 authenticate 工具登录）
  # 登录成功后会生成临时 Token，有效期由 token_expire_seconds 控制
  users:
    admin: admin123
    operator: operator123

  # 用户登录 Token 有效期（秒）
  token_expire_seconds: 3600
```

**配置项说明**：

| 配置项 | 全局常量 | 类型 | 默认值 | 说明 |
|--------|----------|------|--------|------|
| `auth.enabled` | `AUTH_ENABLED` | bool | `False` | 认证全局开关，`False` 时所有认证检查跳过 |
| `auth.token` | `AUTH_TOKEN` | str | `""` | 服务端固定 Token，为空则自动生成 |
| `auth.users` | `AUTH_USERS` | dict | `{}` | 用户名/密码映射，支持多用户 |
| `auth.token_expire_seconds` | `AUTH_TOKEN_EXPIRE_SECONDS` | int | `3600` | 临时 Token 有效期（秒） |

**启动行为**：

```
┌─────────────────────────────────────────────────────────────────┐
│ 启动行为                                                        │
│                                                                 │
│  AUTH_ENABLED == True:
│  ├─ 注册 AuthMiddleware 到 FastMCP 应用
│  ├─ 注册 /auth/token 端点
│  ├─ 获取服务端 Token:
│  │   ├─ AUTH_TOKEN 非空 → 使用配置值
│  │   └─ AUTH_TOKEN 为空 → 自动生成 secrets.token_urlsafe(32)
│  └─ 打印认证信息到控制台:
│     ├─ 认证已启用
│     ├─ 支持的认证方式
│     └─ 服务端 Token（用于 MCP Client 配置）
│                                                                 │
│  AUTH_ENABLED == False:
│  └─ 跳过所有认证，直接启动 MCP Server
└─────────────────────────────────────────────────────────────────┘
```

**MCP Client 连接配置示例**：

```json
// mcp.json（使用 Basic Auth，推荐）
{
  "mcpServers": {
    "SWRDMCPServer": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Basic YWRmin:YWRminMTIz"
      }
    }
  }
}

// mcp.json（使用服务端 Token）
{
  "mcpServers": {
    "SWRDMCPServer": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer swrd-mcp-server-token-2026"
      }
    }
  }
}
```

---

## 3 数据流详解

### 3.1 请求处理主流程

```
MCP Client (IDE/AI Agent)
    │
    │ ① MCP Tool Call (SSE 传输)
    │    参数: pcIP, deviceIP, deviceUser, DevicePwd, method/URL/body 或 command
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ FastMCP Server                                                      │
│                                                                     │
│ ② 路由匹配 → sendRedfish() 或 sendIPMI()                          │
│                                                                     │
│ ③ @auth_required (最外层装饰器，首先执行)                           │
│    ├─ AUTH_ENABLED == False? → 直接放行                             │
│    ├─ 提取 token 参数 (kwargs → args)                              │
│    ├─ _validate_tool_token() 验证有效性                             │
│    │     ├─ Token 为空 → 返回 {"error": "认证失败"}               │
│    │     ├─ Token 过期 → 返回 {"error": "Token 已过期"}           │
│    │     ├─ Token 无效 → 返回 {"error": "Token 无效"}             │
│    │     └─ Token 有效 → 自动注入 userName                        │
│    │     ▼
│ ④ @with_high_risk_check (第二层装饰器)                             │
│    ├─ SECURITY_ENABLED == False? → 直接放行                         │
│    ├─ 提取用户标识 (userName → ctx.client_id → "unknown")          │
│    ├─ 提取参数 → _assess_risk() 评估风险等级                        │
│    ├─ 提取用户标识 (userName → ctx.client_id → "unknown")          │
│    ├─ 提取参数 → _assess_risk() 评估风险等级                        │
│    │     ┌──────────────────────────────────────────────┐           │
│     │     │ HTTP Method → 风险等级映射表                │           │
│     │     │ GET→低危  POST/PATCH/PUT→高危  DELETE→严重  │           │
│     │     │ 无 method (IPMI) → 中危 (默认)             │           │
│     │     └──────────────────────────────────────────────┘           │
│    ├─ 构造 operation_key = "{tool}:{method}:{deviceIP}:{URL}"       │
│    ├─ 查询策略 (SECURITY_ACTIONS)                                   │
│    │     ┌──────────────────────────────────────────────┐           │
│     │     │ 严重→block   高危→confirm   中危→log        │           │
│     │     │ 低危→log     其他→allow                      │           │
│     │     └──────────────────────────────────────────────┘           │
│    │     │
│    │     ├─ block?   → send_alert() + raise SecurityCheckError
│    │     ├─ confirm? → _check_confirm_cache()
│    │     │     ├─ 未确认 → send_alert() + raise ConfirmationRequired
│    │     │     └─ 已确认 → 继续
│    │     ├─ log?     → 记录 WARNING/INFO 日志 → 继续
│    │     └─ allow?   → 继续
│    │     ▼
│ ⑤ @with_operation_log (中间层装饰器)
│    ├─ 生成 request_id (UUID)
│    ├─ 提取用户标识
│    ├─ 提取参数 → _sanitize_parameters() 脱敏
│    │     ┌──────────────────────────────────────────────┐           │
│     │     │ 敏感关键词: password, pwd, secret, token,   │           │
│     │     │ apikey, api_key, auth, credential,          │           │
│     │     │ private_key, access_key                      │           │
│     │     │ 匹配时 → 值替换为 "******"                   │           │
│     │     └──────────────────────────────────────────────┘           │
│    ├─ 记录 request_start (INFO)
│    ├─ 记录开始时间
│    │     ▼
│ ⑥ @validate_input (最内层装饰器)
│    ├─ 遍历所有参数，自动推断校验规则
│    │     ┌──────────────────────────────────────────────┐           │
│     │     │ 参数名含 "ip"       → IPv4 格式校验        │           │
│     │     │ 参数名 == "method"  → 有效 HTTP 方法校验   │           │
│     │     │ 参数名含 "url"      → URL 路径格式校验     │           │
│     │     │ 参数名含 "user"     → 非空校验              │           │
│     │     │ 参数名含 "pwd/password" → 非空校验         │           │
│     │     │ 参数名 == "body"    → 不校验                │           │
│     │     └──────────────────────────────────────────────┘           │
│    ├─ 校验失败 → raise ValidationError
│    │     ▼
│ ⑦ 核心逻辑 (sendRedfish / sendIPMI)
│    ├─ 打印 IDE 用户信息、MCP Client 信息
│    ├─ 构造代理 URL:
│    │     sendRedfish → http://{pcIP}:8888/redfish
│    │     sendIPMI    → http://{pcIP}:8888/ipmi
│    ├─ 构造 JSON payload (含设备凭证)
│    ├─ requests.post(proxy_url, json=payload, timeout=30)
│    ├─ 成功 → 返回 response.text
│    └─ 异常 → 返回 JSON 错误信息
│     │
│     ▼
⑧ 返回路径 (装饰器逐层返回)
    ├─ @with_operation_log:
    │     ├─ 成功 → request_end (INFO, status=success)
    │     └─ 异常 → request_error (ERROR) + request_end (WARNING, status=failed)
    │              + re-raise 异常
    └─ @with_high_risk_check: 直接返回结果
    │
    ▼
MCP Client 收到响应
```

### 3.2 Redfish 请求数据流

```
AI Agent                    SWRDMCPServer                 PC 代理              目标设备
    │                           │                           │                    │
    │  sendRedfish(             │                           │                    │
    │    pcIP="192.168.1.100",  │                           │                    │
    │    deviceIP="10.0.0.1",   │                           │                    │
    │    deviceUser="admin",    │                           │                    │
    │    DevicePwd="******",    │                           │                    │
    │    method="GET",          │                           │                    │
    │    URL="/redfish/v1/..."  │                           │                    │
    │  )                        │                           │                    │
    │ ────────────────────────> │                           │                    │
    │                           │                           │                    │
    │                           │ ① Token 认证: @auth_required 验证 token 参数
    │                           │ ② 安全检查: GET→低危→log
    │                           │ ③ 日志记录: request_start
    │                           │ ④ 参数校验: IP/URL/Method
    │                           │                           │                    │
    │                           │ ⑤ 构造代理请求:           │                    │
    │                           │ POST http://192.168.1.100:8888/redfish         │
    │                           │ {                         │                    │
    │                           │   "deviceIP":"10.0.0.1", │                    │
    │                           │   "deviceUser":"admin",  │                    │
    │                           │   "devicePwd":"******",  │                    │
    │                           │   "method":"GET",        │                    │
    │                           │   "url":"/redfish/v1/...",│                    │
    │                           │   "body":""              │                    │
    │                           │ }                        │                    │
    │                           │ ─────────────────────────>│                    │
    │                           │                           │                    │
    │                           │                           │ ⑥ 转发 Redfish 请求│
    │                           │                           │ GET /redfish/v1/...
    │                           │                           │ (携带设备认证)
    │                           │                           │ ──────────────────>│
    │                           │                           │                    │
    │                           │                           │ ⑦ 返回 Redfish 响应│
    │                           │                           │ <──────────────────│
    │                           │                           │                    │
    │                           │ ⑧ 返回代理响应           │                    │
    │                           │ <─────────────────────────│                    │
    │                           │                           │                    │
    │                           │ ⑨ 日志记录: request_end
    │                           │                           │                    │
    │ ⑩ 返回结果               │                           │                    │
    │ <──────────────────────── │                           │                    │
```

### 3.3 IPMI 请求数据流

```
AI Agent                    SWRDMCPServer                 PC 代理              目标设备
    │                           │                           │                    │
    │  sendIPMI(                │                           │                    │
    │    pcIP="192.168.1.100",  │                           │                    │
    │    deviceIP="10.0.0.1",   │                           │                    │
    │    deviceUser="admin",    │                           │                    │
    │    DevicePwd="******",    │                           │                    │
    │    command="power status" │                           │                    │
    │  )                        │                           │                    │
    │ ────────────────────────> │                           │                    │
    │                           │                           │                    │
    │                           │ ① Token 认证: @auth_required 验证 token 参数
    │                           │ ② 安全检查: 无method→中危→log
    │                           │ ③ 日志记录: request_start
    │                           │ ④ 参数校验: IP校验
    │                           │                           │                    │
    │                           │ ⑤ 构造代理请求:           │                    │
    │                           │ POST http://192.168.1.100:8888/ipmi            │
    │                           │ {                         │                    │
    │                           │   "deviceIP":"10.0.0.1", │                    │
    │                           │   "deviceUser":"admin",  │                    │
    │                           │   "devicePwd":"******",  │                    │
    │                           │   "command":"power status"│                    │
    │                           │ }                        │                    │
    │                           │ ─────────────────────────>│                    │
    │                           │                           │                    │
    │                           │                           │ ⑥ 执行 ipmitool
    │                           │                           │ ipmitool -H 10.0.0.1
    │                           │                           │   -U admin -P ****
    │                           │                           │   power status
    │                           │                           │ ──────────────────>│
    │                           │                           │                    │
    │                           │                           │ ⑦ 返回命令结果     │
    │                           │                           │ <──────────────────│
    │                           │                           │                    │
    │                           │ ⑧ 返回代理响应           │                    │
    │                           │ <─────────────────────────│                    │
    │                           │                           │                    │
    │                           │ ⑨ 日志记录: request_end
    │                           │                           │                    │
    │ ⑩ 返回结果               │                           │                    │
    │ <──────────────────────── │                           │                    │
```

### 3.4 安全拦截数据流

```
AI Agent                    SWRDMCPServer                 预警渠道
    │                           │                           │
    │  sendRedfish(             │                           │
    │    method="DELETE",       │                           │
    │    URL="/redfish/v1/..."  │                           │
    │  )                        │                           │
    │ ────────────────────────> │                           │
    │                           │                           │
    │                           │ ① 安全检查: DELETE→严重→block
    │                           │                           │
    │                           │ ② send_alert()           │
    │                           │ ─────────────────────────>│
    │                           │                           │ (邮件/钉钉/企微/Webhook)
    │                           │                           │
    │                           │ ③ raise SecurityCheckError
    │                           │                           │
    │ ④ 返回错误:              │                           │
    │ "操作已被安全策略拦截"    │                           │
    │ <──────────────────────── │                           │
```

### 3.5 确认机制数据流

```
AI Agent                    SWRDMCPServer
    │                           │
    │  ① sendRedfish(           │
    │    method="POST",         │
    │    URL="/red/v1/..."      │
    │  )                        │
    │ ────────────────────────> │
    │                           │ 安全检查: POST→高危→confirm
    │                           │ 确认缓存: 未确认
    │                           │ send_alert()
    │                           │ raise ConfirmationRequired
    │                           │   (confirm_id="xxx")
    │ ② 返回: 需要确认         │
    │ <──────────────────────── │
    │                           │
    │  ③ confirm_operation(     │
    │    confirm_id="xxx",      │
    │    user="admin",          │
    │    operation_key="..."    │
    │  )                        │
    │ ────────────────────────> │
    │                           │ 写入确认缓存
    │                           │ (有效期: 300秒)
    │ ④ 确认成功               │
    │ <──────────────────────── │
    │                           │
    │  ⑤ sendRedfish(           │
    │    method="POST",         │
    │    URL="/red/v1/..."      │
    │  )                        │
    │ ────────────────────────> │
    │                           │ 安全检查: POST→高危→confirm
    │                           │ 确认缓存: 已确认(在有效期内)
    │                           │ → 放行，继续执行
    │ ⑥ 返回操作结果           │
    │ <──────────────────────── │
```

---

## 4 安全审计方案

### 4.1 安全审计总体架构

SWRDMCPServer 的安全审计体系由三个维度构成：**操作日志审计**、**高危操作拦截**、**安全预警通知**。三者通过装饰器模式有机集成，形成完整的"预防 → 记录 → 预警"安全闭环。

```
┌─────────────────────────────────────────────────────────────────┐
│                     安全审计总体架构                              │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    预防层                                 │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │ @with_high_risk_check                               ││   │
│  │  │  ├─ 风险评估引擎 (_assess_risk)                     ││   │
│  │  │  ├─ 策略执行引擎 (_get_action)                      ││   │
│  │  │  ├─ 确认缓存管理 (_confirm_cache)                   ││   │
│  │  │  └─ 拦截执行 (block / confirm)                      ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    记录层                                 │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │ @with_operation_log                                 ││   │
│  │  │  ├─ 全生命周期日志 (request_start/end/error)        ││   │
│  │  │  ├─ 敏感信息脱敏 (_sanitize_parameters)             ││   │
│  │  │  ├─ 日志轮转管理 (RotatingFileHandler)             ││   │
│  │  │  └─ 双通道输出 (控制台 + 文件)                      ││   │
│  │  └─────────────────────────────────────── ─────────────┘│   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    员警层                                 │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │ alert_handler                                       ││   │
│  │  │  ├─ 员警判断 (_should_alert)                        ││   │
│  │  │  ├─ 模板渲染 (_render_template)                     ││   │
│  │  │  ├─ 渠道分发 (邮件/钉钉/企微/Webhook)              ││   │
│  │  │  └─ 员警日志 (CRITICAL 级别)                        ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 操作日志

#### 4.2.1 实现原理

操作日志通过 `@with_operation_log` 装饰器实现，采用 Python 标准库 `logging` 模块，基于 `RotatingFileHandler` 实现日志轮转。

**装饰器包装机制**：

```
┌─────────────────────────────────────────────────────────────────┐
│ @with_operation_log 装饰器工作原理                               │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ wrapper(*args, **kwargs)                                │   │
│  │                                                         │   │
│  │  ① 生成 request_id = str(uuid.uuid4())                  │   │
│  │  ② 提取用户标识: userName → ctx.client_id → "unknown"  │   │
│  │  ③ 提取参数: func.__code__.co_varnames → args/kwargs   │   │
│  │  ④ 参数脱敏: _sanitize_parameters()                     │   │
│  │  ⑤ 记录 request_start (INFO)                           │   │
│  │  ⑥ 记录开始时间 start_time = time.time()               │   │
│  │  ⑦ 执行核心逻辑: result = func(*args, **kwargs)        │   │
│  │  ⑧ 记录 request_end (INFO, status=success)             │   │
│  │  ⑨ 返回 result                                         │   │
│  │                                                         │   │
│  │  异常路径:                                               │   │
│  │  except Exception as e:                                 │   │
│  │    ⑧' 记录 request_error (ERROR, exc_info=True)        │   │
│  │    ⑨' 记录 request_end (WARNING, status=failed)        │   │
│  │    ⑩' re-raise 异常                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**日志系统初始化**：

```
┌─────────────────────────────────────────────────────────────────┐
│ _setup_logger() 初始化流程                                      │
│                                                                 │
│  Logger("mcp_operation")                                        │
│  ├─ 控制台处理器 (StreamHandler)                                │
│  │   ├─ 级别: CONSOLE_LEVEL (默认 DEBUG)                       │
│  │   └─ 格式: [%(asctime)s] %(levelname)s %(name)s - %(message)s
│  │                                                             │
│  └─ 文件处理器 (RotatingFileHandler)                            │
│      ├─ 路径: LOG_FILE (默认 logs/mcp_operation.log)           │
│      ├─ 级别: FILE_LEVEL (默认 DEBUG)                          │
│      ├─ 格式: %(asctime)s | %(levelname)s | %(name)s | %(message)s
│      ├─ 单文件最大: MAX_BYTES (默认 10 MB)                     │
│      ├─ 备份数量: BACKUP_COUNT (默认 30)                       │
│      └─ 编码: LOG_ENCODING (默认 utf-8)                        │
└─────────────────────────────────────────────────────────────────┘
```

**参数提取与脱敏机制**：

```
┌─────────────────────────────────────────────────────────────────┐
│ 参数提取与脱敏流程                                              │
│                                                                 │
│  func.__code__.co_varnames  →  获取函数参数名列表              │
│  │                                                             │
│  ├─ 遍历参数名列表，从 args/kwargs 中提取值
│  │   (跳过 "ctx" 参数)                                        │
│  │                                                             │
│  └─ _sanitize_parameters(params)
│      │                                                         │
│      ├─ 遍历所有参数
│      │                                                         │
│      ├─ 参数名（小写）包含以下关键词时 → 值替换为 "******"     │
│      │   ┌───────────────────────────────────────────────┐     │
│      │   │ password, pwd, secret, token,                │     │
│      │   │ apikey, api_key, auth, credential,           │     │
│      │   │ private_key, access_key                       │     │
│      │   └───────────────────────────────────────────────┘     │
│      │                                                         │
│      └─ 返回脱敏后的参数字典                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.2.2 日志记录内容详述

##### (1) request_start 事件

**日志级别**：INFO
**触发时机**：请求开始处理时
**记录内容**：

| 字段 | 说明 | 示例 |
|------|------|------|
| request_id | 请求唯一标识 (UUID) | `a3f2e1b0-1234-5678-9abc-def012345678` |
| tool_name | 工具名称 | `sendRedfish` / `sendIPMI` |
| user | 操作用户 | `admin` / `unknown` |
| parameters | 脱敏后的参数 | `{"pcIP":"192.168.1.100", "DevicePwd":"******"}` |

**日志示例**：
```
2026-04-22 10:30:15 | INFO | mcp_operation | request_start | request_id=a3f2e1b0-1234-5678-9abc-def012345678 | tool=sendRedfish | user=admin | params={"pcIP":"192.168.1.100","deviceIP":"10.0.0.1","deviceUser":"admin","DevicePwd":"******","method":"GET","URL":"/redfish/v1/Systems","body":""}
```

##### (2) request_end 事件

**日志级别**：INFO（成功）/ WARNING（失败）/ CRITICAL（拦截）
**触发时机**：请求处理完成时
**记录内容**：

| 字段 | 说明 | 示例 |
|------|------|------|
| request_id | 请求唯一标识 | `a3f2e1b0-1234-5678-9abc-def012345678` |
| tool_name | 工具名称 | `sendRedfish` |
| user | 操作用户 | `admin` |
| status | 请求状态 | `success` / `failed` / `blocked` |
| elapsed_ms | 耗时（毫秒） | `1523.45` |
| result_preview | 结果摘要（前200字符） | `{"Members":[{"@odata.id":"/redfish/v1/Systems/1"}...` |

**日志示例（成功）**：
```
2026-04-22 10:30:16 | INFO | mcp_operation | request_end | request_id=a3f2e1b0-1234-5678-9abc-def012345678 | tool=sendRedfish | user=admin | status=success | elapsed=1523.45ms | result={"Members":[{"@odata.id":"/redfish/v1/Systems/1"}]}
```

**日志示例（失败）**：
```
2026-04-22 10:31:20 | WARNING | mcp_operation | request_end | request_id=b4f3e2c1-2345-6789-abcd-ef0123456789 | tool=sendIPMI | user=admin | status=failed | elapsed=30001.23ms | result={"error":"Request failed: ConnectionTimeout"}
```

##### (3) request_error 事件

**日志级别**：ERROR
**触发时机**：请求处理过程中发生异常时
**记录内容**：

| 字段 | 说明 | 示例 |
|------|------|------|
| request_id | 请求唯一标识 | `b4f3e2c1-2345-6789-abcd-ef0123456789` |
| tool_name | 工具名称 | `sendIPMI` |
| user | 操作用户 | `admin` |
| error_type | 异常类型 | `RequestException` / `ValidationError` |
| error_message | 异常消息 | `ConnectionTimeout: HTTP请求超时` |
| parameters | 脱敏后的参数 | `{"pcIP":"192.168.1.100", "DevicePwd":"******"}` |
| suggestion | 建议信息 | `请检查代理服务是否可用` |
| exc_info | 完整堆栈信息 | `Traceback (most recent call last): ...` |

**日志示例**：
```
2026-04-22 10:31:20 | ERROR | mcp_operation | request_error | request_id=b4f3e2c1-2345-6789-abcd-ef0123456789 | tool=sendIPMI | user=admin | error=RequestException | message=ConnectionTimeout: HTTP请求超时 | params={"pcIP":"192.168.1.100","DevicePwd":"******"} | suggestion=请检查代理服务是否可用
Traceback (most recent call last):
  File "decorators/logging_decorator.py", line xx, in wrapper
    result = func(*args, **kwargs)
  ...
requests.exceptions.ConnectionTimeout: HTTP请求超时
```

##### (4) security_alert 事件

**日志级别**：CRITICAL
**触发时机**：安全员警触发时（block 或 confirm 策略）
**记录内容**：

| 字段 | 说明 | 示例 |
|------|------|------|
| risk_level | 风险等级 | `严重` / `高危` |
| operation | 操作标识 | `sendRedfish:DELETE:10.0.0.1:/redfish/v1/AccountService/Accounts/1` |
| reason | 风险原因 | `Redfish DELETE 操作可能导致数据丢失` |
| user | 操作用户 | `admin` |
| request_id | 请求唯一标识 | `c5f3e3d2-3456-7890-bcde-f01234567890` |
| timestamp | UTC 时间戳 | `2026-04-22T02:30:15.123456Z` |

**日志示例**：
```
2026-04-22 10:30:15 | CRITICAL | mcp_operation | security_alert | risk_level=严重 | operation=sendRedfish:DELETE:10.0.0.1:/redfish/v1/AccountService/Accounts/1 | reason=Redfish DELETE 操作可能导致数据丢失 | user=admin | request_id=c5f3e3d2-3456-7890-bcde-f01234567890 | timestamp=2026-04-22T02:30:15.123456Z
```

#### 4.2.3 日志轮转策略

```
┌─────────────────────────────────────────────────────────────────┐
│ 日志轮转策略                                                    │
│                                                                 │
│  RotatingFileHandler 配置:                                      │
│  ├─ 单文件最大: 10 MB (MAX_BYTES = 10485760)                   │
│  ├─ 备份文件数: 30 (BACKUP_COUNT = 30)                        │
│  │                                                             │
│  文件命名规则:                                                  │
│  ├─ mcp_operation.log         (当前日志)                      │
│  ├─ mcp_operation.log.1       (第1次轮转)                     │
│  ├─ mcp_operation.log.2       (第2次轮转)                     │
│  │  ...                                                        │
│  └─ mcp_operation.log.30      (第30次轮转，最旧)              │
│                                                                 │
│  轮转触发: 当前日志文件超过 MAX_BYTES 时:                       │
│  1. 关闭当前文件                                                │
│  2. .log.29 → .log.30 (最旧的被删除)                          │
│  3. .log.28 → .log.29                                         │
│  4. 逐个重命名 ...                                              │
│  5. .log.1 → .log.2                                           │
│  6. .log → .log.1                                              │
│  7. 创建新的 .log 文件                                         │
│                                                                 │
│  总存储容量: 约 10MB × (1 + 30) = 310 MB                      │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.2.4 敏感信息脱敏规则

| 敏感关键词 | 匹配方式 | 脱敏处理 | 匹配示例 |
|------------|----------|----------|----------|
| `password` | 参数名（不区分大小写）包含该关键词 | 值替换为 `******` | `DevicePwd`, `password` |
| `pwd` | 同上 | 同上 | `DevicePwd`, `pwd` |
| `secret` | 同上 | 同上 | `client_secret` |
| `token` | 同上 | 同上 | `access_token` |
| `apikey` | 同上 | 同上 | `apikey` |
| `api_key` | 同上 | 同上 | `api_key` |
| `auth` | 同上 | 同上 | `authorization` |
| `credential` | 同上 | 同上 | `credential` |
| `private_key` | 同上 | 同上 | `private_key` |
| `access_key` | 同上 | 同上 | `access_key` |

**脱敏示例**：
```
原始参数: {"deviceUser":"admin", "DevicePwd":"mySecret123", "pcIP":"192.168.1.100", "token":"abc123xyz"}
脱敏后:   {"deviceUser":"admin", "DevicePwd":"******", "pcIP":"192.168.1.100", "token":"******"}
```

---

### 4.3 高危操作的定义与阻拦

#### 4.3.1 风险等级定义

系统定义了四个风险等级，每个等级对应不同的处理策略：

```
┌─────────────────────────────────────────────────────────────────┐
│ 风险等级体系                                                    │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  低危    │  │  中危    │  │  高危    │  │  严重    │       │
│  │  LOW     │  │  MEDIUM  │  │  HIGH    │  │  CRITICAL│       │
│  │  策略:log│  │  策略:log│  │策略:confirm│  │策略:block│       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│       ▲            ▲             ▲             ▲              │
│       │            │             │             │              │
│  只读查询     未知操作       修改配置       数据丢失风险       │
│  无副作用     风险不确定     可能影响系统   可能造成不可逆损害  │
└─────────────────────────────────────────────────────────────────┘
```

**详细定义**：

| 风险等级 | 英文标识 | 中文标识 | 触发条件 | 风险描述 | 处理策略 |
|----------|----------|----------|----------|----------|----------|
| 低危 | LOW | 低危 | Redfish GET 操作 | Redfish {method} 操作为只读查询，无副作用 | log（记录日志后放行） |
| 中危 | MEDIUM | 中危 | 未匹配到 method 的操作（如 IPMI 命令） | Redfish {method} 操作风险未知，默认为中危 | log（记录日志后放行） |
| 高危 | HIGH | 高危 | Redfish POST / PATCH / PUT 操作 | Redfish {method} 操作可能修改设备配置 | confirm（需要确认后放行） |
| 严重 | CRITICAL | 严重 | Redfish DELETE 操作 | Redfish {method} 操作可能导致数据丢失 | block（直接拦截，禁止执行） |

#### 4.3.2 风险评估引擎

风险评估引擎 `_assess_risk()` 通过 HTTP Method 与风险等级的映射关系，自动评估每次操作的风险等级：

```
┌─────────────────────────────────────────────────────────────────┐
│ 风险评估引擎 (_assess_risk)                                     │
│                                                                 │
│  输入: func_name (工具名称), params (参数字典)                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ① 从 params 中提取 method 参数                         │   │
│  │     ├─ 存在 method → 继续评估                          │   │
│  │     └─ 不存在 method → 使用 "default" 映射 → 中危      │   │
│  │                                                         │   │
│  │ ② 查询 RISK_LEVEL_MAPPING 配置表                       │   │
│  │     ┌──────────────────────────────────────────┐       │   │
│  │     │ method   │ 风险等级 │ 策略               │       │   │
│  │     ├──────────────────────────────────────────┤       │   │
│  │     │ GET      │ 低危     │ log               │       │   │
│  │     │ POST     │ 高危     │ confirm           │       │   │
│  │     │ PATCH    │ 高危     │ confirm           │       │
│  │     │ PUT      │ 高危     │ confirm           │       │
│  │     │ DELETE   │ 严重     │ block             │       │   │
│  │     │ (其他)   │ 中危     │ log               │       │
│  │     └──────────────────────────────────────────┘       │   │
│  │                                                         │   │
│  │ ③ 生成风险原因描述                                      │   │
│  │     ├─ 低危: "Redfish {method} 操作为只读查询"         │   │
│  │     ├─ 中危: "Redfish {method} 操作风险未知，默认为中危"│   │
│  │     ├─ 高危: "Redfish {method} 操作可能修改设备配置"   │   │
│  │     └─ 严重: "Redfish {method} 操作可能导致数据丢失"   │   │
│  │                                                         │
│  │ ④ 返回 (risk_level, reason)                            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.3.3 拦截策略详解

系统定义了四种拦截策略，根据风险等级自动选择：

```
┌─────────────────────────────────────────────────────────────────┐
│ 拦截策略执行流程                                                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ @with_high_risk_check 装饰器                            │   │
│  │                                                         │   │
│  │ ① 检查 SECURITY_ENABLED 全局开关                       │   │
│  │     └─ False → 直接放行（跳过所有安全检查）             │   │
│  │                                                         │
│  │ ② 生成 request_id (UUID)                               │   │
│  │                                                         │
│  │ ③ 提取用户标识 (userName → ctx.client_id → "unknown")  │   │
│  │                                                         │
│  │ ④ 提取所有参数                                         │   │
│  │                                                         │
│  │ ⑤ 调用 _assess_risk() 评估风险等级                     │   │
│  │                                                         │
│  │ ⑥ 构造 operation_key = "{tool}:{method}:{deviceIP}:{URL}"
│  │                                                         │
│  │ ⑦ 查询策略 (_get_action)                               │   │
│  │     │                                                   │   │
│  │     ├─── block ─────────────────────────────────┐       │   │
│  │     │    风险等级: 严重                          │       │   │
│  │     │    处理:                                   │       │   │
│  │     │    ├─ send_alert() 发送安全员警            │       │   │
│  │     │    └─ raise SecurityCheckError             │       │   │
│  │     │       携带: risk_level, operation, reason  │       │   │
│  │     │       效果: 操作被完全阻止，不可执行        │       │
│  │     │                                           │       │
│  │     ├─── confirm ───────────────────────────────┐       │   │
│  │     │    风险等级: 高危                          │       │   │
│  │     │    处理:                                   │       │
│  │     │    ├─ _check_confirm_cache()               │       │   │
│  │     │    │   ├─ 已确认(在有效期内) → 放行        │       │   │
│  │     │    │   └─ 未确认 →                        │       │
│  │     │    │       ├─ send_alert() 发送安全员警    │       │   │
│  │     │    │       └─ raise ConfirmationRequired   │       │
│  │     │    │           携带: confirm_id, risk_level,│       │   │
│  │     │    │                 operation, reason      │       │   │
│  │     │    │           效果: 需要用户确认后才能执行 │       │   │
│  │     │    └─ confirm_operation() 写入确认缓存     │       │
│  │     │                                           │       │
│  │     ├─── log ───────────────────────────────────┐       │   │
│  │     │    风险等级: 低危 / 中危                   │       │
│  │     │    处理:                                   │       │   │
│  │     │    ├─ 高危/严重 → WARNING 级别日志         │       │   │
│  │     │    └─ 其他 → INFO 级别日志                 │       │
│  │     │    效果: 记录日志后放行                     │       │
│  │     │                                           │       │
│  │     └─── allow ────────────────────────────────┘       │   │
│  │          风险等级: 无(默认)                           │       │   │
│  │          处理: 直接放行，不记录日志                   │       │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.3.4 确证缓存机制

对于 `confirm` 策略（高危操作），系统实现了确认缓存机制，允许用户在确认后在一定时间内免确认地重复执行相同操作：

```
┌─────────────────────────────────────────────────────────────────┐
│ 确认缓存机制                                                    │
│                                                                 │
│  数据结构: _confirm_cache (内存字典)                            │
│  ├─ Key: (user, operation_key)                                 │
│  │   ├─ user: 操作用户标识                                     │
│  │   └─ operation_key: "{tool_name}:{method}:{deviceIP}:{URL}" │
│  │                                                             │
│  └─ Value: (confirmed_at, confirmed)
│      ├─ confirmed_at: 确认时间戳                               │
│      └─ confirmed: 布尔值，是否已确认                          │
│                                                                 │
│  有效期: CONFIRM_EXPIRE_SECONDS (默认 300秒 = 5分钟)           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 确认流程:                                               │   │
│  │                                                         │   │
│  │  ① 用户发起高危操作 (POST/PATCH/PUT)                    │   │
│  │     │                                                   │   │
│  │     ▼                                                   │   │
│  │  ② _check_confirm_cache() 检查缓存                      │   │
│  │     │                                                   │   │
│  │     ├─ 缓存命中 + confirmed=True + 未过期 → 放行        │   │
│  │     │                                                   │   │
│  │     └─ 缓存未命中 或 已过期 → 抛出 ConfirmationRequired │   │
│  │         │                                               │   │
│  │         ▼                                               │   │
│  │  ③ 用户调用 confirm_operation()                         │   │
│  │     │   写入缓存: (user, operation_key) → (now, True)   │   │
│  │     │                                                   │   │
│  │     ▼                                                   │   │
│  │  ④ 用户再次发起相同操作                                  │   │
│  │     │   _check_confirm_cache() → 缓存命中 → 放行       │   │
│  │     │                                                   │   │
│  │     ▼                                                   │   │
│  │  ⑤ 5分钟后缓存过期，需要重新确认                        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**operation_key 构造规则**：

| 字段 | 来源 | 说明 |
|------|------|------|
| tool_name | 函数名 | `sendRedfish` / `sendIPMI` |
| method | 参数 method | HTTP 方法 |
| deviceIP | 参数 deviceIP | 目标设备 IP |
| URL | 参数 URL | Redfish 路径 |

**示例**：`sendRedfish:POST:10.0.0.1:/redfish/v1/AccountService/Accounts`

#### 4.3.5 安全异常类型

| 异常类 | 触发策略 | 携带信息 | 处理方式 |
|--------|----------|----------|----------|
| `SecurityCheckError` | block | `risk_level`, `operation`, `reason` | 操作被完全阻止，不可执行 |
| `ConfirmationRequired` | confirm | `confirm_id`, `risk_level`, `operation`, `reason` | 需要用户确认后才能执行 |
| `AuthenticationError` | auth | 无额外信息 | 认证失败，返回 `{"error": "认证失败", "message": "..."}` |

**异常信息示例**：

```json
// SecurityCheckError (block 策略)
{
    "error": "操作已被安全策略拦截",
    "risk_level": "严重",
    "operation": "sendRedfish:DELETE:10.0.0.1:/redfish/v1/AccountService/Accounts/1",
    "reason": "Redfish DELETE 操作可能导致数据丢失"
}

// ConfirmationRequired (confirm 策略)
{
    "error": "高危操作需要确认",
    "confirm_id": "a3f2e1b0-1234-5678-9abc-def012345678",
    "risk_level": "高危",
    "operation": "sendRedfish:POST:10.0.0.1:/redfish/v1/AccountService/Accounts",
    "reason": "Redfish POST 操作可能修改设备配置"
}

// AuthenticationError (auth 认证失败)
{
    "error": "认证失败",
    "message": "Token 已过期，请重新调用 authenticate 工具获取 Token"
}
```

---

### 4.4 安全预警通知

#### 4.4.1 预警触发条件

```
┌─────────────────────────────────────────────────────────────────┐
│ 员警触发判断 (_should_alert)                                    │
│                                                                 │
│  条件1: ALERT_ENABLED == True (全局开关)                        │
│  AND
│  条件2: risk_level >= ALERT_MINIMUM_LEVEL (风险等级阈值)        │
│                                                                 │
│  默认阈值: high (高危)
│                                                                 │
│  ┌──────────────────────────────────────────────┐               │
│  │ 等级优先级: low=0, medium=1, high=2, critical=3│               │
│  │                                               │               │
│  │ ALERT_MINIMUM_LEVEL=high → high(2) 和 critical(3) 触发员警   │
│  │                                               │               │
│  │ 触发场景:                                     │               │
│  │ 1. block 策略拦截 (严重操作)                  │               │
│  │ 2. confirm 策略未确认 (高危操作)              │               │
│  └──────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.4.2 预警上下文信息

每次员警携带以下上下文信息，用于模板渲染：

| 变量 | 说明 | 示例 |
|------|------|------|
| `{risk_level}` | 风险等级（中文） | `严重` |
| `{operation}` | 操作标识 | `sendRedfish:DELETE:10.0.0.1:/redfish/v1/...` |
| `{reason}` | 风险原因 | `Redfish DELETE 操作可能导致数据丢失` |
| `{user}` | 操作用户 | `admin` |
| `{request_id}` | 请求唯一标识 | `c5f3e3d2-3456-7890-bcde-f01234567890` |
| `{timestamp}` | UTC 时间戳 | `2026-04-22T02:30:15.123456Z` |

#### 4.4.3 预警渠道

| 渠道 | 实现函数 | 协议 | 配置项 | 状态 |
|------|----------|------|--------|------|
| 邮件 | `_send_email()` | SMTP / SMTP_SSL | 服务器、端口、发件人、收件人、模板 | 默认禁用 |
| 钉钉 | `_send_dingtalk()` | Webhook + HMAC-SHA256 签名 | Webhook URL、密钥、消息模板 | 默认禁用 |
| 企业微信 | `_send_wecom()` | Webhook | Webhook URL、消息模板 | 默认禁用 |
| 自定义 Webhook | `_send_webhook()` | HTTP POST | URL、方法、请求头、请求体模板 | 默认禁用 |

**钉钉签名实现**：
```
┌─────────────────────────────────────────────────────────────────┐
│ 钉钉签名算法 (_sign_dingtalk)                                   │
│                                                                 │
│  1. 构造签名字符串: "{timestamp}\n{secret}"                     │
│  2. 使用 HMAC-SHA256 算法，以 secret 为密钥                     │
│  3. 对签名字符串进行签名                                        │
│  4. 将签名结果 Base64 编码                                      │
│  5. 将 Base64 结果 URL 编码                                     │
│  6. 拼接到 Webhook URL:                                         │
│     {webhook_url}&timestamp={timestamp}&sign={sign}             │
└─────────────────────────────────────────────────────────────────┘
```

**员警分发流程**：
```
┌─────────────────────────────────────────────────────────────────┐
│ send_alert() 员警分发流程                                       │
│                                                                 │
│  ① _should_alert() → 判断是否满足员警条件                      │
│     └─ 不满足 → 直接返回                                       │
│                                                                 │
│  ② 构建员警上下文 (含 UTC 时间戳)                              │
│                                                                 │
│  ③ 记录 CRITICAL 级别日志 (security_alert 事件)                │
│                                                                 │
│  ④ 遍历所有已启用的渠道:
│     ├─ email.enabled? → _send_email()                           │
│     ├─ dingtalk.enabled? → _send_dingtalk()                     │
│     ├─ wecom.enabled? → _send_wecom()                           │
│     └─ webhook.enabled? → _send_webhook()                       │
│     │
│     │  每个渠道独立 try/except
│     │  失败不影响其他渠道
│     │  仅记录错误日志
│     ▼
│  ⑤ 返回 (无返回值，仅副作用)                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5 附录：配置参考

### 5.1 config.yaml（日志配置）

```yaml
log_level: DEBUG
log_file: logs/mcp_operation.log
max_bytes: 10485760        # 10 MB
backup_count: 30
log_encoding: utf-8
console_level: DEBUG
console_format: "[%(asctime)s] %(levelname)s %(name)s - %(message)s"
console_date_format: "%Y-%m-%d %H:%M:%S"
file_level: DEBUG
file_format: "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
file_date_format: "%Y-%m-%d:%H:%M:%S"
```

### 5.2 security_config.yaml（安全策略与认证配置）

```yaml
# 安全策略配置
enabled: true
confirm_expire_seconds: 300
risk_level_mapping:
  GET: low
  POST: high
  PATCH: high
  PUT: high
  DELETE: critical
  default: medium
actions:
  critical: block      # 直接拦截
  high: confirm        # 需要确认
  medium: log          # 仅记录日志
  low: log             # 仅记录日志

# ──────────────────────────────────────────────
# 用户认证配置
# ──────────────────────────────────────────────
auth:
  # 是否启用用户认证（全局开关）
  # 启用后，所有 MCP 请求必须携带有效 Token
  enabled: true

  # 服务端固定 Token（用于 MCP Client 配置）
  # 若为空，则启动时自动生成随机 Token 并打印到控制台
  # 建议生产环境设置为固定值，便于 MCP Client 配置
  token: "swrd-mcp-server-token-2026"

  # 用户名/密码列表（用于 authenticate 工具登录）
  # 登录成功后会生成临时 Token，有效期由 token_expire_seconds 控制
  users:
    admin: admin123
    operator: operator123

  # 用户登录 Token 有效期（秒）
  token_expire_seconds: 3600
```

### 5.3 alert_config.yaml（预警配置）

```yaml
enabled: true
minimum_level: high
channels:
  email:
    enabled: false
    smtp_server: ""
    smtp_port: 465
    smtp_ssl: true
    username: ""
    password: ""
    from_addr: ""
    to_addrs: []
    subject_template: "安全员警: {risk_level} - {operation}
    body_template: "..."
  dingtalk:
    enabled: false
    webhook_url: ""
    secret: ""
    message_template: "..."
  wecom:
    enabled: false
    webhook_url: ""
    message_template: "..."
  webhook:
    enabled: false
    url: ""
    method: "POST"
    headers: {}
    body_template: "..."
```

---

## 6 附录：已知风险与改进建议

| 序号 | 风险项 | 级别 | 说明 | 改进建议 |
|------|--------|------|------|----------|
| 1 | IPMI 命令风险评估不足 | 高 | `_assess_risk()` 仅基于 `method` 参数评估风险，`sendIPMI` 无 `method` 参数，所有 IPMI 命令（包括 `power reset` 等）均被默认为中危，仅记录日志 | 增加 IPMI 命令风险评估规则，对 `power reset`, `mc reset`, `user set` 等高危命令定义专门的风险等级 |
| 2 | 代理通信未加密 | 高 | 与 PC 代理的通信使用 HTTP（非 HTTPS），设备凭证在网络中明文传输 | 改用 HTTPS，或在代理层实现加密通信 |
| 3 | ~~无认证机制~~ | ~~高~~ | ~~MCP Server 未实现任何认证，任何能连接到 SSE 端点的客户端均可执行操作~~ | ~~增加 API Key / Token 验证，或实现 IP 白名单~~ **已解决：已实现用户名/密码 + 临时 Token 双重认证机制（`@auth_required` 装饰器 + `AuthMiddleware` 中间件）|
| 4 | 确认缓存未持久化 | 中 | 确认缓存 `_confirm_cache` 存储在内存中，服务重启后丢失 | 改用 Redis 或数据库持久化确认状态 |
| 5 | IPMI 命令注入风险 | 高 | `command` 参数未做校验，理论上可能被用于执行任意命令 | 增加 IPMI 命令白名单校验，禁止非预期命令 |
| 6 | 密码明文传输 | 高 | `DevicePwd` 虽然在日志中脱敏，但在代理请求中以明文 JSON 传输 | 实现端到端加密，或使用密钥管理服务 |
| 7 | 异常信息泄露 | 低 | 错误返回中包含原始异常消息 (`str(e)`)，可能泄露内部信息 | 对返回给客户端的错误信息进行脱敏处理 |
| 8 | 装饰器执行顺序 | 低 | `@with_high_risk_check` 在 `@with_operation_log` 之外，安全拦截不会产生操作日志（仅产生安全日志和员警） | 考虑调整装饰器顺序，或在安全拦截时也记录操作日志 |
| 9 | Token 缓存未持久化 | 中 | 临时 Token 缓存 `_token_cache` 存储在内存中，服务重启后所有 Token 失效，用户需重新认证 | 改用 Redis 或数据库持久化 Token 状态 |
| 10 | 用户密码明文存储 | 中 | 用户密码在 `security_config.yaml` 中以明文存储，存在泄露风险 | 改用哈希存储（如 bcrypt），或集成外部认证服务（LDAP/AD） |
