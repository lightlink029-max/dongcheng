import assert from "node:assert/strict";
import test from "node:test";

import {
  latestResearchReportRun,
  mergeResearchReports,
} from "../lib/research-versions.ts";

test("pending research runs do not hide the latest completed report", () => {
  const completed = {
    id: "completed",
    status: "complete",
    result_payload: { summary: "上一版完整报告", trackCategories: [{ name: "家用测量" }] },
  };
  const selected = latestResearchReportRun([
    { id: "pending", status: "waiting_for_codex", result_payload: {} },
    completed,
  ]);
  assert.equal(selected?.id, "completed");
});

test("incremental research imports preserve and extend prior structured data", () => {
  const previous = {
    summary: "上一版",
    trackCategories: [{ id: "measurement", name: "家用测量", subcategories: ["厨房计量"], targetMarkets: ["GB"] }],
    productPool: [{ name: "数字厨房秤", trackCategory: "家用测量", subcategory: "厨房计量", targetMarkets: ["GB"] }],
    marketHypotheses: [{ marketCode: "GB", marketName: "英国", buyerTypes: ["进口商"] }],
    playbook: { roadmap180Days: { summary: "旧路线", items: ["验证样品"] } },
  };
  const merged = mergeResearchReports(previous, {
    summary: "本轮新增产品",
    trackCategories: [],
    productPool: [{ name: "咖啡电子秤", trackCategory: "家用测量", subcategory: "厨房计量", targetMarkets: ["US"] }],
    marketHypotheses: [],
    playbook: {},
  });
  assert.equal(merged.summary, "本轮新增产品");
  assert.equal(merged.trackCategories.length, 1);
  assert.equal(merged.marketHypotheses.length, 1);
  assert.equal(merged.productPool.length, 2);
  assert.deepEqual(merged.playbook, previous.playbook);
});

test("matching tracks and markets are updated without discarding existing fields", () => {
  const merged = mergeResearchReports(
    {
      trackCategories: [{ name: "家用测量", description: "旧说明", buyerTypes: ["进口商"] }],
      marketHypotheses: [{ marketCode: "GB", marketName: "英国", buyerTypes: ["进口商"], entryMode: "B2B" }],
    },
    {
      trackCategories: [{ name: "家用测量", description: "新说明", buyerTypes: [] }],
      marketHypotheses: [{ marketCode: "GB", marketName: "英国", buyerTypes: [], demandHypothesis: "需求待验证" }],
    },
  );
  assert.equal(merged.trackCategories.length, 1);
  assert.equal(merged.trackCategories[0].description, "新说明");
  assert.deepEqual(merged.trackCategories[0].buyerTypes, ["进口商"]);
  assert.equal(merged.marketHypotheses.length, 1);
  assert.equal(merged.marketHypotheses[0].entryMode, "B2B");
  assert.equal(merged.marketHypotheses[0].demandHypothesis, "需求待验证");
});

test("incremental buyer research preserves profiles and extends the family matrix", () => {
  const previous = {
    buyerProfiles: [{
      companyName: "Example Wholesale Ltd",
      country: "GB",
      buyerType: "专业批发商",
      sourceUrl: "https://example.com/about",
      customerGroups: ["办公用户"],
    }],
    buyerFamilyMatrix: [{
      companyName: "Example Wholesale Ltd",
      country: "GB",
      trackCategory: "桌面设备",
      productFamily: "USB 桌面送风",
      familyRole: "core",
      relationshipScore: 70,
    }],
  };
  const merged = mergeResearchReports(previous, {
    buyerProfiles: [{
      companyName: "Example Wholesale Ltd",
      country: "GB",
      buyerType: "专业批发商",
      sourceUrl: "https://example.com/categories",
      salesChannels: ["B2B 网站"],
    }],
    buyerFamilyMatrix: [{
      companyName: "Example Wholesale Ltd",
      country: "GB",
      trackCategory: "办公配件",
      productFamily: "USB 扩展配件",
      familyRole: "cross_sell",
      relationshipScore: 55,
    }],
  });
  assert.equal(merged.buyerProfiles.length, 1);
  assert.deepEqual(merged.buyerProfiles[0].customerGroups, ["办公用户"]);
  assert.deepEqual(merged.buyerProfiles[0].salesChannels, ["B2B 网站"]);
  assert.equal(merged.buyerProfiles[0].sourceUrl, "https://example.com/categories");
  assert.equal(merged.buyerFamilyMatrix.length, 2);
});
