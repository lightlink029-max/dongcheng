export const OPPORTUNITY_SIGNAL_FIELDS = [
  "tradeTrend",
  "buyerDemand",
  "channelSignal",
  "personaFit",
  "leadQuality",
  "repeatPotential",
  "supplierCoverage",
  "unitEconomics",
  "complianceReadiness",
] as const;

export type OpportunitySignalField = (typeof OPPORTUNITY_SIGNAL_FIELDS)[number];

export type OpportunitySignals = Record<OpportunitySignalField, number | null>;

export type OpportunityEvidenceGrade =
  | "official"
  | "verified_buyer"
  | "supplier_quote"
  | "internal_odoo"
  | "marketplace"
  | "other";

export type OpportunityScores = {
  marketScore: number | null;
  buyerScore: number | null;
  sourcingScore: number | null;
  confidence: number;
  recommendedAction: "continue_validation" | "develop_buyers" | "source_suppliers" | "pilot" | "pause";
};

export type OpportunityAssessmentEvidence = {
  evidence_type?: unknown;
  evidenceType?: unknown;
  source_grade?: unknown;
  sourceGrade?: unknown;
  metrics?: unknown;
};

export type OpportunityAssessmentTradeRow = {
  reporter_code?: unknown;
  reporterCode?: unknown;
  commodity_code?: unknown;
  commodityCode?: unknown;
  flow?: unknown;
  period?: unknown;
  frequency?: unknown;
  metric?: unknown;
  value?: unknown;
  source_name?: unknown;
  sourceName?: unknown;
  data_status?: unknown;
  status?: unknown;
};

export type OpportunitySignalSuggestion = {
  signals: OpportunitySignals;
  reasons: Record<OpportunitySignalField, string>;
  automatedFields: OpportunitySignalField[];
  humanRequiredFields: OpportunitySignalField[];
  summary: string;
};

export type OpportunityDecision = {
  status: "validate_buyers" | "validate_supply" | "pilot_ready" | "hold" | "insufficient";
  headline: string;
  summary: string;
  readiness: number;
  nextGate: string;
  doNotDo: string;
  basis: string[];
  missingFields: OpportunitySignalField[];
};

export const OPPORTUNITY_VALIDATION_PLAN = [
  {
    key: "public_evidence",
    title: "市场与客户假设",
    owner: "assistant",
    description: "先用公开资料确认目标市场、目标客户类型、采购场景和替代方案；这里只证明值得访谈，不把公开页面当作采购意向。",
    acceptance: "至少 6 家匹配公司、3 条渠道/价格证据和 1 条官方准入来源。",
  },
  {
    key: "buyer_discovery",
    title: "客户发现访谈",
    owner: "user",
    description: "联系真实采购、品类或技术角色，先验证使用场景、现有方案、采购周期和痛点，不急着推产品或索要询盘。",
    acceptance: "至少完成 3 个有效发现访谈，并出现可复述的共同场景或痛点。",
  },
  {
    key: "offer_matrix",
    title: "产品与报价矩阵",
    owner: "shared",
    description: "把已验证的场景转成少量可销售方案，明确每个方案的客户、核心规格、差异点、目标价带和样品路径。",
    acceptance: "至少 1 个产品家族、3 个可区分方案；每个方案都有核心规格、目标客户、价带和待验证假设。",
  },
  {
    key: "supplier_feasibility",
    title: "供应可交付验证",
    owner: "user",
    description: "用冻结后的同一规格、数量、币种和贸易术语询价，核实 MOQ、样品、交期、产能、质控和证书原件。",
    acceptance: "至少 3 家同口径可比报价，其中 2 家能确认样品、交期和关键质量要求。",
  },
  {
    key: "economics_compliance",
    title: "落地成本与合规闸门",
    owner: "shared",
    description: "按目标市场计算采购、包装、运费、关税、平台/支付、售后和账期，并逐项核实强制认证、标签和清关责任。",
    acceptance: "落地毛利与现金周期达到公司门槛，强制认证和清关方案无阻断项。",
  },
  {
    key: "buyer_offer_validation",
    title: "方案报价与询盘验证",
    owner: "user",
    description: "只向匹配客户展示已通过成本和合规闸门的具体方案，验证价格、MOQ、样品、交期和决策链。",
    acceptance: "取得 3 个有效方案反馈，或 1 个带明确规格/数量/时间的 RFQ、样品或试单请求。",
  },
  {
    key: "pilot_fulfillment",
    title: "首单履约复盘",
    owner: "shared",
    description: "完成受控样品或小单后，再根据实际质量、准时交付、额外成本、索赔和回款评价供应商能力。",
    acceptance: "至少 1 个已完成并回款的样品/试单，记录验货结果、实际交期、实际毛利和异常处置。",
  },
] as const;

