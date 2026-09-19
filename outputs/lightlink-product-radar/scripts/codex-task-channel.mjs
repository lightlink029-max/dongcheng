#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { createInterface } from "node:readline";
import { access, mkdir, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(SCRIPT_DIR, "..");
const HOST = "127.0.0.1";
const PORT = Number(process.env.LIGHTLINK_CODEX_CHANNEL_PORT || "8788");
const STATE_DIR = join(PROJECT_ROOT, ".codex");
const ALLOWED_ORIGINS = new Set([
  "http://127.0.0.1:8787",
  "http://localhost:8787",
]);
const TRADE_COLLECTION_LEVELS = new Set(["baseline", "trend", "detail"]);
const TRADE_COLLECTION_PROMPTS = Object.freeze({
  baseline: "采集最近5个完整年度的年度汇总；partnerCode 使用 WORLD；优先进口并在可靠时补出口。",
  trend: "在年度基线之外，补最近24–36个月的月度序列；partnerCode 使用 WORLD，用于同比、环比与季节性判断。",
  detail: "在年度与月度数据之外，补可靠的 HS6、目标国家和主要贸易伙伴明细；无法细分时明确记录 missing 或 blocked。",
});

export const CHANNEL_DEFINITIONS = Object.freeze({
  radar: Object.freeze({ id: "radar", title: "LightLink Radar 关键词雷达", stateFile: "lightlink-radar-thread-radar.json" }),
  research: Object.freeze({ id: "research", title: "LightLink Radar 项目调研", stateFile: "lightlink-radar-thread-research.json" }),
  candidate_assist: Object.freeze({ id: "candidate_assist", title: "LightLink Radar 产品调研", stateFile: "lightlink-radar-thread-candidate-assist.json" }),
  candidate_images: Object.freeze({ id: "candidate_images", title: "LightLink Radar 图片采集", stateFile: "lightlink-radar-thread-candidate-images.json" }),
  taxonomy_assist: Object.freeze({ id: "taxonomy_assist", title: "LightLink Radar 画像分类", stateFile: "lightlink-radar-thread-taxonomy-assist.json" }),
  trade_data: Object.freeze({ id: "trade_data", title: "LightLink Radar 贸易数据", stateFile: "lightlink-radar-thread-trade-data.json" }),
  opportunity_validation: Object.freeze({ id: "opportunity_validation", title: "LightLink Radar 商机验证", stateFile: "lightlink-radar-thread-opportunity-validation.json" }),
});

export function channelIdForTask(taskOrType) {
  const taskType = typeof taskOrType === "string" ? taskOrType : taskOrType?.taskType;
  return Object.hasOwn(CHANNEL_DEFINITIONS, taskType) ? taskType : "radar";
}

function reportResearchFailure(job, error) {
  if (job?.taskType === "opportunity_validation" && job.runId) {
    void fetch("http://127.0.0.1:8787/api/radar", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "fail_opportunity_validation_request", runId: job.runId, error: error || "Codex 商机公开证据任务未完成" }),
    }).catch((reportError) => {
      process.stderr.write(`[opportunity-validation-failure] ${reportError instanceof Error ? reportError.message : String(reportError)}\n`);
    });
    return;
  }
  if (job?.taskType === "trade_data" && job.runId) {
    void fetch("http://127.0.0.1:8787/api/radar", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "fail_trade_data_request", runId: job.runId, error: error || "Codex 贸易数据任务未完成" }),
    }).catch((reportError) => {
      process.stderr.write(`[trade-data-failure] ${reportError instanceof Error ? reportError.message : String(reportError)}\n`);
    });
    return;
  }
  if (job?.taskType !== "research" || !job.projectId || !job.researchRunId) return;
  void fetch("http://127.0.0.1:8787/api/radar", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      action: "fail_research_run",
      projectId: job.projectId,
      researchRunId: job.researchRunId,
      error: error || "Codex 调研任务未完成",
    }),
  }).catch((reportError) => {
    process.stderr.write(`[research-failure] ${reportError instanceof Error ? reportError.message : String(reportError)}\n`);
  });
}

const MARKET_PATTERN = /^[A-Z]{2,10}$/;
const REGION_PATTERN = /^[A-Z0-9_]{2,24}$/;
const LANGUAGE_PATTERN = /^[a-z]{2,8}(?:-[a-z0-9]{2,8})?$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function normalizeGlobalBuyerKnowledge(value) {
  const input = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const text = (item, max = 500) => String(item ?? "").trim().slice(0, max);
  const list = (item, maxItems = 30) => Array.isArray(item)
    ? [...new Set(item.map((entry) => text(entry, 300)).filter(Boolean))].slice(0, maxItems)
    : [];
  const profiles = Array.isArray(input.profiles) ? input.profiles.slice(0, 24).map((item) => {
    const profile = item && typeof item === "object" && !Array.isArray(item) ? item : {};
    return {
      id: text(profile.id, 80), companyName: text(profile.companyName, 160), country: text(profile.country, 80),
      buyerType: text(profile.buyerType, 160), customerGroups: list(profile.customerGroups, 30),
      salesChannels: list(profile.salesChannels, 20), purchasingScenarios: list(profile.purchasingScenarios, 30),
      seasonality: text(profile.seasonality, 500), replenishmentCycle: text(profile.replenishmentCycle, 300),
      orderRequirements: text(profile.orderRequirements, 800), sourceUrl: text(profile.sourceUrl, 1000),
      profileStatus: ["hypothesis", "qualified", "validated", "rejected"].includes(String(profile.profileStatus)) ? String(profile.profileStatus) : "hypothesis",
    };
  }).filter((item) => item.id && item.companyName && item.country && item.sourceUrl) : [];
  const profileIds = new Set(profiles.map((item) => item.id));
  const familyMatrix = Array.isArray(input.familyMatrix) ? input.familyMatrix.slice(0, 120).map((item) => {
    const link = item && typeof item === "object" && !Array.isArray(item) ? item : {};
    return {
      buyerProfileId: text(link.buyerProfileId, 80), companyName: text(link.companyName, 160), country: text(link.country, 80),
      trackCategory: text(link.trackCategory, 120), productFamily: text(link.productFamily, 120),
      relationshipScore: Math.max(0, Math.min(100, Math.round(Number(link.relationshipScore) || 0))),
      familyRole: ["core", "cross_sell", "seasonal", "test"].includes(String(link.familyRole)) ? String(link.familyRole) : "test",
      salesScenarios: list(link.salesScenarios, 30), rationale: text(link.rationale, 800),
      evidenceStatus: ["hypothesis", "partial", "validated"].includes(String(link.evidenceStatus)) ? String(link.evidenceStatus) : "hypothesis",
    };
  }).filter((item) => profileIds.has(item.buyerProfileId) && item.trackCategory && item.productFamily) : [];
  const taxonomyInput = input.taxonomy && typeof input.taxonomy === "object" && !Array.isArray(input.taxonomy) ? input.taxonomy : {};
  const taxonomy = {
    regions: Array.isArray(taxonomyInput.regions) ? taxonomyInput.regions.slice(0, 15).map((item) => ({
      code: text(item?.code, 20), name: text(item?.name, 80), countries: list(item?.countries, 50), characteristics: list(item?.characteristics, 10),
    })).filter((item) => item.code && item.name) : [],
    personaCategories: Array.isArray(taxonomyInput.personaCategories) ? taxonomyInput.personaCategories.slice(0, 12).map((item) => ({
      code: text(item?.code, 48), name: text(item?.name, 120), groupName: text(item?.groupName, 120),
      valueChainRole: text(item?.valueChainRole, 300), purchaseScenarios: list(item?.purchaseScenarios, 20),
      buyingTriggers: list(item?.buyingTriggers, 20), orderCharacteristics: list(item?.orderCharacteristics, 20),
    })).filter((item) => item.code && item.name) : [],
    productTracks: Array.isArray(taxonomyInput.productTracks) ? taxonomyInput.productTracks.slice(0, 12).map((item) => ({
      code: text(item?.code, 48), name: text(item?.name, 120), buyerValue: text(item?.buyerValue, 400), complianceFocus: list(item?.complianceFocus, 20),
    })).filter((item) => item.code && item.name) : [],
    productFamilies: Array.isArray(taxonomyInput.productFamilies) ? taxonomyInput.productFamilies.slice(0, 40).map((item) => ({
      code: text(item?.code, 48), trackCode: text(item?.trackCode, 48), name: text(item?.name, 120),
      useScenarios: list(item?.useScenarios, 20), complianceTags: list(item?.complianceTags, 20),
    })).filter((item) => item.code && item.trackCode && item.name) : [],
    personaMatrix: Array.isArray(taxonomyInput.personaMatrix) ? taxonomyInput.personaMatrix.slice(0, 36).map((item) => ({
      personaCode: text(item?.personaCode, 48), regionCode: text(item?.regionCode, 20), trackCode: text(item?.trackCode, 48),
      productFamilyCode: text(item?.productFamilyCode, 48), relevanceScore: Math.max(0, Math.min(100, Math.round(Number(item?.relevanceScore) || 0))),
      familyRole: ["core", "cross_sell", "seasonal", "test"].includes(String(item?.familyRole)) ? String(item?.familyRole) : "test",
      evidenceStatus: ["hypothesis", "partial", "validated"].includes(String(item?.evidenceStatus)) ? String(item?.evidenceStatus) : "hypothesis",
    })).filter((item) => item.personaCode && item.regionCode && item.trackCode) : [],
  };
  return { profileCount: profiles.length, familyLinkCount: familyMatrix.length, profiles, familyMatrix, taxonomy };
}

