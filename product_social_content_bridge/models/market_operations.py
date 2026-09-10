from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


FOOTWEAR_SOURCING_READINESS_TEMPLATE = (
    ("strategy_positioning", 10, "strategy", "确认英文定位与服务边界", 4, True, "joint", 0,
     "确认 China Footwear Sourcing & Supply Chain Partner 定位、服务范围和不宣称自有工厂的边界。"),
    ("strategy_icp", 20, "strategy", "定义进口商、批发商与 Private Label 客户画像", 3, False, "ai", 0,
     "形成目标客户规模、采购角色、需求信号、排除条件和优先级规则。"),
    ("strategy_market_kpi", 30, "strategy", "确认美国与英国首发市场及指标", 3, False, "joint", 1,
     "首期使用英文内容覆盖美国和英国，并确定流量、询盘、报价、订单和净毛利指标。"),
    ("product_shortlist", 40, "product", "建立首批 5 个鞋款候选池", 5, False, "joint", 2,
     "录入真实鞋款或候选产品，不使用虚构产品作为正式发布依据。"),
    ("product_specs", 50, "product", "核实材质、尺码、颜色与包装资料", 6, True, "user", 3,
     "为每个首发鞋款补齐并核实材质、尺码范围、颜色、包装与图片证据。"),
    ("product_supplier_terms", 60, "product", "核实供应商报价、MOQ、产能与交期", 5, True, "user", 4,
     "使用供应商真实资料填写采购价、MOQ、打样周期、量产交期和产能。"),
    ("product_margin", 70, "product", "核算目标售价、样品成本与毛利", 5, True, "ai", 5,
     "基于已核实成本和物流条件计算报价区间、样品成本及目标毛利。"),
    ("product_approval", 80, "product", "完成市场适配评分并批准首发产品", 4, True, "joint", 6,
     "完成需求、价格、MOQ、质量与视觉素材评分，只批准通过硬门槛的产品。"),
    ("compliance_ip", 90, "compliance", "核实商标、图片和款式知识产权", 5, True, "user", 4,
     "确认商标授权、图片使用权和款式风险；未授权品牌或素材不得发布。"),
    ("compliance_us", 100, "compliance", "完成美国鞋类标签与合规清单", 5, True, "joint", 5,
     "按首发产品实际材料和用途核对美国标签、进口与宣传要求并保存依据。"),
    ("compliance_uk", 110, "compliance", "完成英国鞋类标签与合规清单", 5, True, "joint", 5,
     "按首发产品实际材料和用途核对英国标签、进口与宣传要求并保存依据。"),
    ("compliance_claims", 120, "compliance", "复核全部英文声明与证据", 5, True, "ai", 7,
     "价格、认证、环保、性能、产能、交期和案例声明必须与 Odoo 中的证据一致。"),
    ("commercial_rfq", 130, "commercial", "完成英文 RFQ 与报价模板", 5, True, "ai", 6,
     "模板包含 MOQ、价格有效期、Incoterms、付款条件、打样和量产交期。"),
    ("commercial_sample", 140, "commercial", "建立样品申请与跟进流程", 4, False, "ai", 7,
     "明确样品费用、寄送、反馈、改样和转订单的状态及响应时限。"),
    ("commercial_qc", 150, "commercial", "建立验货、质量与索赔规则", 3, True, "joint", 8,
     "明确产前、生产中、出货前检查和不合格处理规则。"),
    ("commercial_shipping", 160, "commercial", "补齐包装、装箱、HS 与运输资料", 3, True, "user", 8,
     "使用真实包装尺寸、重量、装箱量、HS 建议和物流条件。"),
    ("content_message", 170, "content", "完成英文价值主张与网站落地页结构", 4, False, "ai", 8,
     "围绕供应商筛选、验厂、质量控制、成本、交期和出口协调组织英文信息。"),
    ("content_assets", 180, "content", "准备首发产品图片、视频与事实表", 4, True, "user", 9,
     "素材必须真实、可授权，并能支持页面和社媒中的产品事实。"),
    ("content_linkedin", 190, "content", "完成 LinkedIn 首发内容包", 3, False, "ai", 10,
     "准备 4 条英文 B2B 内容，覆盖采购知识、供应商管理、质量控制和产品机会。"),
    ("content_instagram", 200, "content", "完成 Instagram 首发内容包", 3, False, "ai", 10,
     "准备 6 条英文图片或短视频内容，使用真实产品与供应链素材。"),
    ("content_cta", 210, "content", "完成询盘 CTA、表单与隐私说明", 1, True, "joint", 10,
     "网站和社媒统一指向可追踪的询盘入口，并提供必要的隐私说明。"),
    ("channel_website", 220, "channel", "配置英文网站与数据追踪", 4, True, "joint", 11,
     "完成网站发布目标、表单测试、分析工具和来源追踪。"),
    ("channel_linkedin", 230, "channel", "配置 LinkedIn 真实账号授权", 2, True, "user", 11,
     "由本人完成真实账号登录授权；密码和 Cookie 不录入 Odoo。"),
    ("channel_instagram", 240, "channel", "配置 Instagram 真实账号授权", 2, True, "user", 11,
     "由本人完成真实账号登录授权；密码和 Cookie 不录入 Odoo。"),
    ("channel_attribution", 250, "channel", "配置 UTM、来源归因与驾驶舱", 2, True, "ai", 12,
     "网站、LinkedIn、Instagram 的流量、询盘、报价和订单可回溯到渠道与内容。"),
    ("crm_stages", 260, "operations", "配置 ICP、CRM 阶段与响应时限", 2, False, "ai", 12,
     "覆盖新询盘、需求确认、报价、样品、谈判、赢单和流失原因。"),
    ("operations_rehearsal", 270, "operations", "完成询盘到订单的全流程演练", 2, True, "joint", 13,
     "用明确测试标识的数据验证询盘、报价、样品、采购、库存、交付和收款链路。"),
    ("operations_review", 280, "operations", "建立每周数据复盘与优化节奏", 1, False, "ai", 13,
     "每周基于渠道、产品、客户和净毛利数据生成保留、迭代或停止建议。"),
)


