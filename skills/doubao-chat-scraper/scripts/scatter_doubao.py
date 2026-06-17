#!/usr/bin/env python3
"""
1. 重命名豆包文件为更正经的标题
2. 按月份目录打散
   memory/2026-05/情感记忆一段重要的过去.md
   memory/2026-06/OpenClaw排错记录.md
   ...
"""
import os, re, shutil

MEMORY_DIR = "/root/.openclaw/workspace/memory"
DOUBAO_DIR = os.path.join(MEMORY_DIR, "doubao")

# 新文件名映射（去掉豆包味）
NEW_NAMES = {
    "关于她（前任）.md": "情感记忆一段重要的过去.md",
    "OpenClaw与速率限制.md": "OpenClaw排错记录.md",
    "OpenClaw配置文件讨论.md": "OpenClaw配置讨论记录.md",
    "Nginx html目录配置.md": "Nginx静态文件目录配置踩坑.md",
    "Docker启动失败排查.md": "Docker容器启动失败排查.md",
    "PostgreSQL pg_hba.conf安全性.md": "PostgreSQL安全配置pg_hba.md",
    "Linux用户查看方法.md": "Linux系统用户查看方法.md",
    "Windows关闭13336端口.md": "Windows端口占用排查与关闭.md",
    "uTools进程无法终止解决.md": "Windows进程无法终止排查.md",
    "Ollama代理与镜像加速.md": "Ollama模型下载代理配置.md",
    "openclaw doctor --fix.md": "OpenClaw doctor修复记录.md",
    "GT1030运行OpenClaw.md": "GT1030运行本地AI模型.md",
    "Spring Cloud Gateway配置.md": "SpringCloudGateway配置位置.md",
    "AI返工率降低规则（抖音视频）.md": "AI返工率降低技巧记录.md",
    "分析用户特质.md": "自我认知对话记录.md",
    "小黑Skill定制IP配图.md": "小黑表情IP定制配图.md",
    "《遇见你之前》经典对话.md": "电影遇见你之前经典对话.md",
}

# 开始日期 → 目标月份目录
DATE_DIRS = {
    "情感记忆一段重要的过去.md": "2026-05",
    "OpenClaw排错记录.md": "2026-06",
    "OpenClaw配置讨论记录.md": "2026-06",
    "Nginx静态文件目录配置踩坑.md": "2026-06",
    "Docker容器启动失败排查.md": "2026-06",
    "PostgreSQL安全配置pg_hba.md": "2026-06",
    "Linux系统用户查看方法.md": "2026-06",
    "Windows端口占用排查与关闭.md": "2026-06",
    "Windows进程无法终止排查.md": "2026-06",
    "Ollama模型下载代理配置.md": "2026-06",
    "OpenClaw doctor修复记录.md": "2026-06",
    "GT1030运行本地AI模型.md": "2026-06",
    "SpringCloudGateway配置位置.md": "2026-06",
    "AI返工率降低技巧记录.md": "2026-06",
    "自我认知对话记录.md": "2026-06",
    "小黑表情IP定制配图.md": "2026-06",
    "电影遇见你之前经典对话.md": "2026-06",
}

os.makedirs(os.path.join(MEMORY_DIR, "2026-05"), exist_ok=True)
os.makedirs(os.path.join(MEMORY_DIR, "2026-06"), exist_ok=True)

for old_name, new_name in NEW_NAMES.items():
    src = os.path.join(DOUBAO_DIR, old_name)
    if not os.path.exists(src):
        print(f"❌ 不存在: {old_name}")
        continue

    target_dir = os.path.join(MEMORY_DIR, DATE_DIRS[new_name])
    dst = os.path.join(target_dir, new_name)

    # 更新文件内的标题行
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()

    # 替换第一行的 # 标题
    lines = content.split("\n")
    old_title = old_name.replace(".md", "")
    lines[0] = f"# {new_name.replace('.md', '')}"
    new_content = "\n".join(lines)

    with open(dst, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ {old_name:35s} → {target_dir[target_dir.rfind('/')+1:]}/{new_name}")

# 删除 doubao 目录
if os.path.exists(DOUBAO_DIR):
    shutil.rmtree(DOUBAO_DIR)
    print(f"\n🗑️  已删除 memory/doubao/ 目录")

print(f"\n完成！")
