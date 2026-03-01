#!/usr/bin/env python3
"""
Inoreader 选题筛选脚本 - 使用 Claude-Opus-4.6 进行智能选题 (OpenAI 兼容格式)
"""

import json
import subprocess
import os
import re
import time
import openai
import socks
import socket
from datetime import datetime

INOREADER_API = "https://www.inoreader.com/reader/api/0"
PROXY = "socks5h://127.0.0.1:1080"
POE_API_KEY = "VJ-9QIxmurhQkSGzteQz4ZDRp6aUwkAl8MXhp8YvJ1g"
POE_BASE_URL = "https://api.poe.com/v1"

def ensure_proxy_running():
    """确保 Shadowsocks 代理正在运行"""
    try:
        # 检查 ss-local 是否运行
        result = subprocess.run(
            ["pgrep", "-x", "ss-local"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("启动 Shadowsocks 代理...")
            # 启动代理
            subprocess.Popen(
                ["ss-local", "-c", "/tmp/ss-hk03.json"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(2)
            print("代理已启动")
        else:
            print("代理已在运行")
    except Exception as e:
        print(f"检查/启动代理时出错: {e}")

def setup_proxy():
    """设置 SOCKS5 代理并禁用 IPv6"""
    # 确保代理在运行
    ensure_proxy_running()
    
    # 禁用 IPv6
    original_getaddrinfo = socket.getaddrinfo
    def getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    socket.getaddrinfo = getaddrinfo_ipv4_only
    
    # 设置 SOCKS5 代理
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 1080)
    socket.socket = socks.socksocket
    
    return original_getaddrinfo

def restore_socket(original_getaddrinfo):
    """恢复原始 socket 设置"""
    socket.socket = socket._socketobject if hasattr(socket, '_socketobject') else socket.socket
    socket.getaddrinfo = original_getaddrinfo

def curl_request(url, headers=None, timeout=30):
    cmd = ["curl", "-s", "--connect-timeout", str(timeout), "--max-time", str(timeout * 2), "--socks5-hostname", PROXY, "-k", url]
    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def get_token():
    config_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
    with open(config_path) as f:
        config = json.load(f)
    return config.get("inoreader", {}).get("access_token")

def get_recent_items(token, hours=1, limit=50):
    """获取最近1小时的未读内容"""
    # Inoreader 使用微秒时间戳
    since_usec = int(time.time() * 1000000) - (hours * 3600 * 1000000)
    # 使用未读状态流
    url = f"{INOREADER_API}/stream/contents/user/-/state/com.google/reading-list?n={limit}&ot={since_usec}"
    
    try:
        response = curl_request(url, headers={"Authorization": f"Bearer {token}"})
        data = json.loads(response)
        
        # 过滤出未读内容
        items = data.get("items", [])
        print(f"API返回 {len(items)} 条内容")
        
        unread_items = [item for item in items if "user/-/state/com.google/read" not in item.get("categories", [])]
        print(f"其中未读 {len(unread_items)} 条")
        
        data["items"] = unread_items
        return data
    except Exception as e:
        print(f"获取内容出错: {e}")
        import traceback
        traceback.print_exc()
        return {"items": []}

def clean_html(html_text):
    if not html_text:
        return ""
    text = re.sub(r'<(script|style)[^>]*>[^<]*</\1>', ' ', html_text, flags=re.IGNORECASE)
    text = re.sub(r'<img[^>]*>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = ' '.join(text.split())
    return text.strip()[:300]

def analyze_with_claude(items):
    """使用 Claude-Opus-4.6 分析选题"""
    
    # 准备数据 - 减少到20条以避免响应过长
    news_data = []
    for i, item in enumerate(items[:20], 1):
        title = item.get("title", "")
        summary = clean_html(item.get("summary", {}).get("content", ""))
        origin = item.get("origin", {})
        source = origin.get("title", "未知来源")
        
        news_data.append({
            "id": i,
            "title": title,
            "summary": summary,
            "source": source
        })
    
    # 构建提示
    prompt = f"""你是一个资深科技媒体编辑，需要从以下新闻中筛选出最具传播潜力的选题。

【选题评估标准】（按重要性排序）：
1. 核心AI公司/产品提及 (+15分)：OpenAI, Anthropic, Claude, ChatGPT, GPT-4, Gemini, xAI等
2. 重大突破/首次 (+20分)：breakthrough, milestone, world first, 颠覆性技术, 行业首次
3. 核心人物动态 (+12分)：Sam Altman, Elon Musk, Dario Amodei, 黄仁勋等
4. 产品发布 (+18分)：新品发布、重大更新、新功能上线
5. 争议/冲突事件 (+16分)：安全争议、人事变动、公司冲突、法律纠纷
6. 融资/估值 (+14分)：大额融资、IPO、估值变化
7. 安全/伦理问题 (+13分)：AI安全、伦理争议、风险提示
8. 行业影响 (+10分)：对整个行业有重大影响的事件

【输出要求】：
1. 只推荐潜力值≥25分的选题
2. 每个选题包含：
   - 中文标题（突出亮点，吸引人点击）
   - 中文摘要（一句话概括核心内容）
   - 选题类型：【突破】【新品】【争议】【融资】【安全】【人事】
   - 核心实体（公司|人物）
   - 潜力值（0-100分）
   - 选题理由（为什么这个值得报道）
3. 相似新闻要合并成一个选题
4. 按潜力值从高到低排序

【重要提示】：
- 返回的JSON中，所有字符串值必须使用转义的双引号，不能包含未转义的双引号
- 例如："title": "这是一个标题" 是正确的，"title": "这是一个"标题"" 是错误的
- 如果内容中包含引号，请使用单引号替代或删除引号

【待筛选新闻】：
{json.dumps(news_data, ensure_ascii=False, indent=2)}

【输出格式】（JSON格式）：
{{
  "topics": [
    {{
      "title": "【类型】实体：中文标题",
      "summary": "中文摘要",
      "type": "突破|新品|争议|融资|安全|人事",
      "entity": "公司|人物",
      "score": 35,
      "reason": "选题理由",
      "source_ids": [1, 2, 3]
    }}
  ]
}}

请只返回JSON格式的结果，不要有任何其他文字。"""

    # 设置代理
    original_getaddrinfo = setup_proxy()
    
    try:
        client = openai.OpenAI(
            api_key=POE_API_KEY,
            base_url=POE_BASE_URL,
            timeout=120
        )
        
        print("调用 Claude-Opus-4.6 分析选题...")
        chat = client.chat.completions.create(
            model="claude-opus-4.6",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # 恢复代理设置
        restore_socket(original_getaddrinfo)
        
        # 解析响应
        text_response = chat.choices[0].message.content
        
        # 清理响应文本
        text_response = text_response.strip()
        
        # 提取JSON - 尝试多种方式
        result = None
        
        # 方式1: 提取 ```json ``` 代码块
        if "```json" in text_response:
            try:
                json_str = text_response.split("```json")[1].split("```")[0].strip()
                result = json.loads(json_str)
            except Exception as e:
                print(f"方式1解析失败: {e}")
                pass
        
        # 方式2: 提取 ``` ``` 代码块
        if result is None and "```" in text_response:
            try:
                json_str = text_response.split("```")[1].strip()
                result = json.loads(json_str)
            except Exception as e:
                print(f"方式2解析失败: {e}")
                pass
        
        # 方式3: 直接解析
        if result is None:
            try:
                result = json.loads(text_response)
            except Exception as e:
                print(f"方式3解析失败: {e}")
                pass
        
        # 方式4: 提取 { } 包裹的内容
        if result is None:
            try:
                start = text_response.find('{')
                end = text_response.rfind('}')
                if start != -1 and end != -1:
                    json_str = text_response[start:end+1]
                    result = json.loads(json_str)
            except Exception as e:
                print(f"方式4解析失败: {e}")
                pass
        
        if result is None:
            print(f"无法解析JSON响应，完整响应:\n{text_response}")
            return {"topics": []}
        
        return result
            
    except Exception as e:
        restore_socket(original_getaddrinfo)
        print(f"调用 Claude-Opus-4.6 出错: {e}")
        import traceback
        traceback.print_exc()
        return {"topics": []}

def mark_as_read(token, item_ids=None):
    """将所有未读内容标记为已读"""
    try:
        # 使用 mark-all-as-read API
        url = f"{INOREADER_API}/mark-all-as-read"
        cmd = [
            "curl", "-s", "-X", "POST",
            "--connect-timeout", "30",
            "--max-time", "60",
            "--socks5-hostname", PROXY,
            "-k",
            "-H", f"Authorization: Bearer {token}",
            "-d", "s=user/-/state/com.google/reading-list",
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip() == "OK":
            print(f"✅ 已标记所有内容为已读")
        else:
            print(f"⚠️  标记已读失败: {result.stderr}")
    except Exception as e:
        print(f"⚠️  标记已读时出错: {e}")

def update_github_pages(topics, original_items):
    """更新 GitHub Pages"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 读取现有数据 - 使用 x_reader 目录
        data_file = "/root/.openclaw/workspace/x_reader/news_data.json"
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                archive = json.load(f)
        else:
            archive = {}
        
        # 更新今天的数据 - 追加模式
        if today not in archive:
            archive[today] = []
        
        existing_titles = {item.get("title", "") for item in archive[today]}
        
        for t in topics:
            title = t.get("title", "")
            if title and title not in existing_titles:
                # 获取 source_ids 对应的链接
                source_links = []
                for sid in t.get("source_ids", []):
                    if 1 <= sid <= len(original_items):
                        item = original_items[sid - 1]
                        canonical = item.get("canonical", [{}])
                        if canonical:
                            link = canonical[0].get("href", "")
                            origin = item.get("origin", {})
                            source_name = origin.get("title", "未知来源")
                            if link:
                                source_links.append({"name": source_name, "url": link})
                
                archive[today].append({
                    "title": title,
                    "summary": t.get("summary", ""),
                    "type": "hot" if t.get("score", 0) >= 35 else "ai" if t.get("type") in ["突破", "新品"] else "tech",
                    "typeName": t.get("type", "科技"),
                    "sources": len(t.get("source_ids", [])),
                    "sourceLinks": source_links[:5],
                    "categories": [t.get("type", "")] if t.get("type") else [],
                    "score": t.get("score", 0),
                    "timestamp": int(time.time()),
                    "reason": t.get("reason", "")
                })
                existing_titles.add(title)
        
        # 只保留最近30天
        dates = sorted(archive.keys())
        if len(dates) > 30:
            for old_date in dates[:-30]:
                del archive[old_date]
        
        # 保存
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        
        print(f"[GitHub Pages] 数据已保存: {today}, 共 {len(archive[today])} 个选题（本次新增 {len(topics)} 个）")
        
        # Git提交
        try:
            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = "OpenClaw Bot"
            env["GIT_AUTHOR_EMAIL"] = "bot@openclaw.ai"
            
            # 切换到 Git 根目录执行操作
            git_root = "/root/.openclaw/workspace"
            
            subprocess.run(["git", "-C", git_root, "add", data_file], check=True, env=env)
            result = subprocess.run(
                ["git", "-C", git_root, "commit", "-m", f"Update topics for {today} (Claude-Opus-4.6)"],
                capture_output=True, text=True, env=env
            )
            
            if result.returncode == 0 or "nothing to commit" in result.stderr.lower() or "nothing added" in result.stdout.lower():
                push_result = subprocess.run(
                    ["git", "-C", git_root, "push", "origin", "main"],
                    capture_output=True, text=True, env=env
                )
                if push_result.returncode == 0:
                    print("[GitHub Pages] ✅ 更新成功")
                    return True
                else:
                    print(f"[GitHub Pages] ⚠️ 推送失败: {push_result.stderr}")
            else:
                print(f"[GitHub Pages] ⚠️ 提交失败: {result.stderr}")
        except Exception as git_error:
            print(f"[GitHub Pages] ⚠️ Git操作失败: {git_error}")
        
        return False
        
    except Exception as e:
        print(f"[GitHub Pages] ❌ 更新出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始选题筛选 (Claude-Opus-4.6)...")
    
    # 确保代理运行
    ensure_proxy_running()
    
    try:
        token = get_token()
        
        # 获取未读内容（最近1小时）
        print("获取最近1小时的内容...")
        items = get_recent_items(token, hours=1, limit=50)
        
        if not items.get("items"):
            print("没有新内容")
            return
        
        print(f"获取到 {len(items['items'])} 条内容")
        
        # 使用 Claude-Opus-4.6 分析
        result = analyze_with_claude(items["items"])
        
        topics = result.get("topics", [])
        
        if not topics:
            print("\n✅ 未发现高潜力选题")
        else:
            print(f"\n✅ Claude-Opus-4.6 推荐 {len(topics)} 个选题：")
            for i, t in enumerate(topics, 1):
                print(f"{i}. [{t.get('type', '')}] {t.get('title', '')} (潜力: {t.get('score', 0)})")
            
            # 更新 GitHub Pages
            update_github_pages(topics, items["items"])
        
        # 标记所有内容为已读
        mark_as_read(token)
        
        print("\n✅ 完成!")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
