import gzip

from odoo import tools
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


@tagged("post_install", "-at_install")
class TestSourcingContent(TransactionCase):
    def test_local_mirror_pages_are_imported_as_editable_records(self):
        website = self.env.ref("lightlink_sourcing_website.website_global_sourcing")
        self.assertIn("en_US", website.language_ids.mapped("code"))
        pages = self.env["ll.sourcing.content.page"].search([
            ("website_id", "=", website.id),
            ("imported_from_mirror", "=", True),
        ])
        self.assertGreaterEqual(len(pages), 800)
        home = pages.filtered(lambda page: page.source_path == "/")
        self.assertEqual(len(home), 1)
        self.assertTrue(home.body_html)
        self.assertTrue(home.source_stylesheets)
        self.assertTrue(home.source_style_hash)
        style_path = tools.file_path(
            "lightlink_sourcing_website/static/mirror_styles/%s.css.gz"
            % home.source_style_hash
        )
        with gzip.open(style_path, "rt", encoding="utf-8") as archive:
            self.assertIn(".elementor-", archive.read())
        self.assertTrue(website.sourcing_mirror_footer_html)
        home.body_html = home.body_html + "<p>Editable test</p>"
        self.assertIn("Editable test", home.body_html)

    def test_old_demo_content_is_removed(self):
        website = self.env.ref("lightlink_sourcing_website.website_global_sourcing")
        for model_name in (
            "ll.sourcing.offering", "ll.sourcing.asset", "ll.sourcing.metric",
            "ll.sourcing.testimonial", "ll.sourcing.payment.method",
            "ll.sourcing.footer.column",
        ):
            self.assertFalse(self.env[model_name].search([("website_id", "=", website.id)]))

    def test_navigation_and_product_category_landing_content(self):
        website = self.env.ref("lightlink_sourcing_website.website_global_sourcing")
        self.env["website"].initialize_lightlink_sourcing_site()
        services = self.env.ref("lightlink_sourcing_website.menu_sourcing_services")
        solutions = self.env.ref("lightlink_sourcing_website.menu_sourcing_solutions")
        self.assertEqual(services.parent_id, website.menu_id)
        self.assertEqual(len(services.child_id), 4)
        self.assertEqual(len(solutions.child_id), 7)

        self.assertEqual(
            self.env.ref("lightlink_sourcing_website.menu_sourcing_products").url,
            "/sourcing/site/our-products",
        )
        for source_path in (
            "/pricing", "/our-products", "/our-products/bags-sourcing",
            "/blog/c-import-from-china-guide",
            "/find-china-sourcing-agents-company", "/yiwu-china",
        ):
            self.assertEqual(self.env["ll.sourcing.content.page"].search_count([
                ("website_id", "=", website.id),
                ("source_path", "=", source_path),
                ("published", "=", True),
            ]), 1)

        custom_menu = self.env["website.menu"].create({
            "name": "Custom maintained link",
            "url": "/custom-maintained-link",
            "website_id": website.id,
            "parent_id": website.menu_id.id,
        })
        self.env["website"]._cleanup_lightlink_sourcing_bootstrap_menus()
        self.assertTrue(custom_menu.exists())

    def test_unverified_claims_cannot_be_published(self):
        website = self.env.ref("lightlink_sourcing_website.website_global_sourcing")
        with self.assertRaises(ValidationError):
            self.env["ll.sourcing.metric"].create({
                "website_id": website.id,
                "value_text": "100+",
                "label": "Unverified claim",
                "published": True,
            })
        with self.assertRaises(ValidationError):
            self.env["ll.sourcing.testimonial"].create({
                "website_id": website.id,
                "client_name": "Unverified customer",
                "quote": "Unverified feedback",
                "published": True,
            })

    def test_multi_website_operations_and_factory_content(self):
        sourcing_website = self.env.ref(
            "lightlink_sourcing_website.website_global_sourcing"
        )
        self.assertEqual(sourcing_website.ll_business_type, "sourcing_agency")
        self.assertTrue(sourcing_website.sourcing_enabled)

        factory_website = self.env["website"].create({
            "name": "Test Factory Website",
            "ll_business_type": "factory",
        })
        self.assertFalse(factory_website.sourcing_enabled)

        capability = self.env["ll.website.factory.capability"].create({
            "website_id": factory_website.id,
            "category": "production_line",
            "name": "Test production line",
            "summary": "Verified production line summary",
            "evidence_note": "Internal equipment register TEST-001",
            "verified": True,
            "published": True,
        })
        self.assertEqual(capability.website_id, factory_website)
        self.assertEqual(factory_website.ll_factory_capability_count, 1)

        product = self.env["product.template"].create({"name": "Test factory product"})
        presentation = self.env["ll.website.product.presentation"].create({
            "website_id": factory_website.id,
            "product_tmpl_id": product.id,
            "public_name": "Factory product for website",
            "summary": "Site-specific verified product summary",
            "evidence_note": "Internal product sheet TEST-PRODUCT-001",
            "verified": True,
            "published": True,
        })
        self.assertEqual(presentation.website_id, factory_website)
        self.assertEqual(factory_website.ll_product_presentation_count, 1)

        lead = self.env["crm.lead"].create({
            "name": "Factory website inquiry",
            "type": "lead",
            "ll_source_website_id": factory_website.id,
        })
        self.assertEqual(lead.ll_source_website_id, factory_website)

    def test_operations_navigation_keeps_site_context(self):
        website = self.env["website"].create({
            "name": "Operations navigation website",
            "ll_business_type": "factory",
            "homepage_url": "/factory-home",
        })

        related_action = website.action_ll_open_pages()
        self.assertEqual(related_action["target"], "current")
        self.assertIn(website.display_name, related_action["name"])
        self.assertEqual(related_action["context"]["default_website_id"], website.id)
        self.assertEqual(related_action["domain"], [("website_id", "=", website.id)])

        public_action = website.action_ll_open_public_site()
        self.assertEqual(public_action["target"], "new")
        self.assertIn("/website/force/%s?" % website.id, public_action["url"])
        self.assertIn("path=%2Ffactory-home", public_action["url"])

    def test_factory_claim_requires_evidence_before_publication(self):
        factory_website = self.env["website"].create({
            "name": "Unverified Factory Website",
            "ll_business_type": "factory",
        })
        with self.assertRaises(ValidationError):
            self.env["ll.website.factory.capability"].create({
                "website_id": factory_website.id,
                "category": "certification",
                "name": "Unverified certification",
                "summary": "Must not be published",
                "published": True,
            })
