import json
from pathlib import Path

from playwright.sync_api import sync_playwright


SIGNUP_URLS = {
    "facebook": "https://www.facebook.com/r.php",
    "instagram": "https://www.instagram.com/accounts/emailsignup/",
    "tiktok": "https://www.tiktok.com/signup/phone-or-email/email",
    "linkedin": "https://www.linkedin.com/signup",
}


class EnvironmentMismatch(RuntimeError):
    def __init__(self, message, actual=None):
        super().__init__(message)
        self.actual = actual or {}


def validate_environment(actual, expected):
    mismatches = []
    if str(actual.get("ip") or "").strip() != str(expected.get("ip") or "").strip():
        mismatches.append("IP")
    if str(actual.get("country") or "").strip().upper() != str(expected.get("country") or "").strip().upper():
        mismatches.append("国家")
    if str(actual.get("timezone") or "").strip() != str(expected.get("timezone") or "").strip():
        mismatches.append("时区")
    if mismatches:
        raise EnvironmentMismatch(
            "%s不匹配，已停止注册且未打开平台注册页" % "、".join(mismatches), actual,
        )


def _endpoint(open_result):
    data = open_result.get("data", open_result) if isinstance(open_result, dict) else {}
    endpoint = data.get("http") or data.get("ws") or ""
    if not endpoint:
        raise RuntimeError("比特浏览器未返回 Playwright/CDP 调试地址")
    return endpoint


def _fill_first(page, selectors, value):
    if not value:
        return False
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=1500)
            locator.fill(value, timeout=2000)
            return True
        except Exception:
            continue
    return False


def prepare_registration(client, task, screenshot_path):
    platform = str(task.get("platform") or "").lower()
    if platform not in SIGNUP_URLS:
        raise ValueError("暂不支持该平台注册：%s" % platform)
    result = client.open_browser(task["environment_id"])
    playwright = sync_playwright().start()
    check_page = None
    try:
        browser = playwright.chromium.connect_over_cdp(_endpoint(result))
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        check_page = context.new_page()
        check_page.goto("https://ipinfo.io/json", wait_until="domcontentloaded", timeout=30000)
        info = json.loads(check_page.locator("body").inner_text(timeout=5000))
        actual = {
            "ip": str(info.get("ip") or "").strip(),
            "country": str(info.get("country") or "").strip().upper(),
            "timezone": str(check_page.evaluate(
                "Intl.DateTimeFormat().resolvedOptions().timeZone"
            ) or "").strip(),
        }
        validate_environment(actual, {
            "ip": task.get("expected_ip"),
            "country": task.get("expected_country_code"),
            "timezone": task.get("expected_timezone"),
        })
        check_page.close()
        check_page = None
        page = context.new_page()
        page.goto(SIGNUP_URLS[platform], wait_until="domcontentloaded", timeout=45000)
        _fill_first(page, (
            "input[type=email]", "input[name=email]", "input[name=reg_email__]",
            "input[name=emailOrPhone]", "input[id=email-or-phone]", "input[autocomplete=email]",
        ), task.get("email"))
        _fill_first(page, (
            "input[name=name]", "input[name=fullname]", "input[name=firstName]",
            "input[name=fullName]", "input[name=firstname]", "input[autocomplete=name]",
        ), task.get("display_name"))
        _fill_first(page, (
            "input[name=username]", "input[autocomplete=username]",
        ), task.get("desired_username"))
        target = Path(screenshot_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=False)
        return {**actual, "signup_url": SIGNUP_URLS[platform], "screenshot": str(target)}
    finally:
        if check_page:
            check_page.close()
        playwright.stop()


def capture_current_page(client, environment_id, screenshot_path):
    result = client.open_browser(environment_id)
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(_endpoint(result))
        if not browser.contexts:
            raise RuntimeError("比特环境中没有可用浏览器上下文")
        pages = browser.contexts[0].pages
        if not pages:
            raise RuntimeError("比特环境中没有可截图页面")
        target = Path(screenshot_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        pages[-1].screenshot(path=str(target), full_page=False)
        return target
    finally:
        playwright.stop()
