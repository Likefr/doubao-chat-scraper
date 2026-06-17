#!/usr/bin/env python3
"""
修复 memory/doubao/ 下的 md 文件：添加对话时间元数据行
"""
import os, re

MEMORY_DIR = "/root/.openclaw/workspace/memory/doubao"

# 文件名 → (开始时间, 结束时间)
TIME_RANGES = {
    "关于她（前任）.md": ("2026-05-18 12:49", "2026-06-11 07:43"),
    "Linux用户查看方法.md": ("2026-06-10 09:20", "2026-06-10 09:21"),
    "OpenClaw与速率限制.md": ("2026-06-07 17:15", "2026-06-07 17:26"),
    "PostgreSQL pg_hba.conf安全性.md": ("2026-06-08 18:52", "2026-06-08 19:00"),
    "AI返工率降低规则（抖音视频）.md": ("2026-06-09 09:47", "2026-06-09 09:47"),
    "Windows关闭13336端口.md": ("2026-06-09 15:14", "2026-06-09 15:44"),
    "GT1030运行OpenClaw.md": ("2026-06-10 17:36", "2026-06-10 17:37"),
    "Spring Cloud Gateway配置.md": ("2026-06-11 18:38", "2026-06-11 18:40"),
    "uTools进程无法终止解决.md": ("2026-06-15 08:57", "2026-06-15 08:59"),
    "Nginx html目录配置.md": ("2026-06-12 09:27", "2026-06-12 09:37"),
    "Ollama代理与镜像加速.md": ("2026-06-12 09:58", "2026-06-12 09:58"),
    "openclaw doctor --fix.md": ("2026-06-12 12:11", "2026-06-12 12:13"),
    "OpenClaw配置文件讨论.md": ("2026-06-13 16:11", "2026-06-13 19:42"),
    "分析用户特质.md": ("2026-06-13 20:12", "2026-06-13 20:12"),
    "小黑Skill定制IP配图.md": ("2026-06-14 10:12", "2026-06-14 10:12"),
    "《遇见你之前》经典对话.md": ("2026-06-14 22:26", "2026-06-14 22:57"),
    "Docker启动失败排查.md": ("2026-06-15 09:05", "2026-06-15 09:19"),
}

for fname, (start, end) in TIME_RANGES.items():
    fpath = os.path.join(MEMORY_DIR, fname)
    if not os.path.exists(fpath):
        print(f"❌ 不存在: {fname}")
        continue
    
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 如果已经有对话时间元数据了
    if f"> 对话时间: {start} ~" in content:
        print(f"⏭️  已有: {fname}")
        continue
    
    # 替换或插入
    # 当前格式: # 标题\n\n> 🕐 清洗时间 · 来源\n\n---
    # 改成:     # 标题\n> 对话时间: ...\n\n> 🕐 清洗时间 · 来源\n\n---
    
    lines = content.split("\n")
    
    # 找 # 标题 后面第一行
    meta_line = None
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if line_stripped == f"> 🕐 " or "🕐" in line_stripped:
            meta_line = i
            break
    
    if meta_line is not None:
        # 在 > 🕐 前面插入 对话时间
        new_lines = lines[:meta_line] + [f"> 对话时间: {start} ~ {end}"] + lines[meta_line:]
    else:
        # 没有清洗时间行，在 # 标题 后插入
        new_lines = [lines[0], f"> 对话时间: {start} ~ {end}", ""] + lines[1:]
    
    new_content = "\n".join(new_lines)
    
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print(f"✅ {fname} ({start} ~ {end})")

print("\n完成！")