class BusinessCapability(models.Model):
    _name = "psc.business.capability"
    _description = "经营能力标签"
    _order = "sequence, name"

    name = fields.Char(string="能力名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string="能力说明", translate=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "经营能力代码不能重复。")


class BusinessRole(models.Model):
    _name = "psc.business.role"
    _description = "主要经营角色"
    _order = "sequence, name"

    name = fields.Char(string="角色名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string="角色说明", translate=True)
    content_focus = fields.Text(string="默认内容重点", translate=True)
    capability_ids = fields.Many2many(
        "psc.business.capability", "psc_role_capability_rel", "role_id", "capability_id",
        string="默认能力",
    )
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "经营角色代码不能重复。")


class IndustryTrack(models.Model):
    _name = "psc.industry.track"
    _description = "经营赛道模板"
    _order = "sequence, name"

    name = fields.Char(string="赛道名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string="赛道说明", translate=True)
    role_ids = fields.Many2many(
        "psc.business.role", "psc_track_role_rel", "track_id", "role_id",
        string="适用经营角色",
    )
    default_customer_profile = fields.Text(string="默认客户画像", translate=True)
    compliance_notes = fields.Text(string="合规与硬性门槛", translate=True)
    customer_requirement_template = fields.Text(string="客户需求采集模板", translate=True)
    default_kpis = fields.Text(string="默认经营指标", translate=True)
    product_attribute_ids = fields.One2many(
        "psc.track.product.attribute", "track_id", string="产品属性模板",
    )
    scoring_rule_ids = fields.One2many(
        "psc.track.scoring.rule", "track_id", string="产品评分规则",
    )
    content_pillar_ids = fields.One2many(
        "psc.content.pillar", "track_id", string="内容栏目",
    )
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "经营赛道代码不能重复。")


class TrackProductAttribute(models.Model):
    _name = "psc.track.product.attribute"
    _description = "赛道产品属性模板"
    _order = "track_id, sequence, id"

    track_id = fields.Many2one(
        "psc.industry.track", string="经营赛道", required=True, ondelete="cascade", index=True,
    )
    name = fields.Char(string="属性名称", required=True, translate=True)
    code = fields.Char(string="属性代码", required=True)
    value_type = fields.Selection([
        ("text", "文本"), ("number", "数值"), ("boolean", "是/否"),
        ("selection", "选项"), ("date", "日期"),
    ], string="值类型", required=True, default="text")
    unit = fields.Char(string="单位")
    selection_values = fields.Text(string="可选值", help="每行一个可选值。")
    required_for_publish = fields.Boolean(string="发布前必填")
    hard_gate = fields.Boolean(string="硬性门槛")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _track_code_unique = models.Constraint(
        "UNIQUE(track_id, code)", "同一赛道的产品属性代码不能重复。",
    )


class TrackScoringRule(models.Model):
    _name = "psc.track.scoring.rule"
    _description = "赛道产品评分规则"
    _order = "track_id, sequence, id"

    track_id = fields.Many2one(
        "psc.industry.track", string="经营赛道", required=True, ondelete="cascade", index=True,
    )
    name = fields.Char(string="评分维度", required=True, translate=True)
    code = fields.Char(string="代码", required=True)
    weight = fields.Float(string="权重 %", required=True, default=10.0)
    hard_gate = fields.Boolean(string="硬性门槛")
    criteria = fields.Text(string="评分及通过标准", translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _track_code_unique = models.Constraint(
        "UNIQUE(track_id, code)", "同一赛道的评分规则代码不能重复。",
    )

    @api.constrains("weight")
    def _check_weight(self):
        for rule in self:
            if not 0.0 <= rule.weight <= 100.0:
                raise ValidationError(_("评分权重必须在 0 到 100 之间。"))


class ContentPillar(models.Model):
    _name = "psc.content.pillar"
    _description = "赛道内容栏目"
    _order = "track_id, sequence, id"

    name = fields.Char(string="栏目名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True)
    track_id = fields.Many2one(
        "psc.industry.track", string="经营赛道", required=True, ondelete="cascade", index=True,
    )
    role_ids = fields.Many2many(
        "psc.business.role", "psc_pillar_role_rel", "pillar_id", "role_id",
        string="适用角色",
    )
    objective = fields.Char(string="栏目目标", translate=True)
    default_ratio = fields.Float(string="建议占比 %", default=10.0)
    instructions = fields.Text(string="生成规则", translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _track_code_unique = models.Constraint(
        "UNIQUE(track_id, code)", "同一赛道的内容栏目代码不能重复。",
    )

    @api.constrains("default_ratio")
    def _check_ratio(self):
        for pillar in self:
            if not 0.0 <= pillar.default_ratio <= 100.0:
                raise ValidationError(_("内容栏目占比必须在 0 到 100 之间。"))


class ProjectProduct(models.Model):
    _name = "psc.project.product"
    _description = "市场运营项目产品"
    _order = "priority, fit_score desc, id desc"

    name = fields.Char(string="项目产品", compute="_compute_name", store=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    product_id = fields.Many2one(
        "product.template", string="Odoo 正式产品", ondelete="restrict", index=True,
    )
    candidate_id = fields.Many2one(
        "product.intelligence.candidate", string="产品智能候选", ondelete="restrict", index=True,
    )
    source = fields.Selection([
        ("odoo", "Odoo 产品库"), ("intelligence", "产品智能"),
        ("manual", "人工录入"),
    ], string="产品来源", required=True, default="odoo")
    market_ids = fields.Many2many(
        "psc.target.market", "psc_project_product_market_rel", "project_product_id", "market_id",
        string="适用市场",
    )
    status = fields.Selection([
        ("candidate", "候选"), ("quotation", "待询价"),
        ("market_review", "待市场分析"), ("compliance_review", "待合规确认"),
        ("active", "可运营"), ("paused", "暂停推广"), ("rejected", "淘汰"),
    ], string="产品状态", required=True, default="candidate", index=True)
    priority = fields.Selection([
        ("1", "最高"), ("2", "高"), ("3", "普通"), ("4", "低"),
    ], string="推广优先级", default="3", required=True)
    positioning = fields.Text(string="项目产品定位", translate=True)
    selling_points = fields.Text(string="项目核心卖点", translate=True)
    recommendation = fields.Text(string="推荐/不推荐理由", translate=True)
    compliance_state = fields.Selection([
        ("unknown", "未检查"), ("review", "待复核"),
        ("passed", "通过"), ("blocked", "禁止发布"),
    ], string="合规状态", default="unknown", required=True)
    material_state = fields.Selection([
        ("missing", "资料不足"), ("partial", "部分完整"), ("complete", "完整"),
    ], string="产品资料", default="missing", required=True)
    currency_id = fields.Many2one(
        "res.currency", related="project_id.company_id.currency_id", readonly=True,
    )
    target_purchase_price = fields.Monetary(string="目标采购价", currency_field="currency_id")
    target_sale_price = fields.Monetary(string="目标销售价", currency_field="currency_id")
    minimum_order_qty = fields.Float(string="MOQ")
    lead_time_days = fields.Integer(string="交期（天）")
    score_line_ids = fields.One2many(
        "psc.project.product.score", "project_product_id", string="适配评分",
    )
    attribute_value_ids = fields.One2many(
        "psc.project.product.attribute.value", "project_product_id", string="赛道产品属性",
    )
    fit_score = fields.Float(string="市场适配评分", compute="_compute_fit_score", store=True)
    hard_gate_passed = fields.Boolean(string="硬性门槛通过", compute="_compute_fit_score", store=True)
    last_reviewed_at = fields.Datetime(string="最近检查时间")
    next_review_date = fields.Date(string="下次检查日期")

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            project = self.env["psc.publishing.project"].browse(values.get("project_id")).exists()
            candidate = self.env["product.intelligence.candidate"].browse(values.get("candidate_id")).exists()
            if project and not values.get("market_ids"):
                values["market_ids"] = [(6, 0, project.market_ids.ids)]
            if candidate:
                values.setdefault("source", "intelligence")
                values.setdefault("target_purchase_price", candidate.supplier_price)
                values.setdefault("target_sale_price", candidate.target_sale_price)
                values.setdefault("minimum_order_qty", candidate.minimum_order_qty)
                values.setdefault("lead_time_days", candidate.lead_time_days)
            if project and project.track_id and not values.get("score_line_ids"):
                values["score_line_ids"] = [(0, 0, {
                    "rule_id": rule.id, "name": rule.name, "sequence": rule.sequence,
                    "weight": rule.weight, "hard_gate": rule.hard_gate,
                    "gate_passed": not rule.hard_gate,
                }) for rule in project.track_id.scoring_rule_ids.filtered("active")]
            if project and project.track_id and not values.get("attribute_value_ids"):
                values["attribute_value_ids"] = [(0, 0, {
                    "attribute_id": attribute.id, "name": attribute.name,
                    "required_for_publish": attribute.required_for_publish,
                    "hard_gate": attribute.hard_gate, "sequence": attribute.sequence,
                }) for attribute in project.track_id.product_attribute_ids.filtered("active")]
        return super().create(vals_list)

    @api.depends("product_id", "candidate_id", "candidate_id.name")
    def _compute_name(self):
        for record in self:
            record.name = record.product_id.display_name or record.candidate_id.name or _("未命名候选产品")

    @api.depends(
        "score_line_ids.score", "score_line_ids.weight", "score_line_ids.hard_gate",
        "score_line_ids.gate_passed",
    )
    def _compute_fit_score(self):
        for record in self:
            lines = record.score_line_ids
            total_weight = sum(lines.mapped("weight"))
            record.fit_score = (
                sum(line.score * line.weight for line in lines) / total_weight
                if total_weight else 0.0
            )
            record.hard_gate_passed = not any(
                line.hard_gate and not line.gate_passed for line in lines
            )

    @api.constrains("product_id", "candidate_id")
    def _check_source_record(self):
        for record in self:
            if not record.product_id and not record.candidate_id:
                raise ValidationError(_("项目产品必须选择 Odoo 正式产品或产品智能候选。"))
            duplicate = self.search_count([
                ("id", "!=", record.id), ("project_id", "=", record.project_id.id),
                "|", "&", ("product_id", "!=", False), ("product_id", "=", record.product_id.id),
                "&", ("candidate_id", "!=", False), ("candidate_id", "=", record.candidate_id.id),
            ])
            if duplicate:
                raise ValidationError(_("该产品已经存在于当前项目产品池。"))

    def action_link_candidate_product(self):
        for record in self:
            candidate = record.candidate_id
            if not candidate:
                raise UserError(_("当前记录没有产品智能候选。"))
            if candidate.stage not in ("approved", "executed"):
                raise UserError(_("请先在产品智能中审核并批准该候选产品。"))
            if not candidate.product_tmpl_id:
                candidate.action_create_product()
            record.write({"product_id": candidate.product_tmpl_id.id, "source": "intelligence"})
        return True

    def action_mark_active(self):
        for record in self:
            if not record.product_id:
                raise UserError(_("进入可运营状态前，必须先关联 Odoo 正式产品。"))
            if record.material_state != "complete":
                raise UserError(_("产品资料尚未完整，不能批准运营。"))
            missing_attributes = record.attribute_value_ids.filtered(
                lambda line: line.required_for_publish and (not line.value or not line.verified)
            )
            if missing_attributes:
                raise UserError(_("以下发布必填属性尚未填写并核实：%s") % ", ".join(missing_attributes.mapped("name")))
            blocked_attributes = record.attribute_value_ids.filtered(
                lambda line: line.hard_gate and not line.verified
            )
            if blocked_attributes:
                raise UserError(_("以下硬性门槛尚未通过：%s") % ", ".join(blocked_attributes.mapped("name")))
            if record.compliance_state != "passed" or not record.hard_gate_passed:
                raise UserError(_("合规检查或硬性门槛尚未通过，不能对外运营。"))
            record.write({"status": "active", "last_reviewed_at": fields.Datetime.now()})
        return True

    def action_open_source(self):
        self.ensure_one()
        record = self.product_id or self.candidate_id
        if not record:
            return False
        return {
            "type": "ir.actions.act_window", "res_model": record._name,
            "res_id": record.id, "view_mode": "form", "target": "current",
        }


class CandidateMarketFit(models.Model):
    _name = "psc.candidate.market.fit"
    _description = "候选产品市场适配分析"
    _order = "fit_score desc, id desc"

    candidate_id = fields.Many2one(
        "product.intelligence.candidate", string="候选产品", required=True,
        ondelete="cascade", index=True,
    )
    track_id = fields.Many2one("psc.industry.track", string="经营赛道", required=True)
    market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    business_role_id = fields.Many2one("psc.business.role", string="适合角色")
    fit_score = fields.Float(string="市场适配评分", default=50.0)
    demand_evidence = fields.Text(string="需求依据")
    target_customer = fields.Text(string="适合客户")
    recommendation = fields.Text(string="推荐理由")
    compliance_state = fields.Selection([
        ("unknown", "未检查"), ("review", "待复核"),
        ("passed", "通过"), ("blocked", "不适合"),
    ], string="合规判断", default="unknown", required=True)
    state = fields.Selection([
        ("draft", "待分析"), ("review", "待人工复核"),
        ("approved", "确认适合"), ("rejected", "不适合"),
    ], string="结论", default="draft", required=True)

    _candidate_market_track_unique = models.Constraint(
        "UNIQUE(candidate_id, market_id, track_id)",
        "同一候选产品在同一赛道和市场只能有一份适配分析。",
    )

    @api.constrains("fit_score")
    def _check_fit_score(self):
        for fit in self:
            if not 0.0 <= fit.fit_score <= 100.0:
                raise ValidationError(_("市场适配评分必须在 0 到 100 之间。"))


class ProductIntelligenceCandidateMarket(models.Model):
    _inherit = "product.intelligence.candidate"

    psc_market_fit_ids = fields.One2many(
        "psc.candidate.market.fit", "candidate_id", string="适合市场分析",
    )


class ProjectProductScore(models.Model):
    _name = "psc.project.product.score"
    _description = "项目产品适配评分"
    _order = "project_product_id, sequence, id"

    project_product_id = fields.Many2one(
        "psc.project.product", string="项目产品", required=True, ondelete="cascade", index=True,
    )
    rule_id = fields.Many2one("psc.track.scoring.rule", string="评分规则", ondelete="restrict")
    name = fields.Char(string="评分维度", required=True)
    sequence = fields.Integer(default=10)
    weight = fields.Float(string="权重 %", required=True, default=10.0)
    score = fields.Float(string="得分", required=True, default=50.0)
    hard_gate = fields.Boolean(string="硬性门槛")
    gate_passed = fields.Boolean(string="已通过", default=True)
    notes = fields.Text(string="依据与说明")

    @api.onchange("rule_id")
    def _onchange_rule_id(self):
        if self.rule_id:
            self.name = self.rule_id.name
            self.sequence = self.rule_id.sequence
            self.weight = self.rule_id.weight
            self.hard_gate = self.rule_id.hard_gate

    @api.constrains("weight", "score")
    def _check_values(self):
        for line in self:
            if not 0.0 <= line.weight <= 100.0 or not 0.0 <= line.score <= 100.0:
                raise ValidationError(_("权重和得分必须在 0 到 100 之间。"))


class ProjectProductAttributeValue(models.Model):
    _name = "psc.project.product.attribute.value"
    _description = "项目产品赛道属性值"
    _order = "project_product_id, sequence, id"

    project_product_id = fields.Many2one(
        "psc.project.product", string="项目产品", required=True, ondelete="cascade", index=True,
    )
    attribute_id = fields.Many2one(
        "psc.track.product.attribute", string="属性模板", required=True, ondelete="restrict",
    )
    name = fields.Char(string="属性名称", required=True)
    sequence = fields.Integer(default=10)
    value = fields.Char(string="属性值")
    required_for_publish = fields.Boolean(string="发布前必填")
    hard_gate = fields.Boolean(string="硬性门槛")
    verified = fields.Boolean(string="已核实")
    evidence = fields.Text(string="依据/附件说明")

    _product_attribute_unique = models.Constraint(
        "UNIQUE(project_product_id, attribute_id)", "同一个项目产品的赛道属性不能重复。",
    )


class ContentPlan(models.Model):
    _name = "psc.content.plan"
    _description = "项目内容计划"
    _order = "scheduled_at, id"

    name = fields.Char(string="内容主题", required=True, translate=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    pillar_id = fields.Many2one("psc.content.pillar", string="内容栏目", required=True)
    product_id = fields.Many2one("product.template", string="关联产品")
    market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    channel_id = fields.Many2one("psc.publishing.channel", string="发布渠道", required=True)
    scheduled_at = fields.Datetime(string="计划发布时间")
    brief = fields.Text(string="内容要求", translate=True)
    state = fields.Selection([
        ("draft", "计划"), ("prepared", "已生成草稿"),
        ("ready", "待发布"), ("published", "已发布"), ("cancelled", "取消"),
    ], string="状态", default="draft", required=True, index=True)
    content_id = fields.Many2one("psc.content.variant", string="渠道内容", readonly=True)

    def action_prepare_content(self):
        for plan in self:
            if plan.content_id:
                continue
            product = plan.product_id or plan.project_id.project_product_ids.filtered(
                lambda item: item.status == "active" and item.product_id
            )[:1].product_id
            if not product:
                raise UserError(_("请先选择产品，或在项目产品池中批准至少一个可运营产品。"))
            content = self.env["psc.content.variant"].create({
                "project_id": plan.project_id.id,
                "plan_id": plan.id,
                "pillar_id": plan.pillar_id.id,
                "product_id": product.id,
                "market_id": plan.market_id.id,
                "channel_id": plan.channel_id.id,
                "language_id": plan.market_id.lang_id.id,
                "title": plan.name,
                "caption": plan.brief or plan.pillar_id.instructions or "",
                "state": "draft",
            })
            plan.write({"content_id": content.id, "state": "prepared"})
        return self.action_open_content()

    def action_open_content(self):
        self.ensure_one()
        if not self.content_id:
            raise UserError(_("尚未生成渠道内容草稿。"))
        return {
            "type": "ir.actions.act_window", "res_model": "psc.content.variant",
            "res_id": self.content_id.id, "view_mode": "form", "target": "current",
        }


class SocialAccountCluster(models.Model):
    _name = "psc.social.account.cluster"
    _description = "社媒账号集群"
    _order = "name"

    name = fields.Char(string="账号集群", required=True)
    active = fields.Boolean(default=True)
    project_ids = fields.Many2many(
        "psc.publishing.project", "psc_project_account_cluster_rel", "cluster_id", "project_id",
        string="允许发布的项目",
    )
    track_id = fields.Many2one("psc.industry.track", string="主赛道")
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线")
    target_market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    persona = fields.Char(string="品牌/运营身份", required=True)
    positioning = fields.Text(string="账号定位")
    worker_node_id = fields.Many2one(
        "psc.local.worker.node", string="Windows 工作节点", required=True,
    )
    bitbrowser_environment_id = fields.Many2one(
        "psc.bitbrowser.environment", string="比特浏览器环境", required=True,
        domain="[('worker_node_id', '=', worker_node_id), ('available', '=', True)]",
    )
    expected_ip = fields.Char(string="预期固定 IP", required=True)
    expected_country_id = fields.Many2one("res.country", string="预期国家/地区", required=True)
    expected_timezone = fields.Char(string="预期时区", required=True, default="UTC")
    state = fields.Selection([
        ("draft", "待配置"), ("ready", "可使用"),
        ("busy", "环境占用"), ("failed", "环境异常"), ("paused", "暂停"),
    ], string="集群状态", required=True, default="draft", index=True)
    account_ids = fields.One2many(
        "psc.social.publishing.account", "cluster_id", string="平台账号",
    )
    last_validation_at = fields.Datetime(string="最后环境校验", readonly=True)
    last_validation_message = fields.Text(string="环境校验结果", readonly=True)

    _environment_unique = models.Constraint(
        "UNIQUE(bitbrowser_environment_id)", "一个比特浏览器环境只能绑定一个账号集群。",
    )

    @api.onchange("target_market_id")
    def _onchange_target_market_id(self):
        if self.target_market_id:
            self.expected_country_id = self.target_market_id.country_id

    @api.constrains("worker_node_id", "bitbrowser_environment_id")
    def _check_environment_worker(self):
        for cluster in self:
            if cluster.bitbrowser_environment_id.worker_node_id != cluster.worker_node_id:
                raise ValidationError(_("比特环境不属于所选 Windows 工作节点。"))

    def action_mark_ready(self):
        for cluster in self:
            if not cluster.account_ids.filtered(lambda account: account.account_state == "available"):
                raise UserError(_("账号集群至少需要一个可发布的平台账号。"))
            cluster.state = "ready"
        return True

    def action_pause(self):
        self.write({"state": "paused"})
        return True


class CustomerTouchpoint(models.Model):
    _name = "psc.customer.touchpoint"
    _description = "客户来源触点"
    _order = "occurred_at desc, id desc"

    lead_id = fields.Many2one("crm.lead", string="客户/线索", required=True, ondelete="cascade", index=True)
    occurred_at = fields.Datetime(string="发生时间", required=True, default=fields.Datetime.now, index=True)
    event_type = fields.Selection([
        ("impression", "看到内容"), ("click", "点击"), ("visit", "访问网站"),
        ("download", "下载资料"), ("inquiry", "询盘"), ("message", "沟通"),
        ("quote", "报价"), ("sample", "样品"), ("order", "订单"),
        ("offline", "线下接触"),
    ], string="触点类型", required=True, default="inquiry")
    source_type = fields.Selection([
        ("website", "独立站"), ("facebook", "Facebook"),
        ("instagram", "Instagram"), ("tiktok", "TikTok"),
        ("linkedin", "LinkedIn"), ("youtube", "YouTube"),
        ("alibaba", "阿里国际站"), ("exhibition", "展会"),
        ("offline", "线下"), ("referral", "客户介绍"),
        ("manual", "人工录入"), ("unknown", "未知"),
    ], string="来源", required=True, default="unknown", index=True)
    project_id = fields.Many2one("psc.publishing.project", string="市场运营项目", index=True)
    market_id = fields.Many2one("psc.target.market", string="市场")
    channel_id = fields.Many2one("psc.publishing.channel", string="渠道")
    cluster_id = fields.Many2one("psc.social.account.cluster", string="账号集群")
    account_id = fields.Many2one("psc.social.publishing.account", string="平台账号")
    content_id = fields.Many2one("psc.content.variant", string="来源内容")
    product_id = fields.Many2one("product.template", string="感兴趣产品")
    landing_url = fields.Char(string="入口链接")
    external_reference = fields.Char(string="平台询盘/消息编号")
    utm_source = fields.Char(string="UTM Source")
    utm_medium = fields.Char(string="UTM Medium")
    utm_campaign = fields.Char(string="UTM Campaign")
    utm_content = fields.Char(string="UTM Content")
    utm_term = fields.Char(string="UTM Term")
    verified = fields.Boolean(string="来源已确认")
    notes = fields.Text(string="说明")


class CustomerRequirement(models.Model):
    _name = "psc.customer.requirement"
    _description = "客户行业需求单"
    _order = "create_date desc"

    name = fields.Char(string="需求主题", required=True)
    lead_id = fields.Many2one("crm.lead", string="客户/线索", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("psc.publishing.project", string="市场运营项目", required=True)
    track_id = fields.Many2one(related="project_id.track_id", string="经营赛道", store=True, readonly=True)
    product_ids = fields.Many2many("product.template", string="感兴趣产品")
    organization_type = fields.Char(string="机构类型")
    contact_role = fields.Char(string="联系人角色")
    requirement_details = fields.Text(string="行业需求详情")
    quantity = fields.Float(string="预计数量")
    budget = fields.Monetary(string="预算", currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    certification_requirements = fields.Text(string="认证/合规要求")
    delivery_country_id = fields.Many2one("res.country", string="交付国家")
    delivery_port = fields.Char(string="交付港口/地点")
    target_purchase_date = fields.Date(string="预计采购日期")
    stage = fields.Selection([
        ("new", "新需求"), ("qualified", "已确认"), ("quoted", "已报价"),
        ("sample", "样品中"), ("negotiation", "谈判中"),
        ("won", "已成交"), ("lost", "未成交"),
    ], string="采购阶段", default="new", required=True)
    lost_reason = fields.Text(string="未成交原因")


class PerformanceSnapshot(models.Model):
    _name = "psc.performance.snapshot"
    _description = "渠道经营数据快照"
    _order = "snapshot_date desc, id desc"

    snapshot_date = fields.Date(string="数据日期", required=True, default=fields.Date.context_today, index=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    destination_id = fields.Many2one("psc.publishing.destination", string="发布目标")
    cluster_id = fields.Many2one("psc.social.account.cluster", string="账号集群")
    account_id = fields.Many2one("psc.social.publishing.account", string="平台账号")
    content_id = fields.Many2one("psc.content.variant", string="内容")
    product_id = fields.Many2one("product.template", string="产品")
    impressions = fields.Integer(string="曝光")
    views = fields.Integer(string="播放/浏览")
    clicks = fields.Integer(string="点击")
    inquiries = fields.Integer(string="询盘")
    qualified_leads = fields.Integer(string="有效客户")
    quotations = fields.Integer(string="报价")
    orders = fields.Integer(string="订单")
    currency_id = fields.Many2one("res.currency", related="project_id.company_id.currency_id", readonly=True)
    revenue = fields.Monetary(string="销售额", currency_field="currency_id")
    purchase_cost = fields.Monetary(string="采购成本", currency_field="currency_id")
    traffic_cost = fields.Monetary(string="流量成本", currency_field="currency_id")
    notes = fields.Text(string="数据说明")


class OptimizationAction(models.Model):
    _name = "psc.optimization.action"
    _description = "经营优化任务"
    _order = "priority, due_date, id desc"

    name = fields.Char(string="优化任务", required=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    category = fields.Selection([
        ("market", "市场需求"), ("product", "产品"), ("content", "内容"),
        ("channel", "渠道/账号"), ("customer", "客户转化"),
        ("supplier", "供应与采购"),
    ], string="优化类型", required=True, default="content")
    priority = fields.Selection([
        ("1", "紧急"), ("2", "高"), ("3", "普通"), ("4", "低"),
    ], default="3", required=True)
    evidence = fields.Text(string="数据依据", required=True)
    proposed_action = fields.Text(string="建议动作", required=True)
    owner_id = fields.Many2one("res.users", string="负责人", default=lambda self: self.env.user)
    due_date = fields.Date(string="计划完成日期")
    state = fields.Selection([
        ("draft", "待评估"), ("approved", "已批准"), ("doing", "执行中"),
        ("done", "已完成"), ("rejected", "不执行"),
    ], string="状态", default="draft", required=True)
    result = fields.Text(string="执行结果")

    def action_approve(self):
        self.write({"state": "approved"})
        return True

    def action_start(self):
        self.write({"state": "doing"})
        return True

    def action_done(self):
        self.write({"state": "done"})
        return True


class ProjectReadinessItem(models.Model):
    _name = "psc.project.readiness.item"
    _description = "项目上线准备项"
    _order = "due_date, sequence, id"

    name = fields.Char(string="准备事项", required=True)
    template_key = fields.Char(string="模板键", required=True, index=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    sequence = fields.Integer(default=10)
    category = fields.Selection([
        ("strategy", "定位与市场"), ("product", "产品与供应"),
        ("compliance", "合规与知识产权"), ("commercial", "交易与交付"),
        ("content", "英文内容与素材"), ("channel", "渠道与数据"),
        ("operations", "CRM与运营演练"),
    ], string="阶段", required=True, default="strategy", index=True)
    weight = fields.Float(string="进度权重 %", required=True, default=1.0)
    hard_gate = fields.Boolean(string="上线硬门槛")
    responsibility = fields.Selection([
        ("ai", "ChatGPT主办"), ("user", "本人配置"), ("joint", "共同完成"),
    ], string="责任归属", required=True, default="joint", index=True)
    owner_id = fields.Many2one(
        "res.users", string="Odoo负责人", required=True, default=lambda self: self.env.user,
    )
    due_date = fields.Date(string="计划完成日期", index=True)
    state = fields.Selection([
        ("todo", "待开始"), ("doing", "进行中"),
        ("blocked", "阻塞"), ("done", "已完成"),
    ], string="状态", required=True, default="todo", index=True)
    description = fields.Text(string="完成标准")
    evidence = fields.Text(string="完成依据")
    block_reason = fields.Text(string="阻塞原因")
    completed_at = fields.Datetime(string="完成时间", readonly=True)

    _project_template_unique = models.Constraint(
        "UNIQUE(project_id, template_key)", "同一项目不能重复创建相同的准备事项。",
    )

    @api.constrains("weight")
    def _check_weight(self):
        for item in self:
            if not 0.0 < item.weight <= 100.0:
                raise ValidationError(_("准备事项权重必须大于0且不超过100。"))

    def action_start(self):
        self.write({"state": "doing", "block_reason": False, "completed_at": False})
        return True

    def action_block(self):
        for item in self:
            if not item.block_reason:
                raise UserError(_("请先填写阻塞原因。"))
        self.write({"state": "blocked", "completed_at": False})
        return True

    def action_done(self):
        for item in self:
            if item.hard_gate and not item.evidence:
                raise UserError(_("上线硬门槛必须填写真实完成依据。"))
        self.write({
            "state": "done", "block_reason": False,
            "completed_at": fields.Datetime.now(),
        })
        return True

    def action_reopen(self):
        self.write({"state": "todo", "completed_at": False})
        return True


class PublishingProjectOperations(models.Model):
    _inherit = "psc.publishing.project"

    track_id = fields.Many2one("psc.industry.track", string="经营赛道", tracking=True)
    business_role_id = fields.Many2one("psc.business.role", string="主要经营角色", tracking=True)
    capability_ids = fields.Many2many(
        "psc.business.capability", "psc_project_capability_rel", "project_id", "capability_id",
        string="经营能力",
    )
    operation_state = fields.Selection([
        ("planning", "筹备"), ("active", "运营中"),
        ("paused", "暂停"), ("closed", "已结束"),
    ], string="运营状态", default="planning", required=True, tracking=True)
    business_goal = fields.Text(string="项目经营目标", translate=True)
    project_product_ids = fields.One2many("psc.project.product", "project_id", string="项目产品池")
    content_plan_ids = fields.One2many("psc.content.plan", "project_id", string="内容计划")
    account_cluster_ids = fields.Many2many(
        "psc.social.account.cluster", "psc_project_account_cluster_rel", "project_id", "cluster_id",
        string="账号集群",
    )
    lead_ids = fields.One2many("crm.lead", "psc_project_id", string="客户与线索")
    performance_snapshot_ids = fields.One2many(
        "psc.performance.snapshot", "project_id", string="经营数据",
    )
    optimization_action_ids = fields.One2many(
        "psc.optimization.action", "project_id", string="优化任务",
    )
    readiness_item_ids = fields.One2many(
        "psc.project.readiness.item", "project_id", string="上线准备清单",
    )
    readiness_progress = fields.Float(
        string="上线准备进度 %", compute="_compute_readiness", store=True,
    )
    readiness_total_count = fields.Integer(
        string="准备项总数", compute="_compute_readiness", store=True,
    )
    readiness_done_count = fields.Integer(
        string="已完成", compute="_compute_readiness", store=True,
    )
    readiness_blocked_count = fields.Integer(
        string="阻塞项", compute="_compute_readiness", store=True,
    )
    readiness_overdue_count = fields.Integer(string="逾期项", compute="_compute_readiness")
    launch_ready = fields.Boolean(
        string="允许上线", compute="_compute_readiness", store=True,
    )
    readiness_blocker_summary = fields.Text(
        string="上线阻塞摘要", compute="_compute_readiness",
    )

    @api.depends(
        "readiness_item_ids.state", "readiness_item_ids.weight",
        "readiness_item_ids.hard_gate", "readiness_item_ids.due_date",
    )
    def _compute_readiness(self):
        today = fields.Date.context_today(self)
        for project in self:
            items = project.readiness_item_ids
            done = items.filtered(lambda item: item.state == "done")
            blocked = items.filtered(lambda item: item.state == "blocked")
            overdue = items.filtered(
                lambda item: item.state != "done" and item.due_date and item.due_date < today
            )
            total_weight = sum(items.mapped("weight"))
            progress = 100.0 * sum(done.mapped("weight")) / total_weight if total_weight else 0.0
            incomplete_hard_gates = items.filtered(
                lambda item: item.hard_gate and item.state != "done"
            )
            project.readiness_progress = progress
            project.readiness_total_count = len(items)
            project.readiness_done_count = len(done)
            project.readiness_blocked_count = len(blocked)
            project.readiness_overdue_count = len(overdue)
            project.launch_ready = bool(items) and progress >= 100.0 and not incomplete_hard_gates
            blockers = blocked or incomplete_hard_gates[:5]
            project.readiness_blocker_summary = "\n".join(
                "%s：%s" % (item.name, item.block_reason or _("尚未完成"))
                for item in blockers[:5]
            )

    def _check_readiness_before_launch(self):
        for project in self:
            if project.readiness_item_ids and not project.launch_ready:
                raise UserError(_(
                    "项目上线准备进度为 %.1f%%，仍有%s个阻塞项和%s个未完成硬门槛。"
                ) % (
                    project.readiness_progress,
                    project.readiness_blocked_count,
                    len(project.readiness_item_ids.filtered(
                        lambda item: item.hard_gate and item.state != "done"
                    )),
                ))
        return True

    def _check_products_before_launch(self):
        for project in self.filtered("readiness_item_ids"):
            if not project.project_product_ids:
                raise UserError(_("至少需要一个已核实并批准运营的项目产品。"))
            invalid_products = project.project_product_ids.filtered(
                lambda item: item.status != "active"
                or item.compliance_state != "passed"
                or item.material_state != "complete"
                or not item.hard_gate_passed
            )
            if invalid_products:
                raise UserError(_("以下产品尚未通过全部上线门槛：%s") % ", ".join(
                    invalid_products.mapped("name")
                ))
        return True

    def action_open_readiness_items(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "product_social_content_bridge.action_psc_project_readiness_items"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {
            "default_project_id": self.id,
            "search_default_my_work": 1,
        }
        return action

    def ensure_footwear_sourcing_readiness(self):
        item_model = self.env["psc.project.readiness.item"]
        today = fields.Date.context_today(self)
        for project in self:
            existing_keys = set(project.readiness_item_ids.mapped("template_key"))
            values_list = []
            for key, sequence, category, name, weight, hard_gate, responsibility, due_days, description in FOOTWEAR_SOURCING_READINESS_TEMPLATE:
                if key in existing_keys:
                    continue
                values_list.append({
                    "project_id": project.id,
                    "template_key": key,
                    "sequence": sequence,
                    "category": category,
                    "name": name,
                    "weight": weight,
                    "hard_gate": hard_gate,
                    "responsibility": responsibility,
                    "owner_id": project.user_id.id or self.env.user.id,
                    "due_date": today + relativedelta(days=due_days),
                    "description": description,
                })
            if values_list:
                item_model.create(values_list)
        return True

    @api.onchange("track_id")
    def _onchange_track_id(self):
        for project in self:
            if project.track_id and not project.content_brief:
                project.content_brief = project.track_id.compliance_notes

    @api.onchange("business_role_id")
    def _onchange_business_role_id(self):
        for project in self:
            if project.business_role_id:
                project.capability_ids = project.business_role_id.capability_ids

    def action_activate_operation(self):
        for project in self:
            if not project.track_id or not project.business_role_id or not project.market_ids:
                raise UserError(_("请先配置经营赛道、主要角色和目标市场。"))
            project._check_readiness_before_launch()
            project._check_products_before_launch()
            project.operation_state = "active"
        return True

    def action_mark_ready(self):
        self._check_readiness_before_launch()
        self._check_products_before_launch()
        return super().action_mark_ready()

    def action_create_publication_tasks(self):
        self._check_readiness_before_launch()
        self._check_products_before_launch()
        return super().action_create_publication_tasks()

    def action_sync_product_pool(self):
        pool_model = self.env["psc.project.product"]
        for project in self:
            existing = project.project_product_ids.mapped("product_id")
            for product in project.product_ids - existing:
                pool_model.create({
                    "project_id": project.id, "product_id": product.id, "source": "odoo",
                    "market_ids": [(6, 0, project.market_ids.ids)],
                })
        return True


class ContentVariantOperations(models.Model):
    _inherit = "psc.content.variant"

    plan_id = fields.Many2one("psc.content.plan", string="内容计划", ondelete="set null", index=True)
    pillar_id = fields.Many2one("psc.content.pillar", string="内容栏目")


class SocialPublishingAccountCluster(models.Model):
    _inherit = "psc.social.publishing.account"

    cluster_id = fields.Many2one(
        "psc.social.account.cluster", string="账号集群", ondelete="restrict", index=True,
    )

    @api.model
    def _values_from_cluster(self, cluster):
        return {
            "product_line_id": cluster.product_line_id.id,
            "target_market_id": cluster.target_market_id.id,
            "worker_node_id": cluster.worker_node_id.id,
            "bitbrowser_environment_id": cluster.bitbrowser_environment_id.id,
            "expected_ip": cluster.expected_ip,
            "expected_country_id": cluster.expected_country_id.id,
            "expected_timezone": cluster.expected_timezone,
        }

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            cluster = self.env["psc.social.account.cluster"].browse(values.get("cluster_id")).exists()
            if cluster:
                values.update(self._values_from_cluster(cluster))
        return super().create(vals_list)

    def write(self, values):
        if "cluster_id" in values:
            cluster = self.env["psc.social.account.cluster"].browse(values.get("cluster_id")).exists()
            if cluster:
                values = dict(values, **self._values_from_cluster(cluster))
        return super().write(values)

    @api.onchange("cluster_id")
    def _onchange_cluster_id(self):
        for account in self:
            if account.cluster_id:
                cluster = account.cluster_id
                account.product_line_id = cluster.product_line_id
                account.target_market_id = cluster.target_market_id
                account.worker_node_id = cluster.worker_node_id
                account.bitbrowser_environment_id = cluster.bitbrowser_environment_id
                account.expected_ip = cluster.expected_ip
                account.expected_country_id = cluster.expected_country_id
                account.expected_timezone = cluster.expected_timezone

    @api.constrains(
        "cluster_id", "worker_node_id", "bitbrowser_environment_id", "expected_ip",
        "expected_country_id", "expected_timezone", "target_market_id",
    )
    def _check_cluster_environment(self):
        for account in self.filtered("cluster_id"):
            cluster = account.cluster_id
            if (
                account.worker_node_id != cluster.worker_node_id
                or account.bitbrowser_environment_id != cluster.bitbrowser_environment_id
                or account.expected_ip != cluster.expected_ip
                or account.expected_country_id != cluster.expected_country_id
                or account.expected_timezone != cluster.expected_timezone
                or account.target_market_id != cluster.target_market_id
            ):
                raise ValidationError(_("平台账号的环境、IP、国家、时区和市场必须与账号集群一致。"))


class CrmLeadOperations(models.Model):
    _inherit = "crm.lead"

    psc_touchpoint_ids = fields.One2many("psc.customer.touchpoint", "lead_id", string="来源触点")
    psc_first_touchpoint_id = fields.Many2one(
        "psc.customer.touchpoint", string="首次来源", compute="_compute_psc_touchpoints", store=True,
    )
    psc_last_touchpoint_id = fields.Many2one(
        "psc.customer.touchpoint", string="最近来源", compute="_compute_psc_touchpoints", store=True,
    )
    psc_requirement_ids = fields.One2many("psc.customer.requirement", "lead_id", string="行业需求")

    @api.depends("psc_touchpoint_ids.occurred_at", "psc_touchpoint_ids.verified")
    def _compute_psc_touchpoints(self):
        for lead in self:
            verified = lead.psc_touchpoint_ids.filtered("verified").sorted(
                key=lambda item: (item.occurred_at, item.id)
            )
            touches = verified or lead.psc_touchpoint_ids.sorted(
                key=lambda item: (item.occurred_at, item.id)
            )
            lead.psc_first_touchpoint_id = touches[:1]
            lead.psc_last_touchpoint_id = touches[-1:] if touches else False


class SocialRegistrationTaskCluster(models.Model):
    _inherit = "psc.social.registration.task"

    cluster_id = fields.Many2one(
        "psc.social.account.cluster", string="账号集群", ondelete="restrict", index=True,
    )

    @api.onchange("cluster_id")
    def _onchange_cluster_id(self):
        for task in self:
            if task.cluster_id:
                cluster = task.cluster_id
                task.worker_node_id = cluster.worker_node_id
                task.bitbrowser_environment_id = cluster.bitbrowser_environment_id
                task.expected_ip = cluster.expected_ip
                task.expected_country_id = cluster.expected_country_id
                task.expected_timezone = cluster.expected_timezone

    @api.constrains(
        "cluster_id", "worker_node_id", "bitbrowser_environment_id", "expected_ip",
        "expected_country_id", "expected_timezone",
    )
    def _check_cluster_environment(self):
        for task in self.filtered("cluster_id"):
            cluster = task.cluster_id
            if (
                task.worker_node_id != cluster.worker_node_id
                or task.bitbrowser_environment_id != cluster.bitbrowser_environment_id
                or task.expected_ip != cluster.expected_ip
                or task.expected_country_id != cluster.expected_country_id
                or task.expected_timezone != cluster.expected_timezone
            ):
                raise ValidationError(_("注册任务的环境、IP、国家和时区必须与账号集群一致。"))
