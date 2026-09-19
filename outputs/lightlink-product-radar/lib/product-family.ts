export type FamilyCandidate = {
  id: string;
  name: string;
  track_category: string;
  subcategory: string;
  product_family?: string;
  buyer_types: string[];
  target_markets: string[];
  evidence_status: string;
  selection_assessment?: unknown;
};

function selectionTotal(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return 0;
  const scorecard = (value as { scorecard?: unknown }).scorecard;
  if (!scorecard || typeof scorecard !== "object" || Array.isArray(scorecard)) return 0;
  return Object.values(scorecard).reduce<number>((sum, score) => {
    const parsed = Number(score);
    return sum + (Number.isFinite(parsed) ? Math.max(0, parsed) : 0);
  }, 0);
}

export type ProductFamilySummary = {
  key: string;
  name: string;
  track: string;
  subcategory: string;
  candidateCount: number;
  buyerTypes: string[];
  markets: string[];
  candidateIds: string[];
};

export type BuyerFamilyOpportunity = {
  buyerType: string;
  relationshipScore: number;
  familyCount: number;
  trackCount: number;
  candidateCount: number;
  families: Array<{ name: string; track: string; candidateCount: number }>;
  markets: string[];
};

function familyName(candidate: FamilyCandidate) {
  return String(candidate.product_family || candidate.subcategory || candidate.name || "未归组").trim();
}

export function buildProductFamilySummaries(candidates: FamilyCandidate[]): ProductFamilySummary[] {
  const grouped = new Map<string, ProductFamilySummary>();
  for (const candidate of candidates) {
    const name = familyName(candidate);
    const track = String(candidate.track_category || "未分类").trim();
    const subcategory = String(candidate.subcategory || "未细分").trim();
    const key = `${track}|${subcategory}|${name}`.toLocaleLowerCase();
    const current = grouped.get(key) ?? { key, name, track, subcategory, candidateCount: 0, buyerTypes: [], markets: [], candidateIds: [] };
    current.candidateCount += 1;
    current.candidateIds.push(candidate.id);
    current.buyerTypes = [...new Set([...current.buyerTypes, ...candidate.buyer_types])];
    current.markets = [...new Set([...current.markets, ...candidate.target_markets])];
    grouped.set(key, current);
  }
  return [...grouped.values()].sort((a, b) => b.candidateCount - a.candidateCount || a.name.localeCompare(b.name, "zh-CN"));
}

export function buildBuyerFamilyOpportunities(candidates: FamilyCandidate[]): BuyerFamilyOpportunity[] {
  const buyers = new Map<string, FamilyCandidate[]>();
  for (const candidate of candidates) {
    for (const buyerType of candidate.buyer_types) {
      const key = buyerType.trim();
      if (key) buyers.set(key, [...(buyers.get(key) ?? []), candidate]);
    }
  }
  return [...buyers.entries()].map(([buyerType, related]) => {
    const families = buildProductFamilySummaries(related);
    const tracks = new Set(families.map((family) => family.track));
    const markets = [...new Set(related.flatMap((candidate) => candidate.target_markets))];
    const evidencePoints = related.reduce((sum, candidate) => sum + (candidate.evidence_status === "validated" ? 1 : candidate.evidence_status === "partial" ? 0.5 : 0), 0);
    const selectionAverage = related.length
      ? related.reduce((sum, candidate) => sum + selectionTotal(candidate.selection_assessment), 0) / related.length
      : 0;
    const relationshipScore = Math.min(100, Math.round(
      40
      + Math.min(15, related.length * 3)
      + (evidencePoints / Math.max(1, related.length)) * 20
      + selectionAverage * 0.15
      + Math.min(10, markets.length * 2),
    ));
    return {
      buyerType,
      relationshipScore,
      familyCount: families.length,
      trackCount: tracks.size,
      candidateCount: related.length,
      families: families.map((family) => ({ name: family.name, track: family.track, candidateCount: family.candidateCount })),
      markets,
    };
  }).sort((a, b) => b.relationshipScore - a.relationshipScore || b.familyCount - a.familyCount || a.buyerType.localeCompare(b.buyerType, "zh-CN"));
}
