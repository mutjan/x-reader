#!/usr/bin/env python3
"""
重新标准化3月27日新闻的实体字段
"""
import json
import re

def normalize_entities(entities):
    """标准化实体名称"""
    if not entities:
        return []

    entity_mapping = {
        # 公司/品牌
        "openai": "OpenAI", "OPENAI": "OpenAI",
        "anthropic": "Anthropic", "deepmind": "DeepMind",
        "google": "Google", "meta": "Meta", "microsoft": "Microsoft",
        "nvidia": "NVIDIA", "tesla": "Tesla", "spacex": "SpaceX",
        "xai": "xAI", "grok": "Grok", "chatgpt": "GPT", "chatglm": "GLM",
        "claude": "Claude", "gemini": "Gemini", "deepseek": "DeepSeek",
        "cursor": "Cursor", "github": "GitHub", "vercel": "Vercel",
        "manus ai": "Manus", "manus": "Manus", "MANUS": "Manus",
        "perplexity": "Perplexity", "midjourney": "Midjourney",
        "stability ai": "Stability AI", "stability": "Stability AI",
        "elevenlabs": "ElevenLabs", "runway": "Runway",
        "字节": "字节跳动", "bytedance": "字节跳动",
        "腾讯": "腾讯", "tencent": "腾讯",
        "阿里": "阿里巴巴", "alibaba": "阿里巴巴",
        "智谱": "智谱AI", "zhipu": "智谱AI",
        "月之暗面": "月之暗面", "moonshot": "月之暗面",
        "cohere": "Cohere", "chroma": "Chroma",
        "youtube": "YouTube", "apple": "Apple",
        # 产品系列（去版本号）
        "gpt-4": "GPT", "gpt-5": "GPT", "gpt4": "GPT", "gpt5": "GPT",
        "gpt-4o": "GPT", "gpt-3": "GPT", "gpt3": "GPT",
        "o1": "OpenAI", "o3": "OpenAI", "o4": "OpenAI",
        "claude 3": "Claude", "claude 3.5": "Claude", "claude 4": "Claude",
        "claude code": "Claude",
        "gemini 1.5": "Gemini", "gemini 2": "Gemini", "gemini 2.5": "Gemini",
        "gemini 3": "Gemini", "gemini 3.1": "Gemini",
        "gemini ultra": "Gemini", "gemini pro": "Gemini", "gemini flash": "Gemini",
        "gemini 3.1 flash live": "Gemini",
        "grok-2": "Grok", "grok-3": "Grok", "grok 2": "Grok", "grok 3": "Grok",
        "qwen": "Qwen", "qwen3.5": "Qwen", "通义千问": "Qwen",
        "codex": "Codex", "sora": "Sora", "dalle": "DALL-E",
        "siri": "Siri", "composer 2": "Cursor",
        # 人物
        "elon musk": "Elon Musk", "musk": "Elon Musk", "马斯克": "Elon Musk",
        "sam altman": "Sam Altman", "altman": "Sam Altman",
        "sundar pichai": "Sundar Pichai", "satya nadella": "Satya Nadella",
        "tim cook": "Tim Cook", "mark zuckerberg": "Mark Zuckerberg",
        "zuckerberg": "Mark Zuckerberg", "demis hassabis": "Demis Hassabis",
        "hassabis": "Demis Hassabis", "ilya sutskever": "Ilya Sutskever",
        "andrej karpathy": "Andrej Karpathy", "karpathy": "Andrej Karpathy",
        "dario amodei": "Dario Amodei",
        "fei-fei li": "李飞飞", "李飞飞": "李飞飞",
        "jensen huang": "Jensen Huang", "黄仁勋": "Jensen Huang",
        "李彦宏": "李彦宏", "李开复": "李开复",
        "greg brockman": "Greg Brockman", "brockman": "Greg Brockman",
        "mustafa suleyman": "Mustafa Suleyman", "suleyman": "Mustafa Suleyman",
        "logan kilpatrick": "Logan Kilpatrick",
        "etash guha": "Etash Guha",
        "travis kalanick": "Travis Kalanick",
        "sheryl sandberg": "Sheryl Sandberg",
        "eric jang": "Eric Jang",
        # 技术/概念
        "llm": "LLM", "agi": "AGI", "mcp": "MCP",
        "rag": "RAG", "agent": "Agent", "agents": "Agent",
        "lmm": "LMM", "vlm": "VLM", "moe": "MoE",
        "diffusion": "Diffusion", "transformer": "Transformer",
        "多模态ai": "多模态AI", "端侧ai": "端侧AI",
        "具身智能": "具身智能", "人形机器人": "人形机器人",
        "语音识别": "语音识别", "视频生成": "视频生成",
        "预训练": "预训练", "强化学习": "强化学习",
        "越狱": "越狱攻击", "jailbreak": "越狱攻击",
        "开源模型": "开源模型", "开源ai": "开源AI",
        "数据可携带": "数据可携带",
    }

    normalized = []
    seen = set()

    for entity in entities:
        if not entity:
            continue

        # 小写用于映射查找
        entity_lower = entity.lower().strip()

        # 尝试直接映射
        if entity_lower in entity_mapping:
            normalized_entity = entity_mapping[entity_lower]
        elif entity in entity_mapping:
            normalized_entity = entity_mapping[entity]
        else:
            # 检查是否包含版本号模式，尝试提取基础名称
            # 如 "Gemini 2.5 Pro" -> 检查 "Gemini" 是否在映射中
            base_match = re.match(r'^([A-Za-z]+)\s*\d', entity)
            if base_match:
                base_name = base_match.group(1)
                if base_name.lower() in entity_mapping:
                    normalized_entity = entity_mapping[base_name.lower()]
                else:
                    normalized_entity = entity
            else:
                normalized_entity = entity

        # 去重
        if normalized_entity not in seen:
            seen.add(normalized_entity)
            normalized.append(normalized_entity)

    return normalized


