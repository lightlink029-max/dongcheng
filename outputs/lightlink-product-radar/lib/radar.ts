export const SCORE_VERSION = "1.2";

export const CORE_PLATFORMS = [
  "TikTok",
  "Meta Ads",
  "Instagram",
  "Google Trends",
  "Alibaba.com",
] as const;

export const COMMERCE_PLATFORMS = [
  "Amazon",
  "Temu",
  "SHEIN",
  "eBay",
  "Walmart",
  "Etsy",
  "AliExpress",
  "Shopee",
  "Lazada",
  "Mercado Libre",
  "Rakuten",
] as const;

export const VALID_PLATFORMS = [...CORE_PLATFORMS, ...COMMERCE_PLATFORMS] as const;

export type ObservationStatus =
  | "ok"
  | "confirmed_zero"
  | "unsupported"
  | "auth_failed"
  | "rate_limited"
  | "collection_error"
  | "geo_unavailable";

export type SourceKind =
  | "official_api"
  | "official_export"
  | "browser_sample"
  | "open_source"
  | "manual_import"
  | "assistant"
  | "demo";

export type MetricKind = "attention" | "commercial" | "competition";

export type IncomingObservation = {
  keyword: string;
  groupName?: string;
  aliases?: string[];
  category?: string;
  platform: string;
  metric: MetricKind;
  currentValue?: number | null;
  previousValue?: number | null;
  sampleN?: number | null;
  uniqueActorN?: number | null;
  coverageDays: number;
  sourceKind: SourceKind;
  sourceRef?: string;
  geoScope: string;
  status: ObservationStatus;
  missingReason?: string | null;
  collectedAt: string;
  raw?: Record<string, unknown>;
};

export type ComputedScore = {
  canonicalKeyword: string;
  attentionLevel: number | null;
  momentum: number | null;
  commercialValidation: number | null;
  buyerIntent: number;
  competition: number | null;
  heat: number | null;
  opportunity: number | null;
  confidence: number;
  conservativeOpportunity: number | null;
  lifecycle: string;
  rationale: string;
  anomalyFlags: string[];
};

const BUYER_TERMS = [
  "wholesale",
  "supplier",
  "manufacturer",
  "factory",
  "oem",
  "odm",
  "bulk",
  "commercial",
  "industrial",
  "project",
  "distributor",
  "importer",
  "采购",
  "批发",
  "供应商",
  "厂家",
  "工程",
  "经销商",
  "mayorista",
  "proveedor",
  "fabricante",
  "grossiste",
  "fournisseur",
  "fabricant",
  "großhandel",
  "lieferant",
  "hersteller",
  "atacado",
  "fornecedor",
  "جملة",
  "مورد",
  "مصنع",
  "оптом",
  "поставщик",
  "производитель",
  "卸売",
  "メーカー",
  "도매",
  "제조업체",
];

const RETAIL_TERMS = ["cheap", "near me", "amazon", "personal", "home decor", "便宜", "家用", "附近"];

const B2B_KEYWORD_MODIFIERS: Record<string, { prefix?: string[]; suffix: string[] }> = {
  en: { prefix: ["commercial"], suffix: ["wholesale", "supplier", "manufacturer", "oem"] },
  zh: { suffix: ["批发", "供应商", "生产厂家", "工程", "OEM"] },
  es: { suffix: ["mayorista", "proveedor", "fabricante", "comercial", "OEM"] },
  pt: { suffix: ["atacado", "fornecedor", "fabricante", "comercial", "OEM"] },
  fr: { suffix: ["grossiste", "fournisseur", "fabricant", "professionnel", "OEM"] },
  de: { suffix: ["Großhandel", "Lieferant", "Hersteller", "gewerblich", "OEM"] },
  ar: { suffix: ["جملة", "مورد", "مصنع", "تجاري", "OEM"] },
  ru: { suffix: ["оптом", "поставщик", "производитель", "коммерческий", "OEM"] },
  ja: { suffix: ["卸売", "サプライヤー", "メーカー", "業務用", "OEM"] },
  ko: { suffix: ["도매", "공급업체", "제조업체", "상업용", "OEM"] },
};

const RELIABILITY: Record<SourceKind, number> = {
  official_api: 1,
  official_export: 0.95,
  browser_sample: 0.72,
  open_source: 0.62,
  manual_import: 0.78,
  assistant: 0.68,
  demo: 0.25,
};

