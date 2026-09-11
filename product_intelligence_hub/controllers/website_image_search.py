import logging
import threading
import time
from collections import defaultdict, deque

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.http import request


_logger = logging.getLogger(__name__)
_RATE_LOCK = threading.Lock()
_RATE_HITS = defaultdict(deque)


class ProductWebsiteImageSearchController(http.Controller):

    @staticmethod
    def _consume_rate_limit(client_key, limit):
        now = time.monotonic()
        with _RATE_LOCK:
            hits = _RATE_HITS[client_key]
            while hits and hits[0] <= now - 60:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            if len(_RATE_HITS) > 5000:
                stale = [key for key, values in _RATE_HITS.items() if not values or values[-1] <= now - 60]
                for key in stale[:1000]:
                    _RATE_HITS.pop(key, None)
            return True

    @http.route(
        "/shop/image-search",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def product_image_search(self, **post):
        service = request.env["product.image.search.service"].sudo()
        values = {"products": request.env["product.template"], "error": False}
        if not service.is_ready():
            values["error"] = "以图搜产品正在配置中，请稍后再试。"
            return request.render(
                "product_intelligence_hub.product_image_search_results", values
            )

        limits = service.public_limits()
        client_key = request.httprequest.remote_addr or "unknown"
        if not self._consume_rate_limit(client_key, limits["rate_per_minute"]):
            values["error"] = "搜索太频繁，请一分钟后再试。"
            return request.render(
                "product_intelligence_hub.product_image_search_results", values,
                status=429,
            )

        uploaded = request.httprequest.files.get("image")
        if not uploaded:
            values["error"] = "请选择一张需要查找的产品图片。"
            return request.render(
                "product_intelligence_hub.product_image_search_results", values,
                status=400,
            )
        max_bytes = limits["upload_mb"] * 1024 * 1024
        image_bytes = uploaded.stream.read(max_bytes + 1)
        if len(image_bytes) > max_bytes:
            values["error"] = f"图片不能超过 {limits['upload_mb']} MB。"
            return request.render(
                "product_intelligence_hub.product_image_search_results", values,
                status=413,
            )

        try:
            product_ids = service.search_similar_product_ids(image_bytes)
            Product = request.env["product.template"].sudo()
            allowed_products = Product.search(
                Domain("id", "in", product_ids) & request.website.sale_product_domain()
            )
            allowed_ids = set(allowed_products.ids)
            values["products"] = Product.browse(
                [product_id for product_id in product_ids if product_id in allowed_ids]
            )
        except (UserError, ValidationError) as exc:
            _logger.info("Public image search unavailable: %s", exc)
            values["error"] = "图片搜索暂时不可用，请稍后重试或使用关键词搜索。"
        except Exception:
            _logger.exception("Unexpected public product image search failure")
            values["error"] = "图片搜索暂时不可用，请稍后重试。"
        return request.render(
            "product_intelligence_hub.product_image_search_results", values
        )
