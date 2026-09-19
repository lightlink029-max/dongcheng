import assert from "node:assert/strict";
import test from "node:test";

import {
  CHANNEL_DEFINITIONS,
  CodexChannelManager,
  buildTaskPrompt,
  channelIdForTask,
  originAllowed,
  progressForItem,
  terminalJobStatus,
  validateDispatch,
} from "../scripts/codex-task-channel.mjs";

const validTask = {
  runId: "56f08d8a-fed6-41c0-8cd4-d09b34ce3a93",
  query: "电子产品",
  market: "GB",
  language: "en",
  windowDays: 30,
  resultLimit: 20,
  mode: "seed",
  requestNote: "只使用可核验证据",
};

test("Codex channel accepts only the local radar origins", () => {
  assert.equal(originAllowed("http://127.0.0.1:8787"), true);
  assert.equal(originAllowed("http://localhost:8787"), true);
  assert.equal(originAllowed("https://example.com"), false);
  assert.equal(originAllowed(""), false);
});

test("Codex tasks are routed to independent named channels", () => {
  assert.equal(channelIdForTask("radar"), "radar");
  assert.equal(channelIdForTask({ taskType: "research" }), "research");
  assert.equal(channelIdForTask({ taskType: "candidate_assist" }), "candidate_assist");
  assert.equal(channelIdForTask({ taskType: "candidate_images" }), "candidate_images");
  assert.equal(channelIdForTask({ taskType: "taxonomy_assist" }), "taxonomy_assist");
  assert.equal(channelIdForTask({ taskType: "trade_data" }), "trade_data");
  assert.equal(channelIdForTask({ taskType: "opportunity_validation" }), "opportunity_validation");
  assert.equal(channelIdForTask({}), "radar");
  assert.notEqual(CHANNEL_DEFINITIONS.radar.title, CHANNEL_DEFINITIONS.candidate_assist.title);

  const status = new CodexChannelManager().status();
  assert.equal(status.ready, true);
  assert.deepEqual(Object.keys(status.channels), ["radar", "research", "candidate_assist", "candidate_images", "taxonomy_assist", "trade_data", "opportunity_validation"]);
  assert.deepEqual(status.activeJobs, []);
  assert.equal(status.activeJob, null);
});

test("Codex channel validates and normalizes radar fields", () => {
  assert.deepEqual(validateDispatch({ ...validTask, market: "gb", language: "EN" }), validTask);
  assert.throws(() => validateDispatch({ ...validTask, runId: "bad" }), /任务编号无效/);
  assert.throws(() => validateDispatch({ ...validTask, windowDays: 31 }), /分析周期无效/);
  assert.throws(() => validateDispatch({ ...validTask, resultLimit: 6 }), /结果数量无效/);
});

test("Codex task prompt preserves the radar task identity", () => {
  const prompt = buildTaskPrompt(validTask);
  assert.match(prompt, /\$lightlink-radar-bridge/);
  assert.match(prompt, new RegExp(validTask.runId));
  assert.match(prompt, /GB 市场 · EN 关键词 · 近 30 天/);
  assert.match(prompt, /严格区分缺失、失败与确认零/);
  assert.match(prompt, /keywordZh/);
  assert.match(prompt, /imageUrls/);
  assert.match(prompt, /imageSourceRef/);
  assert.match(prompt, /不得复用于不同词簇/);
  assert.match(prompt, /免配置时优先/);
  assert.match(prompt, /20 个/);
  assert.match(prompt, /Google Trends/);
  assert.match(prompt, /Amazon、Temu、SHEIN/);
  assert.match(prompt, /不得把商品结果数写成关键词搜索量/);
  assert.match(prompt, /purchasePriceMin/);
  assert.match(prompt, /geoScope/);
  assert.match(prompt, /scanMode=seed/);
});

