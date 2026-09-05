import asyncio
import base64
import ctypes
import json
import os
import shutil
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


VENDOR_ROOT = Path(__file__).resolve().parent / "vendor" / "douyin"
REQUIRED_COOKIES = {"ttwid", "odin_tt", "passport_csrf_token"}
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt"}


def _enable_vendor():
    value = str(VENDOR_ROOT)
    if value not in sys.path:
        sys.path.insert(0, value)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi(data, protect):
    if os.name != "nt":
        raise RuntimeError("抖音登录信息只能在 Windows 上保存")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    description = wintypes.LPWSTR()
    crypt32 = ctypes.windll.crypt32
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(source), "LightLink Douyin Cookies", None, None, None, 0,
            ctypes.byref(output),
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source), ctypes.byref(description), None, None, None, 0,
            ctypes.byref(output),
        )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        if description:
            ctypes.windll.kernel32.LocalFree(description)
        del source_buffer


def save_cookies(path, cookies):
    payload = json.dumps(cookies, ensure_ascii=False).encode("utf-8")
    encrypted = base64.b64encode(_dpapi(payload, True)).decode("ascii")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"douyin_cookies_dpapi": encrypted}), encoding="utf-8")


def load_cookies(path):
    target = Path(path)
    if not target.exists():
        return {}
    stored = json.loads(target.read_text(encoding="utf-8"))
    encrypted = base64.b64decode(stored["douyin_cookies_dpapi"])
    return json.loads(_dpapi(encrypted, False).decode("utf-8"))


def has_login(path):
    try:
        cookies = load_cookies(path)
    except Exception:
        return False
    return REQUIRED_COOKIES.issubset(cookies) and bool(LOGIN_COOKIES.intersection(cookies))


def self_test():
    _enable_vendor()
    from auth import CookieManager  # noqa: F401
    from config import ConfigLoader  # noqa: F401
    from core import DouyinAPIClient, DownloaderFactory, URLParser  # noqa: F401
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as directory:
        store = Path(directory) / "secrets.json"
        expected = {
            "ttwid": "test", "odin_tt": "test", "passport_csrf_token": "test",
            "sessionid": "test",
        }
        save_cookies(store, expected)
        if load_cookies(store) != expected or "ttwid" in store.read_text(encoding="utf-8"):
            raise RuntimeError("DPAPI 自检失败")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        browser.close()
    return 0


def capture_login(path, proxy="", timeout_seconds=600, status_callback=None):
    from playwright.sync_api import sync_playwright

    notify = status_callback or (lambda _message: None)
    notify("正在打开 Edge，请在新窗口登录抖音")
    with sync_playwright() as playwright:
        options = {"channel": "msedge", "headless": False}
        if proxy:
            options["proxy"] = {"server": proxy}
        browser = playwright.chromium.launch(**options)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=120000)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                cookies = {
                    item["name"]: item["value"]
                    for item in context.cookies()
                    if item.get("domain", "").endswith("douyin.com")
                }
                if REQUIRED_COOKIES.issubset(cookies) and LOGIN_COOKIES.intersection(cookies):
                    save_cookies(path, cookies)
                    notify("抖音登录信息已加密保存")
                    return len(cookies)
                page.wait_for_timeout(2000)
            raise TimeoutError("等待抖音登录超时，请重新点击“登录/更新抖音登录”")
        finally:
            browser.close()


async def _download(url, output_dir, cookies, proxy):
    _enable_vendor()
    from auth import CookieManager
    from config import ConfigLoader
    from control import QueueManager, RateLimiter, RetryHandler
    from core import DouyinAPIClient, DownloaderFactory, URLParser
    from storage import FileManager
    from utils.validators import is_short_url, normalize_short_url

    config = ConfigLoader(None)
    config.update(
        path=str(output_dir), proxy=proxy or "", database=False, thread=1,
        rate_limit=1, retry_times=3, folderstyle=False,
        filename_template="{id}", cover=False, music=False, avatar=False, json=False,
        transcript={"enabled": False}, comments={"enabled": False},
        browser_fallback={"enabled": False},
    )
    cookie_manager = CookieManager()
    cookie_manager.cookies = cookies
    if not cookie_manager.validate_cookies():
        raise RuntimeError("抖音登录信息不完整，请在工具中重新登录抖音")
    async with DouyinAPIClient(cookies, proxy=proxy or "") as api_client:
        if is_short_url(url):
            url = await api_client.resolve_short_url(normalize_short_url(url))
        parsed = URLParser.parse(url) if url else None
        if not parsed:
            raise RuntimeError("Douyin Downloader 无法解析该抖音链接")
        downloader = DownloaderFactory.create(
            parsed["type"], config, api_client, FileManager(str(output_dir)),
            cookie_manager, None, RateLimiter(max_per_second=1),
            RetryHandler(max_retries=3), QueueManager(max_workers=1),
        )
        if not downloader:
            raise RuntimeError("Douyin Downloader 不支持该链接类型")
        result = await downloader.download(parsed)
    if not result or result.success != 1:
        raise RuntimeError("Douyin Downloader 未能下载该视频，请更新抖音登录后重试")


def download_video(url, target, cookie_store, proxy=""):
    cookies = load_cookies(cookie_store)
    if not cookies:
        raise RuntimeError("尚未登录抖音，请先在工具中点击“登录/更新抖音登录”")
    output_dir = Path(target).parent / "douyin-download"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    asyncio.run(_download(url, output_dir, cookies, proxy))
    videos = sorted(output_dir.rglob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
    if len(videos) != 1:
        raise RuntimeError(f"Douyin Downloader 返回了 {len(videos)} 个视频，无法确定目标文件")
    shutil.move(str(videos[0]), str(target))
    return Path(target)
