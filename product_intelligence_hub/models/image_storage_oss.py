import base64
import hashlib
import hmac
import ipaddress
import mimetypes
import socket
from email.utils import formatdate
from urllib.parse import quote, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from odoo import _, models
from odoo.exceptions import UserError


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        ProductImageStorageOSS._validate_remote_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ProductImageStorageOSS(models.AbstractModel):
    _name = "product.image.storage.oss"
    _description = "阿里云 OSS 图片存储"

    PARAM_PREFIX = "product_intelligence_hub.oss_"

    @classmethod
    def _validate_remote_url(cls, url):
        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise UserError(_("图片地址必须是有效的 HTTP 或 HTTPS URL。"))
        try:
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        except socket.gaierror as exc:
            raise UserError(_("无法解析图片服务器地址。")) from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise UserError(_("禁止从内网或本机地址下载图片。"))

    def _config(self):
        params = self.env["ir.config_parameter"].sudo()
        get = lambda name, default="": params.get_param(self.PARAM_PREFIX + name, default)
        endpoint = get("endpoint").strip().replace("https://", "").replace("http://", "").strip("/")
        return {
            "enabled": get("enabled") == "True",
            "access_key_id": get("access_key_id").strip(),
            "access_key_secret": get("access_key_secret").strip(),
            "bucket": get("bucket").strip(),
            "endpoint": endpoint,
            "prefix": get("prefix", "product-intelligence").strip("/ "),
            "public_base_url": get("public_base_url").strip().rstrip("/"),
            "delete_on_unlink": get("delete_on_unlink") == "True",
        }

    def _require_config(self):
        config = self._config()
        missing = [key for key in ("access_key_id", "access_key_secret", "bucket", "endpoint") if not config[key]]
        if missing:
            raise UserError(_("OSS 配置不完整，请填写 AccessKey、Secret、Bucket 和 Endpoint。"))
        return config

    @staticmethod
    def _object_url(config, key):
        encoded = "/".join(quote(part, safe="") for part in key.split("/"))
        if config["public_base_url"]:
            return f'{config["public_base_url"]}/{encoded}'
        return f'https://{config["bucket"]}.{config["endpoint"]}/{encoded}'

    @staticmethod
    def _authorization(config, method, key, content_type=""):
        date = formatdate(usegmt=True)
        resource = f'/{config["bucket"]}/{key}'
        to_sign = f"{method}\n\n{content_type}\n{date}\n{resource}"
        signature = base64.b64encode(
            hmac.new(config["access_key_secret"].encode(), to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        return date, f'OSS {config["access_key_id"]}:{signature}'

    def store_url(self, source_url, external_id=""):
        config = self._require_config()
        self._validate_remote_url(source_url)
        request = Request(source_url, headers={"User-Agent": "Odoo Product Intelligence/1.0"})
        with build_opener(_SafeRedirectHandler()).open(request, timeout=20) as response:
            data = response.read(12 * 1024 * 1024 + 1)
            content_type = (response.headers.get_content_type() or "application/octet-stream").lower()
        if len(data) > 12 * 1024 * 1024:
            raise UserError(_("图片超过 12 MB，已拒绝上传。"))
        if not content_type.startswith("image/"):
            raise UserError(_("远程地址返回的内容不是图片。"))
        extension = mimetypes.guess_extension(content_type) or ".jpg"
        digest = hashlib.sha256(data).hexdigest()
        filename = f"{external_id}-{digest[:16]}{extension}" if external_id else f"{digest}{extension}"
        key = "/".join(filter(None, (config["prefix"], filename)))
        date, authorization = self._authorization(config, "PUT", key, content_type)
        upload = Request(
            self._object_url({**config, "public_base_url": ""}, key),
            data=data,
            method="PUT",
            headers={"Date": date, "Authorization": authorization, "Content-Type": content_type},
        )
        with build_opener().open(upload, timeout=30):
            pass
        return key, self._object_url(config, key)

    def delete_object(self, key):
        config = self._require_config()
        date, authorization = self._authorization(config, "DELETE", key)
        request = Request(
            self._object_url({**config, "public_base_url": ""}, key),
            method="DELETE",
            headers={"Date": date, "Authorization": authorization},
        )
        with build_opener().open(request, timeout=20):
            pass