export type OpportunityValidationStepKey = (typeof OPPORTUNITY_VALIDATION_PLAN)[number]["key"];

export const OPPORTUNITY_SIGNAL_RESPONSIBILITIES: Record<OpportunitySignalField, {
  assistant: string;
  user: string;
}> = {
  tradeTrend: { assistant: "根据同国家、同流向、同来源的年度或月度序列计算趋势", user: "产品可能对应多个 HS 编码时确认业务口径" },
  buyerDemand: { assistant: "整理已入库的真实买家、RFQ 与公开采购证据", user: "确认私有询盘和买家真实回复" },
  channelSignal: { assistant: "汇总公开平台、市场与渠道证据", user: "提供阿里、广告或独立站后台数据" },
  personaFit: { assistant: "根据画像与产品家族关系矩阵计算匹配度", user: "确认是否符合公司的目标客户方向" },
  leadQuality: { assistant: "根据已核实买家公司和线索完整度生成建议", user: "实际联系并确认采购意愿" },
  repeatPotential: { assistant: "根据结构化复购、补货与连带采购指标计算", user: "提供订单、复购或客户反馈" },
  supplierCoverage: { assistant: "汇总供应商数量、MOQ 与报价证据", user: "询价、验厂并确认真实产能" },
  unitEconomics: { assistant: "根据毛利、运费、费用与账期数据计算", user: "提供真实成本、运费和付款条件" },
  complianceReadiness: { assistant: "整理认证、标签、运输与准入证据", user: "取得并核实证书、检测报告与清关方案" },
};

const SIGNAL_GROUPS: Array<{ key: keyof Pick<OpportunityScores, "marketScore" | "buyerScore" | "sourcingScore">; fields: Array<[OpportunitySignalField, number]> }> = [
  { key: "marketScore", fields: [["tradeTrend", 0.35], ["buyerDemand", 0.4], ["channelSignal", 0.25]] },
  { key: "buyerScore", fields: [["personaFit", 0.35], ["leadQuality", 0.4], ["repeatPotential", 0.25]] },
  { key: "sourcingScore", fields: [["supplierCoverage", 0.3], ["unitEconomics", 0.4], ["complianceReadiness", 0.3]] },
];

const EVIDENCE_WEIGHT: Record<OpportunityEvidenceGrade, number> = {
  official: 10,
  verified_buyer: 10,
  supplier_quote: 8,
  internal_odoo: 10,
  marketplace: 5,
  other: 3,
};

function scoreGroup(signals: OpportunitySignals, fields: Array<[OpportunitySignalField, number]>) {
  const available = fields.filter(([field]) => signals[field] !== null);
  if (available.length < 2) return null;
  const totalWeight = available.reduce((sum, [, weight]) => sum + weight, 0);
  const value = available.reduce((sum, [field, weight]) => sum + Number(signals[field]) * weight, 0) / totalWeight;
  return Math.round(Math.min(100, Math.max(0, value)));
}

export function normalizeOpportunitySignals(value: unknown): OpportunitySignals {
  const record = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  return Object.fromEntries(OPPORTUNITY_SIGNAL_FIELDS.map((field) => {
    const raw = record[field];
    if (raw === null || raw === undefined || raw === "") return [field, null];
    const parsed = Number(raw);
    return [field, Number.isFinite(parsed) ? Math.round(Math.min(100, Math.max(0, parsed))) : null];
  })) as OpportunitySignals;
}

