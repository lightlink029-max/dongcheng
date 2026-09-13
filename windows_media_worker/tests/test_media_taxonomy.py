import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from media_taxonomy import asset_match, filter_media, normalize_tags, rank_assets


class MediaTaxonomyTests(unittest.TestCase):
    def test_normalize_tags_accepts_chinese_separators_and_deduplicates(self):
        self.assertEqual(
            normalize_tags("工厂，仓库;工厂\n发货"),
            ["工厂", "仓库", "发货"],
        )

    def test_explicit_filters_combine_role_scene_usage_and_keyword(self):
        records = [{
            "name": "广州仓装柜", "role_tags": ["供应链服务商"],
            "scene_tags": ["仓库", "装货"], "usage_tags": ["交付证明"],
            "custom_tags": ["运动鞋"],
        }, {
            "name": "办公室口播", "role_tags": ["外贸公司"],
            "scene_tags": ["办公室"], "usage_tags": ["身份开场"],
            "custom_tags": [],
        }]
        result = filter_media(
            records, role="供应链服务商", scene="装货",
            usage="交付证明", keyword="运动鞋",
        )
        self.assertEqual([item["name"] for item in result], ["广州仓装柜"])

    def test_plan_matching_ranks_exact_scene_and_purpose_first(self):
        slot = {
            "name": "身份开场", "purpose": "说明我们是谁",
            "visual_requirement": "办公室、厂房或团队真实环境的建立镜头",
        }
        task = {"business_role": {"code": "trading_company", "name": "外贸公司"}}
        exact = {
            "name": "办公室开场", "role_tags": ["外贸公司"],
            "scene_tags": ["办公室"], "usage_tags": ["身份开场"],
        }
        unrelated = {
            "name": "仓库发货", "role_tags": ["供应链服务商"],
            "scene_tags": ["仓库", "发货"], "usage_tags": ["交付证明"],
        }
        self.assertEqual(asset_match(exact, slot, task)["level"], "完全匹配")
        ranked = rank_assets([unrelated, exact], slot, task)
        self.assertEqual(ranked[0][1]["name"], "办公室开场")
        self.assertEqual(rank_assets([unrelated, exact], slot, task, mode="exact")[0][1], exact)


if __name__ == "__main__":
    unittest.main()
