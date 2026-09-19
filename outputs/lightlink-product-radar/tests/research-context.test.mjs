import assert from "node:assert/strict";
import test from "node:test";

import { compactResearchStatus } from "../lib/research-context.mjs";

const data = {
  project: {
    id: "project-1",
    product_name: "电子产品外贸",
    target_markets: ["GB", "US"],
    target_candidate_count: 2000,
    candidate_count: 2,
    run_count: 3,
    evidence_count: 2,
  },
  runs: [
    { id: "pending", status: "waiting_for_codex", request_payload: { runMode: "expand_candidates" } },
    {
      id: "complete",
      status: "complete",
      result_payload: {
        summary: "已有完整报告",
        trackCategories: [{ name: "家用测量" }],
        marketHypotheses: [{ marketCode: "GB" }],
        productPool: [{ name: "不应重复输出的完整产品" }],
        evidence: [{ sourceUrl: "https://example.com/full" }],
      },
    },
  ],
  candidates: [
    { id: "c1", name: "电子量杯", track_category: "家用测量", stage: "research", target_markets: ["GB"], image_urls: [] },
    { id: "c2", name: "数字厨房秤", track_category: "家用测量", stage: "idea", target_markets: ["US"], image_urls: ["https://example.com/image.jpg"] },
  ],
  evidence: [
    { source_title: "官方规则", source_url: "https://example.com/rule", source_type: "official", market: "GB", status: "available" },
    { source_title: "公开商品", source_url: "https://example.com/item", source_type: "marketplace", market: "US", status: "available" },
  ],
  activities: [{ note: "大量历史不应进入上下文" }],
  marketActivities: [{ note: "大量市场历史不应进入上下文" }],
};

test("compact research status keeps decisions while dropping bulky history", () => {
  const status = compactResearchStatus(data);
  assert.equal(status.activeTask.runId, "pending");
  assert.equal(status.latestReport.summary, "已有完整报告");
  assert.deepEqual(status.candidateNames, ["电子量杯", "数字厨房秤"]);
  assert.equal(status.candidateStats.withImages, 1);
  assert.equal(status.evidenceSummary.bySourceType.official, 1);
  assert.equal("runs" in status, false);
  assert.equal("activities" in status, false);
  assert.equal("productPool" in status.latestReport, false);
  assert.equal("evidence" in status.latestReport, false);
});

test("candidate assistance receives only the requested candidate detail", () => {
  const status = compactResearchStatus(data, { candidateId: "c1" });
  assert.equal(status.candidate.id, "c1");
  assert.equal(status.candidate.name, "电子量杯");
  assert.equal("candidateNames" in status, false);
  assert.equal("candidates" in status, false);
  assert.equal("trackCategories" in status.latestReport, false);
});

test("review mode retains compact details for all candidates", () => {
  const status = compactResearchStatus(data, { includeCandidates: true });
  assert.equal(status.candidates.length, 2);
  assert.deepEqual(status.candidates[1].targetMarkets, ["US"]);
  assert.equal("candidateNames" in status, false);
  assert.deepEqual(status.latestReport.trackCategories, [{ name: "家用测量" }]);
});
