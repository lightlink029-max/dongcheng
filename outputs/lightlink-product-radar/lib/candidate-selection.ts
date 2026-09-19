export const SELECTION_SCORE_FIELDS = {
  demand: { label: "需求证据", max: 25 },
  economics: { label: "单位经济", max: 20 },
  supply: { label: "供应稳定", max: 15 },
  compliance: { label: "合规可行", max: 15 },
  differentiation: { label: "差异化", max: 15 },
  execution: { label: "团队可执行", max: 10 },
} as const;

export const SELECTION_GATE_FIELDS = {
  buyerDefined: "目标买家已明确",
  economicsVerified: "报价、MOQ 与毛利已核验",
  supplierVerified: "供应商、交期与产能已核验",
  complianceVerified: "认证、标签与物流门槛已核验",
  intellectualPropertyClear: "商标、图片与外观知识产权已排查",
} as const;

export const CHANNEL_FIT_FIELDS = {
  alibaba: "Alibaba 国际站",
  social: "社媒获客",
  website: "独立站",
} as const;

export type SelectionScoreKey = keyof typeof SELECTION_SCORE_FIELDS;
export type SelectionGateKey = keyof typeof SELECTION_GATE_FIELDS;
export type ChannelFitKey = keyof typeof CHANNEL_FIT_FIELDS;
export type SelectionDecision = "unreviewed" | "research" | "shortlist" | "ready" | "blocked";

export type CandidateSelectionAssessment = {
  version: 1;
  scorecard: Record<SelectionScoreKey, number | null>;
  channelFit: Record<ChannelFitKey, number | null>;
  gates: Record<SelectionGateKey, boolean>;
  decision: SelectionDecision;
  note: string;
  assessedAt: string;
  assessedBy: "user";
};

export type SelectionCandidate = {
  target_markets?: string[];
  buyer_types?: string[];
  price_band?: string;
  moq?: string;
  compliance?: string[];
  image_urls?: string[];
  image_source_ref?: string;
  evidence_status?: string;
};

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function boundedOptional(value: unknown, max: number) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(Math.min(max, Math.max(0, parsed))) : null;
}

export function emptyCandidateSelectionAssessment(): CandidateSelectionAssessment {
  return {
    version: 1,
    scorecard: { demand: null, economics: null, supply: null, compliance: null, differentiation: null, execution: null },
    channelFit: { alibaba: null, social: null, website: null },
    gates: { buyerDefined: false, economicsVerified: false, supplierVerified: false, complianceVerified: false, intellectualPropertyClear: false },
    decision: "unreviewed",
    note: "",
    assessedAt: "",
    assessedBy: "user",
  };
}

export function normalizeCandidateSelectionAssessment(value: unknown): CandidateSelectionAssessment {
  const base = emptyCandidateSelectionAssessment();
  const source = objectValue(value);
  const scorecard = objectValue(source.scorecard);
  const channelFit = objectValue(source.channelFit);
  const gates = objectValue(source.gates);
  const decision = ["unreviewed", "research", "shortlist", "ready", "blocked"].includes(String(source.decision))
    ? source.decision as SelectionDecision
    : "unreviewed";
  return {
    ...base,
    scorecard: Object.fromEntries(Object.entries(SELECTION_SCORE_FIELDS).map(([key, meta]) => [key, boundedOptional(scorecard[key], meta.max)])) as CandidateSelectionAssessment["scorecard"],
    channelFit: Object.fromEntries(Object.keys(CHANNEL_FIT_FIELDS).map((key) => [key, boundedOptional(channelFit[key], 100)])) as CandidateSelectionAssessment["channelFit"],
    gates: Object.fromEntries(Object.keys(SELECTION_GATE_FIELDS).map((key) => [key, gates[key] === true])) as CandidateSelectionAssessment["gates"],
    decision,
    note: String(source.note ?? "").trim().slice(0, 2000),
    assessedAt: String(source.assessedAt ?? "").slice(0, 40),
    assessedBy: "user",
  };
}

export function selectionScoreTotal(assessment: CandidateSelectionAssessment) {
  return Object.values(assessment.scorecard).reduce<number>((sum, value) => sum + (value ?? 0), 0);
}

export function selectionAssessmentComplete(assessment: CandidateSelectionAssessment) {
  return Object.values(assessment.scorecard).every((value) => value !== null)
    && Object.values(assessment.channelFit).every((value) => value !== null);
}

export function candidateHandoffReadiness(candidate: SelectionCandidate, value: unknown) {
  const assessment = normalizeCandidateSelectionAssessment(value);
  const blockers: string[] = [];
  if (assessment.decision !== "ready") blockers.push("人工决策尚未设为“可移交”");
  if (!selectionAssessmentComplete(assessment)) blockers.push("评分卡或渠道适配尚未填完");
  if (selectionScoreTotal(assessment) < 70) blockers.push("选品总分低于 70");
  for (const [key, label] of Object.entries(SELECTION_GATE_FIELDS)) {
    if (!assessment.gates[key as SelectionGateKey]) blockers.push(label);
  }
  if (!candidate.target_markets?.length) blockers.push("缺少目标市场");
  if (!candidate.buyer_types?.length) blockers.push("缺少买家类型");
  if (!candidate.price_band?.trim()) blockers.push("缺少采购/销售价格带");
  if (!candidate.moq?.trim()) blockers.push("缺少 MOQ");
  if (!candidate.compliance?.length) blockers.push("缺少合规要求");
  if (!candidate.image_urls?.length || !candidate.image_source_ref?.trim()) blockers.push("缺少可追溯产品图片");
  if (!candidate.evidence_status || candidate.evidence_status === "hypothesis") blockers.push("产品证据仍是待验证假设");
  return { ready: blockers.length === 0, blockers, score: selectionScoreTotal(assessment), assessment };
}
