import assert from "node:assert/strict";
import test from "node:test";

import { compactRadarStatus } from "../lib/radar-context.mjs";

test("compact radar status keeps scoring inputs and trims repeated metadata", () => {
  const status = compactRadarStatus({
    run: { id: "run-1", query: "鞋子" },
    sources: [{ platform: "Google Trends", source_refs: ["a", "b", "c", "d"], observation_count: 8 }],
    results: [{ canonical_keyword: "walking shoes", heat: 70, opportunity: 65, confidence: 80, rationale: "可核验" }],
    history: Array.from({ length: 8 }, (_, index) => ({ id: `run-${index}`, query: "鞋子" })),
    integrations: [{ id: "google_trends", name: "Google Trends", configured: true, docsUrl: "https://example.com/very-long-doc" }],
    observations: [{ raw_payload: "不进入默认上下文" }],
  });
  assert.equal(status.results[0].keyword, "walking shoes");
  assert.equal(status.results[0].opportunity, 65);
  assert.deepEqual(status.sources[0].sourceRefs, ["a", "b", "c"]);
  assert.equal(status.recentHistory.length, 5);
  assert.equal("docsUrl" in status.integrations[0], false);
  assert.equal("observations" in status, false);
});
