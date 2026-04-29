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
import subprocess
import threading
import time
import os
import re
import sys
from typing import Any
from socketserver import ThreadingMixIn

try:
    import requests as _requests
except Exception:
    _requests = None

try:
    import psutil as _psutil
except Exception:
    _psutil = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

_thread_local = threading.local()
_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSIONS_LOCK = threading.Lock()

# TFTP服务器
_firmware_tftp_process = None
_firmware_tftp_port = 69  # TFTP标准端口
_firmware_dir = r"C:\firmware_upgrade"
_tftpd32_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tftpd32.exe")


def start_firmware_tftp_server():
    """启动固件文件TFTP服务器 - 使用tftpd32.exe实现"""
    global _firmware_tftp_process

    # 检查TFTP服务器是否真的在运行
    if _firmware_tftp_process is not None:
        # 检查进程是否还在运行
        if _firmware_tftp_process.poll() is None:
            return {"ok": True, "message": "TFTP服务器已在运行"}
        else:
            # 进程已退出，重置状态
            print(f"[TFTP服务器] 检测到进程已退出，重置状态")
            _firmware_tftp_process = None

    try:
        # 检查固件目录是否存在
        if not os.path.exists(_firmware_dir):
            os.makedirs(_firmware_dir, exist_ok=True)
            print(f"[TFTP服务器] 创建固件目录: {_firmware_dir}")

        # 检查tftpd32.exe是否存在
        if not os.path.exists(_tftpd32_exe):
            return {"ok": False, "error": f"tftpd32.exe不存在: {_tftpd32_exe}"}

        # 不重新创建配置文件，使用现有的tftpd32.ini
        tftpd32_ini = os.path.join(os.path.dirname(_tftpd32_exe), "tftpd32.ini")

        print(f"[TFTP服务器] 使用现有配置文件: {tftpd32_ini}")
        print(f"[TFTP服务器] TFTP根目录: {_firmware_dir}")
        print(f"[TFTP服务器] 监听端口: {_firmware_tftp_port}")

        # 启动tftpd32.exe TFTP服务器
        # tftpd32.exe会自动读取同目录下的tftpd32.ini配置文件
        # 直接启动tftpd32.exe，不使用start命令
        tftp_dir = os.path.dirname(_tftpd32_exe)
        cmd = [_tftpd32_exe]

        print(f"[TFTP服务器] 启动命令: {cmd[0]}")

        # 直接启动tftpd32.exe，使用CREATE_NEW_CONSOLE在新窗口中运行
        _firmware_tftp_process = subprocess.Popen(
            cmd,
            cwd=tftp_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )

        # 等待一段时间让TFTP服务器启动
        time.sleep(5)

        # 检查端口是否被监听
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 尝试绑定端口，如果失败说明端口已被占用
            sock.bind(("0.0.0.0", _firmware_tftp_port))
            sock.close()
            # 端口未被占用，启动失败
            _firmware_tftp_process = None
            print(f"[TFTP服务器] 启动失败：端口 {_firmware_tftp_port} 未被监听")
            return {"ok": False, "error": f"TFTP服务器启动失败：端口 {_firmware_tftp_port} 未被监听"}
        except socket.error:
            # 端口已被占用，说明TFTP服务器已成功启动
            sock.close()
            print(f"[TFTP服务器] tftpd32.exe TFTP服务器已启动")
            print(f"[TFTP服务器] 监听端口: {_firmware_tftp_port}")
            print(f"[TFTP服务器] 工作目录: {_firmware_dir}")
            return {"ok": True, "message": f"TFTP服务器已启动，监听端口 {_firmware_tftp_port}，工作目录: {_firmware_dir}"}

    except Exception as e:
        print(f"[TFTP服务器] 启动失败: {e}")
        _firmware_tftp_process = None
        return {"ok": False, "error": str(e)}


