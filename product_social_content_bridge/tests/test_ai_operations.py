import uuid
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase

from ..models.res_config_settings import (
    MEDICAL_TEST_ACCOUNT_NAME,
    MEDICAL_TEST_CLUSTER_NAME,
    MEDICAL_TEST_DESTINATION_NAME,
    MEDICAL_TEST_FULFILLMENT_REFERENCE,
    MEDICAL_TEST_LEAD_NAME,
    MEDICAL_TEST_PURCHASE_REFERENCE,
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

    def test_footwear_project_initialization_builds_a_gated_daily_plan(self):
        prepared = self.service.prepare_action(
            action_type="initialize_footwear_sourcing_project",
            title="[AUTO TEST] Initialize footwear sourcing project",
            reason="Create the approved US and UK footwear sourcing launch plan.",
            payload={
                "dataset": "eu_us_footwear_sourcing_v1",
                "project_name": "[AUTO TEST] EU and US Footwear Sourcing",
            },
        )
        self.assertIn("28项", prepared["preview"]["effect"])
        key = str(uuid.uuid4())
        result = self.service.commit_action(prepared["action_token"], key)
        project = self.env["psc.publishing.project"].browse(result["id"])
        self.assertEqual(project.operation_state, "planning")
        self.assertEqual(project.business_role_id.code, "sourcing_agent")
        self.assertEqual(set(project.market_ids.mapped("country_id.code")), {"US", "GB"})
        self.assertEqual(set(project.channel_ids.mapped("platform")), {
            "website", "linkedin", "instagram",
        })
        self.assertFalse(project.product_ids)
        self.assertFalse(project.publication_task_ids)
        self.assertEqual(len(project.readiness_item_ids), 28)
        self.assertEqual(sum(project.readiness_item_ids.mapped("weight")), 100.0)
        self.assertEqual(project.readiness_progress, 0.0)
        self.assertFalse(project.launch_ready)
        with self.assertRaises(UserError):
            project.action_activate_operation()

        hard_gate = project.readiness_item_ids.filtered("hard_gate")[:1]
        with self.assertRaises(UserError):
            hard_gate.action_done()
        hard_gate.evidence = "Verified automated-test evidence"
        hard_gate.action_done()
        self.assertGreater(project.readiness_progress, 0.0)
        snapshot = self.service.get_daily_operations_snapshot(project_id=project.id)
        self.assertEqual(snapshot["summary"]["readiness_incomplete"], 27)
        self.assertTrue(snapshot["readiness_tasks"])
        self.assertIn("responsibility", snapshot["readiness_tasks"][0])
        listed = self.service.list_projects()
        listed_project = next(item for item in listed["projects"] if item["id"] == project.id)
        self.assertEqual(listed_project["readiness_progress"], project.readiness_progress)

        replay = self.service.commit_action(prepared["action_token"], key)
        self.assertEqual(replay["id"], project.id)
        self.assertEqual(len(project.readiness_item_ids), 28)

    def test_readiness_progress_can_be_updated_in_one_approved_batch(self):
        initialized = self.service._initialize_footwear_sourcing_project(
            project_name="[AUTO TEST] Batch readiness update",
        )
        project = self.env["psc.publishing.project"].browse(initialized["id"])
        hard_gate = project.readiness_item_ids.filtered(
            lambda item: item.template_key == "strategy_positioning"
        ).ensure_one()
        ai_task = project.readiness_item_ids.filtered(
            lambda item: item.template_key == "strategy_icp"
        ).ensure_one()
        prepared = self.service.prepare_action(
            action_type="update_project_readiness",
            title="[AUTO TEST] Update launch readiness",
            reason="Apply one reviewed batch of launch-plan progress.",
            payload={
                "project_id": project.id,
                "updates": [
                    {
                        "item_id": hard_gate.id,
                        "state": "done",
                        "evidence": "Approved positioning boundary and English value proposition.",
                    },
                    {"item_id": ai_task.id, "state": "doing"},
                ],
            },
        )
        result = self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))
        self.assertEqual(hard_gate.state, "done")
        self.assertEqual(ai_task.state, "doing")
        self.assertEqual(result["readiness_progress"], 4.0)
        self.assertFalse(result["launch_ready"])
        self.assertEqual({item["id"] for item in result["updated_items"]}, {
            hard_gate.id, ai_task.id,
        })

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

    def test_new_identical_preview_rejects_previous_pending_preview(self):
        values = {
            "action_type": "create_optimization",
            "title": "[AUTO TEST] Replace duplicate preview",
            "reason": "Only the newest identical approval request should remain pending.",
            "payload": {
                "project_id": self.project.id,
                "name": "[AUTO TEST] Duplicate preview",
            },
        }
        first = self.service.prepare_action(**values)
        second = self.service.prepare_action(**values)

        first_action = self.env["psc.ai.action"].browse(first["action_id"])
        second_action = self.env["psc.ai.action"].browse(second["action_id"])
        self.assertEqual(first_action.state, "rejected")
        self.assertEqual(second_action.state, "waiting_approval")

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
        won_stage = self.env["crm.stage"].search([("is_won", "=", True)], limit=1)
        self.assertTrue(won_stage)
        self.lead.stage_id = won_stage
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
        self.assertTrue(self.lead.stage_id.is_won)
        performance = self.service.get_campaign_performance(self.project.id)
        self.assertEqual(performance["totals"]["impressions"], 1)
        self.assertEqual(performance["totals"]["clicks"], 1)
        self.assertEqual(performance["totals"]["inquiries"], 1)
        self.assertEqual(performance["totals"]["quotations"], 1)
        self.assertEqual(performance["totals"]["orders"], 1)
        self.assertGreater(performance["totals"]["order_value"], 0)
        self.assertEqual(performance["totals"]["revenue"], 0.0)
        self.assertEqual(performance["recent_orders"][0]["opportunity"]["id"], self.lead.id)
        self.assertEqual(performance["recent_orders"][0]["market"]["id"], self.project.market_ids[:1].id)
        self.assertEqual(performance["recent_orders"][0]["channel"]["id"], self.lead.psc_channel_id.id)
        order = self.env["sale.order"].browse(result["test_records"]["order"])
        self.assertEqual(order.state, "sale")
        requirement = self.lead.psc_requirement_ids.filtered(
            lambda item: item.project_id == self.project
        )[:1]
        self.assertEqual(requirement.stage, "won")
        self.assertTrue(requirement.target_purchase_date)
        requirement.write({"stage": "new", "target_purchase_date": False})
        sync = self.service.prepare_action(
            action_type="sync_project_business_state",
            title="[AUTO TEST] Sync project business state",
            reason="Repair existing requirement stages from confirmed orders.",
            payload={"project_id": self.project.id},
        )
        sync_result = self.service.commit_action(sync["action_token"], str(uuid.uuid4()))
        self.assertIn(requirement.id, sync_result["updated_requirements"])
        self.assertEqual(requirement.stage, "won")
        self.assertTrue(requirement.target_purchase_date)
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

    def test_complete_medical_scenario_builds_procurement_inventory_flow(self):
        worker = self.env["psc.local.worker.node"].create({"name": "[AUTO TEST] Stock worker"})
        environment = self.env["psc.bitbrowser.environment"].create({
            "name": "[AUTO TEST] Stock environment",
            "environment_id": "auto-test-stock-environment",
            "worker_node_id": worker.id,
            "state": "open",
            "available": True,
        })
        prepared = self.service.prepare_action(
            action_type="complete_medical_test_scenario",
            title="[AUTO TEST] Complete procurement and inventory flow",
            reason="Validate the CRM-to-fulfillment workflow.",
            payload={
                "project_id": self.project.id,
                "dataset": "medical_procurement_smoke_v1",
                "worker_node_id": worker.id,
                "environment_id": environment.id,
                "include_procurement_inventory": True,
            },
        )
        result = self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))
        records = result["test_records"]
        sale_order = self.env["sale.order"].browse(records["fulfillment_order"])
        purchase_order = self.env["purchase.order"].browse(records["purchase_order"])
        receipts = self.env["stock.picking"].browse(records["receipt_pickings"])
        deliveries = self.env["stock.picking"].browse(records["delivery_pickings"])

        self.assertEqual(sale_order.client_order_ref, MEDICAL_TEST_FULFILLMENT_REFERENCE)
        self.assertEqual(sale_order.opportunity_id, self.lead)
        self.assertEqual(sale_order.psc_project_id, self.project)
        self.assertEqual(purchase_order.partner_ref, MEDICAL_TEST_PURCHASE_REFERENCE)
        self.assertEqual(purchase_order.origin, sale_order.name)
        self.assertEqual(purchase_order.psc_sale_order_id, sale_order)
        self.assertEqual(purchase_order.psc_project_id, self.project)
        self.assertEqual(purchase_order.state, "purchase")
        self.assertTrue(receipts)
        self.assertTrue(deliveries)
        self.assertTrue(all(picking.state == "done" for picking in receipts | deliveries))
        self.assertEqual(records["purchased_qty"], 2.0)
        self.assertEqual(records["delivered_qty"], 2.0)
        self.assertEqual(records["internal_stock_qty"], 0.0)
        performance = self.service.get_campaign_performance(self.project.id)
        self.assertEqual(performance["totals"]["purchase_order_value"], 1200.0)
        self.assertEqual(performance["totals"]["purchase_cost"], 0.0)
        self.assertEqual(performance["totals"]["gross_profit"], 0.0)
        self.assertEqual(performance["recent_purchase_orders"][0]["id"], purchase_order.id)

        cleanup = self.env["res.config.settings"].create({})._cleanup_medical_test_data()
        self.assertFalse(self.project.exists())
        self.assertTrue(sale_order.exists())
        self.assertTrue(purchase_order.exists())
        self.assertIn(sale_order.id, cleanup["retained_audit"]["sale.order"])
        self.assertIn(purchase_order.id, cleanup["retained_audit"]["purchase.order"])
        self.assertFalse(sale_order.order_line.product_id.active)

    def test_complete_medical_scenario_builds_finance_and_return_flow(self):
        journals = self.env["account.journal"].search([
            ("company_id", "=", self.env.company.id),
            ("type", "in", ("sale", "purchase", "bank", "cash")),
        ])
        if not {"sale", "purchase"}.issubset(set(journals.mapped("type"))) or not journals.filtered(
            lambda journal: journal.type in ("bank", "cash")
        ):
            self.skipTest("Accounting journals are not configured in this test database.")
        worker = self.env["psc.local.worker.node"].create({"name": "[AUTO TEST] Finance worker"})
        environment = self.env["psc.bitbrowser.environment"].create({
            "name": "[AUTO TEST] Finance environment",
            "environment_id": "auto-test-finance-environment",
            "worker_node_id": worker.id,
            "state": "open",
            "available": True,
        })
        prepared = self.service.prepare_action(
            action_type="complete_medical_test_scenario",
            title="[AUTO TEST] Complete finance and return flow",
            reason="Validate invoices, payments, returns and refunds.",
            payload={
                "project_id": self.project.id,
                "dataset": "medical_procurement_smoke_v1",
                "worker_node_id": worker.id,
                "environment_id": environment.id,
                "include_procurement_inventory": True,
                "include_finance_workflow": True,
            },
        )
        result = self.service.commit_action(prepared["action_token"], str(uuid.uuid4()))
        records = result["test_records"]
        moves = self.env["account.move"].browse([
            records["customer_invoice"],
            records["vendor_bill"],
            records["customer_refund"],
            records["vendor_refund"],
        ])
        returns = self.env["stock.picking"].browse([
            records["customer_return"], records["vendor_return"],
        ])

        self.assertTrue(all(move.state == "posted" for move in moves))
        self.assertTrue(all(move.invoice_date for move in moves))
        self.assertTrue(all(move.payment_state in ("paid", "in_payment") for move in moves))
        self.assertTrue(all(move.currency_id.is_zero(move.amount_residual) for move in moves))
        self.assertTrue(all(picking.state == "done" for picking in returns))
        self.assertEqual(records["customer_return_qty"], 2.0)
        self.assertEqual(records["vendor_return_qty"], 2.0)
        self.assertEqual(records["internal_stock_after_returns"], 0.0)
        performance = self.service.get_campaign_performance(self.project.id)
        totals = performance["totals"]
        self.assertEqual(totals["quotations"], 2)
        self.assertEqual(totals["orders"], 2)
        self.assertEqual(totals["quoted_leads"], 1)
        self.assertEqual(totals["ordered_leads"], 1)
        self.assertEqual(totals["quote_rate"], 1.0)
        self.assertEqual(totals["order_rate"], 1.0)
        self.assertEqual(totals["order_value"], 4000.0)
        self.assertEqual(totals["gross_revenue"], 2000.0)
        self.assertEqual(totals["refund_amount"], 2000.0)
        self.assertEqual(totals["net_revenue"], 0.0)
        self.assertEqual(totals["revenue"], 0.0)
        self.assertEqual(totals["purchase_order_value"], 1200.0)
        self.assertEqual(totals["gross_purchase_cost"], 1200.0)
        self.assertEqual(totals["vendor_refund_amount"], 1200.0)
        self.assertEqual(totals["net_purchase_cost"], 0.0)
        self.assertEqual(totals["purchase_cost"], 0.0)
        self.assertEqual(totals["net_gross_profit"], 0.0)
        self.assertEqual(totals["gross_profit"], 0.0)
