function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function listValue(value) {
  return Array.isArray(value) ? value : [];
}

function countBy(values) {
  const counts = {};
  for (const value of values) {
    const key = String(value ?? "").trim() || "unknown";
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

function compactCandidate(candidate) {
  return {
    id: candidate.id,
    name: candidate.name,
    trackCategory: candidate.track_category,
    subcategory: candidate.subcategory,
    productFamily: candidate.product_family || candidate.subcategory,
    commercialVariant: candidate.commercial_variant,
    targetMarkets: listValue(candidate.target_markets),
    buyerTypes: listValue(candidate.buyer_types),
    priceBand: candidate.price_band,
    moq: candidate.moq,
    compliance: listValue(candidate.compliance),
    riskLevel: candidate.risk_level,
    stage: candidate.stage,
    score: candidate.score,
    rationale: candidate.rationale,
    evidenceStatus: candidate.evidence_status,
    imageUrls: listValue(candidate.image_urls),
    imageSourceRef: candidate.image_source_ref,
  };
}

function compactReport(report, detailLevel) {
  const value = objectValue(report);
  const summary = {
    summary: value.summary,
    recommendation: value.recommendation,
    scorecard: value.scorecard,
  };
  if (detailLevel === "candidate") return summary;
  const structure = {
    ...summary,
    trackCategories: value.trackCategories,
    marketHypotheses: value.marketHypotheses,
  };
  if (detailLevel !== "review") return structure;
  return {
    ...structure,
    playbook: value.playbook,
    sections: value.sections,
    risks: value.risks,
    actionPlan: value.actionPlan,
  };
}

export function compactResearchStatus(data, options = {}) {
  const project = objectValue(data?.project);
  const runs = listValue(data?.runs);
  const candidates = listValue(data?.candidates);
  const evidence = listValue(data?.evidence);
  const activeRun = runs.find((run) => ["waiting_for_codex", "researching", "queued"].includes(String(run?.status)));
  const latestCompletedRun = runs.find((run) => ["complete", "partial"].includes(String(run?.status)));
  const candidateId = String(options.candidateId ?? "").trim();
  const includeCandidates = Boolean(options.includeCandidates);
  const selectedCandidate = candidateId ? candidates.find((candidate) => candidate?.id === candidateId) : null;

  const result = {
    project: {
      id: project.id,
      productName: project.product_name,
      productCategory: project.product_category,
      productDescription: project.product_description,
      targetMarkets: listValue(project.target_markets),
      languages: listValue(project.languages),
      channels: listValue(project.channels),
      templateId: project.template_id,
      targetCandidateCount: project.target_candidate_count,
      objectives: project.objectives,
      constraints: project.constraints,
      status: project.status,
      currentStage: project.current_stage,
      progress: project.progress,
      summary: project.summary,
      recommendation: project.recommendation,
      scorecard: project.scorecard,
      runCount: project.run_count,
      evidenceCount: project.evidence_count,
      candidateCount: project.candidate_count,
    },
    activeTask: activeRun ? {
      runId: activeRun.id,
      status: activeRun.status,
      request: activeRun.request_payload,
      createdAt: activeRun.created_at,
    } : null,
    latestCompletedRun: latestCompletedRun ? {
      runId: latestCompletedRun.id,
      status: latestCompletedRun.status,
      sourceSummary: latestCompletedRun.source_summary,
      createdAt: latestCompletedRun.created_at,
      completedAt: latestCompletedRun.completed_at,
    } : null,
    latestReport: latestCompletedRun
      ? compactReport(latestCompletedRun.result_payload, candidateId ? "candidate" : includeCandidates ? "review" : "structure")
      : null,
    candidateStats: {
      total: candidates.length,
      byTrack: countBy(candidates.map((candidate) => candidate?.track_category)),
      byStage: countBy(candidates.map((candidate) => candidate?.stage)),
      withImages: candidates.filter((candidate) => listValue(candidate?.image_urls).length > 0).length,
    },
    evidenceSummary: {
      total: evidence.length,
      byStatus: countBy(evidence.map((item) => item?.status)),
      bySourceType: countBy(evidence.map((item) => item?.source_type)),
      byMarket: countBy(evidence.map((item) => item?.market)),
    },
    evidenceIndex: evidence.slice(0, 30).map((item) => ({
      section: item.section,
      title: item.source_title,
      url: item.source_url,
      market: item.market,
      status: item.status,
    })),
  };

  if (candidateId) result.candidate = selectedCandidate ? compactCandidate(selectedCandidate) : null;
  else if (includeCandidates) result.candidates = candidates.map(compactCandidate);
  else result.candidateNames = candidates.map((candidate) => candidate?.name).filter(Boolean);

  return result;
}
