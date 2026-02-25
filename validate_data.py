#!/usr/bin/env python3
"""
验证 JSON 数据文件的有效性
在提交前运行此脚本确保数据格式正确
"""

import json
import sys
from pathlib import Path

def validate_json_file(filepath):
    """验证 JSON 文件是否有效"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ {filepath} - 有效")
        if isinstance(data, dict):
            print(f"   包含 {len(data)} 个日期")
            for date in sorted(data.keys()):
                items = data[date]
                if isinstance(items, list):
                    print(f"   - {date}: {len(items)} 条")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ {filepath} - JSON 错误: {e}")
        return False
    except FileNotFoundError:
        print(f"❌ {filepath} - 文件不存在")
        return False
    except Exception as e:
        print(f"❌ {filepath} - 错误: {e}")
        return False

def main():
    """主函数"""
    script_dir = Path(__file__).parent
    
    files_to_check = [
        script_dir / 'news_data.json',
        script_dir / 'x_events_data.json'
    ]
    
    print("=" * 50)
    print("验证 JSON 数据文件")
    print("=" * 50)
    
    all_valid = True
    for filepath in files_to_check:
        if not validate_json_file(filepath):
            all_valid = False
    
    print("=" * 50)
    if all_valid:
        print("✅ 所有文件验证通过")
        return 0
    else:
        print("❌ 验证失败，请修复错误后再提交")
        return 1

if __name__ == '__main__':
    sys.exit(main())