export function validateDispatch(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("任务参数无效");
  if (input.taskType === "opportunity_validation") {
    const runId = String(input.runId ?? "").trim();
    const opportunityId = String(input.opportunityId ?? "").trim();
    const personaCode = String(input.personaCode ?? "").trim().toUpperCase();
    const regionCode = String(input.regionCode ?? "").trim().toUpperCase();
    const productFamilyCode = String(input.productFamilyCode ?? "").trim().toUpperCase();
    const productFamilyName = String(input.productFamilyName ?? "").trim();
    const countries = Array.isArray(input.countries) ? input.countries.map((item) => String(item).trim()).filter(Boolean).slice(0, 80) : [];
    const existingEvidenceTypes = Array.isArray(input.existingEvidenceTypes) ? input.existingEvidenceTypes.map((item) => String(item).trim()).filter(Boolean).slice(0, 20) : [];
    const requestNote = String(input.requestNote ?? "").trim();
    if (!UUID_PATTERN.test(runId) || !UUID_PATTERN.test(opportunityId)) throw new Error("商机验证任务编号无效");
    if (!/^[A-Z0-9_]{2,48}$/.test(personaCode) || !REGION_PATTERN.test(regionCode) || !/^[A-Z0-9_]{2,48}$/.test(productFamilyCode)) throw new Error("商机验证画像、地区或产品家族无效");
    if (productFamilyName.length < 2 || productFamilyName.length > 160) throw new Error("商机验证产品家族名称无效");
    if (requestNote.length > 1200) throw new Error("商机验证补充要求不能超过 1200 个字符");
    return { ...input, taskType: "opportunity_validation", runId, opportunityId, personaCode, regionCode, productFamilyCode, productFamilyName, countries, existingEvidenceTypes, requestNote };
  }
  if (input.taskType === "trade_data") {
    const runId = String(input.runId ?? "").trim();
    const opportunityId = String(input.opportunityId ?? "").trim();
    const personaCode = String(input.personaCode ?? "").trim().toUpperCase();
    const regionCode = String(input.regionCode ?? "").trim().toUpperCase();
    const productFamilyCode = String(input.productFamilyCode ?? "").trim().toUpperCase();
    const productFamilyName = String(input.productFamilyName ?? "").trim();
    const countries = Array.isArray(input.countries) ? input.countries.map((item) => String(item).trim()).filter(Boolean).slice(0, 80) : [];
    const keywords = Array.isArray(input.keywords) ? input.keywords.map((item) => String(item).trim()).filter(Boolean).slice(0, 30) : [];
    const existingPeriods = Array.isArray(input.existingPeriods) ? input.existingPeriods.map((item) => String(item).trim()).filter(Boolean).slice(0, 36) : [];
    const requestNote = String(input.requestNote ?? "").trim();
    const collectionLevel = TRADE_COLLECTION_LEVELS.has(String(input.collectionLevel)) ? String(input.collectionLevel) : "baseline";
    if (!UUID_PATTERN.test(runId) || !UUID_PATTERN.test(opportunityId)) throw new Error("贸易数据任务编号无效");
    if (!/^[A-Z0-9_]{2,48}$/.test(personaCode) || !REGION_PATTERN.test(regionCode) || !/^[A-Z0-9_]{2,48}$/.test(productFamilyCode)) throw new Error("贸易数据画像、地区或产品家族无效");
    if (productFamilyName.length < 2 || productFamilyName.length > 160) throw new Error("产品家族名称无效");
    if (requestNote.length > 1000) throw new Error("贸易数据补充要求不能超过 1000 个字符");
    return { ...input, taskType: "trade_data", runId, opportunityId, personaCode, regionCode, productFamilyCode, productFamilyName, countries, keywords, existingPeriods, requestNote, collectionLevel };
  }
  if (input.taskType === "taxonomy_assist") {
    const runId = String(input.runId ?? "").trim();
    const mode = input.mode === "enrich" ? "enrich" : "discover";
    const personaCode = String(input.personaCode ?? "").trim().toUpperCase();
    const requestedCount = Math.max(1, Math.min(10, Math.round(Number(input.requestedCount) || 3)));
    const requestNote = String(input.requestNote ?? "").trim();
    if (!UUID_PATTERN.test(runId)) throw new Error("AI画像任务编号无效");
    if (personaCode && !/^[A-Z0-9_]{2,48}$/.test(personaCode)) throw new Error("画像分类代码无效");
    if (mode === "enrich" && !personaCode) throw new Error("复核模式需要指定画像分类");
    if (requestNote.length > 1500) throw new Error("AI画像补充要求不能超过 1500 个字符");
    return { taskType: "taxonomy_assist", runId, mode, personaCode, requestedCount, requestNote };
  }
  if (input.taskType === "candidate_assist") {
    const runId = String(input.runId ?? "").trim();
    const projectId = String(input.projectId ?? "").trim();
    const candidateId = String(input.candidateId ?? "").trim();
    const candidateName = String(input.candidateName ?? "").trim();
    const targetMarkets = Array.isArray(input.targetMarkets) ? input.targetMarkets.map((item) => String(item).trim().toUpperCase()).filter(Boolean).slice(0, 30) : [];
    const languages = Array.isArray(input.languages) ? input.languages.map((item) => String(item).trim().toLowerCase()).filter(Boolean).slice(0, 30) : [];
    const currentStage = String(input.currentStage ?? "idea").trim();
    const requestNote = String(input.requestNote ?? "").trim();
    if (![runId, projectId, candidateId].every((item) => UUID_PATTERN.test(item))) throw new Error("AI辅助任务编号无效");
    if (candidateName.length < 2 || candidateName.length > 160) throw new Error("候选产品名称长度必须为 2–160 个字符");
    if (!targetMarkets.length || targetMarkets.some((item) => !MARKET_PATTERN.test(item))) throw new Error("候选产品目标市场无效");
    if (languages.some((item) => !LANGUAGE_PATTERN.test(item))) throw new Error("研究语言无效");
    if (!["idea", "research", "sample", "validation", "shortlist", "validated", "rejected"].includes(currentStage)) throw new Error("候选产品阶段无效");
    if (requestNote.length > 1000) throw new Error("AI辅助要求不能超过 1000 个字符");
    return {
      ...input, taskType: "candidate_assist", runId, projectId, candidateId, candidateName,
      targetMarkets, languages, currentStage, requestNote,
    };
  }
  if (input.taskType === "candidate_images") {
    const runId = String(input.runId ?? "").trim();
    const projectId = String(input.projectId ?? "").trim();
    const projectName = String(input.projectName ?? "").trim();
    const candidates = Array.isArray(input.candidates) ? input.candidates.slice(0, 25).map((value) => {
      const item = value && typeof value === "object" && !Array.isArray(value) ? value : {};
      return {
        candidateId: String(item.candidateId ?? "").trim(),
        name: String(item.name ?? "").trim(),
        commercialVariant: String(item.commercialVariant ?? "").trim(),
        targetMarkets: Array.isArray(item.targetMarkets) ? item.targetMarkets.map((market) => String(market).trim().toUpperCase()).filter(Boolean).slice(0, 10) : [],
      };
    }) : [];
    if (!UUID_PATTERN.test(runId) || !UUID_PATTERN.test(projectId)) throw new Error("图片辅助任务编号无效");
    if (!projectName || !candidates.length) throw new Error("图片辅助任务缺少项目或候选产品");
    if (candidates.some((item) => !UUID_PATTERN.test(item.candidateId) || item.name.length < 2 || item.name.length > 160)) throw new Error("图片辅助候选产品无效");
    return { taskType: "candidate_images", runId, projectId, projectName, candidates };
  }
  if (input.taskType === "research") {
    const projectId = String(input.projectId ?? "").trim();
    const researchRunId = String(input.researchRunId ?? input.runId ?? "").trim();
    const productName = String(input.productName ?? "").trim();
    const productCategory = String(input.productCategory ?? "").trim();
    const productDescription = String(input.productDescription ?? "").trim();
    const targetMarkets = Array.isArray(input.targetMarkets) ? input.targetMarkets.map((item) => String(item).trim().toUpperCase()).filter(Boolean).slice(0, 30) : [];
    const languages = Array.isArray(input.languages) ? input.languages.map((item) => String(item).trim().toLowerCase()).filter(Boolean).slice(0, 30) : [];
    const channels = Array.isArray(input.channels) ? input.channels.map((item) => String(item).trim()).filter(Boolean).slice(0, 30) : [];
    const templateId = String(input.templateId ?? "general_validation").trim();
    const objectives = String(input.objectives ?? "").trim();
    const constraints = String(input.constraints ?? "").trim();
    const requestNote = String(input.requestNote ?? "").trim();
    const candidateCount = Math.max(0, Math.min(2000, Math.round(Number(input.candidateCount) || 0)));
    const targetCandidateCount = Math.max(candidateCount, Math.min(2000, Math.round(Number(input.targetCandidateCount) || 2000)));
    const runMode = input.runMode === "expand_candidates" ? "expand_candidates" : "review";
    const requestedCandidateCount = runMode === "expand_candidates"
      ? Math.round(Number(input.requestedCandidateCount) || Math.min(100, Math.max(1, targetCandidateCount - candidateCount)))
      : 0;
    const globalBuyerKnowledge = normalizeGlobalBuyerKnowledge(input.globalBuyerKnowledge);
    if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(researchRunId)) throw new Error("调研项目或运行编号无效");
    if (productName.length < 2 || productName.length > 120) throw new Error("产品名称长度必须为 2–120 个字符");
    if (!targetMarkets.length || targetMarkets.some((item) => !MARKET_PATTERN.test(item))) throw new Error("目标市场无效");
    if (!languages.length || languages.some((item) => !LANGUAGE_PATTERN.test(item))) throw new Error("研究语言无效");
    if (objectives.length > 6000 || constraints.length > 2000 || requestNote.length > 2000) throw new Error("完整调研任务不能超过 6000 个字符，约束和补充说明不能超过 2000 个字符");
    if (runMode === "expand_candidates" && (requestedCandidateCount < 1 || requestedCandidateCount > 300)) throw new Error("本轮新增数量必须为 1–300");
    return {
      taskType: "research",
      projectId,
      researchRunId,
      productName,
      productCategory,
      productDescription,
      targetMarkets,
      languages,
      channels,
      templateId,
      objectives,
      constraints,
      requestNote,
      candidateCount,
      targetCandidateCount,
      runMode,
      requestedCandidateCount,
      globalBuyerKnowledge,
    };
  }
  const query = String(input.query ?? "").trim();
  const runId = String(input.runId ?? "").trim();
  const market = String(input.market ?? "").trim().toUpperCase();
  const language = String(input.language ?? "").trim().toLowerCase();
  const windowDays = Number(input.windowDays);
  const resultLimit = Number(input.resultLimit ?? 20);
  const mode = input.mode === "discover" ? "discover" : input.mode === "seed" ? "seed" : null;
  const requestNote = String(input.requestNote ?? "").trim();
  if (query.length < 2 || query.length > 500) throw new Error("关键词长度必须为 2–500 个字符");
  if (!UUID_PATTERN.test(runId)) throw new Error("任务编号无效");
  if (!MARKET_PATTERN.test(market)) throw new Error("市场代码无效");
  if (!LANGUAGE_PATTERN.test(language)) throw new Error("语言代码无效");
  if (![7, 30, 90].includes(windowDays)) throw new Error("分析周期无效");
  if (![10, 15, 20].includes(resultLimit)) throw new Error("结果数量无效");
  if (!mode) throw new Error("任务模式无效");
  if (requestNote.length > 1000) throw new Error("整理要求不能超过 1000 个字符");
  return { query, runId, market, language, windowDays, resultLimit, mode, requestNote };
}

