---
name: bmc-control
description: 基于映射表的智能BMC设备浏览器控制技能。通过MCP服务器控制浏览器，实现对H3C BMC设备的自动化操作，包括登录、页面导航、LLDP开关控制及页面探索。触发词：bmc控制、bmc登录、bmc导航、打开LLDP、关闭LLDP、bmc探索。
metadata:
  version: "0.0.1"
---

# BMC Control Skill

基于映射表的智能BMC设备浏览器控制技能。通过MCP服务器控制浏览器，实现对H3C BMC设备的自动化操作。

## 默认控制模式：前台浏览器控制

**BMC控制默认使用前台模式（浏览器控制）**，即通过 MCP 浏览器工具（`browserRun`、`browserOpen`、`browserScreenshot`、`browserClose`）直接操控浏览器界面完成所有操作。

**禁止**使用以下方式作为默认控制手段：
- ❌ `curl` 命令发送 HTTP/Redfish 请求
- ❌ Python 脚本直接调用 REST API
- ❌ 绕过浏览器直接发送网络请求

**仅在以下情况才考虑非浏览器方式**：
- 浏览器无法完成的底层操作（如 IPMI 命令）
- 批量数据查询等浏览器操作效率极低的场景
- 用户明确要求使用非浏览器方式

**原因**：浏览器前台模式能真实模拟用户操作，验证 Web UI 的完整功能链路，包括页面渲染、交互逻辑、二次确认弹窗等，这是 curl/脚本无法覆盖的。

## 功能

- **智能映射表查询** - 先查映射表，根据映射表执行操作
- **自动探索更新** - 映射表中没有时自动探索并更新
- **LLDP开关控制** - 一键启用/禁用LLDP
- **页面导航** - 快速导航到任意BMC页面
- **登录自动化** - 自动登录（凭据从SystemTest.mdc读取）

## 工作流程

### 登录BMC
1. 从 `.codebuddy/rules/SystemTest.mdc` 获取设备连接信息（设备IP、用户名、密码）
2. 逐条调用 `browserRun` 执行登录操作（每次一个 action）：
   - `browserRun(actions=[{"type": "goto", "url": f"https://{device_ip}"}])`
   - `browserRun(actions=[{"type": "fill", "selector": "#username", "text": username}])`
   - `browserRun(actions=[{"type": "fill", "selector": "#password", "text": password}])`
   - `browserRun(actions=[{"type": "click", "selector": "button.ant-btn-primary"}])`
   - `browserRun(actions=[{"type": "wait_for_load_state", "state": "networkidle"}])

### 页面导航
1. 从 `.codebuddy/rules/SystemTest.mdc` 获取设备连接信息
2. 先查映射表 `scripts/bmc_map.json`，找不到则使用默认路径规则，获取目标 URL
3. 逐条调用 `browserRun` 执行导航：
   - `browserRun(actions=[{"type": "goto", "url": target_url}])`
   - `browserRun(actions=[{"type": "wait_for_load_state", "state": "networkidle"}])

### LLDP开关控制
1. 从 `.codebuddy/rules/SystemTest.mdc` 获取设备连接信息
2. 先导航到 LLDP 页面（参照"页面导航"流程）
3. 逐条调用 `browserRun` 执行开关操作（每次一个 action），如启用：
   - `browserRun(actions=[{"type": "click", "selector": ".ant-switch:not(.ant-switch-checked)"}])`
   - `browserRun(actions=[{"type": "click", "selector": "button.ant-btn-primary"}])`
4. 禁用则将选择器改为 `.ant-switch.ant-switch-checked`

### 页面探索
1. 从 `.codebuddy/rules/SystemTest.mdc` 获取设备连接信息
2. 先导航到目标页面（参照"页面导航"流程）
3. 调用 `browserRun` 执行探索操作（单条 eval）：
   - `browserRun(actions=[{"type": "eval", "expression": "() => ({url:window.location.href, title:document.title, sidebar:Array.from(document.querySelectorAll('.ant-menu-item,.ant-menu-submenu-title')).map(m=>m.textContent.trim()).filter(t=>t.length>0&&t.length<30&&t!=='···'), buttons:Array.from(document.querySelectorAll('button')).map(b=>b.textContent.trim()).filter(t=>t.length>0).slice(0,10), links:Array.from(document.querySelectorAll('a')).map(a=>a.textContent.trim()).filter(t=>t.length>0&&t.length<30).slice(0,10)})"}])`

### 通用操作（任意页面/弹窗）
对于未封装为独立函数的操作，**逐条调用 `browserRun`，每次只执行一个 action**，避免多条命令合并导致超时卡住。

**每步执行后检查返回结果，确认成功后再执行下一步。**

辅助函数（用于生成单个 action）：
- `bmc_fill_form({"1": "192.168.33.198", "4": "80"})` — 填写弹窗表单，key 为表单项序号（返回多个 action，需逐个执行）
- `bmc_fill_form_with_range({"1": ["192.168.33.1", "192.168.33.254"], "3": ["80", "443"]})` — 填写弹窗表单，支持范围填写（如IP范围、端口范围）
- `bmc_confirm()` — 等待并点击二次确认弹窗的确认按钮

