#!/usr/bin/env python3
"""
Inoreader OAuth 授权脚本
使用 App ID 和 App Key 获取 Access Token
"""

import urllib.parse
import urllib.request
import json
import webbrowser
import http.server
import socketserver
import threading
import time

# 你的应用凭证
CLIENT_ID = "1000007998"
CLIENT_SECRET = "khF4gCq7J8Uut6kjconX4fdDlIJgP_yX"
REDIRECT_URI = "http://localhost:8080/callback"

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

def start_server():
    with socketserver.TCPServer(("", 8080), CallbackHandler) as httpd:
        httpd.timeout = 1
        print("[INFO] Local server started on port 8080, waiting for callback...")
        while server_running:
            try:
                httpd.handle_request()
            except:
                break

def get_access_token():
    global auth_code

    # 1. 构建授权URL
    auth_url = (
        f"https://www.inoreader.com/oauth2/auth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
        f"response_type=code&"
        f"scope=read&"
        f"state=xreader_auth"
    )

    print("=" * 60)
    print("Inoreader OAuth Authorization")
    print("=" * 60)
    print(f"\nApp ID: {CLIENT_ID}")
    print("\nOpening browser for authorization...")
    print("If browser does not open automatically, please visit:")
    print(f"\n{auth_url}\n")

    # 启动本地服务器
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()

    # 打开浏览器
    try:
        webbrowser.open(auth_url)
    except:
        pass

    # 等待授权码
    print("[INFO] Waiting for authorization...")
    timeout = 120  # 2分钟超时
    elapsed = 0
    while auth_code is None and elapsed < timeout:
        time.sleep(1)
        elapsed += 1
        if elapsed % 10 == 0:
            print(f"  Waiting {elapsed} seconds...")

    if auth_code is None:
        print("[ERROR] Authorization timeout")
        return None

    print(f"\n[INFO] Got authorization code: {auth_code[:20]}...")

    # 2. 交换 Access Token
    token_url = "https://www.inoreader.com/oauth2/token"
    data = urllib.parse.urlencode({
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': 'read',
        'grant_type': 'authorization_code'
    }).encode('utf-8')

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'x-reader/1.0'
    }

    print("\n[INFO] Exchanging for Access Token...")

    try:
        req = urllib.request.Request(token_url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))

            access_token = result.get('access_token')
            refresh_token = result.get('refresh_token')
            expires_in = result.get('expires_in')

            print("\n" + "=" * 60)
            print("Authorization Successful!")
            print("=" * 60)
            print(f"\nAccess Token:\n{access_token}\n")
            print(f"Refresh Token:\n{refresh_token}\n")
            print(f"Expires in: {expires_in} seconds ({expires_in // 3600} hours)")

            # 保存到文件
            config = {
                "inoreader": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_in": expires_in,
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET
                }
            }

            config_path = "/Users/lzw/.openclaw/agents/main/agent/auth-profiles.json"
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            print(f"\n[INFO] Token saved to: {config_path}")

            return access_token

    except urllib.error.HTTPError as e:
        print(f"\n[ERROR] Request failed: {e.code}")
        print(e.read().decode('utf-8'))
        return None
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        return None

def get_saved_token():
    """从配置文件读取已保存的token"""
    try:
        config_path = "/Users/lzw/.openclaw/agents/main/agent/auth-profiles.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
            token = config.get("inoreader", {}).get("access_token")
            if token:
                return token
    except Exception as e:
        print(f"[INFO] No saved token found: {e}", file=sys.stderr)
    return None


def refresh_access_token():
    """使用refresh_token刷新access_token"""
    try:
        config_path = "/Users/lzw/.openclaw/agents/main/agent/auth-profiles.json"
        with open(config_path, 'r') as f:
            config = json.load(f)

        refresh_token = config.get("inoreader", {}).get("refresh_token")
        client_id = config.get("inoreader", {}).get("client_id", CLIENT_ID)
        client_secret = config.get("inoreader", {}).get("client_secret", CLIENT_SECRET)

        if not refresh_token:
            print("[INFO] No refresh token found", file=sys.stderr)
            return None

        token_url = "https://www.inoreader.com/oauth2/token"
        data = urllib.parse.urlencode({
            'refresh_token': refresh_token,
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token'
        }).encode('utf-8')

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'x-reader/1.0'
        }

        print("[INFO] Refreshing access token...", file=sys.stderr)
        req = urllib.request.Request(token_url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            access_token = result.get('access_token')
            new_refresh_token = result.get('refresh_token', refresh_token)
            expires_in = result.get('expires_in', 86400)

            # 更新配置文件
            config["inoreader"]["access_token"] = access_token
            config["inoreader"]["refresh_token"] = new_refresh_token
            config["inoreader"]["expires_in"] = expires_in

            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            print("[INFO] Token refreshed successfully", file=sys.stderr)
            return access_token

    except urllib.error.HTTPError as e:
        print(f"[ERROR] Refresh failed: {e.code} - {e.read().decode('utf-8')}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Refresh error: {e}", file=sys.stderr)
        return None

if __name__ == "__main__":
    import sys
    # 首先尝试读取已保存的token
    saved_token = get_saved_token()
    if saved_token:
        print(saved_token)
    else:
        # 尝试刷新token
        refreshed_token = refresh_access_token()
        if refreshed_token:
            print(refreshed_token)
        else:
            # 最后尝试重新授权
            token = get_access_token()
            if token:
                print(token)