export function buildTaskPrompt(task) {
  if (task.taskType === "opportunity_validation") {
    return [
      "为 LightLink 商机建立一份可复用的公开证据包，并把结果写回商机验证中心。目标是降低人工搜索量，不是替用户虚构买家意向、报价或利润。",
      `任务编号：${task.runId}；商机：${task.opportunityId}；标题：${task.title || task.productFamilyName}`,
      `买家画像：${task.personaName || task.personaCode}；地区：${task.regionName || task.regionCode}；覆盖国家：${task.countries.join("、") || task.regionCode}`,
      `产品赛道：${task.trackName || task.trackCode}；产品家族：${task.productFamilyName}（${task.productFamilyCode}）`,
      `采购场景：${task.purchaseScenario || "待核实"}；销售渠道：${task.salesChannel || "待核实"}；商机假设：${task.hypothesis || "待核实"}`,
      `已有证据类型：${task.existingEvidenceTypes.join("、") || "无"}；用户补充要求：${task.requestNote || "优先补真实买家、渠道价格和官方合规证据。"}`,
      `先运行 node scripts/codex-opportunity-bridge.mjs status --opportunity-id ${task.opportunityId}，读取已有证据，避免重复。`,
      "按决策价值采集：1）6–10家符合画像的真实批发/分销组织及其直接品类页；2）目标渠道的商品、价格、MOQ或公开销售场景；3）目标国家官方法规、认证、标签、关税或物流要求；4）可公开核验的供应商目录只作为供应线索，不能当作已报价。",
      "优先公司官网、公开采购/招标页、行业协会/展会名录、政府及法规官网、目标渠道商品页。不得采集私人联系方式，不得绕过登录或访问限制，不得使用无直接来源的搜索摘要。",
      "真实公司存在及经营该品类不等于有采购意向；公开挂牌价不等于成交价；供应商目录不等于报价或产能。sourceGrade 只能写 official、marketplace 或 other，禁止由 AI 写 verified_buyer、supplier_quote 或 internal_odoo。",
      "每条 evidence 字段：evidenceType(demand/buyer/channel/competition/supply/compliance)、sourceGrade、title、sourceUrl、note、marketCode、period、metrics、capturedAt。sourceUrl 必须是可直接核验的 http/https 页面；metrics 只记录来源中明确给出的客观数量或价格，不输出主观评分。",
      "保存 JSON：{ summary, suggestedNextAction, evidence: [...] }。summary 说明已找到什么、仍缺什么；suggestedNextAction 只给一个最高优先级动作。无法核验的内容不要写入 evidence。",
      `最后运行 node scripts/codex-opportunity-bridge.mjs import --opportunity-id ${task.opportunityId} --run-id ${task.runId} --file <结果JSON>，再运行 status 确认证据已入库。`,
    ].join("\n");
  }
  if (task.taskType === "trade_data") {
    return [
      "为 LightLink 商机补充可复用的官方国际贸易数据。先读本地缓存，只补缺失或过期数据；结果必须写回本地数据库，不要只输出分析。",
      `任务编号：${task.runId}；商机：${task.opportunityId}`,
      `买家画像：${task.personaName || task.personaCode}；地区：${task.regionName || task.regionCode}；覆盖国家：${task.countries.join("、") || task.regionCode}`,
      `产品赛道：${task.trackName || task.trackCode}；产品家族：${task.productFamilyName}（${task.productFamilyCode}）；关键词：${task.keywords.join("、") || "按家族名称判断"}`,
      `采购场景：${task.purchaseScenario || "待核实"}；渠道：${task.salesChannel || "待核实"}；已有期间：${task.existingPeriods.join("、") || "无"}`,
      `本次采集等级：${task.collectionLevel}。${TRADE_COLLECTION_PROMPTS[task.collectionLevel]}`,
      `用户要求：${task.requestNote || "按当前采集等级补齐缺口。"}`,
      `先运行 node scripts/codex-trade-bridge.mjs status --opportunity-id ${task.opportunityId}，确认本地已有期间和缺口。`,
      "来源优先级：UN Comtrade；欧盟市场用 Eurostat Comext 复核；美国用 U.S. Census International Trade API；宏观或关税补充可用 WTO Data/WTO API 与 World Bank WITS。只使用官方页面、官方 API 或官方导出，Alibaba、Amazon、Google Trends 不能作为贸易额或销售额来源。",
      "先确定最接近的 HS 2/4/6 位编码及版本。不得假装精确到不可靠的 HS10；如一个家族对应多个编码，应分别记录。贸易额是进出口流量，不等于终端零售销售额，必须在结果摘要中说明。",
      "每条 observation 字段：reporterCode、partnerCode（默认 WORLD）、classification（例如 HS2022）、commodityCode、commodityLabel、flow(import/export)、period(YYYY/ YYYY-MM / YYYY-Q1)、frequency(annual/monthly/quarterly)、metric、value、unit、sourceName、sourceUrl、sourceGrade(official/official_export/ai_verified)、status(available/missing/blocked)、missingReason、collectedAt。",
      "严格区分 0 与缺失：可用的确认零写 value=0,status=available；查不到写 value=null,status=missing 并说明原因；登录、限流或地区限制写 blocked。每条都必须保留可直接核验的 http/https 官方来源链接。",
      "保存 JSON：{ observations: [...] }。不要生成估算销售额，不要从图表截图猜数，不要用搜索摘要替代原始来源。",
      `最后运行 node scripts/codex-trade-bridge.mjs import --opportunity-id ${task.opportunityId} --run-id ${task.runId} --file <结果JSON>，再运行 status 确认数据已入本地缓存。`,
    ].join("\n");
  }
  if (task.taskType === "taxonomy_assist") {
    return [
      "维护 LightLink 的全球外贸批发买家画像分类。你的结果必须写回为待人工审核建议，禁止直接覆盖或删除正式主数据。",
      `任务编号：${task.runId}；模式：${task.mode === "enrich" ? "复核并补充现有画像" : "发现缺失画像分类"}；目标画像：${task.personaCode || "整个画像库"}；最多建议 ${task.requestedCount} 条。`,
      `用户要求：${task.requestNote || "优先补足稳定的批发业态、价值链角色、采购场景与合规关注，避免按单一产品或单一公司创建分类。"}`,
      `先运行 node scripts/codex-taxonomy-bridge.mjs status${task.personaCode ? ` --persona-code ${task.personaCode}` : ""}，读取现有分类、地区和产品赛道，避免重复。`,
      "研究时优先使用联合国、国家统计分类、行业协会、展会与大型分销行业目录等公开来源。画像是可复用的业态分类，不是具体公司，也不能把分类关系描述成真实采购意向、采购额或复购事实。",
      "每条建议输出：code、groupName、name、description、valueChainRole、customerGroups、salesChannels、purchaseScenarios、buyingTriggers、orderCharacteristics、complianceFocus、sourceRefs、rationale。sourceRefs 至少提供一个可直接打开的 http/https 来源。",
      `保存 JSON：{ mode: "${task.mode}", targetCode: "${task.personaCode}", personas: [...] }。`,
      `最后运行 node scripts/codex-taxonomy-bridge.mjs import --run-id ${task.runId} --file <结果JSON>，再运行 status 确认待审核建议数量已增加。`,
    ].join("\n");
  }
  if (task.taskType === "candidate_assist") {
    return [
      "为 LightLink 调研项目中的单个候选产品执行有限范围、可核验的AI辅助调研，并把建议直接写回产品历史记录。不要自动改变人工阶段。",
      `辅助任务：${task.runId}；项目：${task.projectId}；候选产品：${task.candidateId}`,
      `产品：${task.candidateName}；商业变体：${task.commercialVariant || "待补充"}`,
      `赛道：${task.trackCategory || "未分类"} / ${task.subcategory || "未细分"} / 产品家族：${task.productFamily || task.subcategory || "未归组"}；当前阶段：${task.currentStage}`,
      `目标市场：${task.targetMarkets.join("、")}；目标买家：${Array.isArray(task.buyerTypes) ? task.buyerTypes.join("、") : "待核实"}`,
      `已有价格：${task.priceBand || "未知"}；已有MOQ：${task.moq || "未知"}；合规线索：${Array.isArray(task.compliance) ? task.compliance.join("、") : "未知"}`,
      `用户补充要求：${task.requestNote || "优先核实需求、采购价、MOQ、目标售价、合规物流、买家类型和下一步验证动作。"}`,
      `先运行 node scripts/codex-research-bridge.mjs status --project-id ${task.projectId} --candidate-id ${task.candidateId} 读取该产品的精简上下文。优先使用官方、供应商、目标市场电商、买家网站等公开来源；无法核验的内容必须写未知，禁止编造销量、成交价、认证或买家意向。`,
      "同时尽量找到1–6张该具体产品的公开商品图片直链及原商品页；找不到原图时可使用与产品明确对应的搜索缩略图，但必须同时提供其落地链接。不得使用Logo、无链接素材或把同一张图套给其他产品。无法核验时保持空数组。",
      "输出JSON字段：note（简洁调研结论，可包含多个来源）、evidenceUrl（最重要的直接来源）、nextAction（可执行下一步）、recommendedStage（idea/research/shortlist/sample/validation/validated/rejected之一）、imageUrls、imageSourceRef。推荐阶段只是建议，不得直接改变人工阶段。",
      `最后运行 node scripts/codex-research-bridge.mjs assist-import --project-id ${task.projectId} --candidate-id ${task.candidateId} --run-id ${task.runId} --file <结果JSON> 写回，并再次运行 status 确认AI建议已进入该产品历史记录。`,
    ].join("\n");
  }
  if (task.taskType === "candidate_images") {
    return [
      "为 LightLink 产品池补充可核验的真实商品图片，并直接写回本地工作台。不要生成图片，不要使用Logo或无来源素材。",
      `图片任务：${task.runId}；项目：${task.projectId} · ${task.projectName}`,
      `候选产品：${JSON.stringify(task.candidates)}`,
      "逐项查找公开可访问的官方商品页、供应商商品页或目标市场电商商品页。每款产品提供1–3张直接图片URL和对应落地页 imageSourceRef；找不到原图时可使用与产品名称/变体明确对应的搜索缩略图，但必须保留其可访问落地链接。无法可靠取得时跳过该产品并在结果中留空，不得复用同一图片URL。",
      "输出JSON：{ images: [{ candidateId, imageUrls, imageSourceRef }] }。",
      `最后运行 node scripts/codex-research-bridge.mjs images-import --project-id ${task.projectId} --run-id ${task.runId} --file <结果JSON> 写回，再次运行 status 确认图片已入库。`,
    ].join("\n");
  }
  if (task.taskType === "research") {
    return [
      "完成下面的 LightLink 产品与市场调研任务，并把结构化结果直接写回本地工作台，不要只给建议或操作说明。",
      `调研项目：${task.projectId}`,
      `调研运行：${task.researchRunId}`,
      `产品：${task.productName}${task.productCategory ? ` · ${task.productCategory}` : ""}`,
      `产品说明：${task.productDescription || "待研究补充"}`,
      `目标市场：${task.targetMarkets.join("、")}；研究语言：${task.languages.join("、")}`,
      `优先渠道：${task.channels.join("、") || "Google Trends、供应平台、目标市场电商、买家网站和官方法规"}`,
      `研究模板：${task.templateId}`,
      `研究目标：${task.objectives || "验证需求、竞争、采购可行性与市场进入路径"}`,
      `已知约束：${task.constraints || "无"}`,
      `补充要求：${task.requestNote || "优先使用免费、官方、公开且可核验的来源；证据不足必须明确标注。"}`,
      `候选产品池进度：当前 ${task.candidateCount} / ${task.targetCandidateCount} 条。`,
      task.globalBuyerKnowledge?.profileCount || task.globalBuyerKnowledge?.taxonomy?.personaCategories?.length
        ? `系统已匹配可复用的全球买家知识与商业分类：${task.globalBuyerKnowledge.taxonomy?.personaCategories?.length ?? 0} 个画像分类、${task.globalBuyerKnowledge.taxonomy?.productTracks?.length ?? 0} 个产品赛道、${task.globalBuyerKnowledge.profileCount} 家真实组织、${task.globalBuyerKnowledge.familyLinkCount} 条公司—家族关系。先用“地区→画像分类→采购场景→产品赛道→产品家族”定义研究范围，再用真实公司和直接来源验证；不得把分类关系或“已初筛”描述成真实采购意向。共享知识：${JSON.stringify(task.globalBuyerKnowledge)}`
        : "系统暂无匹配的全球买家知识；本轮发现的新买家画像和家族关系写回后会进入共享知识库，供后续项目复用。",
      task.runMode === "expand_candidates"
        ? `本轮任务：扩充候选产品池。至少整理 ${task.requestedCandidateCount} 个与现有产品不重复的新候选；必须给出具体产品名、所属赛道、细分领域和对应国家，并在来源可核验时同步回填已有缺图候选的图片与图片来源；不得只重复旧结论或只列赛道。`
        : "本轮任务：复查已有结论、证据和候选状态；只在发现真实新方向时增加候选产品。",
      task.runMode === "expand_candidates"
        ? `先运行 node scripts/codex-research-bridge.mjs status --project-id ${task.projectId}，读取项目、待办和已有产品名称。`
        : `先运行 node scripts/codex-research-bridge.mjs status --project-id ${task.projectId} --review，读取项目、待办和已有候选的精简复查数据。`,
      "不要递归扫描 node_modules、dist、.next、.wrangler 或数据库文件，也不要在终端回显完整候选表、完整报告或完整JSON；只输出必要的计数与校验摘要。需要排障时才使用 status --full。",
      "按八个章节研究：产品定义、市场需求、竞品与价格、买家与渠道、供应与MOQ、合规与物流、单位经济、结论与行动。",
      "如果项目包含多个产品大类或多个国家/地区，必须按“产品大类 × 国家/地区”形成判断矩阵；每个组合说明目标客户、需求证据、竞争价格带、供应可行性、合规门槛、预算占用、主要风险和进入优先级。候选方向应尽量丰富但不重复，不要固定缩减为 6–7 个，也不要为了凑数编造证据。",
      "研究主线必须是买家先行，而不是寻找爆品：真实批发买家 → 买家画像 → 销售/采购场景 → 产品家族矩阵 → 具体候选产品 → 对应市场。只收录可由公司官网、公开采购页面、展会名录或可信商业目录证明存在的真实组织，不得把泛化买家类型伪装成公司。产品家族用于复用买家、渠道、供应链和合规判断；同一家族内候选必须是可区分的款式或商业变体，不能只是同义词。",
      "trackCategories 字段：id、name、description、subcategories、targetMarkets、buyerTypes、priority(high/medium/low)、opportunityScore(0-100或null)、evidenceStatus(hypothesis/partial/validated)。",
      `productPool 字段：id、name、trackCategory、subcategory、productFamily、commercialVariant、imageUrls、imageSourceRef、targetMarkets、buyerTypes、priceBand、moq、compliance、riskLevel(low/medium/high/unknown)、stage(idea/research/sample/validation/shortlist/validated/rejected)、score(0-100或null)、rationale、evidenceStatus。productFamily 必须是稳定、可复用的产品族名称；不要直接复制具体款式名。本项目累计目标为 ${task.targetCandidateCount} 条；系统会和已有 ${task.candidateCount} 条自动去重，后续可继续分轮扩充。imageUrls 最多6张，必须是该产品对应的公开图片直链；imageSourceRef 记录商品或来源页面。无法核验时保持空数组，严禁把同一张图片重复套给多个产品。不得为了凑数编造需求、销量或价格证据。`,
      "buyerProfiles 字段：companyName、website、country、buyerType、customerGroups、salesChannels、purchasingScenarios、seasonality、replenishmentCycle、orderRequirements、sourceUrl、profileStatus(hypothesis/qualified)。companyName 必须是真实组织名称，sourceUrl 必须直接证明该组织及其经营/采购场景；只有公开资料充分时才标 qualified，AI 不能标 validated。不要采集私人联系方式或猜测采购金额。",
      "buyerFamilyMatrix 字段：companyName、country、trackCategory、productFamily、relationshipScore(0-100)、familyRole(core/cross_sell/seasonal/test)、salesScenarios、rationale、evidenceStatus(hypothesis/partial)。关系度必须解释是核心常采、跨品类加购、季节采购还是小单测试；没有证据时不得给高分。每个家族必须能在 productPool 中找到对应候选。",
      "marketHypotheses 字段：marketCode、marketName、demandHypothesis、buyerTypes、entryMode、complianceFocus、recommendedTracks、validationStatus(hypothesis/partial/validated)。",
      "在线启动方案长期维护11个模块：总览与边界、大赛道地图、候选产品池、筛选机制、市场映射、180天路线、两人SOP、预算与报价、合规供应链、获客与成交、执行清单。除前三个结构化集合外，在 playbook 中输出 roadmap180Days、teamSop、budgetAndQuoting、complianceSupplyChain、customerAcquisition、executionChecklist；每项包含 summary 和 items 字符串数组。",
      "如果研究目标中包含预算和团队人数，还要给出预算分配、两人职责拆分、前30/60/90天行动表、每周关键指标以及停止/继续条件，确保方案能够直接执行。",
      "数码小家电模板采用五维100分卡：合规安全25、市场买家20、单位经济20、供应稳定20、销售表达15。不能核验的价格、销量、认证和法规结论保持未知，不得编造。",
      "每条证据必须保留来源标题、直接URL、国家/市场、采集时间、状态和简短依据；登录受限、地区限制、失败与确认零必须区分。",
      "将结果保存为 JSON：status、summary、recommendation(go/test/hold/reject)、scorecard、buyerProfiles、buyerFamilyMatrix、trackCategories、productPool、marketHypotheses、playbook、sections、risks、actionPlan、evidence。",
      `最后运行 node scripts/codex-research-bridge.mjs import --project-id ${task.projectId} --run-id ${task.researchRunId} --file <结果JSON> 写回，再次运行 status 确认历史、证据和结论已经入库。`,
    ].join("\n");
  }
  return [
    "使用 $lightlink-radar-bridge 处理下面的 LightLink Radar 待办任务，并直接完成，不要只给操作说明。",
    `任务编号：${task.runId}`,
    `主题：${task.query}`,
    `范围：${task.market} 市场 · ${task.language.toUpperCase()} 关键词 · 近 ${task.windowDays} 天 · ${task.mode === "discover" ? "热点发现" : "关键词扫描"}`,
    `结果数量：整理 ${task.resultLimit} 个彼此不同、具有采购意义的关键词簇；不要固定缩减为 6–7 个，证据不足时保留空值和准确状态。`,
    `整理要求：${task.requestNote || "优先使用免费、官方或公开且可核验的来源。"}`,
    "先读取指定任务；采集或整理可核验证据，严格区分缺失、失败与确认零；写回雷达后再次读取并确认来源明细和历史记录。",
    "每个关键词簇同时整理准确的简体中文品名 keywordZh。可提供 1–6 张不同产品图到 imageUrls，并把图片所在的原商品页或 API URL 写入 imageSourceRef；禁止使用图片搜索结果、图库、品牌 Logo 或与来源页无关的图片，同一图片 URL 不得复用于不同词簇。无法核验时 imageUrls 留空数组。",
    "核心来源包含 TikTok、Meta Ads、Instagram、Google Trends 和 Alibaba.com；Google Trends 优先使用官方 Trends 页面或 CSV，platform 写 Google Trends，metric 写 attention，并保留直接来源链接。",
    "从 Amazon、Temu、SHEIN、eBay、Walmart、Etsy、AliExpress、Shopee、Lazada、Mercado Libre、Rakuten 中选择 2–5 个与目标市场和产品最相关的补充电商来源。免配置时优先可直接访问的官方搜索页或商品页；有授权时再用官方 API 或导出。页面登录、地区限制或反自动化时记录准确失败状态，不绕过限制。商品页只用于商品、图片、价格和市场验证，不得把商品结果数写成关键词搜索量。",
    "采购价只从可核验供应商或商品来源提取，写入 purchasePriceMin、purchasePriceMax、purchasePriceCurrency（三位币种代码）和 purchasePriceUnit；无法核验时留空。",
    task.market === "GLOBAL"
      ? "全球任务的每条证据应在 geoScope 写实际国家代码；只有来源确实为全球汇总或无法细分时才写 GLOBAL。"
      : `单一国家任务的 geoScope 写 ${task.market}；只有来源确实为全球汇总时才写 GLOBAL。`,
    `写回文件根级字段同时保留 scanMode=${task.mode} 和 resultLimit=${task.resultLimit}，不要把任务类型改成 AI 整理。`,
  ].join("\n");
}

