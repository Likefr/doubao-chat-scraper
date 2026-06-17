#!/usr/bin/env python3
"""
豆包对话爬取工具
本机 headless Chrome + CDP，自动登录 + 获取会话列表 + hook API 爬取对话

⚠️ 核心原则：
- 永远不关闭已有页面
- 永远不创建多余新页面（只在完全没有豆包页面时才创建）
- 所有操作复用同一个已登录页面
- 每次运行连接已有 CDP 进程，不重复启动 Chrome
"""

import json, os, sys, time, re, subprocess, hashlib, threading
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 需要安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

CDP_URL = "http://127.0.0.1:18800"
CHROME_DATA_DIR = "/tmp/doubao_chrome_data"
# 导出目录：脚本所在目录的 output/（clone 就能用）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_BASE = os.path.join(os.path.dirname(SCRIPT_DIR), "output")
PHONE = None  # 由 send 命令的参数传入


def safe_name(name):
    """将会话名清洗为安全的文件/目录名，保留中文和字母数字"""
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = name.strip()
    if not name:
        name = "unnamed"
    return name


# ============ XHR Hook: 拦截 /im/chain/single 响应 ============
HOOK_JS = r"""
window._chainResponses = [];
// 拦截 XMLHttpRequest
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
// 拦截 fetch
var _fetch = window.fetch;
window.fetch = function(input, init) {
    var url = typeof input === 'string' ? input : (input && input.url ? input.url : '');
    if (url.indexOf('chain/single') !== -1) {
        return _fetch.apply(this, arguments).then(function(resp) {
            var clone = resp.clone();
            clone.text().then(function(txt) {
                window._chainResponses.push(txt);
            });
            return resp;
        });
    }
    return _fetch.apply(this, arguments);
};
'hooked';
"""


