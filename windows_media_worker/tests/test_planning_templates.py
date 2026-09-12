import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planning_templates import build_video_plan, fallback_options


class PlanningTemplateTests(unittest.TestCase):
    def test_fallback_catalog_uses_odoo_master_codes(self):
        options = fallback_options()
        self.assertIn("trading_company", {item["code"] for item in options["roles"]})
        self.assertIn("footwear_apparel", {item["code"] for item in options["tracks"]})
        self.assertIn("packaging_delivery", {item["code"] for item in options["scopes"]})

    def test_video_plan_builds_ordered_storyboard_for_selected_template(self):
        plan = build_video_plan(
            fallback_options(), "trading_company", "footwear_apparel",
            "packaging_delivery", 30,
        )

        self.assertEqual(plan["role"]["name"], "外贸公司")
        self.assertEqual(plan["scope"]["name"], "包装、验货与交付")
        self.assertEqual(len(plan["storyboard"]), 4)
        self.assertEqual(sum(item["target_duration"] for item in plan["storyboard"]), 30)
        self.assertTrue(all(item["visual_requirement"] for item in plan["storyboard"]))

    def test_live_odoo_guide_overrides_fallback_copy_and_evidence(self):
        options = fallback_options()
        options["guides"] = [{
            "role_code": "trading_company", "track_code": "footwear_apparel",
            "scope_code": "product_category", "execution_goal": "Odoo目标",
            "copy_template_zh": "Odoo文案模板", "required_evidence": "Odoo画面证据",
        }]

        plan = build_video_plan(
            options, "trading_company", "footwear_apparel", "product_category", 20,
        )

        self.assertEqual(plan["goal"], "Odoo目标")
        self.assertEqual(plan["copy_template"], "Odoo文案模板")
        self.assertTrue(all("Odoo画面证据" in item["visual_requirement"] for item in plan["storyboard"]))


if __name__ == "__main__":
    unittest.main()