export function originAllowed(origin) {
  return ALLOWED_ORIGINS.has(origin);
}

export function terminalJobStatus(turnStatus) {
  if (turnStatus === "completed") return "completed";
  if (turnStatus === "interrupted") return "interrupted";
  if (turnStatus === "failed") return "failed";
  return null;
}

export function progressForItem(item, currentProgress = 20) {
  if (!item || typeof item !== "object") return { progress: currentProgress, phase: "正在分析任务" };
  if (item.type === "webSearch") return { progress: Math.max(currentProgress, 45), phase: "正在采集公开证据" };
  if (item.type === "commandExecution") {
    const command = String(item.command ?? "");
    if (/codex-(?:radar|research|taxonomy|trade|opportunity)-bridge\.mjs\s+(?:import|assist-import|images-import)/i.test(command)) return { progress: Math.max(currentProgress, 78), phase: "正在写回雷达" };
    if (/codex-(?:radar|research|taxonomy|trade|opportunity)-bridge\.mjs\s+status/i.test(command) && currentProgress >= 70) return { progress: Math.max(currentProgress, 92), phase: "正在复读核验结果" };
    return { progress: Math.max(currentProgress, 58), phase: "正在整理与校验数据" };
  }
  if (item.type === "agentMessage") return { progress: Math.max(currentProgress, 30), phase: "正在分析任务" };
  return { progress: Math.max(currentProgress, 25), phase: "正在处理任务" };
}

