export type OfficialTradeConnectorId = "un_comtrade" | "eurostat_comext" | "uk_hmrc";

export type ConnectorErrorCategory =
  | "permission"
  | "rate_limit"
  | "network"
  | "remote_service"
  | "source_schema"
  | "invalid_scope"
  | "no_data"
  | "unknown";

export type ConnectorRunStatus = "completed" | "no_data" | "failed" | "not_applicable";

export type OfficialTradeObservation = {
  sourceId: OfficialTradeConnectorId;
  sourceName: string;
  sourceUrl: string;
  reporterCode: string;
  commodityCode: string;
  period: string;
  metric: string;
  value: number;
  unit: string;
  flow: "import";
  title: string;
  summary: string;
  externalId: string;
  raw: Record<string, unknown>;
};

export type OfficialTradeConnectorResult = {
  sourceId: OfficialTradeConnectorId;
  sourceName: string;
  status: ConnectorRunStatus;
  errorCategory: ConnectorErrorCategory | "";
  errorMessage: string;
  coverageCountries: string[];
  resultCount: number;
  durationMs: number;
  retryCount: number;
  quotaSummary: string;
  updateFrequency: string;
  observations: OfficialTradeObservation[];
};

export type OfficialTradeCollectionContext = {
  regionCode: string;
  countryCodes: string[];
  commodityCodes: string[];
  sourceIds?: string[];
  now?: Date;
  fetchImpl?: typeof fetch;
  unComtradeApiKey?: string;
};

type JsonRecord = Record<string, unknown>;

type ConnectorDefinition = {
  id: OfficialTradeConnectorId;
  name: string;
  quotaSummary: string;
  updateFrequency: string;
  collect(context: Required<Pick<OfficialTradeCollectionContext, "regionCode" | "countryCodes" | "commodityCodes">> & {
    now: Date;
    fetchImpl: typeof fetch;
    unComtradeApiKey: string;
  }): Promise<{ observations: OfficialTradeObservation[]; coverageCountries: string[]; retryCount: number }>;
};

class ConnectorRequestError extends Error {
  category: ConnectorErrorCategory;

  constructor(category: ConnectorErrorCategory, message: string) {
    super(message);
    this.name = "ConnectorRequestError";
    this.category = category;
  }
}

const ISO2_TO_M49: Record<string, string> = {
  AT: "40", BE: "56", CA: "124", CH: "756", CN: "156", CZ: "203", DE: "276", DK: "208",
  EG: "818", ES: "724", FI: "246", FR: "250", GB: "826", GR: "300", IL: "376", IN: "356",
  IT: "380", JP: "392", KR: "410", MX: "484", NL: "528", NO: "578", PL: "616", PT: "620",
  RO: "642", RU: "643", SA: "682", SE: "752", SG: "702", TR: "792", UA: "804", US: "842",
};

const EUROSTAT_REPORTERS = new Set([
  "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
  "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK",
]);

