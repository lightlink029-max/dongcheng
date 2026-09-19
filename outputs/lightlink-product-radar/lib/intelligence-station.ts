import { TRADE_SOURCE_CATALOG } from "./trade-source-catalog.ts";

export type MarketSignalType =
  | "event"
  | "attention"
  | "b2b_demand"
  | "supply_competition"
  | "official_trade"
  | "regulation"
  | "internal";

export type TriggerCategory =
  | "seasonal"
  | "event"
  | "macro_risk"
  | "weather_health"
  | "regulation"
  | "industry"
  | "procurement"
  | "attention";

export type TriggerDefinition = {
  id: string;
  category: TriggerCategory;
  name: string;
  description: string;
  defaultSignalTypes: MarketSignalType[];
};

export const MARKET_SIGNAL_LAYERS: Array<{
  id: MarketSignalType;
  name: string;
  description: string;
  decisionUse: string;
  warning: string;
}> = [
  {
    id: "event",
    name: "事件与时机",
    description: "季节、赛事、天气、战争、设备周期和供应中断等采购触发条件。",
    decisionUse: "判断为什么现在值得监控，以及机会窗口能否覆盖采购和交付周期。",
    warning: "事件本身不等于真实采购需求。",
  },
  {
    id: "attention",
    name: "注意力",
    description: "搜索趋势、短视频爆款、内容互动和跨境电商热榜。",
    decisionUse: "发现新关键词、用途、受众和关注度变化。",
    warning: "关注度不等于采购量或成交额。",
  },
  {
    id: "b2b_demand",
    name: "B2B采购意向",
    description: "公开采购请求、RFQ、招标、买家目录变化和补货信号。",
    decisionUse: "判断是否存在更接近采购行为的公开意向。",
    warning: "仍需核实发布时间、买家身份、规格、数量和有效期。",
  },
  {
    id: "supply_competition",
    name: "供给与竞争",
    description: "供应商密度、产地、公开价格、MOQ、交期、认证和渠道竞争。",
    decisionUse: "判断供给拥挤程度和中国供应链可执行性。",
    warning: "商品数量不是需求；页面价格不是可成交报价。",
  },
  {
    id: "official_trade",
    name: "进口与贸易事实",
    description: "官方进口额、数量、伙伴结构、同比、环比、季节性和单位价值代理。",
    decisionUse: "核验地区市场规模、变化方向和进口来源结构。",
    warning: "进口额不等于终端销售额，HS 编码也不总能精确对应产品家族。",
  },
  {
    id: "regulation",
    name: "法规与准入",
    description: "认证、标签、能效、包装、责任主体、关税和禁限用规则变化。",
    decisionUse: "识别进入窗口或不可跨越的阻断项。",
    warning: "摘要不能代替法规原文、证书原件和专业核验。",
  },
  {
    id: "internal",
    name: "内部业务结果",
    description: "Odoo 中的真实线索、回复、RFQ、报价、样品、订单、利润、履约和复购。",
    decisionUse: "验证客户价值、供应能力和是否值得进入下一轮。",
    warning: "样本不足时不能外推到整个市场。",
  },
];

