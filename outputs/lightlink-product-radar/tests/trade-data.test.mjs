import test from "node:test";
import assert from "node:assert/strict";

import {
  groupTradeObservationPoints,
  isTradeCacheFresh,
  normalizeTradeObservation,
  tradeCollectionLevelForOpportunityStatus,
  tradeCoverageLevel,
  tradeCoverageSatisfies,
} from "../lib/trade-data.ts";
import { TRADE_SOURCE_CATALOG } from "../lib/trade-source-catalog.ts";

test("trade observations keep zero distinct from missing data", () => {
  const row = normalizeTradeObservation({
    reporterCode: "gb", commodityCode: "8516", commodityLabel: "Electrical appliances",
    period: "2025", value: 0, sourceName: "UN Comtrade", sourceUrl: "https://comtradeplus.un.org/",
    sourceGrade: "official", status: "available",
  });
  assert.equal(row.reporterCode, "GB");
  assert.equal(row.value, 0);
  assert.equal(row.status, "available");
});

test("missing trade observations require a reason and never accept a value", () => {
  assert.throws(() => normalizeTradeObservation({
    reporterCode: "GB", commodityCode: "8516", commodityLabel: "Electrical appliances",
    period: "2025", value: 10, sourceName: "UN Comtrade", sourceUrl: "https://comtradeplus.un.org/",
    status: "missing", missingReason: "尚未发布",
  }), /不能同时提供数值/);
});

test("trade cache freshness is explicit and deterministic", () => {
  const now = Date.parse("2026-09-17T00:00:00.000Z");
  assert.equal(isTradeCacheFresh("2026-08-01T00:00:00.000Z", now, 120), true);
  assert.equal(isTradeCacheFresh("2025-12-01T00:00:00.000Z", now, 120), false);
});

test("opportunity stages map to the three trade collection levels", () => {
  assert.equal(tradeCollectionLevelForOpportunityStatus("hypothesis"), "baseline");
  assert.equal(tradeCollectionLevelForOpportunityStatus("validating"), "trend");
  assert.equal(tradeCollectionLevelForOpportunityStatus("qualified"), "detail");
  assert.equal(tradeCollectionLevelForOpportunityStatus("pilot"), "detail");
});

test("trade coverage recognizes monthly trends and HS6 partner detail", () => {
  const collectedAt = "2026-09-17T00:00:00.000Z";
  const monthly = Array.from({ length: 24 }, (_, index) => ({
    period: `${2024 + Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`,
    frequency: "monthly",
    commodityCode: "4820",
    partnerCode: "WORLD",
    status: "available",
    collectedAt,
  }));
  const now = Date.parse("2026-09-18T00:00:00.000Z");
  assert.equal(tradeCoverageLevel(monthly, now), "trend");
  assert.equal(tradeCoverageSatisfies("trend", "baseline"), true);
  assert.equal(tradeCoverageSatisfies("trend", "detail"), false);
  assert.equal(tradeCoverageLevel([...monthly, {
    period: "2025",
    frequency: "annual",
    commodityCode: "482010",
    partnerCode: "CN",
    status: "available",
    collectedAt,
  }], now), "detail");
});

test("trade source catalog makes automation and user responsibility explicit", () => {
  assert.equal(TRADE_SOURCE_CATALOG.length >= 8, true);
  assert.equal(new Set(TRADE_SOURCE_CATALOG.map((item) => item.id)).size, TRADE_SOURCE_CATALOG.length);
  for (const source of TRADE_SOURCE_CATALOG) {
    assert.match(source.sourceUrl, /^https:\/\//);
    assert.match(source.docsUrl, /^https:\/\//);
    assert.equal(source.chatgptCanDo.length > 10, true, source.id);
    assert.equal(source.userMustDo.length > 5, true, source.id);
  }
});

test("trade observations from different currencies share one comparison point", () => {
  const rows = [
    { reporter_code: "DK", partner_code: "WORLD", classification: "HS2022", commodity_code: "847180", flow: "export", period: "2026-08", frequency: "monthly", metric: "trade_value_usd", source_name: "UN Comtrade" },
    { reporter_code: "DK", partner_code: "WORLD", classification: "HS2022", commodity_code: "847180", flow: "export", period: "2026-08", frequency: "monthly", metric: "trade_value_eur", source_name: "Eurostat Comext" },
    { reporter_code: "DK", partner_code: "WORLD", classification: "HS2022", commodity_code: "847180", flow: "export", period: "2026-08", frequency: "monthly", metric: "net_weight_kg", source_name: "Eurostat Comext" },
  ];
  const points = groupTradeObservationPoints(rows);
  assert.equal(points.length, 2);
  assert.equal(points.find((point) => point.rows.length === 2)?.rows.length, 2);
});
