import hashlib
import hmac
import json
import secrets
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


ACTION_TOKEN_TTL_MINUTES = 30
SAFE_RETRY_FAILURE_CLASSES = {"network", "timeout", "temporary"}


def _json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(_("JSON 数据格式不正确。")) from error
    if not isinstance(parsed, dict):
        raise ValidationError(_("JSON 数据必须是对象。"))
    return parsed


class ProjectBlueprint(models.Model):
    _name = "psc.project.blueprint"
    _description = "运营项目蓝图"
    _order = "sequence, name"

    name = fields.Char(string="蓝图名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    version = fields.Integer(string="版本", default=1, required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="公司", required=True, default=lambda self: self.env.company,
    )
    track_id = fields.Many2one("psc.industry.track", string="经营赛道", required=True)
    business_role_id = fields.Many2one("psc.business.role", string="经营角色", required=True)
    business_goal = fields.Text(string="经营目标模板", required=True, translate=True)
    customer_profile = fields.Text(string="客户画像", translate=True)
    compliance_notes = fields.Text(string="合规检查", translate=True)
    default_kpis = fields.Text(string="默认指标", translate=True)
    content_brief = fields.Text(string="默认内容要求", translate=True)

    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)", "同一公司的运营项目蓝图代码不能重复。",
    )

    def _project_values(self, values):
        self.ensure_one()
        product_line = self.env["psc.product.line"].browse(values.get("product_line_id")).exists()
        products = self.env["product.template"].browse(values.get("product_ids", [])).exists()
        markets = self.env["psc.target.market"].browse(values.get("market_ids", [])).exists()
        channels = self.env["psc.publishing.channel"].browse(values.get("channel_ids", [])).exists()
        if not product_line or not products or not markets or not channels:
            raise ValidationError(_("创建项目需要产品线、至少一个产品、市场和渠道。"))
        if self.company_id not in self.env.companies:
            raise AccessError(_("当前用户无权使用该公司蓝图。"))
        return {
            "name": (values.get("name") or "").strip(),
            "company_id": self.company_id.id,
            "blueprint_id": self.id,
            "blueprint_version": self.version,
            "track_id": self.track_id.id,
            "business_role_id": self.business_role_id.id,
            "capability_ids": [(6, 0, self.business_role_id.capability_ids.ids)],
            "product_line_id": product_line.id,
            "product_ids": [(6, 0, products.ids)],
            "market_ids": [(6, 0, markets.ids)],
            "channel_ids": [(6, 0, channels.ids)],
            "business_goal": values.get("business_goal") or self.business_goal,
            "content_brief": values.get("content_brief") or self.content_brief,
        }

    def create_project(self, values):
        project_values = self._project_values(values)
        if not project_values["name"]:
            raise ValidationError(_("项目名称不能为空。"))
        project = self.env["psc.publishing.project"].create(project_values)
        project.action_sync_product_pool()
        plan_model = self.env["psc.content.plan"]
        for market in project.market_ids:
            for channel in project.channel_ids:
                for pillar in self.track_id.content_pillar_ids.filtered("active"):
                    if pillar.role_ids and self.business_role_id not in pillar.role_ids:
                        continue
                    plan_model.create({
                        "name": "%s · %s" % (pillar.name, market.name),
                        "project_id": project.id,
                        "pillar_id": pillar.id,
                        "product_id": project.product_ids[:1].id,
                        "market_id": market.id,
                        "channel_id": channel.id,
                        "brief": pillar.instructions or self.content_brief or "",
                    })
        return project


