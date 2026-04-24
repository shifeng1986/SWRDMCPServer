#!/usr/bin/env python3
"""
临时HTTPS服务器 - 用于BMC固件升级

在PC代理上启动HTTPS服务器，提供固件文件供BMC设备下载
"""

import http.server
import socketserver
import ssl
import os
import sys
from pathlib import Path

# 配置
PORT = 8443
FIRMWARE_DIR = r"C:\firmware_upgrade"
FIRMWARE_FILE = "HDM3_3.05_signed.bin"
CERT_FILE = "server.pem"
KEY_FILE = "server.key"

class FirmwareHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义HTTP请求处理器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FIRMWARE_DIR, **kwargs)

    def do_GET(self):
        """处理GET请求"""
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"HTTPS Server is running")
        elif self.path == f"/{FIRMWARE_FILE}":
            # 返回固件文件
            file_path = os.path.join(FIRMWARE_DIR, FIRMWARE_FILE)
            if os.path.exists(file_path):
                self.send_response(200)
                self.send_header('Content-type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{FIRMWARE_FILE}"')
                file_size = os.path.getsize(file_path)
                self.send_header('Content-Length', str(file_size))
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
                print(f"[{self.client_address[0]}] 下载固件文件: {FIRMWARE_FILE} ({file_size} bytes)")
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"File not found")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{self.log_date_time_string()}] {format % args}")

def create_self_signed_cert():
    """创建自签名证书（如果不存在）"""
    if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
        print("正在生成自签名SSL证书...")
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            import datetime

            # 生成私钥
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # 生成证书
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Beijing"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "H3C"),
                x509.NameAttribute(NameOID.COMMON_NAME, "192.168.33.199"),
            ])

            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.utcnow()
            ).not_valid_after(
                datetime.datetime.utcnow() + datetime.timedelta(days=365)
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("192.168.33.199"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(socket.inet_aton("192.168.33.199")),
                ]),
                critical=False,
            ).sign(private_key, hashes.SHA256(), default_backend())

            # 保存证书和私钥
            with open(CERT_FILE, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            with open(KEY_FILE, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))

            print("✅ 自签名SSL证书已生成")
        except ImportError:
            print("❌ 错误：需要安装 cryptography 库")
            print("   运行: pip install cryptography")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 生成证书失败: {e}")
            sys.exit(1)

def main():
    """主函数"""
    # 检查固件文件是否存在
    firmware_path = os.path.join(FIRMWARE_DIR, FIRMWARE_FILE)
    if not os.path.exists(firmware_path):
        print(f"❌ 错误：固件文件不存在: {firmware_path}")
        sys.exit(1)

    print("="*60)
    print("BMC固件升级 - 临时HTTPS服务器")
    print("="*60)
    print(f"\n固件文件: {firmware_path}")
    print(f"文件大小: {os.path.getsize(firmware_path)} bytes")

    # 创建自签名证书
    create_self_signed_cert()

    # 创建SSL上下文
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERT_FILE, KEY_FILE)

    # 启动HTTPS服务器
    with socketserver.TCPServer(("0.0.0.0", PORT), FirmwareHTTPRequestHandler) as httpd:
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

        print(f"\n✅ HTTPS服务器已启动")
        print(f"   监听地址: 0.0.0.0:{PORT}")
        print(f"   设备网访问: https://192.168.33.199:{PORT}/{FIRMWARE_FILE}")
        print(f"   大网访问: https://10.41.112.148:{PORT}/{FIRMWARE_FILE}")
        print(f"\n固件URI: https://192.168.33.199:{PORT}/{FIRMWARE_FILE}")
        print("\n按 Ctrl+C 停止服务器")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n服务器已停止")

if __name__ == "__main__":
    main()