def ensure_chrome():
    """启动 headless Chrome，CDP 监听 18800（复用已有进程，不重复启动）"""
    import urllib.request

    # 先检测是否已有 Chrome 在 18800 端口运行
    try:
        urllib.request.urlopen(CDP_URL + "/json/version", timeout=2)
        print("Chrome CDP 已就绪（复用已有进程）")
        return
    except Exception:
        pass

    # 没有已有进程才启动新的
    subprocess.run(["pkill", "-f", "remote-debugging-port=18800"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

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


def find_existing_page(browser):
    """从已有页面中找豆包页面，复用（不创建新的）
    优先找已在 chat 页面的，其次找任何 doubao.com 页面"""
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "doubao.com/chat/" in page.url and page.url != "https://www.doubao.com/chat/":
                return page
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "doubao.com" in page.url:
                return page
    return None


def new_page(browser):
    """创建新 page（仅在完全没有豆包页面时的最后手段）"""
    print("⚠️ 创建新页面（没有找到已有豆包页面）")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    return ctx.new_page()


def get_or_create_page(browser):
    """获取豆包页面：优先复用已有页面，只有在没有任何豆包页面时才创建新的
    ⚠️ 核心原则：不关闭任何已有页面，不创建多余新页面"""
    page = find_existing_page(browser)
    if page:
        page.reload()
        page.wait_for_load_state("load", timeout=15000)
        page.wait_for_timeout(2000)
        url = page.url
        if "from_login=1" in url:
            return True, page
        has_login_btn = any(b.inner_text().strip() == "登录" and b.is_visible()
                           for b in page.query_selector_all("button"))
        return (not has_login_btn), page
    # 没有已有页面才创建新的
    page = new_page(browser)
    try:
        page.goto("https://www.doubao.com/chat/", timeout=30000, wait_until="load")
        page.wait_for_timeout(3000)
        url = page.url
        if "from_login=1" in url:
            return True, page
        has_login_btn = any(b.inner_text().strip() == "登录" and b.is_visible()
                           for b in page.query_selector_all("button"))
        return (not has_login_btn), page
    except Exception:
        return False, page


def check_login(browser):
    """判断是否已登录（复用已有页面）"""
    logged, page = get_or_create_page(browser)
    return logged, page


def do_login_send(browser, phone):
    """登录第一步：发验证码（复用已有页面，不创建新的）"""
    page = find_existing_page(browser)
    if not page:
        page = new_page(browser)
        page.goto("https://www.doubao.com/chat/", timeout=30000, wait_until="load")
        page.wait_for_timeout(3000)
    else:
        # 复用已有页面，不 goto（避免冲掉弹窗）
        # 检查是否已有验证码弹窗（必须是验证码输入状态，不是手机号输入状态）
        has_code_modal = page.evaluate("""() => {
            const m = document.querySelector('.semi-modal-content');
            if (!m) return false;
            const text = m.innerText || '';
            return text.includes('验证码') || text.includes('6 位');
        }""")
        if has_code_modal:
            print("验证码弹窗已存在")
            print("\n✅ 验证码已发送，等你告之")
            print("用法: python3 doubao_scraper.py verify <验证码>")
            return True

        # 没有验证码弹窗，刷新页面重新走登录流程
        page.reload()
        page.wait_for_load_state("load", timeout=15000)
        page.wait_for_timeout(2000)

    try:
        # 先确认当前是未登录状态
        if page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button')).some(b => b.innerText.trim() === 'Likefr');
        }"""):
            print("❌ 当前已是登录状态，无需重复登录")
            return True

        # 点登录按钮
        page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim() === '登录' && b.offsetParent !== null);
            if (btn) btn.click();
        }""")
        page.wait_for_selector('input[placeholder="请输入手机号"]', timeout=10000)
        page.fill('input[placeholder="请输入手机号"]', phone)

        # 勾协议 — 等协议按钮出现再点
        page.wait_for_selector('button[aria-checked="false"]', timeout=5000)
        page.evaluate("""() => {
            const cb = document.querySelector('button[aria-checked="false"]');
            if (cb) cb.click();
        }""")

        # 点下一步 — 等按钮可点击
        page.wait_for_selector('button:has-text("下一步")', state="visible", timeout=5000)
        page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button'))
                .find(b => b.innerText.trim() === '下一步' && b.offsetParent !== null);
            if (btn) btn.click();
        }""")

        # 等待验证码弹窗出现（用 wait_for_selector，不用 sleep 轮询）
        print("等待验证码弹窗...")
        try:
            page.wait_for_selector('.semi-modal-content input[type="text"]', timeout=15000)
            modal = page.evaluate("""() => {
                const m = document.querySelector('.semi-modal-content');
                return m ? m.innerText.substring(0, 120) : '';
            }""")
            print(f"弹窗内容: {modal}")
            print("\n✅ 验证码已发送，等你告之")
            print("用法: python3 doubao_scraper.py verify <验证码>")
            return True
        except Exception:
            # 超时，看看当前状态
            dialog = page.evaluate("""() => {
                const d = document.querySelector('[role="dialog"], dialog, .semi-modal-content');
                return d ? d.innerText.substring(0, 80) : 'no dialog';
            }""")
            print(f"⚠️ 验证码弹窗未出现，当前: {dialog}")
            return False
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        return False


def do_login_verify(browser, code):
    """登录第二步：填验证码（在已有验证码弹窗页面上操作）"""
    page = find_existing_page(browser)
    if not page:
        print("❌ 没有找到已有页面，请先运行 send")
        return False

    try:
        print(f"填入验证码: {code}")

        # 清空并聚焦验证码input
        page.evaluate("""() => {
            const modal = document.querySelector('.semi-modal-content');
            const input = modal?.querySelector('input[type="text"]');
            if (input) { input.focus(); input.value = ''; }
        }""")
        page.wait_for_timeout(50)

        # 用键盘逐字输入（不能用 fill，否则值会被React覆盖）
        page.keyboard.type(code, delay=80)
        page.wait_for_timeout(100)

        # 点验证码弹窗里的 semi-button-primary（确认按钮）
        # 用 expect_navigation 监听跳转，像 WebView onPageFinished 一样
        try:
            with page.expect_navigation(url="**/chat/**", timeout=15000):
                page.evaluate("""() => {
                    const modal = document.querySelector('.semi-modal-content');
                    const btn = modal?.querySelector('button.semi-button-primary');
                    if (btn) {
                        btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    }
                }""")
            page.wait_for_load_state("load", timeout=10000)
            print(f"\n✅✅✅ 登录成功！URL: {page.url}")
            return True
        except Exception as nav_err:
            # 没有跳转，可能是验证码错误
            modal_text = page.evaluate("""() => {
                const m = document.querySelector('.semi-modal-content');
                return m ? m.innerText.substring(0, 80) : '';
            }""")
            if '验证码错误' in modal_text or '验证码已过期' in modal_text:
                print(f"\n❌ {modal_text}")
                return False
            # 弹窗消失了但没导航，检查页面状态
            has_login = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button')).some(b => b.innerText.trim() === '登录' && b.offsetParent !== null);
            }""")
            if not has_login:
                print(f"\n✅✅✅ 登录成功！（弹窗消失，无登录按钮）")
                return True
            print(f"⚠️ 登录状态不确定: {modal_text}")
            return False
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False


