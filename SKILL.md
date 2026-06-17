---
name: "doubao-chat-scraper"
description: "爬取豆包(doubao.com)对话记录，CDP底层监听+鼠标滚轮滚动，获取带时间戳+图片的完整对话，导出markdown"
---

# 豆包对话爬取

## 命令

```bash
SCRIPT="skills/doubao-chat-scraper/scripts/doubao_scraper.py"
$SCRIPT send <手机号>         # 发验证码 → 问用户要验证码 → verify
$SCRIPT verify <6位验证码>      # 填验证码（expect_navigation 等跳转）
$SCRIPT list                   # 滚动加载全部会话，分页输出
$SCRIPT list --page N         # 第 N 页
$SCRIPT scrape <chat_id>       # 爬单个（推荐，跳过list，最快）
$SCRIPT scrape <序号>          # 爬单个（需先list）
$SCRIPT scrape <起始>-<结束>   # 爬范围，如 scrape 2-20（默认4并发）
$SCRIPT scrape all            # 爬全部（默认4并发，--parallel N 可调）
```

## 导出

- **路径**：`<clone目录>/output/<chat_id>/conversation.md`（跟随项目目录，clone 就能用）
- **文件夹命名**：统一用 chat_id（如 `38426519926531074`），唯一可靠
- **文件**：`conversation.md`，格式：`**角色：** \`时间\` \n\n内容\n\n---\n`

## 流程

1. **问用户手机号** → `send <手机号>` → 等验证码 → `verify <验证码>`
2. **list** → **必须**用 markdown 表格展示（`| 序号 | 会话名称 | 链接 |`），不要省略链接列，不要只说「如上」
3. **scrape <chat_id>** → 直接爬，跳过 list（最快，~8-11s）
4. 告知结果（消息条数 + 输出路径）

## 核心原理

**CDP 底层网络监听 + 鼠标滚轮向上滚动**（不依赖页面 JS hook，不被 SPA 路由影响）

1. **CDP `Network.enable` + `setCacheDisabled`**：底层监听所有网络请求
2. **`Network.responseReceived`**：识别 `chain/single` API 响应
3. **`Network.loadingFinished`**：确保 body 完全加载后调用 `getResponseBody` 拿数据
4. **`page.mouse.wheel(0, -200)`** + JS `scrollTop=0` + 点击「更早」按钮：三重触发向上滚动
5. **2 秒 quiet 判定**：收到新响应立即重置计时，连续 2 秒无新响应 = 完成
6. **Python 端一次性解析**：所有响应 body 汇总后统一 JSON 解析去重

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

## 性能参考

| 会话 | 消息数 | 耗时 |
|------|:------:|:----:|
| 关于她 | 153 | ~8s |
| 解决公众号与开放平台openid不一致问题 | 68 | ~8s |
| 沟通方式建议 | 66 | ~8s |
| Nginx html目录配置 | 31 | ~11s |

- 小对话：nav~1.5s + init~1s + scroll~5-6s = **~8s**
- 大对话（700+条）：scroll 阶段会成比例增长
- **连续 scrape 稳定**：CDP 监听不依赖页面 JS，无 hook 丢失问题
