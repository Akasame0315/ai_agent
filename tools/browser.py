"""
瀏覽器控制工具
路徑：tools/browser.py

使用 Playwright 控制 Chromium 瀏覽器。
支援：開啟網頁、點擊、填表單、抓內容、截圖。

注意：瀏覽器實例在整個程式生命週期內共用，
第一次呼叫時啟動，之後保持開著。
"""
import asyncio
import os
import datetime

FILES_DIR = "agent_files"

# ── 全域瀏覽器實例（lazy init）────────────────────────────────────────
_playwright = None
_browser    = None
_page       = None


def _run_async(coro):
    """在同步環境裡執行 async 函式"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 已有 event loop（Telegram Bot 環境）
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _get_page():
    """取得或初始化瀏覽器 page"""
    global _playwright, _browser, _page

    if _page is None or _page.is_closed():
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()
        _browser    = await _playwright.chromium.launch(
            headless=False,        # False = 看得到瀏覽器視窗，方便觀察
            args=["--start-maximized"]
        )
        context = await _browser.new_context(
            viewport=None,         # 配合 maximized
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        _page = await context.new_page()
        print("[Browser] 瀏覽器已啟動")

    return _page


async def _close_browser():
    global _playwright, _browser, _page
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    _page = None


# ══════════════════════════════════════════════════════════════════════
# 工具實作
# ══════════════════════════════════════════════════════════════════════

async def _navigate(url: str) -> str:
    page = await _get_page()
    if not url.startswith("http"):
        url = "https://" + url
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    title = await page.title()
    return f"✅ 已開啟：{title}\n   網址：{page.url}"

async def _get_content(max_length: int = 3000) -> str:
    page   = await _get_page()
    # 取得頁面純文字（去掉 script/style）
    content = await page.evaluate("""() => {
        const scripts = document.querySelectorAll('script, style, nav, footer, header');
        scripts.forEach(el => el.remove());
        return document.body ? document.body.innerText : '';
    }""")
    content = "\n".join(
        line.strip() for line in content.split("\n")
        if line.strip()
    )
    if len(content) > max_length:
        content = content[:max_length] + "\n...（內容過長，已截斷）"
    return content

async def _click_element(selector: str) -> str:
    page = await _get_page()
    try:
        await page.click(selector, timeout=10000)
        await page.wait_for_load_state("domcontentloaded")
        return f"✅ 已點擊：{selector}"
    except Exception as e:
        return f"❌ 點擊失敗：{e}"

async def _fill_input(selector: str, value: str) -> str:
    page = await _get_page()
    try:
        await page.fill(selector, value)
        return f"✅ 已填入：{selector} = {value}"
    except Exception as e:
        return f"❌ 填寫失敗：{e}"

async def _screenshot(filename: str = "") -> str:
    page = await _get_page()
    os.makedirs(FILES_DIR, exist_ok=True)
    if not filename:
        filename = f"browser_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(FILES_DIR, filename)
    await page.screenshot(path=path, full_page=True)
    return f"✅ 網頁截圖已儲存：{filename}"

async def _search_web(query: str) -> str:
    """用瀏覽器真實搜尋，取得比 DuckDuckGo API 更完整的結果"""
    page = await _get_page()
    url  = f"https://duckduckgo.com/?q={query}&ia=web"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # 抓搜尋結果
    results = await page.evaluate("""() => {
        const items = document.querySelectorAll('[data-result="result"]');
        const out   = [];
        items.forEach((item, i) => {
            if (i >= 5) return;
            const title   = item.querySelector('h2')?.innerText || '';
            const snippet = item.querySelector('[data-result="snippet"]')?.innerText || '';
            const link    = item.querySelector('a')?.href || '';
            if (title) out.push(`• ${title}\\n  ${snippet}\\n  ${link}`);
        });
        return out.join('\\n\\n');
    }""")

    return f"🔍 搜尋「{query}」結果：\n\n{results}" if results else "找不到搜尋結果"


# ── 同步包裝（供 Tool handler 呼叫）──────────────────────────────────

def browser_open(url: str) -> str:
    """開啟指定網址"""
    return _run_async(_navigate(url))

def browser_read() -> str:
    """讀取目前網頁的文字內容"""
    return _run_async(_get_content())

def browser_click(selector: str) -> str:
    """
    點擊網頁元素。
    selector 可以是 CSS selector（如 button.submit）
    或文字（如 text=登入）
    """
    return _run_async(_click_element(selector))

def browser_fill(selector: str, value: str) -> str:
    """在輸入框填入文字，selector 是輸入框的 CSS selector"""
    return _run_async(_fill_input(selector, value))

def browser_screenshot(filename: str = "") -> str:
    """截取目前網頁完整截圖，儲存到 agent_files"""
    return _run_async(_screenshot(filename))

def browser_search(query: str) -> str:
    """用瀏覽器搜尋，結果比純 API 搜尋更完整"""
    return _run_async(_search_web(query))

def browser_close() -> str:
    """關閉瀏覽器"""
    _run_async(_close_browser())
    return "✅ 瀏覽器已關閉"

def browser_current_url() -> str:
    """取得目前網頁的網址和標題"""
    async def _get_info():
        page  = await _get_page()
        title = await page.title()
        return f"📄 標題：{title}\n🔗 網址：{page.url}"
    return _run_async(_get_info())
