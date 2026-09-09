from odoo.tests.common import TransactionCase

from ..models.res_config_settings import (
    MEDICAL_TEST_CHANNEL_NAME,
    MEDICAL_TEST_LEAD_NAME,
    MEDICAL_TEST_MARKET_NAME,
    MEDICAL_TEST_PRODUCT_LINE_CODE,
    MEDICAL_TEST_PRODUCT_NAMES,
    MEDICAL_TEST_PROJECT_NAME,
    MEDICAL_TEST_REQUIREMENT_NAME,
)


class MedicalTestDataCase(TransactionCase):
    def test_initializer_is_complete_and_idempotent(self):
        settings = self.env["res.config.settings"].create({})

        first_action = settings.action_prepare_medical_test_data()
        second_action = settings.action_prepare_medical_test_data()

        projects = self.env["psc.publishing.project"].search([
            ("name", "=", MEDICAL_TEST_PROJECT_NAME),
        ])
        self.assertEqual(len(projects), 1)
        project = projects.ensure_one()
        self.assertEqual(first_action["res_id"], project.id)
        self.assertEqual(second_action["res_id"], project.id)
        self.assertEqual(project.track_id.code, "medical")
        self.assertEqual(project.business_role_id.code, "integrator")
        self.assertEqual(set(project.product_ids.mapped("name")), set(MEDICAL_TEST_PRODUCT_NAMES))
        self.assertEqual(len(project.project_product_ids), 3)

        self.assertEqual(self.env["psc.product.line"].search_count([
            ("code", "=", MEDICAL_TEST_PRODUCT_LINE_CODE),
        ]), 1)
        self.assertEqual(self.env["psc.target.market"].search_count([
            ("name", "=", MEDICAL_TEST_MARKET_NAME),
        ]), 1)
        self.assertEqual(self.env["psc.publishing.channel"].search_count([
            ("name", "=", MEDICAL_TEST_CHANNEL_NAME),
        ]), 1)
        self.assertEqual(self.env["crm.lead"].search_count([
            ("name", "=", MEDICAL_TEST_LEAD_NAME), ("psc_project_id", "=", project.id),
        ]), 1)
        self.assertEqual(self.env["psc.customer.requirement"].search_count([
            ("name", "=", MEDICAL_TEST_REQUIREMENT_NAME), ("project_id", "=", project.id),
        ]), 1)
