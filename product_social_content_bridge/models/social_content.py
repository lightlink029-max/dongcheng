import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


_logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"


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
    video_attachment_id = fields.Many2one("ir.attachment", string="发布视频")
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
