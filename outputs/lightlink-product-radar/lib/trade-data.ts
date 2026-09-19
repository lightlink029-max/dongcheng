export const TRADE_DATA_STATUSES = ["available", "missing", "blocked"] as const;
export const TRADE_DATA_FLOWS = ["import", "export"] as const;
export const TRADE_DATA_FREQUENCIES = ["annual", "monthly", "quarterly"] as const;
export const TRADE_DATA_SOURCE_GRADES = ["official", "official_export", "ai_verified"] as const;
export const TRADE_COLLECTION_LEVELS = ["baseline", "trend", "detail"] as const;

export type TradeDataStatus = typeof TRADE_DATA_STATUSES[number];
export type TradeDataFlow = typeof TRADE_DATA_FLOWS[number];
export type TradeDataFrequency = typeof TRADE_DATA_FREQUENCIES[number];
export type TradeDataSourceGrade = typeof TRADE_DATA_SOURCE_GRADES[number];
export type TradeCollectionLevel = typeof TRADE_COLLECTION_LEVELS[number];

export type ComparableTradeObservation = {
  reporterCode?: unknown;
  reporter_code?: unknown;
  partnerCode?: unknown;
  partner_code?: unknown;
  classification?: unknown;
  commodityCode?: unknown;
  commodity_code?: unknown;
  flow?: unknown;
  period?: unknown;
  frequency?: unknown;
  metric?: unknown;
};

export type TradeObservationPoint<T> = {
  key: string;
  rows: T[];
};

export const TRADE_COLLECTION_POLICIES: Record<TradeCollectionLevel, {
  label: string;
  description: string;
  prompt: string;
}> = {
  baseline: {
    label: "5年年度基线",
    description: "商机建立后采集最近5个完整年度、全球伙伴口径的进出口汇总。",
    prompt: "仅采集最近5个完整年度；partnerCode 使用 WORLD；优先进口并在可靠时补出口；每个可信 HS 编码分别记录。",
  },
  trend: {
    label: "24–36个月趋势",
    description: "重点验证阶段补最近24–36个月月度序列，用于同比、环比和季节性判断。",
    prompt: "保留年度基线，并补最近24–36个月的月度序列；partnerCode 使用 WORLD；不要用年度值伪造月度值。",
  },
  detail: {
    label: "HS6与伙伴明细",
    description: "商机成立或进入试单后补目标国家、主要贸易伙伴及可靠的HS6明细。",
    prompt: "保留年度和月度数据，并补可靠的 HS6 编码、主要贸易伙伴及目标国家明细；无法可靠细分时必须标记 missing 或 blocked。",
  },
};

export function normalizeTradeCollectionLevel(value: unknown): TradeCollectionLevel {
  const level = String(value ?? "");
  return (TRADE_COLLECTION_LEVELS as readonly string[]).includes(level) ? level as TradeCollectionLevel : "baseline";
}

export function tradeCollectionLevelForOpportunityStatus(status: unknown): TradeCollectionLevel {
  const normalized = String(status ?? "");
  if (["qualified", "pilot"].includes(normalized)) return "detail";
  if (normalized === "validating") return "trend";
  return "baseline";
}

type CoverageObservation = {
  period?: unknown;
  frequency?: unknown;
  commodityCode?: unknown;
  commodity_code?: unknown;
  partnerCode?: unknown;
  partner_code?: unknown;
  status?: unknown;
  data_status?: unknown;
  collectedAt?: unknown;
  collected_at?: unknown;
};

export type TradeCoverageLevel = "none" | TradeCollectionLevel;

export function tradeCoverageLevel(rows: CoverageObservation[], now = Date.now()): TradeCoverageLevel {
  const available = rows.filter((row) => {
    const status = String(row.status ?? row.data_status ?? "available");
    const collectedAt = String(row.collectedAt ?? row.collected_at ?? "");
    return status === "available" && isTradeCacheFresh(collectedAt, now);
  });
  if (!available.length) return "none";
  const annualPeriods = new Set(available
    .filter((row) => String(row.frequency) === "annual" || /^\d{4}$/.test(String(row.period ?? "")))
    .map((row) => String(row.period)));
  const monthlyPeriods = new Set(available
    .filter((row) => String(row.frequency) === "monthly" || /^\d{4}-(?:0[1-9]|1[0-2])$/.test(String(row.period ?? "")))
    .map((row) => String(row.period)));
  const hasPartnerHs6 = available.some((row) => {
    const commodityCode = String(row.commodityCode ?? row.commodity_code ?? "").replace(/\D/g, "");
    const partnerCode = String(row.partnerCode ?? row.partner_code ?? "WORLD").toUpperCase();
    return commodityCode.length >= 6 && !["", "0", "WORLD", "WLD"].includes(partnerCode);
  });
  if (hasPartnerHs6) return "detail";
  if (monthlyPeriods.size >= 24) return "trend";
  if (annualPeriods.size >= 3 || monthlyPeriods.size >= 12) return "baseline";
  return "none";
}

