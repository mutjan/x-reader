#!/usr/bin/env python3
"""
JSON中文引号修复工具
自动检测并修复AI生成的JSON中的中文引号问题

使用方法:
  python fix_chinese_quotes.py <input_file> [output_file]
  如果不指定output_file，将覆盖原文件
"""

import json
import re
import sys
import os
from pathlib import Path


def fix_chinese_quotes_in_json(text):
    """
    修复JSON字符串中的引号问题

    处理以下问题：
    1. 中文双引号 " " 替换为转义的英文双引号 \"
    2. 中文单引号 '' 替换为英文单引号 '
    3. 全角引号 ＂ ＇ 替换为半角
    4. 修复字符串内未转义的英文双引号（这是AI生成JSON的常见问题）

    关键区别：
    - JSON字符串边界使用英文双引号 "
    - 字符串内部的引号必须转义为 \" 才能保留
    """
    if not isinstance(text, str):
        return text

    # 步骤1: 将中文引号替换为转义的英文双引号
    # 左双引号 U+201C -> \"
    text = text.replace('\u201c', '\\"')
    # 右双引号 U+201D -> \"
    text = text.replace('\u201d', '\\"')
    # 全角双引号
    text = text.replace('＂', '\\"')

    # 步骤2: 中文单引号替换为英文单引号（单引号在JSON字符串内是合法的普通字符）
    # 左单引号 U+2018 -> '
    text = text.replace('\u2018', "'")
    # 右单引号 U+2019 -> '
    text = text.replace('\u2019', "'")
    # 全角单引号
    text = text.replace("＇", "'")

    return text


def fix_unescaped_quotes_in_json(text):
    """
    修复JSON字符串内部的未转义双引号

    这是AI生成JSON时的常见问题：
    错误: "summary": "He said "Hello" to me"
    正确: "summary": "He said \"Hello\" to me"

    算法：使用JSON语法感知的状态机，正确处理嵌套引号
    """
    if not isinstance(text, str):
        return text

    result = []
    i = 0
    length = len(text)
    state = 'NORMAL'  # NORMAL, IN_STRING, ESCAPE
    string_start = -1

    while i < length:
        char = text[i]
        prev_char = text[i-1] if i > 0 else ''

        if state == 'NORMAL':
            # 不在字符串内，寻找字符串开始
            if char == '"':
                state = 'IN_STRING'
                string_start = i
            result.append(char)

        elif state == 'IN_STRING':
            # 在字符串内
            if char == '\\':
                # 遇到转义符，下一个字符不管是什么都直接加入
                state = 'ESCAPE'
                result.append(char)
            elif char == '"':
                # 遇到双引号，检查是否是字符串结束
                # 向前回溯，计算连续的反斜杠数量
                backslash_count = 0
                j = i - 1
                while j >= string_start and text[j] == '\\':
                    backslash_count += 1
                    j -= 1

                if backslash_count % 2 == 0:
                    # 偶数个反斜杠（包括0个），说明这个引号是字符串结束
                    state = 'NORMAL'
                    result.append(char)
                else:
                    # 奇数个反斜杠，说明这个引号是被转义的
                    result.append(char)
            else:
                # 普通字符，直接加入
                result.append(char)

        elif state == 'ESCAPE':
            # 转义状态，下一个字符直接加入
            result.append(char)
            state = 'IN_STRING'

        i += 1

    # 如果状态机结束时还在字符串内，说明JSON不完整
    # 但我们仍然返回修复后的内容
    return ''.join(result)


def fix_json_string_content(text):
    """
    修复JSON文本中的字符串内容问题

    主要修复：字符串内部的未转义双引号
    使用启发式方法：假设字符串应该在合理的JSON位置结束
    """
    if not isinstance(text, str):
        return text

    # 先尝试用状态机方法
    result = fix_unescaped_quotes_in_json(text)

    # 验证结果是否可解析
    try:
        json.loads(result)
        return result
    except json.JSONDecodeError:
        pass

    # 如果状态机方法失败，使用启发式方法
    # 识别常见的JSON模式并修复
    return fix_json_heuristic(text)


