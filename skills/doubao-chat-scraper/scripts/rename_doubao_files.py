#!/usr/bin/env python3
"""
从 /tmp/doubao_cleaned 读取清洗好的对话内容
重新生成文件，使用对话名称作为文件名（去掉 chat_id 前缀）
然后按原样写入 memory/doubao/ 下
"""
import os, re

CLEANED_DIR = "/tmp/doubao_cleaned"
OUTPUT_DIR = "/root/.openclaw/workspace/memory/doubao"

# 文件名映射（去掉 chat_id）
FILENAME_MAP = {
    "38426519926531074_关于她（前任）.md": "关于她（前任）.md",
    "38429382241292034_Linux用户查看方法.md": "Linux用户查看方法.md",
    "38429483146920450_OpenClaw与速率限制.md": "OpenClaw与速率限制.md",
    "38429715121286914_PostgreSQL pg_hba.conf安全性.md": "PostgreSQL pg_hba.conf安全性.md",
    "38429721830424322_AI返工率降低规则（抖音视频）.md": "AI返工率降低规则（抖音视频）.md",
    "38429892069808130_Windows关闭13336端口.md": "Windows关闭13336端口.md",
    "38430041663011074_GT1030运行OpenClaw.md": "GT1030运行OpenClaw.md",
    "38430141681031682_Spring Cloud Gateway配置.md": "Spring Cloud Gateway配置.md",
    "38430208347173634_uTools进程无法终止解决.md": "uTools进程无法终止解决.md",
    "38430334913725442_Nginx html目录配置.md": "Nginx html目录配置.md",
    "38430371295611394_Ollama代理与镜像加速.md": "Ollama代理与镜像加速.md",
    "38430372917518594_openclaw doctor --fix.md": "openclaw doctor --fix.md",
    "38430484526707202_OpenClaw配置文件讨论.md": "OpenClaw配置文件讨论.md",
    "38430504789113858_分析用户特质.md": "分析用户特质.md",
    "38430577937949186_小黑Skill定制IP配图.md": "小黑Skill定制IP配图.md",
    "38430586164980738_《遇见你之前》经典对话.md": "《遇见你之前》经典对话.md",
    "38430669169594882_Docker启动失败排查.md": "Docker启动失败排查.md",
}

for old_name, new_name in FILENAME_MAP.items():
    old_path = os.path.join(CLEANED_DIR, old_name)
    new_path = os.path.join(OUTPUT_DIR, new_name)
    
    if not os.path.exists(old_path):
        print(f"❌ 不存在: {old_name}")
        continue
    
    with open(old_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    with open(new_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    # 删除旧文件（带 chat_id 前缀的）
    old_in_output = os.path.join(OUTPUT_DIR, old_name)
    if os.path.exists(old_in_output):
        os.remove(old_in_output)
        print(f"🗑️  删除旧文件: {old_name}")
    
    print(f"✅ {new_name}")

print("\n完成！请重新 index 刷新数据库")
