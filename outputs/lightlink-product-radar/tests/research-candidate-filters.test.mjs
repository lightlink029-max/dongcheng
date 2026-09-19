import assert from "node:assert/strict";
import test from "node:test";

import { matchesResearchCandidateFilters } from "../lib/research-candidate-filters.ts";

const candidate = {
  name: "USB桌面风扇",
  track_category: "USB桌面舒适用品",
  subcategory: "桌面风扇",
  commercial_variant: "5V有线礼赠款",
  target_markets: ["GB", "US"],
  buyer_types: ["礼赠品公司", "办公用品分销商"],
  price_band: "USD 3.39–6.49",
  moq: "100件",
  compliance: ["FCC", "RoHS"],
  risk_level: "medium",
  stage: "shortlist",
};

const defaults = { search: "", buyerTypes: [], conditions: "", tracks: [], markets: [], risks: [], stages: ["active"] };

test("buyer types and commercial conditions are independent filters", () => {
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, buyerTypes: ["礼赠品公司"] }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, buyerTypes: ["医疗进口商", "办公用品分销商"] }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, buyerTypes: ["医疗进口商"] }), false);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, conditions: "MOQ" }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, conditions: "100件" }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, conditions: "RoHS" }), true);
});

test("product search no longer conflates buyer and market fields", () => {
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, search: "桌面风扇" }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, search: "礼赠品公司" }), false);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, markets: ["DE", "US"] }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, markets: ["DE", "AU"] }), false);
});

test("default stage keeps rejected products hidden", () => {
  assert.equal(matchesResearchCandidateFilters({ ...candidate, stage: "rejected" }, defaults), false);
  assert.equal(matchesResearchCandidateFilters({ ...candidate, stage: "rejected" }, { ...defaults, stages: [] }), true);
});

test("track, risk and stage selections use OR within each field", () => {
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, tracks: ["医疗电子", "USB桌面舒适用品"] }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, risks: ["low", "medium"] }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, stages: ["sample", "shortlist"] }), true);
  assert.equal(matchesResearchCandidateFilters(candidate, { ...defaults, stages: ["sample", "validation"] }), false);
});
