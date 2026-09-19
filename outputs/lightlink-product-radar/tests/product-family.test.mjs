import assert from "node:assert/strict";
import test from "node:test";

import { buildBuyerFamilyOpportunities, buildProductFamilySummaries } from "../lib/product-family.ts";

const candidates = [
  { id: "1", name: "USB桌面风扇", track_category: "办公舒适", subcategory: "桌面风扇", product_family: "USB桌面风扇", buyer_types: ["办公用品分销商"], target_markets: ["US"], evidence_status: "partial" },
  { id: "2", name: "USB夹扇", track_category: "办公舒适", subcategory: "桌面风扇", product_family: "USB桌面风扇", buyer_types: ["办公用品分销商"], target_markets: ["US", "GB"], evidence_status: "hypothesis" },
  { id: "3", name: "桌面理线器", track_category: "桌面配件", subcategory: "理线", product_family: "桌面线缆管理", buyer_types: ["办公用品分销商"], target_markets: ["GB"], evidence_status: "validated" },
];

test("product families group variants without losing track and market coverage", () => {
  const families = buildProductFamilySummaries(candidates);
  assert.equal(families.length, 2);
  assert.equal(families[0].candidateCount, 2);
  assert.deepEqual(families[0].markets.sort(), ["GB", "US"]);
});

test("buyer opportunities reveal cross-track purchasing combinations", () => {
  const opportunities = buildBuyerFamilyOpportunities(candidates);
  assert.equal(opportunities[0].buyerType, "办公用品分销商");
  assert.equal(opportunities[0].familyCount, 2);
  assert.equal(opportunities[0].trackCount, 2);
  assert.ok(opportunities[0].relationshipScore > 40);
});