def stop_firmware_tftp_server():
    """停止固件文件TFTP服务器"""
    global _firmware_tftp_process

    # 先尝试停止已记录的进程
    if _firmware_tftp_process is not None:
        try:
            _firmware_tftp_process.terminate()
            try:
                _firmware_tftp_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _firmware_tftp_process.kill()
                _firmware_tftp_process.wait()
            print("[TFTP服务器] 已停止记录的进程")
        except Exception as e:
            print(f"[TFTP服务器] 停止记录的进程失败: {e}")

    # 查找并停止所有tftpd32.exe进程
    try:
        if _psutil is None:
            return {"ok": False, "error": "psutil模块未安装，无法查找和停止tftpd32进程"}

        killed_count = 0
        print("[TFTP服务器] 开始查找tftpd32进程...")
        for proc in _psutil.process_iter(['pid', 'name', 'exe']):
            try:
                proc_name = proc.info.get('name', '')
                if proc_name and 'tftpd32' in proc_name.lower():
                    print(f"[TFTP服务器] 发现tftpd32进程: PID={proc.info['pid']}, 路径={proc.info.get('exe')}")
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except _psutil.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    killed_count += 1
                    print(f"[TFTP服务器] 已停止进程: PID={proc.info['pid']}")
            except (_psutil.NoSuchProcess, _psutil.AccessDenied, _psutil.ZombieProcess) as e:
                print(f"[TFTP服务器] 访问进程失败: {e}")
                continue

        _firmware_tftp_process = None
        if killed_count > 0:
            print(f"[TFTP服务器] 共停止了 {killed_count} 个tftpd32进程")
            return {"ok": True, "message": f"TFTP服务器已停止，共停止了 {killed_count} 个进程"}
        else:
            print("[TFTP服务器] 未找到运行中的tftpd32进程")
            return {"ok": True, "message": "TFTP服务器未运行"}
    except Exception as e:
        print(f"[TFTP服务器] 停止失败: {e}")
        return {"ok": False, "error": str(e)}



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
        elif self.path == "/firmware/download":
            self._handle_firmware_download()
        elif self.path == "/firmware/upload":
            self._handle_firmware_upload()
        elif self.path == "/firmware/tftp/start":
            self._handle_firmware_tftp_start()
        elif self.path == "/firmware/tftp/stop":
            self._handle_firmware_tftp_stop()
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

    def _handle_firmware_download(self):
        """从FTP服务器下载固件到PC代理"""
        try:
            payload = self._read_payload() or {}
            
            ftp_server = payload.get("ftpServer", "")
            ftp_user = payload.get("ftpUser", "")
            ftp_password = payload.get("ftpPassword", "")
            firmware_path = payload.get("firmwarePath", "")
            local_dir = payload.get("localDir", "C:\\firmware_upgrade")
            local_filename = payload.get("localFilename", "firmware.bin")
            
            if not all([ftp_server, ftp_user, ftp_password, firmware_path]):
                self._send_error_response(400, "缺少FTP服务器信息")
                return
            
            # 创建本地目录
            import os
            os.makedirs(local_dir, exist_ok=True)
            
            # 构建FTP URL
            ftp_url = f"ftp://{ftp_user}:{ftp_password}@{ftp_server}{firmware_path}"
            local_path = os.path.join(local_dir, local_filename)
            
            # 使用curl下载
            cmd = ["curl", "-o", local_path, ftp_url]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # 检查文件是否存在并获取大小
            file_size = 0
            if os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
            
            result = {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "local_path": local_path,
                "file_size": file_size,
                "success": proc.returncode == 0 and file_size > 0
            }
            
            self.log_message("固件下载完成: %s, 大小: %d bytes", local_path, file_size)
            self._send_json(200, result)
        except Exception as e:
            self.log_message("固件下载失败: %s", str(e))
            self._send_error_response(500, f"固件下载失败: {e}")

    def _handle_firmware_upload(self):
        """通过TFTP上传固件到BMC设备（优先方式）"""
        try:
            payload = self._read_payload() or {}

            device_ip = payload.get("deviceIP", "")
            device_user = payload.get("deviceUser", "")
            device_pwd = payload.get("DevicePwd", "")
            local_path = payload.get("localPath", "")
            preserve = payload.get("preserve", "Retain")
            reboot_mode = payload.get("rebootMode", "Auto")
            pc_ip = payload.get("pcIP", "192.168.33.199")  # PC代理的设备网IP

            # 如果没有指定本地路径，使用默认路径
            if not local_path:
                # 尝试从固件路径参数中提取文件名
                firmware_path = payload.get("firmwarePath", "")
                if firmware_path:
                    local_filename = os.path.basename(firmware_path)
                    local_path = os.path.join(_firmware_dir, local_filename)
                    self.log_message("使用固件路径参数: %s", local_path)
                else:
                    self._send_error_response(400, "缺少 localPath 或 firmwarePath 参数")
                    return

            if not all([device_ip, device_user, device_pwd]):
                self._send_error_response(400, "缺少必要参数")
                return

            # 检查文件是否存在
            import os
            if not os.path.exists(local_path):
                self._send_error_response(404, f"固件文件不存在: {local_path}")
                return

            # 获取固件文件名
            firmware_filename = os.path.basename(local_path)
            self.log_message("固件文件名: %s", firmware_filename)

            # 步骤1: 启动TFTP服务器
            self.log_message("步骤1: 启动TFTP服务器...")
            tftp_result = start_firmware_tftp_server()
            if not tftp_result.get("ok"):
                self.log_message("TFTP服务器启动失败: %s", tftp_result.get("error"))
                # TFTP启动失败，回退到HTTP方式
                self.log_message("回退到HTTP上传方式...")
                return self._upload_via_http(device_ip, device_user, device_pwd,
                                            local_path, preserve, reboot_mode)

            self.log_message("TFTP服务器启动成功")

            # 步骤2: 构建TFTP URI
            tftp_uri = f"tftp://{pc_ip}/{firmware_filename}"
            self.log_message("步骤2: TFTP URI: %s", tftp_uri)

            # 步骤3: 通过Redfish SimpleUpdate接口触发固件升级
            self.log_message("步骤3: 通过Redfish触发固件升级...")
            upgrade_url = f"https://{device_ip}/redfish/v1/UpdateService/Actions/UpdateService.SimpleUpdate"

            # 构建请求体
            request_body = {
                "ImageURI": tftp_uri,
                "Oem": {
                    "Public": {
                        "Preserve": preserve,
                        "RebootMode": reboot_mode
                    }
                }
            }

            # 使用curl发送Redfish请求
            cmd = [
                "curl", "-k", "-X", "POST", upgrade_url,
                "-u", f"{device_user}:{device_pwd}",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(request_body, ensure_ascii=False)
            ]

            self.log_message("发送Redfish请求到: %s", upgrade_url)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            result = {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "tftp_uri": tftp_uri,
                "method": "TFTP",
                "success": proc.returncode == 0,
                "message": "固件升级请求已触发，TFTP服务器正在运行，请监控升级进度。当升级进度达到60%时，固件上传完成，可以手动停止TFTP服务器。"
            }

            self.log_message("固件升级请求完成: 返回码: %d", proc.returncode)
            self.log_message("注意: TFTP服务器仍在运行，BMC设备正在通过TFTP下载固件文件")
            self.log_message("提示: 请监控升级进度，当进度达到60%%时可以手动停止TFTP服务器")

            self._send_json(200, result)
        except Exception as e:
            self.log_message("固件上传失败: %s", str(e))
            self._send_error_response(500, f"固件上传失败: {e}")

    def _upload_via_http(self, device_ip: str, device_user: str, device_pwd: str,
                        local_path: str, preserve: str, reboot_mode: str):
        """通过HTTP multipart/form-data上传固件到BMC设备（备用方式）"""
        try:
            self.log_message("使用HTTP方式上传固件: %s", local_path)

            # 使用curl multipart/form-data上传到H3C BMC的UpdateService接口
            upload_url = f"https://{device_ip}/redfish/v1/UpdateService"

            # 构建curl命令 - 使用form-data格式
            cmd = [
                "curl", "-k", "-X", "PATCH", upload_url,
                "-u", f"{device_user}:{device_pwd}"
            ]

            # 添加form-data字段
            cmd.extend(["-F", f"rom.ima=@{local_path}"])

            # 如果有其他参数，可以添加
            if preserve:
                cmd.extend(["-F", f"Preserve={preserve}"])
            if reboot_mode:
                cmd.extend(["-F", f"RebootMode={reboot_mode}"])

            self.log_message("开始HTTP上传固件到: %s", upload_url)

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            result = {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "method": "HTTP",
                "success": proc.returncode == 0
            }

            self.log_message("HTTP固件上传完成: 返回码: %d", proc.returncode)

            self._send_json(200, result)
        except Exception as e:
            self.log_message("HTTP固件上传失败: %s", str(e))
            self._send_error_response(500, f"HTTP固件上传失败: {e}")

    def _handle_firmware_tftp_start(self):
        """启动固件文件TFTP服务器"""
        try:
            result = start_firmware_tftp_server()
            self._send_json(200, result)
        except Exception as e:
            self._send_error_response(500, f"启动TFTP服务器失败: {e}")

    def _handle_firmware_tftp_stop(self):
        """停止固件文件TFTP服务器"""
        try:
            result = stop_firmware_tftp_server()
            self._send_json(200, result)
        except Exception as e:
            self._send_error_response(500, f"停止TFTP服务器失败: {e}")


def run_proxy_server(host="0.0.0.0", port=8888):
    server_address = (host, port)
    httpd = http.server.HTTPServer(server_address, LocalProxyHandler)
    
    print(f"Local Proxy 启动: http://{host}:{port}")
    print("模式: 单线程，支持 Redfish/IPMI 转发和浏览器控制")
    print("\n支持的路径:")
    print("  - /redfish: 转发 Redfish 请求到目标设备")
    print("  - /ipmi: 执行 IPMI 命令")
    print("  - /browser/open: 打开浏览器")
    print("  - /browser/run: 执行浏览器操作")
    print("  - /browser/close: 关闭浏览器")
    print("  - /firmware/download: 从FTP下载固件")
    print("  - /firmware/upload: 上传固件到BMC")
    print("  - /firmware/tftp/start: 启动固件TFTP服务器")
    print("  - /firmware/tftp/stop: 停止固件TFTP服务器")
    print("\n注意: TFTP服务器需要手动启动，使用 /firmware/tftp/start 接口")

    httpd.serve_forever()


if __name__ == "__main__":
    run_proxy_server()
