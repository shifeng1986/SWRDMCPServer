"""
Local Proxy 代理转发工具

在 PC 上启动 HTTP 服务，监听 MCP Server 下发的 Redfish/IPMI 请求，
将请求转发到目标设备，并将设备的响应返回给 MCP Server。

工作流程：
1. MCP Server 通过 HTTP POST（http://{pcIP}:8888/redfish 或 /ipmi）
   将请求信息发送给本代理
2. 本代理接收请求，打印请求内容
3. 通过 HTTPS 向设备发送 Redfish 请求，或通过 ipmitool 执行 IPMI 命令
4. 打印设备响应内容
5. 将设备的响应原样返回给 MCP Server
"""

import http.server
import json
import os
import subprocess

import requests


# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

PROXY_HOST = "0.0.0.0"
PROXY_PORT = 8888
REQUEST_TIMEOUT = 30

# ipmitool 可执行文件路径：优先从脚本同级目录查找
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_IPMITOOL_PATH = os.path.join(_SCRIPT_DIR, "ipmitool.exe")
if not os.path.isfile(_IPMITOOL_PATH):
    # 同级目录没有，回退到系统 PATH 中的 ipmitool
    _IPMITOOL_PATH = "ipmitool"


# ──────────────────────────────────────────────
# 日志工具
# ──────────────────────────────────────────────

def _log(level: str, msg: str):
    """简单日志输出"""
    print(f"[{level}] {msg}")


def log_info(msg: str):
    _log("INFO", msg)


def log_warn(msg: str):
    _log("WARN", msg)


def log_error(msg: str):
    _log("ERROR", msg)


# ──────────────────────────────────────────────
# Redfish 请求转发核心逻辑
# ──────────────────────────────────────────────

def forward_redfish_request(
    method: str,
    device_ip: str,
    url: str,
    auth: tuple,
    body: str,
) -> requests.Response:
    """
    将请求转发到目标设备

    Args:
        method: HTTP 方法
        device_ip: 目标设备 IP
        url: Redfish 路径（如 /redfish/v1）
        auth: Basic 认证元组 (username, password)
        body: 请求体字符串

    Returns:
        requests.Response: 设备的响应
    """
    target_url = f"https://{device_ip}{url}"
    kwargs = {
        "url": target_url,
        "method": method,
        "auth": auth,
        "verify": False,
        "timeout": REQUEST_TIMEOUT,
        "allow_redirects": True,
    }

    if method.upper() in ("POST", "PATCH", "PUT") and body:
        try:
            kwargs["json"] = json.loads(body)
        except json.JSONDecodeError:
            kwargs["data"] = body

    return requests.request(**kwargs)


def forward_ipmi_request(
    device_ip: str,
    auth: tuple,
    command: str,
) -> dict:
    """
    通过 ipmitool 执行 IPMI 命令

    Args:
        device_ip: 目标设备 IP
        auth: 认证元组 (username, password)
        command: ipmitool 命令（如 "mc info", "sensor list"）

    Returns:
        dict: 执行结果，包含 returncode, stdout, stderr
    """
    username, password = auth
    # 构建 ipmitool 命令
    ipmi_cmd = [
        _IPMITOOL_PATH,
        "-I", "lanplus",
        "-H", device_ip,
        "-U", username,
        "-P", password,
    ]
    # 将用户输入的命令拆分追加
    ipmi_cmd.extend(command.split())

    log_info(f"执行 IPMI 命令: {' '.join(ipmi_cmd[:6])} *** {command}")

    try:
        result = subprocess.run(
            ipmi_cmd,
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"IPMI 命令执行超时（{REQUEST_TIMEOUT}s）",
        }
    except FileNotFoundError:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "ipmitool 未安装或不在 PATH 中",
        }
    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"IPMI 命令执行异常: {e}",
        }


# ──────────────────────────────────────────────
# HTTP 代理服务器 Handler
# ──────────────────────────────────────────────

