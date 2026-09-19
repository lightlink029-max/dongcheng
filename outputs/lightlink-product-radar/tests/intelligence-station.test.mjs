import assert from "node:assert/strict";
import test from "node:test";

import {
  INTELLIGENCE_SOURCE_CATALOG,
  MARKET_SIGNAL_LAYERS,
  TRIGGER_CATALOG,
  assessSignalOpportunity,
  marketSignalFingerprint,
  monitorScopeKey,
  simulateMonitorScenario,
  triggerById,
} from "../lib/intelligence-station.ts";
import { collectOfficialTradeSignals, normalizeCommodityCodes } from "../lib/intelligence-connectors.ts";

test("market signals remain separated by evidence meaning", () => {
  assert.deepEqual(
    MARKET_SIGNAL_LAYERS.map((item) => item.id),
    ["event", "attention", "b2b_demand", "supply_competition", "official_trade", "regulation", "internal"],
  );
});

test("trigger catalog covers recurring, event, risk, regulation and attention triggers", () => {
  const categories = new Set(TRIGGER_CATALOG.map((item) => item.category));
  for (const category of ["seasonal", "event", "macro_risk", "weather_health", "regulation", "industry", "procurement", "attention"]) {
    assert.equal(categories.has(category), true);
  }
  assert.equal(triggerById("back_to_school")?.name, "返校季");
  assert.equal(triggerById("sports_event")?.name, "大型赛事");
});

test("monitor scope deduplicates spacing and case but keeps business dimensions", () => {
  const first = monitorScopeKey({ regionCode: " UK ", triggerType: "Back_To_School", triggerName: "  Back   to School ", personaCode: "DIST", productFamilyCode: "BAG" });
  const second = monitorScopeKey({ regionCode: "uk", triggerType: "back_to_school", triggerName: "back to school", personaCode: "dist", productFamilyCode: "bag" });
  assert.equal(first, second);
  assert.notEqual(first, monitorScopeKey({ regionCode: "US", triggerType: "back_to_school", triggerName: "back to school", personaCode: "dist", productFamilyCode: "bag" }));
});

test("source catalog includes official trade, B2B and attention sources", () => {
  const ids = new Set(INTELLIGENCE_SOURCE_CATALOG.map((item) => item.id));
  for (const id of ["un_comtrade", "alibaba_b2b", "made_in_china", "google", "tiktok", "odoo_sales"]) assert.equal(ids.has(id), true);
  assert.equal(INTELLIGENCE_SOURCE_CATALOG.find((item) => item.id === "made_in_china")?.signalTypes.includes("attention"), false);
});

test("signal fingerprint reuses the same fact across monitors but keeps business dimensions", () => {
  const first = marketSignalFingerprint({ sourceId: "UN Comtrade", signalType: "official_trade", regionCode: " UK ", productFamilyCode: "BAG", commodityCode: "4202", period: "2026-01", metric: "import_value" });
  const second = marketSignalFingerprint({ sourceId: "un comtrade", signalType: "OFFICIAL_TRADE", regionCode: "uk", productFamilyCode: "bag", commodityCode: "4202", period: "2026-01", metric: "import_value" });
  assert.equal(first, second);
  assert.notEqual(first, marketSignalFingerprint({ sourceId: "un comtrade", signalType: "official_trade", regionCode: "DE", productFamilyCode: "bag", commodityCode: "4202", period: "2026-01", metric: "import_value" }));
});

test("candidate review requires cross-source demand evidence", () => {
  const attentionOnly = assessSignalOpportunity([
    { id: "a", signalType: "attention", sourceId: "google", dataStatus: "available", evidenceGrade: "primary", direction: "rising", confidence: 80 },
    { id: "b", signalType: "event", sourceId: "calendar", dataStatus: "available", evidenceGrade: "official", confidence: 90 },
  ]);
  assert.equal(attentionOnly.readyForReview, false);
  assert.equal(attentionOnly.opportunityType, "observe");

  const crossValidated = assessSignalOpportunity([
    { id: "a", signalType: "official_trade", sourceId: "un_comtrade", dataStatus: "available", evidenceGrade: "official", direction: "rising", period: "2025", confidence: 80 },
    { id: "b", signalType: "supply_competition", sourceId: "made_in_china", dataStatus: "available", evidenceGrade: "primary", direction: "limited", confidence: 70 },
  ]);
  assert.equal(crossValidated.readyForReview, true);
  assert.equal(crossValidated.opportunityType, "blue_ocean_candidate");
  assert.deepEqual(crossValidated.blockers, []);
});

