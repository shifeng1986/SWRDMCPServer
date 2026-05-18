# SWRDMCPServer
SWRD MCP Server，support Redfish、IPMI、playwright command forward

## 1 CodeBuddy MCP配置

将.codebuddy整个目录拷贝至自己的工程代码目录下，这样可以让codebuddy使用里面的skills和rules文件。

在CodeBuddyde MCP配置中进行如下配置：

```json
{
  "mcpServers": {
    "SWRDMCPServer": {
      "url": "http://10.41.6.8:8000/mcp",
      "transport": "streamable-http",
      "headers": {
        "Authorization": "Basic YWRtaW46YWRtaW4="
      },
      "disabled": false
    }
  }
}
```

其中"url": "http://10.41.6.8:8000/mcp",是SWRDMCPServer运行的IP地址；

"Authorization": "Basic czEwNjQzOnNoaXl1ZXhpITU="需要将Basic后面的字符串改为自己的域账号和密码，例如假设我的域账号是admin，密码也是admin则需要将"admin:admin"（注意中间有冒号分割）这个字符串进行base64编码（可以直接让AI进行编码）。

其余字段不用做修改。

## 2 rules&skills文件定制

### 2.1 rules文件定制

在SystemTest.mdc文件中，需要针对自己的测试环境进行定制，主要包括自己绿区PC的IP和BMC设备的IP信息。

绿区PC的IP配置：

```json
## 测试PC（PC代理）
- 大网IP（MCP服务器调用用）：10.41.6.8
- 设备网IP（访问BMC用）：192.168.106.43
- PC代理端口：8888
- PC代理地址：http://10.41.6.8:8888
```

写明自己绿区PC的大网IP和小网IP；

BMC设备的IP信息：

```json
## 测试设备（BMC）
- 测试设备IP：192.168.88.222
- 测试设备用户名：admin
- 测试设备密码：h3c@1234
```

包括设备的IP地址和用户名密码信息。

如果还需要进行串口操作以及FTP文件下载操作，还需要进行相关的配置：

```json
## 串口
- 测试设备串口交换机端口：192.168.0.200:3004

## 固件升级配置
- FTP服务器地址：10.141.228.15
- FTP用户名：ftp-CCSPLSmart1
- FTP密码：X2HWrK
- 固件文件路径：/data-out/xxx/xxx
- 完整固件URI：ftp://ftp-CCSPLSmart1:X2HWrK@10.141.228.15/data-out/w33199/0428/HDM3_3.05.01_FTC_signed.bin
```

### 2.2 skills定制

 对BMC进行自动化测试的skills是system-test。在这个skills中会定义每个模块的测试用例，但是目前只简单使用了用户管理的模块进行举例说明。

system-test/module case/yser management.md：

```markdown
---
description: 用户管理模块的用例列表
---

Redfish命令：
1、查询用户服务信息
2、获取用户列表信息
3、依次获取每个用户的详细信息
4、获取角色列表信息
5、依次获取指定角色信息


IPMI命令：
1、获取所有用户信息
2、获取用户摘要信息
```

如果想增加模块的话，可以在SKILL.md这个文件中的“资源引用”章节，进行增加：

```markdown
##资源引用
- reference/H3C HDM3 IPMI基础命令参考手册.md - IPMI基础命令参考手册
- reference/H3C HDM2&HDM3 Redfish参考手册.md - Redfish参考手册
- reference/module case/UserManager.md - 用户管理用例
```

## 3 运行&提示词

### 3.1运行说明

SWRDMCPServer的运行，依赖python3.12，并安装SWRDMCPServer目录下的requirements.txt中的依赖软件包（pip install），然后在SWRDMCPServer目录下执行python main.py即可，执行成功，有如下输出：

```
PS D:\Workspace\SWRDMCPServer\MCPServer> python main.py
============================================================
[认证] 用户认证已启用
[认证] 认证方式：连接级别 Basic Auth（HTTP层）
[认证] MCP Client 配置示例:
[认证]   "headers": {"Authorization": "Basic YWRtaW46YWRtaW4xMjM="}
============================================================

Starting SWRDMCPServer on 0.0.0.0:8000
[32mINFO[0m:     Started server process [[36m14572[0m]
[32mINFO[0m:     Waiting for application startup.
StreamableHTTP session manager started
[32mINFO[0m:     Application startup complete.
[32mINFO[0m:     Uvicorn running on [1mhttp://0.0.0.0:8000[0m (Press CTRL+C to quit)
```

