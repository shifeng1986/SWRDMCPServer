"""
Fixed MCP Server for OpenClaw compatibility
更新：添加非截图操作的文档说明
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import requests
import json
import socket
import psutil

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
async def sendRedfish(
    pcIP: str,
    deviceIP: str,
    deviceUser: str,
    DevicePwd: str,
    method: str,
    URL: str,
    body: str,
    userName: str = "",
) -> str:
    """发送Redfish请求，通过指定PC代理访问目标设备的Redfish API"""
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
async def sendIPMI(
    pcIP: str,
    deviceIP: str,
    deviceUser: str,
    DevicePwd: str,
    command: str,
    userName: str = "",
) -> str:
    """发送IPMI命令，通过指定PC代理执行ipmitool命令"""
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


if __name__ == "__main__":
    print("Starting SWRDMCPServer on 0.0.0.0:8000")
    print(f"Allowed hosts: {allowed_hosts}")
    print(f"Allowed origins: {allowed_origins}")
    mcp.run(transport="sse")