def scroll_load_all(page, max_scrolls=50, stable_rounds=2):
    """滚动 flow-scrollbar 容器到底部，加载全部会话列表"""
    stable = 0
    for i in range(max_scrolls):
        before = page.evaluate('document.querySelectorAll(\'a[href*="/chat/"]\').length')
        page.evaluate("""() => {
            const s = document.querySelector('[class*="flow-scrollbar"]');
            if (s) s.scrollTop = s.scrollHeight;
        }""")
        page.wait_for_timeout(800)
        after = page.evaluate('document.querySelectorAll(\'a[href*="/chat/"]\').length')
        if before == after:
            stable += 1
            if stable >= stable_rounds:
                break
        else:
            stable = 0
    return page.evaluate('document.querySelectorAll(\'a[href*="/chat/"]\').length')


def list_conversations(browser):
    """获取侧边栏会话列表（滚动加载全部），返回 [{title, url}]
    ⚠️ 复用已有页面，不创建新的"""
    page = find_existing_page(browser)
    if not page:
        page = new_page(browser)
        try:
            page.goto("https://www.doubao.com/chat/", timeout=30000, wait_until="load")
            page.wait_for_timeout(3000)
        except Exception:
            return []
    try:
        # 导航到聊天首页（复用已有页面，不刷新避免丢失登录态）
        page.goto("https://www.doubao.com/chat/", timeout=30000, wait_until="load")
        page.wait_for_timeout(3000)

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
    except Exception as e:
        print(f"❌ 获取会话列表失败: {e}")
        return []