export const TRIGGER_CATALOG: TriggerDefinition[] = [
  { id: "daily_replenishment", category: "seasonal", name: "日常补货", description: "常规消耗、库存安全线和固定补货周期。", defaultSignalTypes: ["b2b_demand", "official_trade", "internal"] },
  { id: "season_change", category: "seasonal", name: "换季", description: "气温、日照、雨雪和生活场景随季节变化。", defaultSignalTypes: ["event", "attention", "official_trade"] },
  { id: "back_to_school", category: "seasonal", name: "返校季", description: "学校开学、教育预算和学生用品采购窗口。", defaultSignalTypes: ["event", "attention", "b2b_demand", "official_trade"] },
  { id: "holiday_promotion", category: "seasonal", name: "节日与促销季", description: "圣诞、斋月、黑五等节庆和促销采购。", defaultSignalTypes: ["event", "attention", "b2b_demand"] },
  { id: "sports_event", category: "event", name: "大型赛事", description: "世界杯、奥运会、区域赛事及其周边采购。", defaultSignalTypes: ["event", "attention", "b2b_demand"] },
  { id: "trade_show", category: "event", name: "展会与行业活动", description: "专业展会、发布会和行业大会带来的采购窗口。", defaultSignalTypes: ["event", "b2b_demand"] },
  { id: "war_sanction", category: "macro_risk", name: "战争与制裁", description: "战争、制裁、出口管制和供应路线变化。", defaultSignalTypes: ["event", "official_trade", "regulation"] },
  { id: "fx_freight", category: "macro_risk", name: "汇率与运价", description: "汇率、燃油、海运和航空成本的显著变化。", defaultSignalTypes: ["event", "official_trade", "internal"] },
  { id: "extreme_weather", category: "weather_health", name: "极端天气与灾害", description: "高温、低温、洪水、台风、火灾、地震等。", defaultSignalTypes: ["event", "attention", "b2b_demand"] },
  { id: "public_health", category: "weather_health", name: "公共卫生事件", description: "疫情、健康政策和防护需求变化。", defaultSignalTypes: ["event", "attention", "b2b_demand", "regulation"] },
  { id: "regulatory_change", category: "regulation", name: "法规与认证变化", description: "准入、标签、包装、能效、关税和生产者责任变化。", defaultSignalTypes: ["regulation", "official_trade"] },
  { id: "equipment_refresh", category: "industry", name: "设备更新", description: "设备寿命、技术替代、维护周期和预算更新。", defaultSignalTypes: ["event", "b2b_demand", "official_trade"] },
  { id: "technology_upgrade", category: "industry", name: "技术升级与新品", description: "新标准、新接口、新平台或新品发布产生的配套需求。", defaultSignalTypes: ["event", "attention", "supply_competition"] },
  { id: "supply_disruption", category: "industry", name: "供应中断与召回", description: "停产、召回、原料短缺或产能迁移带来的替代采购。", defaultSignalTypes: ["event", "supply_competition", "official_trade"] },
  { id: "tender_project", category: "procurement", name: "项目与公开招标", description: "政府、企业或工程项目的公开采购。", defaultSignalTypes: ["b2b_demand", "regulation"] },
  { id: "rfq_growth", category: "procurement", name: "RFQ与采购请求增长", description: "B2B平台或行业渠道的有效采购请求增加。", defaultSignalTypes: ["b2b_demand", "supply_competition"] },
  { id: "social_breakout", category: "attention", name: "短视频与社媒爆款", description: "TikTok、YouTube、Meta 等内容快速增长。", defaultSignalTypes: ["attention", "supply_competition"] },
  { id: "search_growth", category: "attention", name: "搜索关键词增长", description: "Google Trends、Keyword Planner 等搜索需求变化。", defaultSignalTypes: ["attention", "official_trade"] },
  { id: "commerce_bestseller", category: "attention", name: "跨境平台热卖", description: "历史热卖、榜单、评价和商品供给变化。", defaultSignalTypes: ["attention", "supply_competition"] },
];

export const TRIGGER_CATEGORY_LABELS: Record<TriggerCategory, string> = {
  seasonal: "周期与季节",
  event: "赛事与活动",
  macro_risk: "宏观与风险",
  weather_health: "天气与公共事件",
  regulation: "法规与准入",
  industry: "产业变化",
  procurement: "采购行为",
  attention: "注意力变化",
};

export type IntelligenceSourceDefinition = {
  id: string;
  name: string;
  signalTypes: MarketSignalType[];
  regions: string;
  access: "public" | "setup" | "authorized_export";
  priority: "P0" | "P1" | "P2";
  sourceUrl: string;
  boundary: string;
};

const TRADE_SOURCE_SIGNAL_TYPES: Record<string, MarketSignalType[]> = {
  official_trade: ["official_trade"],
  official_macro: ["official_trade", "regulation"],
  internal_sales: ["internal", "b2b_demand", "supply_competition"],
  b2b_platform: ["b2b_demand", "supply_competition"],
  private_platform: ["internal", "b2b_demand", "attention"],
};

/**
 * 情报站和“数据来源”页面共享同一份贸易来源主目录。这里仅补充情报层级，
 * 不再维护第二套名称、入口和接入说明。
 */
export const INTELLIGENCE_SOURCE_CATALOG: IntelligenceSourceDefinition[] = [
  ...TRADE_SOURCE_CATALOG.map((source): IntelligenceSourceDefinition => ({
    id: source.id,
    name: source.name,
    signalTypes: TRADE_SOURCE_SIGNAL_TYPES[source.category] ?? ["official_trade"],
    regions: source.scope,
    access: source.automation === "automatic" ? "public" : source.automation === "one_time_setup" ? "setup" : "authorized_export",
    priority: source.category === "official_trade" || source.category === "internal_sales" ? "P0" : source.category === "b2b_platform" || source.category === "private_platform" ? "P1" : "P2",
    sourceUrl: source.sourceUrl,
    boundary: `${source.chatgptCanDo} 人工责任：${source.userMustDo}`,
  })),
  { id: "google", name: "Google Trends / Keyword Planner", signalTypes: ["attention"], regions: "全球搜索", access: "setup", priority: "P2", sourceUrl: "https://trends.google.com/", boundary: "用于搜索趋势和关键词；不能替代进口或成交数据。" },
  { id: "tiktok", name: "TikTok", signalTypes: ["attention"], regions: "社交内容", access: "authorized_export", priority: "P2", sourceUrl: "https://www.tiktok.com/", boundary: "爆款内容只触发调研，需用采购和贸易来源复核。" },
  { id: "commerce", name: "跨境电商平台", signalTypes: ["attention", "supply_competition"], regions: "区域零售", access: "authorized_export", priority: "P2", sourceUrl: "https://www.amazon.com/", boundary: "榜单、商品和价格样本不代表全市场销量。" },
];