export function normalizeKeyword(input: string) {
  return input
    .normalize("NFKC")
    .trim()
    .toLocaleLowerCase("en-US")
    .replace(/^#+/, "")
    .replace(/[‐‑‒–—_-]+/g, " ")
    .replace(/[“”‘’'"`]+/g, "")
    .replace(/\s+/g, " ");
}

export function splitKeywords(input: string) {
  const seen = new Set<string>();
  return input
    .split(/[\n,;，；]+/)
    .map(normalizeKeyword)
    .filter((keyword) => keyword.length > 1 && !seen.has(keyword) && seen.add(keyword))
    .slice(0, 100);
}

export function expandSeedKeyword(keyword: string, language = "en") {
  const normalized = normalizeKeyword(keyword);
  const modifiers = B2B_KEYWORD_MODIFIERS[language.toLowerCase()] ?? { suffix: ["OEM"] };
  const candidates = [
    normalized,
    ...(modifiers.prefix ?? []).map((modifier) => `${modifier} ${normalized}`),
    ...modifiers.suffix.map((modifier) => `${normalized} ${modifier}`),
  ];
  return [...new Set(candidates.map(normalizeKeyword))].slice(0, 6);
}

export function buyerIntentScore(keyword: string, aliases: string[] = []) {
  const haystack = normalizeKeyword([keyword, ...aliases].join(" "));
  let score = 48;
  for (const term of BUYER_TERMS) {
    if (haystack.includes(term)) score += 9;
  }
  for (const term of RETAIL_TERMS) {
    if (haystack.includes(term)) score -= 12;
  }
  if (/\b(price|cost|quote|quotation|moq)\b/.test(haystack)) score += 8;
  return clamp(score);
}

export function percentileRanks(values: number[]) {
  if (values.length === 0) return [];
  if (values.every((value) => value === values[0])) return values.map(() => 50);

  const sorted = [...values].sort((a, b) => a - b);
  return values.map((value) => {
    const first = sorted.indexOf(value);
    const last = sorted.lastIndexOf(value);
    const averageIndex = (first + last) / 2;
    return (averageIndex / (sorted.length - 1)) * 100;
  });
}

function clamp(value: number) {
  return Math.max(0, Math.min(100, value));
}

function round(value: number | null) {
  return value === null ? null : Math.round(value * 10) / 10;
}

function average(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function weightedAverage(parts: Array<[number | null, number]>) {
  const valid = parts.filter((part): part is [number, number] => part[0] !== null);
  if (!valid.length) return null;
  const weight = valid.reduce((sum, part) => sum + part[1], 0);
  return valid.reduce((sum, part) => sum + part[0] * part[1], 0) / weight;
}

function freshnessScore(timestamp: string, evaluationTime: number) {
  const ageHours = Math.max(0, (evaluationTime - new Date(timestamp).getTime()) / 3_600_000);
  if (ageHours <= 24) return 1;
  if (ageHours <= 72) return 0.8;
  if (ageHours <= 168) return 0.55;
  return 0.25;
}

export function computeScores(rows: IncomingObservation[]): ComputedScore[] {
  const canonicalRows = rows.map((row) => ({ ...row, canonicalKeyword: normalizeKeyword(row.keyword) }));
  const evaluationTime = Math.max(
    0,
    ...canonicalRows
      .map((row) => new Date(row.collectedAt).getTime())
      .filter((value) => Number.isFinite(value)),
  );
  const scored = new Map<IncomingObservation & { canonicalKeyword: string }, { level: number; momentum: number | null }>();
  const buckets = new Map<string, Array<IncomingObservation & { canonicalKeyword: string }>>();

  for (const row of canonicalRows) {
    if (!["ok", "confirmed_zero"].includes(row.status) || row.currentValue == null) continue;
    const key = `${row.platform}\u0000${row.metric}`;
    const bucket = buckets.get(key) ?? [];
    bucket.push(row);
    buckets.set(key, bucket);
  }

  for (const bucket of buckets.values()) {
    const levels = percentileRanks(bucket.map((row) => Math.log1p(Math.max(0, row.currentValue ?? 0))));
    const growthValues = bucket.map((row) => {
      if (row.previousValue == null) return null;
      return Math.log((Math.max(0, row.currentValue ?? 0) + 1) / (Math.max(0, row.previousValue) + 1));
    });
    bucket.forEach((row, index) => {
      const growth = growthValues[index];
      const momentum = growth === null ? null : clamp(50 + 50 * Math.tanh(growth));
      scored.set(row, { level: levels[index], momentum });
    });
  }

  const grouped = new Map<string, Array<IncomingObservation & { canonicalKeyword: string }>>();
  for (const row of canonicalRows) {
    const bucket = grouped.get(row.canonicalKeyword) ?? [];
    bucket.push(row);
    grouped.set(row.canonicalKeyword, bucket);
  }

  return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([canonicalKeyword, clusterRows]) => {
    const validRows = clusterRows.filter((row) => scored.has(row));
    const attentionScores = validRows
      .filter((row) => row.metric === "attention")
      .map((row) => scored.get(row)!.level);
    const momentumScores = validRows
      .filter((row) => row.metric !== "competition")
      .map((row) => scored.get(row)!.momentum)
      .filter((value): value is number => value !== null);
    const commercialScores = validRows
      .filter((row) => row.metric === "commercial")
      .map((row) => scored.get(row)!.level);
    const competitionScores = validRows
      .filter((row) => row.metric === "competition")
      .map((row) => scored.get(row)!.level);

    const attentionLevel = average(attentionScores);
    const momentum = average(momentumScores);
    const commercialValidation = average(commercialScores);
    const competition = average(competitionScores);
    const aliases = clusterRows.flatMap((row) => row.aliases ?? []);
    const buyerIntent = buyerIntentScore(canonicalKeyword, aliases);
    const heat = weightedAverage([
      [attentionLevel, 0.6],
      [momentum, 0.4],
    ]);

    const platforms = new Set(validRows.map((row) => row.platform));
    const enoughEvidence = platforms.size >= 2 && (attentionLevel !== null || commercialValidation !== null) && competition !== null;
    const opportunity = enoughEvidence
      ? weightedAverage([
          [attentionLevel, 0.3],
          [momentum, 0.25],
          [commercialValidation, 0.15],
          [buyerIntent, 0.15],
          [competition === null ? null : 100 - competition, 0.15],
        ])
      : null;

    const sourceCoverage = Math.min(1, platforms.size / CORE_PLATFORMS.length);
    const freshness = average(validRows.map((row) => freshnessScore(row.collectedAt, evaluationTime))) ?? 0;
    const reliability = average(validRows.map((row) => RELIABILITY[row.sourceKind])) ?? 0;
    const sample = validRows.some((row) => (row.sampleN ?? 0) >= 30 || (row.uniqueActorN ?? 0) >= 10) ? 1 : 0.45;
    const platformValues = attentionScores.length ? attentionScores : commercialScores;
    const spread = platformValues.length > 1 ? Math.max(...platformValues) - Math.min(...platformValues) : 100;
    const consistency = clamp(100 - spread) / 100;
    let confidence = 100 * (0.4 * sourceCoverage + 0.2 * freshness + 0.2 * reliability + 0.1 * sample + 0.1 * consistency);

    if (!validRows.length) confidence = 0;
    if (platforms.size <= 1) confidence = Math.min(confidence, 55);
    if (validRows.length && validRows.every((row) => row.sourceKind === "demo")) confidence = Math.min(confidence, 40);
    if (validRows.length && validRows.every((row) => row.sourceKind === "assistant")) confidence = Math.min(confidence, 70);
    if (validRows.length && validRows.every((row) => !["official_api", "official_export"].includes(row.sourceKind))) confidence = Math.min(confidence, 80);
    const anomalyFlags: string[] = [];
    if (spread > 65) anomalyFlags.push("platform_divergence");
    if (clusterRows.some((row) => row.status !== "ok" && row.status !== "confirmed_zero")) anomalyFlags.push("partial_source_failure");
    if (validRows.some((row) => row.uniqueActorN != null && row.sampleN != null && row.sampleN > 0 && row.uniqueActorN / row.sampleN < 0.2)) anomalyFlags.push("actor_concentration");
    if (anomalyFlags.length) confidence = Math.min(confidence, 65);

    const conservativeOpportunity = opportunity === null ? null : 50 + (opportunity - 50) * (confidence / 100);
    const lifecycle =
      (momentum ?? 0) >= 75 && (attentionLevel ?? 0) < 75
        ? "新兴"
        : (attentionLevel ?? 0) >= 75 && (momentum ?? 0) >= 55
          ? "热门"
          : (attentionLevel ?? 0) >= 70
            ? "成熟"
            : (momentum ?? 50) < 35
              ? "衰退"
              : "观察";

    const rationale = opportunity === null
      ? "来源覆盖不足，当前只作为探索候选；补充至少两个平台和供应竞争证据后再判断。"
      : `${lifecycle}阶段；${buyerIntent >= 75 ? "采购意图明确" : "采购意图一般"}，${(competition ?? 50) >= 70 ? "供应竞争偏高" : "供应竞争仍有空间"}。`;

    return {
      canonicalKeyword,
      attentionLevel: round(attentionLevel),
      momentum: round(momentum),
      commercialValidation: round(commercialValidation),
      buyerIntent: round(buyerIntent)!,
      competition: round(competition),
      heat: round(heat),
      opportunity: round(opportunity),
      confidence: round(clamp(confidence))!,
      conservativeOpportunity: round(conservativeOpportunity),
      lifecycle,
      rationale,
      anomalyFlags,
    };
  });
}

export function safeCsvCell(value: unknown) {
  let text = value == null ? "" : String(value);
  if (/^[\u0000-\u0020]*[=+\-@]/.test(text)) text = `'${text}`;
  if (/[",\n\r]/.test(text)) text = `"${text.replaceAll('"', '""')}"`;
  return text;
}
