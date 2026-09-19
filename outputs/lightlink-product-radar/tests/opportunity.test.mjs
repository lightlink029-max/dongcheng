import test from "node:test";
import assert from "node:assert/strict";

import {
  OPPORTUNITY_VALIDATION_PLAN,
  buildOpportunityDecision,
  computeOpportunityScores,
  isOpportunityValidationStepDone,
  normalizeOpportunitySignals,
  opportunityValidationPrerequisite,
  suggestOpportunitySignals,
} from "../lib/opportunity.ts";

test("opportunity scores remain incomplete until enough signals exist", () => {
  const result = computeOpportunityScores({ tradeTrend: 80 }, ["official"]);
  assert.equal(result.marketScore, null);
  assert.equal(result.buyerScore, null);
  assert.equal(result.recommendedAction, "continue_validation");
});

test("opportunity scores keep market, buyer and sourcing decisions separate", () => {
  const result = computeOpportunityScores({
    tradeTrend: 82, buyerDemand: 78, channelSignal: 74,
    personaFit: 85, leadQuality: 76, repeatPotential: 72,
    supplierCoverage: 70, unitEconomics: 75, complianceReadiness: 68,
  }, ["official", "verified_buyer", "supplier_quote", "internal_odoo"]);
  assert.equal(result.marketScore, 78);
  assert.equal(result.buyerScore, 78);
  assert.equal(result.sourcingScore, 71);
  assert.equal(result.recommendedAction, "pilot");
});

test("low sourcing readiness recommends supplier development after demand is supported", () => {
  const result = computeOpportunityScores({
    tradeTrend: 75, buyerDemand: 72, channelSignal: 70,
    supplierCoverage: 30, unitEconomics: 38, complianceReadiness: 40,
  }, ["official", "verified_buyer", "marketplace", "other"]);
  assert.equal(result.marketScore, 73);
  assert.equal(result.sourcingScore, 36);
  assert.equal(result.recommendedAction, "source_suppliers");
});

test("signal normalization clamps values and preserves missing data", () => {
  const signals = normalizeOpportunitySignals({ tradeTrend: 140, buyerDemand: -4, channelSignal: "" });
  assert.equal(signals.tradeTrend, 100);
  assert.equal(signals.buyerDemand, 0);
  assert.equal(signals.channelSignal, null);
});

test("evidence pre-assessment fills supported fields and preserves unknowns", () => {
  const suggestion = suggestOpportunitySignals({
    personaMatrixScore: 82,
    tradeRows: [2021, 2022, 2023, 2024, 2025].map((year, index) => ({
      reporter_code: "GB", commodity_code: "847180", flow: "import", period: String(year), frequency: "annual",
      metric: "trade_value_usd", source_name: "UN Comtrade", data_status: "available", value: 100 + index * 10,
    })),
    evidence: [
      { evidence_type: "buyer", source_grade: "verified_buyer", metrics: { buyer_count: 1 } },
      { evidence_type: "supply", source_grade: "supplier_quote", metrics: { supplier_count: 3, gross_margin_pct: 24 } },
    ],
  });
  assert.equal(suggestion.signals.tradeTrend, 85);
  assert.equal(suggestion.signals.personaFit, null);
  assert.equal(suggestion.signals.buyerDemand, 63);
  assert.equal(suggestion.signals.supplierCoverage, 69);
  assert.equal(suggestion.signals.unitEconomics, 70);
  assert.equal(suggestion.signals.repeatPotential, null);
  assert.equal(suggestion.humanRequiredFields.includes("repeatPotential"), true);
});

test("pre-assessment never turns missing evidence into zero", () => {
  const suggestion = suggestOpportunitySignals({ evidence: [], tradeRows: [], personaMatrixScore: null });
  assert.deepEqual(suggestion.automatedFields, []);
  assert.equal(Object.values(suggestion.signals).every((value) => value === null), true);
});

test("strong trade and persona fit recommend a low-cost buyer validation instead of stocking", () => {
  const decision = buildOpportunityDecision({ tradeTrend: 85, personaFit: 96 });
  assert.equal(decision.status, "validate_buyers");
  assert.match(decision.headline, /低成本买家验证/);
  assert.match(decision.doNotDo, /不要备货/);
  assert.equal(decision.readiness, 22);
});

test("opportunity decision requires buyer proof and delivery proof before a pilot", () => {
  const buyerDecision = buildOpportunityDecision({
    tradeTrend: 75, buyerDemand: 72, channelSignal: 68,
    personaFit: 85, leadQuality: 70,
  });
  assert.equal(buyerDecision.status, "validate_supply");

  const pilotDecision = buildOpportunityDecision({
    tradeTrend: 75, buyerDemand: 72, channelSignal: 68,
    personaFit: 85, leadQuality: 70, repeatPotential: 62,
    supplierCoverage: 70, unitEconomics: 68, complianceReadiness: 72,
  });
  assert.equal(pilotDecision.status, "pilot_ready");
});

test("public buyer pages remain weak evidence until a buyer is verified", () => {
  const suggestion = suggestOpportunitySignals({
    evidence: [1, 2, 3, 4].map((index) => ({ evidence_type: "buyer", source_grade: "other", metrics: { public_buyer: index } })),
  });
  assert.equal(suggestion.signals.buyerDemand, null);
  assert.equal(suggestion.signals.leadQuality, null);
});

test("validation plan follows the real trade sequence and keeps fulfillment last", () => {
  assert.deepEqual(OPPORTUNITY_VALIDATION_PLAN.map((step) => step.key), [
    "public_evidence", "buyer_discovery", "offer_matrix", "supplier_feasibility",
    "economics_compliance", "buyer_offer_validation", "pilot_fulfillment",
  ]);
});

test("customer discovery and offer matrix require direct structured evidence", () => {
  const publicEvidence = [
    { evidence_type: "buyer", source_grade: "other", metrics: {} },
    { evidence_type: "channel", source_grade: "marketplace", metrics: {} },
  ];
  assert.equal(isOpportunityValidationStepDone("public_evidence", publicEvidence), true);
  assert.equal(opportunityValidationPrerequisite("buyer_discovery", publicEvidence), null);
  assert.equal(isOpportunityValidationStepDone("buyer_discovery", publicEvidence), false);

  const discoveryEvidence = [...publicEvidence, {
    evidence_type: "buyer_discovery", source_grade: "verified_buyer", metrics: { qualified_discovery_count: 3 },
  }];
  assert.equal(isOpportunityValidationStepDone("buyer_discovery", discoveryEvidence), true);
  assert.equal(opportunityValidationPrerequisite("offer_matrix", discoveryEvidence), null);
  assert.equal(isOpportunityValidationStepDone("offer_matrix", discoveryEvidence), false);
});

test("supplier capability is not complete until a real fulfillment result exists", () => {
  const evidence = [
    { evidence_type: "fulfillment", source_grade: "internal_odoo", metrics: { completed_order_count: 1 } },
  ];
  assert.equal(isOpportunityValidationStepDone("pilot_fulfillment", evidence), false);
  evidence.push({ evidence_type: "fulfillment", source_grade: "internal_odoo", metrics: { inspection_pass_rate: 100 } });
  assert.equal(isOpportunityValidationStepDone("pilot_fulfillment", evidence), true);
});
