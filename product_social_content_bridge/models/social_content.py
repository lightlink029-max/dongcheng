import json
import logging
import base64
import mimetypes
import time
from io import BytesIO

import requests
from PIL import Image, ImageOps

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


_logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_IMAGES_EDIT_URL = "https://api.openai.com/v1/images/edits"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-2"
MAX_ASSET_BYTES = 50 * 1024 * 1024


class MediaAsset(models.Model):
    _name = "psc.media.asset"
    _description = "内容模板与素材"
    _order = "sequence, name"

    name = fields.Char(string="素材名称", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    asset_type = fields.Selection([
        ("image_template", "图片模板"), ("video_template", "视频模板"),
        ("reference_image", "参考图片"), ("logo", "品牌Logo"),
        ("packaging", "包装图片"), ("video_clip", "视频片段"),
        ("audio", "音频素材"),
    ], string="素材类型", required=True, default="reference_image")
    file_data = fields.Binary(string="本地文件", required=True, attachment=True)
    file_name = fields.Char(string="文件名", required=True)
    mimetype = fields.Char(string="文件类型", compute="_compute_file_info", store=True)
    file_size = fields.Integer(string="文件大小（字节）", compute="_compute_file_info", store=True)
    is_image = fields.Boolean(string="图片素材", compute="_compute_file_info", store=True)
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线")
    channel_id = fields.Many2one("psc.publishing.channel", string="适用渠道")
    usage_instructions = fields.Text(string="使用说明", translate=True)

    @api.depends("file_data", "file_name")
    def _compute_file_info(self):
        for asset in self:
            raw = base64.b64decode(asset.file_data or b"")
            asset.file_size = len(raw)
            asset.mimetype = mimetypes.guess_type(asset.file_name or "")[0] or "application/octet-stream"
            asset.is_image = asset.mimetype.startswith("image/")

    @api.constrains("file_data", "file_name", "asset_type")
    def _check_file(self):
        for asset in self:
            raw = base64.b64decode(asset.file_data or b"")
            if len(raw) > MAX_ASSET_BYTES:
                raise UserError(_("单个素材不能超过 50 MB。"))
            mimetype = mimetypes.guess_type(asset.file_name or "")[0] or ""
            if asset.asset_type in ("image_template", "reference_image", "logo", "packaging") and not mimetype.startswith("image/"):
                raise UserError(_("图片模板和图片素材只能上传图片文件。"))
            if asset.asset_type in ("video_template", "video_clip") and not mimetype.startswith("video/"):
                raise UserError(_("视频模板和视频片段只能上传视频文件。"))
            if asset.asset_type == "audio" and not mimetype.startswith("audio/"):
                raise UserError(_("音频素材只能上传音频文件。"))


class ProductLine(models.Model):
    _name = "psc.product.line"
    _description = "品牌/产品线"
    _order = "name"

    name = fields.Char(string="产品线", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    brand_name = fields.Char(string="品牌")
    active = fields.Boolean(default=True)
    website_id = fields.Many2one("website", string="默认网站")
    product_ids = fields.Many2many("product.template", string="产品")
    tone = fields.Selection([
        ("professional", "专业"), ("persuasive", "营销"),
        ("friendly", "亲和"), ("technical", "技术"),
    ], string="内容语气", default="professional")
    target_customer = fields.Text(string="目标客户", translate=True)
    key_selling_points = fields.Text(string="默认卖点", translate=True)
    compliance_notes = fields.Text(string="合规与禁用词", translate=True)

    _code_unique = models.Constraint("UNIQUE(code)", "产品线代码不能重复。")


class TargetMarket(models.Model):
    _name = "psc.target.market"
    _description = "目标市场"
    _order = "country_id, name"

    name = fields.Char(string="市场名称", required=True, translate=True)
    active = fields.Boolean(default=True)
    country_id = fields.Many2one("res.country", string="国家/地区", required=True)
    lang_id = fields.Many2one("res.lang", string="语言", required=True)
    currency_id = fields.Many2one("res.currency", string="币种", required=True)
    customer_type = fields.Selection([("b2b", "B2B"), ("b2c", "B2C")], default="b2b", required=True)
    keywords = fields.Text(string="市场关键词", translate=True)
    compliance_notes = fields.Text(string="认证与合规要求", translate=True)


class MediaModel(models.Model):
    _name = "psc.media.model"
    _description = "图片/视频生成模型"
    _order = "media_type, sequence, name"

    name = fields.Char(string="显示名称", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    media_type = fields.Selection([
        ("image", "图片生成"), ("video", "视频生成"),
    ], string="媒体类型", required=True)
    provider = fields.Selection([
        ("openai", "OpenAI"), ("fal", "fal.ai"), ("bfl", "Black Forest Labs"),
        ("runway", "Runway"), ("ffmpeg", "自建 FFmpeg"),
        ("creatomate", "Creatomate"), ("shotstack", "Shotstack"),
        ("custom", "自定义接口"),
    ], string="服务商", required=True, default="openai")
    model_code = fields.Char(string="模型/引擎代码", required=True)
    api_base_url = fields.Char(string="接口地址")
    api_key_parameter = fields.Char(string="API Key 系统参数", help="填写系统参数名称，例如 ai.fal_key；不要在这里直接填写密钥。")
    deprecated = fields.Boolean(string="已弃用")
    notes = fields.Text(string="说明")


class PublishingChannel(models.Model):
    _name = "psc.publishing.channel"
    _description = "发布渠道"
    _order = "name"

    name = fields.Char(string="渠道名称", required=True)
    active = fields.Boolean(default=True)
    platform = fields.Selection([
        ("facebook", "Facebook"), ("instagram", "Instagram"),
        ("linkedin", "LinkedIn"), ("youtube", "YouTube"),
        ("twitter", "X/Twitter"), ("tiktok", "TikTok（预留）"),
        ("website", "Odoo独立站"), ("alibaba", "阿里国际站（预留）"),
    ], required=True)
    social_account_ids = fields.Many2many("social.account", string="Odoo社媒账号")
    image_ratio = fields.Selection([("1_1", "1:1"), ("4_5", "4:5"), ("9_16", "9:16")], default="1_1")
    max_caption_length = fields.Integer(string="文案字数限制", default=2200)
    default_instructions = fields.Text(string="渠道内容规则", translate=True)
    image_quality = fields.Selection([
        ("low", "低（测试/省费用）"), ("medium", "中（推荐）"), ("high", "高"),
    ], string="图片质量", default="medium", required=True)
    image_model_id = fields.Many2one(
        "psc.media.model", string="图片生成模型",
        domain="[('media_type', '=', 'image'), ('active', '=', True)]",
        default=lambda self: self.env.ref(
            "product_social_content_bridge.media_model_openai_gpt_image_2", raise_if_not_found=False
        ),
    )
    video_model_id = fields.Many2one(
        "psc.media.model", string="视频生成模型",
        domain="[('media_type', '=', 'video'), ('active', '=', True)]",
        default=lambda self: self.env.ref(
            "product_social_content_bridge.media_model_ffmpeg_default", raise_if_not_found=False
        ),
    )
    template_asset_ids = fields.Many2many(
        "psc.media.asset", "psc_channel_template_asset_rel", "channel_id", "asset_id",
        string="默认模板与素材",
    )


class PublishingProject(models.Model):
    _name = "psc.publishing.project"
    _description = "社媒发布项目"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="发布项目", required=True, tracking=True)
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线", required=True, tracking=True)
    product_ids = fields.Many2many("product.template", string="发布产品", required=True)
    market_ids = fields.Many2many("psc.target.market", string="目标市场", required=True)
    channel_ids = fields.Many2many("psc.publishing.channel", string="发布渠道", required=True)
    user_id = fields.Many2one("res.users", string="负责人", default=lambda self: self.env.user)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    scheduled_date = fields.Datetime(string="计划发布时间")
    content_brief = fields.Text(string="本期内容要求", translate=True)
    state = fields.Selection([
        ("draft", "草稿"), ("generated", "待确认"),
        ("ready", "待发布"), ("published", "已发布"), ("failed", "发布失败"),
    ], default="draft", required=True, tracking=True)
    content_ids = fields.One2many("psc.content.variant", "project_id", string="渠道内容")
    content_count = fields.Integer(compute="_compute_content_count")
    ai_model = fields.Char(string="AI模型", default=DEFAULT_OPENAI_MODEL)
    material_asset_ids = fields.Many2many(
        "psc.media.asset", "psc_project_material_asset_rel", "project_id", "asset_id",
        string="项目模板与素材",
    )

    @api.depends("content_ids")
    def _compute_content_count(self):
        for record in self:
            record.content_count = len(record.content_ids)

    @api.onchange("product_line_id")
    def _onchange_product_line_id(self):
        if self.product_line_id and not self.product_ids:
            self.product_ids = self.product_line_id.product_ids

    def action_generate_drafts(self):
        for project in self:
            if not project.product_ids or not project.market_ids or not project.channel_ids:
                raise UserError(_("请先选择产品、目标市场和发布渠道。"))
            existing = {(x.product_id.id, x.market_id.id, x.channel_id.id) for x in project.content_ids}
            commands = []
            for product in project.product_ids:
                for market in project.market_ids:
                    for channel in project.channel_ids:
                        key = (product.id, market.id, channel.id)
                        if key in existing:
                            continue
                        selling = project.product_line_id.key_selling_points or product.description_sale or ""
                        commands.append((0, 0, {
                            "product_id": product.id, "market_id": market.id, "channel_id": channel.id,
                            "language_id": market.lang_id.id,
                            "title": product.name,
                            "caption": "\n\n".join(filter(None, [product.name, selling, project.content_brief or ""])),
                            "state": "draft",
                        }))
            if commands:
                project.write({"content_ids": commands, "state": "generated"})
            project.content_ids.filtered(lambda item: item.state != "published").action_generate_ai_content()
        return True

    def action_mark_ready(self):
        self.write({"state": "ready"})
        self.mapped("content_ids").filtered(lambda x: x.state == "draft").write({"state": "ready"})
        return True


class ContentVariant(models.Model):
    _name = "psc.content.variant"
    _description = "产品渠道内容版本"
    _order = "project_id desc, product_id, market_id, channel_id"

    project_id = fields.Many2one("psc.publishing.project", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.template", string="产品", required=True, ondelete="cascade")
    market_id = fields.Many2one("psc.target.market", string="市场", required=True)
    channel_id = fields.Many2one("psc.publishing.channel", string="渠道", required=True)
    language_id = fields.Many2one("res.lang", string="内容语言", required=True)
    title = fields.Char(string="标题", translate=True)
    caption = fields.Text(string="发布文案", translate=True)
    hashtags = fields.Char(string="标签")
    video_script = fields.Text(string="短视频脚本", translate=True)
    image_attachment_id = fields.Many2one("ir.attachment", string="发布图片")
    generated_image = fields.Binary(related="image_attachment_id.datas", string="图片预览", readonly=True)
    video_attachment_id = fields.Many2one("ir.attachment", string="发布视频")
    material_asset_ids = fields.Many2many(
        "psc.media.asset", "psc_content_material_asset_rel", "content_id", "asset_id",
        string="本次使用的模板与素材",
    )
    state = fields.Selection([
        ("draft", "草稿"), ("ready", "待发布"),
        ("published", "已发布"), ("failed", "失败"),
    ], default="draft", required=True)
    social_post_id = fields.Many2one("social.post", string="Odoo社媒帖子", readonly=True)
    published_url = fields.Char(string="发布链接")
    error_message = fields.Text(string="错误信息")
    ai_state = fields.Selection([
        ("pending", "待生成"), ("done", "已生成"), ("failed", "生成失败"),
    ], string="AI生成状态", default="pending", required=True, readonly=True)
    ai_model = fields.Char(string="生成模型", readonly=True)
    ai_generated_at = fields.Datetime(string="AI生成时间", readonly=True)
    ai_input_tokens = fields.Integer(string="输入Token", readonly=True)
    ai_output_tokens = fields.Integer(string="输出Token", readonly=True)
    image_prompt = fields.Text(string="图片素材提示词", translate=True)
    image_ai_state = fields.Selection([
        ("pending", "待生成"), ("done", "已生成"), ("failed", "生成失败"),
    ], string="图片生成状态", default="pending", required=True, readonly=True)
    image_ai_model = fields.Char(string="图片模型", readonly=True)
    image_generated_at = fields.Datetime(string="图片生成时间", readonly=True)
    video_ai_state = fields.Selection([
        ("pending", "待生成"), ("processing", "生成中"),
        ("done", "已生成"), ("failed", "生成失败"),
    ], string="视频生成状态", default="pending", required=True, readonly=True)
    video_ai_model = fields.Char(string="视频模型", readonly=True)
    video_generated_at = fields.Datetime(string="视频生成时间", readonly=True)

    _variant_unique = models.Constraint(
        "UNIQUE(project_id, product_id, market_id, channel_id)",
        "同一项目中产品、市场和渠道组合不能重复。",
    )

    @api.model
    def _openai_api_key(self):
        key = self.env["ir.config_parameter"].sudo().get_param("ai.openai_key")
        if not key:
            raise UserError(_("尚未配置 OpenAI API Key，请先在系统参数 ai.openai_key 中配置。"))
        return key

    @api.model
    def _media_api_key(self, media_model):
        parameter = media_model.api_key_parameter or {
            "openai": "ai.openai_key", "fal": "ai.fal_key",
            "bfl": "ai.bfl_key", "runway": "ai.runway_key",
        }.get(media_model.provider)
        key = parameter and self.env["ir.config_parameter"].sudo().get_param(parameter)
        if not key:
            raise UserError(_("尚未配置 %(provider)s API Key，请在系统参数 %(parameter)s 中配置。",
                              provider=media_model.provider, parameter=parameter or "API Key"))
        return key

    def _fal_submit_and_wait(self, media_model, payload, timeout=600):
        self.ensure_one()
        api_key = self._media_api_key(media_model)
        endpoint = (media_model.api_base_url or "https://queue.fal.run").rstrip("/")
        submit = requests.post(
            "%s/%s" % (endpoint, media_model.model_code.lstrip("/")),
            headers={"Authorization": "Key %s" % api_key, "Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        submit.raise_for_status()
        job = submit.json()
        response_url, status_url = job.get("response_url"), job.get("status_url")
        if not response_url:
            return job
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if status_url:
                status = requests.get(status_url, headers={"Authorization": "Key %s" % api_key}, timeout=30)
                status.raise_for_status()
                state = (status.json().get("status") or "").upper()
                if state in ("FAILED", "CANCELLED"):
                    raise ValueError(status.text)
                if state not in ("COMPLETED", "OK"):
                    time.sleep(4)
                    continue
            result = requests.get(response_url, headers={"Authorization": "Key %s" % api_key}, timeout=60)
            if result.status_code in (202, 404):
                time.sleep(4)
                continue
            result.raise_for_status()
            return result.json()
        raise ValueError("fal.ai generation timed out")

    def _source_image_data_url(self):
        raw, _filename, mimetype = self._source_product_image()
        return "data:%s;base64,%s" % (mimetype, base64.b64encode(raw).decode())

    @api.model
    def _response_output_text(self, response_data):
        if response_data.get("output_text"):
            return response_data["output_text"]
        parts = []
        for item in response_data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(content["text"])
        return "\n".join(parts)

    def _product_context(self):
        self.ensure_one()
        product = self.product_id.with_context(lang=self.language_id.code)
        source_description = (
            getattr(product, "description_ecommerce", False)
            or product.description_sale
            or ""
        )
        return {
            "product_name": product.name or "",
            "sales_description": html2plaintext(source_description)[:8000],
            "list_price": product.list_price,
            "currency": self.project_id.company_id.currency_id.name,
            "brand": self.project_id.product_line_id.brand_name or "",
            "product_line": self.project_id.product_line_id.name,
            "default_selling_points": self.project_id.product_line_id.key_selling_points or "",
            "target_customer": self.project_id.product_line_id.target_customer or "",
            "product_line_compliance": self.project_id.product_line_id.compliance_notes or "",
            "market": self.market_id.name,
            "country": self.market_id.country_id.name,
            "language": self.language_id.name,
            "customer_type": self.market_id.customer_type.upper(),
            "market_keywords": self.market_id.keywords or "",
            "market_compliance": self.market_id.compliance_notes or "",
            "channel": self.channel_id.name,
            "platform": self.channel_id.platform,
            "caption_limit": self.channel_id.max_caption_length,
            "channel_rules": self.channel_id.default_instructions or "",
            "content_brief": self.project_id.content_brief or "",
        }

    def _openai_payload(self):
        self.ensure_one()
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "selling_points": {"type": "array", "items": {"type": "string"}},
                "seo_keywords": {"type": "array", "items": {"type": "string"}},
                "caption": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
                "video_script": {"type": "string"},
                "image_prompt": {"type": "string"},
            },
            "required": ["title", "selling_points", "seo_keywords", "caption", "hashtags", "video_script", "image_prompt"],
            "additionalProperties": False,
        }
        instructions = (
            "You create accurate export-commerce product and social content. "
            "Use only facts in the supplied product context; never invent certifications, performance, materials, "
            "prices, shipping promises, customer testimonials, or medical claims. "
            "Write all customer-facing output in the requested language. "
            "Return concise, platform-appropriate content and respect the caption limit. "
            "The video_script must be a practical 15-30 second shot list with voiceover and on-screen text. "
            "The image_prompt must preserve the real product and describe a clean commercial composition."
        )
        return {
            "model": self.project_id.ai_model or DEFAULT_OPENAI_MODEL,
            "instructions": instructions,
            "input": json.dumps(self._product_context(), ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": "social_product_content", "strict": True, "schema": schema}},
            "max_output_tokens": 2400,
            "store": False,
        }

    def action_generate_ai_content(self):
        api_key = self._openai_api_key()
        for variant in self:
            payload = variant._openai_payload()
            try:
                response = requests.post(
                    OPENAI_RESPONSES_URL,
                    headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=90,
                )
                response.raise_for_status()
                response_data = response.json()
                output_text = variant._response_output_text(response_data)
                if not output_text:
                    raise ValueError("OpenAI response did not contain output text")
                generated = json.loads(output_text)
                hashtags = []
                for tag in generated.get("hashtags", []):
                    clean_tag = str(tag).strip().lstrip("#").replace(" ", "")
                    if clean_tag:
                        hashtags.append("#%s" % clean_tag)
                selling_points = generated.get("selling_points", [])
                seo_keywords = generated.get("seo_keywords", [])
                caption_parts = [generated.get("caption", "")]
                if selling_points:
                    caption_parts.append("\n".join("• %s" % point for point in selling_points))
                if seo_keywords:
                    caption_parts.append(_("SEO关键词：%s") % ", ".join(seo_keywords))
                usage = response_data.get("usage") or {}
                variant.write({
                    "title": generated.get("title") or variant.product_id.name,
                    "caption": "\n\n".join(filter(None, caption_parts)),
                    "hashtags": " ".join(hashtags),
                    "video_script": generated.get("video_script", ""),
                    "image_prompt": generated.get("image_prompt", ""),
                    "ai_state": "done",
                    "ai_model": response_data.get("model") or payload["model"],
                    "ai_generated_at": fields.Datetime.now(),
                    "ai_input_tokens": usage.get("input_tokens", 0),
                    "ai_output_tokens": usage.get("output_tokens", 0),
                    "error_message": False,
                })
            except (requests.RequestException, ValueError, json.JSONDecodeError) as error:
                detail = str(error)
                if isinstance(error, requests.HTTPError) and error.response is not None:
                    try:
                        detail = (error.response.json().get("error") or {}).get("message") or detail
                    except (ValueError, AttributeError):
                        pass
                _logger.exception("OpenAI content generation failed for variant %s", variant.id)
                variant.write({
                    "ai_state": "failed",
                    "ai_model": payload["model"],
                    "error_message": detail[:2000],
                })
        return True

    def _source_product_image(self):
        self.ensure_one()
        encoded = self.product_id.image_1920
        if not encoded:
            raise UserError(_("产品没有主图，请先在产品中上传主图。"))
        try:
            raw = base64.b64decode(encoded)
        except (ValueError, TypeError) as error:
            raise UserError(_("产品主图数据无效。")) from error
        if raw.startswith(b"\x89PNG"):
            return raw, "product.png", "image/png"
        if raw.startswith(b"\xff\xd8"):
            return raw, "product.jpg", "image/jpeg"
        if raw[:4] in (b"RIFF", b"WEBP") or raw[8:12] == b"WEBP":
            return raw, "product.webp", "image/webp"
        return raw, "product.png", "application/octet-stream"

    def _image_size(self):
        self.ensure_one()
        return "1024x1024" if self.channel_id.image_ratio == "1_1" else "1024x1536"

    def _selected_image_inputs(self):
        self.ensure_one()
        assets = (
            self.channel_id.template_asset_ids
            | self.project_id.material_asset_ids
            | self.material_asset_ids
        ).filtered(
            lambda item: item.active and item.asset_type in ("image_template", "reference_image", "logo", "packaging")
        ).sorted(lambda item: (item.sequence, item.id))[:4]
        result = []
        for asset in assets:
            raw = base64.b64decode(asset.file_data or b"")
            if raw:
                result.append((asset, raw, asset.file_name, asset.mimetype))
        return result

    def _finalize_social_image(self, raw_image):
        self.ensure_one()
        target_sizes = {"1_1": (1080, 1080), "4_5": (1080, 1350), "9_16": (1080, 1920)}
        target_size = target_sizes.get(self.channel_id.image_ratio, (1080, 1080))
        with Image.open(BytesIO(raw_image)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image = ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
            return output.getvalue()

    def action_generate_social_image(self):
        for variant in self:
            if variant.ai_state != "done":
                raise UserError(_("请先生成并确认文字内容，再生成图片素材。"))
            source_image, filename, mimetype = variant._source_product_image()
            image_model = variant.channel_id.image_model_id
            image_model_code = image_model.model_code if image_model else DEFAULT_OPENAI_IMAGE_MODEL
            if image_model and image_model.deprecated:
                raise UserError(_("所选图片模型已被标记为弃用，请在发布渠道中更换模型。"))
            selected_images = variant._selected_image_inputs()
            asset_roles = "; ".join(
                "%s: %s%s" % (index + 2, asset.name, (" — " + asset.usage_instructions) if asset.usage_instructions else "")
                for index, (asset, _raw, _filename, _mimetype) in enumerate(selected_images)
            )
            prompt = "\n".join(filter(None, [
                variant.image_prompt,
                "Create a polished commercial social-media product image using the supplied real product photo as the reference.",
                "Keep the product identity, shape, colors, materials, construction details, and proportions faithful to the reference.",
                "Do not add logos, certifications, prices, discounts, watermarks, labels, packaging claims, or readable text.",
                "Use a clean export-commerce composition suitable for %s in the %s market." % (
                    variant.channel_id.name, variant.market_id.name,
                ),
                "Reference image 1 is the real product and must remain the visual source of truth.",
                ("Additional ordered references/templates: %s" % asset_roles) if asset_roles else "",
                "Use templates as layout guidance and logos only when explicitly supplied as a logo asset.",
            ]))
            try:
                if image_model and image_model.provider == "fal":
                    response_data = variant._fal_submit_and_wait(image_model, {
                        "prompt": prompt,
                        "image_url": variant._source_image_data_url(),
                        "aspect_ratio": variant.channel_id.image_ratio.replace("_", ":"),
                    })
                    output = (response_data.get("images") or [{}])[0]
                    output_url = output.get("url") or (response_data.get("image") or {}).get("url")
                    if not output_url:
                        raise ValueError("fal.ai image response did not contain an image URL")
                    download = requests.get(output_url, timeout=90)
                    download.raise_for_status()
                    generated = download.content
                elif not image_model or image_model.provider == "openai":
                    api_key = variant._openai_api_key()
                    files = [("image[]", (filename, source_image, mimetype))]
                    files.extend(
                        ("image[]", (asset_filename, raw, asset_mimetype))
                        for _asset, raw, asset_filename, asset_mimetype in selected_images
                    )
                    response = requests.post(
                        OPENAI_IMAGES_EDIT_URL,
                        headers={"Authorization": "Bearer %s" % api_key},
                        data={
                            "model": image_model_code,
                            "prompt": prompt,
                            "size": variant._image_size(),
                            "quality": variant.channel_id.image_quality,
                            "output_format": "png",
                        },
                        files=files,
                        timeout=180,
                    )
                    response.raise_for_status()
                    response_data = response.json()
                    result = (response_data.get("data") or [{}])[0]
                    if result.get("b64_json"):
                        generated = base64.b64decode(result["b64_json"])
                    elif result.get("url"):
                        download = requests.get(result["url"], timeout=90)
                        download.raise_for_status()
                        generated = download.content
                    else:
                        raise ValueError("OpenAI image response did not contain image data")
                else:
                    raise UserError(_("所选图片服务商尚未接入自动生成。"))
                final_image = variant._finalize_social_image(generated)
                attachment = self.env["ir.attachment"].create({
                    "name": "social-%s-%s-%s.jpg" % (variant.product_id.id, variant.market_id.id, variant.channel_id.id),
                    "type": "binary",
                    "datas": base64.b64encode(final_image),
                    "mimetype": "image/jpeg",
                    "res_model": variant._name,
                    "res_id": variant.id,
                })
                previous = variant.image_attachment_id
                variant.write({
                    "image_attachment_id": attachment.id,
                    "image_ai_state": "done",
                    "image_ai_model": image_model_code,
                    "image_generated_at": fields.Datetime.now(),
                    "error_message": False,
                })
                if previous and previous != attachment:
                    previous.unlink()
            except (requests.RequestException, ValueError, OSError) as error:
                detail = str(error)
                if isinstance(error, requests.HTTPError) and error.response is not None:
                    try:
                        detail = (error.response.json().get("error") or {}).get("message") or detail
                    except (ValueError, AttributeError):
                        pass
                _logger.exception("OpenAI image generation failed for variant %s", variant.id)
                variant.write({
                    "image_ai_state": "failed",
                    "image_ai_model": image_model_code,
                    "error_message": detail[:2000],
                })
        return True

    def action_create_social_post(self):
        for variant in self:
            if variant.channel_id.platform in ("tiktok", "alibaba", "website"):
                raise UserError(_("该渠道当前为预留接口，不能创建Odoo社媒帖子。"))
            if not variant.channel_id.social_account_ids:
                raise UserError(_("请先在渠道中关联Odoo社媒账号。"))
            values = {
                "message": "\n\n".join(filter(None, [variant.caption, variant.hashtags])),
                "account_ids": [(6, 0, variant.channel_id.social_account_ids.ids)],
                "company_id": variant.project_id.company_id.id,
            }
            if variant.image_attachment_id:
                values["image_ids"] = [(6, 0, variant.image_attachment_id.ids)]
            post = self.env["social.post"].create(values)
            variant.write({"social_post_id": post.id, "state": "ready", "error_message": False})
        return True

    def action_generate_social_video(self):
        for variant in self:
            media_model = variant.channel_id.video_model_id
            if not media_model or media_model.provider != "fal":
                raise UserError(_("请选择已接入的 fal.ai 视频模型。"))
            if media_model.deprecated:
                raise UserError(_("所选视频模型已停用，请更换模型。"))
            variant.write({"video_ai_state": "processing", "video_ai_model": media_model.model_code})
            try:
                prompt = "\n".join(filter(None, [
                    variant.video_script, variant.caption,
                    "Preserve the real product identity, shape, colors, materials and proportions.",
                ]))
                result = variant._fal_submit_and_wait(media_model, {
                    "prompt": prompt,
                    "image_url": variant._source_image_data_url(),
                    "duration": "5",
                    "aspect_ratio": variant.channel_id.image_ratio.replace("_", ":"),
                })
                video = result.get("video") or (result.get("videos") or [{}])[0]
                video_url = video.get("url") if isinstance(video, dict) else video
                if not video_url:
                    raise ValueError("fal.ai response did not contain a video URL")
                download = requests.get(video_url, timeout=180)
                download.raise_for_status()
                attachment = self.env["ir.attachment"].create({
                    "name": "social-%s-%s-%s.mp4" % (
                        variant.product_id.id, variant.market_id.id, variant.channel_id.id,
                    ),
                    "type": "binary",
                    "datas": base64.b64encode(download.content),
                    "mimetype": "video/mp4",
                    "res_model": variant._name,
                    "res_id": variant.id,
                })
                previous = variant.video_attachment_id
                variant.write({
                    "video_attachment_id": attachment.id,
                    "video_ai_state": "done",
                    "video_generated_at": fields.Datetime.now(),
                    "error_message": False,
                })
                if previous and previous != attachment:
                    previous.unlink()
            except (requests.RequestException, ValueError, OSError) as error:
                _logger.exception("Video generation failed for variant %s", variant.id)
                variant.write({"video_ai_state": "failed", "error_message": str(error)[:2000]})
        return True

    def action_open_social_post(self):
        self.ensure_one()
        if not self.social_post_id:
            raise UserError(_("尚未创建Odoo社媒帖子。"))
        return {
            "type": "ir.actions.act_window", "res_model": "social.post",
            "res_id": self.social_post_id.id, "view_mode": "form", "target": "current",
        }


class CrmLead(models.Model):
    _inherit = "crm.lead"

    psc_project_id = fields.Many2one("psc.publishing.project", string="来源发布项目", index=True)
    psc_product_line_id = fields.Many2one("psc.product.line", string="来源产品线", index=True)
    psc_market_id = fields.Many2one("psc.target.market", string="来源市场", index=True)
    psc_channel_id = fields.Many2one("psc.publishing.channel", string="来源渠道", index=True)
    psc_content_id = fields.Many2one("psc.content.variant", string="来源帖子内容", index=True)