export type OpportunityCandidateType =
  | "short_term"
  | "long_term"
  | "blue_ocean_candidate"
  | "growth_red_ocean"
  | "observe";

export type AssessableMarketSignal = {
  id: string;
  signalType: MarketSignalType;
  sourceId: string;
  dataStatus: string;
  evidenceGrade: string;
  direction?: string;
  period?: string;
  confidence?: number;
};

export type MonitorSimulationScenario =
  | "candidate_ready"
  | "attention_only"
  | "missing_data"
  | "source_failure";

export type MonitorSimulationStepStatus =
  | "completed"
  | "ready"
  | "waiting"
  | "blocked"
  | "failed"
  | "not_started";

export const MONITOR_SIMULATION_SCENARIOS: Array<{
  id: MonitorSimulationScenario;
  name: string;
  description: string;
}> = [
  { id: "candidate_ready", name: "达到候选门槛", description: "模拟官方贸易、B2B采购和事件证据同时成立，进入人工复核。" },
  { id: "attention_only", name: "只有热度信号", description: "模拟搜索与内容升温，但没有采购或贸易事实，继续观察。" },
  { id: "missing_data", name: "来源等待数据", description: "模拟来源未授权或缺失，运行进入等待数据且不生成候选。" },
  { id: "source_failure", name: "来源执行失败", description: "模拟连接器失败，验证错误提示和人工处理路径。" },
];

export function marketSignalFingerprint(input: {
  sourceId: unknown;
  signalType: unknown;
  regionCode: unknown;
  personaCode?: unknown;
  productFamilyCode?: unknown;
  commodityCode?: unknown;
  period?: unknown;
  metric?: unknown;
  externalId?: unknown;
}) {
  return [
    input.sourceId,
    input.signalType,
    input.regionCode,
    input.personaCode,
    input.productFamilyCode,
    input.commodityCode,
    input.period,
    input.metric,
    input.externalId,
  ].map(normalizeMonitorScopePart).join("|");
}

export function assessSignalOpportunity(signals: AssessableMarketSignal[]) {
  const available = signals.filter((signal) => signal.dataStatus === "available");
  const evidenceGrades = new Set(["official", "primary", "internal"]);
  const reliable = available.filter((signal) => evidenceGrades.has(signal.evidenceGrade) && (signal.confidence ?? 0) >= 40);
  const sourceCount = new Set(reliable.map((signal) => signal.sourceId).filter(Boolean)).size;
  const signalTypes = new Set(reliable.map((signal) => signal.signalType));
  const demandTypes = new Set<MarketSignalType>(["official_trade", "b2b_demand", "internal"]);
  const hasDemandEvidence = reliable.some((signal) => demandTypes.has(signal.signalType));
  const blockers: string[] = [];
  if (!hasDemandEvidence) blockers.push("缺少贸易、采购或内部业务证据");
  if (sourceCount < 2) blockers.push("不足两个独立可靠来源");
  if (signalTypes.size < 2) blockers.push("不足两类交叉证据");

  const readyForReview = blockers.length === 0;
  const hasEvent = reliable.some((signal) => signal.signalType === "event");
  const demandRising = reliable.some((signal) => demandTypes.has(signal.signalType) && signal.direction === "rising");
  const competitionRising = reliable.some((signal) => signal.signalType === "supply_competition" && signal.direction === "rising");
  const competitionLimited = reliable.some((signal) => signal.signalType === "supply_competition" && ["falling", "limited"].includes(signal.direction ?? ""));
  const officialPeriods = new Set(reliable.filter((signal) => signal.signalType === "official_trade").map((signal) => signal.period).filter(Boolean)).size;
  let opportunityType: OpportunityCandidateType = "observe";
  if (readyForReview && hasEvent && hasDemandEvidence) opportunityType = "short_term";
  else if (readyForReview && demandRising && competitionLimited) opportunityType = "blue_ocean_candidate";
  else if (readyForReview && demandRising && competitionRising) opportunityType = "growth_red_ocean";
  else if (readyForReview && demandRising && officialPeriods >= 2) opportunityType = "long_term";

  return {
    readyForReview,
    opportunityType,
    evidenceCount: reliable.length,
    sourceCount,
    signalTypeCount: signalTypes.size,
    signalIds: reliable.map((signal) => signal.id),
    blockers,
  };
}