test("monitor simulations exercise downstream gates without producing formal signals", () => {
  const ready = simulateMonitorScenario("candidate_ready");
  assert.equal(ready.simulation, true);
  assert.equal(ready.runStatus, "completed");
  assert.equal(ready.assessment.readyForReview, true);
  assert.equal(ready.pipelineSteps.find((step) => step.id === "candidate_review")?.status, "ready");
  assert.equal(ready.pipelineSteps.find((step) => step.id === "validation_round")?.status, "not_started");

  const attentionOnly = simulateMonitorScenario("attention_only");
  assert.equal(attentionOnly.assessment.readyForReview, false);
  assert.equal(attentionOnly.pipelineSteps.find((step) => step.id === "evidence_gate")?.status, "blocked");

  const missing = simulateMonitorScenario("missing_data");
  assert.equal(missing.runStatus, "waiting_for_data");

  const failure = simulateMonitorScenario("source_failure");
  assert.equal(failure.runStatus, "failed");
});

test("commodity codes are normalized, deduplicated and limited to supported HS/CN levels", () => {
  assert.deepEqual(normalizeCommodityCodes([" HS 85 ", "8517", "8517", "85171300", "851", "invalid"]), ["85", "8517", "85171300"]);
});

test("official connectors normalize UN, Eurostat and HMRC responses into one observation model", async () => {
  const fetchImpl = async (input) => {
    const url = String(input);
    if (url.includes("comtradeapi.un.org")) return new Response(JSON.stringify({ data: [{ reporterISO: "DE", cmdCode: "85", period: "2025", primaryValue: 1200, netWgt: 42 }] }), { status: 200 });
    if (url.includes("ec.europa.eu/eurostat")) return new Response(JSON.stringify({
      id: ["freq", "reporter", "partner", "product", "flow", "indicators", "time"],
      size: [1, 1, 1, 1, 1, 1, 1],
      dimension: {
        freq: { category: { index: { M: 0 } } }, reporter: { category: { index: { DE: 0 } } },
        partner: { category: { index: { WORLD: 0 } } }, product: { category: { index: { 85: 0 } } },
        flow: { category: { index: { 1: 0 } } }, indicators: { category: { index: { VALUE_IN_EUROS: 0 } } },
        time: { category: { index: { "2026-08": 0 } } },
      },
      value: { 0: 900 },
    }), { status: 200 });
    if (url.includes("api.uktradeinfo.com")) return new Response(JSON.stringify({ value: [{ MonthId: 202608, TotalValue: 700, TotalNetMass: 18 }] }), { status: 200 });
    throw new Error(`unexpected URL ${url}`);
  };

  const results = await collectOfficialTradeSignals({
    regionCode: "GLOBAL",
    countryCodes: ["DE", "GB"],
    commodityCodes: ["85"],
    sourceIds: ["un_comtrade", "eurostat_comext", "uk_hmrc"],
    now: new Date("2026-09-19T00:00:00Z"),
    fetchImpl,
  });

  assert.deepEqual(results.map((result) => result.status), ["completed", "completed", "completed"]);
  assert.equal(results.every((result) => result.observations.length > 0), true);
  assert.equal(results.flatMap((result) => result.observations).every((item) => item.metric && item.period && item.sourceUrl), true);
});

test("official connector retries transient errors once but never retries permission failures", async () => {
  let transientCalls = 0;
  const transient = await collectOfficialTradeSignals({
    regionCode: "DE",
    countryCodes: ["DE"],
    commodityCodes: ["85"],
    sourceIds: ["un_comtrade"],
    now: new Date("2026-09-19T00:00:00Z"),
    fetchImpl: async () => {
      transientCalls += 1;
      if (transientCalls === 1) return new Response("temporary", { status: 503 });
      return new Response(JSON.stringify({ data: [{ reporterISO: "DE", cmdCode: "85", period: "2025", primaryValue: 1 }] }), { status: 200 });
    },
  });
  assert.equal(transient[0].status, "completed");
  assert.equal(transient[0].retryCount, 1);
  assert.equal(transientCalls, 3);

  let permissionCalls = 0;
  const permission = await collectOfficialTradeSignals({
    regionCode: "DE",
    countryCodes: ["DE"],
    commodityCodes: ["85"],
    sourceIds: ["un_comtrade"],
    fetchImpl: async () => {
      permissionCalls += 1;
      return new Response("forbidden", { status: 403 });
    },
  });
  assert.equal(permission[0].status, "failed");
  assert.equal(permission[0].errorCategory, "permission");
  assert.equal(permissionCalls, 1);
});