def generate_markdown(all_msgs_data, conv_url):
    """纯数据处理：从消息 dict 生成 markdown，返回 (行数, 输出路径)"""
    conv_id = conv_url.rstrip("/").split("/")[-1]
    output_dir = os.path.join(OUTPUT_BASE, conv_id)
    os.makedirs(output_dir, exist_ok=True)
    md_lines = []
    for m in sorted(all_msgs_data.values(), key=lambda x: int(x.get("create_time", 0))):
        ct = int(m.get("create_time", 0))
        ts = datetime.fromtimestamp(ct).strftime("%Y-%m-%d %H:%M:%S")
        role = "我" if m.get("user_type", 0) == 1 else "豆包"
        text, images = "", []
        for cb in m.get("content_block", []):
            bt = cb.get("block_type", 0)
            if bt == 10052:
                for att in cb.get("content", {}).get("attachment_block", {}).get("attachments", []):
                    url = (att.get("image", {}).get("image_ori", {}).get("url", "") or
                           att.get("image", {}).get("image_thumb", {}).get("url", ""))
                    if url: images.append(url)
            elif bt == 10000:
                tb = cb.get("content", {}).get("text_block", {}).get("text", "")
                if tb: text = tb; break
        if not text: text = m.get("content", "")
        parts = [text] if text else []
        for url in images: parts.append(f"![图片]({url})")
        content_str = "\n\n".join(parts)
        if content_str:
            md_lines.append(f"**{role}：** `{ts}`\n\n{content_str}\n\n---\n")
    md_path = os.path.join(output_dir, "conversation.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("".join(md_lines))
    return len(md_lines), md_path


def scrape_one_tab(context, conv_url, conv_name):
    """在独立 tab 中爬取单个会话（并发安全）
    每个调用创建独立 page + 独立 CDP session，互不干扰。
    核心策略：CDP Network 底层监听 + 鼠标滚轮向上滚动。"""
    page = context.new_page()
    try:
        t0 = time.time()

        # CDP 底层网络监听（独立 session，tab 间隔离）
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        captured = []  # 存储所有 chain/single 响应 body
        pending_ids = {}  # requestId -> url（等待 loadingFinished）

        def on_response_received(params):
            resp = params.get("response", {})
            url = resp.get("url", "")
            req_id = params.get("requestId", "")
            if "chain/single" in url and resp.get("status") == 200:
                pending_ids[req_id] = url

        def on_loading_finished(params):
            req_id = params.get("requestId", "")
            if req_id in pending_ids:
                try:
                    body = cdp.send("Network.getResponseBody", {"requestId": req_id})
                    raw = body.get("body", "")
                    if raw:
                        captured.append(raw)
                except Exception:
                    pass
                del pending_ids[req_id]

        cdp.on("Network.responseReceived", on_response_received)
        cdp.on("Network.loadingFinished", on_loading_finished)

        # 导航到目标会话（load 阶段首屏 API 已返回，不需额外等 DOM）
        page.goto(conv_url, timeout=30000, wait_until="load")
        t1 = time.time()
        page.wait_for_timeout(1000)
        t2 = time.time()

        print(f"    加载历史...", end="", flush=True)
        last_count = 0
        quiet_start = time.time()
        QUIET_SEC = 2.0

        # 鼠标滚轮不断向上 + JS scrollTop=0 + 点击「更早」按钮
        while time.time() - quiet_start < QUIET_SEC:
            page.mouse.wheel(0, -200)
            page.evaluate("""() => {
                const s = document.querySelector('[class*="v_list_scroller"]');
                if (!s) return;
                s.scrollTop = 0;
                s.dispatchEvent(new Event('scroll', {bubbles: true}));
                const btn = Array.from(document.querySelectorAll('button, [role="button"]'))
                    .find(b => /更早|查看更多|加载更多|展开/.test(b.innerText || ''));
                if (btn) btn.click();
            }""")
            page.wait_for_timeout(150)
            cur = len(captured)
            if cur > last_count:
                last_count = cur
                quiet_start = time.time()

        t3 = time.time()
        cdp.remove_listener("Network.responseReceived", on_response_received)
        cdp.remove_listener("Network.loadingFinished", on_loading_finished)
        cdp.send("Network.disable")
        all_msgs_data = {}
        for raw in captured:
            try:
                j = json.loads(raw)
                for m in j.get("downlink_body", {}).get("pull_singe_chain_downlink_body", {}).get("messages", []):
                    mid = m.get("message_id", "")
                    if mid and mid not in all_msgs_data:
                        all_msgs_data[mid] = m
            except Exception:
                pass
        t4 = time.time()
        print(f" {last_count} 个API响应，{len(all_msgs_data)} 条消息", flush=True)
        print(f"    [计时] nav={t1-t0:.1f}s init={t2-t1:.1f}s scroll={t3-t2:.1f}s parse={t4-t3:.1f}s", flush=True)

        # 生成 markdown
        # 统一用 chat_id 作为文件夹名（唯一且可靠）
        conv_id = conv_url.rstrip("/").split("/")[-1]
        output_dir = os.path.join(OUTPUT_BASE, conv_id)
        os.makedirs(output_dir, exist_ok=True)

        md_lines = []
        for m in sorted(all_msgs_data.values(), key=lambda x: int(x.get("create_time", 0))):
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
        try:
            page.close()
        except Exception:
            pass


def scrape_one(browser, conv_url, conv_name):
    """单爬兼容层：复用已有页面（不创建新 tab）"""
    page = find_existing_page(browser)
    if not page:
        print("  ❌ 没有已登录页面，无法爬取")
        return 0
    return scrape_one_tab(page.context, conv_url, conv_name)


def scrape_all_parallel(browser, convs, workers=4):
    """并发爬取所有会话（async 多 tab 并行，共享 context cookie）
    Playwright sync API 不支持多线程（greenlet 绑定线程），
    用 asyncio + async Playwright API 实现真并发。"""
    import asyncio
    from playwright.async_api import async_playwright

    async def _run():
        pw = await async_playwright().start()
        br = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = br.contexts[0]

        skip = 1  # 跳过主对话
        tasks_conv = [(i, c) for i, c in enumerate(convs) if i >= skip]
        total = len(tasks_conv)
        done = [0]
        total_msgs = [0]
        lock = asyncio.Lock()

        async def worker(idx, conv):
            page = await ctx.new_page()
            try:
                responses = []

                async def on_response(resp):
                    if "chain/single" in resp.url and resp.status == 200:
                        try:
                            body = await resp.body()
                            if body:
                                responses.append(body)
                        except Exception:
                            pass

                page.on("response", on_response)

                await page.goto(conv["url"], timeout=30000, wait_until="load")
                await page.wait_for_timeout(1000)

                quiet_start = time.time()
                last_count = 0
                while time.time() - quiet_start < 2.0:
                    await page.mouse.wheel(0, -200)
                    await page.evaluate("""() => {
                        const s = document.querySelector('[class*="v_list_scroller"]');
                        if (!s) return;
                        s.scrollTop = 0;
                        s.dispatchEvent(new Event('scroll', {bubbles: true}));
                        const btn = Array.from(document.querySelectorAll('button, [role="button"]'))
                            .find(b => /更早|查看更多|加载更多|展开/.test(b.innerText || ''));
                        if (btn) btn.click();
                    }""")
                    await page.wait_for_timeout(150)
                    cur = len(responses)
                    if cur > last_count:
                        last_count = cur
                        quiet_start = time.time()

                page.remove_listener("response", on_response)

                # 解析
                all_msgs_data = {}
                for raw in responses:
                    try:
                        j = json.loads(raw)
                        for m in j.get("downlink_body", {}).get("pull_singe_chain_downlink_body", {}).get("messages", []):
                            mid = m.get("message_id", "")
                            if mid and mid not in all_msgs_data:
                                all_msgs_data[mid] = m
                    except Exception:
                        pass

                count = generate_markdown(all_msgs_data, conv["url"])[0]
                async with lock:
                    done[0] += 1
                    total_msgs[0] += count
                    print(f"  [{done[0]}/{total}] ✅ {conv['title']}: {count} 条消息")
                return count
            except Exception as e:
                print(f"  ❌ {conv['title']}: {e}")
                return 0
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

        t0 = time.time()
        print(f"\n🚀 并发爬取开始: {total} 个会话, {workers} 并发")
        await asyncio.gather(*[worker(idx, conv) for idx, conv in tasks_conv])
        elapsed = time.time() - t0
        print(f"\n🎉 并发({workers})爬取完成，共 {total_msgs[0]} 条消息, 耗时 {elapsed:.1f}s → {OUTPUT_BASE}/")
        await pw.stop()
        return total_msgs[0]

    import nest_asyncio
    nest_asyncio.apply()
    return asyncio.get_event_loop().run_until_complete(_run())


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    ensure_chrome()

    # 单一 Playwright 实例 + 单一 CDP 连接，全程复用 browser 对象
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=15000)

        if cmd == "send":
            phone = sys.argv[2] if len(sys.argv) > 2 else ""
            if not phone:
                print("用法: python3 doubao_scraper.py send <手机号>")
            else:
                do_login_send(browser, phone)

        elif cmd == "verify":
            code = sys.argv[2] if len(sys.argv) > 2 else ""
            if not code:
                print("用法: python3 doubao_scraper.py verify <验证码>")
            else:
                do_login_verify(browser, code)

        elif cmd == "list":
            logged, _ = check_login(browser)
            if not logged:
                print("未登录，请先执行: python3 doubao_scraper.py send")
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
            logged, _ = check_login(browser)
            if not logged:
                print("未登录，请先执行: python3 doubao_scraper.py send")
                sys.exit(1)

            arg = sys.argv[2] if len(sys.argv) > 2 else "all"

            # scrape_by_id: 不走 list，直接用 chat_id（快）
            if arg.startswith("http") or arg.isdigit() and len(arg) > 15:
                # chat_id 数字或完整 URL
                if arg.isdigit():
                    conv_url = f"https://www.doubao.com/chat/{arg}"
                else:
                    conv_url = arg
                conv_id = conv_url.rstrip("/").split("/")[-1]
                print(f"爬取: {conv_id}...")
                count = scrape_one(browser, conv_url, conv_id)
                print(f"✅ {count} 条消息 → {OUTPUT_BASE}/{conv_id}/conversation.md")
                return

            # scrape all / scrape <序号> 需要先 list
            convs = list_conversations(browser)
            if not convs:
                print("❌ 没有可爬取的会话")
                sys.exit(1)

            # 范围爬取: scrape 2-20
            if '-' in arg and not arg.startswith('http'):
                parts = arg.split('-')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    start_idx = int(parts[0]) - 1
                    end_idx = int(parts[1])
                    slice_convs = convs[start_idx:end_idx]
                    if not slice_convs:
                        print(f"❌ 范围 {arg} 无有效会话")
                    else:
                        workers = 4
                        args_list = sys.argv[2:]
                        for j in range(len(args_list)):
                            if args_list[j] == "--parallel" and j + 1 < len(args_list):
                                workers = int(args_list[j + 1])
                                break
                        print(f"爬取范围: 序号 {parts[0]}-{parts[1]}（共 {len(slice_convs)} 个会话，{workers} 并发）")
                        scrape_all_parallel(browser, slice_convs, workers=workers)
                    return

            if arg.lower() == "all":
                workers = 4  # 默认4并发
                args = sys.argv[2:]
                for j in range(len(args)):
                    if args[j] == "--parallel" and j + 1 < len(args):
                        workers = int(args[j + 1])
                        break
                scrape_all_parallel(browser, convs, workers=workers)
            else:
                idx = int(arg) - 1
                if 0 <= idx < len(convs):
                    c = convs[idx]
                    print(f"爬取: {c['title']}...")
                    count = scrape_one(browser, c["url"], c["title"])
                    print(f"✅ {count} 条消息 → {OUTPUT_BASE}/{c['url'].rstrip('/').split('/')[-1]}/conversation.md")
                else:
                    print(f"❌ 序号超出范围 (1-{len(convs)})")

        else:
            print("用法:")
            print("  python3 doubao_scraper.py send           # 登录：发验证码")
            print("  python3 doubao_scraper.py verify <验证码> # 登录：填验证码完成")
            print("  python3 doubao_scraper.py list           # 列出所有会话")
            print("  python3 doubao_scraper.py scrape <序号> # 爬取指定会话")
            print("  python3 doubao_scraper.py scrape all     # 爬取全部会话")
            print("  python3 doubao_scraper.py scrape all --parallel 4  # 并发爬取（推荐）")


if __name__ == "__main__":
    main()
