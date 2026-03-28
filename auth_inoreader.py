#!/usr/bin/env python3
"""
Inoreader OAuth 授权脚本
使用 App ID 和 App Key 获取 Access Token
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import urllib.parse
import webbrowser
import http.server
import socketserver
import threading
import time

from src.utils.auth import get_inoreader_auth
from src.config.settings import RSS_CONFIG
from src.utils.common import setup_logger

logger = setup_logger("inoreader_auth")

# 全局变量存储授权码
auth_code = None
server_running = True

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, server_running

        if "/callback" in self.path:
            # 解析URL参数
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if 'code' in params:
                auth_code = params['code'][0]
                state = params.get('state', [''])[0]

                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                html = b"""
                <html>
                <head><title>Authorization Success</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>Authorization Successful!</h1>
                    <p>Authorization code received. Please return to the terminal.</p>
                </body>
                </html>
                """
                self.wfile.write(html)
                server_running = False
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Error: No authorization code received")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 静默日志

def start_server(port: int = 8081):
    """启动本地服务器接收回调"""
    with socketserver.TCPServer(("", port), CallbackHandler) as httpd:
        httpd.timeout = 1
        logger.info(f"本地服务器已启动，监听端口 {port}，等待回调...")
        while server_running:
            try:
                httpd.handle_request()
            except:
                break

def main():
    print("=" * 60)
    print("Inoreader OAuth 授权工具")
    print("=" * 60)

    auth = get_inoreader_auth()

    # 检查是否已经认证
    if auth.is_authenticated():
        print("\n✓ 检测到有效token，无需重新授权")
        print(f"  Access Token: {auth.token_data.get('access_token', '')[:20]}...")
        expires_at = time.localtime(auth.token_data.get('expires_at', 0))
        print(f"  过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', expires_at)}")

        # 询问是否重新授权
        choice = input("\n是否重新授权？(y/N): ").strip().lower()
        if choice != 'y' and choice != 'yes':
            print("授权流程已取消")
            return 0

    client_id = RSS_CONFIG["inoreader"]["client_id"]
    redirect_uri = RSS_CONFIG["inoreader"]["redirect_uri"]

    print(f"\nApp ID: {client_id}")
    print("\n即将打开浏览器进行授权...")
    print("如果浏览器没有自动打开，请手动访问以下地址:")
    print()

    # 构建授权URL
    auth_url = (
        f"https://www.inoreader.com/oauth2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"response_type=code&"
        f"scope=read&"
        f"state=xreader_auth"
    )

    print(auth_url)
    print()

    # 启动服务器线程
    server_thread = threading.Thread(target=start_server, args=(8081,))
    server_thread.daemon = True
    server_thread.start()

    # 打开浏览器
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        logger.warning(f"无法自动打开浏览器: {e}")

    # 等待授权码
    global auth_code
    timeout = 300  # 5分钟超时
    start_time = time.time()

    while auth_code is None and time.time() - start_time < timeout:
        time.sleep(1)

    if auth_code is None:
        logger.error("授权超时，请重试")
        return 1

    print("\n✓ 收到授权码，正在交换Access Token...")

    # 交换token
    if auth.exchange_code_for_token(auth_code):
        print("\n" + "=" * 60)
        print("✅ 授权成功！")
        print("=" * 60)
        print(f"\nAccess Token:")
        print(f"  {auth.token_data.get('access_token', '')}")
        print(f"\nRefresh Token:")
        print(f"  {auth.token_data.get('refresh_token', '')}")
        print(f"\n过期时间: {auth.token_data.get('expires_in', 86400)} 秒 (24小时)")
        print("\nToken已自动保存到配置文件")
        print("\n现在可以正常使用Inoreader数据源了")
        return 0
    else:
        logger.error("授权失败，请重试")
        return 1

if __name__ == "__main__":
    sys.exit(main())