class ProjectLaunchWizard(models.TransientModel):
    _name = "psc.project.launch.wizard"
    _description = "创建运营项目"

    blueprint_id = fields.Many2one("psc.project.blueprint", string="项目蓝图", required=True)
    name = fields.Char(string="项目名称", required=True)
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线", required=True)
    product_ids = fields.Many2many("product.template", string="首批产品", required=True)
    market_ids = fields.Many2many("psc.target.market", string="目标市场", required=True)
    channel_ids = fields.Many2many("psc.publishing.channel", string="运营渠道", required=True)
    business_goal = fields.Text(string="经营目标")
    content_brief = fields.Text(string="内容要求")

    @api.onchange("blueprint_id")
    def _onchange_blueprint_id(self):
        if self.blueprint_id:
            self.business_goal = self.blueprint_id.business_goal
            self.content_brief = self.blueprint_id.content_brief

    @api.onchange("product_line_id")
    def _onchange_product_line_id(self):
        if self.product_line_id and not self.product_ids:
            self.product_ids = self.product_line_id.product_ids

    def action_create_project(self):
        self.ensure_one()
        project = self.blueprint_id.create_project({
            "name": self.name,
            "product_line_id": self.product_line_id.id,
            "product_ids": self.product_ids.ids,
            "market_ids": self.market_ids.ids,
            "channel_ids": self.channel_ids.ids,
            "business_goal": self.business_goal,
            "content_brief": self.content_brief,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "psc.publishing.project",
            "res_id": project.id,
            "view_mode": "form",
            "target": "current",
        }


class AiRun(models.Model):
    _name = "psc.ai.run"
    _description = "AI运行记录"
    _order = "create_date desc, id desc"

    name = fields.Char(string="任务", required=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True,
    )
    user_id = fields.Many2one(
        "res.users", string="操作人", required=True, default=lambda self: self.env.user, index=True,
    )
    project_id = fields.Many2one("psc.publishing.project", string="项目", index=True)
    intent = fields.Char(string="用户意图", required=True)
    source = fields.Selection([
        ("chatgpt", "ChatGPT"), ("odoo", "Odoo"), ("scheduled", "计划任务"),
    ], default="chatgpt", required=True)
    state = fields.Selection([
        ("running", "执行中"), ("done", "完成"), ("partial", "部分完成"), ("failed", "失败"),
    ], default="running", required=True, index=True)
    started_at = fields.Datetime(default=fields.Datetime.now, required=True)
    finished_at = fields.Datetime()
    input_summary = fields.Text(string="输入摘要")
    result_summary = fields.Text(string="结果摘要")
    related_records_json = fields.Text(string="涉及记录")
    action_ids = fields.One2many("psc.ai.action", "run_id", string="行动卡")

    def action_finish(self, state="done", summary=None):
        if state not in ("done", "partial", "failed"):
            raise ValidationError(_("AI运行结束状态无效。"))
        self.write({
            "state": state,
            "finished_at": fields.Datetime.now(),
            "result_summary": summary or self.result_summary,
        })
        return True


class AiAction(models.Model):
    _name = "psc.ai.action"
    _description = "AI行动卡"
    _order = "priority, create_date desc, id desc"

    name = fields.Char(string="行动标题", required=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True,
    )
    run_id = fields.Many2one("psc.ai.run", string="AI运行", ondelete="set null", index=True)
    project_id = fields.Many2one("psc.publishing.project", string="项目", index=True)
    action_type = fields.Selection([
        ("launch_project", "创建运营项目"),
        ("create_content_plan", "创建内容计划"),
        ("create_content_draft", "创建内容草稿"),
        ("create_lead_followup", "创建客户跟进"),
        ("create_project_task", "创建运营任务"),
        ("create_optimization", "创建优化实验"),
        ("close_optimization", "完成优化复盘"),
        ("retry_publication", "重试发布任务"),
        ("record_feedback", "记录AI建议反馈"),
        ("initialize_medical_test_data", "初始化医疗测试数据"),
        ("complete_medical_test_scenario", "补齐医疗全业务测试场景"),
        ("cleanup_medical_test_data", "清理医疗测试数据"),
    ], string="动作类型", required=True, index=True)
    priority = fields.Selection([
        ("0", "P0"), ("1", "P1"), ("2", "P2"), ("3", "P3"),
    ], default="2", required=True)
    reason = fields.Text(string="建议原因", required=True)
    evidence_json = fields.Text(string="事实依据")
    risk_level = fields.Selection([
        ("low", "低"), ("medium", "中"), ("high", "高"),
    ], default="medium", required=True)
    estimated_impact = fields.Char(string="预计影响")
    payload_json = fields.Text(string="执行参数", required=True)
    preview_json = fields.Text(string="变更预览", required=True)
    precondition_json = fields.Text(string="目标版本快照", readonly=True)
    state = fields.Selection([
        ("waiting_approval", "待批准"), ("approved", "已批准"),
        ("executing", "执行中"), ("done", "完成"),
        ("rejected", "拒绝"), ("expired", "已过期"), ("failed", "失败"),
    ], default="waiting_approval", required=True, index=True)
    token_digest = fields.Char(readonly=True, copy=False)
    token_expires_at = fields.Datetime(readonly=True, copy=False)
    idempotency_key = fields.Char(index=True, copy=False)
    approved_by_id = fields.Many2one("res.users", string="批准人", readonly=True)
    approved_at = fields.Datetime(readonly=True)
    executed_at = fields.Datetime(readonly=True)
    result_json = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    execution_ids = fields.One2many("psc.ai.execution", "action_id", string="执行记录")
    feedback_ids = fields.One2many("psc.ai.feedback", "action_id", string="用户反馈")

    _idempotency_company_unique = models.Constraint(
        "UNIQUE(idempotency_key, company_id)", "同一幂等键不能重复执行。",
    )

    @api.model
    def _signing_secret(self):
        parameters = self.env["ir.config_parameter"].sudo()
        secret = parameters.get_param("psc.ai_action_signing_secret")
        if not secret:
            secret = secrets.token_urlsafe(48)
            parameters.set_param("psc.ai_action_signing_secret", secret)
        return secret.encode()

    def _issue_token(self):
        self.ensure_one()
        expires_at = fields.Datetime.now() + relativedelta(minutes=ACTION_TOKEN_TTL_MINUTES)
        nonce = secrets.token_urlsafe(24)
        expires = int((expires_at - datetime(1970, 1, 1)).total_seconds())
        message = "%s:%s:%s" % (self.id, nonce, expires)
        signature = hmac.new(self._signing_secret(), message.encode(), hashlib.sha256).hexdigest()
        token = "%s.%s.%s.%s" % (self.id, expires, nonce, signature)
        self.write({
            "token_digest": hashlib.sha256(token.encode()).hexdigest(),
            "token_expires_at": expires_at,
        })
        return token

    @api.model
    def _action_from_token(self, token):
        try:
            action_id, expires_text, nonce, signature = (token or "").split(".", 3)
            action_id = int(action_id)
            expires = int(expires_text)
        except (AttributeError, TypeError, ValueError) as error:
            raise AccessError(_("行动确认令牌无效。")) from error
        action = self.search([("id", "=", action_id)], limit=1)
        if not action:
            raise AccessError(_("行动卡不存在。"))
        message = "%s:%s:%s" % (action.id, nonce, expires)
        expected = hmac.new(action._signing_secret(), message.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise AccessError(_("行动确认令牌签名无效。"))
        if action.token_digest != hashlib.sha256(token.encode()).hexdigest():
            raise AccessError(_("行动确认令牌已被替换。"))
        # A completed action remains safely replayable with the same idempotency
        # key even after the short-lived approval token expires.
        if action.state != "done" and fields.Datetime.now() > datetime.utcfromtimestamp(expires):
            action.state = "expired"
            raise UserError(_("行动确认令牌已过期，请重新生成预览。"))
        return action

    def action_reject(self):
        self.filtered(lambda action: action.state == "waiting_approval").write({"state": "rejected"})
        return True

    def action_approve(self):
        self.filtered(lambda action: action.state == "waiting_approval").write({
            "state": "approved", "approved_by_id": self.env.user.id,
            "approved_at": fields.Datetime.now(),
        })
        return True

    def _validate_preconditions(self):
        self.ensure_one()
        preconditions = _json_loads(self.precondition_json).get("records", [])
        allowed_models = {
            "psc.publishing.project", "psc.project.product", "psc.content.plan",
            "psc.content.pillar", "psc.target.market", "psc.publishing.channel",
            "crm.lead", "psc.optimization.action", "psc.publication.task", "psc.ai.action",
            "product.template", "psc.product.line", "psc.project.blueprint",
            "psc.local.worker.node", "psc.bitbrowser.environment",
        }
        for item in preconditions:
            model_name = item.get("model")
            if model_name not in allowed_models:
                raise AccessError(_("行动包含不允许的目标模型。"))
            record = self.env[model_name].search([("id", "=", item.get("id"))], limit=1)
            current_version = fields.Datetime.to_string(record.write_date) if record else None
            if current_version != item.get("write_date"):
                raise UserError(_("行动目标在预览后已发生变化，请重新生成行动预览。"))
        return True

    def _execute_payload(self):
        self.ensure_one()
        values = _json_loads(self.payload_json)
        if self.action_type == "launch_project":
            blueprint = self.env["psc.project.blueprint"].browse(values.get("blueprint_id")).exists()
            if not blueprint:
                raise ValidationError(_("项目蓝图不存在。"))
            record = blueprint.create_project(values)
        elif self.action_type == "create_content_plan":
            project = self.env["psc.publishing.project"].browse(values.get("project_id")).exists()
            pillar = self.env["psc.content.pillar"].browse(values.get("pillar_id")).exists()
            market = self.env["psc.target.market"].browse(values.get("market_id")).exists()
            channel = self.env["psc.publishing.channel"].browse(values.get("channel_id")).exists()
            if not all((project, pillar, market, channel)):
                raise ValidationError(_("内容计划关联的项目、栏目、市场或渠道不存在。"))
            if pillar.track_id != project.track_id or market not in project.market_ids or channel not in project.channel_ids:
                raise ValidationError(_("内容计划不符合项目的赛道、市场或渠道范围。"))
            record = self.env["psc.content.plan"].create({
                "name": values.get("name") or pillar.name,
                "project_id": project.id,
                "pillar_id": pillar.id,
                "product_id": values.get("product_id") or False,
                "market_id": market.id,
                "channel_id": channel.id,
                "scheduled_at": values.get("scheduled_at") or False,
                "brief": values.get("brief") or "",
            })
        elif self.action_type == "create_content_draft":
            plan = self.env["psc.content.plan"].browse(values.get("plan_id")).exists()
            if not plan or plan.state in ("published", "cancelled") or plan.content_id:
                raise ValidationError(_("内容计划不存在、已关闭或已经生成草稿。"))
            product = self.env["product.template"].browse(values.get("product_id") or plan.product_id.id).exists()
            project_product = self.env["psc.project.product"].search([
                ("project_id", "=", plan.project_id.id), ("product_id", "=", product.id),
            ], limit=1)
            if (
                not product or not project_product or project_product.status != "active"
                or project_product.compliance_state != "passed"
                or project_product.material_state != "complete"
                or not project_product.hard_gate_passed
            ):
                raise UserError(_("产品尚未通过可运营、资料、合规和硬性门槛，不能创建对外内容。"))
            record = self.env["psc.content.variant"].create({
                "project_id": plan.project_id.id,
                "plan_id": plan.id,
                "pillar_id": plan.pillar_id.id,
                "product_id": product.id,
                "market_id": plan.market_id.id,
                "channel_id": plan.channel_id.id,
                "language_id": plan.market_id.lang_id.id,
                "title": values.get("title") or plan.name,
                "caption": values.get("caption") or "",
                "hashtags": values.get("hashtags") or "",
                "seo_keywords": values.get("seo_keywords") or "",
                "video_script": values.get("video_script") or "",
                "image_prompt": values.get("image_prompt") or "",
                "state": "draft",
                "ai_state": "done",
                "ai_model": "ChatGPT MCP",
                "ai_generated_at": fields.Datetime.now(),
            })
            plan.write({"content_id": record.id, "state": "prepared"})
        elif self.action_type == "create_lead_followup":
            lead = self.env["crm.lead"].browse(values.get("lead_id")).exists()
            activity_type = self.env["mail.activity.type"].browse(values.get("activity_type_id")).exists()
            if not lead or not activity_type:
                raise ValidationError(_("客户或活动类型不存在。"))
            record = self.env["mail.activity"].create({
                "res_model_id": self.env["ir.model"]._get_id("crm.lead"),
                "res_id": lead.id,
                "activity_type_id": activity_type.id,
                "summary": values.get("summary") or _("AI建议跟进"),
                "note": values.get("note") or "",
                "date_deadline": values.get("date_deadline") or fields.Date.context_today(self),
                "user_id": values.get("user_id") or lead.user_id.id or self.env.user.id,
            })
        elif self.action_type == "create_project_task":
            project = self.env["psc.publishing.project"].browse(values.get("project_id")).exists()
            activity_type = self.env["mail.activity.type"].browse(values.get("activity_type_id")).exists()
            if not project or not activity_type:
                raise ValidationError(_("运营项目或活动类型不存在。"))
            record = self.env["mail.activity"].create({
                "res_model_id": self.env["ir.model"]._get_id("psc.publishing.project"),
                "res_id": project.id,
                "activity_type_id": activity_type.id,
                "summary": values.get("summary") or self.name,
                "note": values.get("note") or self.reason,
                "date_deadline": values.get("date_deadline") or fields.Date.context_today(self),
                "user_id": values.get("user_id") or project.user_id.id or self.env.user.id,
            })
        elif self.action_type == "create_optimization":
            project = self.env["psc.publishing.project"].browse(values.get("project_id")).exists()
            if not project:
                raise ValidationError(_("运营项目不存在。"))
            record = self.env["psc.optimization.action"].create({
                "name": values.get("name") or self.name,
                "project_id": project.id,
                "category": values.get("category") or "content",
                "priority": values.get("priority") or "3",
                "evidence": values.get("evidence") or self.reason,
                "proposed_action": values.get("proposed_action") or self.name,
                "owner_id": values.get("owner_id") or self.env.user.id,
                "due_date": values.get("due_date") or False,
                "target_metric": values.get("target_metric") or "",
                "baseline_value": values.get("baseline_value") or 0.0,
                "target_value": values.get("target_value") or 0.0,
                "observation_days": values.get("observation_days") or 14,
                "success_criteria": values.get("success_criteria") or "",
                "rollback_criteria": values.get("rollback_criteria") or "",
            })
        elif self.action_type == "close_optimization":
            record = self.env["psc.optimization.action"].browse(values.get("optimization_id")).exists()
            if not record:
                raise ValidationError(_("优化实验不存在。"))
            decision = values.get("final_decision")
            if decision not in ("adopt", "iterate", "rollback"):
                raise ValidationError(_("优化实验复盘结论无效。"))
            record.write({
                "actual_value": values.get("actual_value") or 0.0,
                "final_decision": decision,
                "result": values.get("result") or "",
                "state": "done",
            })
        elif self.action_type == "retry_publication":
            task = self.env["psc.publication.task"].browse(values.get("task_id")).exists()
            failure_class = values.get("failure_class")
            if not task or task.state != "failed":
                raise ValidationError(_("发布任务不存在或当前不是失败状态。"))
            if failure_class not in SAFE_RETRY_FAILURE_CLASSES:
                raise UserError(_("只有网络、超时或明确的临时错误可以通过AI批准重试。"))
            task.action_retry()
            record = task
        elif self.action_type == "record_feedback":
            source_action = self.browse(values.get("action_id")).exists()
            decision = values.get("decision")
            if not source_action or decision not in ("accepted", "modified", "rejected"):
                raise ValidationError(_("AI行动或反馈结论无效。"))
            record = self.env["psc.ai.feedback"].create({
                "action_id": source_action.id,
                "decision": decision,
                "reason": values.get("reason") or "",
                "actual_effect": values.get("actual_effect") or "",
            })
        elif self.action_type == "initialize_medical_test_data":
            if values.get("dataset") != "medical_procurement_smoke_v1":
                raise ValidationError(_("不支持的测试数据集。"))
            record = self.env["res.config.settings"].create({})._upsert_medical_test_data()
        elif self.action_type == "complete_medical_test_scenario":
            if values.get("dataset") != "medical_procurement_smoke_v1":
                raise ValidationError(_("不支持的测试数据集。"))
            return self.env["res.config.settings"].create({})._complete_medical_test_scenario(
                worker_node_id=values.get("worker_node_id"),
                environment_id=values.get("environment_id"),
                include_procurement_inventory=bool(values.get("include_procurement_inventory")),
            )
        elif self.action_type == "cleanup_medical_test_data":
            return self.env["res.config.settings"].create({})._cleanup_medical_test_data(
                exclude_action_id=self.id,
            )
        else:
            raise ValidationError(_("不支持的AI动作类型。"))
        return {"model": record._name, "id": record.id, "display_name": record.display_name}

    @api.model
    def commit_token(self, token, idempotency_key):
        if not (idempotency_key or "").strip():
            raise ValidationError(_("执行写操作必须提供幂等键。"))
        action = self._action_from_token(token)
        if action.company_id not in self.env.companies:
            raise AccessError(_("当前用户无权执行该公司的行动。"))
        if action.state == "done":
            if action.idempotency_key != idempotency_key:
                raise ValidationError(_("该行动已经使用其他幂等键执行。"))
            return _json_loads(action.result_json)
        if action.state not in ("waiting_approval", "approved", "failed"):
            raise UserError(_("当前行动状态不能执行。"))
        action._validate_preconditions()
        duplicate = self.search([
            ("company_id", "=", action.company_id.id),
            ("idempotency_key", "=", idempotency_key),
            ("id", "!=", action.id),
        ], limit=1)
        if duplicate:
            raise ValidationError(_("该幂等键已用于其他行动。"))
        action.write({
            "state": "executing", "idempotency_key": idempotency_key,
            "approved_by_id": self.env.user.id,
            "approved_at": action.approved_at or fields.Datetime.now(),
            "error_message": False,
        })
        execution = self.env["psc.ai.execution"].create({
            "action_id": action.id,
            "company_id": action.company_id.id,
            "user_id": self.env.user.id,
            "tool_name": action.action_type,
            "idempotency_key": idempotency_key,
            "input_summary": action.preview_json,
            "state": "running",
            "started_at": fields.Datetime.now(),
        })
        try:
            # Roll back all business-record changes when an action fails while
            # retaining the action and execution audit written outside this savepoint.
            with self.env.cr.savepoint():
                result = action._execute_payload()
        except Exception as error:
            message = str(error)[:4000]
            action.write({"state": "failed", "error_message": message})
            execution.write({
                "state": "failed", "error_message": message,
                "finished_at": fields.Datetime.now(),
            })
            raise
        action.write({
            "state": "done", "executed_at": fields.Datetime.now(),
            "result_json": _json_dumps(result),
        })
        execution.write({
            "state": "done", "result_json": _json_dumps(result),
            "finished_at": fields.Datetime.now(),
        })
        return result


class AiExecution(models.Model):
    _name = "psc.ai.execution"
    _description = "AI执行记录"
    _order = "create_date desc, id desc"

    action_id = fields.Many2one("psc.ai.action", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, index=True)
    tool_name = fields.Char(required=True)
    idempotency_key = fields.Char(required=True, index=True)
    input_summary = fields.Text()
    state = fields.Selection([
        ("running", "执行中"), ("done", "完成"), ("failed", "失败"),
    ], default="running", required=True)
    started_at = fields.Datetime(required=True)
    finished_at = fields.Datetime()
    result_json = fields.Text()
    error_message = fields.Text()

    _idempotency_unique = models.Constraint(
        "UNIQUE(idempotency_key, company_id)", "AI执行幂等键不能重复。",
    )


class AiFeedback(models.Model):
    _name = "psc.ai.feedback"
    _description = "AI建议反馈"
    _order = "create_date desc, id desc"

    action_id = fields.Many2one("psc.ai.action", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="action_id.company_id", store=True, readonly=True)
    user_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, index=True,
    )
    decision = fields.Selection([
        ("accepted", "直接接受"), ("modified", "修改后接受"), ("rejected", "拒绝"),
    ], required=True)
    reason = fields.Text()
    actual_effect = fields.Text(string="实际效果")


class OptimizationActionExperiment(models.Model):
    _inherit = "psc.optimization.action"

    target_metric = fields.Char(string="目标指标")
    baseline_value = fields.Float(string="当前基线")
    target_value = fields.Float(string="目标值")
    observation_days = fields.Integer(string="观察天数", default=14)
    success_criteria = fields.Text(string="成功标准")
    rollback_criteria = fields.Text(string="回退条件")
    actual_value = fields.Float(string="实际结果")
    final_decision = fields.Selection([
        ("pending", "待评估"), ("adopt", "采纳"),
        ("iterate", "继续优化"), ("rollback", "回退"),
    ], default="pending")

    @api.constrains("observation_days")
    def _check_observation_days(self):
        if any(action.observation_days < 1 for action in self):
            raise ValidationError(_("优化实验观察天数必须大于0。"))


class PublishingProjectAi(models.Model):
    _inherit = "psc.publishing.project"

    blueprint_id = fields.Many2one("psc.project.blueprint", string="项目蓝图", readonly=True)
    blueprint_version = fields.Integer(string="蓝图版本", readonly=True)
    ai_run_ids = fields.One2many("psc.ai.run", "project_id", string="AI运行")
    ai_action_ids = fields.One2many("psc.ai.action", "project_id", string="AI行动卡")


class SaleOrderAttribution(models.Model):
    _inherit = "sale.order"

    psc_project_id = fields.Many2one("psc.publishing.project", string="市场运营项目", index=True)
    psc_market_id = fields.Many2one("psc.target.market", string="来源市场")
    psc_channel_id = fields.Many2one("psc.publishing.channel", string="来源渠道")

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            opportunity = self.env["crm.lead"].browse(values.get("opportunity_id")).exists()
            if opportunity:
                values.setdefault("psc_project_id", opportunity.psc_project_id.id)
                values.setdefault("psc_market_id", opportunity.psc_market_id.id)
                values.setdefault("psc_channel_id", opportunity.psc_channel_id.id)
        return super().create(vals_list)

    @api.onchange("opportunity_id")
    def _onchange_opportunity_psc_attribution(self):
        if self.opportunity_id:
            self.psc_project_id = self.opportunity_id.psc_project_id
            self.psc_market_id = self.opportunity_id.psc_market_id
            self.psc_channel_id = self.opportunity_id.psc_channel_id


class AiOperationsService(models.AbstractModel):
    _name = "psc.ai.service"
    _description = "LightLink AI运营服务"

    @api.model
    def _record_ref(self, record):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        return {
            "model": record._name,
            "id": record.id,
            "name": record.display_name,
            "url": "%s/web#id=%s&model=%s&view_type=form" % (base_url, record.id, record._name),
        }

    @api.model
    def _required_record(self, model_name, record_id, label):
        record = self.env[model_name].search([("id", "=", record_id)], limit=1)
        if not record:
            raise ValidationError(_("%s不存在或当前无权访问。") % label)
        return record

    @api.model
    def _action_target_records(self, action_type, payload):
        target_specs = {
            "launch_project": [
                ("psc.project.blueprint", "blueprint_id", "项目蓝图", True),
                ("psc.product.line", "product_line_id", "产品线", True),
                ("product.template", "product_ids", "产品", True),
                ("psc.target.market", "market_ids", "市场", True),
                ("psc.publishing.channel", "channel_ids", "渠道", True),
            ],
            "create_content_plan": [
                ("psc.publishing.project", "project_id", "运营项目", True),
                ("psc.content.pillar", "pillar_id", "内容栏目", True),
                ("psc.target.market", "market_id", "市场", True),
                ("psc.publishing.channel", "channel_id", "渠道", True),
                ("product.template", "product_id", "产品", False),
            ],
            "create_content_draft": [
                ("psc.content.plan", "plan_id", "内容计划", True),
                ("product.template", "product_id", "产品", False),
            ],
            "create_lead_followup": [("crm.lead", "lead_id", "客户", True)],
            "create_project_task": [("psc.publishing.project", "project_id", "运营项目", True)],
            "create_optimization": [("psc.publishing.project", "project_id", "运营项目", True)],
            "close_optimization": [("psc.optimization.action", "optimization_id", "优化实验", True)],
            "retry_publication": [("psc.publication.task", "task_id", "发布任务", True)],
            "record_feedback": [("psc.ai.action", "action_id", "AI行动", True)],
            "complete_medical_test_scenario": [
                ("psc.publishing.project", "project_id", "测试运营项目", True),
                ("psc.bitbrowser.environment", "environment_id", "比特环境", True),
            ],
            "cleanup_medical_test_data": [
                ("psc.publishing.project", "project_id", "测试运营项目", True),
            ],
        }
        records = []
        for model_name, field_name, label, required in target_specs.get(action_type, []):
            record_ids = payload.get(field_name)
            if required and not record_ids:
                raise ValidationError(_("行动参数缺少%s。") % label)
            if not record_ids:
                continue
            if not isinstance(record_ids, list):
                record_ids = [record_ids]
            for record_id in record_ids:
                records.append(self._required_record(model_name, record_id, label))
        if action_type == "create_content_draft":
            plan = next((record for record in records if record._name == "psc.content.plan"), False)
            product = next((record for record in records if record._name == "product.template"), False)
            if plan:
                product = product or plan.product_id
                project_product = self.env["psc.project.product"].search([
                    ("project_id", "=", plan.project_id.id), ("product_id", "=", product.id),
                ], limit=1)
                if project_product:
                    records.append(project_product)
        if action_type == "initialize_medical_test_data":
            if payload.get("dataset") != "medical_procurement_smoke_v1":
                raise ValidationError(_("只能初始化内置的医疗测试数据集。"))
        if action_type == "complete_medical_test_scenario":
            project = next((record for record in records if record._name == "psc.publishing.project"), False)
            worker = self._required_record(
                "psc.local.worker.node", payload.get("worker_node_id"), _("Windows工作节点"),
            )
            environment = next((
                record for record in records if record._name == "psc.bitbrowser.environment"
            ), False)
            if (
                payload.get("dataset") != "medical_procurement_smoke_v1"
                or not project or project.name != "[TEST] 西非医疗类综合采购商运营项目"
                or not environment or environment.worker_node_id != worker or not environment.available
            ):
                raise ValidationError(_("只能补齐内置的医疗测试数据集。"))
        if action_type == "cleanup_medical_test_data":
            project = next((record for record in records if record._name == "psc.publishing.project"), False)
            if not project or project.name != "[TEST] 西非医疗类综合采购商运营项目":
                raise ValidationError(_("只能清理内置的医疗测试数据集。"))
        return records

    @api.model
    def start_ai_run(self, intent, project_id=None, input_summary=None):
        project = self.env["psc.publishing.project"]
        if project_id:
            project = self._required_record("psc.publishing.project", project_id, _("运营项目"))
        run = self.env["psc.ai.run"].create({
            "name": (intent or _("ChatGPT运营任务"))[:200],
            "company_id": (project.company_id or self.env.company).id,
            "project_id": project.id,
            "intent": intent,
            "input_summary": input_summary or "",
        })
        return {"run_id": run.id, "state": run.state, "started_at": fields.Datetime.to_string(run.started_at)}

    @api.model
    def finish_ai_run(self, run_id, state="done", summary=None, related_records=None):
        run = self._required_record("psc.ai.run", run_id, _("AI运行"))
        if run.company_id not in self.env.companies:
            raise AccessError(_("当前用户无权结束该AI运行。"))
        if related_records is not None:
            run.related_records_json = _json_dumps({"records": related_records})
        run.action_finish(state=state, summary=summary)
        return {"run_id": run.id, "state": run.state, "finished_at": fields.Datetime.to_string(run.finished_at)}

    @api.model
    def list_projects(self, limit=50):
        projects = self.env["psc.publishing.project"].search([
            ("company_id", "in", self.env.companies.ids),
        ], order="write_date desc", limit=min(limit, 100))
        return {"projects": [{
            **self._record_ref(project),
            "operation_state": project.operation_state,
            "track": project.track_id.name,
            "business_role": project.business_role_id.name,
            "markets": project.market_ids.mapped("name"),
            "owner": project.user_id.name,
        } for project in projects]}

    @api.model
    def get_daily_operations_snapshot(self, project_id=None, limit=12):
        project_domain = [("company_id", "in", self.env.companies.ids)]
        if project_id:
            project_domain.append(("id", "=", project_id))
        else:
            project_domain.append(("operation_state", "=", "active"))
        projects = self.env["psc.publishing.project"].search(project_domain, limit=100)
        if project_id and not projects:
            raise UserError(_("运营项目不存在或当前无权访问。"))
        project_ids = projects.ids
        product_domain = [("project_id", "in", project_ids)]
        failed_domain = [("project_id", "in", project_ids), ("state", "=", "failed")]
        lead_domain = [("psc_project_id", "in", project_ids), ("active", "=", True)]
        blocked_products = self.env["psc.project.product"].search(
            product_domain + ["|", ("compliance_state", "!=", "passed"), ("material_state", "!=", "complete")],
            order="priority, fit_score desc", limit=limit,
        )
        failed_tasks = self.env["psc.publication.task"].search(failed_domain, order="write_date desc", limit=limit)
        overdue_leads = self.env["crm.lead"].search(
            lead_domain + [("activity_state", "=", "overdue")],
            order="expected_revenue desc", limit=limit,
        )
        opportunity_leads = self.env["crm.lead"].search(
            lead_domain + [("expected_revenue", ">", 0)],
            order="expected_revenue desc", limit=limit,
        )
        waiting_actions = self.env["psc.ai.action"].search([
            ("project_id", "in", project_ids), ("state", "=", "waiting_approval"),
        ], order="priority, create_date desc", limit=limit)
        account_health = self.get_account_environment_health(project_id=project_id, limit=limit)
        return {
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
            "project_count": len(projects),
            "summary": {
                "blocked_products": self.env["psc.project.product"].search_count(product_domain + [
                    "|", ("compliance_state", "!=", "passed"), ("material_state", "!=", "complete"),
                ]),
                "failed_publications": self.env["psc.publication.task"].search_count(failed_domain),
                "overdue_leads": self.env["crm.lead"].search_count(lead_domain + [("activity_state", "=", "overdue")]),
                "active_opportunities": self.env["crm.lead"].search_count(lead_domain),
                "waiting_approvals": self.env["psc.ai.action"].search_count([
                    ("project_id", "in", project_ids), ("state", "=", "waiting_approval"),
                ]),
                "unhealthy_accounts": account_health["summary"]["unhealthy_accounts"],
                "account_setup_required": account_health.get("setup_required", False),
            },
            "blockers": [{
                "kind": "product",
                "title": item.display_name,
                "reason": "；".join(filter(None, [
                    _("合规状态：%s") % item.compliance_state
                    if item.compliance_state != "passed" else None,
                    _("资料状态：%s") % item.material_state
                    if item.material_state != "complete" else None,
                    _("硬性门槛未通过") if not item.hard_gate_passed else None,
                ])),
                "priority": "P0" if item.compliance_state == "blocked" else "P1",
                "evidence": [self._record_ref(item)],
            } for item in blocked_products] + [{
                "kind": "publication",
                "title": task.display_name,
                "reason": task.error_message or task.status_message or _("发布失败"),
                "priority": "P0",
                "evidence": [self._record_ref(task)],
            } for task in failed_tasks] + [{
                "kind": "account_environment",
                "title": item["name"],
                "reason": item["reason"],
                "priority": "P0" if item["state"] in ("failed", "suspended") else "P1",
                "evidence": item["evidence"],
            } for item in account_health["unhealthy"]] + ([{
                "kind": "account_setup",
                "title": _("需要配置发布账号环境"),
                "reason": account_health["setup_reason"],
                "priority": "P1",
                "evidence": [self._record_ref(projects[:1])],
            }] if account_health.get("setup_required") else []),
            "opportunities": [{
                "kind": "lead",
                "title": lead.display_name,
                "expected_revenue": lead.expected_revenue,
                "currency": lead.company_currency.name,
                "overdue": lead.activity_state == "overdue",
                "evidence": [self._record_ref(lead)],
            } for lead in (overdue_leads | opportunity_leads)[:limit]],
            "waiting_approvals": [{
                "id": action.id,
                "title": action.name,
                "priority": "P%s" % action.priority,
                "risk_level": action.risk_level,
                "reason": action.reason,
            } for action in waiting_actions],
        }

    @api.model
    def get_account_environment_health(self, project_id=None, limit=30):
        allowed_projects = self.env["psc.publishing.project"].search([
            ("company_id", "in", self.env.companies.ids),
        ])
        cluster_domain = [("project_ids", "in", allowed_projects.ids)]
        project = self.env["psc.publishing.project"]
        if project_id:
            project = self._required_record("psc.publishing.project", project_id, _("运营项目"))
            if project.company_id not in self.env.companies:
                raise AccessError(_("当前用户无权访问该运营项目。"))
            cluster_domain = [("id", "in", project.account_cluster_ids.ids)]
        clusters = self.env["psc.social.account.cluster"].search(cluster_domain, limit=min(limit, 100))
        rows = []
        for cluster in clusters:
            accounts = cluster.account_ids
            unhealthy_accounts = accounts.filtered(
                lambda account: account.account_state != "available" or account.last_validation_state != "passed"
            )
            healthy = cluster.state == "ready" and not unhealthy_accounts
            reasons = []
            if cluster.state != "ready":
                reasons.append(_("账号集群状态：%s") % cluster.state)
            if unhealthy_accounts:
                reasons.append(_("%s个账号不可用或环境未通过") % len(unhealthy_accounts))
            rows.append({
                **self._record_ref(cluster),
                "state": cluster.state,
                "healthy": healthy,
                "reason": "；".join(reasons) or _("环境与账号可用"),
                "market": cluster.target_market_id.name,
                "expected_country": cluster.expected_country_id.code,
                "expected_timezone": cluster.expected_timezone,
                "last_validation_at": fields.Datetime.to_string(cluster.last_validation_at)
                if cluster.last_validation_at else None,
                "accounts": [{
                    **self._record_ref(account),
                    "channel": account.channel_id.name,
                    "account_state": account.account_state,
                    "validation_state": account.last_validation_state,
                    "last_validation_at": fields.Datetime.to_string(account.last_validation_at)
                    if account.last_validation_at else None,
                } for account in accounts],
                "evidence": [self._record_ref(cluster)],
            })
        unhealthy = [row for row in rows if not row["healthy"]]
        setup_required = bool(project_id and not clusters)
        return {
            "summary": {"clusters": len(rows), "unhealthy_accounts": len(unhealthy)},
            "setup_required": setup_required,
            "setup_reason": _("项目尚未关联账号集群和发布账号；需要用户配置真实平台账号、环境及授权。")
            if setup_required else False,
            "unhealthy": unhealthy,
            "clusters": rows,
        }

    @api.model
    def get_product_market_context(self, project_product_id):
        item = self.env["psc.project.product"].browse(project_product_id).exists()
        if not item or item.project_id.company_id not in self.env.companies:
            raise UserError(_("项目产品不存在或当前无权访问。"))
        return {
            "product": self._record_ref(item.product_id or item.candidate_id),
            "project_product": self._record_ref(item),
            "project": self._record_ref(item.project_id),
            "markets": [self._record_ref(market) for market in item.market_ids],
            "positioning": item.positioning,
            "selling_points": item.selling_points,
            "fit_score": item.fit_score,
            "hard_gate_passed": item.hard_gate_passed,
            "compliance_state": item.compliance_state,
            "material_state": item.material_state,
            "price": {
                "purchase": item.target_purchase_price,
                "sale": item.target_sale_price,
                "currency": item.currency_id.name,
                "moq": item.minimum_order_qty,
                "lead_time_days": item.lead_time_days,
            },
            "attributes": [{
                "name": line.name, "value": line.value, "verified": line.verified,
                "required": line.required_for_publish, "hard_gate": line.hard_gate,
                "evidence": line.evidence,
            } for line in item.attribute_value_ids],
            "scores": [{
                "name": line.name, "score": line.score, "weight": line.weight,
                "hard_gate": line.hard_gate, "gate_passed": line.gate_passed,
                "notes": line.notes,
            } for line in item.score_line_ids],
        }

    @api.model
    def get_content_backlog(self, project_id, limit=30):
        project = self.env["psc.publishing.project"].browse(project_id).exists()
        if not project or project.company_id not in self.env.companies:
            raise UserError(_("运营项目不存在或当前无权访问。"))
        pillars = project.track_id.content_pillar_ids.filtered(
            lambda pillar: pillar.active
            and (not pillar.role_ids or project.business_role_id in pillar.role_ids)
        )
        plans = self.env["psc.content.plan"].search([
            ("project_id", "=", project.id), ("state", "in", ("draft", "prepared", "ready")),
        ], order="scheduled_at, id", limit=min(limit, 100))
        return {
            "project": self._record_ref(project),
            "available": {
                "pillars": [self._record_ref(pillar) for pillar in pillars],
                "products": [self._record_ref(product) for product in project.product_ids],
                "markets": [self._record_ref(market) for market in project.market_ids],
                "channels": [self._record_ref(channel) for channel in project.channel_ids],
            },
            "plans": [{
            **self._record_ref(plan),
            "state": plan.state,
            "pillar": plan.pillar_id.name,
            "product": plan.product_id.display_name,
            "market": plan.market_id.name,
            "channel": plan.channel_id.name,
            "scheduled_at": fields.Datetime.to_string(plan.scheduled_at) if plan.scheduled_at else None,
            "brief": plan.brief,
        } for plan in plans],
        }

    @api.model
    def get_publication_exceptions(self, project_id=None, limit=30):
        domain = [
            ("state", "=", "failed"),
            ("project_id.company_id", "in", self.env.companies.ids),
        ]
        if project_id:
            domain.append(("project_id", "=", project_id))
        tasks = self.env["psc.publication.task"].search(domain, order="write_date desc", limit=min(limit, 100))
        return {"exceptions": [{
            **self._record_ref(task),
            "project": task.project_id.display_name,
            "market": task.market_id.name,
            "channel": task.channel_id.name,
            "account": task.publishing_account_id.username,
            "attempt_count": task.attempt_count,
            "error": task.error_message or task.status_message,
            "retry_requires_approval": True,
        } for task in tasks]}

    @api.model
    def get_priority_leads(self, project_id=None, days=7, limit=20):
        domain = [
            ("active", "=", True),
            ("psc_project_id.company_id", "in", self.env.companies.ids),
        ]
        if project_id:
            domain.append(("psc_project_id", "=", project_id))
        if days:
            domain.append(("write_date", ">=", fields.Datetime.now() - relativedelta(days=min(days, 365))))
        leads = self.env["crm.lead"].search(domain, order="expected_revenue desc, write_date desc", limit=min(limit, 100))
        activity_types = self.env["mail.activity.type"].search([], order="sequence, id", limit=100)
        return {
            "available_activity_types": [self._record_ref(activity_type) for activity_type in activity_types],
            "leads": [{
            **self._record_ref(lead),
            "project": lead.psc_project_id.display_name,
            "country": lead.country_id.name,
            "language": lead.lang_id.name,
            "stage": lead.stage_id.name,
            "expected_revenue": lead.expected_revenue,
            "probability": lead.probability,
            "owner": lead.user_id.name,
            "activity_state": lead.activity_state,
            "next_activity": lead.activity_summary,
            "first_source": lead.psc_first_touchpoint_id.source_type,
            "last_source": lead.psc_last_touchpoint_id.source_type,
            "requirements": [{
                "id": requirement.id, "name": requirement.name,
                "stage": requirement.stage, "quantity": requirement.quantity,
                "budget": requirement.budget, "currency": requirement.currency_id.name,
                "target_purchase_date": fields.Date.to_string(requirement.target_purchase_date)
                if requirement.target_purchase_date else None,
            } for requirement in lead.psc_requirement_ids],
        } for lead in leads],
        }

    @api.model
    def get_campaign_performance(self, project_id, date_from=None, date_to=None):
        project = self.env["psc.publishing.project"].browse(project_id).exists()
        if not project or project.company_id not in self.env.companies:
            raise UserError(_("运营项目不存在或当前无权访问。"))
        domain = [("project_id", "=", project.id)]
        if date_from:
            domain.append(("snapshot_date", ">=", date_from))
        if date_to:
            domain.append(("snapshot_date", "<=", date_to))
        snapshots = self.env["psc.performance.snapshot"].search(domain)
        recent_orders = self.env["sale.order"].search([
            ("psc_project_id", "=", project.id),
        ], order="create_date desc, id desc", limit=20)
        totals = {field: sum(snapshots.mapped(field)) for field in (
            "impressions", "views", "clicks", "inquiries", "qualified_leads",
            "quotations", "orders", "revenue", "purchase_cost", "traffic_cost",
        )}
        totals.update({
            "click_rate": totals["clicks"] / totals["impressions"] if totals["impressions"] else 0.0,
            "inquiry_rate": totals["inquiries"] / totals["clicks"] if totals["clicks"] else 0.0,
            "quote_rate": totals["quotations"] / totals["qualified_leads"] if totals["qualified_leads"] else 0.0,
            "order_rate": totals["orders"] / totals["quotations"] if totals["quotations"] else 0.0,
            "gross_profit": totals["revenue"] - totals["purchase_cost"] - totals["traffic_cost"],
        })
        return {
            "project": self._record_ref(project),
            "currency": project.company_id.currency_id.name,
            "date_from": date_from,
            "date_to": date_to,
            "totals": totals,
            "recent_orders": [{
                **self._record_ref(order),
                "state": order.state,
                "opportunity": self._record_ref(order.opportunity_id) if order.opportunity_id else None,
                "market": self._record_ref(order.psc_market_id) if order.psc_market_id else None,
                "channel": self._record_ref(order.psc_channel_id) if order.psc_channel_id else None,
                "amount_total": order.amount_total,
                "currency": order.currency_id.name,
            } for order in recent_orders],
        }

    @api.model
    def prepare_action(self, action_type, title, reason, payload, **metadata):
        if action_type not in dict(self.env["psc.ai.action"]._fields["action_type"].selection):
            raise ValidationError(_("不支持的AI动作类型。"))
        payload = payload or {}
        target_records = self._action_target_records(action_type, payload)
        project = self.env["psc.publishing.project"].browse(payload.get("project_id")).exists()
        if not project:
            for record in target_records:
                if record._name == "psc.publishing.project":
                    project = record
                else:
                    project = getattr(record, "project_id", False) or getattr(record, "psc_project_id", False)
                if project:
                    break
        if project and project.company_id not in self.env.companies:
            raise AccessError(_("当前用户无权访问该运营项目。"))
        company = project.company_id if project else self.env.company
        if not project:
            for record in target_records:
                record_company = getattr(record, "company_id", False)
                if record_company:
                    company = record_company
                    break
        if company not in self.env.companies:
            raise AccessError(_("当前用户无权为该公司准备行动。"))
        run = self.env["psc.ai.run"].browse(metadata.get("run_id")).exists()
        action = self.env["psc.ai.action"].create({
            "name": title,
            "company_id": company.id,
            "run_id": run.id,
            "project_id": project.id,
            "action_type": action_type,
            "priority": metadata.get("priority") or "2",
            "reason": reason,
            "evidence_json": _json_dumps(metadata.get("evidence")),
            "risk_level": "high" if action_type == "cleanup_medical_test_data"
            else metadata.get("risk_level") or "medium",
            "estimated_impact": metadata.get("estimated_impact") or "",
            "payload_json": _json_dumps(payload),
            "precondition_json": _json_dumps({"records": [{
                "model": record._name,
                "id": record.id,
                "write_date": fields.Datetime.to_string(record.write_date),
            } for record in target_records]}),
            "preview_json": _json_dumps({
                "action_type": action_type,
                "target": payload,
                "target_records": [self._record_ref(record) for record in target_records],
                "effect": (
                    _("将删除内置医疗测试数据及其测试依赖；任何目标变化或非测试引用都会拒绝执行。")
                    if action_type == "cleanup_medical_test_data"
                    else _("将创建或修复带[TEST]标识的内置医疗业务测试数据，不修改真实业务记录。")
                    if action_type == "initialize_medical_test_data"
                    else (
                        _("将补齐[TEST] CRM客户、销售订单、采购订单、收货入库、销售出库和库存核验；所有外部发布仍保持关闭。")
                        if payload.get("include_procurement_inventory")
                        else _("将补齐[TEST]产品成功门槛、内容计划、漏斗触点、测试报价和经营快照；不发布内容，不创建真实账号。")
                    )
                    if action_type == "complete_medical_test_scenario"
                    else _("仅创建或更新预览中列出的业务记录；目标发生变化时执行将被拒绝。")
                ),
                "requires_approval": True,
            }),
        })
        token = action._issue_token()
        return {
            "action_id": action.id,
            "title": action.name,
            "state": action.state,
            "risk_level": action.risk_level,
            "reason": action.reason,
            "preview": _json_loads(action.preview_json),
            "action_token": token,
            "expires_at": fields.Datetime.to_string(action.token_expires_at),
        }

    @api.model
    def commit_action(self, action_token, idempotency_key):
        return self.env["psc.ai.action"].commit_token(action_token, idempotency_key)

    @api.model
    def get_action_execution_status(self, action_id):
        action = self._required_record("psc.ai.action", action_id, _("AI行动"))
        return {
            "action_id": action.id,
            "title": action.name,
            "state": action.state,
            "risk_level": action.risk_level,
            "result": _json_loads(action.result_json),
            "error": action.error_message,
            "executed_at": fields.Datetime.to_string(action.executed_at) if action.executed_at else None,
        }


class PerformanceSnapshotAutomation(models.Model):
    _inherit = "psc.performance.snapshot"

    @api.model
    def cron_build_project_snapshots(self):
        snapshot_date = fields.Date.context_today(self)
        day_start = fields.Datetime.to_datetime(snapshot_date)
        day_end = day_start + relativedelta(days=1)
        for project in self.env["psc.publishing.project"].search([("operation_state", "=", "active")]):
            touchpoints = self.env["psc.customer.touchpoint"].search([
                ("project_id", "=", project.id),
                ("occurred_at", ">=", day_start), ("occurred_at", "<", day_end),
                ("verified", "=", True),
            ])
            orders = self.env["sale.order"].search([
                ("psc_project_id", "=", project.id),
                ("date_order", ">=", day_start), ("date_order", "<", day_end),
                ("state", "in", ("draft", "sent", "sale", "done")),
            ])
            confirmed = orders.filtered(lambda order: order.state in ("sale", "done"))
            quotations = orders.filtered(lambda order: order.state in ("draft", "sent"))
            leads = self.env["crm.lead"].search([
                ("psc_project_id", "=", project.id),
                ("create_date", ">=", day_start), ("create_date", "<", day_end),
            ])
            values = {
                "impressions": len(touchpoints.filtered(lambda row: row.event_type == "impression")),
                "views": len(touchpoints.filtered(lambda row: row.event_type == "visit")),
                "clicks": len(touchpoints.filtered(lambda row: row.event_type == "click")),
                "inquiries": len(touchpoints.filtered(lambda row: row.event_type == "inquiry")),
                "qualified_leads": len(leads.filtered(lambda lead: lead.probability >= 30)),
                "quotations": len(quotations),
                "orders": len(confirmed),
                "revenue": sum(confirmed.mapped("amount_total")),
            }
            snapshot = self.search([
                ("snapshot_date", "=", snapshot_date), ("project_id", "=", project.id),
                ("destination_id", "=", False), ("cluster_id", "=", False),
                ("account_id", "=", False), ("content_id", "=", False),
                ("product_id", "=", False),
            ], limit=1)
            if snapshot:
                snapshot.write(values)
            else:
                self.create({"snapshot_date": snapshot_date, "project_id": project.id, **values})
        return True
