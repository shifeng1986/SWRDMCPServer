---
name: system-test
description: 对服务器BMC进行测试的技能。能够支持IPMI、Redfish、SNMP、Web UI等界面的自动化测试。触发词：BMC测试、系统测试、自动化测试。
metadata:
  version: "0.0.1"
---

# BMC自动化测试工具 

## 概述
此技能利用SWRDMCPServer，打通黄区和绿区的环境，对BMC进行自动化测试。包括IPMI、Redfish、SNMP、Web UI等界面的自动化测试。

## 工作流程
### 第一步：根据用例获取对应的命令列表
1、根据当前需要测试的模块，在"资源引用"中找到对应模块的用例；
2、根据用例描述，在"资源引用"的命令参考手册中查找到对应的命令；
3、输出查找结果，等待用户确认当前查找结果是否符合预期；

待测试模式涉及xxx条用例，共计xxx个命令，具体如下：
| 用例描述 | 命令描述 | 命令字    |  
|---------|----------|----------|
| 用户管理 |          |          |
|         | 获取用户列表|  https：//ip:port/redfish/v1/AccountService/Accounts          |
|         | 获取指定用户详细信息 | https://ip:port/redfish/v1/AccountService/Accounts/1 |
请确认是否继续进行测试（y/n），如果确认继续，则继续执行第二步，否则退出。

### 第二步：依次执行每条命令，并获取执行结果。
IPMI：
- 如果返回值为0x00，则测试通过
- 如果返回值为其他值，则测试失败
Redfish：
- 如果HTTP状态码为200，则测试通过
- 如果HTTP状态码为其他值，则测试失败
如果某个用例对应的命令中，有一条命令返回失败，则认为该用例失败。

### 第三步：输出测试结果

总计测试xxx个模块，xxx条用例，xxx个命令，其中xxx个用例失败，xxx个用例通过。
| 用例描述 | 命令描述 | 命令字    |   测试结果 |
|---------|----------|----------|-----------|
| 用户管理 |          |          |
|         | 获取用户列表|  https：//ip:port/redfish/v1/AccountService/Accounts          | PASS,FAIL|
|         | 获取指定用户详细信息 | https://ip:port/redfish/v1/AccountService/Accounts/1 | PASS,FAIL|


##资源引用
- reference/H3C HDM3 IPMI基础命令参考手册.md - IPMI基础命令参考手册
- reference/H3C HDM2&HDM3 Redfish参考手册.md - Redfish参考手册
- reference/module case/UserManager.md - 用户管理用例

##质量要求
1. 对于SWRDMCPServer的调用，userName: str需要传入当前IDE所在系统登录时使用的用户名
2. 一条用例涉及哪些命令，必须严格遵守资源引用中对应模块所描述的命令，不允许自己随意添加命令
3. 不要并发调用，一条一条的去执行；