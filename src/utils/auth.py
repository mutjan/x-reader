#!/usr/bin/env python3
"""
认证工具模块
处理Inoreader OAuth token的获取和刷新
"""
import json
import os
import time
from typing import Optional, Dict, Any
import urllib.parse
import urllib.request

from src.config.settings import AUTH_PROFILES_FILE, RSS_CONFIG
from src.utils.common import setup_logger, save_json, load_json

logger = setup_logger("auth")

class InoreaderAuth:
    """Inoreader认证管理器"""

    def __init__(self):
        self.client_id = RSS_CONFIG["inoreader"]["client_id"]
        self.client_secret = RSS_CONFIG["inoreader"]["client_secret"]
        self.redirect_uri = RSS_CONFIG["inoreader"]["redirect_uri"]
        self.token_data: Dict[str, Any] = {}
        self.load_token()

    def load_token(self) -> bool:
        """从文件加载token"""
        if not os.path.exists(AUTH_PROFILES_FILE):
            logger.debug("认证文件不存在")
            return False

        try:
            data = load_json(AUTH_PROFILES_FILE)
            if "inoreader" in data:
                self.token_data = data["inoreader"]
                return True
            return False
        except Exception as e:
            logger.error(f"加载token失败: {e}")
            return False

    def save_token(self) -> bool:
        """保存token到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(AUTH_PROFILES_FILE), exist_ok=True)

            # 读取现有数据
            data = load_json(AUTH_PROFILES_FILE)
            data["inoreader"] = self.token_data

            # 保存
            save_json(data, AUTH_PROFILES_FILE)
            logger.info(f"Token已保存到: {AUTH_PROFILES_FILE}")
            return True
        except Exception as e:
            logger.error(f"保存token失败: {e}")
            return False

    def get_access_token(self) -> Optional[str]:
        """获取有效的access token，自动刷新如果过期"""
        if not self.token_data:
            logger.error("没有可用的token，请先运行授权流程")
            return None

        # 检查是否过期（提前5分钟刷新）
        expires_at = self.token_data.get("expires_at", 0)
        if time.time() > expires_at - 300:
            logger.info("Token即将过期，尝试刷新...")
            if not self.refresh_token():
                logger.error("Token刷新失败，请重新授权")
                return None

        return self.token_data.get("access_token")

    def refresh_token(self) -> bool:
        """刷新access token"""
        refresh_token = self.token_data.get("refresh_token")
        if not refresh_token:
            logger.error("没有refresh token，无法刷新")
            return False

        try:
            token_url = "https://www.inoreader.com/oauth2/token"
            data = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token
            }

            data_encoded = urllib.parse.urlencode(data).encode('utf-8')
            req = urllib.request.Request(token_url, data=data_encoded, method='POST')

            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))

            if "access_token" in result:
                # 更新token数据
                self.token_data["access_token"] = result["access_token"]
                self.token_data["expires_in"] = result.get("expires_in", 86400)
                self.token_data["expires_at"] = time.time() + result.get("expires_in", 86400)

                # 如果返回新的refresh token，更新它
                if "refresh_token" in result:
                    self.token_data["refresh_token"] = result["refresh_token"]

                self.save_token()
                logger.info("Token刷新成功")
                return True
            else:
                logger.error(f"Token刷新失败: {result}")
                return False

        except Exception as e:
            logger.error(f"Token刷新异常: {e}")
            return False

    def exchange_code_for_token(self, code: str) -> bool:
        """使用授权码交换access token"""
        try:
            token_url = "https://www.inoreader.com/oauth2/token"
            data = {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "code": code
            }

            data_encoded = urllib.parse.urlencode(data).encode('utf-8')
            req = urllib.request.Request(token_url, data=data_encoded, method='POST')

            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))

            if "access_token" in result:
                self.token_data = {
                    "access_token": result["access_token"],
                    "refresh_token": result.get("refresh_token", ""),
                    "expires_in": result.get("expires_in", 86400),
                    "expires_at": time.time() + result.get("expires_in", 86400),
                    "scope": result.get("scope", ""),
                    "token_type": result.get("token_type", "Bearer")
                }
                self.save_token()
                return True
            else:
                logger.error(f"交换token失败: {result}")
                return False

        except Exception as e:
            logger.error(f"交换token异常: {e}")
            return False

    def is_authenticated(self) -> bool:
        """检查是否已经认证并且token有效"""
        return self.get_access_token() is not None

# 全局单例
_inoreader_auth_instance: Optional[InoreaderAuth] = None

def get_inoreader_auth() -> InoreaderAuth:
    """获取Inoreader认证单例"""
    global _inoreader_auth_instance
    if _inoreader_auth_instance is None:
        _inoreader_auth_instance = InoreaderAuth()
    return _inoreader_auth_instance
