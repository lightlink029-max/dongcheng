type FilterableResearchCandidate = {
  name: string;
  track_category: string;
  subcategory: string;
  product_family?: string;
  commercial_variant: string;
  target_markets: string[];
  buyer_types: string[];
  price_band: string;
  moq: string;
  compliance: string[];
  risk_level: string;
  stage: string;
};

export type ResearchCandidateFilters = {
  search: string;
  buyerTypes: string[];
  conditions: string;
  tracks: string[];
  markets: string[];
  risks: string[];
  stages: string[];
};

function normalized(value: unknown) {
  return String(value ?? "").trim().toLocaleLowerCase();
}

export function matchesResearchCandidateFilters(candidate: FilterableResearchCandidate, filters: ResearchCandidateFilters) {
  const productQuery = normalized(filters.search);
  const conditionQuery = normalized(filters.conditions);
  const productText = [candidate.name, candidate.track_category, candidate.subcategory, candidate.product_family, candidate.commercial_variant]
    .join(" ")
    .toLocaleLowerCase();
  const conditionText = [
    candidate.price_band ? `价格 ${candidate.price_band}` : "",
    candidate.moq ? `MOQ ${candidate.moq}` : "",
    ...candidate.compliance,
  ]
    .join(" ")
    .toLocaleLowerCase();

  return (!productQuery || productText.includes(productQuery))
    && (!filters.buyerTypes.length || candidate.buyer_types.some((buyer) => filters.buyerTypes.includes(buyer)))
    && (!conditionQuery || conditionText.includes(conditionQuery))
    && (!filters.tracks.length || filters.tracks.includes(candidate.track_category))
    && (!filters.markets.length || candidate.target_markets.some((market) => filters.markets.includes(market)))
    && (!filters.risks.length || filters.risks.includes(candidate.risk_level))
    && (!filters.stages.length || (filters.stages.includes("active") ? candidate.stage !== "rejected" : filters.stages.includes(candidate.stage)));
}