class CodexAppServerClient {
  constructor(channel) {
    this.channel = channel;
    this.stateFile = join(STATE_DIR, channel.stateFile);
    this.proc = null;
    this.sequence = 0;
    this.pending = new Map();
    this.starting = null;
    this.threadId = null;
    this.activeJob = null;
    this.lastJob = null;
  }

  async start() {
    if (this.proc && !this.proc.killed) return;
    if (this.starting) return this.starting;
    this.starting = this.#startProcess();
    try {
      await this.starting;
    } finally {
      this.starting = null;
    }
  }

  async #startProcess() {
    const codexBin = process.env.LIGHTLINK_CODEX_BIN || "codex";
    const childEnv = { ...process.env };
    for (const key of [
      "CODEX_APP_TOOLS_PIPE_PATH",
      "CODEX_CI",
      "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
      "CODEX_SESSION_ID",
      "CODEX_THREAD_ID",
    ]) {
      delete childEnv[key];
    }
    const proc = spawn(codexBin, ["app-server", "--stdio"], {
      cwd: PROJECT_ROOT,
      env: childEnv,
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    this.proc = proc;
    proc.stdout.setEncoding("utf8");
    proc.stderr.setEncoding("utf8");
    const lines = createInterface({ input: proc.stdout });
    lines.on("line", (line) => this.#receive(line));
    proc.stderr.on("data", (chunk) => process.stderr.write(`[codex:${this.channel.id}] ${chunk}`));
    proc.once("exit", (code) => {
      const error = new Error(`Codex 通道已停止（${code ?? "unknown"}）`);
      for (const entry of this.pending.values()) entry.reject(error);
      this.pending.clear();
      this.proc = null;
      if (this.activeJob) this.activeJob = { ...this.activeJob, status: "failed", error: error.message };
    });
    proc.once("error", (error) => {
      for (const entry of this.pending.values()) entry.reject(error);
      this.pending.clear();
      this.proc = null;
    });
    await this.request("initialize", {
      clientInfo: {
        name: `lightlink_radar_${this.channel.id}`,
        title: this.channel.title,
        version: "0.1.0",
      },
    });
    this.notify("initialized", {});
  }

  #receive(line) {
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      return;
    }
    if (message.id != null && !message.method) {
      const entry = this.pending.get(message.id);
      if (!entry) return;
      clearTimeout(entry.timer);
      this.pending.delete(message.id);
      if (message.error) entry.reject(new Error(message.error.message || "Codex 请求失败"));
      else entry.resolve(message.result);
      return;
    }
    if (message.method === "turn/started" && this.activeJob) {
      this.activeJob = {
        ...this.activeJob,
        status: "running",
        turnId: message.params?.turn?.id ?? this.activeJob.turnId,
        progress: Math.max(this.activeJob.progress ?? 0, 20),
        phase: "Codex 已接收，正在分析",
        lastActivityAt: new Date().toISOString(),
      };
    }
    if (message.method === "item/started" && this.activeJob) {
      const next = progressForItem(message.params?.item, this.activeJob.progress);
      this.activeJob = {
        ...this.activeJob,
        ...next,
        lastActivityAt: new Date().toISOString(),
      };
    }
    if (message.method === "item/completed" && this.activeJob) {
      this.activeJob = {
        ...this.activeJob,
        completedItems: (this.activeJob.completedItems ?? 0) + 1,
        lastActivityAt: new Date().toISOString(),
      };
    }
    if (message.method === "turn/plan/updated" && this.activeJob) {
      const plan = Array.isArray(message.params?.plan) ? message.params.plan : [];
      const completed = plan.filter((step) => step?.status === "completed").length;
      const planProgress = plan.length ? 25 + Math.round((completed / plan.length) * 55) : 25;
      this.activeJob = {
        ...this.activeJob,
        progress: Math.max(this.activeJob.progress ?? 0, planProgress),
        phase: message.params?.explanation || this.activeJob.phase || "正在执行计划",
        lastActivityAt: new Date().toISOString(),
      };
    }
    if (message.method === "turn/completed" && this.activeJob) {
      const turn = message.params?.turn;
      const sameTurn = !this.activeJob.turnId || !turn?.id || turn.id === this.activeJob.turnId;
      if (sameTurn) this.#finishActiveJob(turn);
    }
    if (message.method === "error") {
      process.stderr.write(`[codex-event] ${JSON.stringify(message.params ?? {})}\n`);
    }
  }