export function simulateMonitorScenario(scenario: MonitorSimulationScenario) {
  const signals: AssessableMarketSignal[] = scenario === "candidate_ready"
    ? [
        { id: "sim-official-trade", signalType: "official_trade", sourceId: "simulation-un-comtrade", dataStatus: "available", evidenceGrade: "official", direction: "rising", period: "2025", confidence: 85 },
        { id: "sim-b2b-demand", signalType: "b2b_demand", sourceId: "simulation-b2b-export", dataStatus: "available", evidenceGrade: "primary", direction: "rising", period: "current", confidence: 75 },
        { id: "sim-event", signalType: "event", sourceId: "simulation-event-calendar", dataStatus: "available", evidenceGrade: "primary", direction: "stable", period: "current", confidence: 70 },
      ]
    : scenario === "attention_only"
      ? [
          { id: "sim-attention", signalType: "attention", sourceId: "simulation-search", dataStatus: "available", evidenceGrade: "primary", direction: "rising", period: "current", confidence: 80 },
          { id: "sim-event", signalType: "event", sourceId: "simulation-event-calendar", dataStatus: "available", evidenceGrade: "primary", direction: "stable", period: "current", confidence: 70 },
        ]
      : scenario === "missing_data"
        ? [
            { id: "sim-official-missing", signalType: "official_trade", sourceId: "simulation-un-comtrade", dataStatus: "missing", evidenceGrade: "official", direction: "unknown", period: "current", confidence: 0 },
            { id: "sim-b2b-blocked", signalType: "b2b_demand", sourceId: "simulation-b2b-export", dataStatus: "blocked", evidenceGrade: "primary", direction: "unknown", period: "current", confidence: 0 },
          ]
        : [];
  const assessment = assessSignalOpportunity(signals);
  const sourceFailure = scenario === "source_failure";
  const waitingForData = scenario === "missing_data";
  const runStatus = sourceFailure ? "failed" : waitingForData ? "waiting_for_data" : "completed";
  const collectionStatus: MonitorSimulationStepStatus = sourceFailure ? "failed" : waitingForData ? "waiting" : "completed";
  const gateStatus: MonitorSimulationStepStatus = assessment.readyForReview ? "completed" : sourceFailure ? "not_started" : "blocked";
  const pipelineSteps: Array<{ id: string; name: string; status: MonitorSimulationStepStatus; detail: string }> = [
    { id: "monitor_triggered", name: "监控触发", status: "completed", detail: "调度器收到本次灰度运行，不改变正式监控的下次执行时间。" },
    { id: "source_collection", name: "来源采集", status: collectionStatus, detail: sourceFailure ? "模拟连接器返回错误。" : waitingForData ? "模拟来源未授权或暂时无数据。" : `模拟获得 ${signals.length} 条隔离证据。` },
    { id: "evidence_gate", name: "交叉证据闸门", status: gateStatus, detail: assessment.readyForReview ? "达到两个独立可靠来源、两类证据和一类需求证据的门槛。" : assessment.blockers.join("；") || "尚未执行。" },
    { id: "candidate_review", name: "机会候选人工复核", status: assessment.readyForReview ? "ready" : "not_started", detail: assessment.readyForReview ? "真实运行会创建待复核候选；灰度运行只展示预览。" : "证据闸门未通过，不产生候选。" },
    { id: "global_profile", name: "回到全球画像确认", status: assessment.readyForReview ? "waiting" : "not_started", detail: assessment.readyForReview ? "需人工确认地区、画像、场景、渠道和关联产品矩阵。" : "等待候选通过人工复核。" },
    { id: "validation_round", name: "建立第一轮验证项目", status: "not_started", detail: "只有人工从全球画像发起后才会建立，不允许灰度运行自动写入。" },
  ];
  return {
    simulation: true,
    scenario,
    runStatus,
    signals,
    assessment,
    pipelineSteps,
    nextAction: assessment.readyForReview
      ? "检查灰度步骤；确认真实来源后执行正式监控，再人工复核候选。"
      : sourceFailure
        ? "检查来源连接和错误处理后重试。"
        : waitingForData
          ? "完成来源授权或导入后重新执行。"
          : "继续观察，并补充贸易、采购或内部业务证据。",
  };
}

export function normalizeMonitorScopePart(value: unknown) {
  return String(value ?? "").trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

export function monitorScopeKey(input: {
  regionCode: unknown;
  triggerType: unknown;
  triggerName: unknown;
  personaCode?: unknown;
  productFamilyCode?: unknown;
}) {
  return [
    input.regionCode,
    input.triggerType,
    input.triggerName,
    input.personaCode,
    input.productFamilyCode,
  ].map(normalizeMonitorScopePart).join("|");
}

export function triggerById(id: string) {
  return TRIGGER_CATALOG.find((item) => item.id === id) ?? null;
}

export function signalLayerById(id: string) {
  return MARKET_SIGNAL_LAYERS.find((item) => item.id === id) ?? null;
}
