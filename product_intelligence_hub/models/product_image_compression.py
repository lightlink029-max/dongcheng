import base64
import logging
from io import BytesIO

from PIL import Image, ImageOps

from odoo import api, models


_logger = logging.getLogger(__name__)

MAX_IMAGE_SIDE = 1920
MIN_COMPRESS_BYTES = 200 * 1024
JPEG_QUALITY = 82
WEBP_QUALITY = 82


def _compress_product_image(value):
    """Compress uploaded product media without ever making it larger."""
    if not value:
        return value
    try:
        raw = base64.b64decode(value)
        if len(raw) < MIN_COMPRESS_BYTES:
            return value

        with Image.open(BytesIO(raw)) as source:
            source_format = (source.format or "").upper()
            if source_format in {"GIF", "SVG"} or getattr(source, "is_animated", False):
                return value

            image = ImageOps.exif_transpose(source)
            image.load()
            if max(image.size) > MAX_IMAGE_SIDE:
                image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)

            alpha = image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            target = BytesIO()
            if alpha:
                image.convert("RGBA").save(
                    target, format="WEBP", quality=WEBP_QUALITY, method=6
                )
            else:
                image.convert("RGB").save(
                    target,
                    format="JPEG",
                    quality=JPEG_QUALITY,
                    optimize=True,
                    progressive=True,
                )
            compressed = target.getvalue()
            if len(compressed) >= len(raw):
                return value
            return base64.b64encode(compressed)
    except Exception:
        _logger.warning("Product image compression skipped", exc_info=True)
        return value


class ProductImage(models.Model):
    _inherit = "product.image"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("image_1920"):
                vals["image_1920"] = _compress_product_image(vals["image_1920"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("image_1920"):
            vals = dict(vals, image_1920=_compress_product_image(vals["image_1920"]))
        return super().write(vals)


class ProductTemplateImageCompression(models.Model):
    _inherit = "product.template"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("image_1920"):
                vals["image_1920"] = _compress_product_image(vals["image_1920"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("image_1920"):
            vals = dict(vals, image_1920=_compress_product_image(vals["image_1920"]))
        return super().write(vals)
