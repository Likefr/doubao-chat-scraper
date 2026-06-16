#!/usr/bin/env python3
"""
豆包对话爬取工具
本机 headless Chrome + CDP，自动登录 + 获取会话列表 + hook API 爬取对话
"""

import json, os, sys, time, re, subprocess
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 需要安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

CDP_URL = "http://127.0.0.1:18800"
CHROME_DATA_DIR = "/tmp/doubao_chrome_data"
OUTPUT_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# ============ XHR Hook: 拦截 /im/chain/single 响应 ============
HOOK_JS = r"""
window._chainResponses = [];
var _open = XMLHttpRequest.prototype.open;
var _send = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function(m, u) {
    this._url = u; this._method = m;
    return _open.apply(this, arguments);
};
XMLHttpRequest.prototype.send = function(b) {
    var self = this;
    if (this._url && this._url.indexOf('chain/single') !== -1) {
        var _orig = this.onreadystatechange;
        this.onreadystatechange = function() {
            if (self.readyState === 4) {
                window._chainResponses.push(self.responseText);
            }
            if (_orig) _orig.apply(this, arguments);
        };
    }
    return _send.apply(this, arguments);
};
'hooked';
"""


def ensure_chrome():
    """启动 headless Chrome，CDP 监听 18800"""
    import urllib.request
    try:
        urllib.request.urlopen(CDP_URL + "/json/version", timeout=3)
        print("Chrome CDP 已就绪")
        return
    except Exception:
        pass

    print("启动 headless Chrome...")
    subprocess.Popen([
        "google-chrome-stable",
        "--headless=new", "--no-sandbox", "--disable-gpu",
        "--remote-debugging-port=18800",
        "--user-data-dir=" + CHROME_DATA_DIR,
        "--disable-extensions", "--disable-background-networking"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(15):
        time.sleep(1)
        try:
            urllib.request.urlopen(CDP_URL + "/json/version", timeout=2)
            print("Chrome CDP 已就绪")
            return
        except Exception:
            continue
    print("❌ Chrome 启动失败，请确认已安装 google-chrome-stable")
    sys.exit(1)


def new_page(browser):
    """从 browser 创建新 page，自动选 context"""
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    return ctx.new_page()


def check_login(browser):
    """判断是否已登录"""
    page = new_page(browser)
    try:
        page.goto("https://www.doubao.com/chat/", timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(4)
        url = page.url
        if "from_login=1" in url:
            return True
        for btn in page.query_selector_all("button"):
            if btn.inner_text().strip() == "登录" and btn.is_visible():
                return False
        return True
    finally:
        page.close()


def do_login(browser):
    """自动登录：需要用户提供手机号和验证码"""
    page = new_page(browser)

    try:
        print("\n需要登录豆包，请提供信息：")

        phone = input("手机号: ").strip()
        if not phone:
            print("❌ 手机号不能为空")
            return False

        # 点击登录按钮
        for btn in page.query_selector_all("button"):
            if btn.inner_text().strip() == "登录" and btn.is_visible():
                btn.click()
                break
        time.sleep(2)

        # 输入手机号
        phone_input = page.query_selector('input[placeholder="请输入手机号"]')
        if not phone_input:
            print("❌ 找不到手机号输入框")
            return False
        phone_input.fill(phone)
        time.sleep(0.5)

        # 勾选协议 checkbox
        checkbox = page.query_selector('button[aria-checked="false"][class*="cursor-pointer"]')
        if checkbox:
            checkbox.click()
            time.sleep(0.3)
        else:
            print("⚠️ 找不到协议 checkbox，尝试继续")

        # 点击下一步（发送验证码）
        for btn in page.query_selector_all("button"):
            if btn.inner_text().strip() == "下一步" and btn.is_visible():
                btn.click()
                print("验证码已发送")
                break
        else:
            print("❌ 找不到'下一步'按钮")
            return False

        time.sleep(2)

        # 输入验证码
        code = input("验证码: ").strip()
        if not code:
            print("❌ 验证码不能为空")
            return False

        # 找验证码输入框（非 file 的 input）
        inputs = page.query_selector_all("input")
        code_input = None
        for inp in inputs:
            if inp.get_attribute("type") != "file":
                code_input = inp
        if code_input:
            code_input.fill(code)
        else:
            print("❌ 找不到验证码输入框")
            return False
        time.sleep(0.5)

        # 点击登录
        for btn in page.query_selector_all("button"):
            text = btn.inner_text().strip()
            if ("登录" in text or "确认" in text) and btn.is_visible() and text != "登录":
                btn.click()
                break
        time.sleep(5)

        if "from_login=1" in page.url:
            print("✅ 登录成功")
            return True
        print(f"⚠️ 当前 URL: {page.url}，登录状态不确定")
        return True
    finally:
        page.close()


def scroll_load_all(page, max_scrolls=50, stable_rounds=2):
    """滚动 flow-scrollbar 容器到底部，加载全部会话列表"""
    stable = 0
    for i in range(max_scrolls):
        before = page.evaluate('document.querySelectorAll(\'a[href*="/chat/"]\').length')
        page.evaluate("""() => {
            const s = document.querySelector('[class*="flow-scrollbar"]');
            if (s) s.scrollTop = s.scrollHeight;
        }""")
        time.sleep(1.5)
        after = page.evaluate('document.querySelectorAll(\'a[href*="/chat/"]\').length')
        if before == after:
            stable += 1
            if stable >= stable_rounds:
                break
        else:
            stable = 0
    return page.evaluate('document.querySelectorAll(\'a[href*="/chat/"]\').length')


def list_conversations(browser):
    """获取侧边栏会话列表（滚动加载全部），返回 [{title, url}]"""
    page = new_page(browser)
    try:
        page.goto("https://www.doubao.com/chat/", timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(5)

        total = scroll_load_all(page)
        print(f"共 {total} 个会话")

        links = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href*="/chat/"]'))
                .filter(a => !a.href.includes('/chat/create-image') && !a.href.includes('/chat/drive'))
                .map(a => ({ title: a.innerText.trim(), url: a.href }));
        }""")

        if not links:
            print("⚠️ 未获取到会话列表")
        return links
    finally:
        page.close()


def scrape_one(browser, conv_url, conv_name):
    """hook API 爬取单个会话"""
    page = new_page(browser)
    try:
        page.add_init_script(HOOK_JS)
        page.goto(conv_url, timeout=30000)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(6)

        # 强制 scrollTop=0 加载全部历史
        page.evaluate("""() => {
            window._done = false; window._lastSh = 0; window._stableCount = 0;
            window._scrollIv = setInterval(function() {
                var s = document.querySelector('[class*="v_list_scroller"]');
                if (!s) return;
                s.scrollTop = 0;
                if (s.scrollHeight === window._lastSh) {
                    window._stableCount++;
                    if (window._stableCount > 20) {
                        clearInterval(window._scrollIv);
                        window._done = true;
                    }
                } else {
                    window._stableCount = 0;
                    window._lastSh = s.scrollHeight;
                }
            }, 150);
        }""")

        for _ in range(120):
            if page.evaluate("window._done"):
                break
            time.sleep(1)
        time.sleep(3)

        # 解析消息
        all_msgs = {}
        resp_count = page.evaluate("window._chainResponses.length")
        for i in range(resp_count):
            raw = page.evaluate(f"window._chainResponses[{i}]")
            try:
                j = json.loads(raw)
                for m in j.get("downlink_body", {}).get("pull_singe_chain_downlink_body", {}).get("messages", []):
                    mid = m.get("message_id", "")
                    if mid and mid not in all_msgs:
                        all_msgs[mid] = m
            except Exception:
                pass

        # 生成 markdown
        output_dir = os.path.join(OUTPUT_BASE, conv_name)
        os.makedirs(output_dir, exist_ok=True)

        md_lines = []
        for m in sorted(all_msgs.values(), key=lambda x: int(x.get("create_time", 0))):
            ct = int(m.get("create_time", 0))
            ts = datetime.fromtimestamp(ct).strftime("%Y-%m-%d %H:%M:%S")
            role = "我" if m.get("user_type", 0) == 1 else "豆包"
            text = ""
            images = []
            for cb in m.get("content_block", []):
                bt = cb.get("block_type", 0)
                if bt == 10052:
                    for att in cb.get("content", {}).get("attachment_block", {}).get("attachments", []):
                        url = (att.get("image", {}).get("image_ori", {}).get("url", "") or
                               att.get("image", {}).get("image_thumb", {}).get("url", ""))
                        if url:
                            images.append(url)
                elif bt == 10000:
                    tb = cb.get("content", {}).get("text_block", {}).get("text", "")
                    if tb:
                        text = tb
                        break
            if not text:
                text = m.get("content", "")
            parts = [text] if text else []
            for url in images:
                parts.append(f"![图片]({url})")
            content_str = "\n\n".join(parts)
            if content_str:
                md_lines.append(f"**{role}：** `{ts}`\n\n{content_str}\n\n---\n")

        md_path = os.path.join(output_dir, "conversation.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("".join(md_lines))

        return len(md_lines)
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return 0
    finally:
        page.close()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    ensure_chrome()

    # 单一 Playwright 实例 + 单一 CDP 连接，全程复用 browser 对象
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)

        if cmd == "login":
            do_login(browser)

        elif cmd == "list":
            if not check_login(browser):
                print("未登录，请先执行: python3 doubao_scraper.py login")
                sys.exit(1)
            convs = list_conversations(browser)
            page_num = 1
            args = sys.argv[2:]
            for i, a in enumerate(args):
                if a == '--page' and i + 1 < len(args):
                    page_num = int(args[i + 1])
            page_size = 20
            start = (page_num - 1) * page_size
            end = start + page_size
            preview = convs[start:end]
            total_pages = (len(convs) + page_size - 1) // page_size
            print(f"\n共 {len(convs)} 个会话，当前显示第 {page_num} 页（{start+1}-{min(end, len(convs))}，共 {total_pages} 页）：\n")
            print(f"{'序号':<6} {'会话名称':<25} {'链接'}")
            print("─" * 70)
            for i, c in enumerate(preview):
                short_url = c['url'].replace('https://www.doubao.com', '').replace('http://www.doubao.com', '')
                title = c['title'][:22] + '..' if len(c['title']) > 22 else c['title']
                print(f"{start+i+1:<6} {title:<25} {short_url}")
            if convs:
                print(f"\n翻页: python3 doubao_scraper.py list --page <1-{total_pages}>")
                print(f"爬取单个: python3 doubao_scraper.py scrape <序号>")
                print(f"爬取全部: python3 doubao_scraper.py scrape all")
            return

        elif cmd == "scrape":
            if not check_login(browser):
                print("未登录，请先执行: python3 doubao_scraper.py login")
                sys.exit(1)

            convs = list_conversations(browser)
            if not convs:
                print("❌ 没有可爬取的会话")
                sys.exit(1)

            arg = sys.argv[2] if len(sys.argv) > 2 else "all"

            if arg.lower() == "all":
                total = 0
                for i, c in enumerate(convs):
                    print(f"\n[{i+1}/{len(convs)}] 爬取: {c['title']}...")
                    count = scrape_one(browser, c["url"], c["title"])
                    total += count
                    print(f"  ✅ {count} 条消息")
                print(f"\n🎉 全部完成，共 {total} 条消息 → {OUTPUT_BASE}/")
            else:
                idx = int(arg) - 1
                if 0 <= idx < len(convs):
                    c = convs[idx]
                    print(f"爬取: {c['title']}...")
                    count = scrape_one(browser, c["url"], c["title"])
                    print(f"✅ {count} 条消息 → {OUTPUT_BASE}/{c['title']}/conversation.md")
                else:
                    print(f"❌ 序号超出范围 (1-{len(convs)})")

        else:
            print("用法:")
            print("  python3 doubao_scraper.py login        # 登录豆包（手机号+验证码）")
            print("  python3 doubao_scraper.py list          # 列出所有会话")
            print("  python3 doubao_scraper.py scrape <序号> # 爬取指定会话")
            print("  python3 doubao_scraper.py scrape all     # 爬取全部会话")


if __name__ == "__main__":
    main()