  #finishActiveJob(turn) {
    if (!this.activeJob) return;
    const status = terminalJobStatus(turn?.status) ?? "failed";
    const phase = status === "completed"
      ? "任务已完成"
      : status === "interrupted"
        ? "任务已中断"
        : "任务执行失败";
    const finishedJob = {
      ...this.activeJob,
      status,
      progress: status === "completed" ? 100 : this.activeJob.progress,
      phase,
      error: turn?.error?.message ?? this.activeJob.error,
      completedAt: new Date().toISOString(),
    };
    this.lastJob = finishedJob;
    this.activeJob = null;
    if (status !== "completed") reportResearchFailure(finishedJob, finishedJob.error || phase);
  }

  request(method, params, timeoutMs = 20_000) {
    if (!this.proc?.stdin) return Promise.reject(new Error("Codex 通道尚未启动"));
    const id = ++this.sequence;
    return new Promise((resolveRequest, rejectRequest) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        rejectRequest(new Error(`Codex ${method} 请求超时`));
      }, timeoutMs);
      this.pending.set(id, { resolve: resolveRequest, reject: rejectRequest, timer });
      this.proc.stdin.write(`${JSON.stringify({ method, id, params })}\n`);
    });
  }

  notify(method, params) {
    this.proc?.stdin?.write(`${JSON.stringify({ method, params })}\n`);
  }

  async #createThread(task) {
    const result = await this.request("thread/start", {
      cwd: PROJECT_ROOT,
      approvalPolicy: "never",
      sandbox: "workspace-write",
    });
    const threadId = result?.thread?.id;
    if (!threadId) throw new Error("Codex 没有返回任务编号");
    const subject = String(task.productName || task.candidateName || task.productFamilyName || task.projectName || task.query || "新任务").trim().slice(0, 28);
    await this.request("thread/name/set", { threadId, name: `${this.channel.title} · ${subject}` });
    await mkdir(STATE_DIR, { recursive: true });
    await writeFile(this.stateFile, `${JSON.stringify({ threadId }, null, 2)}\n`, "utf8");
    return threadId;
  }

  async dispatch(task) {
    if (this.activeJob) throw new Error(`${this.channel.title}仍有任务正在处理；其他通道可以继续使用`);
    await this.start();
    // Every job gets a clean task context. State lives in the local bridge, so
    // reusing an ever-growing Codex conversation only wastes tokens.
    const threadId = await this.#createThread(task);
    this.threadId = threadId;
    const skillPath = join(process.env.USERPROFILE || "", ".codex", "skills", "lightlink-radar-bridge", "SKILL.md");
    const input = [];
    if (!["research", "candidate_assist", "candidate_images", "taxonomy_assist", "trade_data", "opportunity_validation"].includes(task.taskType)) {
      try {
        await access(skillPath);
        input.push({ type: "skill", name: "lightlink-radar-bridge", path: skillPath });
      } catch {
        // The text prompt still names the skill and the task remains executable through the bridge script.
      }
    }
    input.push({ type: "text", text: buildTaskPrompt(task) });
    this.activeJob = {
      channelId: this.channel.id,
      channelTitle: this.channel.title,
      taskType: ["research", "candidate_assist", "candidate_images", "taxonomy_assist", "trade_data", "opportunity_validation"].includes(task.taskType) ? task.taskType : "radar",
      runId: task.taskType === "research" ? task.researchRunId : task.runId,
      projectId: ["research", "candidate_assist", "candidate_images"].includes(task.taskType) ? task.projectId : undefined,
      researchRunId: task.taskType === "research" ? task.researchRunId : undefined,
      candidateId: task.taskType === "candidate_assist" ? task.candidateId : undefined,
      query: task.taskType === "research" ? task.productName : task.taskType === "candidate_assist" ? task.candidateName : task.taskType === "candidate_images" ? `${task.projectName} · 补产品图片` : task.taskType === "taxonomy_assist" ? `${task.mode === "enrich" ? "复核" : "补充"}买家画像${task.personaCode ? ` · ${task.personaCode}` : ""}` : task.taskType === "trade_data" ? `${task.productFamilyName} · 贸易数据` : task.taskType === "opportunity_validation" ? `${task.productFamilyName} · 商机验证` : task.query,
      market: ["research", "candidate_assist"].includes(task.taskType) ? task.targetMarkets.join(",") : task.taskType === "taxonomy_assist" ? "GLOBAL" : ["trade_data", "opportunity_validation"].includes(task.taskType) ? task.regionCode : task.market,
      language: ["research", "candidate_assist"].includes(task.taskType) ? task.languages.join(",") : ["taxonomy_assist", "trade_data", "opportunity_validation"].includes(task.taskType) ? "zh-CN" : task.language,
      windowDays: task.windowDays,
      resultLimit: task.resultLimit,
      mode: task.mode,
      threadId,
      turnId: null,
      status: "starting",
      progress: 10,
      phase: "正在发送到 Codex",
      completedItems: 0,
      startedAt: new Date().toISOString(),
      lastActivityAt: new Date().toISOString(),
    };
    try {
      const result = await this.request("turn/start", {
        threadId,
        input,
        cwd: PROJECT_ROOT,
        approvalPolicy: "never",
        sandboxPolicy: {
          type: "workspaceWrite",
          writableRoots: [PROJECT_ROOT],
          networkAccess: true,
        },
        turnTrigger: "lightlink_radar_button",
      });
      this.activeJob = {
        ...this.activeJob,
        turnId: result?.turn?.id ?? null,
        status: "running",
        progress: Math.max(this.activeJob.progress, 20),
        phase: "Codex 已接收，正在分析",
        lastActivityAt: new Date().toISOString(),
      };
    } catch (error) {
      const failedJob = {
        ...this.activeJob,
        status: "failed",
        phase: "任务发送失败",
        error: error instanceof Error ? error.message : String(error),
        completedAt: new Date().toISOString(),
      };
      this.lastJob = failedJob;
      this.activeJob = null;
      reportResearchFailure(failedJob, failedJob.error);
      throw error;
    }
    return this.activeJob;
  }

  async refreshStatus() {
    if (!this.proc) return this.status();
    if (!this.activeJob?.threadId || !this.activeJob.turnId) return this.status();
    try {
      const result = await this.request("thread/read", {
        threadId: this.activeJob.threadId,
        includeTurns: true,
      });
      const turns = Array.isArray(result?.thread?.turns) ? result.thread.turns : [];
      const turn = turns.find((entry) => entry?.id === this.activeJob?.turnId);
      if (terminalJobStatus(turn?.status)) this.#finishActiveJob(turn);
    } catch (error) {
      process.stderr.write(`[codex-status] ${error instanceof Error ? error.message : String(error)}\n`);
    }
    return this.status();
  }

  status() {
    return {
      id: this.channel.id,
      title: this.channel.title,
      ready: Boolean(this.proc && !this.proc.killed),
      threadId: this.threadId,
      activeJob: this.activeJob,
      lastJob: this.lastJob,
    };
  }

  close() {
    this.proc?.kill();
  }
}

