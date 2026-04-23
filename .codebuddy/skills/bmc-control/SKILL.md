# BMC Control Skill

基于映射表的智能BMC设备浏览器控制Skill。通过MCP服务器控制浏览器，实现对H3C BMC设备的自动化操作。

## 功能

- **智能映射表查询** - 先查映射表，根据映射表执行操作
- **自动探索更新** - 映射表中没有时自动探索并更新
- **LLDP开关控制** - 一键启用/禁用LLDP
- **页面导航** - 快速导航到任意BMC页面
- **登录自动化** - 自动登录（默认admin/Password@_）

## 触发词

- bmc控制
- bmc登录
- bmc导航
- 打开LLDP
- 关闭LLDP
- bmc探索

## 使用方法

### Python API

```python
from bmc_control import bmc_login, bmc_enable_lldp, bmc_disable_lldp, bmc_navigate

# 登录
actions = bmc_login()
# 通过MCP执行actions

# 启用LLDP
actions = bmc_enable_lldp()

# 禁用LLDP
actions = bmc_disable_lldp()

# 导航到页面
actions = bmc_navigate("remote_maintenance")
```

### 自然语言触发

```
帮我登录BMC
```
自动执行：
1. 打开浏览器
2. 访问 https://192.168.49.71
3. 填写用户名admin，密码Password@_
4. 点击登录

```
导航到LLDP设置页面
```

```
打开LLDP
关闭LLDP
```

```
探索运维诊断页面
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

映射表位置：`/tmp/env/bmc_complete_map.json`

默认设备IP：192.168.49.71
默认用户名：admin
默认密码：Password@_

## 依赖

- MCP服务器连接（SWRDMCPServer）
- PC代理服务（端口8888）
- 浏览器控制工具