绿区PC上代理程序的运行，也是依赖python3.12，并安装playwright（python -m playwright install），然后在TestTool目录下执行python local_proxy.py即可，执行成功，有如下输出：

```
PS D:\Workspace\SWRDMCPServer\TestTool> python local_proxy.py
Local Proxy 启动: https://0.0.0.0:8888
模式: 单线程，支持 Redfish/IPMI 转发和浏览器控制

支持的路径:
  - /redfish: 转发 Redfish 请求到目标设备
  - /ipmi: 执行 IPMI 命令
  - /browser/open: 打开浏览器
  - /browser/run: 执行浏览器操作
  - /browser/close: 关闭浏览器
  - /command: 执行本地命令（ftp_download/serial/ssh/tftp_server/shell）
```

在MCP Server运行起来后，在code buddy中的MCP配置页面，点击刷新按钮，应该就可以正常进行连接，如果连接报错，很有可能是部门信息被阻拦了，需要在security_config.yaml中增加部门信息，例如可将三级部门信息填进去:

```
      allowed_departments:
        - "平台软件开发部"
        - "平台软件开发部BMC开发一部"
        - "平台软件开发部BMC开发二部"
        - "平台软件开发部BMC开发三部"
```

### 2.3.2 提示词举例

```
I：请对我的BMC用户管理模块进行自动化测试。
```

AI会输出结果：

```
待测试模式涉及2条用例（Redfish + IPMI），共计7个命令，具体如下：

用例描述	命令描述	命令字
Redfish - 用户管理		
查询用户服务信息	GET /redfish/v1/AccountService
获取用户列表信息	GET /redfish/v1/AccountService/Accounts
依次获取每个用户的详细信息	GET /redfish/v1/AccountService/Accounts/{user_id}
获取角色列表信息	GET /redfish/v1/AccountService/Roles
依次获取指定角色信息	GET /redfish/v1/AccountService/Roles/{role_id}
IPMI - 用户管理		
获取所有用户信息	ipmitool user list
获取用户摘要信息	ipmitool user summary
请确认是否继续进行测试（y/n）？

以上是用户管理模块的测试计划，包含Redfish 5个命令和IPMI 2个命令，是否确认继续进行测试？

确认，继续执行测试
取消测试
```

```
I：确认，继续执行测试
```

AI会完成测试，并输出测试报告：

```
用户管理模块自动化测试报告
总计测试2个模块（Redfish + IPMI），2条用例，15个命令，其中0个用例失败，2个用例通过。

用例描述	命令描述	命令字	测试结果
Redfish - 用户管理			PASS
查询用户服务信息	GET /redfish/v1/AccountService	PASS
获取用户列表信息	GET /redfish/v1/AccountService/Accounts	PASS
获取用户1详细信息	GET /redfish/v1/AccountService/Accounts/1	PASS
获取用户2详细信息	GET /redfish/v1/AccountService/Accounts/2	PASS
获取用户3详细信息	GET /redfish/v1/AccountService/Accounts/3	PASS
获取用户4详细信息	GET /redfish/v1/AccountService/Accounts/4	PASS
获取用户5详细信息	GET /redfish/v1/AccountService/Accounts/5	PASS
获取用户6详细信息	GET /redfish/v1/AccountService/Accounts/6	PASS
获取角色列表信息	GET /redfish/v1/AccountService/Roles	PASS
获取Administrator角色	GET /redfish/v1/AccountService/Roles/Administrator	PASS
获取Operator角色	GET /redfish/v1/AccountService/Roles/Operator	PASS
获取User角色	GET /redfish/v1/AccountService/Roles/User	PASS
获取CustomRole1_1角色	GET /redfish/v1/AccountService/Roles/CustomRole1_1	PASS
获取CustomRole2角色	GET /redfish/v1/AccountService/Roles/CustomRole2	PASS
获取CustomRole3角色	GET /redfish/v1/AccountService/Roles/CustomRole3	PASS
获取CustomRole4_2角色	GET /redfish/v1/AccountService/Roles/CustomRole4_2	PASS
获取None角色	GET /redfish/v1/AccountService/Roles/None	PASS
IPMI - 用户管理			PASS
获取所有用户信息	ipmitool user list	PASS
获取用户摘要信息	ipmitool user summary	PASS
```