def extract_entities_from_text(title, summary, title_en=""):
    """从标题和摘要中提取实体"""
    entities = []

    # 公司和产品关键词
    keywords = {
        # 公司
        "OpenAI": ["OpenAI", "ChatGPT", "GPT", "Codex", "Sora", "o3", "o1", "o4"],
        "Anthropic": ["Anthropic", "Claude"],
        "Google": ["Google", "Gemini", "DeepMind", "Gemma"],
        "Meta": ["Meta", "Facebook", "Instagram", "WhatsApp"],
        "Microsoft": ["Microsoft", "Azure", "Copilot"],
        "xAI": ["xAI", "Grok"],
        "NVIDIA": ["NVIDIA"],
        "SpaceX": ["SpaceX"],
        "Tesla": ["Tesla"],
        "Apple": ["Apple", "Siri", "Apple Intelligence"],
        "Amazon": ["Amazon", "AWS"],
        "字节跳动": ["字节跳动", "字节", "ByteDance", "TikTok"],
        "阿里巴巴": ["阿里巴巴", "阿里", "Alibaba", "通义千问", "Qwen"],
        "腾讯": ["腾讯", "Tencent", "微信", "WeChat"],
        "智谱AI": ["智谱", "智谱AI", "Zhipu", "GLM", "ChatGLM"],
        "月之暗面": ["月之暗面", "Moonshot", "Kimi"],
        "DeepSeek": ["DeepSeek"],
        "Cohere": ["Cohere"],
        "Chroma": ["Chroma"],
        "Cursor": ["Cursor", "Composer"],
        "Perplexity": ["Perplexity"],
        "Midjourney": ["Midjourney"],
        "Runway": ["Runway"],
        "Stability AI": ["Stability AI", "Stable Diffusion"],
        "ElevenLabs": ["ElevenLabs"],
        "Mozilla": ["Mozilla"],
        "Mila": ["Mila"],
        "MIT": ["MIT"],
        "YouTube": ["YouTube"],
        # "X": ["X", "Twitter"],  # 只在明确提到X公司时才添加，不作为平台标识
        "Telegram": ["Telegram"],
        "LinkedIn": ["LinkedIn"],
        "NeurIPS": ["NeurIPS"],
        "宇树": ["宇树", "Unitree"],
        # 产品（去版本号）
        "GPT": ["GPT-4", "GPT-5", "GPT-4o", "GPT-3", "GPT4", "GPT5"],
        "Claude": ["Claude 3", "Claude 3.5", "Claude 4", "Claude Code"],
        "Gemini": ["Gemini 1.5", "Gemini 2", "Gemini 2.5", "Gemini 3", "Gemini 3.1", "Gemini Ultra", "Gemini Pro", "Gemini Flash", "Gemini 3.1 Flash Live"],
        "Grok": ["Grok-2", "Grok-3", "Grok 2", "Grok 3"],
        "Qwen": ["Qwen3.5", "Qwen 3.5", "通义千问"],
        "Siri": ["Siri"],
        "Codex": ["Codex"],
        "Sora": ["Sora"],
        "DALL-E": ["DALL-E", "DALL·E"],
        "Whisper": ["Whisper"],
        # 人物
        "Elon Musk": ["Elon Musk", "马斯克", "Musk"],
        "Sam Altman": ["Sam Altman", "Altman"],
        "Andrej Karpathy": ["Andrej Karpathy", "Karpathy"],
        "Dario Amodei": ["Dario Amodei"],
        "Demis Hassabis": ["Demis Hassabis", "Hassabis"],
        "Mustafa Suleyman": ["Mustafa Suleyman", "Suleyman"],
        "Mark Zuckerberg": ["Mark Zuckerberg", "Zuckerberg"],
        "Satya Nadella": ["Satya Nadella"],
        "Sundar Pichai": ["Sundar Pichai"],
        "Tim Cook": ["Tim Cook"],
        "Jensen Huang": ["Jensen Huang", "黄仁勋"],
        "李飞飞": ["Fei-Fei Li", "李飞飞"],
        "李彦宏": ["李彦宏"],
        "李开复": ["李开复"],
        "Greg Brockman": ["Greg Brockman", "Brockman"],
        "Ilya Sutskever": ["Ilya Sutskever"],
        "Logan Kilpatrick": ["Logan Kilpatrick"],
        "Etash Guha": ["Etash Guha"],
        "Travis Kalanick": ["Travis Kalanick"],
        "Sheryl Sandberg": ["Sheryl Sandberg"],
        "Eric Jang": ["Eric Jang"],
        "Peter Steinberger": ["Peter Steinberger"],
        # 技术概念
        "AI": ["AI", "人工智能"],
        "AGI": ["AGI", "通用人工智能"],
        "LLM": ["LLM", "大语言模型", "大模型"],
        "Agent": ["Agent", "Agents", "智能体", "AI Agent"],
        "MCP": ["MCP", "Model Context Protocol"],
        "RAG": ["RAG", "检索增强生成"],
        "MoE": ["MoE", "Mixture of Experts", "混合专家"],
        "多模态AI": ["多模态AI", "多模态", "Multimodal AI"],
        "端侧AI": ["端侧AI", "Edge AI", "本地AI"],
        "具身智能": ["具身智能", "Embodied AI"],
        "人形机器人": ["人形机器人", "Humanoid Robot"],
        "语音识别": ["语音识别", "Speech Recognition"],
        "视频理解": ["视频理解", "Video Understanding"],
        "视频生成": ["视频生成", "Video Generation"],
        "图像生成": ["图像生成", "Image Generation"],
        "预训练": ["预训练", "Pre-training"],
        "强化学习": ["强化学习", "RL", "Reinforcement Learning"],
        "越狱攻击": ["越狱", "Jailbreak", "Jailbreak Attack"],
        "开源AI": ["开源AI", "Open Source AI"],
        "数据可携带": ["数据可携带", "Data Portability"],
        "IPO": ["IPO", "上市"],
        "GPU": ["GPU", "显卡"],
        "AI安全": ["AI安全", "AI Safety"],
        "AI伦理": ["AI伦理", "AI Ethics"],
    }

    text = f"{title} {summary} {title_en}".lower()

    for entity, patterns in keywords.items():
        for pattern in patterns:
            if pattern.lower() in text:
                entities.append(entity)
                break

    return list(set(entities))


