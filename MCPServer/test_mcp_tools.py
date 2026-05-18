"""
SWRDMCPServer 工具接口测试程序

通过直接调用 MCP Server 的 streamable-http 接口，测试各个 tool 的功能。
支持命令行参数指定要测试的工具和参数。

用法:
    # 测试所有工具（使用默认参数）
    python test_mcp_tools.py

    # 测试指定工具
    python test_mcp_tools.py --tool sendRedfish --method GET --URL /redfish/v1

    # 测试指定工具并指定所有参数
    python test_mcp_tools.py --tool sendIPMI --command "user list"

    # 列出所有可用工具
    python test_mcp_tools.py --list-tools

    # 查看工具参数说明
    python test_mcp_tools.py --tool sendRedfish --help-tool
"""

import argparse
import base64
import json
import re
import sys
import time
import uuid
from typing import Any, Dict, Optional

import requests

# ──────────────────────────────────────────────
# 默认配置（从项目环境配置中读取）
# ──────────────────────────────────────────────

# MCP Server 地址
MCP_SERVER_URL = "http://10.41.6.8:8000/mcp"

# 认证信息（Basic Auth）
AUTH_USERNAME = "s10643"
AUTH_PASSWORD = "shiyuexi!5"

# 默认设备参数（从项目环境配置中读取）
DEFAULT_PC_IP = "10.41.6.8"
DEFAULT_DEVICE_IP = "192.168.88.222"
DEFAULT_DEVICE_USER = "admin"
DEFAULT_DEVICE_PWD = "h3c@1234"

# ──────────────────────────────────────────────
# 工具定义
# ──────────────────────────────────────────────

TOOL_DEFINITIONS = {
    "sendRedfish": {
        "description": "发送Redfish请求，通过指定PC代理访问目标设备的Redfish API",
        "params": {
            "pcIP": {"description": "PC代理的IP地址", "default": DEFAULT_PC_IP},
            "deviceIP": {"description": "目标设备的IP地址", "default": DEFAULT_DEVICE_IP},
            "deviceUser": {"description": "设备登录用户名", "default": DEFAULT_DEVICE_USER},
            "DevicePwd": {"description": "设备登录密码", "default": DEFAULT_DEVICE_PWD},
            "method": {"description": "HTTP方法（GET/POST/PUT/PATCH/DELETE）", "default": "GET"},
            "URL": {"description": "Redfish路径（如 /redfish/v1）", "default": "/redfish/v1"},
            "body": {"description": "请求体（GET请求传空字符串）", "default": ""},
        },
    },
    "sendIPMI": {
        "description": "发送IPMI命令，通过指定PC代理执行ipmitool命令",
        "params": {
            "pcIP": {"description": "PC代理的IP地址", "default": DEFAULT_PC_IP},
            "deviceIP": {"description": "目标设备的IP地址", "default": DEFAULT_DEVICE_IP},
            "deviceUser": {"description": "设备登录用户名", "default": DEFAULT_DEVICE_USER},
            "DevicePwd": {"description": "设备登录密码", "default": DEFAULT_DEVICE_PWD},
            "command": {"description": "ipmitool命令（如 mc info, sensor list）", "default": "mc info"},
        },
    },
    "browserOpen": {
        "description": "在PC代理上打开浏览器",
        "params": {
            "pcIP": {"description": "PC代理的IP地址", "default": DEFAULT_PC_IP},
            "sessionId": {"description": "浏览器会话ID", "default": ""},
            "headless": {"description": "是否无头模式", "default": False},
        },
    },
    "browserRun": {
        "description": "在已打开的浏览器会话中执行操作",
        "params": {
            "pcIP": {"description": "PC代理的IP地址", "default": DEFAULT_PC_IP},
            "sessionId": {"description": "浏览器会话ID", "default": ""},
            "actions": {
                "description": "操作JSON数组字符串",
                "default": '[{"type":"get_page_info"}]',
            },
            "options": {"description": "可选配置JSON字符串", "default": ""},
        },
    },
    "browserScreenshot": {
        "description": "截取浏览器当前页面的截图",
        "params": {
            "pcIP": {"description": "PC代理的IP地址", "default": DEFAULT_PC_IP},
            "sessionId": {"description": "浏览器会话ID", "default": ""},
            "fullPage": {"description": "是否全页截图", "default": False},
        },
    },
    "sendCommand": {
        "description": "在PC代理上执行本地命令",
        "params": {
            "pcIP": {"description": "PC代理的IP地址", "default": DEFAULT_PC_IP},
            "commandType": {
                "description": "命令类型（ftp_download/serial/ssh/tftp_server/shell）",
                "default": "shell",
            },
            "params": {
                "description": "JSON字符串，包含该命令类型所需的参数",
                "default": json.dumps({"command": "echo hello", "timeout": 10}),
            },
        },
    },
    "browserClose": {
        "description": "关闭浏览器会话",
        "params": {
            "pcIP": {"description": "PC代理的IP地址", "default": DEFAULT_PC_IP},
            "sessionId": {"description": "浏览器会话ID", "default": ""},
        },
    },
}


