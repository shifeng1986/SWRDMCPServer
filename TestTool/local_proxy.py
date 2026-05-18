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

__version__ = "0.1.0"

import http.server
import json
import subprocess
import threading
import time
import os
import ssl
from typing import Any

try:
    import requests as _requests
except Exception:
    _requests = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

_thread_local = threading.local()
_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSIONS_LOCK = threading.Lock()



def _get_playwright():
    if sync_playwright is None:
        raise RuntimeError("未安装 playwright")
    if not hasattr(_thread_local, 'pw') or _thread_local.pw is None:
        _thread_local.pw = sync_playwright().start()
    return _thread_local.pw

def _browser_open(session_id: str, headless: bool = True, browser: str = "chromium"):
    pw = _get_playwright()
    
    with _SESSIONS_LOCK:
        if session_id in _SESSIONS:
            return {"ok": True, "message": f"session 已存在: {session_id}"}

        b = getattr(pw, browser).launch(headless=headless)
        ctx = b.new_context(ignore_https_errors=True)
        page = ctx.new_page()
        _SESSIONS[session_id] = {
            "browser": b, 
            "context": ctx, 
            "page": page, 
            "ts": time.time(),
            "thread_id": threading.current_thread().ident
        }
        return {"ok": True, "sessionId": session_id}

def _get_page(session_id: str):
    with _SESSIONS_LOCK:
        s = _SESSIONS.get(session_id)
        if not s:
            raise RuntimeError(f"session 不存在: {session_id}")
        if s.get("thread_id") != threading.current_thread().ident:
            raise RuntimeError(f"session {session_id} 只能在创建它的线程中访问")
        s["ts"] = time.time()
        return s["page"]

