"""
BMC Control Skill - 基于映射表的智能BMC设备控制
默认登录: admin / Password@_
设备IP: 192.168.49.71
"""

import json
import os
from typing import Dict, List, Any, Optional

DEFAULT_DEVICE_IP = "192.168.49.71"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Password@_"
MAP_FILE = os.path.join(os.path.dirname(__file__), "bmc_map.json")

class BMCController:
    """BMC设备控制器"""
    
    def __init__(self, device_ip: str = DEFAULT_DEVICE_IP):
        self.device_ip = device_ip
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
            {"type": "fill", "selector": "#username", "text": DEFAULT_USERNAME},
            {"type": "fill", "selector": "#password", "text": DEFAULT_PASSWORD},
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


# 便捷函数
def bmc_login() -> List[Dict]:
    """登录BMC"""
    controller = BMCController()
    return controller.login()

def bmc_enable_lldp() -> List[Dict]:
    """启用LLDP"""
    controller = BMCController()
    return controller.enable_lldp()

def bmc_disable_lldp() -> List[Dict]:
    """禁用LLDP"""
    controller = BMCController()
    return controller.disable_lldp()

def bmc_navigate(page_name: str) -> List[Dict]:
    """导航到页面"""
    controller = BMCController()
    return controller.navigate_to_page(page_name)

def bmc_explore(page_name: str) -> List[Dict]:
    """探索页面"""
    controller = BMCController()
    return controller.explore_page(page_name)