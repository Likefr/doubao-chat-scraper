---
name: "doubao-chat-scraper"
description: "爬取豆包(doubao.com)对话记录，hook API 获取带时间戳+图片的完整对话，导出markdown"
---

# 豆包对话爬取

## 命令

```bash
SCRIPT="skills/doubao-chat-scraper/scripts/doubao_scraper.py"
$SCRIPT send <手机号>         # 发验证码 → 问用户要验证码 → verify
$SCRIPT verify <6位验证码>      # 填验证码（expect_navigation 等跳转）
$SCRIPT list                   # 滚动加载全部会话，分页输出
$SCRIPT list --page N         # 第 N 页
$SCRIPT scrape <序号>          # 爬单个，输出 output/<会话名>/conversation.md
$SCRIPT scrape all            # 爬全部
```

## 流程

1. **问用户手机号** → `send <手机号>` → 等验证码 → `verify <验证码>`
2. **list** → **必须**用 markdown 表格展示（`| 序号 | 会话名称 | 链接 |`），不要省略链接列，不要只说「如上」
3. **scrape** → 告知结果（消息条数 + 输出路径）

## 红线

- **只用 `doubao_scraper.py` 命令行**，禁止自己写 Python 操作 Playwright
- **手机号必须问用户要**，不许硬编码
- **不要在 send/verify 之间做其他操作**
- 列表用短路径 `/chat/xxx`，三列表格，不带域名
- 登录失败不要反复重试，告知用户重新 send

## 脚本行为约束

- `ensure_chrome`：先检测 18800 端口，有则复用，不杀不重启
- `find_existing_page`：所有操作复用已有页面，`new_page` 仅在完全无豆包页面时 fallback（会打印警告）
- 零 `page.close()`，永远不关闭已有页面
- `verify` 用 `expect_navigation` 等页面跳转，不用 sleep