test("Codex channel validates and explains reusable product research tasks", () => {
  const researchTask = validateDispatch({
    taskType: "research",
    projectId: "56f08d8a-fed6-41c0-8cd4-d09b34ce3a93",
    researchRunId: "4dc282e3-96c4-4d44-8d15-588775854f11",
    productName: "便携涡轮风扇",
    productCategory: "数码小家电",
    productDescription: "USB-C 充电，面向夏季礼品与户外渠道",
    targetMarkets: ["gb", "de"],
    languages: ["EN", "de"],
    channels: ["google_trends", "alibaba", "amazon"],
    templateId: "battery_gadget_export",
    objectives: "验证需求、价格带、买家与合规门槛",
    targetCandidateCount: 120,
    candidateCount: 24,
    runMode: "expand_candidates",
    requestedCandidateCount: 50,
    globalBuyerKnowledge: {
      profileCount: 1,
      familyLinkCount: 1,
      profiles: [{ id: "buyer-1", companyName: "Example Distributor", country: "GB", buyerType: "办公用品分销商", sourceUrl: "https://example.com" }],
      familyMatrix: [{ buyerProfileId: "buyer-1", companyName: "Example Distributor", country: "GB", trackCategory: "电脑与会议配件", productFamily: "扩展坞", relationshipScore: 88, familyRole: "core", evidenceStatus: "partial" }],
    },
  });
  assert.equal(researchTask.taskType, "research");
  assert.deepEqual(researchTask.targetMarkets, ["GB", "DE"]);
  assert.deepEqual(researchTask.languages, ["en", "de"]);
  const prompt = buildTaskPrompt(researchTask);
  assert.match(prompt, /产品与市场调研/);
  assert.match(prompt, /八个章节/);
  assert.match(prompt, /五维100分卡/);
  assert.match(prompt, /产品大类 × 国家\/地区/);
  assert.match(prompt, /前30\/60\/90天行动表/);
  assert.match(prompt, /不要固定缩减为 6–7 个/);
  assert.match(prompt, /trackCategories/);
  assert.match(prompt, /productPool/);
  assert.match(prompt, /marketHypotheses/);
  assert.match(prompt, /长期维护11个模块/);
  assert.match(prompt, /playbook/);
  assert.equal(researchTask.targetCandidateCount, 120);
  assert.equal(researchTask.requestedCandidateCount, 50);
  assert.match(prompt, /累计目标为 120 条/);
  assert.match(prompt, /至少整理 50 个/);
  assert.match(prompt, /同步回填已有缺图候选/);
  assert.match(prompt, /已有产品名称/);
  assert.match(prompt, /不要递归扫描 node_modules/);
  assert.match(prompt, /status --full/);
  assert.match(prompt, /不得只重复旧结论或只列赛道/);
  assert.match(prompt, /可复用的全球买家知识/);
  assert.match(prompt, /Example Distributor/);
  assert.match(prompt, /imageUrls/);
  assert.match(prompt, /严禁把同一张图片重复套给多个产品/);
  assert.match(prompt, /codex-research-bridge\.mjs import/);
  assert.match(prompt, new RegExp(researchTask.projectId));
  assert.match(prompt, new RegExp(researchTask.researchRunId));
});

test("Codex channel validates candidate assistance without auto-advancing the stage", () => {
  const task = validateDispatch({
    taskType: "candidate_assist",
    runId: "b6d30308-65ea-4049-a97c-7ecb13849f9b",
    projectId: "56f08d8a-fed6-41c0-8cd4-d09b34ce3a93",
    candidateId: "4dc282e3-96c4-4d44-8d15-588775854f11",
    candidateName: "带称重功能电子量杯",
    targetMarkets: ["gb", "de"],
    languages: ["EN"],
    currentStage: "research",
    buyerTypes: ["厨房用品进口商"],
  });
  assert.equal(task.taskType, "candidate_assist");
  assert.deepEqual(task.targetMarkets, ["GB", "DE"]);
  const prompt = buildTaskPrompt(task);
  assert.match(prompt, /不要自动改变人工阶段/);
  assert.match(prompt, /recommendedStage/);
  assert.match(prompt, /imageUrls/);
  assert.match(prompt, /assist-import/);
  assert.match(prompt, new RegExp(`--candidate-id ${task.candidateId}`));
});

test("Codex channel limits batch image assistance to verified candidate rows", () => {
  const task = validateDispatch({
    taskType: "candidate_images",
    runId: "b6d30308-65ea-4049-a97c-7ecb13849f9b",
    projectId: "56f08d8a-fed6-41c0-8cd4-d09b34ce3a93",
    projectName: "电子产品外贸",
    candidates: [{ candidateId: "4dc282e3-96c4-4d44-8d15-588775854f11", name: "电子量杯", targetMarkets: ["GB"] }],
  });
  const prompt = buildTaskPrompt(task);
  assert.match(prompt, /不要生成图片/);
  assert.match(prompt, /搜索缩略图/);
  assert.match(prompt, /落地链接/);
  assert.match(prompt, /不得复用同一图片URL/);
  assert.match(prompt, /images-import/);
});

