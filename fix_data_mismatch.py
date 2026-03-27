#!/usr/bin/env python3
"""
修复3月26日数据错位问题
通过URL匹配，将正确的标题与URL关联
"""

import json

# 定义URL到正确标题的映射（根据实际推文内容）
url_to_title = {
    # 已验证的URL和正确标题
    "https://x.com/ziv_ravid/status/2036869372438876439": {
        "title": "ARC-AGI-3发布：人类100%通过率，AI不到1%",
        "summary": "ARC Prize发布新一代AGI基准测试ARC-AGI-3，人类首次接触通过率100%，而当前前沿AI推理模型通过率不到1%，展示了人类与AI在适应性学习上的巨大差距。",
        "entities": ["ARC-AGI-3", "AGI", "基准测试", "ARC Prize"],
        "type": "ai"
    },
    "https://x.com/RobertTLange/status/2036858629316280826": {
        "title": "The AI Scientist发表于Nature：全自动AI科研系统问世",
        "summary": "Sakana AI的The AI Scientist研究正式发表于Nature，该系统能够端到端自动进行科学研究，从构思到论文撰写全流程自动化，标志着AI自主科研能力的重要里程碑。",
        "entities": ["The AI Scientist", "Sakana AI", "Nature", "自动科研"],
        "type": "ai"
    },
    "https://x.com/cryptopunk7213/status/2036803164410695772": {
        "title": "谷歌TurboQuant算法炸裂发布：AI内存需求暴降6倍，内存芯片股集体暴跌",
        "summary": "Google Research推出TurboQuant压缩算法，可将AI模型内存占用降低6倍同时保持零精度损失，推理速度提升8倍。该技术可能改变AI基础设施需求，引发内存芯片股大幅下跌。",
        "entities": ["Google", "TurboQuant", "AI推理", "压缩算法"],
        "type": "ai"
    },
    "https://x.com/ai_for_success/status/2036658834266378734": {
        "title": "谷歌TurboQuant详解：KV缓存压缩至3bit，无需微调",
        "summary": "Google TurboQuant算法可将LLM的KV缓存压缩至约3bit而无需微调，实现高达8倍的注意力计算加速，解决了大模型内存瓶颈问题，在QA、编程、摘要等任务上表现优异。",
        "entities": ["Google", "TurboQuant", "KV缓存", "量化压缩"],
        "type": "ai"
    },
    "https://x.com/willccbb/status/2036671108553048569": {
        "title": "网友热议TurboQuant：'家里的多头潜在注意力'",
        "summary": "Google发布TurboQuant后，网友幽默回应'we have multi-head latent attention at home'，调侃这一突破性压缩技术让复杂的注意力机制优化变得像家用产品一样普及。",
        "entities": ["TurboQuant", "Google", "注意力机制", "MLA"],
        "type": "ai"
    },
    "https://x.com/Techmeme/status/2036797019474588137": {
        "title": "Periodic Labs融资70亿美元估值：前OpenAI和DeepMind科学家联手",
        "summary": "由前OpenAI VP Liam Fedus和DeepMind科学家Ekin Cubuk联合创立的AI科学公司Periodic Labs正寻求数亿美元融资，估值约70亿美元，专注AI for Science领域。",
        "entities": ["Periodic Labs", "Liam Fedus", "Ekin Cubuk", "AI科研"],
        "type": "business"
    },
    "https://x.com/elonmusk/status/2036889456142397808": {
        "title": "重磅！前苹果设计高管Benji Taylor加盟X任设计负责人",
        "summary": "前苹果设计高管Benji Taylor宣布加入X（原Twitter）担任设计负责人，Elon Musk发文欢迎。Taylor表示X是世界上最重要的平台，期待与团队共同塑造未来。",
        "entities": ["Benji Taylor", "X", "Elon Musk", "设计负责人"],
        "type": "business"
    },
    "https://x.com/MiTiBennett/status/2036913817754493351": {
        "title": "待验证内容",
        "summary": "需要进一步验证实际推文内容",
        "entities": [],
        "type": "tech"
    },
    "https://x.com/himanshustwts/status/2036881752174846065": {
        "title": "前Claude科学家创立Neolab：融资1.75亿美元民主化前沿AI研究",
        "summary": "由前Anthropic/Claude科学家团队创立的Neolab宣布融资1.75亿美元，致力于民主化前沿AI和研究，让先进AI技术更加开放可及。",
        "entities": ["Neolab", "Anthropic", "Claude", "AI民主化"],
        "type": "ai"
    },
    "https://x.com/ivanleomk/status/2036906271711035690": {
        "title": "待验证内容",
        "summary": "需要进一步验证实际推文内容",
        "entities": [],
        "type": "tech"
    },
    "https://x.com/Dr_JohnFletcher/status/2036828311217660025": {
        "title": "剑桥博士向Karpathy介绍The Innovation Game：去中心化算法创新平台",
        "summary": "剑桥大学数学物理博士John Fletcher向Andrej Karpathy介绍其创立的The Innovation Game (TIG)平台，通过去中心化计算协调和激励机制，让算法创新者协作解决计算难题。",
        "entities": ["The Innovation Game", "TIG", "Andrej Karpathy", "去中心化计算"],
        "type": "ai"
    },
    "https://x.com/fchollet/status/2036861893701492918": {
        "title": "ARC-AGI-3正式发布：唯一未饱和的Agentic智能基准测试",
        "summary": "François Chollet转发ARC-AGI-3发布，强调这是世界上唯一未饱和的Agentic智能基准，人类得分100%，AI不到1%，真正测试学习能力而非记忆能力。",
        "entities": ["ARC-AGI-3", "François Chollet", "AGI", "基准测试"],
        "type": "ai"
    }
}

def fix_news_data():
    """修复news_data.json中的错位数据"""
    with open('news_data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    if '2026-03-26' not in data:
        print("没有找到2026-03-26的数据")
        return

    fixed_count = 0
    for item in data['2026-03-26']:
        url = item.get('url')
        if url in url_to_title:
            correct = url_to_title[url]
            # 只更新已验证的字段
            if correct['title'] != "待验证内容":
                item['title'] = correct['title']
                item['summary'] = correct['summary']
                item['entities'] = correct['entities']
                item['type'] = correct['type']
                item['typeName'] = {"hot": "热点", "ai": "AI", "tech": "科技", "business": "商业"}.get(correct['type'], "科技")
                fixed_count += 1
                print(f"✅ 已修复: {correct['title'][:40]}...")

    # 保存修复后的数据
    with open('news_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n共修复 {fixed_count} 条数据")

if __name__ == "__main__":
    fix_news_data()