class LocalProxyHandler(http.server.BaseHTTPRequestHandler):
    """处理 MCP Server 转发过来的 Redfish/IPMI 请求"""

    def do_POST(self):
        """处理 POST 请求，支持 /redfish 和 /ipmi 路径"""
        if self.path == "/redfish":
            self._handle_redfish()
        elif self.path == "/ipmi":
            self._handle_ipmi()
        else:
            self._send_error_response(404, f"路径不存在: {self.path}")

    def _read_payload(self) -> dict:
        """读取并解析请求体 JSON"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return None
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _handle_redfish(self):
        """处理 /redfish 请求"""
        try:
            payload = self._read_payload()
        except Exception as e:
            self._send_error_response(400, f"请求体解析失败: {e}")
            return

        if not payload:
            self._send_error_response(400, "请求体为空")
            return

        # 提取请求参数
        device_ip = payload.get("deviceIP", "")
        device_user = payload.get("deviceUser", "")
        device_pwd = payload.get("devicePwd", "")
        method = payload.get("method", "GET").upper()
        url = payload.get("url", "")
        request_body = payload.get("body", "")

        # ── 打印请求信息 ──
        log_info("=" * 60)
        log_info(f"收到 Redfish 请求: {method} https://{device_ip}{url}")
        log_info(f"认证信息: {device_user}:***")
        if request_body:
            log_info(f"请求体: {request_body}")
        else:
            log_info("请求体: (无)")
        log_info("=" * 60)

        # ── 转发请求到设备 ──
        try:
            response = forward_redfish_request(
                method=method,
                device_ip=device_ip,
                url=url,
                auth=(device_user, device_pwd),
                body=request_body,
            )

            # ── 打印响应信息 ──
            log_info("=" * 60)
            log_info(f"设备响应: HTTP {response.status_code}")
            log_info(f"响应头: {json.dumps(dict(response.headers), ensure_ascii=False, indent=2)}")
            log_info(f"响应体: {response.text}")
            log_info("=" * 60)

            # ── 将响应返回给 MCP Server ──
            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }
            result_json = json.dumps(result, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(result_json.encode("utf-8"))

        except requests.exceptions.RequestException as e:
            log_error(f"请求转发失败: {e}")
            self._send_error_response(502, f"请求转发失败: {e}")
        except Exception as e:
            log_error(f"请求处理异常: {e}")
            self._send_error_response(500, f"请求处理异常: {e}")

    def _handle_ipmi(self):
        """处理 /ipmi 请求"""
        try:
            payload = self._read_payload()
        except Exception as e:
            self._send_error_response(400, f"请求体解析失败: {e}")
            return

        if not payload:
            self._send_error_response(400, "请求体为空")
            return

        # 提取请求参数
        device_ip = payload.get("deviceIP", "")
        device_user = payload.get("deviceUser", "")
        device_pwd = payload.get("devicePwd", "")
        command = payload.get("command", "")

        # ── 打印请求信息 ──
        log_info("=" * 60)
        log_info(f"收到 IPMI 请求: ipmitool -H {device_ip} -U {device_user} {command}")
        log_info(f"认证信息: {device_user}:***")
        log_info("=" * 60)

        # ── 执行 IPMI 命令 ──
        try:
            result = forward_ipmi_request(
                device_ip=device_ip,
                auth=(device_user, device_pwd),
                command=command,
            )

            # ── 打印执行结果 ──
            log_info("=" * 60)
            log_info(f"IPMI 执行结果: returncode={result['returncode']}")
            if result["stdout"]:
                log_info(f"stdout: {result['stdout']}")
            if result["stderr"]:
                log_info(f"stderr: {result['stderr']}")
            log_info("=" * 60)

            # ── 将结果返回给 MCP Server ──
            result_json = json.dumps(result, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(result_json.encode("utf-8"))

        except Exception as e:
            log_error(f"IPMI 命令处理异常: {e}")
            self._send_error_response(500, f"IPMI 命令处理异常: {e}")

    def _send_error_response(self, code: int, message: str):
        """发送错误响应"""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        error_body = json.dumps({"error": message}, ensure_ascii=False, indent=2)
        self.wfile.write(error_body.encode("utf-8"))

    def log_message(self, format, *args):
        """覆盖默认日志格式"""
        log_info(f"{self.client_address[0]}:{self.client_address[1]} - {format % args}")


# ──────────────────────────────────────────────
# 服务器启动
# ──────────────────────────────────────────────

def run_proxy_server(host: str = PROXY_HOST, port: int = PROXY_PORT):
    """启动 Local Proxy 代理服务器"""
    server_address = (host, port)
    httpd = http.server.HTTPServer(server_address, LocalProxyHandler)

    log_info(f"Local Proxy 代理服务器启动: http://{host}:{port}")
    log_info("等待 MCP Server 转发 Redfish/IPMI 请求...")
    log_info("按 Ctrl+C 停止服务器")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log_info("收到停止信号，正在关闭服务器...")
        httpd.shutdown()
        httpd.server_close()
        log_info("服务器已关闭")


if __name__ == "__main__":
    run_proxy_server()
