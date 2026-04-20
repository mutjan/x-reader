#!/usr/bin/env python3
"""
时代情绪管理命令行工具
"""
import argparse
from src.processors.zeitgeist import zeitgeist_manager

def list_trends(args):
    """列出当前热点"""
    trends = zeitgeist_manager.list_current_trends(include_all=args.all)
    if args.all:
        print(f"所有时代情绪热点 ({len(trends)}个):")
    else:
        print(f"当前有效时代情绪热点 ({len(trends)}个):")
    print("-" * 100)
    for i, trend in enumerate(trends, 1):
        # 基础信息
        base_info = f"{i:2d}. {trend['keyword']:<20} 分类: {trend['category']:<8} 加分: {trend['boost_value']:<3d}"

        # 状态和有效期
        if trend['expires_in'] <= 0:
            status = "已过期"
        else:
            status = f"剩余: {trend['expires_in']:3d}天"
        base_info += f" {status}"

        # 热度和趋势
        if trend.get('heat_score'):
            base_info += f" 热度: {trend['heat_score']}"
        if trend.get('trend_name'):
            base_info += f" 趋势: {trend['trend_name']}"

        print(base_info)
        print(f"     描述: {trend['description']}")

        # 扩展信息（如果有）
        if trend.get('category_name'):
            print(f"     分类名: {trend['category_name']}")
        if trend.get('related_entities') and len(trend['related_entities']) > 0:
            print(f"     相关词: {', '.join(trend['related_entities'][:5])}{'...' if len(trend['related_entities']) > 5 else ''}")
        if trend.get('mentions_count', 0) > 0:
            print(f"     提及次数: {trend['mentions_count']}")

        if i < len(trends):
            print()

def add_trend(args):
    """添加热点"""
    success = zeitgeist_manager.add_trend(
        keyword=args.keyword,
        boost_value=args.boost,
        duration_days=args.days,
        category=args.category,
        description=args.desc,
        weight=args.weight
    )
    if success:
        print(f"✅ 成功添加热点: {args.keyword}")
        print(f"   加分: {args.boost}, 有效期: {args.days}天, 分类: {args.category}")
        print(f"   描述: {args.desc}")
    else:
        print(f"❌ 热点 '{args.keyword}' 已存在")

def remove_trend(args):
    """移除热点"""
    success = zeitgeist_manager.remove_trend(args.keyword)
    if success:
        print(f"✅ 成功移除热点: {args.keyword}")
    else:
        print(f"❌ 热点 '{args.keyword}' 不存在")

def test_match(args):
    """测试内容匹配"""
    boost, matched = zeitgeist_manager.get_boost_for_content(
        args.title or "",
        args.content or "",
        args.entities.split(",") if args.entities else None
    )
    print(f"匹配结果:")
    print(f"  匹配热点: {matched if matched else '无'}")
    print(f"  总加分: {boost}")

def main():
    parser = argparse.ArgumentParser(description="时代情绪管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # list 命令
    list_parser = subparsers.add_parser("list", help="列出当前有效热点")
    list_parser.add_argument("-a", "--all", action="store_true", help="显示所有热点，包括已过期的")

    # add 命令
    add_parser = subparsers.add_parser("add", help="添加新热点")
    add_parser.add_argument("keyword", help="热点关键词")
    add_parser.add_argument("-b", "--boost", type=int, default=3, help="加分值 (默认: 3)")
    add_parser.add_argument("-d", "--days", type=int, default=30, help="有效天数 (默认: 30)")
    add_parser.add_argument("-c", "--category", default="ai", help="分类 (默认: ai)")
    add_parser.add_argument("-D", "--desc", default="", help="描述")
    add_parser.add_argument("-w", "--weight", type=float, default=0.5, help="权重 (0.1-1.0, 默认: 0.5)")

    # remove 命令
    remove_parser = subparsers.add_parser("remove", help="移除热点")
    remove_parser.add_argument("keyword", help="要移除的热点关键词")

    # test 命令
    test_parser = subparsers.add_parser("test", help="测试内容匹配")
    test_parser.add_argument("-t", "--title", help="新闻标题")
    test_parser.add_argument("-C", "--content", help="新闻内容")
    test_parser.add_argument("-e", "--entities", help="实体列表，逗号分隔")

    args = parser.parse_args()

    if args.command == "list":
        list_trends(args)
    elif args.command == "add":
        add_trend(args)
    elif args.command == "remove":
        remove_trend(args)
    elif args.command == "test":
        test_match(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