const OFFICIAL_CONNECTOR_IDS = new Set<OfficialTradeConnectorId>(["un_comtrade", "eurostat_comext", "uk_hmrc"]);

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function rows(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter((item): item is JsonRecord => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
}

function numeric(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function cleanCountryCodes(values: string[]) {
  return [...new Set(values.map((value) => value.trim().toUpperCase()).filter((value) => /^[A-Z]{2}$/.test(value)))];
}

export function normalizeCommodityCodes(values: string[]) {
  return [...new Set(values
    .map((value) => value.replace(/\D/g, ""))
    .filter((value) => [2, 4, 6, 8].includes(value.length)))]
    .slice(0, 12);
}

function previousCompleteMonth(now: Date) {
  const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  date.setUTCMonth(date.getUTCMonth() - 1);
  return date;
}

function monthCode(date: Date) {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function compactMonthCode(date: Date) {
  return `${date.getUTCFullYear()}${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function retryable(category: ConnectorErrorCategory) {
  return ["network", "rate_limit", "remote_service"].includes(category);
}

function httpCategory(status: number, body: string): ConnectorErrorCategory {
  const lower = body.toLowerCase();
  if (status === 401 || status === 403) return "permission";
  if (status === 429) return "rate_limit";
  if ((status === 400 || status === 404) && (lower.includes("no result") || lower.includes("no data"))) return "no_data";
  if (status >= 500 || status === 408) return "remote_service";
  if (status >= 400 && status < 500) return "source_schema";
  return "unknown";
}

async function requestJson(
  url: string,
  fetchImpl: typeof fetch,
  headers: Record<string, string> = {},
) {
  let retryCount = 0;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20_000);
    try {
      const response = await fetchImpl(url, { headers: { accept: "application/json", ...headers }, signal: controller.signal });
      const body = await response.text();
      if (!response.ok) {
        const category = httpCategory(response.status, body);
        if (attempt === 0 && retryable(category)) {
          retryCount += 1;
          await new Promise((resolve) => setTimeout(resolve, 250));
          continue;
        }
        throw new ConnectorRequestError(category, `HTTP ${response.status}${body ? `：${body.slice(0, 220)}` : ""}`);
      }
      try {
        return { payload: JSON.parse(body) as unknown, retryCount };
      } catch {
        throw new ConnectorRequestError("source_schema", "来源返回的内容不是有效 JSON");
      }
    } catch (error) {
      const normalized = error instanceof ConnectorRequestError
        ? error
        : new ConnectorRequestError("network", error instanceof Error && error.name === "AbortError" ? "请求超时" : "网络请求失败");
      if (attempt === 0 && retryable(normalized.category)) {
        retryCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 250));
        continue;
      }
      throw normalized;
    } finally {
      clearTimeout(timeout);
    }
  }
  throw new ConnectorRequestError("unknown", "来源请求失败");
}

function unComtradeObservation(row: JsonRecord, sourceUrl: string): OfficialTradeObservation[] {
  const reporterCode = String(row.reporterISO || row.reporterCode || "");
  const commodityCode = String(row.cmdCode || "");
  const period = String(row.period || row.refYear || "");
  const primaryValue = numeric(row.primaryValue);
  if (!reporterCode || !commodityCode || !period || primaryValue === null) return [];
  const observations: OfficialTradeObservation[] = [{
    sourceId: "un_comtrade",
    sourceName: "UN Comtrade",
    sourceUrl,
    reporterCode,
    commodityCode,
    period,
    metric: "import_value",
    value: primaryValue,
    unit: "USD",
    flow: "import",
    title: `UN Comtrade · ${reporterCode} · HS ${commodityCode} · ${period}`,
    summary: "官方年度进口额；伙伴为世界合计，公开预览接口可能受记录和配额限制。",
    externalId: `un:${reporterCode}:${commodityCode}:${period}:import_value`,
    raw: row,
  }];
  const netWeight = numeric(row.netWgt);
  if (netWeight !== null) observations.push({
    ...observations[0],
    metric: "net_weight",
    value: netWeight,
    unit: "kg",
    title: `UN Comtrade · ${reporterCode} · HS ${commodityCode} · ${period} 净重`,
    externalId: `un:${reporterCode}:${commodityCode}:${period}:net_weight`,
  });
  return observations;
}

async function collectUnComtrade(context: Parameters<ConnectorDefinition["collect"]>[0]) {
  const reporterCodes = context.countryCodes.map((code) => ISO2_TO_M49[code]).filter(Boolean);
  if (!reporterCodes.length) return { observations: [], coverageCountries: [], retryCount: 0 };
  const currentYear = context.now.getUTCFullYear();
  const periods = [String(currentYear - 1), String(currentYear - 2)];
  const observations: OfficialTradeObservation[] = [];
  let retryCount = 0;
  for (const commodityCode of context.commodityCodes) {
    for (const period of periods) {
      const url = new URL("https://comtradeapi.un.org/public/v1/preview/C/A/HS");
      url.searchParams.set("reporterCode", reporterCodes.join(","));
      url.searchParams.set("period", period);
      url.searchParams.set("cmdCode", commodityCode);
      url.searchParams.set("flowCode", "M");
      url.searchParams.set("partnerCode", "0");
      url.searchParams.set("partner2Code", "0");
      url.searchParams.set("customsCode", "C00");
      url.searchParams.set("motCode", "0");
      url.searchParams.set("maxRecords", "500");
      const headers: Record<string, string> = context.unComtradeApiKey ? { "Ocp-Apim-Subscription-Key": context.unComtradeApiKey } : {};
      const response = await requestJson(url.toString(), context.fetchImpl, headers);
      retryCount += response.retryCount;
      const payload = record(response.payload);
      if (!Array.isArray(payload.data)) throw new ConnectorRequestError("source_schema", "UN Comtrade 响应缺少 data 数组");
      for (const item of rows(payload.data)) observations.push(...unComtradeObservation(item, url.toString()));
    }
  }
  return { observations, coverageCountries: context.countryCodes.filter((code) => Boolean(ISO2_TO_M49[code])), retryCount };
}

function eurostatCoordinates(flatIndex: number, sizes: number[]) {
  const coordinates = new Array<number>(sizes.length).fill(0);
  let remainder = flatIndex;
  for (let index = sizes.length - 1; index >= 0; index -= 1) {
    coordinates[index] = remainder % sizes[index];
    remainder = Math.floor(remainder / sizes[index]);
  }
  return coordinates;
}

function eurostatCodes(payload: JsonRecord, dimensionId: string) {
  const dimensions = record(payload.dimension);
  const dimension = record(dimensions[dimensionId]);
  const category = record(dimension.category);
  const index = record(category.index);
  return Object.entries(index).sort(([, left], [, right]) => Number(left) - Number(right)).map(([code]) => code);
}

function parseEurostat(payload: JsonRecord, sourceUrl: string): OfficialTradeObservation[] {
  const dimensionIds = Array.isArray(payload.id) ? payload.id.map(String) : [];
  const sizes = Array.isArray(payload.size) ? payload.size.map(Number) : [];
  const values = record(payload.value);
  if (!dimensionIds.length || dimensionIds.length !== sizes.length || !dimensionIds.includes("time") || !dimensionIds.includes("indicators")) {
    throw new ConnectorRequestError("source_schema", "Eurostat JSON-stat 维度结构无法识别");
  }
  const codeByDimension = new Map(dimensionIds.map((id) => [id, eurostatCodes(payload, id)]));
  const observations: OfficialTradeObservation[] = [];
  for (const [flatKey, rawValue] of Object.entries(values)) {
    const value = numeric(rawValue);
    if (value === null) continue;
    const coordinates = eurostatCoordinates(Number(flatKey), sizes);
    const code = (id: string) => codeByDimension.get(id)?.[coordinates[dimensionIds.indexOf(id)]] ?? "";
    const indicator = code("indicators");
    const metric = indicator === "VALUE_IN_EUROS" ? "import_value" : indicator === "QUANTITY_IN_100KG" ? "net_weight_100kg" : indicator.toLowerCase();
    const unit = indicator === "VALUE_IN_EUROS" ? "EUR" : indicator === "QUANTITY_IN_100KG" ? "100kg" : "count";
    const reporterCode = code("reporter");
    const commodityCode = code("product");
    const period = code("time");
    if (!reporterCode || !commodityCode || !period || !metric) continue;
    observations.push({
      sourceId: "eurostat_comext",
      sourceName: "Eurostat Comext",
      sourceUrl,
      reporterCode,
      commodityCode,
      period,
      metric,
      value,
      unit,
      flow: "import",
      title: `Eurostat · ${reporterCode} · HS/CN ${commodityCode} · ${period}`,
      summary: "欧盟官方月度进口数据；伙伴为世界合计。",
      externalId: `eurostat:${reporterCode}:${commodityCode}:${period}:${metric}`,
      raw: { reporterCode, commodityCode, period, indicator, value },
    });
  }
  return observations;
}

async function collectEurostat(context: Parameters<ConnectorDefinition["collect"]>[0]) {
  const reporters = context.countryCodes.filter((code) => EUROSTAT_REPORTERS.has(code));
  if (!reporters.length) return { observations: [], coverageCountries: [], retryCount: 0 };
  const end = previousCompleteMonth(context.now);
  const start = new Date(end);
  start.setUTCMonth(start.getUTCMonth() - 12);
  const observations: OfficialTradeObservation[] = [];
  let retryCount = 0;
  for (const reporter of reporters) {
    for (const commodityCode of context.commodityCodes) {
      const url = new URL("https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409");
      url.searchParams.set("format", "JSON");
      url.searchParams.set("lang", "EN");
      url.searchParams.set("freq", "M");
      url.searchParams.set("reporter", reporter);
      url.searchParams.set("partner", "WORLD");
      url.searchParams.set("flow", "1");
      url.searchParams.set("product", commodityCode);
      url.searchParams.set("sinceTimePeriod", monthCode(start));
      url.searchParams.set("untilTimePeriod", monthCode(end));
      const response = await requestJson(url.toString(), context.fetchImpl);
      retryCount += response.retryCount;
      observations.push(...parseEurostat(record(response.payload), url.toString()));
    }
  }
  return { observations, coverageCountries: reporters, retryCount };
}

function commodityRange(code: string) {
  const multiplier = 10 ** (8 - code.length);
  const lower = Number(code) * multiplier;
  return { lower, upper: lower + multiplier };
}

async function collectHmrc(context: Parameters<ConnectorDefinition["collect"]>[0]) {
  if (!context.countryCodes.includes("GB") && context.regionCode !== "GLOBAL") {
    return { observations: [], coverageCountries: [], retryCount: 0 };
  }
  const end = previousCompleteMonth(context.now);
  const start = new Date(end);
  start.setUTCMonth(start.getUTCMonth() - 12);
  const observations: OfficialTradeObservation[] = [];
  let retryCount = 0;
  for (const commodityCode of context.commodityCodes) {
    const { lower, upper } = commodityRange(commodityCode);
    const filter = `MonthId ge ${compactMonthCode(start)} and MonthId le ${compactMonthCode(end)} and CommodityId ge ${lower} and CommodityId lt ${upper} and (FlowTypeId eq 1 or FlowTypeId eq 3)`;
    const apply = `filter(${filter})/groupby((MonthId),aggregate(Value with sum as TotalValue,NetMass with sum as TotalNetMass))`;
    const url = new URL("https://api.uktradeinfo.com/OTS");
    url.searchParams.set("$apply", apply);
    const response = await requestJson(url.toString(), context.fetchImpl);
    retryCount += response.retryCount;
    const payload = record(response.payload);
    if (!Array.isArray(payload.value)) throw new ConnectorRequestError("source_schema", "HMRC 响应缺少 value 数组");
    for (const item of rows(payload.value)) {
      const periodRaw = String(item.MonthId || "");
      const period = periodRaw.length === 6 ? `${periodRaw.slice(0, 4)}-${periodRaw.slice(4)}` : periodRaw;
      const totalValue = numeric(item.TotalValue);
      if (period && totalValue !== null) observations.push({
        sourceId: "uk_hmrc",
        sourceName: "UK HMRC Trade Info",
        sourceUrl: url.toString(),
        reporterCode: "GB",
        commodityCode,
        period,
        metric: "import_value",
        value: totalValue,
        unit: "GBP",
        flow: "import",
        title: `UK HMRC · GB · HS ${commodityCode} · ${period}`,
        summary: "英国官方月度进口额；汇总欧盟与非欧盟进口流。",
        externalId: `hmrc:GB:${commodityCode}:${period}:import_value`,
        raw: item,
      });
      const netMass = numeric(item.TotalNetMass);
      if (period && netMass !== null) observations.push({
        sourceId: "uk_hmrc",
        sourceName: "UK HMRC Trade Info",
        sourceUrl: url.toString(),
        reporterCode: "GB",
        commodityCode,
        period,
        metric: "net_weight",
        value: netMass,
        unit: "kg",
        flow: "import",
        title: `UK HMRC · GB · HS ${commodityCode} · ${period} 净重`,
        summary: "英国官方月度进口净重；汇总欧盟与非欧盟进口流。",
        externalId: `hmrc:GB:${commodityCode}:${period}:net_weight`,
        raw: item,
      });
    }
  }
  return { observations, coverageCountries: ["GB"], retryCount };
}

const CONNECTORS: ConnectorDefinition[] = [
  { id: "un_comtrade", name: "UN Comtrade", quotaSummary: "公开预览接口；批量配额取决于订阅", updateFrequency: "年度/月度，按报告国发布", collect: collectUnComtrade },
  { id: "eurostat_comext", name: "Eurostat Comext", quotaSummary: "官方公开 REST API，无需密钥", updateFrequency: "月度；数据服务每日更新", collect: collectEurostat },
  { id: "uk_hmrc", name: "UK HMRC Trade Info", quotaSummary: "60 次请求/分钟", updateFrequency: "月度", collect: collectHmrc },
];

export async function collectOfficialTradeSignals(context: OfficialTradeCollectionContext) {
  const now = context.now && !Number.isNaN(context.now.getTime()) ? context.now : new Date();
  const fetchImpl = context.fetchImpl ?? fetch;
  const countryCodes = cleanCountryCodes(context.countryCodes);
  const commodityCodes = normalizeCommodityCodes(context.commodityCodes);
  const requested = context.sourceIds?.length
    ? new Set(context.sourceIds.filter((id): id is OfficialTradeConnectorId => OFFICIAL_CONNECTOR_IDS.has(id as OfficialTradeConnectorId)))
    : new Set(CONNECTORS.map((connector) => connector.id));
  const selected = CONNECTORS.filter((connector) => requested.has(connector.id));
  if (!selected.length) return [];
  if (!commodityCodes.length) return selected.map((connector): OfficialTradeConnectorResult => ({
    sourceId: connector.id,
    sourceName: connector.name,
    status: "failed",
    errorCategory: "invalid_scope",
    errorMessage: "尚未确认 HS/CN 编码，不能执行官方贸易查询",
    coverageCountries: [],
    resultCount: 0,
    durationMs: 0,
    retryCount: 0,
    quotaSummary: connector.quotaSummary,
    updateFrequency: connector.updateFrequency,
    observations: [],
  }));

  const results: OfficialTradeConnectorResult[] = [];
  for (const connector of selected) {
    const started = Date.now();
    try {
      const collected = await connector.collect({
        regionCode: context.regionCode,
        countryCodes,
        commodityCodes,
        now,
        fetchImpl,
        unComtradeApiKey: context.unComtradeApiKey ?? "",
      });
      const notApplicable = connector.id === "uk_hmrc" && !countryCodes.includes("GB") && context.regionCode !== "GLOBAL";
      results.push({
        sourceId: connector.id,
        sourceName: connector.name,
        status: notApplicable ? "not_applicable" : collected.observations.length ? "completed" : "no_data",
        errorCategory: notApplicable ? "" : collected.observations.length ? "" : "no_data",
        errorMessage: notApplicable ? "当前监控范围不包含英国" : collected.observations.length ? "" : "来源请求成功，但当前范围没有返回数据",
        coverageCountries: collected.coverageCountries,
        resultCount: collected.observations.length,
        durationMs: Date.now() - started,
        retryCount: collected.retryCount,
        quotaSummary: connector.quotaSummary,
        updateFrequency: connector.updateFrequency,
        observations: collected.observations,
      });
    } catch (error) {
      const normalized = error instanceof ConnectorRequestError ? error : new ConnectorRequestError("unknown", error instanceof Error ? error.message : "来源执行失败");
      results.push({
        sourceId: connector.id,
        sourceName: connector.name,
        status: "failed",
        errorCategory: normalized.category,
        errorMessage: normalized.message,
        coverageCountries: [],
        resultCount: 0,
        durationMs: Date.now() - started,
        retryCount: retryable(normalized.category) ? 1 : 0,
        quotaSummary: connector.quotaSummary,
        updateFrequency: connector.updateFrequency,
        observations: [],
      });
    }
  }
  return results;
}
