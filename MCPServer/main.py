"""
Fixed MCP Server for OpenClaw compatibility
更新：添加非截图操作的文档说明
"""

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.transport_security import TransportSecuritySettings
import requests
import json
import socket
import psutil
from decorators import with_high_risk_check, with_operation_log, validate_input
from decorators.security_decorator import SecurityCheckError, ConfirmationRequired
from decorators.auth_decorator import AuthMiddleware, get_server_token, _authenticate_user, _revoke_token, token_endpoint
from config import AUTH_ENABLED


def get_local_ipv4s():
    ips = set()
    for _name, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET and a.address:
                ips.add(a.address)
    return ips

ips = get_local_ipv4s()
allowed_hosts = ["localhost:*", "127.0.0.1:*"] + [f"{ip}:*" for ip in ips]
allowed_origins = ["http://localhost:*", "http://127.0.0.1:*"] + [f"http://{ip}:*" for ip in ips]

ts = TransportSecuritySettings(
    allowed_hosts=allowed_hosts,
    allowed_origins=allowed_origins,
)

mcp = FastMCP(
    "SWRDMCPServer",
    host="0.0.0.0",
    port=8000,
    transport_security=ts,
)

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
        payload = {
            "deviceIP": deviceIP,
            "deviceUser": deviceUser,
            "devicePwd": DevicePwd,
            "method": method.upper(),
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
        return json.dumps({"error": f"Request failed: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"}, ensure_ascii=False)


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
        return json.dumps({"error": f"Request failed: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
@with_high_risk_check      # 高危操作检查（最外层）
@with_operation_log        # 操作日志记录
@validate_input            # 输入参数校验
async def browserOpen(
    pcIP: str,
    sessionId: str,
    headless: bool,
    userName: str = "",
) -> str:
    """在PC代理上打开浏览器"""
    try:
        proxy_url = f"http://{pcIP}:8888/browser/open"
        payload = {
            "sessionId": sessionId,
            "headless": headless,
            "browser": "chromium"
        }
        response = requests.post(proxy_url, json=payload, timeout=60)
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
@with_high_risk_check      # 高危操作检查（最外层）
@with_operation_log        # 操作日志记录
@validate_input            # 输入参数校验
async def browserRun(
    pcIP: str,
    sessionId: str,
    actions: str,
    userName: str = "",
    options: str = "",
) -> str:
    """
    在已打开的浏览器会话中执行操作
    
    支持的操作类型（actions参数为JSON数组）：
    - {"type":"goto","url":"http://..."} - 导航到URL
    - {"type":"click","selector":"#btn"} - 点击元素
    - {"type":"fill","selector":"#input","text":"value"} - 填写输入框
    - {"type":"press","selector":"#input","key":"Enter"} - 按键
    - {"type":"wait_for_selector","selector":"#elem"} - 等待元素出现
    - {"type":"wait_for_load_state","state":"networkidle"} - 等待页面加载
    - {"type":"get_text","selector":"#elem"} - 获取元素文本（非截图）
    - {"type":"get_html","selector":"#elem"} - 获取元素HTML（非截图）
    - {"type":"get_attribute","selector":"#elem","attribute":"href"} - 获取属性（非截图）
    - {"type":"eval","expression":"()=>document.title"} - 执行JS（非截图）
    - {"type":"get_all_links"} - 获取所有链接（非截图）
    - {"type":"get_all_inputs"} - 获取所有输入框（非截图）
    - {"type":"get_all_buttons"} - 获取所有按钮（非截图）
    - {"type":"get_page_info"} - 获取页面信息（非截图）
    - {"type":"query_selector_all","selector":"li"} - 查询多个元素（非截图）
    
    示例actions参数：
    '[{"type":"goto","url":"http://192.168.49.71"},{"type":"get_page_info"}]'
    """
    try:
        proxy_url = f"http://{pcIP}:8888/browser/run"
        payload = {
            "sessionId": sessionId,
            "actions": json.loads(actions)
        }
        if options:
            payload["options"] = json.loads(options)
        response = requests.post(proxy_url, json=payload, timeout=120)
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
@with_high_risk_check      # 高危操作检查（最外层）
@with_operation_log        # 操作日志记录
@validate_input            # 输入参数校验
async def browserScreenshot(
    pcIP: str,
    sessionId: str,
    fullPage: bool,
    userName: str = "",
) -> str:
    """截取浏览器当前页面的截图（注意：可能超时，建议使用get_page_info等替代）"""
    try:
        proxy_url = f"http://{pcIP}:8888/browser/screenshot"
        payload = {
            "sessionId": sessionId,
            "fullPage": fullPage
        }
        response = requests.post(proxy_url, json=payload, timeout=60)
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
@with_high_risk_check      # 高危操作检查（最外层）
@with_operation_log        # 操作日志记录
@validate_input            # 输入参数校验
async def browserClose(
    pcIP: str,
    sessionId: str,
    userName: str = "",
) -> str:
    """关闭浏览器会话"""
    try:
        proxy_url = f"http://{pcIP}:8888/browser/close"
        payload = {"sessionId": sessionId}
        response = requests.post(proxy_url, json=payload, timeout=60)
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def authenticate(
    username: str,
    password: str,
    ctx: Context,
) -> str:
    """用户认证，通过用户名和密码获取访问 Token

    Args:
        username: 用户名
        password: 密码
        ctx: MCP上下文
    """
    token = _authenticate_user(username, password)
    if token:
        return json.dumps(
            {
                "status": "success",
                "message": "认证成功",
                "token": token,
                "token_type": "Bearer",
                "expires_in": 3600,
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        return json.dumps(
            {
                "status": "error",
                "message": "认证失败：用户名或密码错误",
            },
            ensure_ascii=False,
            indent=2,
        )


@mcp.tool()
async def logout(
    token: str,
    ctx: Context,
) -> str:
    """注销 Token，使其失效

    Args:
        token: 要注销的 Token
        ctx: MCP上下文
    """
    if _revoke_token(token):
        return json.dumps({"status": "success", "message": "Token 已注销"}, ensure_ascii=False, indent=2)
    else:
        return json.dumps({"status": "error", "message": "Token 不存在或已过期"}, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 注册认证中间件
    if AUTH_ENABLED:
        app = mcp.streamable_http_app()
        # 注册 /auth/token 认证端点（无需 Token 即可访问）
        app.add_route("/auth/token", token_endpoint, methods=["POST"])
        # 注册认证中间件（/auth 路径已放行，仅 /mcp 需要认证）
        app.add_middleware(AuthMiddleware)
        # 打印服务端 Token，用于 MCP Client 配置
        server_token = get_server_token()
        print(f"\n{'='*60}")
        print(f"[认证] 用户认证已启用")
        print(f"[认证] 服务端 Token: {server_token}")
        print(f"[认证] 请将此 Token 配置到 MCP Client 的 Authorization 头中")
        print(f"[认证] 格式: Authorization: Bearer {server_token}")
        print(f"[认证] 或使用用户名/密码获取 Token: POST /auth/token")
        print(f"{'='*60}\n")
        # 手动启动 uvicorn，使用已注册中间件的 app
        import uvicorn
        config = uvicorn.Config(
            app,
            host=mcp.settings.host,
            port=mcp.settings.port,
            log_level=mcp.settings.log_level.lower(),
        )
        server = uvicorn.Server(config)
        import anyio
        anyio.run(server.serve)
    else:
        print("Starting SWRDMCPServer on 0.0.0.0:8000")
        print(f"Allowed hosts: {allowed_hosts}")
        print(f"Allowed origins: {allowed_origins}")
        mcp.run(transport="streamable-http")