export function computeOpportunityScores(
  value: unknown,
  evidenceGrades: OpportunityEvidenceGrade[] = [],
): OpportunityScores {
  const signals = normalizeOpportunitySignals(value);
  const scores = Object.fromEntries(SIGNAL_GROUPS.map((group) => [group.key, scoreGroup(signals, group.fields)])) as Pick<OpportunityScores, "marketScore" | "buyerScore" | "sourcingScore">;
  const completedSignals = OPPORTUNITY_SIGNAL_FIELDS.filter((field) => signals[field] !== null).length;
  const inputCoverage = Math.round((completedSignals / OPPORTUNITY_SIGNAL_FIELDS.length) * 45);
  const evidenceConfidence = Math.min(55, evidenceGrades.reduce((sum, grade) => sum + EVIDENCE_WEIGHT[grade], 0));
  const confidence = Math.min(100, inputCoverage + evidenceConfidence);

  let recommendedAction: OpportunityScores["recommendedAction"] = "continue_validation";
  if (confidence >= 60 && scores.marketScore !== null && scores.marketScore < 45) recommendedAction = "pause";
  else if (confidence >= 60 && (scores.marketScore ?? 0) >= 70 && (scores.buyerScore ?? 0) >= 65 && (scores.sourcingScore ?? 0) >= 60) recommendedAction = "pilot";
  else if (confidence >= 50 && (scores.marketScore ?? 0) >= 65 && (scores.buyerScore ?? 0) >= 60) recommendedAction = "develop_buyers";
  else if (confidence >= 50 && (scores.marketScore ?? 0) >= 65 && (scores.sourcingScore ?? 0) < 60) recommendedAction = "source_suppliers";

  return { ...scores, confidence, recommendedAction };
}

