import json
from unittest import mock

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase

from ..models import social_content
from ..models.res_config_settings import (
    MEDICAL_TEST_LEAD_NAME,
    MEDICAL_TEST_PROJECT_NAME,
)


class MarketOperationsWorkflowCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.settings = cls.env["res.config.settings"].create({})
        cls.project = cls.settings._upsert_medical_test_data()
        cls.market = cls.project.market_ids.ensure_one()
        cls.channel = cls.project.channel_ids.ensure_one()
        cls.product = cls.project.product_ids[:1]

    def _generate_channel_content(self):
        self.env["ir.config_parameter"].sudo().set_param("ai.openai_key", "test-key")
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "model": "test-content-model",
            "output_text": json.dumps({
                "title": "Reliable medical procurement for Nigerian hospitals",
                "selling_points": ["Integrated product selection", "Documented compliance review"],
                "seo_keywords": ["medical procurement Nigeria", "hospital equipment supplier"],
                "caption": "Source essential medical equipment and consumables through one coordinated workflow.",
                "hashtags": ["MedicalProcurement", "NigeriaHealthcare"],
                "video_script": "Show the product, explain selection criteria, then present delivery support.",
                "image_prompt": "A factual B2B medical procurement presentation using the real product.",
            }),
            "usage": {"input_tokens": 100, "output_tokens": 80},
        }
        with mock.patch.object(social_content.requests, "post", return_value=response) as post:
            self.project.action_generate_drafts()
        return post

    def _social_resources(self):
        channel = self.env["psc.publishing.channel"].create({
            "name": "[AUTO TEST] Facebook Nigeria Medical",
            "platform": "facebook",
        })
        node = self.env["psc.local.worker.node"].create({"name": "[AUTO TEST] Windows Node"})
        environment = self.env["psc.bitbrowser.environment"].create({
            "name": "[AUTO TEST] Bit Environment",
            "environment_id": "auto-test-bit-environment",
            "worker_node_id": node.id,
            "state": "closed",
            "available": True,
        })
        cluster = self.env["psc.social.account.cluster"].create({
            "name": "[AUTO TEST] Nigeria Medical Cluster",
            "project_ids": [(6, 0, self.project.ids)],
            "track_id": self.project.track_id.id,
            "product_line_id": self.project.product_line_id.id,
            "target_market_id": self.market.id,
            "persona": "Medical procurement integrator",
            "worker_node_id": node.id,
            "bitbrowser_environment_id": environment.id,
            "expected_ip": "203.0.113.10",
            "expected_country_id": self.market.country_id.id,
            "expected_timezone": "Africa/Lagos",
        })
        return channel, node, environment, cluster

    def test_product_pool_requires_complete_verified_data(self):
        item = self.project.project_product_ids.filtered(
            lambda row: row.product_id == self.product
        ).ensure_one()
        self.assertEqual(len(item.score_line_ids), 5)
        self.assertEqual(len(item.attribute_value_ids), 4)
        self.assertEqual(item.fit_score, 50.0)
        self.assertFalse(item.hard_gate_passed)

        with self.assertRaises(UserError):
            item.action_mark_active()
        item.material_state = "complete"
        with self.assertRaises(UserError):
            item.action_mark_active()

        item.attribute_value_ids.write({
            "value": "Verified test evidence",
            "verified": True,
            "evidence": "Backend workflow test",
        })
        item.score_line_ids.filtered("hard_gate").write({"gate_passed": True})
        item.compliance_state = "passed"
        item.action_mark_active()
        self.assertEqual(item.status, "active")
        self.assertTrue(item.hard_gate_passed)

        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["psc.project.product"].create({
                "project_id": self.project.id,
                "product_id": self.product.id,
                "source": "odoo",
            })

    def test_content_plan_prepares_one_reusable_draft(self):
        pillar = self.env.ref("product_social_content_bridge.pillar_medical_solution")
        plan = self.env["psc.content.plan"].create({
            "name": "[AUTO TEST] Hospital procurement selection guide",
            "project_id": self.project.id,
            "pillar_id": pillar.id,
            "product_id": self.product.id,
            "market_id": self.market.id,
            "channel_id": self.channel.id,
            "brief": "Explain verified selection criteria without clinical claims.",
        })

        first_action = plan.action_prepare_content()
        content = plan.content_id
        second_action = plan.action_prepare_content()

        self.assertTrue(content)
        self.assertEqual(plan.state, "prepared")
        self.assertEqual(content.pillar_id, pillar)
        self.assertEqual(content.caption, plan.brief)
        self.assertEqual(first_action["res_id"], content.id)
        self.assertEqual(second_action["res_id"], content.id)
        self.assertEqual(self.env["psc.content.variant"].search_count([
            ("plan_id", "=", plan.id),
        ]), 1)

    def test_project_level_plan_creates_channel_versions_without_product(self):
        second_channel = self.env["psc.publishing.channel"].create({
            "name": "[AUTO TEST] LinkedIn project positioning",
            "platform": "linkedin",
        })
        scope = self.env.ref("product_social_content_bridge.content_scope_brand_positioning")
        plan = self.env["psc.content.plan"].create({
            "name": "[AUTO TEST] China sourcing partner positioning",
            "project_id": self.project.id,
            "scope_id": scope.id,
            "content_format": "short_video",
            "market_ids": [(6, 0, self.market.ids)],
            "channel_ids": [(6, 0, (self.channel | second_channel).ids)],
            "brief": "Explain the project role and evidence boundaries without product claims.",
        })

        action = plan.action_prepare_content()

        self.assertEqual(plan.content_count, 2)
        self.assertEqual(set(plan.content_ids.mapped("channel_id").ids), set((self.channel | second_channel).ids))
        self.assertFalse(plan.content_ids.mapped("product_id"))
        self.assertEqual(set(plan.content_ids.mapped("scope_id").ids), {scope.id})
        self.assertEqual(set(plan.content_ids.mapped("content_format")), {"short_video"})
        self.assertEqual(action["view_mode"], "list,form")

    def test_default_content_mix_has_ten_editable_types_and_totals_one_hundred(self):
        self.env["psc.content.mix.rule"].ensure_default_profiles()
        rules = self.env["psc.content.mix.rule"].search([
            ("track_id", "=", self.project.track_id.id),
            ("role_id", "=", self.project.business_role_id.id),
            ("active", "=", True),
        ])

        self.assertEqual(len(rules), 10)
        self.assertEqual(sum(rules.mapped("content_ratio")), 100)
        self.assertTrue(all(0 <= value <= 100 for value in rules.mapped("video_ratio")))
        self.assertTrue(all(rules.mapped("execution_goal")))
        self.assertTrue(all(rules.mapped("copy_template")))
        self.assertTrue(all(rules.mapped("required_evidence")))

        footwear_rule = self.env["psc.content.mix.rule"].search([
            ("track_id", "=", self.env.ref("product_social_content_bridge.track_footwear_apparel").id),
            ("role_id", "=", self.env.ref("product_social_content_bridge.role_sourcing_agent").id),
            ("scope_id", "=", self.env.ref("product_social_content_bridge.content_scope_sourcing_service").id),
        ], limit=1)
        self.assertIn("footwear", footwear_rule.copy_template.lower())
        self.assertIn("china sourcing", footwear_rule.copy_template.lower())
        self.assertEqual(footwear_rule.action_open_guide()["res_id"], footwear_rule.id)

    def test_ai_content_and_website_publication_workflow(self):
        post = self._generate_channel_content()
        contents = self.project.content_ids
        self.assertEqual(len(contents), 3)
        self.assertEqual(post.call_count, 3)
        self.assertTrue(all(state == "done" for state in contents.mapped("ai_state")))
        self.assertTrue(all(contents.mapped("video_script")))

        self._generate_channel_content()
        self.assertEqual(len(self.project.content_ids), 3)

        website = self.env["website"].search([], limit=1)
        self.assertTrue(website)
        destination = self.env["psc.publishing.destination"].create({
            "name": "[AUTO TEST] Nigeria Medical Website",
            "destination_type": "website",
            "product_line_id": self.project.product_line_id.id,
            "market_id": self.market.id,
            "channel_id": self.channel.id,
            "website_id": website.id,
        })
        destination.action_mark_ready()
        self.project.destination_ids = [(6, 0, destination.ids)]
        self.project.action_mark_ready()
        self.project.action_create_publication_tasks()
        self.project.action_create_publication_tasks()
        tasks = self.project.publication_task_ids
        self.assertEqual(len(tasks), 3)

        tasks.action_queue()
        self.assertTrue(all(state == "published" for state in tasks.mapped("state")))
        self.assertTrue(all(state == "published" for state in contents.mapped("state")))
        self.assertEqual(self.project.state, "published")
        self.assertTrue(all(tasks.mapped("published_url")))

    def test_local_media_queue_prevents_duplicates_and_retries(self):
        content = self.env["psc.content.variant"].create({
            "project_id": self.project.id,
            "product_id": self.product.id,
            "market_id": self.market.id,
            "channel_id": self.channel.id,
            "language_id": self.market.lang_id.id,
            "title": "[AUTO TEST] Medical product video",
            "caption": "Verified sourcing workflow.",
            "video_script": "Show product, documents and delivery support.",
            "source_video_urls": "https://v.douyin.com/auto-test/",
        })
        content.action_generate_social_video()
        task = content.local_task_ids.ensure_one()
        self.assertEqual(task.task_type, "translate_mix")
        self.assertEqual(task.state, "queued")
        with self.assertRaises(UserError):
            content.action_generate_social_video()

        task.write({"state": "failed", "worker_id": "test-worker", "progress": 55,
                    "error_message": "simulated failure"})
        task.action_retry()
        self.assertEqual(task.state, "queued")
        self.assertFalse(task.worker_id)
        self.assertEqual(task.progress, 0)
        self.assertFalse(task.error_message)

        empty_content = content.copy({"title": "[AUTO TEST] Missing source", "source_video_urls": False})
        with self.assertRaises(UserError):
            empty_content.action_generate_social_video()

    def test_social_publication_environment_validation_and_retry(self):
        channel, _node, _environment, cluster = self._social_resources()
        account = self.env["psc.social.publishing.account"].create({
            "name": "[AUTO TEST] Nigeria Medical Facebook",
            "cluster_id": cluster.id,
            "channel_id": channel.id,
            "username": "lightlink_medical_test",
            "platform_account_id": "facebook-auto-test-1",
            "account_state": "available",
            "last_validation_state": "passed",
        })
        cluster.action_mark_ready()
        attachment = self.env["ir.attachment"].create({
            "name": "auto-test.png", "raw": b"test-image", "mimetype": "image/png",
        })
        content = self.env["psc.content.variant"].create({
            "project_id": self.project.id,
            "product_id": self.product.id,
            "market_id": self.market.id,
            "channel_id": channel.id,
            "language_id": self.market.lang_id.id,
            "title": "[AUTO TEST] Facebook medical content",
            "caption": "Verified product information.",
            "ai_state": "done",
            "state": "ready",
            "image_attachment_id": attachment.id,
        })
        destination = self.env["psc.publishing.destination"].create({
            "name": "[AUTO TEST] Facebook destination",
            "destination_type": "social",
            "product_line_id": self.project.product_line_id.id,
            "market_id": self.market.id,
            "channel_id": channel.id,
            "publishing_account_id": account.id,
        })
        destination.action_mark_ready()
        task = self.env["psc.publication.task"].create({
            "name": "[AUTO TEST] Facebook publish",
            "content_id": content.id,
            "project_id": self.project.id,
            "destination_id": destination.id,
        })
        task.action_queue()
        self.assertEqual(task.state, "queued")

        task.state = "validating"
        mismatches = task.apply_environment_validation(
            "198.51.100.20", "NG", "Africa/Lagos", "lightlink_medical_test",
        )
        self.assertEqual(mismatches, ["IP"])
        self.assertEqual(task.state, "failed")
        self.assertEqual(content.state, "failed")
        self.assertEqual(self.project.state, "failed")

        task.action_retry()
        task.state = "validating"
        mismatches = task.apply_environment_validation(
            "203.0.113.10", "ng", "Africa/Lagos", "LIGHTLINK_MEDICAL_TEST",
        )
        self.assertFalse(mismatches)
        self.assertEqual(task.state, "publishing")

    def test_account_replacement_is_idempotent_and_environment_checked(self):
        channel, _node, _environment, cluster = self._social_resources()
        email_model = self.env["psc.email.asset"]
        old_email = email_model.create({
            "email": "old-medical-auto-test@example.com",
            "provider": "enterprise",
            "product_line_id": self.project.product_line_id.id,
            "target_market_id": self.market.id,
        })
        new_email = email_model.create({
            "email": "new-medical-auto-test@example.com",
            "provider": "enterprise",
            "product_line_id": self.project.product_line_id.id,
            "target_market_id": self.market.id,
        })
        account = self.env["psc.social.publishing.account"].create({
            "name": "[AUTO TEST] Replaceable Facebook account",
            "cluster_id": cluster.id,
            "channel_id": channel.id,
            "username": "old_medical_account",
            "platform_account_id": "facebook-old-auto-test",
            "email_asset_id": old_email.id,
            "account_state": "available",
            "last_validation_state": "passed",
            "unavailable_reason": "Platform account disabled in test",
        })
        account.action_mark_unavailable()
        first_action = account.action_create_replacement()
        second_action = account.action_create_replacement()
        self.assertEqual(first_action["res_id"], second_action["res_id"])
        self.assertEqual(account.account_state, "replacement_pending")
        self.assertEqual(account.slot_id.state, "replacing")
        self.assertEqual(self.env["psc.social.registration.task"].search_count([
            ("replacement_account_id", "=", account.id),
            ("state", "in", ("draft", "ready", "environment_check", "awaiting_verification")),
        ]), 1)

        task = self.env["psc.social.registration.task"].browse(first_action["res_id"])
        task.email_asset_id = new_email
        task.action_submit()
        self.assertEqual(task.state, "ready")
        task.state = "environment_check"
        self.assertEqual(
            task.apply_environment_validation("203.0.113.99", "NG", "Africa/Lagos"),
            ["IP"],
        )
        self.assertEqual(task.state, "environment_mismatch")
        task.action_retry()
        task.state = "environment_check"
        self.assertFalse(task.apply_environment_validation(
            "203.0.113.10", "ng", "Africa/Lagos",
        ))
        self.assertEqual(task.state, "awaiting_verification")

    def test_customer_attribution_metrics_and_optimization_states(self):
        lead = self.env["crm.lead"].search([
            ("name", "=", MEDICAL_TEST_LEAD_NAME),
            ("psc_project_id", "=", self.project.id),
        ], limit=1)
        first = self.env["psc.customer.touchpoint"].create({
            "lead_id": lead.id,
            "occurred_at": "2026-09-01 10:00:00",
            "event_type": "click",
            "source_type": "facebook",
            "project_id": self.project.id,
            "market_id": self.market.id,
            "product_id": self.product.id,
            "verified": True,
        })
        second = self.env["psc.customer.touchpoint"].create({
            "lead_id": lead.id,
            "occurred_at": "2026-09-02 10:00:00",
            "event_type": "inquiry",
            "source_type": "website",
            "project_id": self.project.id,
            "market_id": self.market.id,
            "product_id": self.product.id,
            "verified": False,
        })
        self.assertEqual(lead.psc_first_touchpoint_id, first)
        self.assertEqual(lead.psc_last_touchpoint_id, first)
        second.verified = True
        self.assertEqual(lead.psc_first_touchpoint_id, first)
        self.assertEqual(lead.psc_last_touchpoint_id, second)

        snapshot = self.env["psc.performance.snapshot"].create({
            "project_id": self.project.id,
            "product_id": self.product.id,
            "impressions": 1000,
            "clicks": 80,
            "inquiries": 6,
            "qualified_leads": 3,
            "quotations": 2,
            "orders": 1,
            "revenue": 50000,
            "purchase_cost": 30000,
        })
        self.assertEqual(snapshot.orders, 1)
        action = self.env["psc.optimization.action"].create({
            "name": "[AUTO TEST] Improve medical landing page",
            "project_id": self.project.id,
            "category": "content",
            "evidence": "80 clicks generated 6 inquiries.",
            "proposed_action": "Clarify certification and delivery evidence.",
        })
        action.action_approve()
        action.action_start()
        action.action_done()
        self.assertEqual(action.state, "done")

    def test_test_initializer_rejects_non_admin_user(self):
        user = self.env["res.users"].create({
            "name": "[AUTO TEST] Basic User",
            "login": "market-operations-basic-user",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            self.env["res.config.settings"].with_user(user).create({})._upsert_medical_test_data()

        self.assertEqual(self.env["psc.publishing.project"].search_count([
            ("name", "=", MEDICAL_TEST_PROJECT_NAME),
        ]), 1)
