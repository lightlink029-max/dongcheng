import base64
import hashlib
import json
import logging
import re
import uuid
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageOps, UnidentifiedImageError

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


class ProductImageSearchService(models.AbstractModel):
    _name = "product.image.search.service"
    _description = "Qdrant product image search service"

    _PARAM_PREFIX = "product_intelligence_hub."
    _DEFAULTS = {
        "qdrant_collection": "odoo_product_images",
        "qdrant_image_model": "Qdrant/clip-ViT-B-32-vision",
        "qdrant_vector_dimension": 512,
        "qdrant_result_limit": 12,
        "qdrant_score_threshold": 0.18,
        "qdrant_upload_limit_mb": 5,
        "qdrant_rate_limit": 20,
    }

    @api.model
    def _parameter(self, name, default=None):
        value = self.env["ir.config_parameter"].sudo().get_param(
            f"{self._PARAM_PREFIX}{name}"
        )
        return default if value in (False, None, "") else value

    @api.model
    def _int_parameter(self, name, minimum, maximum):
        try:
            value = int(self._parameter(name, self._DEFAULTS[name]))
        except (TypeError, ValueError):
            value = self._DEFAULTS[name]
        return max(minimum, min(maximum, value))

    @api.model
    def _float_parameter(self, name, minimum, maximum):
        try:
            value = float(self._parameter(name, self._DEFAULTS[name]))
        except (TypeError, ValueError):
            value = self._DEFAULTS[name]
        return max(minimum, min(maximum, value))

    @api.model
    def is_enabled(self):
        return self._parameter("qdrant_enabled", "False") == "True"

    @api.model
    def is_ready(self):
        return bool(
            self.is_enabled()
            and self._parameter("qdrant_url", "")
            and self._parameter("qdrant_api_key", "")
        )

    @api.model
    def public_limits(self):
        return {
            "upload_mb": self._int_parameter("qdrant_upload_limit_mb", 1, 10),
            "rate_per_minute": self._int_parameter("qdrant_rate_limit", 1, 120),
        }

    @api.model
    def _config(self, require_enabled=True):
        enabled = self.is_enabled()
        base_url = str(self._parameter("qdrant_url", "") or "").strip().rstrip("/")
        api_key = str(self._parameter("qdrant_api_key", "") or "").strip()
        collection = str(
            self._parameter("qdrant_collection", self._DEFAULTS["qdrant_collection"])
        ).strip()
        image_model = str(
            self._parameter("qdrant_image_model", self._DEFAULTS["qdrant_image_model"])
        ).strip()

        if require_enabled and not enabled:
            raise UserError(_("网站以图搜产品尚未启用。"))
        if not base_url or not api_key:
            raise UserError(_("请先保存 Qdrant 集群地址和 API Key。"))
        parsed = urlparse(base_url)
        is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_local):
            raise ValidationError(_("Qdrant 集群必须使用 HTTPS。"))
        if parsed.username or parsed.password:
            raise ValidationError(_("Qdrant 地址中不能包含用户名或密码。"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}", collection):
            raise ValidationError(_("Qdrant 集合名称格式不正确。"))
        if not image_model:
            raise ValidationError(_("图片向量模型不能为空。"))
        return {
            "enabled": enabled,
            "base_url": base_url,
            "api_key": api_key,
            "collection": collection,
            "image_model": image_model,
            "dimension": self._int_parameter("qdrant_vector_dimension", 32, 8192),
            "result_limit": self._int_parameter("qdrant_result_limit", 1, 48),
            "score_threshold": self._float_parameter(
                "qdrant_score_threshold", 0.0, 1.0
            ),
            **self.public_limits(),
        }

    @api.model
    def _qdrant_request(self, method, path, payload=None, allow_not_found=False):
        config = self._config()
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(
            f"{config['base_url']}{path}",
            data=body,
            method=method,
            headers={
                "api-key": config["api_key"],
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "LightLink-Odoo-Image-Search/1.0",
            },
        )
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as exc:
            if allow_not_found and exc.code == 404:
                return None
            detail = exc.read(2048).decode("utf-8", errors="replace")
            _logger.warning("Qdrant returned HTTP %s: %s", exc.code, detail)
            raise UserError(_("Qdrant 请求失败（HTTP %s）。", exc.code)) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            _logger.warning("Qdrant connection failed: %s", exc)
            raise UserError(_("暂时无法连接 Qdrant，请稍后重试。")) from exc

    @api.model
    def _ensure_collection(self):
        config = self._config()
        collection_path = quote(config["collection"], safe="")
        existing = self._qdrant_request(
            "GET", f"/collections/{collection_path}", allow_not_found=True
        )
        if existing is None:
            self._qdrant_request(
                "PUT",
                f"/collections/{collection_path}",
                {
                    "vectors": {
                        "image": {
                            "size": config["dimension"],
                            "distance": "Cosine",
                        }
                    }
                },
            )
            return True

        vectors = (
            (existing.get("result") or {}).get("config", {}).get("params", {}).get("vectors")
            or {}
        )
        image_vector = vectors.get("image") if isinstance(vectors, dict) else None
        existing_size = image_vector.get("size") if isinstance(image_vector, dict) else None
        if existing_size and int(existing_size) != config["dimension"]:
            raise ValidationError(
                _(
                    "现有 Qdrant 集合的向量维度是 %(actual)s，当前设置是 %(expected)s。"
                    "请恢复原维度，或使用新的集合名称。",
                    actual=existing_size,
                    expected=config["dimension"],
                )
            )
        return False

    @api.model
    def test_connection(self):
        self._ensure_collection()
        config = self._config()
        image = Image.new("RGB", (8, 8), "white")
        output = BytesIO()
        image.save(output, format="JPEG")
        data_url, _digest = self._prepare_image(output.getvalue())
        point_id = str(uuid.uuid4())
        collection = quote(config["collection"], safe="")
        self._qdrant_request(
            "PUT",
            f"/collections/{collection}/points?wait=true",
            {
                "points": [
                    {
                        "id": point_id,
                        "vector": {
                            "image": {
                                "image": data_url,
                                "model": config["image_model"],
                            }
                        },
                        "payload": {"connection_test": True},
                    }
                ]
            },
        )
        self._qdrant_request(
            "POST",
            f"/collections/{collection}/points/delete?wait=true",
            {"points": [point_id]},
        )
        return True

    @api.model
    def _prepare_image(self, image_bytes, max_bytes=None):
        if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
            raise ValidationError(_("请选择有效的图片文件。"))
        limit = max_bytes or self.public_limits()["upload_mb"] * 1024 * 1024
        if len(image_bytes) > limit:
            raise ValidationError(_("图片不能超过 %s MB。", max(1, limit // 1024 // 1024)))
        try:
            with Image.open(BytesIO(image_bytes)) as source:
                if source.width * source.height > 25_000_000:
                    raise ValidationError(_("图片像素过大，请压缩后重试。"))
                source.load()
                image = ImageOps.exif_transpose(source)
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                if image.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=88, optimize=True)
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError(_("文件不是可识别的 JPG、PNG 或 WebP 图片。")) from exc
        normalized = output.getvalue()
        return (
            "data:image/jpeg;base64," + base64.b64encode(normalized).decode("ascii"),
            hashlib.sha256(normalized).hexdigest(),
        )

    @api.model
    def _decode_odoo_image(self, value):
        if not value:
            return b""
        try:
            return base64.b64decode(value)
        except (ValueError, TypeError):
            return b""

    @api.model
    def _point_id(self, product_id, image_kind, image_id):
        database_uuid = self.env["ir.config_parameter"].sudo().get_param("database.uuid")
        source = f"{database_uuid or self.env.cr.dbname}:product.template:{product_id}:{image_kind}:{image_id}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, source))

    @api.model
    def _delete_product_points(self, product_id):
        config = self._config()
        collection = quote(config["collection"], safe="")
        self._qdrant_request(
            "POST",
            f"/collections/{collection}/points/delete?wait=true",
            {
                "filter": {
                    "must": [
                        {"key": "product_tmpl_id", "match": {"value": product_id}}
                    ]
                }
            },
        )

    @api.model
    def _product_image_values(self, product):
        images = []
        main_image = self._decode_odoo_image(product.image_1920)
        if main_image:
            images.append(("main", product.id, main_image))
        for extra in product.product_template_image_ids.sorted("sequence"):
            image_bytes = self._decode_odoo_image(extra.image_1920)
            if image_bytes:
                images.append(("gallery", extra.id, image_bytes))
        return images

    @api.model
    def index_product(self, product):
        product.ensure_one()
        config = self._config()
        self._ensure_collection()
        self._delete_product_points(product.id)

        eligible = bool(
            product.active
            and product.sale_ok
            and product.website_published
            and product.image_1920
        )
        if not eligible:
            product.with_context(pi_skip_image_search_dirty=True).write(
                {
                    "pi_image_search_state": "skipped",
                    "pi_image_search_indexed_at": fields.Datetime.now(),
                    "pi_image_search_error": False,
                }
            )
            return 0

        points = []
        hashes = []
        for image_kind, image_id, image_bytes in self._product_image_values(product):
            image_data_url, digest = self._prepare_image(image_bytes, max_bytes=20 * 1024 * 1024)
            hashes.append(digest)
            points.append(
                {
                    "id": self._point_id(product.id, image_kind, image_id),
                    "vector": {
                        "image": {
                            "image": image_data_url,
                            "model": config["image_model"],
                        }
                    },
                    "payload": {
                        "product_tmpl_id": product.id,
                        "image_kind": image_kind,
                        "image_id": image_id,
                        "company_id": product.company_id.id or 0,
                    },
                }
            )

        if points:
            collection = quote(config["collection"], safe="")
            self._qdrant_request(
                "PUT",
                f"/collections/{collection}/points?wait=true",
                {"points": points},
            )
        product.with_context(pi_skip_image_search_dirty=True).write(
            {
                "pi_image_search_state": "indexed" if points else "skipped",
                "pi_image_search_signature": hashlib.sha256(
                    "|".join(hashes).encode("ascii")
                ).hexdigest() if hashes else False,
                "pi_image_search_indexed_at": fields.Datetime.now(),
                "pi_image_search_error": False,
            }
        )
        return len(points)

    @api.model
    def action_index_pending_products(self, limit=20):
        if not self.is_enabled():
            return {"processed": 0, "indexed_images": 0, "errors": 0}
        products = self.env["product.template"].sudo().search(
            ["|", ("pi_image_search_state", "=", False), ("pi_image_search_state", "=", "pending")],
            order="write_date asc, id asc",
            limit=max(1, min(int(limit), 100)),
        )
        indexed_images = errors = 0
        for product in products:
            try:
                with self.env.cr.savepoint():
                    indexed_images += self.index_product(product)
            except Exception as exc:
                _logger.exception("Unable to index product %s in Qdrant", product.id)
                product.with_context(pi_skip_image_search_dirty=True).write(
                    {
                        "pi_image_search_state": "error",
                        "pi_image_search_error": str(exc)[:500],
                    }
                )
                errors += 1
        return {
            "processed": len(products),
            "indexed_images": indexed_images,
            "errors": errors,
        }

    @api.model
    def search_similar_product_ids(self, image_bytes):
        config = self._config()
        image_data_url, _digest = self._prepare_image(image_bytes)
        collection = quote(config["collection"], safe="")
        response = self._qdrant_request(
            "POST",
            f"/collections/{collection}/points/query",
            {
                "query": {
                    "image": image_data_url,
                    "model": config["image_model"],
                },
                "using": "image",
                "with_payload": ["product_tmpl_id"],
                "with_vector": False,
                "limit": min(config["result_limit"] * 4, 100),
                "score_threshold": config["score_threshold"],
            },
        )
        result = response.get("result") or {}
        points = result.get("points", []) if isinstance(result, dict) else result
        product_ids = []
        for point in points or []:
            product_id = (point.get("payload") or {}).get("product_tmpl_id")
            if isinstance(product_id, int) and product_id not in product_ids:
                product_ids.append(product_id)
            if len(product_ids) >= config["result_limit"]:
                break
        return product_ids


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pi_image_search_state = fields.Selection(
        [
            ("pending", "待索引"),
            ("indexed", "已索引"),
            ("skipped", "未公开/无图片"),
            ("error", "失败"),
        ],
        string="图片搜索索引",
        default="pending",
        copy=False,
        index=True,
        readonly=True,
    )
    pi_image_search_signature = fields.Char(copy=False, readonly=True)
    pi_image_search_indexed_at = fields.Datetime(
        string="图片索引时间", copy=False, readonly=True
    )
    pi_image_search_error = fields.Char(
        string="图片索引错误", copy=False, readonly=True
    )

    @api.model
    def _cron_update_image_search_index(self):
        return self.env["product.image.search.service"].action_index_pending_products(
            limit=20
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("pi_skip_image_search_dirty"):
            records.with_context(pi_skip_image_search_dirty=True).write(
                {"pi_image_search_state": "pending", "pi_image_search_error": False}
            )
        return records

    def write(self, vals):
        watched = {"image_1920", "website_published", "is_published", "sale_ok", "active"}
        result = super().write(vals)
        if not self.env.context.get("pi_skip_image_search_dirty") and watched.intersection(vals):
            self.with_context(pi_skip_image_search_dirty=True).write(
                {"pi_image_search_state": "pending", "pi_image_search_error": False}
            )
        return result

    def action_pi_index_image_search(self):
        indexed = 0
        for product in self:
            indexed += self.env["product.image.search.service"].index_product(product)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("图片索引完成"),
                "message": _("已更新 %s 张商品图片。", indexed),
                "type": "success",
                "sticky": False,
            },
        }


class ProductImage(models.Model):
    _inherit = "product.image"

    @api.model_create_multi
    def create(self, vals_list):
        images = super().create(vals_list)
        images.mapped("product_tmpl_id").with_context(
            pi_skip_image_search_dirty=True
        ).write({"pi_image_search_state": "pending", "pi_image_search_error": False})
        return images

    def write(self, vals):
        products = self.mapped("product_tmpl_id")
        result = super().write(vals)
        if {"image_1920", "product_tmpl_id", "sequence"}.intersection(vals):
            (products | self.mapped("product_tmpl_id")).with_context(
                pi_skip_image_search_dirty=True
            ).write({"pi_image_search_state": "pending", "pi_image_search_error": False})
        return result

    def unlink(self):
        products = self.mapped("product_tmpl_id")
        result = super().unlink()
        products.with_context(pi_skip_image_search_dirty=True).write(
            {"pi_image_search_state": "pending", "pi_image_search_error": False}
        )
        return result
