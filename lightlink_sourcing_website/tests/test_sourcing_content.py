from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


@tagged("post_install", "-at_install")
class TestSourcingContent(TransactionCase):
    def test_bilingual_content_and_expanded_services(self):
        website = self.env.ref("lightlink_sourcing_website.website_global_sourcing")
        self.assertIn("en_US", website.language_ids.mapped("code"))
        chinese = self.env["res.lang"].search([
            ("code", "=", "zh_CN"), ("active", "=", True),
        ], limit=1)

        service = self.env.ref(
            "lightlink_sourcing_website.offering_product_photography_video"
        )
        self.assertEqual(
            service.with_context(lang="en_US").name,
            "Product Photography & Video",
        )
        if chinese:
            self.assertIn("zh_CN", website.language_ids.mapped("code"))
            self.assertEqual(
                service.with_context(lang="zh_CN").name,
                "产品摄影与视频",
            )
        self.assertEqual(service.request_type, "photography_video")

        offerings = self.env["ll.sourcing.offering"].search([
            ("website_id", "=", website.id),
            ("active", "=", True),
        ])
        self.assertEqual(len(offerings.filtered(lambda item: item.kind == "service")), 12)
        self.assertEqual(len(offerings.filtered(lambda item: item.kind == "solution")), 5)
        self.assertEqual(len(offerings.filtered(lambda item: item.kind == "plan")), 2)

        guide = self.env.ref("lightlink_sourcing_website.page_importing_from_china")
        self.assertEqual(
            guide.with_context(lang="en_US").name,
            "Importing from China: Working Guide",
        )
        self.assertEqual(len(guide.chapter_ids.filtered("published")), 10)
        categories = self.env["product.public.category"].search([
            ("website_id", "=", website.id), ("parent_id", "=", False),
        ])
        self.assertGreaterEqual(len(categories), 20)
        if chinese:
            self.assertEqual(
                guide.with_context(lang="zh_CN").name,
                "从中国进口：实操指南",
            )

    def test_footer_and_safe_draft_content(self):
        website = self.env.ref("lightlink_sourcing_website.website_global_sourcing")
        footer_columns = self.env["ll.sourcing.footer.column"].search([
            ("website_id", "=", website.id), ("active", "=", True),
        ])
        self.assertGreaterEqual(len(footer_columns), 5)
        self.assertEqual(len(footer_columns.filtered("published")), 3)
        product_link = self.env.ref("lightlink_sourcing_website.footer_link_products")
        self.assertEqual(product_link.url, "/sourcing/products")
        payment_drafts = self.env["ll.sourcing.payment.method"].search([
            ("website_id", "=", website.id), ("active", "=", True),
        ])
        self.assertGreaterEqual(len(payment_drafts), 3)
        self.assertFalse(payment_drafts.filtered("published"))

    def test_navigation_and_product_category_landing_content(self):
        website = self.env.ref("lightlink_sourcing_website.website_global_sourcing")
        self.env["website"].initialize_lightlink_sourcing_site()
        services = self.env.ref("lightlink_sourcing_website.menu_sourcing_services")
        solutions = self.env.ref("lightlink_sourcing_website.menu_sourcing_solutions")
        self.assertEqual(services.parent_id, website.menu_id)
        self.assertEqual(len(services.child_id), 4)
        self.assertEqual(len(solutions.child_id), 7)

        bags = self.env.ref("lightlink_sourcing_website.product_category_bags_cases")
        self.assertEqual(bags.website_id, website)
        self.assertEqual(len(bags.child_id), 6)
        self.assertTrue(bags.sourcing_hero_subtitle)
        self.assertTrue(bags.sourcing_inquiry_heading)

        visit_yiwu = self.env.ref("lightlink_sourcing_website.page_visit_yiwu")
        yiwu_pages = self.env["ll.sourcing.content.page"].search([
            ("website_id", "=", website.id),
            ("code", "like", "yiwu-%"),
            ("published", "=", True),
        ])
        self.assertTrue(visit_yiwu.published)
        self.assertEqual(len(yiwu_pages), 7)

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

    def test_generated_assets_are_attached(self):
        for xmlid in (
            "asset_dropshipping_fulfillment",
            "asset_product_photography",
            "asset_packaging_design",
            "asset_warehousing_kitting",
            "asset_factory_audit",
        ):
            asset = self.env.ref("lightlink_sourcing_website.%s" % xmlid)
            self.assertTrue(asset.image)
            self.assertTrue(asset.alt_text)
