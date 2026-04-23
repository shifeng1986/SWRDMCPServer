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
import threading
import time
from typing import Any

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
        if self.path == "/browser/open":
            self._handle_browser_open()
        elif self.path == "/browser/run":
            self._handle_browser_run()
        elif self.path == "/browser/close":
            self._handle_browser_close()
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


def run_proxy_server(host="0.0.0.0", port=8888):
    server_address = (host, port)
    httpd = http.server.HTTPServer(server_address, LocalProxyHandler)
    
    print(f"Local Proxy 启动: http://{host}:{port}")
    print("模式: 单线程，支持非截图操作")
    print("\n支持的操作类型:")
    print("  - goto: 导航到URL")
    print("  - click: 点击元素")
    print("  - fill: 填写输入框")
    print("  - press: 按键")
    print("  - wait_for_selector: 等待元素")
    print("  - wait_for_load_state: 等待页面加载")
    print("  - get_text: 获取元素文本")
    print("  - get_html: 获取元素HTML")
    print("  - get_attribute: 获取元素属性")
    print("  - eval: 执行JavaScript")
    print("  - get_all_links: 获取所有链接")
    print("  - get_all_inputs: 获取所有输入框")
    print("  - get_all_buttons: 获取所有按钮")
    print("  - get_page_info: 获取页面信息")
    print("  - query_selector_all: 查询多个元素")
    
    httpd.serve_forever()


if __name__ == "__main__":
    run_proxy_server()
