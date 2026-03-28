#!/usr/bin/env python3
"""
配置管理模块
集中管理所有配置项，支持环境变量覆盖和校验
"""
import os
from typing import Dict, List, Any
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings

class AppSettings(BaseSettings):
    """应用配置校验模型"""
    # GitHub配置
    GITHUB_TOKEN: str = Field(default="", description="GitHub访问令牌")
    GITHUB_BRANCH: str = Field(default="main", description="GitHub发布分支")

    # 基础配置
    MAX_CACHED_IDS: int = Field(default=5000, ge=1000, description="最大缓存处理ID数量")
    DEFAULT_BATCH_SIZE: int = Field(default=30, ge=1, le=100, description="AI处理批量大小")

    # RSS配置校验
    @validator('RSS_CONFIG', check_fields=False)
    def validate_rss_config(cls, v):
        required_fields = ['type', 'name']
        for source, config in v.items():
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"RSS源{source}缺少必填字段{field}")
        return v

# 初始化配置并校验
settings = AppSettings()

# ==================== 基础配置 ====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = BASE_DIR

# 文件路径配置
DATA_FILE = os.path.join(DATA_DIR, "news_data.json")
PROCESSED_IDS_FILE = os.path.join(DATA_DIR, ".processed_ids.json")
WORK_LOG_FILE = os.path.join(DATA_DIR, ".work_log.json")
TEMP_DIR = os.path.join(DATA_DIR, ".tmp")
AUTH_PROFILES_FILE = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")

# 缓存配置
MAX_CACHED_IDS = 5000

# GitHub配置
GITHUB_BRANCH = "main"

# 默认批量大小
DEFAULT_BATCH_SIZE = 30

# ==================== RSS 源配置 ====================
RSS_CONFIG: Dict[str, Dict[str, Any]] = {
    "twitter": {
        "url": "http://localhost:1200/twitter/home/2026563584311108010?filter_time=86400",
        "type": "rss",
        "name": "Twitter"
    },
    "inoreader": {
        "api": "https://www.inoreader.com/reader/api/0",
        "type": "api",
        "name": "Inoreader",
        "client_id": os.getenv("INOREADER_CLIENT_ID", "1000007998"),
        "client_secret": os.getenv("INOREADER_CLIENT_SECRET", "khF4gCq7J8Uut6kjconX4fdDlIJgP_yX"),
        "redirect_uri": "http://localhost:8081/callback"
    }
}

# ==================== 关键词配置 ====================
PRIORITY_KEYWORDS: Dict[str, List[str]] = {
    "ai": ["gpt-5", "gpt-4.5", "gpt5.4", "claude 4", "gemini 2",
           "o3", "o4", "reasoning", "agent", "agents", "agi",
           "openai", "anthropic", "deepmind", "xai", "grok", "perplexity", "cursor", "manus", "sora",
           "chatgpt", "claude", "gemini", "deepseek", "grok-3",
           "llm", "foundation model", "moe", "mixture of experts",
           "mcp", "model context protocol", "function calling", "tool use"],
    "bigtech": ["apple intelligence", "google ai", "microsoft ai", "meta ai",
                "nvidia", "tesla fsd", "spacex", "neuralink", "starlink",
                "微信", "wechat", "tiktok", "字节跳动", "bytedance",
                "腾讯", "tencent", "阿里", "alibaba", "百度", "baidu",
                "苹果", "apple", "谷歌", "google", "微软", "microsoft",
                "meta", "facebook", "亚马逊", "amazon"],
    "chip": ["h100", "h200", "b100", "b200", "gb200", "gh200",
             "a100", "rtx 5090", "rtx 5080", "blackwell", "hopper",
             "cuda", "ai chip", "gpu", "tpu", "npu",
             "台积电", "tsmc", "中芯国际", "smic", "高通", "qualcomm"],
    "person": ["musk", "elon musk", "altman", "sam altman",
               "hassabis", "demis hassabis", "karpathy", "andrej karpathy",
               "sundar pichai", "satya nadella", "mark zuckerberg",
               "李开复", "李彦宏", "马化腾", "马云", "张一鸣", "雷军"],
    "research": ["nature", "science", "arxiv", "paper", "research",
                 "breakthrough", "milestone", "benchmark", "sota"],
    "business": ["ipo", "融资", "估值", "收购", "并购", "融资", "funding",
                 "valuation", "acquisition", "merge", "unicorn"],
    "robotics": ["robotics", "robot", "embodied ai", "具身智能",
                 "humanoid", "人形机器人", "波士顿动力", "boston dynamics"],
    "policy": ["监管", "regulation", "policy", "ai act", "数据安全",
               "网络安全", "cybersecurity", "隐私", "privacy"]
}

# 黑名单关键词（匹配到则直接过滤）
BLACKLIST_KEYWORDS: List[str] = [
    "元宇宙", "metaverse", "vr", "ar", "mr", "xr",
    "nft", "区块链", "blockchain", "加密货币", "crypto",
    "币圈", "虚拟货币", "比特币", "bitcoin", "以太坊", "ethereum"
]

# ==================== 新闻分级配置 ====================
GRADE_THRESHOLDS = {
    "S": 90,
    "A+": 85,
    "A": 75,
    "B": 65,
    "C": 0
}

# 新闻类型配置
NEWS_TYPES = [
    "product",    # 产品发布
    "funding",    # 融资上市
    "personnel",  # 人事变动
    "opinion",    # 观点访谈
    "industry",   # 行业动态
    "safety",     # 安全伦理
    "research",   # 研究成果
    "financial",  # 商业数据
    "breaking",   # 突发事件
    "tool",       # 工具技巧
    "society",    # 社会影响
    "hardware"    # 硬件基建
]

# ==================== 日志配置 ====================
LOGGING_CONFIG = {
    "level": "INFO",
    "format": "[%(asctime)s] [%(levelname)s] %(message)s",
    "datefmt": "%Y-%m-%d %H:%M:%S"
}

# 确保临时目录存在
os.makedirs(TEMP_DIR, exist_ok=True)
