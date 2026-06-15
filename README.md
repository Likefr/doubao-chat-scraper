# doubao-chat-scraper

豆包（doubao.com）对话爬取工具。Hook API 获取带时间戳+图片的完整对话，导出 Markdown。

## 功能

- Headless Chrome + Playwright 自动登录（手机号+验证码）
- 自动滚动加载全部会话列表
- 支持爬取单个/全部会话
- 导出带时间戳的 Markdown（含图片链接）

## 前提

- `google-chrome-stable`
- Python 3 + `playwright`（`pip install playwright`）
- 端口 18800 未被占用

## 使用

```bash
# 1. 登录
python3 scripts/doubao_scraper.py send <手机号>   # 发验证码
python3 scripts/doubao_scraper.py verify 123456       # 填验证码

# 2. 列出会话
python3 scripts/doubao_scraper.py list                # 第1页
python3 scripts/doubao_scraper.py list --page 2      # 第2页

# 3. 爬取
python3 scripts/doubao_scraper.py scrape 3            # 爬取第3个
python3 scripts/doubao_scraper.py scrape all          # 爬取全部
```

输出：`scripts/output/<会话名>/conversation.md`

## 导出预览

**我：** `2026-06-10 09:20:00`

今天天气怎么样

---
**豆包：** `2026-06-10 09:20:01`

请问你想查询哪个城市的天气呢？

---
**我：** `2026-06-10 09:20:05`

北京

---
**豆包：** `2026-06-10 09:20:06`

北京今天晴转多云，气温 18~28°C，空气质量良好。

## 原理

1. Headless Chrome（`--headless=new --remote-debugging-port=18800`），复用已有进程
2. Playwright CDP 连接，注入 XHR hook 拦截 `/im/chain/single` 响应
3. 强制 `scrollTop=0` 触发历史消息加载（虚拟滚动）
4. 从 API 响应解析 `message_id`、`create_time`、`content_block`
5. 按 `create_time` 排序去重，输出 Markdown

## License

MIT
