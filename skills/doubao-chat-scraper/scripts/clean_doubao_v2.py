#!/usr/bin/env python3
"""
清洗豆包对话 → 导入 SummerMemory
v2: 优化文件命名、标题识别、自动导入 SummerMemory
"""
import os, re, json, sys
from datetime import datetime

INPUT_DIR = "/root/.openclaw/workspace/skills/doubao-chat-scraper/output"
OUTPUT_DIR = "/tmp/doubao_cleaned"

# 会话命名映射
CHAT_NAMES = {
    "38426519926531074": "关于她（前任）",
    "38429382241292034": "Linux用户查看方法",
    "38429403870955778": "4K电影资源下载咨询",
    "38429483146920450": "OpenClaw与速率限制",
    "38429715121286914": "PostgreSQL pg_hba.conf安全性",
    "38429721830424322": "AI返工率降低规则（抖音视频）",
    "38429892069808130": "Windows关闭13336端口",
    "38430041663011074": "GT1030运行OpenClaw",
    "38430141681031682": "Spring Cloud Gateway配置",
    "38430208347173634": "uTools进程无法终止解决",
    "38430334913725442": "Nginx html目录配置",
    "38430371295611394": "Ollama代理与镜像加速",
    "38430372917518594": "openclaw doctor --fix",
    "38430484526707202": "OpenClaw配置文件讨论",
    "38430504789113858": "分析用户特质",
    "38430577937949186": "小黑Skill定制IP配图",
    "38430586164980738": "《遇见你之前》经典对话",
    "38430669169594882": "Docker启动失败排查",
}

# 完整保留的对话（前任相关）
FULL_KEEP = {"38426519926531074", "38430586164980738"}

def parse_md(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    blocks = re.split(r'\n---\n', text)
    entries = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = re.match(r'\*\*(我|豆包)：\*\*\s*`([^`]+)`\s*\n(.*)', block, re.DOTALL)
        if not m:
            continue
        role = m.group(1)
        ts = m.group(2)
        content = m.group(3).strip()
        images = re.findall(r'!\[.*?\]\((https?://[^\s\)]+)\)', content)
        text_content = re.sub(r'!\[.*?\]\([^\)]+\)\s*', '', content).strip()
        entries.append((role, ts, text_content, images))
    return entries

def extract_valuable_points(entries):
    points = []
    for role, ts, text, images in entries:
        if role != "豆包":
            continue
        text_stripped = text.strip()
        if not text_stripped or len(text_stripped) < 30:
            continue
        # 过滤明显无效的
        skip = ['补充说明', '译文：', '首先明确', '我先说']
        if any(text_stripped.startswith(k) for k in skip):
            continue
        points.append((ts, text_stripped[:600]))
    return points

def clean_chat(chat_id):
    md_path = os.path.join(INPUT_DIR, chat_id, "conversation.md")
    if not os.path.exists(md_path):
        return None
    entries = parse_md(md_path)
    if not entries:
        return None
    
    chat_name = CHAT_NAMES.get(chat_id, chat_id)
    topic = ""
    for role, ts, text, images in entries:
        if role == "我" and text:
            topic = text[:80].strip()
            break
    
    output = []
    output.append(f"# {chat_name}")
    output.append(f"")
    output.append(f"> 🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 来源：豆包对话记录")
    output.append("")
    
    if chat_id in FULL_KEEP:
        output.append("---")
        for role, ts, text, images in entries:
            label = "Likefr" if role == "我" else "豆包"
            output.append(f"**{label}** ({ts})")
            if text:
                output.append("")
                output.append(text)
            for img in images:
                output.append(f"![图片]({img})")
            output.append("")
            output.append("---")
        result = "\n".join(output)
    else:
        my_entries = [e for e in entries if e[0] == "我"]
        for role, ts, text, images in my_entries:
            if text or images:
                output.append(f"**{ts}**")
                if text:
                    output.append("")
                    output.append(text)
                for img in images:
                    output.append(f"![图片]({img})")
                output.append("")
        
        points = extract_valuable_points(entries)
        if points:
            output.append("---")
            output.append("> 豆包回答知识点摘录：")
            for ts, point in points:
                output.append(f"> - ({ts}) {point}")
                output.append("")
        
        result = "\n".join(output).rstrip() + "\n"
    
    os.makedirs(os.path.join(OUTPUT_DIR, chat_id), exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{chat_id}_{chat_name}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    
    return {
        "chat_id": chat_id,
        "name": chat_name,
        "mode": "full_keep" if chat_id in FULL_KEEP else "my_only",
        "my_msgs": sum(1 for e in entries if e[0] == "我"),
        "total_msgs": len(entries),
        "output": out_path,
    }

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = []
    for d in sorted(os.listdir(INPUT_DIR)):
        if not os.path.isdir(os.path.join(INPUT_DIR, d)):
            continue
        info = clean_chat(d)
        if info:
            results.append(info)
            mode_label = "📌 完整" if info["mode"] == "full_keep" else "✂️ 仅我"
            print(f"  {mode_label}  {info['name'][:30]:30s}  {info['my_msgs']}条提问")
    
    print(f"\n✅ 共清洗 {len(results)} 篇对话")
    print(f"   完整保留（前任）: {sum(1 for r in results if r['mode']=='full_keep')} 篇")
    print(f"   仅保留提问: {sum(1 for r in results if r['mode']=='my_only')} 篇")
    print(f"   输出: {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
