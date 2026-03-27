import json
import shutil

with open('/Users/lzw/Documents/LobsterAI/lzw/x-reader/news_data.json') as f:
    data = json.load(f)

today = data['2026-03-20']

# 备份
shutil.copy('/Users/lzw/Documents/LobsterAI/lzw/x-reader/news_data.json',
            '/Users/lzw/Documents/LobsterAI/lzw/x-reader/news_data.json.bak_20260320_fix')
print("已备份")

fixes = {
    4: {
        "title": "Cursor Composer 2正式发布，AI编程体验全面升级",
        "summary": "Cursor 宣布 Composer 2 正式上线，这是其 AI 编程助手的重要更新版本，带来更强的代码生成与编辑能力。",
        "entities": ["Cursor", "Composer 2"],
        "level": "A", "rating": "A", "score": 75
    },
    5: {
        "title": "Cursor迎来史上最大公关胜利：开源替代品反而为其打出口碑",
        "summary": "有评论称此次事件（opencode/Claude Max 插件事件）是 Cursor 有史以来最大的公关胜利，通过对比反而凸显了 Cursor 的产品价值。",
        "entities": ["Cursor"],
        "level": "B", "rating": "B", "score": 68
    },
    6: {
        "title": "OpenAI Codex爆发：用户数增3倍、使用量涨5倍，周活超200万",
        "summary": "OpenAI 旗下 AI 编程工具 Codex 迎来高速增长，用户数增长 3 倍、使用量增长 5 倍，周活跃用户突破 200 万，展现出强劲的市场需求。",
        "entities": ["OpenAI", "Codex"],
        "level": "A", "rating": "A", "score": 78
    },
    8: {
        "title": "Google AI Studio重磅升级：支持多人协作、实时数据连接和Firebase持久化",
        "summary": "Google DeepMind 宣布 AI Studio 的 vibe coding 功能重大升级，新增多人实时协作模式、真实服务连接能力，并支持 Firebase 进行持久化存储，大幅拓展了应用开发场景。",
        "entities": ["Google DeepMind", "AI Studio", "Firebase"],
        "level": "A", "rating": "A", "score": 78
    },
    41: {
        "title": "Overstory开源：AI编程代理编排框架新选择",
        "summary": "开源工具 Overstory 发布，专注于协调和编排多个 AI 编程代理协同工作，提供灵活的代理任务编排能力。",
        "entities": ["Overstory", "AI编程代理"],
        "level": "B", "rating": "B", "score": 68
    },
    42: {
        "title": "Codeg开源：统一本地AI代理的多智能体编程工作空间",
        "summary": "开源项目 Codeg 发布，提供统一管理多个本地 AI 编程代理的工作空间，让开发者能在单一界面中协调多个 AI 代理完成复杂开发任务。",
        "entities": ["Codeg", "多智能体", "编程代理"],
        "level": "B", "rating": "B", "score": 68
    },
    43: {
        "title": "scuda开源：通过网络远程使用GPU，解决算力资源分配难题",
        "summary": "开源项目 scuda 实现了 GPU over IP 功能，允许通过网络桥接远程机器的 GPU 资源，为分布式 AI 训练和推理提供了新的算力共享方案。",
        "entities": ["scuda", "GPU", "开源"],
        "level": "B", "rating": "B", "score": 68
    },
    44: {
        "title": "社区吐槽：OpenAI新战略？抄Anthropic而已",
        "summary": "有评论讽刺称 OpenAI 的最新产品战略不过是在复制 Anthropic 的路线，在 AI 竞争日趋激烈的背景下，大厂间互相借鉴的现象引发社区热议。",
        "entities": ["OpenAI", "Anthropic"],
        "level": "B", "rating": "B", "score": 65,
        "type": "business"
    },
    45: {
        "title": "swyx：AI竞争格局令人捧腹，行业观察者的一声苦笑",
        "summary": "知名 AI 社区观察者 swyx 对当前 AI 行业某一动态发出感叹，简短评论折射出对行业竞争态势的无奈与调侃。",
        "entities": ["swyx"],
        "level": "B", "rating": "B", "score": 62,
        "type": "business"
    },
    46: {
        "title": "Demis Hassabis点赞：AI Studio vibe coding体验迎来重大升级",
        "summary": "DeepMind CEO Demis Hassabis 转发了 Google AI Studio 的重大更新，新功能包括多人协作模式和实时服务连接，展现出 Google 在 AI 开发工具领域持续发力的决心。",
        "entities": ["Demis Hassabis", "Google AI Studio", "DeepMind"],
        "level": "B", "rating": "B", "score": 70,
        "source": "Demis Hassabis"
    },
    47: {
        "title": "CoWork大胆设想：Claude写代码+GPT 5.4处理Excel+Kling生成视频，一站式AI工作台",
        "summary": "Bindu Reddy 分享了对 CoWork 工具的大胆构想：根据不同任务智能调用最强专用模型，包括 Claude 编程、GPT 5.4 处理表格、Kling 生成视频，实现本地 AI 工作台的极致能力组合。",
        "entities": ["CoWork", "Claude", "GPT", "Kling"],
        "level": "B", "rating": "B", "score": 70,
        "source": "Bindu Reddy"
    },
    48: {
        "title": "NIK：这也太离谱了，AI圈神评层出不穷",
        "summary": "知名 AI 评论账号 NIK 对某一行业动态发出极度震惊的评论，反映出当前 AI 领域频频出现令人意想不到的新进展。",
        "entities": ["NIK"],
        "level": "B", "rating": "B", "score": 60,
        "type": "business"
    },
    49: {
        "title": 'OpenAI秘密筹备"超级应用"：统一ChatGPT、Codex、Sora等产品线',
        "summary": "据 swyx 独家爆料，OpenAI 正计划简化产品线，将 ChatGPT、Codex、Sora 等多个产品整合为一款统一的超级应用，目标是打造覆盖全场景的 AI 助手入口，与 Anthropic 等竞争对手展开正面竞争。",
        "entities": ["OpenAI", "ChatGPT", "Codex", "Sora"],
        "level": "A+", "rating": "A+", "score": 86
    },
    50: {
        "title": "dlt开源：LLM原生数据管道，支持5000+数据源一键接入",
        "summary": "开源 Python 库 dlt（data load tool）专为 LLM 应用设计，支持超过 5000 个数据源的原生连接，大幅降低 AI 应用数据管道的构建门槛。",
        "entities": ["dlt", "LLM", "数据管道", "Python"],
        "level": "B", "rating": "B", "score": 70
    },
}

# 应用修复
for idx, fix in fixes.items():
    if idx < len(today):
        item = today[idx]
        old_title = item.get('title', '')
        for key, val in fix.items():
            item[key] = val
        level = fix.get('level', item.get('level', 'B'))
        score = fix.get('score', item.get('score', 65))
        item['reason'] = "【%s级】评分%d分 | 修复错位数据" % (level, score)
        print("[%02d] 修复: %s -> %s" % (idx, old_title[:40], fix['title'][:40]))

# 检查条目 [02]
item_02 = today[2]
print("\n[02] 检查: title=%s" % item_02.get('title','')[:60])
print("         title_en=%s" % item_02.get('title_en','')[:80])

# 保存
with open('/Users/lzw/Documents/LobsterAI/lzw/x-reader/news_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("\n修复完成，已保存 news_data.json")
