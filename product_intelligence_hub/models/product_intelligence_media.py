import html

from odoo import api, fields, models


class ProductIntelligenceMedia(models.Model):
    _name = "product.intelligence.media"
    _description = "产品机会媒体"
    _order = "sequence, id"

    candidate_id = fields.Many2one(
        "product.intelligence.candidate", string="产品机会", required=True,
        ondelete="cascade", index=True,
    )
    sequence = fields.Integer(string="排序", default=10)
    media_type = fields.Selection(
        [("image", "图片"), ("video", "视频")], string="类型", required=True,
        default="image", index=True,
    )
    name = fields.Char(string="名称")
    source_url = fields.Char(string="来源链接", required=True, index=True)
    preview = fields.Html(string="预览", compute="_compute_preview", sanitize=False)
    product_image_id = fields.Many2one(
        "product.image", string="电商媒体", readonly=True, copy=False, ondelete="set null",
    )

    @api.depends("source_url", "media_type")
    def _compute_preview(self):
        for record in self:
            url = html.escape(record.source_url or "", quote=True)
            if not url:
                record.preview = ""
            elif record.media_type == "video":
                record.preview = (
                    f'<video src="{url}" controls preload="metadata" '
                    'style="width:240px;max-height:180px;border-radius:6px"></video>'
                )
            else:
                record.preview = (
                    f'<img src="{url}" alt="产品图片" '
                    'style="width:180px;height:180px;object-fit:contain;border-radius:6px"/>'
                )


class ProductImage(models.Model):
    _inherit = "product.image"

    pi_source_url = fields.Char(string="选品媒体来源", index=True, copy=False)
    pi_candidate_media_id = fields.Many2one(
        "product.intelligence.media", string="产品机会媒体", index=True,
        copy=False, ondelete="set null",
    )
