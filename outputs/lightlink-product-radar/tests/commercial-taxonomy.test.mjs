import test from "node:test";
import assert from "node:assert/strict";

import {
  BUYER_PERSONA_SEEDS,
  PERSONA_FAMILY_AFFINITY_SEEDS,
  PERSONA_TRACK_AFFINITY_SEEDS,
  PRODUCT_FAMILY_SEEDS,
  PRODUCT_TRACK_SEEDS,
  TRADE_REGION_SEEDS,
  regionCodeForCountry,
  suggestPersonaCode,
} from "../lib/commercial-taxonomy.ts";

test("commercial taxonomy has independent region, persona, track and family masters", () => {
  assert.equal(TRADE_REGION_SEEDS.filter((item) => item.code !== "GLOBAL").length, 14);
  assert.equal(BUYER_PERSONA_SEEDS.length, 57);
  assert.equal(PRODUCT_TRACK_SEEDS.length, 28);
  assert.equal(PRODUCT_FAMILY_SEEDS.length, 227);
  assert.equal(PERSONA_TRACK_AFFINITY_SEEDS.length, 240);
  assert.equal(PERSONA_FAMILY_AFFINITY_SEEDS.length, 501);
});

test("commercial taxonomy codes and references are valid", () => {
  const unique = (values) => new Set(values).size === values.length;
  assert.equal(unique(TRADE_REGION_SEEDS.map((item) => item.code)), true);
  assert.equal(unique(BUYER_PERSONA_SEEDS.map((item) => item.code)), true);
  assert.equal(unique(PRODUCT_TRACK_SEEDS.map((item) => item.code)), true);
  assert.equal(unique(PRODUCT_FAMILY_SEEDS.map((item) => item.code)), true);
  for (const persona of BUYER_PERSONA_SEEDS) {
    assert.equal(persona.sourceRefs.length >= 1, true, persona.code);
    assert.equal(persona.sourceRefs.every((url) => /^https:\/\//.test(url)), true, persona.code);
  }

  const personaCodes = new Set(BUYER_PERSONA_SEEDS.map((item) => item.code));
  const regionCodes = new Set(TRADE_REGION_SEEDS.map((item) => item.code));
  const trackCodes = new Set(PRODUCT_TRACK_SEEDS.map((item) => item.code));
  const familyByCode = new Map(PRODUCT_FAMILY_SEEDS.map((item) => [item.code, item]));
  for (const family of PRODUCT_FAMILY_SEEDS) assert.equal(trackCodes.has(family.trackCode), true, family.code);
  for (const link of PERSONA_TRACK_AFFINITY_SEEDS) {
    assert.equal(personaCodes.has(link.personaCode), true, link.personaCode);
    assert.equal(regionCodes.has(link.regionCode), true, link.regionCode);
    assert.equal(trackCodes.has(link.trackCode), true, link.trackCode);
  }
  const trackLinks = new Set(PERSONA_TRACK_AFFINITY_SEEDS.map((item) => `${item.personaCode}:${item.regionCode}:${item.trackCode}`));
  for (const link of PERSONA_FAMILY_AFFINITY_SEEDS) {
    const family = familyByCode.get(link.productFamilyCode);
    assert.ok(family, link.productFamilyCode);
    assert.equal(family.trackCode, link.trackCode, link.productFamilyCode);
    assert.equal(trackLinks.has(`${link.personaCode}:${link.regionCode}:${link.trackCode}`), true, link.productFamilyCode);
  }
});

test("product family depth follows track reality instead of a fixed quota", () => {
  const counts = PRODUCT_TRACK_SEEDS.map((track) => PRODUCT_FAMILY_SEEDS.filter((family) => family.trackCode === track.code).length);
  assert.equal(Math.min(...counts), 6);
  assert.equal(Math.max(...counts), 11);
  assert.equal(new Set(counts).size > 1, true);

  const personasWithFamilies = new Set(PERSONA_FAMILY_AFFINITY_SEEDS.map((item) => item.personaCode));
  for (const persona of BUYER_PERSONA_SEEDS) assert.equal(personasWithFamilies.has(persona.code), true, persona.code);
});

test("persona track breadth follows its product-family matrix instead of a fixed quota", () => {
  const trackCounts = BUYER_PERSONA_SEEDS.map((persona) => (
    PERSONA_TRACK_AFFINITY_SEEDS.filter((item) => item.personaCode === persona.code).length
  ));
  assert.equal(Math.min(...trackCounts), 2);
  assert.equal(Math.max(...trackCounts), 9);
  assert.equal(new Set(trackCounts).size, 8);

  const familyTracks = new Set(PERSONA_FAMILY_AFFINITY_SEEDS.map((item) => (
    `${item.personaCode}:${item.regionCode}:${item.trackCode}`
  )));
  for (const link of PERSONA_TRACK_AFFINITY_SEEDS) {
    assert.equal(
      familyTracks.has(`${link.personaCode}:${link.regionCode}:${link.trackCode}`),
      true,
      `${link.personaCode}:${link.trackCode}`,
    );
  }
});

test("country and legacy buyer text can be classified without defining the taxonomy", () => {
  assert.equal(regionCodeForCountry("US"), "NAM");
  assert.equal(regionCodeForCountry("DE"), "WEU");
  assert.equal(regionCodeForCountry("AE"), "WAS");
  assert.equal(regionCodeForCountry("unknown"), "GLOBAL");
  assert.equal(suggestPersonaCode("电子电气与工贸用品分销商"), "ELEC_MRO_DIST");
  assert.equal(suggestPersonaCode("Medical devices distributor"), "MEDICAL_DIST");
  assert.equal(suggestPersonaCode("Unclassified importer"), "GEN_IMPORT");
});
