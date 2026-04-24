"""
BMC Control Skill - 基于映射表的智能BMC设备控制

设备连接信息请参考 .codebuddy/rules/SystemTest.mdc 中的环境配置，
不要硬编码或自行猜测 IP 地址。
"""

import json
import os
from typing import Dict, List, Any, Optional

# 设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取，不允许硬编码或自行猜测
MAP_FILE = os.path.join(os.path.dirname(__file__), "bmc_map.json")

class BMCController:
    """BMC设备控制器"""
    
    def __init__(self, device_ip: str, username: str, password: str):
        """
        初始化BMC控制器。
        设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取，不允许硬编码或自行猜测。
        
        Args:
            device_ip: BMC设备IP地址（从SystemTest.mdc读取）
            username: 登录用户名（从SystemTest.mdc读取）
            password: 登录密码（从SystemTest.mdc读取）
        """
        self.device_ip = device_ip
        self.username = username
        self.password = password
        self.base_url = f"https://{device_ip}"
        self.map_data = self._load_map()
        
    def _load_map(self) -> Dict:
        """加载映射表"""
        if os.path.exists(MAP_FILE):
            with open(MAP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def login(self) -> List[Dict]:
        """
        登录BMC
        返回操作列表
        """
        return [
            {"type": "goto", "url": self.base_url},
            {"type": "fill", "selector": "#username", "text": self.username},
            {"type": "fill", "selector": "#password", "text": self.password},
            {"type": "click", "selector": "button.ant-btn-primary"},
            {"type": "wait_for_load_state", "state": "networkidle"}
        ]
    
    def navigate_to_lldp(self) -> List[Dict]:
        """导航到LLDP页面"""
        lldp_url = f"{self.base_url}/bmc_setting/lldp"
        return [
            {"type": "goto", "url": lldp_url},
            {"type": "wait_for_load_state", "state": "networkidle"}
        ]
    
    def enable_lldp(self) -> List[Dict]:
        """启用LLDP"""
        actions = self.navigate_to_lldp()
        actions.extend([
            {"type": "click", "selector": ".ant-switch:not(.ant-switch-checked)"},
            {"type": "click", "selector": "button.ant-btn-primary"}
        ])
        return actions
    
    def disable_lldp(self) -> List[Dict]:
        """禁用LLDP"""
        actions = self.navigate_to_lldp()
        actions.extend([
            {"type": "click", "selector": ".ant-switch.ant-switch-checked"},
            {"type": "click", "selector": "button.ant-btn-primary"}
        ])
        return actions
    
    def navigate_to_page(self, page_name: str) -> List[Dict]:
        """
        导航到指定页面
        先查映射表，找不到则使用默认路径
        """
        pages = self.map_data.get("pages", {})
        page_info = pages.get(page_name, {})
        
        if page_info and page_info.get("url"):
            url = page_info.get("url")
        else:
            # 默认路径规则
            url_map = {
                "dashboard": f"{self.base_url}/dashboard",
                "system": f"{self.base_url}/system",
                "bmc_setting": f"{self.base_url}/bmc_setting",
                "lldp": f"{self.base_url}/bmc_setting/lldp",
                "remote_service": f"{self.base_url}/remote_service",
                "remote_maintenance": f"{self.base_url}/remote_maintenance/log/event_log",
                "firmware": f"{self.base_url}/firmware",
                "security": f"{self.base_url}/security",
                "debug": f"{self.base_url}/debug"
            }
            url = url_map.get(page_name, f"{self.base_url}/{page_name}")
        
        return [
            {"type": "goto", "url": url},
            {"type": "wait_for_load_state", "state": "networkidle"}
        ]
    
    def explore_page(self, page_name: str) -> List[Dict]:
        """
        探索页面并返回操作
        用于更新映射表
        """
        actions = self.navigate_to_page(page_name)
        actions.append({
            "type": "eval",
            "expression": """() => ({
                url: window.location.href,
                title: document.title,
                sidebar: Array.from(document.querySelectorAll('.ant-menu-item, .sider-menu')).map(m => m.textContent.trim()).filter(t => t.length > 0 && t.length < 30 && t !== '···'),
                buttons: Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).filter(t => t.length > 0).slice(0,10),
                links: Array.from(document.querySelectorAll('a')).map(a => a.textContent.trim()).filter(t => t.length > 0 && t.length < 30).slice(0,10)
            })"""
        })
        return actions
    
    def get_page_info_from_map(self, page_name: str) -> Dict:
        """从映射表获取页面信息"""
        pages = self.map_data.get("pages", {})
        return pages.get(page_name, {})


# ──────────────────────────────────────────────
# 通用辅助操作（可组合到任意 actions 列表中）
# ──────────────────────────────────────────────

def confirm_second_dialog() -> List[Dict]:
    """
    等待并检查二次确认弹窗，若存在则点击确认。
    H3C BMC Web 界面在部分操作（如添加规则、保存配置等）后可能会弹出二次确认弹窗。
    注意：并非所有操作都有二次确认，删除操作通常无二次确认。
    
    将此函数的返回值追加到 actions 列表中即可。
    
    示例：
        actions = controller.login()
        actions.append({"type": "click", "selector": ".ant-btn-primary"})
        actions.extend(confirm_second_dialog())
    """
    return [
        {"type": "wait_for_load_state", "state": "networkidle"},
        {
            "type": "eval",
            "expression": """() => {
                const modals = document.querySelectorAll('.ant-modal-wrap');
                if (modals.length > 1) {
                    const last = modals[modals.length - 1];
                    const btn = last.querySelector('.ant-btn-primary');
                    if (btn) { btn.click(); return 'clicked second confirm'; }
                }
                return 'no second confirm';
            }"""
        },
        {"type": "wait_for_load_state", "state": "networkidle"}
    ]


def fill_modal_form(fields: Dict[str, str]) -> List[Dict]:
    """
    在当前弹窗的表单中填写字段。

    Args:
        fields: 表单项序号与值的映射，如 {"1": "192.168.33.198", "3": "80"}
                key 为 .ant-form-item 的 nth-child 序号（从1开始）

    示例：
        # 填写第1项（IP/IP段）和第4项（端口）
        actions.extend(fill_modal_form({"1": "192.168.33.198", "4": "80"}))
    """
    actions = []
    for nth, value in fields.items():
        actions.append({
            "type": "fill",
            "selector": f".ant-modal-body .ant-form-item:nth-child({nth}) input.ant-input",
            "text": value
        })
    return actions


def fill_modal_form_with_range(field_configs: Dict[str, Any]) -> List[Dict]:
    """
    在当前弹窗的表单中填写字段，支持范围填写（如IP范围、端口范围）。

    Args:
        field_configs: 表单项配置，支持两种格式：
            1. 简单值：{"1": "192.168.33.198"} - 填写第1项为该值
            2. 范围值：{"1": ["192.168.33.1", "192.168.33.254"]} - 填写第1项为起始值，第2项为结束值

    示例：
        # 防火墙规则：IP范围 + 端口范围
        # 假设表单结构：第1项=起始IP，第2项=结束IP，第3项=起始端口，第4项=结束端口
        actions.extend(fill_modal_form_with_range({
            "1": ["192.168.33.1", "192.168.33.254"],  # IP范围
            "3": ["80", "443"]  # 端口范围
        }))

        # 混合使用：IP为单个值，端口为范围
        actions.extend(fill_modal_form_with_range({
            "1": "192.168.33.198",  # 单个IP
            "3": ["80", "8080"]  # 端口范围
        }))
    """
    actions = []
    for nth, value in field_configs.items():
        if isinstance(value, list) and len(value) == 2:
            # 范围值：填写两个连续的表单项（起始值和结束值）
            start_value, end_value = value
            # 填写起始值
            actions.append({
                "type": "fill",
                "selector": f".ant-modal-body .ant-form-item:nth-child({nth}) input.ant-input",
                "text": start_value
            })
            # 填写结束值（下一个表单项）
            actions.append({
                "type": "fill",
                "selector": f".ant-modal-body .ant-form-item:nth-child({int(nth) + 1}) input.ant-input",
                "text": end_value
            })
        else:
            # 简单值：只填写一个表单项
            if isinstance(value, list):
                # 如果是列表但不是2个元素，只取第一个
                value = value[0] if len(value) > 0 else ""
            actions.append({
                "type": "fill",
                "selector": f".ant-modal-body .ant-form-item:nth-child({nth}) input.ant-input",
                "text": str(value)
            })
    return actions


# ──────────────────────────────────────────────
# 便捷函数
# ──────────────────────────────────────────────

def bmc_login(device_ip: str, username: str, password: str) -> List[Dict]:
    """登录BMC。设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取。"""
    controller = BMCController(device_ip, username, password)
    return controller.login()

def bmc_enable_lldp(device_ip: str, username: str, password: str) -> List[Dict]:
    """启用LLDP。设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取。"""
    controller = BMCController(device_ip, username, password)
    return controller.enable_lldp()

def bmc_disable_lldp(device_ip: str, username: str, password: str) -> List[Dict]:
    """禁用LLDP。设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取。"""
    controller = BMCController(device_ip, username, password)
    return controller.disable_lldp()

def bmc_navigate(page_name: str, device_ip: str, username: str, password: str) -> List[Dict]:
    """导航到页面。设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取。"""
    controller = BMCController(device_ip, username, password)
    return controller.navigate_to_page(page_name)

def bmc_explore(page_name: str, device_ip: str, username: str, password: str) -> List[Dict]:
    """探索页面。设备连接信息必须从 .codebuddy/rules/SystemTest.mdc 获取。"""
    controller = BMCController(device_ip, username, password)
    return controller.explore_page(page_name)

def bmc_confirm() -> List[Dict]:
    """等待并点击二次确认弹窗的确认按钮"""
    return confirm_second_dialog()

def bmc_fill_form(fields: Dict[str, str]) -> List[Dict]:
    """在当前弹窗表单中填写字段，fields 为 {表单项序号: 值}"""
    return fill_modal_form(fields)

def bmc_fill_form_with_range(field_configs: Dict[str, Any]) -> List[Dict]:
    """
    在当前弹窗表单中填写字段，支持范围填写（如IP范围、端口范围）。
    
    适用于防火墙规则添加等场景，其中IP和端口可能需要设置起始和结束值。
    
    Args:
        field_configs: 表单项配置，支持简单值或范围值
    
    示例：
        # IP范围 + 端口范围
        actions.extend(bmc_fill_form_with_range({
            "1": ["192.168.33.1", "192.168.33.254"],
            "3": ["80", "443"]
        }))
    """
    return fill_modal_form_with_range(field_configs)