def _run_actions(session_id: str, actions: list, options: dict | None = None):
    """
    支持的操作类型（无需截图）：
    - goto: 导航到URL
    - click: 点击元素
    - fill: 填写输入框
    - press: 按键
    - wait_for_selector: 等待元素出现
    - wait_for_load_state: 等待页面加载状态
    - get_text: 获取元素文本内容
    - get_html: 获取元素HTML
    - eval: 执行JavaScript并返回结果
    - get_all_links: 获取所有链接
    - get_all_inputs: 获取所有输入框
    - get_page_info: 获取页面基本信息
    """
    page = _get_page(session_id)
    results = []
    
    for i, a in enumerate(actions):
        t = (a.get("type") or "").lower()
        timeout = a.get("timeout", 30000)
        try:
            if t == "goto":
                page.goto(a["url"], wait_until=a.get("waitUntil", "domcontentloaded"), timeout=timeout)
                results.append({"i": i, "ok": True, "url": page.url})
                
            elif t == "click":
                page.click(a["selector"], timeout=timeout)
                results.append({"i": i, "ok": True})
                
            elif t == "fill":
                page.fill(a["selector"], a.get("text", ""), timeout=timeout)
                results.append({"i": i, "ok": True})
                
            elif t == "press":
                page.press(a["selector"], a["key"], timeout=timeout)
                results.append({"i": i, "ok": True})
                
            elif t == "wait_for_selector":
                page.wait_for_selector(a["selector"], timeout=timeout)
                results.append({"i": i, "ok": True})
                
            elif t == "wait_for_load_state":
                page.wait_for_load_state(a.get("state", "load"), timeout=timeout)
                results.append({"i": i, "ok": True})
                
            elif t == "get_text":
                # 获取元素文本内容（替代截图）
                text = page.text_content(a["selector"], timeout=timeout)
                results.append({"i": i, "ok": True, "text": text})
                
            elif t == "get_html":
                # 获取元素HTML
                html = page.inner_html(a["selector"], timeout=timeout)
                results.append({"i": i, "ok": True, "html": html})
                
            elif t == "get_attribute":
                # 获取元素属性
                attr = page.get_attribute(a["selector"], a["attribute"], timeout=timeout)
                results.append({"i": i, "ok": True, "attribute": attr})
                
            elif t == "eval":
                # 执行JavaScript并返回结果
                result = page.evaluate(a["expression"], a.get("arg"))
                results.append({"i": i, "ok": True, "result": result})
                
            elif t == "get_all_links":
                # 获取所有链接（替代截图查看页面结构）
                links = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a')).map(a => ({
                        text: a.textContent.trim(),
                        href: a.href,
                        id: a.id,
                        class: a.className
                    })).filter(l => l.text.length > 0);
                }""")
                results.append({"i": i, "ok": True, "links": links})
                
            elif t == "get_all_inputs":
                # 获取所有输入框
                inputs = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('input,textarea,select')).map(e => ({
                        tag: e.tagName,
                        type: e.type,
                        name: e.name,
                        id: e.id,
                        placeholder: e.placeholder,
                        class: e.className
                    }));
                }""")
                results.append({"i": i, "ok": True, "inputs": inputs})
                
            elif t == "get_all_buttons":
                # 获取所有按钮
                buttons = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('button,[role=button]')).map(e => ({
                        text: e.textContent.trim(),
                        id: e.id,
                        class: e.className,
                        type: e.type
                    })).filter(b => b.text.length > 0);
                }""")
                results.append({"i": i, "ok": True, "buttons": buttons})
                
            elif t == "get_page_info":
                # 获取页面基本信息（标题、URL、所有文本内容）
                info = page.evaluate("""() => ({
                    title: document.title,
                    url: window.location.href,
                    text: document.body.innerText.slice(0, 2000),
                    meta: Array.from(document.querySelectorAll('meta')).map(m => ({
                        name: m.name,
                        content: m.content
                    })).filter(m => m.name)
                })""")
                results.append({"i": i, "ok": True, "info": info})
                
            elif t == "query_selector_all":
                # 查询多个元素并返回信息
                elements = page.evaluate("""(selector) => {
                    return Array.from(document.querySelectorAll(selector)).map((e, i) => ({
                        index: i,
                        tag: e.tagName,
                        text: e.textContent.trim().slice(0, 100),
                        id: e.id,
                        class: e.className
                    }));
                }""", a["selector"])
                results.append({"i": i, "ok": True, "elements": elements})
                
            else:
                results.append({"i": i, "ok": False, "error": f"不支持的 action.type: {t}"})
                
        except Exception as e:
            results.append({"i": i, "ok": False, "error": str(e)})
    
    return {"ok": True, "results": results}


class LocalProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/redfish":
            self._handle_redfish()
        elif self.path == "/ipmi":
            self._handle_ipmi()
        elif self.path == "/browser/open":
            self._handle_browser_open()
        elif self.path == "/browser/run":
            self._handle_browser_run()
        elif self.path == "/browser/close":
            self._handle_browser_close()
        elif self.path == "/command":
            self._handle_command()
        else:
            self._send_error_response(404, f"路径不存在: {self.path}")

    def _read_payload(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return None
        return json.loads(self.rfile.read(content_length).decode("utf-8"))

    def _send_error_response(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}, ensure_ascii=False).encode())

    def _send_json(self, code: int, obj: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.client_address[0]} - {format % args}")

    def _handle_redfish(self):
        """转发 Redfish 请求到目标设备"""
        try:
            payload = self._read_payload() or {}
            device_ip = payload.get("deviceIP", "")
            device_user = payload.get("deviceUser", "")
            device_pwd = payload.get("devicePwd", "")
            method = payload.get("method", "GET").upper()
            url = payload.get("url", "")
            body = payload.get("body", "")
            
            if not device_ip or not url:
                self._send_error_response(400, "缺少 deviceIP 或 url")
                return
            
            full_url = f"https://{device_ip}{url}"
            auth = (device_user, device_pwd) if device_user else None
            data = body if body else None
            
            if _requests is None:
                self._send_error_response(500, "requests 库未安装")
                return
            
            resp = _requests.request(
                method=method,
                url=full_url,
                auth=auth,
                data=data,
                headers={"Content-Type": "application/json"},
                verify=False,
                timeout=30,
            )
            result = {
                "status_code": resp.status_code,
                "body": resp.text
            }
            self._send_json(200, result)
        except Exception as e:
            self._send_error_response(500, f"Redfish 请求失败: {e}")

    def _handle_ipmi(self):
        """执行 IPMI 命令"""
        try:
            payload = self._read_payload() or {}
            device_ip = payload.get("deviceIP", "")
            device_user = payload.get("deviceUser", "")
            device_pwd = payload.get("devicePwd", "")
            command = payload.get("command", "")
            
            if not device_ip or not command:
                self._send_error_response(400, "缺少 deviceIP 或 command")
                return
            
            cmd = [
                "ipmitool", "-I", "lanplus",
                "-H", device_ip,
                "-U", device_user,
                "-P", device_pwd,
            ] + command.split()
            
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            result = {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr
            }
            self._send_json(200, result)
        except Exception as e:
            self._send_error_response(500, f"IPMI 命令失败: {e}")

    def _handle_browser_open(self):
        try:
            payload = self._read_payload() or {}
            result = _browser_open(
                session_id=payload.get("sessionId", ""),
                headless=bool(payload.get("headless", True))
            )
            self._send_json(200, result)
        except Exception as e:
            self._send_error_response(500, f"browser open 失败: {e}")

    def _handle_browser_run(self):
        try:
            payload = self._read_payload() or {}
            result = _run_actions(
                session_id=payload.get("sessionId", ""),
                actions=payload.get("actions", []),
                options=payload.get("options", {})
            )
            self._send_json(200, result)
        except Exception as e:
            self._send_error_response(500, f"browser run 失败: {e}")

    def _handle_browser_close(self):
        try:
            payload = self._read_payload() or {}
            session_id = payload.get("sessionId", "")
            with _SESSIONS_LOCK:
                s = _SESSIONS.get(session_id)
                if s:
                    try:
                        s["context"].close()
                        s["browser"].close()
                    except Exception:
                        pass
                    _SESSIONS.pop(session_id, None)
            self._send_json(200, {"ok": True, "sessionId": session_id})
        except Exception as e:
            self._send_error_response(500, f"browser close 失败: {e}")

    def _handle_command(self):
        """处理通用命令执行请求"""
        try:
            payload = self._read_payload() or {}
            command_type = payload.get("commandType", "").lower()
            params_str = payload.get("params", "{}")

            # 解析 params JSON
            try:
                params = json.loads(params_str) if isinstance(params_str, str) else params_str
            except (json.JSONDecodeError, TypeError):
                self._send_error_response(400, f"params 不是有效的 JSON: {params_str}")
                return

            if not command_type:
                self._send_error_response(400, "缺少 commandType")
                return

            handler = _COMMAND_HANDLERS.get(command_type)
            if not handler:
                self._send_error_response(400, f"不支持的命令类型: {command_type}")
                return

            self.log_message("执行命令: %s, params: %s", command_type, params_str)
            result = handler(params)
            self._send_json(200, result)

        except Exception as e:
            self.log_message("命令执行失败: %s", str(e))
            self._send_error_response(500, f"命令执行失败: {e}")


# ──────────────────────────────────────────────
# 通用命令执行
# ──────────────────────────────────────────────

# 串口连接管理
_SERIAL_CONNECTIONS: dict[str, subprocess.Popen] = {}
_SERIAL_LOCK = threading.Lock()


def _exec_ftp_download(params: dict) -> dict:
    """从FTP服务器下载文件"""
    ftp_server = params.get("ftpServer", "")
    ftp_user = params.get("ftpUser", "")
    ftp_password = params.get("ftpPassword", "")
    remote_path = params.get("remotePath", "")
    local_path = params.get("localPath", "")

    if not all([ftp_server, ftp_user, ftp_password, remote_path, local_path]):
        return {"ok": False, "error": "缺少FTP下载参数"}

    # 确保本地目录存在
    local_dir = os.path.dirname(local_path)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    # 使用 curl 下载
    ftp_url = f"ftp://{ftp_user}:{ftp_password}@{ftp_server}{remote_path}"
    cmd = ["curl", "-o", local_path, ftp_url]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        file_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        return {
            "ok": proc.returncode == 0 and file_size > 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "local_path": local_path,
            "file_size": file_size,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "FTP下载超时（300秒）"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _exec_serial(params: dict) -> dict:
    """连接设备串口（通过 plink 或串口工具）"""
    host = params.get("host", "")
    port = params.get("port", 3004)
    baud = params.get("baud", 115200)
    action = params.get("action", "open").lower()
    session_id = params.get("sessionId", f"serial_{host}_{port}")

    if action == "close":
        with _SERIAL_LOCK:
            proc = _SERIAL_CONNECTIONS.pop(session_id, None)
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                return {"ok": True, "message": f"串口连接已关闭: {session_id}"}
            return {"ok": True, "message": "串口连接不存在"}

    # action == "open"
    if not host or not port:
        return {"ok": False, "error": "缺少串口连接参数 host 或 port"}

    # 使用 plink 建立串口连接（通过串口交换机）
    cmd = [
        "plink", "-telnet",
        "-P", str(port),
        host,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with _SERIAL_LOCK:
            # 关闭已有连接
            old_proc = _SERIAL_CONNECTIONS.get(session_id)
            if old_proc:
                try:
                    old_proc.terminate()
                except Exception:
                    pass
            _SERIAL_CONNECTIONS[session_id] = proc

        return {"ok": True, "message": f"串口连接已建立: {host}:{port}", "sessionId": session_id}
    except FileNotFoundError:
        return {"ok": False, "error": "plink 未安装，请安装 PuTTY"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _exec_ssh(params: dict) -> dict:
    """SSH连接到设备并执行命令"""
    host = params.get("host", "")
    port = params.get("port", 22)
    user = params.get("user", "")
    password = params.get("password", "")
    command = params.get("command", "")
    timeout = params.get("timeout", 30)

    if not all([host, user, command]):
        return {"ok": False, "error": "缺少SSH参数 host、user 或 command"}

    # 使用 sshpass + ssh 执行远程命令
    # 如果 sshpass 不可用，尝试使用 plink
    cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-p", str(port),
        f"{user}@{host}",
        command,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except FileNotFoundError:
        # sshpass 不可用，尝试 plink
        return _exec_ssh_via_plink(host, port, user, password, command, timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"SSH命令执行超时（{timeout}秒）"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _exec_ssh_via_plink(host: str, port: int, user: str, password: str, command: str, timeout: int) -> dict:
    """通过 plink 执行 SSH 命令（sshpass 不可用时的回退方案）"""
    try:
        # 使用 echo 管道传递密码
        cmd = [
            "cmd.exe", "/c",
            f"echo {password} | plink -ssh -P {port} -l {user} -pw {password} "
            f"-batch -no-antispoof {host} {command}"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "method": "plink",
        }
    except FileNotFoundError:
        return {"ok": False, "error": "sshpass 和 plink 均未安装，无法执行SSH命令"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"SSH命令执行超时（{timeout}秒）"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# TFTP 服务器管理
_TFTP_PROCESS: subprocess.Popen | None = None
_TFTP_LOCK = threading.Lock()


def _exec_tftp_server(params: dict) -> dict:
    """启动/停止 TFTP 服务器"""
    global _TFTP_PROCESS

    action = params.get("action", "").lower()
    port = params.get("port", 69)
    tftp_dir = params.get("dir", r"C:\firmware_upgrade")

    if action == "stop":
        with _TFTP_LOCK:
            if _TFTP_PROCESS:
                try:
                    _TFTP_PROCESS.terminate()
                    _TFTP_PROCESS.wait(timeout=5)
                except Exception:
                    _TFTP_PROCESS.kill()
                _TFTP_PROCESS = None
            return {"ok": True, "message": "TFTP服务器已停止"}

    if action != "start":
        return {"ok": False, "error": f"不支持的 TFTP 操作: {action}，支持 start/stop"}

    # 启动 TFTP 服务器
    with _TFTP_LOCK:
        if _TFTP_PROCESS and _TFTP_PROCESS.poll() is None:
            return {"ok": True, "message": "TFTP服务器已在运行"}

        # 确保目录存在
        os.makedirs(tftp_dir, exist_ok=True)

        # 查找 tftpd32.exe
        tftpd32_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tftpd32.exe")
        if not os.path.exists(tftpd32_exe):
            return {"ok": False, "error": f"tftpd32.exe 不存在: {tftpd32_exe}"}

        try:
            _TFTP_PROCESS = subprocess.Popen(
                [tftpd32_exe],
                cwd=os.path.dirname(tftpd32_exe),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            return {"ok": True, "message": f"TFTP服务器已启动，端口: {port}，目录: {tftp_dir}"}
        except Exception as e:
            return {"ok": False, "error": f"TFTP服务器启动失败: {e}"}


def _exec_shell(params: dict) -> dict:
    """在PC代理上执行 shell 命令"""
    command = params.get("command", "")
    timeout = params.get("timeout", 30)

    if not command:
        return {"ok": False, "error": "缺少 shell 命令"}

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Shell命令执行超时（{timeout}秒）"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# 命令类型到处理函数的映射
_COMMAND_HANDLERS = {
    "ftp_download": _exec_ftp_download,
    "serial": _exec_serial,
    "ssh": _exec_ssh,
    "tftp_server": _exec_tftp_server,
    "shell": _exec_shell,
}


def _generate_self_signed_cert(cert_path: str, key_path: str):
    """生成自签名SSL证书（优先使用 Python cryptography，回退到 openssl）"""
    import socket as _socket

    hostname = _socket.gethostname()

    # 优先使用 Python 方式（跨平台更可靠）
    try:
        _generate_self_signed_cert_python(cert_path, key_path)
        return
    except ImportError:
        print("[SSL] cryptography 库未安装，尝试使用 openssl...")
    except Exception as e:
        print(f"[SSL] Python 生成证书失败: {e}")
        print("[SSL] 尝试使用 openssl...")

    # 回退到 openssl
    openssl_cmd = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", key_path,
        "-out", cert_path,
        "-days", "3650",
        "-nodes",
        "-subj", f"/CN={hostname}/O=LocalProxy",
        "-addext", f"subjectAltName=DNS:{hostname},DNS:localhost,IP:127.0.0.1"
    ]

    try:
        subprocess.run(openssl_cmd, check=True, capture_output=True, text=True)
        print(f"[SSL] 自签名证书已生成: {cert_path}")
        print(f"[SSL] 私钥已生成: {key_path}")
    except Exception as e:
        raise RuntimeError(
            "无法生成自签名证书。请安装 cryptography 库:\n"
            "  pip install cryptography\n"
        ) from e


def _generate_self_signed_cert_python(cert_path: str, key_path: str):
    """使用 Python 的 cryptography 库生成自签名证书"""
    import socket as _socket
    import ipaddress
    from datetime import datetime, timedelta, timezone

    hostname = _socket.gethostname()

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # 生成私钥
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # 保存私钥
        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        # 构建证书
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LocalProxy"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ])

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(hostname),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256(), backend=default_backend())
        )

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        print(f"[SSL] 自签名证书已生成 (cryptography): {cert_path}")

    except ImportError:
        raise RuntimeError(
            "无法生成自签名证书。请安装 cryptography 库:\n"
            "  pip install cryptography\n"
            "或者确保 openssl 命令可用。"
        )


def run_proxy_server(host="0.0.0.0", port=8888, cert_file=None, key_file=None):
    server_address = (host, port)
    httpd = http.server.HTTPServer(server_address, LocalProxyHandler)

    # 如果没有指定证书，自动生成自签名证书
    if cert_file is None or key_file is None:
        cert_dir = os.path.dirname(os.path.abspath(__file__))
        cert_file = os.path.join(cert_dir, "proxy_cert.pem")
        key_file = os.path.join(cert_dir, "proxy_key.pem")

        if not (os.path.exists(cert_file) and os.path.exists(key_file)):
            _generate_self_signed_cert(cert_file, key_file)

    # 配置 SSL
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    print(f"Local Proxy v{__version__} 启动: https://{host}:{port}")
    print("模式: 单线程，支持 Redfish/IPMI 转发和浏览器控制")
    print("\n支持的路径:")
    print("  - /redfish: 转发 Redfish 请求到目标设备")
    print("  - /ipmi: 执行 IPMI 命令")
    print("  - /browser/open: 打开浏览器")
    print("  - /browser/run: 执行浏览器操作")
    print("  - /browser/close: 关闭浏览器")
    print("  - /command: 执行本地命令（ftp_download/serial/ssh/tftp_server/shell）")

    httpd.serve_forever()


if __name__ == "__main__":
    run_proxy_server()
