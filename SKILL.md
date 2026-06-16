---
name: "doubao-chat-scraper"
description: "爬取豆包(doubao.com)对话记录，hook /im/chain/single API 获取带时间戳+图片的完整对话，导出markdown"
---

# 豆包对话爬取技能

本机 headless Chrome，自动登录 + 获取会话列表 + hook API 爬取，导出 markdown。

## ⚠️ 安全声明

- **本工具不上传任何数据** — 所有操作均在本地执行，爬取的对话保存在本地 `output/` 目录
- **不会连接任何第三方服务器** — 仅与 doubao.com 通信，无外传行为
- **pkill 只针对自身启动的 Chrome** — 每次运行前清理上次残留的 headless Chrome 进程（`pkill -f remote-debugging-port=18800`），不影响系统其他进程
- **JS hook 仅拦截本地 XHR** — `add_init_script` 注入的 JS 仅在浏览器页面内拦截 doubao 的 API 响应，不修改页面、不注入恶意代码、不窃取 cookie
- **无网络外传** — 脚本不含 `requests`/`urllib` 外传逻辑（`ensure_chrome` 里的 urllib 仅用于检测本地 CDP 端口）
- **开源透明** — 所有代码可审查，无混淆、无加密、无隐藏逻辑

## 前提

- `google-chrome-stable` 已安装
- `playwright` 已安装（`pip install playwright`）
- 端口 18800 未被占用

## 三个命令

```bash
# 1. 登录（首次或 cookie 过期时执行，交互式输入手机号+验证码）
python3 scripts/doubao_scraper.py login

# 2. 列出会话（自动滚动加载全部，支持翻页）
python3 scripts/doubao_scraper.py list           # 第1页（默认）
python3 scripts/doubao_scraper.py list --page 2  # 第2页

# 3. 爬取（指定序号或全部）
python3 scripts/doubao_scraper.py scrape 3      # 爬取第 3 个会话
python3 scripts/doubao_scraper.py scrape all   # 爬取全部
```

脚本路径：`/root/.openclaw/workspace/skills/doubao-chat-scraper/scripts/doubao_scraper.py`
输出目录：`skills/doubao-chat-scraper/scripts/output/<会话名>/conversation.md`

## AI 使用流程（Skill 触发时的引导回复）

当用户请求爬取豆包对话时，按以下流程操作：

1. **先执行 `list`**（不加 --page，默认第1页），脚本会滚动加载全部会话
2. **引导回复用户**，必须以 markdown 表格展示三列：序号、会话名称、链接

模板如下：

> 豆包当前共有 **272** 个会话，当前显示第 1 页（1-20，共 14 页）。
>
> | 序号 | 会话名称 | 链接 |
> |------|----------|------|
> | 1 | 主对话 | /chat/26351192501800962 |
> | 2 | 抖音链接解析 | /chat/38430949903238914 |
> | ... | ... | ... |
> | 20 | AI返工率降低的规则 | /chat/38429721830424322 |
>
> 需要我爬取哪个呢？你可以回复序号，或者爬取全部到本地。
> 需要翻页请说「第2页」「下一页」。

3. **翻页**：用户说翻页时，执行 `list --page N`，展示对应页
4. 用户回复序号后，执行 `scrape <序号>`
5. 爬取完成后告知用户结果（消息条数 + 输出路径）

**注意：**
- 首页默认不加 `--page`，翻页时加 `--page N`
- 脚本输出文案：「共 272 个会话，当前显示第 N 页（x-y，共 14 页）」
- AI 回复时展示脚本输出的内容，不要说「已加载全部」，要说「当前显示前 N 条」
- 链接列用短路径（`/chat/xxx`），不带域名
- 表格必须是三列：**序号 | 会话名称 | 链接**，不要省略任何列

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

⚠️ **必须先滚动加载全部**：侧边栏会话是懒加载的，首屏只显示约 20 个，需要滚动 `[class*="flow-scrollbar"]` 容器到底部才能加载全部。`list_conversations` 函数已内置 `scroll_load_all` 自动完成。

列表以表格形式输出（序号 + 会话名称 + 链接），每页 20 条，支持 `--page N` 翻页。

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
