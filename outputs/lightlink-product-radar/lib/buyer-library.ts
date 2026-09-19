export type BuyerLibraryProfile = {
  id: string;
  company_name: string;
  country: string;
  buyer_type: string;
  customer_groups: string[];
  sales_channels: string[];
  purchasing_scenarios: string[];
  seasonality: string;
  replenishment_cycle: string;
  order_requirements: string;
  source_url: string;
  profile_status: string;
};

export type BuyerLibraryFamilyLink = {
  buyer_profile_id: string;
  track_category: string;
  product_family: string;
  relationship_score: number;
  family_role: string;
  sales_scenarios: string[];
  rationale: string;
  evidence_status: string;
};

function searchTerms(...values: string[]) {
  return [...new Set(values
    .flatMap((value) => String(value || "").toLocaleLowerCase().split(/[\s,，、/;；|]+/))
    .map((value) => value.trim())
    .filter((value) => value.length >= 2))]
    .slice(0, 30);
}

export function buildProjectBuyerKnowledge({
  profiles,
  links,
  targetMarkets,
  productCategory,
  productDescription,
  objectives,
  limit = 24,
}: {
  profiles: BuyerLibraryProfile[];
  links: BuyerLibraryFamilyLink[];
  targetMarkets: string[];
  productCategory: string;
  productDescription: string;
  objectives: string;
  limit?: number;
}) {
  const markets = new Set(targetMarkets.map((value) => value.toUpperCase()));
  const globalScope = markets.size === 0 || markets.has("GLOBAL");
  const terms = searchTerms(productCategory, productDescription, objectives);
  const linksByBuyer = new Map<string, BuyerLibraryFamilyLink[]>();
  for (const link of links) linksByBuyer.set(link.buyer_profile_id, [...(linksByBuyer.get(link.buyer_profile_id) ?? []), link]);

  const ranked = profiles.map((profile) => {
    const profileLinks = linksByBuyer.get(profile.id) ?? [];
    const haystack = [
      profile.buyer_type,
      ...profile.customer_groups,
      ...profile.sales_channels,
      ...profile.purchasing_scenarios,
      ...profileLinks.flatMap((link) => [link.track_category, link.product_family, ...link.sales_scenarios]),
    ].join(" ").toLocaleLowerCase();
    const marketMatch = globalScope || markets.has(profile.country.toUpperCase());
    const termMatches = terms.filter((term) => haystack.includes(term)).length;
    const averageRelationship = profileLinks.length
      ? profileLinks.reduce((sum, link) => sum + Number(link.relationship_score || 0), 0) / profileLinks.length
      : 0;
    return {
      profile,
      profileLinks,
      score: (marketMatch ? 50 : 0) + Math.min(30, termMatches * 6) + averageRelationship * 0.15
        + (profile.profile_status === "validated" ? 10 : profile.profile_status === "qualified" ? 5 : 0),
      marketMatch,
      termMatches,
    };
  }).filter((item) => globalScope || item.marketMatch || item.termMatches > 0)
    .sort((a, b) => b.score - a.score || b.profileLinks.length - a.profileLinks.length || a.profile.company_name.localeCompare(b.profile.company_name))
    .slice(0, Math.max(1, Math.min(50, limit)));

  const selectedIds = new Set(ranked.map((item) => item.profile.id));
  return {
    profileCount: ranked.length,
    familyLinkCount: links.filter((link) => selectedIds.has(link.buyer_profile_id)).length,
    profiles: ranked.map(({ profile }) => ({
      id: profile.id,
      companyName: profile.company_name,
      country: profile.country,
      buyerType: profile.buyer_type,
      customerGroups: profile.customer_groups,
      salesChannels: profile.sales_channels,
      purchasingScenarios: profile.purchasing_scenarios,
      seasonality: profile.seasonality,
      replenishmentCycle: profile.replenishment_cycle,
      orderRequirements: profile.order_requirements,
      sourceUrl: profile.source_url,
      profileStatus: profile.profile_status,
    })),
    familyMatrix: ranked.flatMap(({ profile, profileLinks }) => profileLinks.map((link) => ({
      buyerProfileId: profile.id,
      companyName: profile.company_name,
      country: profile.country,
      trackCategory: link.track_category,
      productFamily: link.product_family,
      relationshipScore: link.relationship_score,
      familyRole: link.family_role,
      salesScenarios: link.sales_scenarios,
      rationale: link.rationale,
      evidenceStatus: link.evidence_status,
    }))).sort((a, b) => b.relationshipScore - a.relationshipScore),
  };
}