**示例：添加防火墙黑名单（逐条 browserRun）**
```python
# 设备连接信息从 .codebuddy/rules/SystemTest.mdc 获取
device_ip = "..."  # 从SystemTest.mdc读取

# 第1步：导航到防火墙页面
browserRun(actions=[{"type": "goto", "url": f"https://{device_ip}/security/firewall"}])
# 第2步：等待页面加载
browserRun(actions=[{"type": "wait_for_load_state", "state": "networkidle"}])
# 第3步：点击添加按钮
browserRun(actions=[{"type": "eval", "expression": "() => { document.querySelectorAll('.add-btn')[0].click(); return 'clicked'; }"}])
# 第4步：等待弹窗加载
browserRun(actions=[{"type": "wait_for_load_state", "state": "networkidle"}])
# 第5步：填写IP范围（第1项起始IP，第2项结束IP）
browserRun(actions=[{"type": "fill", "selector": ".ant-modal-body .ant-form-item:nth-child(1) input.ant-input", "text": "192.168.33.1"}])
browserRun(actions=[{"type": "fill", "selector": ".ant-modal-body .ant-form-item:nth-child(2) input.ant-input", "text": "192.168.33.254"}])
# 第6步：填写端口范围（第3项起始端口，第4项结束端口）
browserRun(actions=[{"type": "fill", "selector": ".ant-modal-body .ant-form-item:nth-child(3) input.ant-input", "text": "80"}])
browserRun(actions=[{"type": "fill", "selector": ".ant-modal-body .ant-form-item:nth-child(4) input.ant-input", "text": "443"}])
# 第7步：首次确认
browserRun(actions=[{"type": "eval", "expression": "() => { document.querySelector('.ant-modal').querySelector('.ant-btn-primary').click(); return 'clicked'; }"}])
# 第8步：检查并处理二次确认（如有）
browserRun(actions=bmc_confirm())
```

**示例：使用 bmc_fill_form_with_range 添加防火墙规则**
```python
# 导入辅助函数
from .codebuddy.skills.bmc-control.scripts.bmc_control import bmc_fill_form_with_range

# 填写IP范围和端口范围
actions = bmc_fill_form_with_range({
    "1": ["192.168.33.1", "192.168.33.254"],  # IP范围：第1项起始，第2项结束
    "3": ["80", "443"]  # 端口范围：第3项起始，第4项结束
})
# 逐条执行
for action in actions:
    browserRun(actions=[action])
```

## 支持的页面

- 登录页、Dashboard
- 系统管理（系统信息、存储管理、电源管理等）
- BMC设置（网络设置、LLDP、NTP等）
- 远程服务（服务设置、远程控制台、虚拟媒体等）
- 运维诊断（日志、告警、配置管理等14个子功能）
- 固件&软件（固件清单、更新等）
- 用户&安全（用户管理、防火墙、SSL证书等）
- DEBUG（告警计数、I2C数据统计、BMC性能）

## 配置

- **设备连接信息**：从 `.codebuddy/rules/SystemTest.mdc` 读取，**不允许硬编码或自行猜测 IP 地址**
- 映射表：`scripts/bmc_map.json`

### userName 参数
调用所有 MCP 浏览器工具（`browserOpen`、`browserRun`、`browserScreenshot`、`browserClose`）时，**必须传入 `userName` 参数**，用于日志记录操作用户。`userName` 取当前系统登录用户名。

### MCP 工具调用方式
**必须通过 IDE 的 MCP Client（CodeBuddy）直接调用 MCP 工具**，如 `browserRun`、`sendRedfish`、`sendIPMI` 等。禁止使用 python 脚本或 curl 手动发 HTTP 请求绕过 MCP Client，否则会出现会话失效（401 Unauthorized）问题。MCP Client 已自动管理会话和认证，无需手动初始化。

## 重要注意事项

### 二次确认弹窗
H3C BMC Web 界面在部分操作（如添加规则、保存配置等）后，**可能会弹出二次确认弹窗**。注意：并非所有操作都有二次确认，删除操作通常无二次确认。操作流程中应：
1. 点击确认/保存按钮后，**检查是否出现二次确认弹窗**（`document.querySelectorAll('.ant-modal-wrap')` 数量增加）
2. 若出现二次确认弹窗，在其中点击确认按钮
3. 若无二次确认弹窗，操作已直接生效，无需额外处理

检测二次确认弹窗的方法：
- 使用 `eval 获取 `document.querySelectorAll('.ant-modal-wrap')` 的数量和内容
- 二次确认弹窗通常是最后一个（`modals[modals.length - 1]`）
- 在二次确认弹窗中查找 `.ant-btn-primary` 按钮并点击

### 表单填写
- 使用 Playwright 的 `fill` 方法填写表单（而非 `eval 设置 value），确保 React 状态正确更新
- 表单输入框无 ID 时，使用 `.ant-modal-body .ant-form-item:nth-child(N) input.ant-input` 选择器定位

### 弹窗遮挡问题
- 当弹窗遮挡页面元素时，`click` 操作会超时失败
- 需先处理弹窗（点击确认/关闭），或使用 `eval 直接操作 DOM

## 依赖

- MCP服务器连接（SWRDMCPServer）
- PC代理服务（端口8888）
- 浏览器控制工具