function objectValue(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function boundedScore(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(Math.min(100, Math.max(0, parsed))) : null;
}

function metricValue(evidence: OpportunityAssessmentEvidence[], keys: string[]) {
  const wanted = new Set(keys.map((key) => key.toLocaleLowerCase()));
  for (const item of evidence) {
    for (const [key, value] of Object.entries(objectValue(item.metrics))) {
      if (wanted.has(key.toLocaleLowerCase())) {
        const score = boundedScore(value);
        if (score !== null) return score;
      }
    }
  }
  return null;
}

function numericMetric(evidence: OpportunityAssessmentEvidence[], keys: string[]) {
  const wanted = new Set(keys.map((key) => key.toLocaleLowerCase()));
  for (const item of evidence) {
    for (const [key, value] of Object.entries(objectValue(item.metrics))) {
      if (wanted.has(key.toLocaleLowerCase())) {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
      }
    }
  }
  return null;
}

function evidenceType(item: OpportunityAssessmentEvidence) {
  return String(item.evidence_type ?? item.evidenceType ?? "");
}

function evidenceGrade(item: OpportunityAssessmentEvidence) {
  return String(item.source_grade ?? item.sourceGrade ?? "other");
}

function evidenceMetricAtLeast(evidence: OpportunityAssessmentEvidence[], keys: string[], minimum: number) {
  const wanted = new Set(keys.map((key) => key.toLocaleLowerCase()));
  return evidence.some((item) => Object.entries(objectValue(item.metrics)).some(([key, value]) => {
    const parsed = Number(value);
    return wanted.has(key.toLocaleLowerCase()) && Number.isFinite(parsed) && parsed >= minimum;
  }));
}

export function isOpportunityValidationStepDone(stepKey: OpportunityValidationStepKey, evidence: OpportunityAssessmentEvidence[]) {
  if (stepKey === "public_evidence") {
    const types = new Set(evidence
      .filter((item) => ["official", "marketplace", "other"].includes(evidenceGrade(item)))
      .map(evidenceType));
    return ["buyer", "channel", "compliance"].filter((type) => types.has(type)).length >= 2;
  }
  if (stepKey === "buyer_discovery") {
    const rows = evidence.filter((item) => evidenceType(item) === "buyer_discovery" && ["verified_buyer", "internal_odoo"].includes(evidenceGrade(item)));
    return rows.length >= 3 || evidenceMetricAtLeast(rows, ["qualified_discovery_count", "discovery_interview_count"], 3);
  }
  if (stepKey === "offer_matrix") {
    const rows = evidence.filter((item) => evidenceType(item) === "product_matrix" && ["internal_odoo", "supplier_quote"].includes(evidenceGrade(item)));
    return rows.length >= 3 || evidenceMetricAtLeast(rows, ["sellable_variant_count", "offer_count", "variant_count"], 3);
  }
  if (stepKey === "supplier_feasibility") {
    const rows = evidence.filter((item) => evidenceType(item) === "supply" && evidenceGrade(item) === "supplier_quote");
    return rows.length >= 3 || evidenceMetricAtLeast(rows, ["comparable_quote_count", "quote_count", "qualified_supplier_count"], 3);
  }
  if (stepKey === "economics_compliance") {
    const hasEconomics = evidence.some((item) => Object.keys(objectValue(item.metrics)).some((key) => ["gross_margin_pct", "margin_pct", "landed_margin_pct", "unit_economics_score"].includes(key)));
    const hasCompliance = evidence.some((item) => evidenceType(item) === "compliance" && ["official", "internal_odoo"].includes(evidenceGrade(item)));
    return hasEconomics && hasCompliance;
  }
  if (stepKey === "buyer_offer_validation") {
    const rows = evidence.filter((item) => evidenceType(item) === "buyer" && ["verified_buyer", "internal_odoo"].includes(evidenceGrade(item)));
    return evidenceMetricAtLeast(rows, ["rfq_count", "sample_request_count", "trial_order_count"], 1)
      || evidenceMetricAtLeast(rows, ["qualified_offer_response_count", "effective_response_count"], 3);
  }
  if (stepKey === "pilot_fulfillment") {
    const rows = evidence.filter((item) => evidenceType(item) === "fulfillment" && evidenceGrade(item) === "internal_odoo");
    const hasCompletedOrder = evidenceMetricAtLeast(rows, ["completed_order_count", "paid_trial_order_count"], 1);
    const hasDeliveryResult = rows.some((item) => Object.keys(objectValue(item.metrics)).some((key) => ["on_time_delivery_rate", "inspection_pass_rate", "realized_margin_pct", "claim_rate"].includes(key)));
    return hasCompletedOrder && hasDeliveryResult;
  }
  return false;
}

export function opportunityValidationPrerequisite(stepKey: OpportunityValidationStepKey, evidence: OpportunityAssessmentEvidence[]) {
  const dependencies: Partial<Record<OpportunityValidationStepKey, OpportunityValidationStepKey[]>> = {
    buyer_discovery: ["public_evidence"],
    offer_matrix: ["buyer_discovery"],
    supplier_feasibility: ["offer_matrix"],
    economics_compliance: ["supplier_feasibility"],
    buyer_offer_validation: ["economics_compliance"],
    pilot_fulfillment: ["buyer_offer_validation"],
  };
  return (dependencies[stepKey] ?? []).find((dependency) => !isOpportunityValidationStepDone(dependency, evidence)) ?? null;
}

function scoreEvidenceCount(rows: OpportunityAssessmentEvidence[], strongGrades: string[]) {
  if (!rows.length) return null;
  const strong = rows.some((item) => strongGrades.includes(evidenceGrade(item)));
  return strong
    ? Math.min(90, 55 + Math.min(4, rows.length) * 8)
    : Math.min(49, 30 + Math.min(4, rows.length) * 5);
}

export function buildOpportunityDecision(value: unknown): OpportunityDecision {
  const signals = normalizeOpportunitySignals(value);
  const knownFields = OPPORTUNITY_SIGNAL_FIELDS.filter((field) => signals[field] !== null);
  const missingFields = OPPORTUNITY_SIGNAL_FIELDS.filter((field) => signals[field] === null);
  const readiness = Math.round((knownFields.length / OPPORTUNITY_SIGNAL_FIELDS.length) * 100);
  const basis = knownFields
    .filter((field) => Number(signals[field]) >= 60)
    .map((field) => `${field}:${signals[field]}`);
  const marketSignal = [signals.tradeTrend, signals.buyerDemand, signals.channelSignal]
    .filter((score): score is number => score !== null && score >= 60).length > 0;
  const buyerFit = signals.personaFit !== null && signals.personaFit >= 60;
  const buyerProof = signals.buyerDemand !== null && signals.buyerDemand >= 60
    && signals.leadQuality !== null && signals.leadQuality >= 50;
  const sourcingProof = signals.supplierCoverage !== null && signals.supplierCoverage >= 60
    && signals.unitEconomics !== null && signals.unitEconomics >= 60
    && signals.complianceReadiness !== null && signals.complianceReadiness >= 60;
  const weakMarketSignals = [signals.tradeTrend, signals.buyerDemand, signals.channelSignal]
    .filter((score): score is number => score !== null && score < 40).length;

  if (weakMarketSignals >= 2) {
    return {
      status: "hold",
      headline: "当前证据偏弱，建议暂停投入",
      summary: "至少两项市场信号低于验证门槛；先检查 HS 口径、目标地区和买家画像是否选错，再决定是否重启。",
      readiness,
      nextGate: "复核产品口径，并找到一条独立需求证据。",
      doNotDo: "不要继续扩大采购、投放或批量开发名单。",
      basis,
      missingFields,
    };
  }

  if (marketSignal && buyerFit && !buyerProof) {
    return {
      status: "validate_buyers",
      headline: "有初步吸引力，值得做一轮低成本买家验证",
      summary: "贸易或渠道信号与画像匹配支持继续验证，但还没有真实回复证明买家现在愿意采购。",
      readiness,
      nextGate: "先完成公开买家证据包，并取得 3 个有效回复或 1 个明确 RFQ/样品请求。",
      doNotDo: "当前不要备货、付大额样品费或启动大规模广告。",
      basis,
      missingFields,
    };
  }

  if (buyerProof && !sourcingProof) {
    return {
      status: "validate_supply",
      headline: "买家方向已得到支持，下一步验证能否交付并赚钱",
      summary: "已经出现可用买家证据，但供应覆盖、落地利润或合规物流尚未全部过关。",
      readiness,
      nextGate: "取得 3 家可比报价，完成落地成本，并核实目标市场强制准入。",
      doNotDo: "在利润和合规闸门通过前，不要承诺正式交期或锁定大货。",
      basis,
      missingFields,
    };
  }

  if (marketSignal && buyerProof && sourcingProof) {
    return {
      status: "pilot_ready",
      headline: "具备小单或样品验证条件",
      summary: "市场、买家与履约三组关键闸门均有支持，可以用受控预算验证成交和复购。",
      readiness,
      nextGate: "限定客户、数量、预算和复盘日期，执行一轮样品或小单。",
      doNotDo: "仍不要直接扩成大库存；先验证交付、回款和二次采购。",
      basis,
      missingFields,
    };
  }

  return {
    status: "insufficient",
    headline: "证据不足，暂时不能判断商机价值",
    summary: "现有数据还没有同时形成市场信号与画像匹配；先补公开贸易、渠道或买家证据。",
    readiness,
    nextGate: "补齐一个可核验的市场信号和画像—产品家族匹配依据。",
    doNotDo: "不要把“未知”当作 0 分，也不要凭单一来源做采购决策。",
    basis,
    missingFields,
  };
}

function median(values: number[]) {
  const sorted = [...values].sort((left, right) => left - right);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function suggestTradeTrend(rows: OpportunityAssessmentTradeRow[]) {
  const available = rows.filter((row) => {
    const status = String(row.data_status ?? row.status ?? "available");
    return status === "available" && Number.isFinite(Number(row.value));
  });
  const annualCount = available.filter((row) => String(row.frequency) === "annual").length;
  const preferredFrequency = annualCount ? "annual" : "monthly";
  const series = new Map<string, Array<{ period: string; value: number }>>();
  for (const row of available.filter((item) => String(item.frequency) === preferredFrequency)) {
    const key = [row.reporter_code ?? row.reporterCode, row.commodity_code ?? row.commodityCode, row.flow,
      row.metric, row.source_name ?? row.sourceName].map((value) => String(value ?? "")).join("|");
    const current = series.get(key) ?? [];
    current.push({ period: String(row.period ?? ""), value: Number(row.value) });
    series.set(key, current);
  }
  const growthRates: number[] = [];
  for (const values of series.values()) {
    const sorted = [...values].sort((left, right) => left.period.localeCompare(right.period));
    const minimumPoints = preferredFrequency === "annual" ? 3 : 12;
    if (sorted.length < minimumPoints || sorted[0].value <= 0) continue;
    growthRates.push((sorted[sorted.length - 1].value - sorted[0].value) / sorted[0].value);
  }
  const growth = median(growthRates);
  if (growth === null) return null;
  const score = growth >= 0.25 ? 85 : growth >= 0.1 ? 75 : growth >= 0.03 ? 65 : growth >= -0.03 ? 55 : growth >= -0.1 ? 40 : 25;
  return {
    score,
    reason: `${preferredFrequency === "annual" ? "年度" : "月度"}同口径序列 ${growthRates.length} 组，中位区间增幅 ${(growth * 100).toFixed(1)}%。`,
  };
}

export function suggestOpportunitySignals(input: {
  evidence?: OpportunityAssessmentEvidence[];
  tradeRows?: OpportunityAssessmentTradeRow[];
  personaMatrixScore?: number | null;
}): OpportunitySignalSuggestion {
  const evidence = input.evidence ?? [];
  const signals = normalizeOpportunitySignals({});
  const reasons = Object.fromEntries(OPPORTUNITY_SIGNAL_FIELDS.map((field) => [field, "证据不足，需补充或由你确认。"] as const)) as Record<OpportunitySignalField, string>;

  const assign = (field: OpportunitySignalField, score: number | null, reason: string) => {
    if (score === null) return;
    signals[field] = Math.round(Math.min(100, Math.max(0, score)));
    reasons[field] = reason;
  };

  const tradeTrend = suggestTradeTrend(input.tradeRows ?? []);
  if (tradeTrend) assign("tradeTrend", tradeTrend.score, tradeTrend.reason);

  const buyerRows = evidence.filter((item) => ["buyer", "buyer_discovery"].includes(evidenceType(item))
    && ["verified_buyer", "internal_odoo"].includes(evidenceGrade(item)));
  const buyerDemandDirect = metricValue(evidence, ["buyer_demand_score", "rfq_score"]);
  assign("buyerDemand", buyerDemandDirect ?? scoreEvidenceCount(buyerRows, ["verified_buyer", "internal_odoo"]), buyerDemandDirect !== null
    ? "采用证据中的结构化买家需求评分。"
    : buyerRows.length ? `根据 ${buyerRows.length} 条真实买家证据生成建议；实际回复仍需人工确认。` : "");

  const channelRows = evidence.filter((item) => evidenceType(item) === "channel" || (evidenceType(item) === "competition" && evidenceGrade(item) === "marketplace"));
  const channelDirect = metricValue(evidence, ["channel_signal_score", "channel_score"]);
  assign("channelSignal", channelDirect ?? scoreEvidenceCount(channelRows, ["marketplace", "internal_odoo"]), channelDirect !== null
    ? "采用证据中的结构化渠道评分。"
    : channelRows.length ? `根据 ${channelRows.length} 条渠道或平台证据生成建议。` : "");

  const personaFitDirect = metricValue(buyerRows, ["persona_fit_score", "customer_fit_score"]);
  assign("personaFit", personaFitDirect, personaFitDirect === null
    ? "" : "采用真实客户访谈、RFQ 或成交记录中的画像匹配评分；画像矩阵只用于筛选候选客户。" );

  const verifiedBuyers = buyerRows.filter((item) => ["verified_buyer", "internal_odoo"].includes(evidenceGrade(item)));
  const leadDirect = metricValue(evidence, ["lead_quality_score", "lead_score"]);
  assign("leadQuality", leadDirect ?? scoreEvidenceCount(verifiedBuyers, ["verified_buyer", "internal_odoo"]), leadDirect !== null
    ? "采用证据中的结构化线索质量评分。"
    : verifiedBuyers.length ? `根据 ${verifiedBuyers.length} 条已核实买家或内部线索生成建议；是否回复仍需人工确认。` : "");

  const repeatDirect = metricValue(evidence, ["repeat_potential_score", "repeat_score", "reorder_score"]);
  const repeatRate = numericMetric(evidence, ["repeat_rate", "repeat_purchase_rate", "reorder_rate"]);
  assign("repeatPotential", repeatDirect ?? (repeatRate === null ? null : repeatRate <= 1 ? repeatRate * 100 : repeatRate), repeatDirect !== null
    ? "采用证据中的结构化复购评分。"
    : repeatRate !== null ? "根据已记录的复购或补货比例生成建议。" : "");

  const supplyRows = evidence.filter((item) => evidenceType(item) === "supply");
  const supplierDirect = metricValue(evidence, ["supplier_coverage_score", "supply_score"]);
  const supplierCount = numericMetric(evidence, ["supplier_count", "qualified_supplier_count", "quote_count", "comparable_quote_count"]);
  const supplierScore = supplierDirect ?? (supplierCount === null ? scoreEvidenceCount(supplyRows, ["supplier_quote", "internal_odoo"]) : Math.min(90, 45 + Math.min(5, supplierCount) * 8));
  assign("supplierCoverage", supplierScore, supplierDirect !== null
    ? "采用证据中的结构化供应覆盖评分。"
    : supplierCount !== null ? `根据 ${supplierCount} 家已记录供应商或报价生成建议。` : supplyRows.length ? `根据 ${supplyRows.length} 条供应与报价证据生成建议。` : "");

  const economicsDirect = metricValue(evidence, ["unit_economics_score", "profitability_score"]);
  const margin = numericMetric(evidence, ["gross_margin_pct", "margin_pct", "landed_margin_pct", "gross_margin"]);
  const marginScore = margin === null ? null : margin >= 30 ? 85 : margin >= 20 ? 70 : margin >= 10 ? 50 : 25;
  assign("unitEconomics", economicsDirect ?? marginScore, economicsDirect !== null
    ? "采用证据中的结构化单位经济评分。"
    : margin !== null ? `根据已记录毛利率 ${margin}% 生成建议；仍需确认费用和账期。` : "");

  const complianceRows = evidence.filter((item) => evidenceType(item) === "compliance");
  const complianceDirect = metricValue(evidence, ["compliance_readiness_score", "compliance_score", "logistics_score"]);
  assign("complianceReadiness", complianceDirect ?? scoreEvidenceCount(complianceRows, ["official", "internal_odoo"]), complianceDirect !== null
    ? "采用证据中的结构化合规物流评分。"
    : complianceRows.length ? `根据 ${complianceRows.length} 条合规与物流证据生成建议；证书真伪仍需人工核实。` : "");

  const automatedFields = OPPORTUNITY_SIGNAL_FIELDS.filter((field) => signals[field] !== null);
  const humanRequiredFields = OPPORTUNITY_SIGNAL_FIELDS.filter((field) => signals[field] === null);
  return {
    signals,
    reasons,
    automatedFields,
    humanRequiredFields,
    summary: `本地证据可预填 ${automatedFields.length} 项；${humanRequiredFields.length} 项因缺少真实买家、报价、利润或合规证据保持未知。`,
  };
}
