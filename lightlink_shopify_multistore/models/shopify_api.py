import base64
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.parse
import urllib.request


SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")
RETRYABLE_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class ShopifyAPIError(Exception):
    def __init__(self, message, *, retryable=False, details=None):
        super().__init__(message)
        self.retryable = retryable
        self.details = details or {}


def normalize_shop_domain(value):
    value = (value or "").strip().lower()
    if "://" in value:
        value = urllib.parse.urlparse(value).netloc
    value = value.split("/", 1)[0].split(":", 1)[0]
    if value and "." not in value:
        value = f"{value}.myshopify.com"
    if not SHOP_DOMAIN_RE.fullmatch(value):
        raise ValueError("店铺域名必须是有效的 *.myshopify.com 域名。")
    return value


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def payload_hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def verify_webhook_hmac(secret, body, signature):
    if not secret or not signature:
        return False
    digest = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(digest, signature)


def verify_oauth_hmac(secret, params):
    if not secret or not params.get("hmac"):
        return False
    supplied = str(params.get("hmac"))
    pairs = []
    for key in sorted(params):
        if key in {"hmac", "signature"}:
            continue
        values = params[key] if isinstance(params[key], (list, tuple)) else [params[key]]
        for value in values:
            pairs.append(
                f"{urllib.parse.quote(str(key), safe='')}="
                f"{urllib.parse.quote(str(value), safe='')}"
            )
    message = "&".join(pairs).encode()
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def graphql_request(domain, api_version, token, query, variables=None, timeout=30):
    url = f"https://{normalize_shop_domain(domain)}/admin/api/{api_version}/graphql.json"
    body = canonical_json({"query": query, "variables": variables or {}}).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token,
            "User-Agent": "LightLink-Odoo-Shopify/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")[:2000]
        raise ShopifyAPIError(
            f"Shopify HTTP {error.code}",
            retryable=error.code in RETRYABLE_HTTP_CODES,
            details={"status": error.code, "body": raw},
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ShopifyAPIError("无法连接 Shopify。", retryable=True) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ShopifyAPIError("Shopify 返回了无法解析的响应。", retryable=True) from error
    if payload.get("errors"):
        error_codes = {
            ((error.get("extensions") or {}).get("code") or "").upper()
            for error in payload["errors"]
        }
        raise ShopifyAPIError(
            "Shopify GraphQL 请求失败。",
            retryable=bool(error_codes & {"THROTTLED", "INTERNAL_SERVER_ERROR"}),
            details={"errors": payload["errors"]},
        )
    return payload.get("data") or {}


def exchange_oauth_code(domain, api_version, client_id, client_secret, code, timeout=30):
    url = f"https://{normalize_shop_domain(domain)}/admin/oauth/access_token"
    body = canonical_json(
        {"client_id": client_id, "client_secret": client_secret, "code": code}
    ).encode()
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ShopifyAPIError("Shopify OAuth 换取令牌失败。", retryable=True) from error
    token = payload.get("access_token")
    if not token:
        raise ShopifyAPIError("Shopify OAuth 响应没有访问令牌。")
    return token, payload.get("scope") or ""
