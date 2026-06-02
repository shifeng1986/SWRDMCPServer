"""
SWRDMCPServer - BMC设备管理MCP服务
"""

__version__ = "0.6.0"

from doctest import debug
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.transport_security import TransportSecuritySettings
import httpx
import json
import socket
import psutil
from decorators import with_high_risk_check, with_operation_log, validate_input, auth_required
from decorators.security_decorator import SecurityCheckError, ConfirmationRequired
from config import AUTH_ENABLED
from connection_auth import ConnectionAuthMiddleware

# 全局异步 HTTP 客户端（复用连接池，支持高并发）
_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    """获取全局异步 HTTP 客户端（懒加载）"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            verify=False,
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
            ),
        )
    return _http_client


async def close_http_client():
    """关闭全局异步 HTTP 客户端"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None

def get_local_ipv4s():
    ips = set()
    for _name, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET and a.address:
                ips.add(a.address)
    return ips

ips = get_local_ipv4s()
allowed_hosts = ["localhost:*", "127.0.0.1:*", "10.*:*"] + [f"{ip}:*" for ip in ips]
allowed_origins = ["http://localhost:*", "http://127.0.0.1:*", "http://10.*:*"] + [f"http://{ip}:*" for ip in ips]

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
@auth_required              # 统一认证检查
@with_operation_log        # 操作日志记录（外层，确保拦截也记录日志）
@validate_input            # 输入参数校验（先校验，再检查高危）
@with_high_risk_check      # 高危操作检查
async def sendRedfish(
    ctx: Context,
    pcIP: str,
    deviceIP: str,
    deviceUser: str,
    DevicePwd: str,
    method: str,
    URL: str,
    body: str,
) -> str:
    """发送Redfish请求，通过指定PC代理访问目标设备的Redfish API

    Args:
        ctx: MCP上下文（用户信息从连接级别认证中获取）
        pcIP: PC代理的IP地址
        deviceIP: 目标设备的IP地址
        deviceUser: 设备登录用户名
        DevicePwd: 设备登录密码
        method: HTTP方法（GET/POST/PUT/PATCH/DELETE）
        URL: Redfish路径（如 /redfish/v1）
        body: 请求体（GET请求传空字符串）
    """

    # 打印用户信息（从连接级别认证中获取）
    username = "unknown"
    try:
        if hasattr(ctx, "request_context") and ctx.request_context:
            request = getattr(ctx.request_context, "request", None)
            if request and hasattr(request, "state"):
                username = getattr(request.state, "authenticated_user", "unknown")
    except Exception:
        pass

    try:
        proxy_url = f"https://{pcIP}:8888/redfish"
        payload = {
            "deviceIP": deviceIP,
            "deviceUser": deviceUser,
            "devicePwd": DevicePwd,
            "method": method.upper(),
            "url": URL,
            "body": body,
        }
        client = await get_http_client()
        response = await client.post(
            proxy_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        return response.text
    except httpx.HTTPError as e:
        return json.dumps({"error": f"Request failed: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
@auth_required              # 统一认证检查
@with_operation_log        # 操作日志记录（外层，确保拦截也记录日志）
@validate_input            # 输入参数校验（先校验，再检查高危）
@with_high_risk_check      # 高危操作检查
async def sendIPMI(
    ctx: Context,
    pcIP: str,
    deviceIP: str,
    deviceUser: str,
    DevicePwd: str,
    command: str,
) -> str:
    """发送IPMI命令，通过指定PC代理执行ipmitool命令

    Args:
        ctx: MCP上下文
        pcIP: PC代理的IP地址
        deviceIP: 目标设备的IP地址
        deviceUser: 设备登录用户名
        DevicePwd: 设备登录密码
        command: ipmitool命令（如 "mc info", "sensor list", "power status"）
    """
    # 打印用户信息（从连接级别认证中获取）
    username = "unknown"
    try:
        if hasattr(ctx, "request_context") and ctx.request_context:
            request = getattr(ctx.request_context, "request", None)
            if request and hasattr(request, "state"):
                username = getattr(request.state, "authenticated_user", "unknown")
    except Exception:
        pass

    try:
        proxy_url = f"https://{pcIP}:8888/ipmi"
        payload = {
            "deviceIP": deviceIP,
            "deviceUser": deviceUser,
            "devicePwd": DevicePwd,
            "command": command,
        }
        client = await get_http_client()
        response = await client.post(
            proxy_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        return response.text
    except httpx.HTTPError as e:
        return json.dumps({"error": f"Request failed: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
@auth_required              # 统一认证检查
@with_operation_log        # 操作日志记录（外层，确保拦截也记录日志）
@validate_input            # 输入参数校验（先校验，再检查高危）
@with_high_risk_check      # 高危操作检查
async def browserOpen(
    ctx: Context,
    pcIP: str,
    sessionId: str,
    headless: bool,
) -> str:
    """在PC代理上打开浏览器

    Args:
        ctx: MCP上下文
        pcIP: PC代理的IP地址
        sessionId: 浏览器会话ID
        headless: 是否无头模式
    """
    try:
        proxy_url = f"https://{pcIP}:8888/browser/open"
        payload = {
            "sessionId": sessionId,
            "headless": headless,
            "browser": "chromium"
        }
        client = await get_http_client()
        response = await client.post(proxy_url, json=payload)
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
@auth_required              # 统一认证检查
@with_operation_log        # 操作日志记录（外层，确保拦截也记录日志）
@validate_input            # 输入参数校验（先校验，再检查高危）
@with_high_risk_check      # 高危操作检查
async def browserRun(
    ctx: Context,
    pcIP: str,
    sessionId: str,
    actions: str,
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

    Args:
        ctx: MCP上下文
        pcIP: PC代理的IP地址
        sessionId: 浏览器会话ID
        actions: 操作JSON数组
        options: 可选配置JSON
    """
    try:
        proxy_url = f"https://{pcIP}:8888/browser/run"
        payload = {
            "sessionId": sessionId,
            "actions": json.loads(actions)
        }
        if options:
            payload["options"] = json.loads(options)
        client = await get_http_client()
        response = await client.post(proxy_url, json=payload)
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
@auth_required              # 统一认证检查
@with_operation_log        # 操作日志记录（外层，确保拦截也记录日志）
@validate_input            # 输入参数校验（先校验，再检查高危）
@with_high_risk_check      # 高危操作检查
async def browserScreenshot(
    ctx: Context,
    pcIP: str,
    sessionId: str,
    fullPage: bool,
) -> str:
    """截取浏览器当前页面的截图（注意：可能超时，建议使用get_page_info等替代）

    Args:
        ctx: MCP上下文
        pcIP: PC代理的IP地址
        sessionId: 浏览器会话ID
        fullPage: 是否全页截图
    """
    try:
        proxy_url = f"https://{pcIP}:8888/browser/screenshot"
        payload = {
            "sessionId": sessionId,
            "fullPage": fullPage
        }
        client = await get_http_client()
        response = await client.post(proxy_url, json=payload)
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
@auth_required              # 统一认证检查
@with_operation_log        # 操作日志记录（外层，确保拦截也记录日志）
@validate_input            # 输入参数校验（先校验，再检查高危）
@with_high_risk_check      # 高危操作检查（含高危命令拦截）
async def sendCommand(
    ctx: Context,
    pcIP: str,
    commandType: str,
    params: str,
) -> str:
    """在PC代理上执行本地命令

    支持的命令类型：
    - ftp_download: 从FTP服务器下载文件到PC代理
    - serial: 连接设备串口（通过串口交换机）
    - ssh: SSH连接到设备并执行命令
    - tftp_server: 启动/停止TFTP服务器
    - shell: 在PC代理上执行shell命令

    Args:
        ctx: MCP上下文
        pcIP: PC代理的IP地址
        commandType: 命令类型（ftp_download/serial/ssh/tftp_server/shell）
        params: JSON字符串，包含该命令类型所需的参数

    ftp_download params 示例:
        {"ftpServer":"10.141.228.15","ftpUser":"user","ftpPassword":"pass",
         "remotePath":"/path/firmware.bin","localPath":"C:\\firmware\\firmware.bin"}

    serial params 示例:
        {"host":"192.168.0.200","port":3004,"baud":115200,"action":"open"}

    ssh params 示例:
        {"host":"192.168.88.222","port":22,"user":"admin","password":"pass",
         "command":"mc info","timeout":30}

    tftp_server params 示例:
        {"action":"start","port":69,"dir":"C:\\firmware_upgrade"}

    shell params 示例:
        {"command":"dir /b C:\\firmware","timeout":30}
    """
    try:
        proxy_url = f"https://{pcIP}:8888/command"
        payload = {
            "commandType": commandType,
            "params": params,
        }
        client = await get_http_client()
        response = await client.post(
            proxy_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        return response.text
    except httpx.HTTPError as e:
        return json.dumps({"error": f"Command request failed: {str(e)}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
@auth_required              # 统一认证检查
@with_operation_log        # 操作日志记录（外层，确保拦截也记录日志）
@validate_input            # 输入参数校验（先校验，再检查高危）
@with_high_risk_check      # 高危操作检查
async def browserClose(
    ctx: Context,
    pcIP: str,
    sessionId: str,
) -> str:
    """关闭浏览器会话

    Args:
        ctx: MCP上下文
        pcIP: PC代理的IP地址
        sessionId: 浏览器会话ID
    """
    try:
        proxy_url = f"https://{pcIP}:8888/browser/close"
        payload = {"sessionId": sessionId}
        client = await get_http_client()
        response = await client.post(proxy_url, json=payload)
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

if __name__ == "__main__":
    # 添加连接级别认证中间件
    if AUTH_ENABLED:
        # 启动后台线程定期清理过期缓存
        import threading
        import time

        def cache_cleanup_worker():
            """后台工作线程，定期清理过期的认证缓存"""
            while True:
                time.sleep(300)  # 每5分钟清理一次
                ConnectionAuthMiddleware.clear_expired_cache()

        cleanup_thread = threading.Thread(target=cache_cleanup_worker, daemon=True)
        cleanup_thread.start()

        # Monkey patch streamable_http_app方法来添加中间件
        original_streamable_http_app = mcp.streamable_http_app

        def streamable_http_app_with_auth():
            # 获取原始的Starlette应用
            app = original_streamable_http_app()

            # 添加连接认证中间件
            app.add_middleware(ConnectionAuthMiddleware)

            return app

        # 替换方法
        mcp.streamable_http_app = streamable_http_app_with_auth

        print(f"\n{'='*60}")
        print(f"[认证] 用户认证已启用")
        print(f"[认证] 认证方式：连接级别 Basic Auth（HTTP层）")
        print(f"[认证] MCP Client 配置示例:")
        print(f'[认证]   "headers": {{"Authorization": "Basic YWRtaW46YWRtaW4xMjM="}}')
        print(f"{'='*60}\n")
    
    print(f"[版本] SWRDMCPServer v{__version__}")
    print("Starting SWRDMCPServer on 0.0.0.0:8000")
    try:
        mcp.run(transport="streamable-http")
    finally:
        import asyncio
        asyncio.run(close_http_client())
