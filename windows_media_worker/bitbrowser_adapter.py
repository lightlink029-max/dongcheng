from urllib.parse import urlparse

import requests


class BitBrowserClient:
    def __init__(self, base_url, token="", timeout=30):
        self.base_url = str(base_url or "").strip().rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in (
            "127.0.0.1", "localhost", "::1",
        ):
            raise ValueError("比特 Local API 地址必须是本机 http(s) 地址")
        self.token = str(token or "").strip()
        self.timeout = timeout

    def _post(self, path, payload=None):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["x-api-key"] = self.token
        response = requests.post(
            self.base_url + path, json=payload or {}, headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError("比特 Local API 返回的不是 JSON") from exc
        if isinstance(result, dict) and result.get("success") is False:
            raise RuntimeError(result.get("msg") or "比特 Local API 调用失败")
        return result

    def health(self):
        return self._post("/health")

    def list_browsers(self):
        browsers = []
        page = 0
        while True:
            result = self._post("/browser/list", {"page": page, "pageSize": 100})
            data = result.get("data", result) if isinstance(result, dict) else result
            if isinstance(data, list):
                batch = data
                total = len(data)
            elif isinstance(data, dict):
                batch = data.get("list") or data.get("items") or data.get("rows") or []
                total = data.get("totalNum", data.get("total", len(batch)))
            else:
                batch, total = [], 0
            browsers.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100 or len(browsers) >= int(total or 0):
                return browsers
            page += 1

    def open_browser(self, browser_id):
        if not str(browser_id or "").strip():
            raise ValueError("请选择要启动的比特环境")
        return self._post("/browser/open", {
            "id": str(browser_id), "loadExtensions": True, "extractIp": True,
        })

    def close_browser(self, browser_id):
        if not str(browser_id or "").strip():
            raise ValueError("请选择要关闭的比特环境")
        return self._post("/browser/close", {"id": str(browser_id)})
