"""
告警处理模块

提供统一的告警通知功能，支持多种告警渠道：
- 邮件通知（SMTP）
- 钉钉机器人
- 企业微信机器人
- 自定义 Webhook

告警配置由 alert_config.yaml 管理。
"""

import hashlib
import hmac
import json
import smtplib
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any, Optional
from urllib.parse import quote

from .logging_decorator import logger
from config import (
    ALERT_ENABLED,
    ALERT_MINIMUM_LEVEL,
    ALERT_CHANNELS,
    RISK_LEVEL_MAP,
    ALERT_LEVEL_ORDER,
)


# 告警内容可用的模板变量
_TEMPLATE_VARS = [
    "risk_level", "operation", "reason", "user", "request_id", "timestamp"
]


def _render_template(template: str, context: dict) -> str:
    """渲染模板字符串，替换 {variable} 占位符"""
    for var in _TEMPLATE_VARS:
        template = template.replace(f"{{{var}}}", str(context.get(var, "")))
    return template


def _should_alert(risk_level: str) -> bool:
    """判断当前风险等级是否满足告警最低等级"""
    if not ALERT_ENABLED:
        return False
    reverse_map = {v: k for k, v in RISK_LEVEL_MAP.items()}
    level_key = reverse_map.get(risk_level, "medium")
    min_key = ALERT_MINIMUM_LEVEL.lower()
    return ALERT_LEVEL_ORDER.get(level_key, 0) >= ALERT_LEVEL_ORDER.get(min_key, 0)


# ──────────────────────────────────────────────
# 邮件通知
# ──────────────────────────────────────────────

def _send_email(config: dict, context: dict) -> bool:
    """通过 SMTP 发送告警邮件"""
    try:
        subject = _render_template(config.get("subject_template", "[MCPServer 告警] {risk_level} - {operation}"), context)
        body = _render_template(config.get("body_template", ""), context)

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = config.get("from_addr", "")
        msg["To"] = ", ".join(config.get("to_addrs", []))

        smtp_host = config.get("smtp_host", "")
        smtp_port = config.get("smtp_port", 465)
        smtp_ssl = config.get("smtp_ssl", True)

        if smtp_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                username = config.get("smtp_username")
                password = config.get("smtp_password")
                if username and password:
                    server.login(username, password)
                server.sendmail(msg["From"], config.get("to_addrs", []), msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                username = config.get("smtp_username")
                password = config.get("smtp_password")
                if username and password:
                    server.login(username, password)
                server.sendmail(msg["From"], config.get("to_addrs", []), msg.as_string())

        logger.info(f"告警邮件已发送: {subject}")
        return True
    except Exception as e:
        logger.error(f"告警邮件发送失败: {e}")
        return False


# ──────────────────────────────────────────────
# 钉钉机器人通知
# ──────────────────────────────────────────────

def _sign_dingtalk(secret: str, timestamp: str) -> str:
    """生成钉钉机器人签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.digest(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    )
    return quote(base64.b64encode(hmac_code).decode("utf-8"))


def _send_dingtalk(config: dict, context: dict) -> bool:
    """通过钉钉机器人发送告警"""
    try:
        message = _render_template(config.get("message_template", ""), context)

        webhook_url = config.get("webhook_url", "")
        security_type = config.get("security_type", "")
        secret = config.get("secret", "")

        if security_type == "sign" and secret:
            timestamp = str(int(datetime.now(timezone.utc).timestamp() * 1000))
            sign = _sign_dingtalk(secret, timestamp)
            webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {
                "title": "MCPServer 安全告警",
                "text": message,
            },
        }, ensure_ascii=False)

        req = urllib.request.Request(
            webhook_url,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("errcode", 0) != 0:
                logger.error(f"钉钉告警发送失败: {result}")
                return False

        logger.info("钉钉告警已发送")
        return True
    except Exception as e:
        logger.error(f"钉钉告警发送失败: {e}")
        return False


# ──────────────────────────────────────────────
# 企业微信机器人通知
# ──────────────────────────────────────────────

def _send_wecom(config: dict, context: dict) -> bool:
    """通过企业微信机器人发送告警"""
    try:
        message = _render_template(config.get("message_template", ""), context)

        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {
                "content": message,
            },
        }, ensure_ascii=False)

        req = urllib.request.Request(
            config.get("webhook_url", ""),
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("errcode", 0) != 0:
                logger.error(f"企业微信告警发送失败: {result}")
                return False

        logger.info("企业微信告警已发送")
        return True
    except Exception as e:
        logger.error(f"企业微信告警发送失败: {e}")
        return False


# ──────────────────────────────────────────────
# 自定义 Webhook 通知
# ──────────────────────────────────────────────

def _send_webhook(config: dict, context: dict) -> bool:
    """通过自定义 Webhook 发送告警"""
    try:
        body_str = _render_template(config.get("body_template", "{}"), context)
        headers = config.get("headers", {})

        req = urllib.request.Request(
            config.get("url", ""),
            data=body_str.encode("utf-8"),
            headers=headers,
            method=config.get("method", "POST"),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                logger.error(f"Webhook 告警发送失败: HTTP {resp.status}")
                return False

        logger.info("Webhook 告警已发送")
        return True
    except Exception as e:
        logger.error(f"Webhook 告警发送失败: {e}")
        return False


# ──────────────────────────────────────────────
# 统一告警分发
# ──────────────────────────────────────────────

# 渠道名称到处理函数的映射
_CHANNEL_HANDLERS = {
    "email": _send_email,
    "dingtalk": _send_dingtalk,
    "wecom": _send_wecom,
    "webhook": _send_webhook,
}


def send_alert(
    risk_level: str,
    operation: str,
    reason: str,
    user: str,
    request_id: str,
) -> None:
    """
    统一告警分发入口

    根据告警配置，将告警信息发送到所有已启用的渠道。
    """
    if not _should_alert(risk_level):
        return

    # 构建告警上下文
    context = {
        "risk_level": risk_level,
        "operation": operation,
        "reason": reason,
        "user": user,
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 记录告警日志
    logger.critical(
        json.dumps(
            {
                "timestamp": context["timestamp"],
                "event": "security_alert",
                "request_id": request_id,
                "risk_level": risk_level,
                "operation": operation,
                "reason": reason,
                "user": user,
            },
            ensure_ascii=False,
        )
    )

    # 遍历所有已启用的渠道发送告警
    for channel_name, channel_config in ALERT_CHANNELS.items():
        if not channel_config.get("enabled", False):
            continue
        handler = _CHANNEL_HANDLERS.get(channel_name)
        if handler:
            try:
                handler(channel_config, context)
            except Exception as e:
                logger.error(f"告警渠道 [{channel_name}] 处理异常: {e}")
        else:
            logger.warning(f"未知告警渠道: {channel_name}")


__all__ = ["send_alert"]
