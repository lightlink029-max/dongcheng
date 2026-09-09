import uuid
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase

from ..models.res_config_settings import (
    MEDICAL_TEST_ACCOUNT_NAME,
    MEDICAL_TEST_CLUSTER_NAME,
    MEDICAL_TEST_DESTINATION_NAME,
    MEDICAL_TEST_LEAD_NAME,
    MEDICAL_TEST_PUBLICATION_TASK_NAME,
)


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

    def test_failed_action_rolls_back_business_changes_and_keeps_audit(self):
        original_name = self.project.name
        prepared = self.service.prepare_action(
            action_type="create_optimization",
            title="[AUTO TEST] Transaction rollback",
            reason="Verify failed actions are atomic.",
            payload={"project_id": self.project.id, "name": "Rollback test"},
        )
        action = self.env["psc.ai.action"].browse(prepared["action_id"])

        def fail_after_write(action_record):
            action_record.project_id.name = "[AUTO TEST] Must roll back"
            raise UserError("Forced failure after write")

        with patch.object(action.__class__, "_execute_payload", fail_after_write):
            with self.assertRaises(UserError):
                self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))
        self.project.invalidate_recordset(["name"])
        action.invalidate_recordset(["state", "error_message"])
        self.assertEqual(self.project.name, original_name)
        self.assertEqual(action.state, "failed")
        self.assertIn("Forced failure", action.error_message)

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

    def test_close_optimization_supports_every_review_decision(self):
        for decision in ("adopt", "iterate", "rollback"):
            optimization = self.env["psc.optimization.action"].create({
                "name": "[AUTO TEST] Optimization %s" % decision,
                "project_id": self.project.id,
                "evidence": "Synthetic test evidence.",
                "proposed_action": "Exercise the review decision workflow.",
            })
            prepared = self.service.prepare_action(
                action_type="close_optimization",
                title="[AUTO TEST] Close optimization %s" % decision,
                reason="Verify the %s review decision." % decision,
                payload={
                    "optimization_id": optimization.id,
                    "actual_value": 0.02,
                    "final_decision": decision,
                    "result": "[AUTO TEST] Synthetic review result.",
                },
            )
            self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))
            self.assertEqual(optimization.state, "done")
            self.assertEqual(optimization.final_decision, decision)
            self.assertEqual(optimization.actual_value, 0.02)

    def test_ai_publication_retry_allows_only_transient_failures(self):
        channel = self.project.channel_ids.filtered(lambda item: item.platform == "website")[:1]
        website = self.env["website"].search([], limit=1)
        content = self.env["psc.content.variant"].create({
            "project_id": self.project.id,
            "product_id": self.project.product_ids[:1].id,
            "market_id": self.project.market_ids[:1].id,
            "channel_id": channel.id,
            "language_id": self.project.market_ids[:1].lang_id.id,
            "title": "[AUTO TEST] Safe publication retry",
            "caption": "[AUTO TEST] Verified synthetic content.",
            "ai_state": "done",
            "state": "failed",
        })
        destination = self.env["psc.publishing.destination"].create({
            "name": "[AUTO TEST] Website destination",
            "destination_type": "website",
            "product_line_id": self.project.product_line_id.id,
            "market_id": self.project.market_ids[:1].id,
            "channel_id": channel.id,
            "website_id": website.id,
            "state": "ready",
        })
        task = self.env["psc.publication.task"].create({
            "name": "[AUTO TEST] Website publication retry",
            "content_id": content.id,
            "project_id": self.project.id,
            "destination_id": destination.id,
            "state": "failed",
        })

        unsafe = self.service.prepare_action(
            action_type="retry_publication",
            title="[AUTO TEST] Reject unsafe publication retry",
            reason="Authentication failures require user configuration.",
            payload={"task_id": task.id, "failure_class": "authentication"},
        )
        with self.assertRaises(UserError):
            self.service.commit_action(unsafe["action_token"], str(uuid.uuid4()))
        self.assertEqual(task.state, "failed")

        safe = self.service.prepare_action(
            action_type="retry_publication",
            title="[AUTO TEST] Retry transient publication failure",
            reason="A confirmed temporary network failure can be retried safely.",
            payload={"task_id": task.id, "failure_class": "network"},
        )
        self.service.commit_action(safe["action_token"], str(uuid.uuid4()))
        self.assertEqual(task.state, "published")

    def test_ai_run_lifecycle_and_account_health_are_available(self):
        started = self.service.start_ai_run("[AUTO TEST] Daily cockpit", project_id=self.project.id)
        finished = self.service.finish_ai_run(started["run_id"], summary="Snapshot reviewed.")
        self.assertEqual(finished["state"], "done")
        health = self.service.get_account_environment_health(project_id=self.project.id)
        self.assertIn("unhealthy_accounts", health["summary"])
        self.assertTrue(health["setup_required"])

    def test_daily_snapshot_and_priority_leads_are_traceable(self):
        snapshot = self.service.get_daily_operations_snapshot(project_id=self.project.id)
        self.assertEqual(snapshot["project_count"], 1)
        self.assertIn("blocked_products", snapshot["summary"])
        self.assertIn("资料状态", snapshot["blockers"][0]["reason"])
        self.assertIn("硬性门槛", snapshot["blockers"][0]["reason"])
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

    def test_project_snapshot_accepts_planning_project(self):
        self.project.operation_state = "planning"
        snapshot = self.service.get_daily_operations_snapshot(project_id=self.project.id)
        self.assertEqual(snapshot["project_count"], 1)
        self.assertEqual(snapshot["summary"]["active_opportunities"], 1)

    def test_content_backlog_exposes_action_inputs(self):
        backlog = self.service.get_content_backlog(self.project.id)
        self.assertTrue(backlog["available"]["pillars"])
        self.assertTrue(backlog["available"]["products"])
        self.assertTrue(backlog["available"]["markets"])
        self.assertTrue(backlog["available"]["channels"])

    def test_priority_leads_exposes_activity_types(self):
        result = self.service.get_priority_leads(project_id=self.project.id)
        self.assertTrue(result["available_activity_types"])
        self.assertEqual(result["leads"][0]["id"], self.lead.id)

    def test_medical_test_data_cleanup_is_approved_and_scoped(self):
        unrelated = self.env["product.template"].create({"name": "Production product"})
        worker = self.env["psc.local.worker.node"].create({"name": "[AUTO TEST] Cleanup worker"})
        environment = self.env["psc.bitbrowser.environment"].create({
            "name": "[AUTO TEST] Cleanup environment",
            "environment_id": "auto-test-cleanup-environment",
            "worker_node_id": worker.id,
            "state": "open",
            "available": True,
        })
        scenario = self.env["res.config.settings"].create({})._complete_medical_test_scenario(
            worker_node_id=worker.id,
            environment_id=environment.id,
        )
        quotation = self.env["sale.order"].browse(scenario["test_records"]["quotation"])
        touchpoint = self.env["psc.customer.touchpoint"].search([
            ("lead_id", "=", self.lead.id), ("external_reference", "like", "test-medical-funnel-"),
        ], limit=1)
        activity = self.env["mail.activity"].create({
            "res_model_id": self.env["ir.model"]._get_id("crm.lead"),
            "res_id": self.lead.id,
            "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
            "summary": "[TEST] Cleanup activity",
        })
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
        self.assertFalse(quotation.exists())
        self.assertFalse(touchpoint.exists())
        self.assertFalse(activity.exists())
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

    def test_complete_medical_scenario_builds_full_funnel(self):
        worker = self.env["psc.local.worker.node"].create({"name": "[AUTO TEST] Worker"})
        environment = self.env["psc.bitbrowser.environment"].create({
            "name": "[AUTO TEST] Existing environment",
            "environment_id": "auto-test-existing-environment",
            "worker_node_id": worker.id,
            "state": "open",
            "available": True,
        })
        prepared = self.service.prepare_action(
            action_type="complete_medical_test_scenario",
            title="[AUTO TEST] Complete medical test scenario",
            reason="Build the fixed end-to-end test dataset.",
            payload={
                "project_id": self.project.id,
                "dataset": "medical_procurement_smoke_v1",
                "worker_node_id": worker.id,
                "environment_id": environment.id,
            },
        )
        result = self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))
        product_item = self.env["psc.project.product"].browse(result["test_records"]["project_product"])
        self.assertEqual(product_item.status, "active")
        self.assertTrue(product_item.hard_gate_passed)
        self.assertEqual(product_item.compliance_state, "passed")
        performance = self.service.get_campaign_performance(self.project.id)
        self.assertEqual(performance["totals"]["impressions"], 1)
        self.assertEqual(performance["totals"]["clicks"], 1)
        self.assertEqual(performance["totals"]["inquiries"], 1)
        self.assertEqual(performance["totals"]["quotations"], 1)
        self.assertEqual(performance["totals"]["orders"], 1)
        self.assertGreater(performance["totals"]["revenue"], 0)
        self.assertEqual(performance["recent_orders"][0]["opportunity"]["id"], self.lead.id)
        self.assertEqual(performance["recent_orders"][0]["market"]["id"], self.project.market_ids[:1].id)
        self.assertEqual(performance["recent_orders"][0]["channel"]["id"], self.lead.psc_channel_id.id)
        order = self.env["sale.order"].browse(result["test_records"]["order"])
        self.assertEqual(order.state, "sale")
        cluster = self.env["psc.social.account.cluster"].browse(
            result["test_records"]["account_cluster"]
        )
        account = self.env["psc.social.publishing.account"].browse(
            result["test_records"]["publishing_account"]
        )
        destination = self.env["psc.publishing.destination"].browse(
            result["test_records"]["publishing_destination"]
        )
        publication_task = self.env["psc.publication.task"].browse(
            result["test_records"]["publication_task"]
        )
        self.assertEqual(cluster.name, MEDICAL_TEST_CLUSTER_NAME)
        self.assertEqual(cluster.state, "draft")
        self.assertEqual(account.name, MEDICAL_TEST_ACCOUNT_NAME)
        self.assertEqual(account.account_state, "pending")
        self.assertEqual(destination.name, MEDICAL_TEST_DESTINATION_NAME)
        self.assertEqual(destination.state, "draft")
        self.assertEqual(publication_task.name, MEDICAL_TEST_PUBLICATION_TASK_NAME)
        self.assertEqual(publication_task.state, "failed")
        health = self.service.get_account_environment_health(project_id=self.project.id)
        self.assertFalse(health["setup_required"])
        self.assertEqual(health["summary"]["clusters"], 1)
