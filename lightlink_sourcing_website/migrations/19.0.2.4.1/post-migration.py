from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    category_assets = {
        "product_category_bags_cases": "asset_product_photography",
        "product_category_bags_handbags": "asset_product_development",
        "product_category_bags_backpacks": "asset_quality_inspection",
        "product_category_bags_toiletry": "asset_packaging_design",
        "product_category_bags_travel": "asset_shipping_consolidation",
        "product_category_bags_pouches": "asset_product_photography",
        "product_category_bags_special": "asset_factory_audit",
    }
    for category_xmlid, asset_xmlid in category_assets.items():
        category = env.ref(
            "lightlink_sourcing_website.%s" % category_xmlid,
            raise_if_not_found=False,
        )
        asset = env.ref(
            "lightlink_sourcing_website.%s" % asset_xmlid,
            raise_if_not_found=False,
        )
        if category and asset and not category.sourcing_image_asset_id:
            category.sourcing_image_asset_id = asset
