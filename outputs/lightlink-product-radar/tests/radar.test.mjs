import assert from "node:assert/strict";
import test from "node:test";

import {
  COMMERCE_PLATFORMS,
  CORE_PLATFORMS,
  VALID_PLATFORMS,
  buyerIntentScore,
  computeScores,
  expandSeedKeyword,
  normalizeKeyword,
  safeCsvCell,
  splitKeywords,
} from "../lib/radar.ts";
import {
  LANGUAGE_OPTIONS,
  MARKET_OPTIONS,
  defaultLanguageForMarket,
  languageNameForCode,
  marketNameForCode,
} from "../lib/markets.ts";

const collectedAt = "2026-09-15T08:00:00.000Z";

function observation(overrides = {}) {
  return {
    keyword: "solar street light",
    groupName: "solar street light",
    aliases: [],
    category: "lighting",
    platform: "TikTok",
    metric: "attention",
    currentValue: 100,
    previousValue: 80,
    sampleN: 50,
    uniqueActorN: 30,
    coverageDays: 30,
    sourceKind: "official_export",
    sourceRef: "https://example.test/evidence",
    geoScope: "US",
    status: "ok",
    missingReason: null,
    collectedAt,
    ...overrides,
  };
}

test("normalizes and de-duplicates seed keywords", () => {
  assert.equal(normalizeKeyword("  #Solar–Street_Light  "), "solar street light");
  assert.deepEqual(splitKeywords("Solar light, solar light\nCamera light"), ["solar light", "camera light"]);
});

test("keeps multilingual keywords and expands common B2B languages", () => {
  assert.deepEqual(splitKeywords("太阳能路灯，lámpara solar；مصباح شمسي"), ["太阳能路灯", "lámpara solar", "مصباح شمسي"]);
  assert.ok(expandSeedKeyword("太阳能路灯", "zh").includes("太阳能路灯 批发"));
  assert.ok(expandSeedKeyword("lámpara solar", "es").includes("lámpara solar proveedor"));
});

test("market catalog covers major regions with valid default languages", () => {
  assert.ok(MARKET_OPTIONS.length >= 50);
  assert.equal(new Set(MARKET_OPTIONS.map((option) => option.code)).size, MARKET_OPTIONS.length);
  assert.equal(defaultLanguageForMarket("DE"), "de");
  assert.equal(defaultLanguageForMarket("BR"), "pt");
  assert.equal(marketNameForCode("pl"), "波兰");
  assert.equal(languageNameForCode("PL"), "波兰语");
  const languages = new Set(LANGUAGE_OPTIONS.map((option) => option.code));
  for (const market of MARKET_OPTIONS) assert.ok(languages.has(market.defaultLanguage));
});

test("source catalog separates score-critical sources from supplemental marketplaces", () => {
  assert.deepEqual(CORE_PLATFORMS, ["TikTok", "Meta Ads", "Instagram", "Google Trends", "Alibaba.com"]);
  for (const platform of ["Amazon", "Temu", "SHEIN", "eBay", "Walmart", "Etsy", "AliExpress", "Shopee", "Lazada", "Mercado Libre", "Rakuten"]) {
    assert.ok(COMMERCE_PLATFORMS.includes(platform));
    assert.ok(VALID_PLATFORMS.includes(platform));
  }
  assert.equal(new Set(VALID_PLATFORMS).size, VALID_PLATFORMS.length);
});

test("scores are deterministic for identical evidence", () => {
  const rows = [
    observation(),
    observation({ platform: "Meta Ads", metric: "commercial", currentValue: 40, previousValue: 30 }),
    observation({ platform: "Alibaba.com", metric: "competition", currentValue: 18, previousValue: 16 }),
  ];
  assert.deepEqual(computeScores(rows), computeScores(rows));
});

test("failed collection stays missing while a confirmed zero remains a valid zero", () => {
  const rows = [
    observation({ keyword: "missing product", currentValue: null, previousValue: null, status: "collection_error", missingReason: "request failed" }),
    observation({ keyword: "zero product", currentValue: 0, previousValue: 0, status: "confirmed_zero" }),
  ];
  const [missing, zero] = computeScores(rows);
  assert.equal(missing.canonicalKeyword, "missing product");
  assert.equal(missing.attentionLevel, null);
  assert.equal(missing.confidence, 0);
  assert.equal(zero.canonicalKeyword, "zero product");
  assert.equal(zero.attentionLevel, 50);
});

test("growth momentum preserves absolute direction", () => {
  const rows = [
    observation({ keyword: "slight decline", currentValue: 90, previousValue: 100 }),
    observation({ keyword: "large decline", currentValue: 10, previousValue: 20 }),
  ];
  for (const score of computeScores(rows)) assert.ok(score.momentum < 50);
});

test("assistant-only evidence cannot claim official-grade confidence", () => {
  const rows = [
    observation({ platform: "TikTok", sourceKind: "assistant" }),
    observation({ platform: "Meta Ads", metric: "commercial", sourceKind: "assistant" }),
    observation({ platform: "Instagram", sourceKind: "assistant" }),
    observation({ platform: "Alibaba.com", metric: "competition", sourceKind: "assistant" }),
  ];
  assert.ok(computeScores(rows)[0].confidence <= 70);
});

test("buyer terms improve intent without exceeding the score range", () => {
  assert.ok(buyerIntentScore("commercial solar light supplier") > buyerIntentScore("solar light home decor"));
  assert.ok(buyerIntentScore("supplier manufacturer factory wholesale oem odm") <= 100);
});

test("CSV export neutralizes formulas even after leading whitespace or control characters", () => {
  for (const value of ["=1+1", " +SUM(A1:A2)", "\t=CMD()", "\r@payload", "-2+3"]) {
    assert.match(safeCsvCell(value), /^['\"]/);
  }
  assert.equal(safeCsvCell("ordinary"), "ordinary");
});
