#!/usr/bin/env python3
"""
清洗豆包对话 → 导入 SummerMemory 的 Markdown
规则：
1. 前任相关（关于她、遇见你之前）：保留完整对话 + 图片
2. 其他会话只保留我的发言（去掉豆包回答），但豆包回答中有价值的知识点我会摘出来作为标注
3. 输出到 /tmp/doubao_cleaned/
"""

import os, re, json, sys
from datetime import datetime

INPUT_DIR = "/root/.openclaw/workspace/skills/doubao-chat-scraper/output"
OUTPUT_DIR = "/tmp/doubao_cleaned"

# ═══ 会话分类 ═══
FULL_KEEP = {"38426519926531074", "38430586164980738"}  # 前任相关，完整保留

def parse_md(filepath):
    """把 md 解析成 [(role, timestamp, text, images), ...]"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    
    blocks = re.split(r'\n---\n', text)
    entries = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        # 提取角色和时间
        m = re.match(r'\*\*(我|豆包)：\*\*\s*`([^`]+)`\s*\n(.*)', block, re.DOTALL)
        if not m:
            continue
        
        role = m.group(1)
        ts = m.group(2)
        content = m.group(3).strip()
        
        # 提取图片链接
        images = re.findall(r'!\[.*?\]\((https?://[^\s\)]+)\)', content)
        text_content = re.sub(r'!\[.*?\]\([^\)]+\)\s*', '', content).strip()
        
        entries.append((role, ts, text_content, images))
    
    return entries

def extract_valuable_points(entries):
    """从豆包回答中提取有价值的知识点摘要"""
    points = []
    for role, ts, text, images in entries:
        if role != "豆包":
            continue
        text_stripped = text.strip()
        if not text_stripped:
            continue
        # 过滤掉纯 greeting、警告、重复说明等
        skip_patterns = [
            r'^(译文|补充说明|首先明确|我先说|先说心里话)',
            r'^(我懂你|我记得|我安安静静|我知道)',
        ]
        if any(re.match(p, text_stripped) for p in skip_patterns):
            # 但如果是前任相关的，不跳过
            if not any(kw in text_stripped for kw in ['前任', '后悔', '分手', '感情']):
                continue
        
        # 太长或者太短就跳过
        if len(text_stripped) < 30 or len(text_stripped) > 2000:
            continue
        
        points.append((ts, text_stripped[:500]))
    return points

def clean_chat(chat_id):
    """清洗单篇对话"""
    md_path = os.path.join(INPUT_DIR, chat_id, "conversation.md")
    if not os.path.exists(md_path):
        return None
    
    entries = parse_md(md_path)
    if not entries:
        return None
    
    # 获取会话名称（第一句我的提问）
    topic = ""
    for role, ts, text, images in entries:
        if role == "我" and text:
            topic = text[:60].strip()
            break
    if not topic:
        topic = chat_id
    
    output = []
    output.append(f"# {topic}")
    output.append(f"> 来源：豆包对话 · {chat_id}")
    output.append(f"> 清洗时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output.append("")
    
    # ─── 前任相关：完整保留 ───
    if chat_id in FULL_KEEP:
        output.append("> 📌 完整保留（含豆包回答）")
        output.append("")
        for role, ts, text, images in entries:
            output.append(f"**{'Likefr' if role == '我' else '豆包'}：** `{ts}`")
            if text:
                output.append("")
                output.append(text)
            for img in images:
                output.append(f"![图片]({img})")
            output.append("")
            output.append("---")
            output.append("")
        
        result = "\n".join(output).rstrip() + "\n"
        os.makedirs(os.path.join(OUTPUT_DIR, chat_id), exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, chat_id, "cleaned.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result)
        return {
            "chat_id": chat_id,
            "topic": topic,
            "mode": "full_keep",
            "my_msgs": sum(1 for e in entries if e[0] == "我"),
            "total_msgs": len(entries),
            "output": out_path,
        }
    
    # ─── 其他会话：只保留我的发言 + 豆包知识点摘要 ───
    my_entries = [e for e in entries if e[0] == "我"]
    
    output.append("### 💬 我的提问记录")
    output.append("")
    for role, ts, text, images in my_entries:
        if text or images:
            output.append(f"**{ts}**")
            if text:
                output.append("")
                output.append(text)
            for img in images:
                output.append(f"![图片]({img})")
            output.append("")
    
    # 提取豆包的有价值知识点
    points = extract_valuable_points(entries)
    if points:
        output.append("---")
        output.append("### 📝 豆包回答中有价值的知识点摘录")
        output.append("")
        for ts, point in points:
            output.append(f"- ({ts}) {point}")
            output.append("")
    
    result = "\n".join(output).rstrip() + "\n"
    os.makedirs(os.path.join(OUTPUT_DIR, chat_id), exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, chat_id, "cleaned.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    
    return {
        "chat_id": chat_id,
        "topic": topic,
        "mode": "my_only",
        "my_msgs": len(my_entries),
        "points": len(points),
        "output": out_path,
    }

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results = []
    for d in sorted(os.listdir(INPUT_DIR)):
        if not os.path.isdir(os.path.join(INPUT_DIR, d)):
            continue
        md_path = os.path.join(INPUT_DIR, d, "conversation.md")
        if not os.path.exists(md_path):
            continue
        info = clean_chat(d)
        if info:
            results.append(info)
            mode_label = "📌 完整保留" if info["mode"] == "full_keep" else "✂️ 仅保留我的"
            print(f"{mode_label}: {info['topic'][:40]:40s} → {info['output']}")
    
    # 输出汇总
    print("\n" + "="*60)
    print(f"✅ 共清洗 {len(results)} 篇对话")
    print(f"   📌 完整保留（前任相关）: {sum(1 for r in results if r['mode']=='full_keep')} 篇")
    print(f"   ✂️ 仅保留我的发言: {sum(1 for r in results if r['mode']=='my_only')} 篇")
    print(f"   输出目录: {OUTPUT_DIR}")
    
    # 生成导入清单
    manifest = []
    for r in results:
        manifest.append({
            "chat_id": r["chat_id"],
            "topic": r["topic"],
            "mode": r["mode"],
            "path": r["output"],
        })
    
    manifest_path = os.path.join(OUTPUT_DIR, "_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"   清单: {manifest_path}")

if __name__ == "__main__":
    main()
