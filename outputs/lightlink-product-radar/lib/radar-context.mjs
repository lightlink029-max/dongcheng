function listValue(value) {
  return Array.isArray(value) ? value : [];
}

export function compactRadarStatus(data) {
  return {
    run: data?.run ?? null,
    sources: listValue(data?.sources).map((source) => ({
      platform: source.platform,
      coverage: source.coverage,
      statuses: source.statuses,
      clusterCount: source.cluster_count,
      observationCount: source.observation_count,
      sourceKinds: source.source_kinds,
      sourceRefs: listValue(source.source_refs).slice(0, 3),
    })),
    results: listValue(data?.results).map((result) => ({
      keyword: result.canonical_keyword,
      group: result.group_name,
      aliases: result.aliases,
      category: result.category,
      market: result.market,
      language: result.language,
      intent: result.intent_label,
      status: result.cluster_status,
      attention: result.attention_level,
      momentum: result.momentum,
      commercialValidation: result.commercial_validation,
      buyerIntent: result.buyer_intent,
      competition: result.competition,
      heat: result.heat,
      opportunity: result.opportunity,
      confidence: result.confidence,
      rationale: result.rationale,
      anomalyFlags: result.anomaly_flags,
    })),
    recentHistory: listValue(data?.history).slice(0, 5).map((run) => ({
      id: run.id,
      query: run.query,
      market: run.market,
      language: run.language,
      status: run.status,
      clusterCount: run.cluster_count,
      createdAt: run.created_at,
    })),
    integrations: listValue(data?.integrations).map((integration) => ({
      id: integration.id,
      name: integration.name,
      configured: integration.configured,
      publicMode: integration.publicMode,
      automaticCollection: integration.automaticCollection,
    })),
  };
}