def main():
    # 读取数据
    with open("news_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # 处理3月27日的数据
    date = "2026-03-27"
    if date not in data:
        print(f"未找到 {date} 的数据")
        return

    items = data[date]
    print(f"处理 {date} 的 {len(items)} 条新闻...")

    updated_count = 0
    for item in items:
        # 从文本中提取实体
        new_entities = extract_entities_from_text(
            item.get("title", ""),
            item.get("summary", ""),
            item.get("title_en", "")
        )

        # 合并现有实体（如果有）
        existing_entities = item.get("entities", [])
        all_entities = list(set(existing_entities + new_entities))

        # 标准化
        normalized = normalize_entities(all_entities)

        # 限制数量
        if len(normalized) > 5:
            normalized = normalized[:5]

        # 过滤掉非核心实体（地点、时间等）和过于泛化的实体
        filtered = []
        location_keywords = ["洛杉矶", "新墨西哥州", "北京", "上海", "深圳", "杭州", "美国", "中国"]
        generic_entities = ["AI", "人工智能", "LLM", "大语言模型", "X"]  # 过于泛化的实体 + 平台标识
        for e in normalized:
            if e not in location_keywords and e not in generic_entities:
                filtered.append(e)

        if filtered:
            item["entities"] = filtered
            updated_count += 1
            print(f"  [{item.get('title', '')[:40]}...] -> {filtered}")
        else:
            item["entities"] = []

    print(f"\n更新了 {updated_count} 条新闻的实体")

    # 保存数据
    with open("news_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("保存完成")


if __name__ == "__main__":
    main()
