from mcp.server.fastmcp import FastMCP, Context
import requests
import json

from decorators import with_high_risk_check, with_operation_log, validate_input
from decorators.security_decorator import SecurityCheckError, ConfirmationRequired

# 创建 MCP Server 实例
mcp = FastMCP("SWRDMCPServer")


@mcp.tool()
@with_high_risk_check      # 高危操作检查（最外层）
@with_operation_log        # 操作日志记录
@validate_input            # 输入参数校验
async def sendRedfish(
    pcIP: str,
    deviceIP: str,
    deviceUser: str,
    DevicePwd: str,
    method: str,
    URL: str,
    body: str,
    ctx: Context,
    userName: str = "",
) -> str:
    """发送Redfish请求，通过指定PC代理访问目标设备的Redfish API
    
    Args:
        pcIP: PC代理的IP地址
        deviceIP: 目标设备的IP地址
        deviceUser: 设备登录用户名
        DevicePwd: 设备登录密码
        method: HTTP方法（GET/POST/PUT/PATCH/DELETE）
        URL: Redfish路径（如 /redfish/v1）
        body: 请求体（GET请求传空字符串）
        ctx: MCP上下文
        userName: IDE运行系统的登录用户名，由IDE侧传入
    """
    # 打印用户信息
    user_display = userName if userName else "unknown"
    print(f"[用户信息] IDE用户: {user_display}")

    # 打印远端 MCP Client 信息
    client_info = {
        "client_id": ctx.client_id,
        "request_id": ctx.request_id,
    }
    if ctx.session and ctx.session.client_params:
        params = ctx.session.client_params
        client_info["client_name"] = params.clientInfo.name
        client_info["client_version"] = params.clientInfo.version
        client_info["protocol_version"] = params.protocolVersion
    print(f"[MCP Client 信息] {json.dumps(client_info, ensure_ascii=False, indent=2)}")

    try:
        proxy_url = f"http://{pcIP}:8888/redfish"

        method = method.upper()
        payload = {
            "deviceIP": deviceIP,
            "deviceUser": deviceUser,
            "devicePwd": DevicePwd,
            "method": method,
            "url": URL,
            "body": body,
        }

        response = requests.post(
            proxy_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        return response.text

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Request failed: {str(e)}"}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"}, ensure_ascii=False, indent=2)


@mcp.tool()
@with_high_risk_check      # 高危操作检查（最外层）
@with_operation_log        # 操作日志记录
@validate_input            # 输入参数校验
async def sendIPMI(
    pcIP: str,
    deviceIP: str,
    deviceUser: str,
    DevicePwd: str,
    command: str,
    ctx: Context,
    userName: str = "",
) -> str:
    """发送IPMI命令，通过指定PC代理执行ipmitool命令

    Args:
        pcIP: PC代理的IP地址
        deviceIP: 目标设备的IP地址
        deviceUser: 设备登录用户名
        DevicePwd: 设备登录密码
        command: ipmitool命令（如 "mc info", "sensor list", "power status"）
        ctx: MCP上下文
        userName: IDE运行系统的登录用户名，由IDE侧传入
    """
    # 打印用户信息
    user_display = userName if userName else "unknown"
    print(f"[用户信息] IDE用户: {user_display}")

    # 打印远端 MCP Client 信息
    client_info = {
        "client_id": ctx.client_id,
        "request_id": ctx.request_id,
    }
    if ctx.session and ctx.session.client_params:
        params = ctx.session.client_params
        client_info["client_name"] = params.clientInfo.name
        client_info["client_version"] = params.clientInfo.version
        client_info["protocol_version"] = params.protocolVersion
    print(f"[MCP Client 信息] {json.dumps(client_info, ensure_ascii=False, indent=2)}")

    try:
        proxy_url = f"http://{pcIP}:8888/ipmi"

        payload = {
            "deviceIP": deviceIP,
            "deviceUser": deviceUser,
            "devicePwd": DevicePwd,
            "command": command,
        }

        response = requests.post(
            proxy_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        return response.text

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Request failed: {str(e)}"}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"}, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="sse")
