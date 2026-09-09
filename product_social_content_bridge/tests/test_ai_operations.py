import uuid

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase

from ..models.res_config_settings import MEDICAL_TEST_LEAD_NAME


class AiOperationsCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["res.config.settings"].create({})._upsert_medical_test_data()
        cls.project.operation_state = "active"
        cls.lead = cls.env["crm.lead"].search([
            ("name", "=", MEDICAL_TEST_LEAD_NAME),
            ("psc_project_id", "=", cls.project.id),
        ], limit=1)
        cls.service = cls.env["psc.ai.service"]

    def test_blueprint_launches_reusable_project(self):
        blueprint = self.env.ref(
            "product_social_content_bridge.blueprint_west_africa_medical_procurement"
        )
        project = blueprint.create_project({
            "name": "[AUTO TEST] Blueprint project",
            "product_line_id": self.project.product_line_id.id,
            "product_ids": self.project.product_ids.ids,
            "market_ids": self.project.market_ids.ids,
            "channel_ids": self.project.channel_ids.ids,
        })
        self.assertEqual(project.blueprint_id, blueprint)
        self.assertEqual(project.blueprint_version, blueprint.version)
        self.assertEqual(project.track_id, blueprint.track_id)
        self.assertTrue(project.project_product_ids)
        self.assertTrue(project.content_plan_ids)

    def test_prepare_commit_is_approved_audited_and_idempotent(self):
        prepared = self.service.prepare_action(
            action_type="create_optimization",
            title="[AUTO TEST] Improve inquiry conversion",
            reason="Verified clicks are not becoming qualified inquiries.",
            payload={
                "project_id": self.project.id,
                "name": "[AUTO TEST] Improve inquiry conversion",
                "category": "customer",
                "evidence": "Test evidence",
                "proposed_action": "Run a two-week landing-page experiment.",
                "target_metric": "qualified inquiry rate",
                "baseline_value": 0.05,
                "target_value": 0.07,
                "observation_days": 14,
                "success_criteria": "Rate reaches 7%.",
                "rollback_criteria": "Bounce rate increases by 15%.",
            },
            priority="1",
            risk_level="medium",
        )
        key = str(uuid.uuid4())
        first = self.service.commit_action(prepared["action_token"], key)
        second = self.service.commit_action(prepared["action_token"], key)
        self.assertEqual(first, second)
        action = self.env["psc.ai.action"].browse(prepared["action_id"])
        self.assertEqual(action.state, "done")
        self.assertEqual(len(action.execution_ids), 1)
        self.assertEqual(action.execution_ids.state, "done")
        optimization = self.env[first["model"]].browse(first["id"])
        self.assertEqual(optimization.target_metric, "qualified inquiry rate")
        self.assertEqual(optimization.observation_days, 14)

    def test_invalid_action_token_is_rejected(self):
        with self.assertRaises(AccessError):
            self.service.commit_action("invalid", str(uuid.uuid4()))

    def test_changed_target_requires_a_fresh_preview(self):
        prepared = self.service.prepare_action(
            action_type="create_optimization",
            title="[AUTO TEST] Stale preview",
            reason="Verify optimistic target locking.",
            payload={"project_id": self.project.id, "name": "Stale preview"},
        )
        self.project.name = "%s updated" % self.project.name
        with self.assertRaises(UserError):
            self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))

    def test_chatgpt_content_draft_obeys_product_gates(self):
        item = self.project.project_product_ids.filtered("product_id")[:1]
        item.score_line_ids.filtered("hard_gate").write({"gate_passed": True})
        item.attribute_value_ids.filtered("hard_gate").write({"value": "verified", "verified": True})
        item.write({"status": "active", "compliance_state": "passed", "material_state": "complete"})
        plan = self.project.content_plan_ids[:1]
        plan.product_id = item.product_id
        prepared = self.service.prepare_action(
            action_type="create_content_draft",
            title="[AUTO TEST] Approved content draft",
            reason="Content is based on verified Odoo product facts.",
            payload={
                "plan_id": plan.id,
                "product_id": item.product_id.id,
                "title": "Verified product title",
                "caption": "Verified product copy for the selected market.",
                "hashtags": "#LightLink",
            },
        )
        result = self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))
        content = self.env[result["model"]].browse(result["id"])
        self.assertEqual(content.caption, "Verified product copy for the selected market.")
        self.assertEqual(plan.content_id, content)
        self.assertEqual(plan.state, "prepared")

    def test_ai_run_lifecycle_and_account_health_are_available(self):
        started = self.service.start_ai_run("[AUTO TEST] Daily cockpit", project_id=self.project.id)
        finished = self.service.finish_ai_run(started["run_id"], summary="Snapshot reviewed.")
        self.assertEqual(finished["state"], "done")
        health = self.service.get_account_environment_health(project_id=self.project.id)
        self.assertIn("unhealthy_accounts", health["summary"])

    def test_daily_snapshot_and_priority_leads_are_traceable(self):
        snapshot = self.service.get_daily_operations_snapshot(project_id=self.project.id)
        self.assertEqual(snapshot["project_count"], 1)
        self.assertIn("blocked_products", snapshot["summary"])
        leads = self.service.get_priority_leads(project_id=self.project.id)
        self.assertEqual(leads["leads"][0]["id"], self.lead.id)
        self.assertTrue(leads["leads"][0]["url"])

    def test_sale_order_keeps_project_attribution(self):
        order = self.env["sale.order"].create({
            "partner_id": self.lead.partner_id.id,
            "opportunity_id": self.lead.id,
        })
        self.assertEqual(order.psc_project_id, self.project)
        self.assertEqual(order.psc_market_id, self.lead.psc_market_id)
        self.assertEqual(order.psc_channel_id, self.lead.psc_channel_id)

    def test_daily_snapshot_cron_is_repeatable(self):
        snapshot_model = self.env["psc.performance.snapshot"]
        snapshot_model.cron_build_project_snapshots()
        snapshot_model.cron_build_project_snapshots()
        self.assertEqual(snapshot_model.search_count([
            ("snapshot_date", "=", fields.Date.context_today(snapshot_model)),
            ("project_id", "=", self.project.id),
            ("destination_id", "=", False),
            ("cluster_id", "=", False),
            ("account_id", "=", False),
            ("content_id", "=", False),
            ("product_id", "=", False),
        ]), 1)

    def test_medical_test_data_cleanup_is_approved_and_scoped(self):
        unrelated = self.env["product.template"].create({"name": "Production product"})
        old_preview = self.service.prepare_action(
            action_type="create_optimization",
            title="[AUTO TEST] Pending preview",
            reason="Verify cleanup retains the audit record.",
            payload={"project_id": self.project.id, "name": "Pending preview"},
        )
        prepared = self.service.prepare_action(
            action_type="cleanup_medical_test_data",
            title="[AUTO TEST] Cleanup medical smoke data",
            reason="Reset only the fixed medical smoke dataset.",
            payload={"project_id": self.project.id},
            risk_level="high",
        )
        result = self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))
        self.assertFalse(self.project.exists())
        self.assertFalse(self.lead.exists())
        self.assertTrue(unrelated.exists())
        retained_action = self.env["psc.ai.action"].browse(old_preview["action_id"])
        self.assertEqual(retained_action.state, "rejected")
        self.assertIn("psc.publishing.project", result["deleted"])

        initialize = self.service.prepare_action(
            action_type="initialize_medical_test_data",
            title="[AUTO TEST] Initialize medical smoke data",
            reason="Rebuild the fixed medical smoke dataset.",
            payload={"dataset": "medical_procurement_smoke_v1"},
        )
        initialized = self.service.commit_action(initialize["action_token"], str(uuid.uuid4()))
        rebuilt_project = self.env["psc.publishing.project"].browse(initialized["id"])
        self.assertEqual(rebuilt_project.name, "[TEST] 西非医疗类综合采购商运营项目")
        self.assertTrue(rebuilt_project.project_product_ids)
        self.assertTrue(self.env["crm.lead"].search([
            ("name", "=", MEDICAL_TEST_LEAD_NAME),
            ("psc_project_id", "=", rebuilt_project.id),
        ], limit=1))