export class CodexChannelManager {
  constructor() {
    this.channels = new Map(
      Object.values(CHANNEL_DEFINITIONS).map((channel) => [channel.id, new CodexAppServerClient(channel)]),
    );
  }

  async dispatch(task) {
    const channelId = channelIdForTask(task);
    const client = this.channels.get(channelId);
    if (!client) throw new Error("未找到对应的 Codex 任务通道");
    return client.dispatch(task);
  }

  async refreshStatus() {
    await Promise.all([...this.channels.values()].map((client) => client.refreshStatus()));
    return this.status();
  }

  status() {
    const channels = Object.fromEntries([...this.channels.entries()].map(([id, client]) => [id, client.status()]));
    const activeJobs = Object.values(channels).map((channel) => channel.activeJob).filter(Boolean);
    const lastJobs = Object.values(channels)
      .map((channel) => channel.lastJob)
      .filter(Boolean)
      .sort((left, right) => String(right.completedAt ?? "").localeCompare(String(left.completedAt ?? "")));
    const firstThread = Object.values(channels).find((channel) => channel.threadId)?.threadId ?? null;
    return {
      ready: true,
      threadId: channels.radar.threadId ?? firstThread,
      activeJob: activeJobs[0] ?? null,
      lastJob: lastJobs[0] ?? null,
      activeJobs,
      lastJobs,
      channels,
    };
  }

