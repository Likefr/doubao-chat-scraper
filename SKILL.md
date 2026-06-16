---
name: "doubao-chat-scraper"
description: "爬取豆包(doubao.com)对话记录，hook /im/chain/single API 获取带时间戳+图片的完整对话，导出markdown"
---

# 豆包对话爬取技能

本机 headless Chrome，自动登录 + 获取会话列表 + hook API 爬取，导出 markdown。

## 前提

- `google-chrome-stable` 已安装
- `playwright` 已安装（`pip install playwright`）
- 端口 18800 未被占用

## 三个命令

```bash
# 1. 登录（首次或 cookie 过期时执行，交互式输入手机号+验证码）
python3 scripts/doubao_scraper.py login

# 2. 列出会话（自动滚动加载全部，表格展示前 20 个）
python3 scripts/doubao_scraper.py list

# 3. 爬取（指定序号或全部）
python3 scripts/doubao_scraper.py scrape 3      # 爬取第 3 个会话
python3 scripts/doubao_scraper.py scrape all   # 爬取全部
```

脚本路径：`/root/.openclaw/workspace/skills/doubao-chat-scraper/scripts/doubao_scraper.py`
输出目录：`skills/doubao-chat-scraper/scripts/output/<会话名>/conversation.md`

## AI 使用流程（Skill 触发时的引导回复）

当用户请求爬取豆包对话时，按以下流程操作：

1. **先执行 `list`**，获取全部会话列表（脚本自动滚动加载全部）
2. **引导回复用户**，模板如下：

> 豆包当前共有 **272** 个会话（已加载全部）。
>
> | 序号 | 会话名称 | 链接 |
> |------|----------|------|
> | 1 | 主对话 | /chat/26351192501800962 |
> | 2 | 抖音链接解析 | /chat/38430949903238914 |
> | ... | ... | ... |
> | 20 | AI返工率降低的规则 | /chat/38429721830424322 |
>
> 需要我爬取哪个呢？你可以回复序号，或者爬取全部到本地。

3. 用户回复序号或「全部」后，执行 `scrape <序号>` 或 `scrape all`
4. 爬取完成后告知用户结果（消息条数 + 输出路径）

**注意：**
- 脚本 `list` 输出前 20 个作为预览，AI 回复时也展示前 20 个
- 会话总数（如 272）从脚本输出中获取
- 链接列用短路径（`/chat/xxx`），不带域名

## 登录流程细节

脚本自动完成以下步骤（用户只需输入手机号和验证码）：

1. 启动 headless Chrome（`--headless=new --no-sandbox --remote-debugging-port=18800`）
2. 打开 `https://www.doubao.com/chat/`
3. 点击 `button`，`innerText == "登录"`，`is_visible()`
4. `input[placeholder="请输入手机号"]` → `.fill(手机号)`
5. 勾选协议：`button[aria-checked="false"][class*="cursor-pointer"]` → `.click()`
6. 点击 `button`，`innerText == "下一步"` → 发送验证码
7. 等用户输入验证码 → `input[type != "file"]` → `.fill(验证码)`
8. 点击包含"登录"或"确认"的可见按钮（排除已匹配的"登录"按钮）
9. 成功标志：URL 包含 `from_login=1`

## 获取会话列表

选择器：`a[href*="/chat/"]`，排除 `/chat/create-image` 和 `/chat/drive/`

⚠️ **必须先滚动加载全部**：侧边栏会话是懒加载的，首屏只显示约 20 个，需要滚动 `[class*="flow-scrollbar"]` 容器到底部才能加载全部。`list_conversations` 函数已内置 `scroll_load_all` 自动完成，`list` 和 `scrape` 命令都会自动滚动加载。

列表以表格形式输出（序号 + 会话名称 + 链接），预览前 20 个，总共 N 个。

## 爬取核心原理

1. `add_init_script(HOOK_JS)` 注入 XHR hook（**必须在 `goto` 之前**）
2. 打开会话 URL → `reload()` → 等 6 秒
3. 强制 `scrollTop=0` 循环，直到 `[class*="v_list_scroller"]` 的 `scrollHeight` 稳定 20 次（加载全部历史）
4. 解析 `window._chainResponses`，按 `create_time` 排序去重
5. 输出 markdown

## asyncio 避坑

- 整个脚本只用一个 `with sync_playwright() as pw`，只 `connect_over_cdp` 一次
- 所有函数接收 `browser` 对象，只 `new_page()` / `page.close()`，不复用也不重复连接
- 这样无论爬多少个会话都不会触发事件循环冲突

## API 结构

```
POST /im/chain/single → downlink_body.pull_singe_chain_downlink_body.messages[]
```

每条消息：
- `message_id` — 唯一 ID（用于去重）
- `create_time` — 秒级 Unix 时间戳
- `user_type` — 1=用户, 2=豆包
- `content_block[].block_type` — 消息类型

| block_type | 类型 |
|---|---|
| 10000 | 文本 |
| 10052 | 图片（CDN 链接，有效期约 10 年） |
| 10025 | 搜索引用 |
| 10040 | 深度思考 |