# ──────────────────────────────────────────────
# MCP Session 管理
# ──────────────────────────────────────────────


class MCPSession:
    """MCP streamable-http 会话管理"""

    def __init__(
        self,
        server_url: str = MCP_SERVER_URL,
        auth_username: str = AUTH_USERNAME,
        auth_password: str = AUTH_PASSWORD,
    ):
        self.server_url = server_url
        self.auth_header = self._make_auth_header(auth_username, auth_password)
        self.session_id: Optional[str] = None
        self._base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self.auth_header,
        }

    @staticmethod
    def _make_auth_header(username: str, password: str) -> str:
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        return f"Basic {encoded}"

    @staticmethod
    def _parse_sse_response(text: str) -> Dict[str, Any]:
        """解析 SSE (text/event-stream) 响应，提取 JSON-RPC 消息"""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
        # 如果不是 SSE 格式，尝试直接解析为 JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "无法解析响应", "raw": text[:500]}

    def initialize(self) -> bool:
        """
        初始化 MCP 会话（发送 initialize 请求）

        Returns:
            True 表示初始化成功，False 表示失败
        """
        payload = {
            "jsonrpc": "2.0",
            "id": f"init-{uuid.uuid4().hex[:8]}",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-test-client", "version": "1.0"},
            },
        }

        try:
            resp = requests.post(
                self.server_url,
                json=payload,
                headers=self._base_headers,
                timeout=30,
            )

            if resp.status_code != 200:
                print(f"[错误] 初始化失败，HTTP {resp.status_code}: {resp.text[:200]}")
                return False

            # 从响应头获取 session ID
            self.session_id = resp.headers.get("mcp-session-id")
            if not self.session_id:
                print(f"[错误] 初始化响应中缺少 mcp-session-id")
                return False

            # 解析响应体
            result = self._parse_sse_response(resp.text)
            if "error" in result:
                print(f"[错误] 初始化失败: {result['error']}")
                return False

            server_info = result.get("result", {}).get("serverInfo", {})
            print(f"[会话] 已建立，Session ID: {self.session_id}")
            print(f"[会话] 服务器: {server_info.get('name', 'unknown')} v{server_info.get('version', '?')}")
            return True

        except requests.exceptions.RequestException as e:
            print(f"[错误] 初始化请求失败: {e}")
            return False

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: int = 120) -> Dict[str, Any]:
        """
        调用 MCP 工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数字典
            timeout: 超时时间（秒）

        Returns:
            工具调用结果
        """
        if not self.session_id:
            print("[错误] 会话未初始化，请先调用 initialize()")
            return {"error": "Session not initialized"}

        request_id = f"call-{uuid.uuid4().hex[:8]}"
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        headers = {
            **self._base_headers,
            "Mcp-Session-Id": self.session_id,
        }

        print(f"\n{'='*70}")
        print(f"[请求] 工具: {tool_name}")
        print(f"[请求] 参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}")
        print(f"{'='*70}")

        try:
            start_time = time.time()
            resp = requests.post(
                self.server_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            elapsed = time.time() - start_time

            print(f"[响应] 状态码: {resp.status_code}")
            print(f"[响应] 耗时: {elapsed:.2f}s")

            if resp.status_code == 401:
                print(f"[错误] 认证失败 (401)，请检查用户名/密码")
                return {"error": "Authentication failed"}

            # 解析响应
            result = self._parse_sse_response(resp.text)

            if "error" in result:
                error_info = result["error"]
                print(f"[错误] {error_info.get('message', '未知错误')}")
                return {"error": error_info.get("message", str(error_info))}

            # 提取工具返回的内容
            tool_result = result.get("result", {})
            content_list = tool_result.get("content", [])

            for item in content_list:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    try:
                        parsed = json.loads(text)
                        print(f"[结果] (JSON):")
                        print(json.dumps(parsed, ensure_ascii=False, indent=2))
                    except (json.JSONDecodeError, TypeError):
                        print(f"[结果]: {text}")

            return result

        except requests.exceptions.Timeout:
            print(f"[错误] 请求超时（{timeout}s）")
            return {"error": "Request timeout"}
        except requests.exceptions.ConnectionError as e:
            print(f"[错误] 连接失败: {e}")
            return {"error": f"Connection failed: {e}"}
        except Exception as e:
            print(f"[错误] 未知错误: {e}")
            return {"error": str(e)}

    def close(self):
        """关闭会话（发送关闭通知）"""
        if not self.session_id:
            return

        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
            headers = {
                **self._base_headers,
                "Mcp-Session-Id": self.session_id,
            }
            requests.post(self.server_url, json=payload, headers=headers, timeout=5)
        except Exception:
            pass
        finally:
            self.session_id = None


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def list_tools():
    """列出所有可用工具及其参数说明"""
    print(f"\n{'='*70}")
    print(f"SWRDMCPServer 可用工具列表")
    print(f"{'='*70}")

    for tool_name, tool_def in TOOL_DEFINITIONS.items():
        print(f"\n{'─'*50}")
        print(f"工具: {tool_name}")
        print(f"描述: {tool_def['description']}")
        print(f"参数:")
        for param_name, param_info in tool_def["params"].items():
            default_val = param_info.get("default", "")
            print(f"  - {param_name}: {param_info['description']}")
            print(f"    默认值: {default_val}")
    print()


def show_tool_help(tool_name: str):
    """显示指定工具的详细帮助"""
    if tool_name not in TOOL_DEFINITIONS:
        print(f"错误: 未知工具 '{tool_name}'")
        print(f"可用工具: {', '.join(TOOL_DEFINITIONS.keys())}")
        return

    tool_def = TOOL_DEFINITIONS[tool_name]
    print(f"\n{'='*70}")
    print(f"工具: {tool_name}")
    print(f"描述: {tool_def['description']}")
    print(f"{'='*70}")
    print(f"\n参数列表:")
    for param_name, param_info in tool_def["params"].items():
        print(f"  --{param_name}: {param_info['description']}")
        print(f"    默认值: {param_info.get('default', '')}")
    print(f"\n示例:")
    print(f"  python test_mcp_tools.py --tool {tool_name}")
    for param_name, param_info in tool_def["params"].items():
        default_val = param_info.get("default", "")
        print(f"  python test_mcp_tools.py --tool {tool_name} --{param_name} {default_val}")
    print()


def run_all_tools():
    """运行所有工具的默认测试"""
    print(f"\n{'#'*70}")
    print(f"# SWRDMCPServer 全量工具测试")
    print(f"{'#'*70}")

    session = MCPSession()
    if not session.initialize():
        print("[错误] 无法建立 MCP 会话，测试终止")
        return

    results = {}
    for tool_name in TOOL_DEFINITIONS:
        print(f"\n{'#'*70}")
        print(f"# 测试工具: {tool_name}")
        print(f"{'#'*70}")

        # 获取默认参数
        arguments = {}
        for param_name, param_info in TOOL_DEFINITIONS[tool_name]["params"].items():
            arguments[param_name] = param_info["default"]

        # 特殊处理：browser 相关工具的 sessionId
        if tool_name in ("browserOpen", "browserRun", "browserScreenshot", "browserClose"):
            arguments["sessionId"] = f"test_session_{uuid.uuid4().hex[:8]}"

        result = session.call_tool(tool_name, arguments)
        results[tool_name] = result

    session.close()

    # 汇总结果
    print(f"\n\n{'#'*70}")
    print(f"# 测试结果汇总")
    print(f"{'#'*70}")
    passed = 0
    failed = 0
    for tool_name, result in results.items():
        if "error" in result:
            status = "FAIL"
            failed += 1
        else:
            status = "PASS"
            passed += 1
        print(f"  [{status}] - {tool_name}")

    print(f"\n总计: {len(results)} 个工具, {passed} 通过, {failed} 失败")


def main():
    parser = argparse.ArgumentParser(
        description="SWRDMCPServer 工具接口测试程序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试所有工具
  python test_mcp_tools.py

  # 测试指定工具
  python test_mcp_tools.py --tool sendRedfish --method GET --URL /redfish/v1

  # 测试IPMI命令
  python test_mcp_tools.py --tool sendIPMI --command "user list"

  # 自定义服务器地址
  python test_mcp_tools.py --tool sendRedfish --server http://10.41.6.8:8000/mcp

  # 自定义认证信息
  python test_mcp_tools.py --tool sendRedfish --auth-user myuser --auth-pass mypass
        """,
    )

    parser.add_argument("--tool", "-t", help="要测试的工具名称")
    parser.add_argument("--list-tools", action="store_true", help="列出所有可用工具")
    parser.add_argument("--help-tool", action="store_true", help="查看指定工具的详细帮助")
    parser.add_argument("--server", default=MCP_SERVER_URL, help=f"MCP Server URL (默认: {MCP_SERVER_URL})")
    parser.add_argument("--auth-user", default=AUTH_USERNAME, help=f"认证用户名 (默认: {AUTH_USERNAME})")
    parser.add_argument("--auth-pass", default=AUTH_PASSWORD, help="认证密码")
    parser.add_argument("--timeout", type=int, default=120, help="请求超时时间（秒）")

    # 为每个工具参数添加命令行参数（去重，避免冲突）
    seen_args = set()
    for tool_name, tool_def in TOOL_DEFINITIONS.items():
        for param_name, param_info in tool_def["params"].items():
            arg_name = f"--{param_name}"
            if arg_name not in seen_args:
                seen_args.add(arg_name)
                default_val = param_info["default"]
                parser.add_argument(
                    arg_name,
                    default=None,
                    help=f"[{tool_name}] {param_info['description']} (默认: {default_val})",
                )

    args = parser.parse_args()

    # 列出工具
    if args.list_tools:
        list_tools()
        return

    # 查看工具帮助
    if args.help_tool and args.tool:
        show_tool_help(args.tool)
        return

    # 测试指定工具
    if args.tool:
        if args.tool not in TOOL_DEFINITIONS:
            print(f"错误: 未知工具 '{args.tool}'")
            print(f"可用工具: {', '.join(TOOL_DEFINITIONS.keys())}")
            sys.exit(1)

        # 构建参数
        arguments = {}
        tool_def = TOOL_DEFINITIONS[args.tool]
        for param_name, param_info in tool_def["params"].items():
            arg_value = getattr(args, param_name, None)
            if arg_value is not None:
                if isinstance(param_info["default"], bool):
                    if isinstance(arg_value, str):
                        arg_value = arg_value.lower() in ("true", "1", "yes")
                arguments[param_name] = arg_value
            else:
                arguments[param_name] = param_info["default"]

        # 建立会话并调用工具
        session = MCPSession(
            server_url=args.server,
            auth_username=args.auth_user,
            auth_password=args.auth_pass,
        )

        if not session.initialize():
            print("[错误] 无法建立 MCP 会话")
            sys.exit(1)

        result = session.call_tool(args.tool, arguments, timeout=args.timeout)
        session.close()

        if "error" in result:
            sys.exit(1)
    else:
        # 测试所有工具
        run_all_tools()


if __name__ == "__main__":
    main()