  close() {
    for (const client of this.channels.values()) client.close();
  }
}

async function readJson(request) {
  let body = "";
  for await (const chunk of request) {
    body += chunk;
    if (body.length > 64 * 1024) throw new Error("请求内容过大");
  }
  return JSON.parse(body || "{}");
}

function sendJson(response, status, payload, origin) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": originAllowed(origin) ? origin : "http://127.0.0.1:8787",
    "vary": "Origin",
    "cache-control": "no-store",
  });
  response.end(JSON.stringify(payload));
}

export async function main() {
  const codex = new CodexChannelManager();
  const server = createServer(async (request, response) => {
    const origin = String(request.headers.origin || "");
    if (!originAllowed(origin)) {
      sendJson(response, 403, { error: "只允许本机 LightLink Radar 调用" }, origin);
      return;
    }
    if (request.method === "OPTIONS") {
      response.writeHead(204, {
        "access-control-allow-origin": origin,
        "access-control-allow-methods": "GET, POST, OPTIONS",
        "access-control-allow-headers": "content-type",
        "access-control-max-age": "600",
        "vary": "Origin",
      });
      response.end();
      return;
    }
    if (request.method === "GET" && request.url === "/status") {
      try {
        sendJson(response, 200, await codex.refreshStatus(), origin);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Codex 通道启动失败";
        sendJson(response, 503, { ...codex.status(), error: message }, origin);
      }
      return;
    }
    if (request.method === "POST" && request.url === "/dispatch") {
      try {
        const task = validateDispatch(await readJson(request));
        const job = await codex.dispatch(task);
        sendJson(response, 202, { accepted: true, ...job }, origin);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Codex 任务发送失败";
        sendJson(response, message.includes("仍在处理") ? 409 : 400, { error: message }, origin);
      }
      return;
    }
    sendJson(response, 404, { error: "未找到接口" }, origin);
  });
  server.listen(PORT, HOST, () => {
    process.stdout.write(`LightLink Codex channel ready on http://${HOST}:${PORT}\n`);
  });
  const stop = () => {
    codex.close();
    server.close(() => process.exit(0));
  };
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
}

const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
