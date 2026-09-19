import assert from "node:assert/strict";
import test from "node:test";

import {
  candidateHandoffReadiness,
  emptyCandidateSelectionAssessment,
  normalizeCandidateSelectionAssessment,
  selectionScoreTotal,
} from "../lib/candidate-selection.ts";

const completeCandidate = {
  target_markets: ["US"],
  buyer_types: ["办公用品分销商"],
  price_band: "USD 5-8",
  moq: "100件",
  compliance: ["FCC", "RoHS"],
  image_urls: ["https://example.com/product.jpg"],
  image_source_ref: "https://example.com/product",
  evidence_status: "partial",
};

const readyAssessment = {
  version: 1,
  scorecard: { demand: 20, economics: 16, supply: 12, compliance: 12, differentiation: 10, execution: 8 },
  channelFit: { alibaba: 80, social: 60, website: 70 },
  gates: { buyerDefined: true, economicsVerified: true, supplierVerified: true, complianceVerified: true, intellectualPropertyClear: true },
  decision: "ready",
  note: "已完成人工复核",
  assessedAt: "2026-09-17T00:00:00.000Z",
  assessedBy: "user",
};

test("selection score uses the fixed 100-point model", () => {
  assert.equal(selectionScoreTotal(normalizeCandidateSelectionAssessment(readyAssessment)), 78);
});

test("normalization clamps score and channel values", () => {
  const assessment = normalizeCandidateSelectionAssessment({
    scorecard: { demand: 99, economics: -1 },
    channelFit: { alibaba: 120 },
  });
  assert.equal(assessment.scorecard.demand, 25);
  assert.equal(assessment.scorecard.economics, 0);
  assert.equal(assessment.channelFit.alibaba, 100);
  assert.equal(assessment.channelFit.social, null);
});

test("handoff is ready only after score, gates, evidence and core fields pass", () => {
  const readiness = candidateHandoffReadiness(completeCandidate, readyAssessment);
  assert.equal(readiness.ready, true);
  assert.deepEqual(readiness.blockers, []);
});

test("handoff returns concrete blockers instead of silently exporting incomplete data", () => {
  const readiness = candidateHandoffReadiness({ ...completeCandidate, moq: "", image_urls: [] }, emptyCandidateSelectionAssessment());
  assert.equal(readiness.ready, false);
  assert.ok(readiness.blockers.includes("缺少 MOQ"));
  assert.ok(readiness.blockers.includes("缺少可追溯产品图片"));
  assert.ok(readiness.blockers.includes("人工决策尚未设为“可移交”"));
});
