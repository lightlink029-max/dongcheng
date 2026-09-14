from odoo.tests import tagged
from odoo.tests.common import TransactionCase


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
