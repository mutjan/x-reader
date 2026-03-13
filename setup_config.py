#!/usr/bin/env python3
"""
Twitter RSS 新闻选题工具 - 配置脚本
用于设置 API Key 和其他配置
"""

import os
import sys


def setup_claude_api_key():
    """设置 Claude API Key"""
    print("=" * 60)
    print("Twitter RSS 新闻选题工具 - 配置向导")
    print("=" * 60)
    print()

    # 检查当前环境变量
    current_key = os.environ.get("ANTHROPIC_API_KEY")
    if current_key:
        masked_key = current_key[:8] + "..." + current_key[-4:]
        print(f"当前已设置 ANTHROPIC_API_KEY: {masked_key}")
        choice = input("是否更新? (y/N): ").strip().lower()
        if choice != 'y':
            print("保持现有配置")
            return

    print()
    print("请输入您的 Claude API Key (从 https://console.anthropic.com/ 获取)")
    print("如果不想使用 API 调用，直接按回车跳过")
    print()

    api_key = input("API Key: ").strip()

    if not api_key:
        print()
        print("未输入 API Key，将使用本地模型模式")
        print("运行脚本时会生成提示词，需要手动发送给 Claude Desktop 处理")
        return

    # 验证 API Key 格式
    if not api_key.startswith("sk-"):
        print()
        print("警告: API Key 格式不正确，应以 'sk-' 开头")
        confirm = input("是否继续? (y/N): ").strip().lower()
        if confirm != 'y':
            return

    # 保存到配置文件
    config_dir = os.path.expanduser("~/.config/anthropic")
    os.makedirs(config_dir, exist_ok=True)

    config_file = os.path.join(config_dir, "api_key")
    with open(config_file, "w") as f:
        f.write(api_key)

    # 设置权限
    os.chmod(config_file, 0o600)

    print()
    print(f"✓ API Key 已保存到: {config_file}")
    print()
    print("配置完成！现在可以运行: python3 update_twitter_news.py")
    print()
    print("提示:")
    print("  - 脚本会自动检测并使用 API Key 进行 AI 处理")
    print("  - 如果 API 调用失败，会自动切换到本地模型模式")
    print("  - 也可以在环境变量中设置 ANTHROPIC_API_KEY")


def show_current_config():
    """显示当前配置"""
    print("=" * 60)
    print("当前配置")
    print("=" * 60)
    print()

    # 检查环境变量
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        masked = env_key[:8] + "..." + env_key[-4:]
        print(f"✓ 环境变量 ANTHROPIC_API_KEY: {masked}")
    else:
        print("✗ 环境变量 ANTHROPIC_API_KEY: 未设置")

    # 检查配置文件
    config_file = os.path.expanduser("~/.config/anthropic/api_key")
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            key = f.read().strip()
        if key:
            masked = key[:8] + "..." + key[-4:]
            print(f"✓ 配置文件 api_key: {masked}")
        else:
            print("✗ 配置文件 api_key: 为空")
    else:
        print("✗ 配置文件 api_key: 不存在")

    print()
    print("RSS 源配置:")
    print("  - URL: http://localhost:1200/twitter/list/2026563584311108010")
    print("  - 需要本地运行 RSSHub 服务")
    print()
    print("GitHub 配置:")
    print("  - 仓库: x-reader")
    print("  - 分支: main")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--show", "-s", "show"):
            show_current_config()
            return

    setup_claude_api_key()


if __name__ == "__main__":
    main()