test("Codex channel keeps buyer persona AI changes behind human review", () => {
  const task = validateDispatch({
    taskType: "taxonomy_assist",
    runId: "b6d30308-65ea-4049-a97c-7ecb13849f9b",
    mode: "enrich",
    personaCode: "ELEC_MRO_DIST",
    requestedCount: 1,
    requestNote: "补充公开分类依据和采购场景",
  });
  assert.equal(task.taskType, "taxonomy_assist");
  assert.equal(task.personaCode, "ELEC_MRO_DIST");
  const prompt = buildTaskPrompt(task);
  assert.match(prompt, /待人工审核建议/);
  assert.match(prompt, /禁止直接覆盖或删除正式主数据/);
  assert.match(prompt, /codex-taxonomy-bridge\.mjs status --persona-code ELEC_MRO_DIST/);
  assert.match(prompt, /sourceRefs/);
  assert.match(prompt, /codex-taxonomy-bridge\.mjs import/);
});

test("Codex channel validates local-first official trade data tasks", () => {
  const task = validateDispatch({
    taskType: "trade_data",
    runId: "b6d30308-65ea-4049-a97c-7ecb13849f9b",
    opportunityId: "56f08d8a-fed6-41c0-8cd4-d09b34ce3a93",
    personaCode: "ELEC_MRO_DIST",
    personaName: "电子电气与工贸用品分销商",
    regionCode: "EU",
    regionName: "欧盟",
    countries: ["DE", "FR"],
    trackCode: "ELEC_MRO",
    trackName: "电子电气与MRO用品",
    productFamilyCode: "MRO_METERS",
    productFamilyName: "工业测量仪表",
    keywords: ["digital multimeter"],
    existingPeriods: ["2024"],
    collectionLevel: "trend",
  });
  assert.equal(task.taskType, "trade_data");
  assert.deepEqual(task.countries, ["DE", "FR"]);
  const prompt = buildTaskPrompt(task);
  assert.match(prompt, /先读本地缓存/);
  assert.match(prompt, /UN Comtrade/);
  assert.match(prompt, /不等于终端零售销售额/);
  assert.match(prompt, /严格区分 0 与缺失/);
  assert.match(prompt, /本次采集等级：trend/);
  assert.match(prompt, /24–36个月/);
  assert.match(prompt, /codex-trade-bridge\.mjs import/);
});

test("Codex channel collects opportunity evidence without inventing buying intent", () => {
  const task = validateDispatch({
    taskType: "opportunity_validation",
    runId: "b6d30308-65ea-4049-a97c-7ecb13849f9b",
    opportunityId: "56f08d8a-fed6-41c0-8cd4-d09b34ce3a93",
    title: "北欧消费电子分销商 · 扩展坞",
    personaCode: "ELEC_MRO_DIST",
    personaName: "电子电气与工贸用品分销商",
    regionCode: "NORDICS_UK",
    regionName: "北欧与英国",
    countries: ["GB", "SE", "DK"],
    trackCode: "COMPUTER_AV",
    trackName: "电脑、办公与会议配件",
    productFamilyCode: "DOCK_HUB",
    productFamilyName: "扩展坞与多口转换",
    purchaseScenario: "经销补货",
    salesChannel: "专业分销",
    existingEvidenceTypes: ["demand"],
  });
  assert.equal(task.taskType, "opportunity_validation");
  assert.deepEqual(task.countries, ["GB", "SE", "DK"]);
  const prompt = buildTaskPrompt(task);
  assert.match(prompt, /真实批发\/分销组织/);
  assert.match(prompt, /不等于有采购意向/);
  assert.match(prompt, /禁止由 AI 写 verified_buyer/);
  assert.match(prompt, /codex-opportunity-bridge\.mjs import/);
});

test("Codex terminal states distinguish completion, interruption, and failure", () => {
  assert.equal(terminalJobStatus("completed"), "completed");
  assert.equal(terminalJobStatus("interrupted"), "interrupted");
  assert.equal(terminalJobStatus("failed"), "failed");
  assert.equal(terminalJobStatus("inProgress"), null);
});

test("Codex item activity exposes meaningful radar phases", () => {
  assert.deepEqual(progressForItem({ type: "webSearch" }, 20), { progress: 45, phase: "正在采集公开证据" });
  assert.deepEqual(
    progressForItem({ type: "commandExecution", command: "node scripts/codex-radar-bridge.mjs import --file result.json" }, 58),
    { progress: 78, phase: "正在写回雷达" },
  );
  assert.deepEqual(
    progressForItem({ type: "commandExecution", command: "node scripts/codex-radar-bridge.mjs status" }, 78),
    { progress: 92, phase: "正在复读核验结果" },
  );
});