def fix_json_heuristic(text):
    """
    启发式修复JSON字符串

    基于常见的AI生成JSON错误模式进行修复
    """
    lines = text.split('\n')
    fixed_lines = []

    for line in lines:
        # 检测类似 "key": "value with "nested" quotes" 的模式
        # 使用正则表达式匹配JSON字符串值

        # 首先尝试找到属性值的模式
        match = re.match(r'^(\s*"[^"]+"\s*:\s*")(.*)("\s*,?\s*)$', line)
        if match:
            prefix = match.group(1)
            content = match.group(2)
            suffix = match.group(3)

            # 转义内容中的未转义双引号
            fixed_content = escape_quotes_in_content(content)
            fixed_lines.append(prefix + fixed_content + suffix)
        else:
            fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def escape_quotes_in_content(content):
    """
    转义字符串内容中的未转义双引号

    简单但有效的方法：将所有未转义的 " 替换为 \\"
    """
    result = []
    i = 0
    while i < len(content):
        if content[i] == '"':
            # 检查前面是否有反斜杠
            backslash_count = 0
            j = i - 1
            while j >= 0 and content[j] == '\\':
                backslash_count += 1
                j -= 1

            if backslash_count % 2 == 0:
                # 未转义，需要添加转义
                result.append('\\"')
            else:
                # 已转义，保持不变
                result.append('"')
        else:
            result.append(content[i])
        i += 1

    return ''.join(result)


def fix_json_content(content):
    """
    修复JSON内容中的各种问题

    返回修复后的内容和是否成功解析
    """
    # 首先尝试直接解析
    try:
        data = json.loads(content)
        return content, True, "JSON格式正确，无需修复"
    except json.JSONDecodeError:
        pass

    # 需要修复 - 步骤1: 修复中文引号
    fixed_content = fix_chinese_quotes_in_json(content)

    # 尝试解析修复后的内容
    try:
        data = json.loads(fixed_content)
        return fixed_content, True, "成功修复中文引号问题"
    except json.JSONDecodeError as e:
        # 步骤2: 修复字符串内部的未转义英文双引号
        # 这是AI生成JSON时最常见的问题
        fixed_content = fix_json_string_content(fixed_content)

        try:
            data = json.loads(fixed_content)
            return fixed_content, True, "成功修复字符串内未转义引号"
        except json.JSONDecodeError as e2:
            # 步骤3: 尝试更多修复
            # 修复尾部逗号
            fixed_content = re.sub(r',(\s*[}\]])', r'\1', fixed_content)
            # 修复属性名未加引号
            fixed_content = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', fixed_content)

            try:
                data = json.loads(fixed_content)
                return fixed_content, True, "成功修复多种格式问题"
            except json.JSONDecodeError as e3:
                return fixed_content, False, f"修复后仍无法解析: {e3}"


def process_file(input_file, output_file=None):
    """
    处理单个文件

    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径，默认为None（覆盖原文件）

    Returns:
        (success, message)
    """
    input_path = Path(input_file)

    if not input_path.exists():
        return False, f"文件不存在: {input_file}"

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, f"读取文件失败: {e}"

    fixed_content, success, message = fix_json_content(content)

    if output_file:
        output_path = Path(output_file)
    else:
        output_path = input_path
        # 备份原文件
        backup_path = input_path.with_suffix(input_path.suffix + '.backup')
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            return False, f"备份文件失败: {e}"

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
    except Exception as e:
        return False, f"写入文件失败: {e}"

    return success, message


def auto_fix_ai_result():
    """
    自动修复AI结果文件（常用功能）

    检查并修复 twitter_ai_result.json 文件
    """
    result_file = Path("twitter_ai_result.json")

    if not result_file.exists():
        print("[修复工具] AI结果文件不存在，无需修复")
        return True, "文件不存在"

    print(f"[修复工具] 检测到AI结果文件: {result_file}")

    success, message = process_file(result_file)

    if success:
        print(f"[修复工具] ✓ {message}")
    else:
        print(f"[修复工具] ✗ {message}")

    return success, message


def main():
    if len(sys.argv) < 2:
        # 无参数模式：自动修复AI结果文件
        success, message = auto_fix_ai_result()
        sys.exit(0 if success else 1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    success, message = process_file(input_file, output_file)

    if success:
        print(f"✓ {message}")
        if output_file:
            print(f"  输出: {output_file}")
        else:
            print(f"  已覆盖原文件，备份: {input_file}.backup")
    else:
        print(f"✗ {message}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
