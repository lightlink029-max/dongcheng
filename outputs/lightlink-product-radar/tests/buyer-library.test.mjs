import test from "node:test";
import assert from "node:assert/strict";

import { buildProjectBuyerKnowledge } from "../lib/buyer-library.ts";

const profiles = [
  {
    id: "gb-office",
    company_name: "GB Office Distributor",
    country: "GB",
    buyer_type: "办公用品分销商",
    customer_groups: ["企业客户"],
    sales_channels: ["B2B 网站"],
    purchasing_scenarios: ["办公桌面配件补货"],
    seasonality: "返校季",
    replenishment_cycle: "待核实",
    order_requirements: "贸易报价",
    source_url: "https://example.com/gb",
    profile_status: "qualified",
  },
  {
    id: "us-medical",
    company_name: "US Medical Distributor",
    country: "US",
    buyer_type: "医疗器械分销商",
    customer_groups: ["诊所"],
    sales_channels: ["经销网络"],
    purchasing_scenarios: ["医疗设备补货"],
    seasonality: "常年",
    replenishment_cycle: "待核实",
    order_requirements: "FDA 路径",
    source_url: "https://example.com/us",
    profile_status: "qualified",
  },
];

const links = [
  { buyer_profile_id: "gb-office", track_category: "电脑与会议配件", product_family: "扩展坞", relationship_score: 88, family_role: "core", sales_scenarios: ["办公室升级"], rationale: "办公采购", evidence_status: "partial" },
  { buyer_profile_id: "us-medical", track_category: "医疗电子", product_family: "电子血压计", relationship_score: 90, family_role: "core", sales_scenarios: ["诊所补货"], rationale: "医疗采购", evidence_status: "partial" },
];

test("project buyer knowledge prioritizes target market and relevant families", () => {
  const result = buildProjectBuyerKnowledge({
    profiles,
    links,
    targetMarkets: ["GB"],
    productCategory: "办公数码",
    productDescription: "电脑会议配件",
    objectives: "寻找办公用品分销商",
  });
  assert.equal(result.profiles[0].id, "gb-office");
  assert.equal(result.familyMatrix[0].productFamily, "扩展坞");
});

test("global projects keep a compact reusable buyer library", () => {
  const result = buildProjectBuyerKnowledge({
    profiles,
    links,
    targetMarkets: ["GLOBAL"],
    productCategory: "",
    productDescription: "",
    objectives: "全球买家调研",
    limit: 1,
  });
  assert.equal(result.profileCount, 1);
  assert.equal(result.profiles.length, 1);
});