export function tradeCoverageSatisfies(actual: TradeCoverageLevel, required: TradeCollectionLevel) {
  const rank: Record<TradeCoverageLevel, number> = { none: 0, baseline: 1, trend: 2, detail: 3 };
  return rank[actual] >= rank[required];
}

export function tradeMetricFamily(metric: unknown) {
  const normalized = String(metric ?? "").trim().toLocaleLowerCase();
  return /^trade_value_(?:usd|eur|gbp|cny|jpy)$/.test(normalized) ? "trade_value" : normalized;
}

export function tradeObservationPointKey(row: ComparableTradeObservation) {
  return [
    row.reporterCode ?? row.reporter_code,
    row.partnerCode ?? row.partner_code ?? "WORLD",
    row.classification ?? "HS",
    row.commodityCode ?? row.commodity_code,
    row.flow,
    row.period,
    row.frequency,
    tradeMetricFamily(row.metric),
  ].map((value) => String(value ?? "").trim().toLocaleLowerCase()).join("|");
}

export function groupTradeObservationPoints<T extends ComparableTradeObservation>(rows: T[]): TradeObservationPoint<T>[] {
  const groups = new Map<string, T[]>();
  for (const row of rows) {
    const key = tradeObservationPointKey(row);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return [...groups.entries()].map(([key, groupedRows]) => ({ key, rows: groupedRows }));
}

export type NormalizedTradeObservation = {
  reporterCode: string;
  partnerCode: string;
  classification: string;
  commodityCode: string;
  commodityLabel: string;
  flow: TradeDataFlow;
  period: string;
  frequency: TradeDataFrequency;
  metric: string;
  value: number | null;
  unit: string;
  sourceName: string;
  sourceUrl: string;
  sourceGrade: TradeDataSourceGrade;
  status: TradeDataStatus;
  missingReason: string;
  collectedAt: string;
};

function cleanText(value: unknown, max: number) {
  return String(value ?? "").trim().slice(0, max);
}

function oneOf<T extends readonly string[]>(value: unknown, options: T, fallback: T[number]) {
  const text = String(value ?? "");
  return (options as readonly string[]).includes(text) ? text as T[number] : fallback;
}

function validHttpUrl(value: unknown) {
  const text = cleanText(value, 1200);
  try {
    const parsed = new URL(text);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.toString() : "";
  } catch {
    return "";
  }
}

export function normalizeTradeObservation(input: Record<string, unknown>): NormalizedTradeObservation {
  const status = oneOf(input.status, TRADE_DATA_STATUSES, "available");
  const rawValue = input.value === null || input.value === "" || input.value === undefined ? null : Number(input.value);
  const value = rawValue !== null && Number.isFinite(rawValue) ? rawValue : null;
  const period = cleanText(input.period, 20);
  const sourceUrl = validHttpUrl(input.sourceUrl);
  if (!/^\d{4}(?:-(?:0[1-9]|1[0-2])|-[Qq][1-4])?$/.test(period)) throw new Error("贸易数据周期必须为 YYYY、YYYY-MM 或 YYYY-Q1 格式");
  if (!sourceUrl) throw new Error("贸易数据必须保留可核验的 http/https 官方来源");
  if (status === "available" && value === null) throw new Error("可用贸易数据必须提供数值；缺失值请标记 missing");
  if (status !== "available" && value !== null) throw new Error("缺失或受阻数据不能同时提供数值");
  const normalized = {
    reporterCode: cleanText(input.reporterCode, 20).toUpperCase(),
    partnerCode: cleanText(input.partnerCode || "WORLD", 20).toUpperCase(),
    classification: cleanText(input.classification || "HS", 30).toUpperCase(),
    commodityCode: cleanText(input.commodityCode, 20),
    commodityLabel: cleanText(input.commodityLabel, 240),
    flow: oneOf(input.flow, TRADE_DATA_FLOWS, "import"),
    period,
    frequency: oneOf(input.frequency, TRADE_DATA_FREQUENCIES, period.length === 7 ? "monthly" : "annual"),
    metric: cleanText(input.metric || "trade_value_usd", 60),
    value,
    unit: cleanText(input.unit || "USD", 40),
    sourceName: cleanText(input.sourceName, 120),
    sourceUrl,
    sourceGrade: oneOf(input.sourceGrade, TRADE_DATA_SOURCE_GRADES, "ai_verified"),
    status,
    missingReason: cleanText(input.missingReason, 500),
    collectedAt: cleanText(input.collectedAt, 40) || new Date().toISOString(),
  } satisfies NormalizedTradeObservation;
  if (!normalized.reporterCode || !normalized.commodityCode || !normalized.commodityLabel || !normalized.sourceName) {
    throw new Error("贸易数据缺少报告国、商品编码、商品名称或来源名称");
  }
  if (status !== "available" && !normalized.missingReason) throw new Error("缺失或受阻数据必须说明原因");
  return normalized;
}

export function isTradeCacheFresh(collectedAt: string | null | undefined, now = Date.now(), maxAgeDays = 120) {
  const parsed = Date.parse(String(collectedAt ?? ""));
  return Number.isFinite(parsed) && now - parsed <= maxAgeDays * 86_400_000;
}
