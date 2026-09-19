"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Archive, ArrowLeft, Bot, CalendarClock, CheckCircle2, ChevronRight, Database, FileCheck2, PackageSearch, RefreshCw, Search, Target, TrendingUp, Users, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  OpportunityPrograms,
  type OpportunityCustomerFeedback,
  type OpportunityProgram,
  type OpportunityProgramSeed,
  type OpportunityRound,
  type OpportunityRoundFamily,
} from "@/components/opportunity-programs";
import {
  OPPORTUNITY_SIGNAL_FIELDS,
  OPPORTUNITY_SIGNAL_RESPONSIBILITIES,
  OPPORTUNITY_VALIDATION_PLAN,
  buildOpportunityDecision,
  isOpportunityValidationStepDone,
  opportunityValidationPrerequisite,
  suggestOpportunitySignals,
  type OpportunitySignalField,
  type OpportunitySignalSuggestion,
  type OpportunitySignals,
  type OpportunityValidationStepKey,
} from "@/lib/opportunity";
import {
  groupTradeObservationPoints,
  TRADE_COLLECTION_LEVELS,
  TRADE_COLLECTION_POLICIES,
  tradeCollectionLevelForOpportunityStatus,
  tradeCoverageLevel,
  tradeCoverageSatisfies,
  type TradeCollectionLevel,
} from "@/lib/trade-data";
import { CHATGPT_TRADE_WORKFLOW, USER_TRADE_RESPONSIBILITIES } from "@/lib/trade-source-catalog";

type TaxonomyRegion = { code: string; name: string };
type TaxonomyPersona = { code: string; name: string; purchase_scenarios: string[]; sales_channels: string[] };
type TaxonomyFamily = { code: string; name: string; track_code: string; track_name: string };
type TaxonomyMatrix = {
  id: string;
  persona_code: string;
  region_code: string;
  track_code: string;
  product_family_code: string;
  relevance_score: number;
  family_role: string;
  sales_scenarios: string[];
  rationale: string;
  evidence_status: string;
};

type OpportunityScores = {
  marketScore: number | null;
  buyerScore: number | null;
  sourcingScore: number | null;
  confidence: number;
  recommendedAction: "continue_validation" | "develop_buyers" | "source_suppliers" | "pilot" | "pause";
};

type OpportunityCase = {
  id: string;
  dossier_id: string;
  program_id: string;
  title: string;
  persona_code: string;
  persona_name: string;
  region_code: string;
  region_name: string;
  track_code: string;
  track_name: string;
  product_family_code: string;
  product_family_name: string;
  purchase_scenario: string;
  sales_channel: string;
  hypothesis: string;
  status: string;
  owner_name: string;
  next_review_at: string;
  next_action: string;
  active: boolean;
  version: number;
  updated_at: string;
  signals: OpportunitySignals;
  scores: OpportunityScores;
  evidence_count: number;
  last_evidence_at: string | null;
  latest_assessment: { rationale: string; created_at: string } | null;
};

type OpportunityEvidence = {
  id: string;
  opportunity_id: string;
  dossier_id: string;
  evidence_scope: "shared" | "project";
  evidence_type: string;
  source_grade: string;
  title: string;
  source_url: string;
  note: string;
  period: string;
  metrics: Record<string, unknown>;
  captured_at: string;
};

type OpportunityData = {
  cases: OpportunityCase[];
  evidence: OpportunityEvidence[];
  programs: OpportunityProgram[];
  rounds: OpportunityRound[];
  roundFamilies: OpportunityRoundFamily[];
  customerFeedback: OpportunityCustomerFeedback[];
  taxonomy: {
    regions: TaxonomyRegion[];
    personaCategories: TaxonomyPersona[];
    productFamilies: TaxonomyFamily[];
    personaMatrix: TaxonomyMatrix[];
  };
  tradeData: TradeObservation[];
  tradeRequests: TradeRequest[];
  validationRequests: OpportunityValidationRequest[];
  stats: { total: number; active: number; validating: number; qualified: number; needsEvidence: number; archived: number; localTradeObservations: number; programs?: number; activePrograms?: number; validatingPrograms?: number; scalingPrograms?: number; reviewDuePrograms?: number; voidedPrograms?: number };
  automation?: { tradeData?: TradeRequestResult | null };
};

type TradeObservation = {
  id: string;
  opportunity_id: string;
  product_family_code: string;
  region_code: string;
  reporter_code: string;
  partner_code: string;
  commodity_code: string;
  classification: string;
  commodity_label: string;
  flow: string;
  period: string;
  frequency: string;
  metric: string;
  value: number | null;
  unit: string;
  source_name: string;
  source_url: string;
  source_grade: string;
  data_status: string;
  missing_reason: string;
  collected_at: string;
};

type TradeRequest = { id: string; opportunity_id: string; status: string; collection_level: TradeCollectionLevel; error: string; created_at: string; completed_at: string | null };
type OpportunityValidationRequest = { id: string; opportunity_id: string; status: string; summary: string; suggested_next_action: string; error: string; created_at: string; completed_at: string | null };
type TradeRequestResult = {
  reuseLocal?: boolean;
  pending?: boolean;
  collectionLevel?: TradeCollectionLevel;
  request?: Record<string, unknown> & { runId?: string; collectionLevel?: TradeCollectionLevel };
  error?: string;
};
type TradeRequestConfirmation = {
  collectionLevel: TradeCollectionLevel;
  forceRefresh: boolean;
};
type OpportunityValidationRequestResult = {
  pending?: boolean;
  runId?: string;
  request?: Record<string, unknown> & { runId?: string; opportunityId?: string };
  error?: string;
};

const STATUS_LABELS: Record<string, string> = {
  hypothesis: "待验证",
  validating: "验证中",
  qualified: "商机成立",
  pilot: "样品/试单",
  paused: "暂停观察",
  archived: "已归档",
};

const ACTION_LABELS: Record<OpportunityScores["recommendedAction"], string> = {
  continue_validation: "继续补证据",
  develop_buyers: "开发画像客户",
  source_suppliers: "寻找产品货源",
  pilot: "进入样品/试单",
  pause: "暂停观察",
};

const DECISION_STATUS_LABELS: Record<string, string> = {
  validate_buyers: "值得低成本验证",
  validate_supply: "验证交付与利润",
  pilot_ready: "可进入小单验证",
  hold: "建议暂停",
  insufficient: "证据不足",
};

const SIGNAL_LABELS: Record<OpportunitySignalField, string> = {
  tradeTrend: "贸易增长",
  buyerDemand: "已验证需求",
  channelSignal: "渠道信号",
  personaFit: "真实客户匹配",
  leadQuality: "有效商机质量",
  repeatPotential: "已验证复购潜力",
  supplierCoverage: "供应准备度",
  unitEconomics: "预计落地利润",
  complianceReadiness: "合规准备度",
};

const SIGNAL_GROUPS: Array<{
  title: string;
  description: string;
  fields: OpportunitySignalField[];
}> = [
  {
    title: "市场机会",
    description: "判断市场是否存在、渠道是否有响应；公开买家公司页面不等于真实需求。",
    fields: ["tradeTrend", "buyerDemand", "channelSignal"],
  },
  {
    title: "客户价值",
    description: "仅用真实访谈、RFQ 或成交记录评分；画像矩阵只用于筛选候选，不生成高分。",
    fields: ["personaFit", "leadQuality", "repeatPotential"],
  },
  {
    title: "成交前交付准备",
    description: "报价、样品和证书只能评估准备度；供应商真实能力要在首单后按质量、交期和异常复盘。",
    fields: ["supplierCoverage", "unitEconomics", "complianceReadiness"],
  },
];

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  demand: "市场需求",
  buyer: "真实买家",
  buyer_discovery: "客户发现访谈",
  channel: "销售渠道",
  competition: "竞争价格",
  product_matrix: "产品与报价矩阵",
  supply: "供应与报价",
  compliance: "合规物流",
  fulfillment: "首单履约结果",
  internal: "Odoo 内部结果",
};

const VALIDATION_STEP_PRESETS: Record<OpportunityValidationStepKey, { evidenceType: string; sourceGrade: string; metricName: string; title: string }> = {
  public_evidence: { evidenceType: "demand", sourceGrade: "official", metricName: "", title: "公开市场与客户证据" },
  buyer_discovery: { evidenceType: "buyer_discovery", sourceGrade: "verified_buyer", metricName: "qualified_discovery_count", title: "客户发现访谈汇总" },
  offer_matrix: { evidenceType: "product_matrix", sourceGrade: "internal_odoo", metricName: "sellable_variant_count", title: "产品与报价矩阵" },
  supplier_feasibility: { evidenceType: "supply", sourceGrade: "supplier_quote", metricName: "comparable_quote_count", title: "同口径供应商报价汇总" },
  economics_compliance: { evidenceType: "compliance", sourceGrade: "internal_odoo", metricName: "landed_margin_pct", title: "落地成本与合规核验" },
  buyer_offer_validation: { evidenceType: "buyer", sourceGrade: "verified_buyer", metricName: "rfq_count", title: "方案报价与询盘反馈" },
  pilot_fulfillment: { evidenceType: "fulfillment", sourceGrade: "internal_odoo", metricName: "completed_order_count", title: "首单履约复盘" },
};

const SOURCE_GRADE_LABELS: Record<string, string> = {
  official: "官方数据",
  verified_buyer: "已核实买家",
  supplier_quote: "供应商报价",
  internal_odoo: "Odoo 内部记录",
  marketplace: "平台信号",
  other: "其他来源",
};

const emptySignals = Object.fromEntries(OPPORTUNITY_SIGNAL_FIELDS.map((field) => [field, null])) as OpportunitySignals;

async function postOpportunity(body: Record<string, unknown>) {
  const response = await fetch("/api/radar", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await response.json() as OpportunityData & { error?: string };
  if (!response.ok) throw new Error(result.error ?? "保存商机失败");
  return result;
}

async function getOpportunityData() {
  const response = await fetch("/api/radar?view=opportunity_center", { cache: "no-store" });
  const result = await response.json() as OpportunityData & { error?: string };
  if (!response.ok) throw new Error(result.error ?? "读取商机验证中心失败");
  return result;
}

async function dispatchTradeTask(request: NonNullable<TradeRequestResult["request"]>) {
  if (!request.runId) throw new Error("补采任务缺少运行编号");
  try {
    const response = await fetch("http://127.0.0.1:8788/dispatch", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ taskType: "trade_data", ...request }),
    });
    const result = await response.json() as { accepted?: boolean; error?: string };
    if (!response.ok || !result.accepted) throw new Error(result.error ?? "贸易数据 AI 通道未响应");
  } catch (error) {
    await fetch("/api/radar", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "fail_trade_data_request", runId: request.runId, error: error instanceof Error ? error.message : "贸易数据任务失败" }),
    }).catch(() => undefined);
    throw error;
  }
}

async function dispatchOpportunityValidationTask(request: NonNullable<OpportunityValidationRequestResult["request"]>) {
  if (!request.runId) throw new Error("公开证据任务缺少运行编号");
  try {
    const response = await fetch("http://127.0.0.1:8788/dispatch", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ taskType: "opportunity_validation", ...request }),
    });
    const result = await response.json() as { accepted?: boolean; error?: string };
    if (!response.ok || !result.accepted) throw new Error(result.error ?? "商机验证 AI 通道未响应");
  } catch (error) {
    await fetch("/api/radar", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "fail_opportunity_validation_request", runId: request.runId, error: error instanceof Error ? error.message : "公开证据任务失败" }),
    }).catch(() => undefined);
    throw error;
  }
}

function scoreText(value: number | null) {
  return value === null ? "待补" : String(value);
}

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("zh-CN");
}

export function OpportunityCenter({ seed, onSeedConsumed, onOpenSources, onOpenGlobalPersonas }: {
  seed?: OpportunityProgramSeed | null;
  onSeedConsumed?: () => void;
  onOpenSources?: () => void;
  onOpenGlobalPersonas: () => void;
}) {
  const detailScrollRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<OpportunityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState("overview");
  const [activeValidationStepKey, setActiveValidationStepKey] = useState<OpportunityValidationStepKey | null>(null);
  const [signals, setSignals] = useState<OpportunitySignals>(emptySignals);
  const [assessmentSuggestion, setAssessmentSuggestion] = useState<OpportunitySignalSuggestion | null>(null);
  const [assessmentRationale, setAssessmentRationale] = useState("");
  const [evidenceType, setEvidenceType] = useState("demand");
  const [sourceGrade, setSourceGrade] = useState("official");
  const [evidenceTitle, setEvidenceTitle] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [evidencePeriod, setEvidencePeriod] = useState("");
  const [evidenceNote, setEvidenceNote] = useState("");
  const [metricName, setMetricName] = useState("");
  const [metricValue, setMetricValue] = useState("");
  const [tradeBusy, setTradeBusy] = useState(false);
  const [tradeMessage, setTradeMessage] = useState("");
  const [tradeConfirmation, setTradeConfirmation] = useState<TradeRequestConfirmation | null>(null);
  const [validationBusy, setValidationBusy] = useState(false);
  const [validationMessage, setValidationMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      setData(await getOpportunityData());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取商机验证中心失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void getOpportunityData()
      .then((result) => { if (!cancelled) setData(result); })
      .catch((error: unknown) => { if (!cancelled) setMessage(error instanceof Error ? error.message : "读取商机验证中心失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const selected = data?.cases.find((item) => item.id === selectedId) ?? null;
  const selectedCanEdit = Boolean(selected?.active && selected.status !== "archived");
  const selectedEvidence = useMemo(() => data?.evidence.filter((item) => item.opportunity_id === selectedId
    || (item.evidence_scope === "shared" && selected?.dossier_id && item.dossier_id === selected.dossier_id)) ?? [], [data?.evidence, selected, selectedId]);
  const activeValidationStep = OPPORTUNITY_VALIDATION_PLAN.find((step) => step.key === activeValidationStepKey) ?? null;
  const selectedTradeRows = useMemo(() => selected ? (data?.tradeData ?? []).filter((item) => item.product_family_code === selected.product_family_code
    && (item.region_code === selected.region_code || item.region_code === "GLOBAL")) : [], [data?.tradeData, selected]);
  const selectedTradeGroups = useMemo(() => {
    const groups = new Map<string, { key: string; commodityCode: string; commodityLabel: string; flow: string; rows: TradeObservation[] }>();
    [...selectedTradeRows]
      .sort((left, right) => right.period.localeCompare(left.period) || left.reporter_code.localeCompare(right.reporter_code))
      .forEach((row) => {
        const key = `${row.commodity_code}:${row.flow}`;
        const group = groups.get(key) ?? {
          key,
          commodityCode: row.commodity_code,
          commodityLabel: row.commodity_label,
          flow: row.flow,
          rows: [],
        };
        group.rows.push(row);
        groups.set(key, group);
      });
    return [...groups.values()].map((group) => ({ ...group, points: groupTradeObservationPoints(group.rows) }));
  }, [selectedTradeRows]);
  const selectedTradeSummary = useMemo(() => {
    const points = groupTradeObservationPoints(selectedTradeRows);
    const countries = new Set(selectedTradeRows.map((item) => item.reporter_code).filter(Boolean));
    const periods = [...new Set(selectedTradeRows.map((item) => item.period).filter(Boolean))].sort();
    const commodities = new Set(selectedTradeRows.map((item) => item.commodity_code).filter(Boolean));
    const available = points.filter((point) => point.rows.some((item) => item.data_status === "available" && item.value !== null)).length;
    return {
      points: points.length,
      sourceRecords: selectedTradeRows.length,
      countries: countries.size,
      commodities: commodities.size,
      available,
      periodRange: periods.length ? (periods.length === 1 ? periods[0] : `${periods[0]} – ${periods[periods.length - 1]}`) : "—",
    };
  }, [selectedTradeRows]);
  const selectedTradeRequest = selected ? (data?.tradeRequests ?? []).find((item) => item.opportunity_id === selected.id) : null;
  const selectedValidationRequest = selected ? (data?.validationRequests ?? []).find((item) => item.opportunity_id === selected.id) : null;
  const selectedTradeCoverage = tradeCoverageLevel(selectedTradeRows);
  const recommendedTradeLevel = tradeCollectionLevelForOpportunityStatus(selected?.status);
  const recommendedTradeCovered = tradeCoverageSatisfies(selectedTradeCoverage, recommendedTradeLevel);
  const automaticSuggestion = useMemo(() => {
    if (!selected || !data) return null;
    const matrixScores = data.taxonomy.personaMatrix
      .filter((item) => item.persona_code === selected.persona_code
        && item.product_family_code === selected.product_family_code
        && (item.region_code === selected.region_code || item.region_code === "GLOBAL"))
      .map((item) => Number(item.relevance_score))
      .filter(Number.isFinite);
    return suggestOpportunitySignals({
      evidence: selectedEvidence,
      tradeRows: selectedTradeRows,
      personaMatrixScore: matrixScores.length ? Math.max(...matrixScores) : null,
    });
  }, [data, selected, selectedEvidence, selectedTradeRows]);
  const effectiveSignals = useMemo(() => Object.fromEntries(OPPORTUNITY_SIGNAL_FIELDS.map((field) => [
    field,
    automaticSuggestion?.signals[field] ?? signals[field],
  ])) as OpportunitySignals, [automaticSuggestion, signals]);
  const opportunityDecision = useMemo(() => buildOpportunityDecision(effectiveSignals), [effectiveSignals]);
  const openCase = (item: OpportunityCase) => {
    setSelectedId(item.id);
    setDetailTab("overview");
    setActiveValidationStepKey(null);
    setSignals(item.signals);
    setAssessmentSuggestion(null);
    setAssessmentRationale(item.latest_assessment?.rationale ?? "");
    setMessage("");
    setTradeMessage("");
    setTradeConfirmation(null);
    setValidationMessage("");
  };

  const closeCase = () => {
    setSelectedId(null);
    setTradeConfirmation(null);
    setActiveValidationStepKey(null);
    setMessage("");
    setTradeMessage("");
    setValidationMessage("");
  };

  const saveAssessment = async () => {
    if (!selected || !selectedCanEdit) return;
    setBusy(true);
    try {
      const result = await postOpportunity({ action: "add_opportunity_assessment", opportunityId: selected.id, signals, rationale: assessmentRationale });
      setData(result);
      setMessage("验证指标已保存为新的评估快照。" );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存评估失败");
    } finally {
      setBusy(false);
    }
  };

  const generateAssessmentSuggestion = () => {
    if (!automaticSuggestion) return;
    const suggestion = automaticSuggestion;
    setAssessmentSuggestion(suggestion);
    setSignals((current) => Object.fromEntries(OPPORTUNITY_SIGNAL_FIELDS.map((field) => [
      field,
      suggestion.signals[field] ?? current[field],
    ])) as OpportunitySignals);
    setAssessmentRationale((current) => current.trim() ? current : suggestion.summary);
  };

  const saveEvidence = async () => {
    if (!selected || !selectedCanEdit) return;
    setBusy(true);
    try {
      const metrics = metricName.trim() ? { [metricName.trim()]: metricValue.trim() } : {};
      const result = await postOpportunity({
        action: "add_opportunity_evidence",
        opportunityId: selected.id,
        evidenceType,
        sourceGrade,
        title: evidenceTitle,
        sourceUrl: evidenceUrl,
        period: evidencePeriod,
        note: evidenceNote,
        marketCode: selected.region_code,
        metrics,
      });
      setData(result);
      setAssessmentSuggestion(null);
      setEvidenceTitle("");
      setEvidenceUrl("");
      setEvidencePeriod("");
      setEvidenceNote("");
      setMetricName("");
      setMetricValue("");
      setMessage("证据已追加，原有记录没有被覆盖。" );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存证据失败");
    } finally {
      setBusy(false);
    }
  };

  const requestTradeData = async (forceRefresh = false, collectionLevel: TradeCollectionLevel = recommendedTradeLevel) => {
    if (!selected || !selectedCanEdit) return;
    setTradeBusy(true);
    setTradeMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "create_trade_data_request", opportunityId: selected.id, forceRefresh, collectionLevel, triggerReason: "manual", confirmed: true }),
      });
      const result = await response.json() as TradeRequestResult;
      if (!response.ok) throw new Error(result.error ?? "建立贸易数据补采任务失败");
      if (result.reuseLocal) {
        setTradeMessage("已命中120天内的本地贸易数据，本次无需联网查询。");
        return;
      }
      if (result.pending) {
        setTradeMessage("该商机已有贸易数据任务在执行，无需重复发送。");
        await load();
        return;
      }
      if (!result.request?.runId) throw new Error("补采任务缺少运行编号");
      await dispatchTradeTask(result.request);
      setTradeMessage(`本地尚未满足“${TRADE_COLLECTION_POLICIES[collectionLevel].label}”，已转入独立 AI 补采通道；完成后自动入库。`);
      setData(await getOpportunityData());
      setAssessmentSuggestion(null);
    } catch (error) {
      setTradeMessage(error instanceof Error ? error.message : "贸易数据补采失败");
    } finally {
      setTradeBusy(false);
    }
  };

  const prepareTradeDataRequest = (forceRefresh = false, collectionLevel: TradeCollectionLevel = recommendedTradeLevel) => {
    if (!selected || !selectedCanEdit || tradeBusy) return;
    if (selectedTradeRequest?.status === "pending") {
      setTradeMessage(`“${TRADE_COLLECTION_POLICIES[selectedTradeRequest.collection_level ?? "baseline"].label}”正在补采，无需重复操作。`);
      return;
    }
    setTradeConfirmation({ forceRefresh, collectionLevel });
  };

  const confirmTradeDataRequest = async () => {
    if (!tradeConfirmation || selectedTradeRequest?.status === "pending") return;
    const request = tradeConfirmation;
    setTradeConfirmation(null);
    await requestTradeData(request.forceRefresh, request.collectionLevel);
  };

  const requestOpportunityValidation = async () => {
    if (!selected || !selectedCanEdit) return;
    setValidationBusy(true);
    setValidationMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "create_opportunity_validation_request",
          opportunityId: selected.id,
          triggerReason: "decision_gate",
          requestNote: "优先补真实买家公司及品类页、目标渠道价格和官方合规来源；不得把公开经营范围描述成真实采购意向。",
        }),
      });
      const result = await response.json() as OpportunityValidationRequestResult;
      if (!response.ok) throw new Error(result.error ?? "建立公开证据任务失败");
      if (result.pending) {
        setValidationMessage("该商机已有公开证据任务在执行，无需重复发送。");
        await load();
        return;
      }
      if (!result.request?.runId) throw new Error("公开证据任务缺少运行编号");
      await dispatchOpportunityValidationTask(result.request);
      setValidationMessage("已发送到独立商机验证通道：AI 会采集可核验的买家、渠道和官方合规来源并自动入库。");
      setData(await getOpportunityData());
    } catch (error) {
      setValidationMessage(error instanceof Error ? error.message : "公开证据任务启动失败");
    } finally {
      setValidationBusy(false);
    }
  };

  const openValidationStep = (requestedStepKey: OpportunityValidationStepKey) => {
    if (!selected) return;
    const prerequisite = opportunityValidationPrerequisite(requestedStepKey, selectedEvidence);
    const stepKey = prerequisite ?? requestedStepKey;
    const step = OPPORTUNITY_VALIDATION_PLAN.find((item) => item.key === stepKey);
    if (!step) return;

    if (prerequisite) {
      const requested = OPPORTUNITY_VALIDATION_PLAN.find((item) => item.key === requestedStepKey);
      setValidationMessage(`“${requested?.title ?? "该阶段"}”尚未开放，请先完成“${step.title}”。`);
    }

    if (stepKey === "public_evidence" && !isOpportunityValidationStepDone(stepKey, selectedEvidence)) {
      void requestOpportunityValidation();
      return;
    }

    const hasUnsavedEvidence = [evidenceTitle, evidenceUrl, evidencePeriod, evidenceNote, metricName, metricValue]
      .some((value) => value.trim());
    if (!hasUnsavedEvidence) {
      const preset = VALIDATION_STEP_PRESETS[stepKey];
      setEvidenceType(preset.evidenceType);
      setSourceGrade(preset.sourceGrade);
      setEvidenceTitle(`${selected.product_family_name} · ${preset.title}`);
      setMetricName(preset.metricName);
    }
    setActiveValidationStepKey(stepKey);
    setDetailTab("evidence");
    window.setTimeout(() => detailScrollRef.current?.scrollTo({ top: 0, behavior: "smooth" }), 0);
  };

  useEffect(() => {
    if (!selectedId || selectedTradeRequest?.status !== "pending" && selectedValidationRequest?.status !== "pending") return;
    const timer = window.setInterval(() => {
      void getOpportunityData().then(setData).catch(() => undefined);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [selectedId, selectedTradeRequest?.status, selectedValidationRequest?.status]);

  if (loading && !data) return <div className="rounded-2xl border bg-white p-8 text-center text-muted-foreground">正在读取商机验证中心…</div>;

  return (
    <div className="space-y-5">
      <section className="rounded-3xl bg-gradient-to-br from-cyan-950 via-cyan-900 to-teal-800 p-7 text-white shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200">Opportunity Validation</p>
            <h2 className="mt-2 text-2xl font-semibold">画像 × 地区 × 场景 × 渠道 × 产品家族</h2>
            <p className="mt-2 text-sm leading-6 text-cyan-100">持续追加贸易趋势、真实买家、渠道、供应和合规证据，分别判断是否开发客户、寻找货源或进入样品试单。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white" onClick={onOpenSources}><Database /> 数据渠道与分工</Button>
            <Button variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white" onClick={() => void load()} disabled={loading}><RefreshCw /> 刷新</Button>
            <Button className="bg-cyan-300 text-cyan-950 hover:bg-cyan-200" onClick={onOpenGlobalPersonas}>从全球画像建立</Button>
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {([
          { label: "在用项目", value: data?.stats.activePrograms ?? 0, Icon: Target },
          { label: "验证中", value: data?.stats.validatingPrograms ?? 0, Icon: TrendingUp },
          { label: "常态开发", value: data?.stats.scalingPrograms ?? 0, Icon: FileCheck2 },
          { label: "待复核", value: data?.stats.reviewDuePrograms ?? 0, Icon: Search },
          { label: "已作废", value: data?.stats.voidedPrograms ?? 0, Icon: Archive },
        ] satisfies Array<{ label: string; value: number; Icon: LucideIcon }>).map(({ label, value, Icon }) => (
          <Card key={label}><CardContent className="flex items-center gap-3 p-4"><div className="rounded-xl bg-cyan-50 p-2 text-cyan-800"><Icon className="size-5" /></div><div><p className="text-xs text-muted-foreground">{label}</p><p className="text-2xl font-semibold tabular-nums">{value}</p></div></CardContent></Card>
        ))}
      </div>
      {message && <p className="rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-900">{message}</p>}

      {data && <OpportunityPrograms
        data={data}
        seed={seed}
        onSeedConsumed={onSeedConsumed}
        onOpenGlobalPersonas={onOpenGlobalPersonas}
        onDataChange={(result) => setData(result as OpportunityData)}
        onOpenOpportunity={(opportunityId) => {
          const opportunity = data.cases.find((item) => item.id === opportunityId);
          if (opportunity) openCase(opportunity);
        }}
      />}

      <Dialog open={Boolean(tradeConfirmation)} onOpenChange={(open) => { if (!open && !tradeBusy) setTradeConfirmation(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tradeConfirmation?.forceRefresh ? "确认强制更新贸易数据？" : `确认补采“${TRADE_COLLECTION_POLICIES[tradeConfirmation?.collectionLevel ?? recommendedTradeLevel].label}”？`}</DialogTitle>
            <DialogDescription>
              {tradeConfirmation?.forceRefresh
                ? "系统将重新采集所选层级并增量写入，不会删除现有观测。"
                : "系统会先检查 120 天内的本地缓存；覆盖不足时才创建独立补采任务。"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 rounded-xl border bg-slate-50 p-4 text-sm">
            <div><span className="text-muted-foreground">商机：</span><span className="font-medium">{selected?.title}</span></div>
            <div><span className="text-muted-foreground">采集层级：</span><span className="font-medium">{TRADE_COLLECTION_POLICIES[tradeConfirmation?.collectionLevel ?? recommendedTradeLevel].label}</span></div>
            <p className="leading-6 text-muted-foreground">{TRADE_COLLECTION_POLICIES[tradeConfirmation?.collectionLevel ?? recommendedTradeLevel].description}</p>
            <p className="flex items-start gap-2 text-amber-800"><AlertTriangle className="mt-0.5 size-4 shrink-0" />任务开始后会显示“补采中/更新中”，完成前不能再次发起贸易数据任务。</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTradeConfirmation(null)}>取消</Button>
            <Button onClick={() => void confirmTradeDataRequest()} disabled={tradeBusy || selectedTradeRequest?.status === "pending"}>
              <Bot /> {tradeConfirmation?.forceRefresh ? "确认强制更新" : "确认补采"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={Boolean(selected)} onOpenChange={(open) => { if (!open) closeCase(); }}>
        <SheetContent className="w-full gap-0 overflow-hidden p-0 sm:max-w-5xl">
          {selected && <Tabs value={detailTab} onValueChange={setDetailTab} className="h-full min-w-0 gap-0">
            <SheetHeader className="shrink-0 border-b bg-white px-5 py-4 pr-14 sm:px-6">
              <Button variant="ghost" size="sm" className="mb-1 w-fit -translate-x-2" onClick={closeCase}>
                <ArrowLeft /> {selected.program_id ? "返回验证项目" : "返回商机列表"}
              </Button>
              <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <SheetTitle className="break-words text-xl leading-7">{selected.title}</SheetTitle>
                  <SheetDescription className="mt-1 break-words">{selected.persona_name} · {selected.region_name} · {selected.product_family_name}</SheetDescription>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Badge>{STATUS_LABELS[selected.status]}</Badge>
                  <Badge variant="outline">{ACTION_LABELS[selected.scores.recommendedAction]}</Badge>
                  <Badge variant="outline">v{selected.version}</Badge>
                </div>
              </div>
            </SheetHeader>

            <TabsList variant="line" className="h-auto w-full shrink-0 justify-start gap-1 overflow-x-auto rounded-none border-b bg-white px-4 py-0 sm:px-6">
              <TabsTrigger value="overview" className="min-w-24 py-3">概览</TabsTrigger>
              <TabsTrigger value="trade" className="min-w-28 py-3">贸易数据 <span className="text-xs">{selectedTradeSummary.points}</span></TabsTrigger>
              <TabsTrigger value="assessment" className="min-w-24 py-3">验证评分</TabsTrigger>
              <TabsTrigger value="evidence" className="min-w-24 py-3">证据 <span className="text-xs">{selectedEvidence.length}</span></TabsTrigger>
            </TabsList>

            <div ref={detailScrollRef} className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden bg-slate-50/70 p-4 sm:p-6">
              <TabsContent value="overview" className="m-0 space-y-5">
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  {([['市场需求', selected.scores.marketScore], ['客户开发', selected.scores.buyerScore], ['找货可行', selected.scores.sourcingScore], ['置信度', selected.scores.confidence]] as Array<[string, number | null]>).map(([label, value]) => (
                    <div key={label} className="rounded-2xl border bg-white p-4 shadow-sm">
                      <p className="text-xs text-muted-foreground">{label}</p>
                      <p className="mt-2 text-2xl font-semibold tabular-nums">{scoreText(value)}</p>
                      {label === "置信度" && <Progress className="mt-3" value={Number(value)} />}
                    </div>
                  ))}
                </div>

                <section className="rounded-2xl border border-cyan-200 bg-cyan-50 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-cyan-950">商机假设</p>
                      <p className="mt-2 break-words text-sm leading-6 text-cyan-950">{selected.hypothesis || "尚未填写"}</p>
                      <p className="mt-3 text-xs text-cyan-800">场景：{selected.purchase_scenario} · 渠道：{selected.sales_channel}</p>
                    </div>
                    <Badge variant="outline" className="bg-white">由验证项目统一维护</Badge>
                  </div>
                </section>

                <section className="rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">当前阶段结论</p><Badge className="bg-cyan-950">{DECISION_STATUS_LABELS[opportunityDecision.status]}</Badge><Badge variant="outline">证据准备度 {opportunityDecision.readiness}%</Badge></div>
                      <h3 className="mt-2 text-lg font-semibold">{opportunityDecision.headline}</h3>
                      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{opportunityDecision.summary}</p>
                      <p className="mt-3 text-sm font-medium text-cyan-950">下一道闸门：{opportunityDecision.nextGate}</p>
                      <p className="mt-1 flex items-start gap-2 text-sm text-amber-800"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{opportunityDecision.doNotDo}</p>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <Button variant="outline" onClick={() => setDetailTab("trade")}><Database /> 查看贸易数据</Button>
                      <Button onClick={() => setDetailTab("assessment")}><TrendingUp /> 执行验证计划</Button>
                    </div>
                  </div>
                </section>

                <div className="grid gap-3 lg:grid-cols-2">
                  <section className="rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm">
                    <h3 className="flex items-center gap-2 font-semibold text-cyan-950"><Bot className="size-4" /> ChatGPT 自动完成</h3>
                    <div className="mt-3 space-y-2">{CHATGPT_TRADE_WORKFLOW.map((item) => <p key={item} className="text-sm leading-6 text-cyan-950">✓ {item}</p>)}</div>
                    <p className="mt-2 text-sm leading-6 text-cyan-950">✓ 采集真实买家公司品类页、目标渠道价格和官方合规来源，并直接写入证据时间线</p>
                  </section>
                  <section className="rounded-2xl border bg-white p-5 shadow-sm">
                    <h3 className="flex items-center gap-2 font-semibold"><Users className="size-4 text-cyan-800" /> 你只需要处理</h3>
                    <div className="mt-3 space-y-2">{USER_TRADE_RESPONSIBILITIES.map((item) => <p key={item} className="text-sm leading-6 text-muted-foreground">• {item}</p>)}</div>
                    {onOpenSources && <Button variant="outline" size="sm" className="mt-4" onClick={onOpenSources}><Database /> 查看全部数据渠道</Button>}
                  </section>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-2xl border bg-white p-4"><Users className="size-5 text-cyan-800" /><p className="mt-3 font-medium">开发客户</p><p className="mt-1 text-sm text-muted-foreground">画像匹配、真实线索和复购潜力</p></div>
                  <div className="rounded-2xl border bg-white p-4"><PackageSearch className="size-5 text-cyan-800" /><p className="mt-3 font-medium">寻找货源</p><p className="mt-1 text-sm text-muted-foreground">供应、利润、MOQ、合规和物流</p></div>
                  <div className="rounded-2xl border bg-white p-4"><CalendarClock className="size-5 text-cyan-800" /><p className="mt-3 font-medium">持续复核</p><p className="mt-1 text-sm text-muted-foreground">{selected.next_review_at ? `下次 ${selected.next_review_at}` : "尚未设置日期"}</p></div>
                </div>

              </TabsContent>

              <TabsContent value="trade" className="m-0 space-y-5">
                <section className="rounded-2xl border bg-white p-5 shadow-sm">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <h3 className="flex items-center gap-2 text-lg font-semibold"><Database className="size-5 text-cyan-800" /> 本地贸易数据</h3>
                      <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">按商机阶段自动采用三级采集，120 天内优先复用。进出口额是市场需求证据，不等于终端销售额。</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" onClick={() => prepareTradeDataRequest(false, recommendedTradeLevel)} disabled={!selectedCanEdit || tradeBusy || selectedTradeRequest?.status === "pending" || recommendedTradeCovered}><Bot /> {selectedTradeRequest?.status === "pending" ? "补采进行中" : recommendedTradeCovered ? "建议等级已覆盖" : "补足建议等级"}</Button>
                      {selectedTradeRows.length > 0 && <Button variant="ghost" onClick={() => prepareTradeDataRequest(true, recommendedTradeLevel)} disabled={!selectedCanEdit || tradeBusy || selectedTradeRequest?.status === "pending"}>强制更新</Button>}
                    </div>
                  </div>

                  <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
                    <div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-muted-foreground">有效观测点</p><p className="mt-1 font-semibold tabular-nums">{selectedTradeSummary.available}</p><p className="mt-1 text-xs text-muted-foreground">{selectedTradeSummary.sourceRecords} 条原始来源记录</p></div>
                    {[['国家/地区', selectedTradeSummary.countries], ['HS 编码', selectedTradeSummary.commodities], ['覆盖期间', selectedTradeSummary.periodRange]].map(([label, value]) => (
                      <div key={String(label)} className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 break-words font-semibold tabular-nums">{value}</p></div>
                    ))}
                  </div>
                </section>

                <div className="grid gap-3 lg:grid-cols-3">
                  {TRADE_COLLECTION_LEVELS.map((level) => {
                    const rank = { none: 0, baseline: 1, trend: 2, detail: 3 } as const;
                    const covered = rank[selectedTradeCoverage] >= rank[level];
                    const recommended = level === recommendedTradeLevel;
                    const pending = selectedTradeRequest?.status === "pending" && selectedTradeRequest.collection_level === level;
                    const failed = selectedTradeRequest?.status === "failed" && selectedTradeRequest.collection_level === level;
                    const stateLabel = pending ? (covered ? "更新中" : "补采中") : covered ? "已覆盖" : failed ? "补采失败" : recommended ? "当前建议" : "待补";
                    return <button key={level} type="button" className={`rounded-2xl border p-4 text-left shadow-sm transition disabled:cursor-not-allowed disabled:opacity-75 ${pending ? "border-amber-300 bg-amber-50" : recommended ? "border-cyan-300 bg-cyan-50" : "bg-white"}`} onClick={() => prepareTradeDataRequest(false, level)} disabled={!selectedCanEdit || covered || tradeBusy || selectedTradeRequest?.status === "pending"}><div className="flex items-center justify-between gap-2"><p className="font-medium">{TRADE_COLLECTION_POLICIES[level].label}</p><Badge variant={pending ? "secondary" : covered ? "default" : failed ? "destructive" : "outline"} className={pending ? "border border-amber-300 bg-amber-100 text-amber-900" : undefined}>{stateLabel}</Badge></div><p className="mt-2 text-sm leading-6 text-muted-foreground">{TRADE_COLLECTION_POLICIES[level].description}</p></button>;
                  })}
                </div>

                {tradeMessage && <p className="rounded-xl bg-cyan-50 px-4 py-3 text-sm text-cyan-900">{tradeMessage}</p>}
                {selectedTradeRequest?.status === "pending" && <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">“{TRADE_COLLECTION_POLICIES[selectedTradeRequest.collection_level ?? "baseline"].label}”补采正在进行，页面会自动检查写回结果。</p>}
                {selectedTradeRequest?.status === "failed" && <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">上次补采失败：{selectedTradeRequest.error || "未返回错误说明"}</p>}

                {selectedTradeGroups.length ? <section className="space-y-3">
                  <div><h3 className="font-semibold">按 HS 编码与流向查看</h3><p className="mt-1 text-sm text-muted-foreground">默认收起原始观测；需要核验时再展开对应产品与流向。</p></div>
                  {selectedTradeGroups.map((group) => {
                    const countries = new Set(group.rows.map((row) => row.reporter_code)).size;
                    const periods = [...new Set(group.rows.map((row) => row.period))].sort();
                    const periodRange = periods.length === 1 ? periods[0] : `${periods[0]} – ${periods[periods.length - 1]}`;
                    return <details key={group.key} className="group overflow-hidden rounded-2xl border bg-white shadow-sm">
                      <summary className="flex cursor-pointer list-none items-start gap-3 p-4 [&::-webkit-details-marker]:hidden">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">HS {group.commodityCode}</Badge><Badge variant="outline">{group.flow === "import" ? "进口" : "出口"}</Badge></div>
                          <p className="mt-2 break-words text-sm font-medium leading-6">{group.commodityLabel}</p>
                          <p className="mt-1 text-xs text-muted-foreground">{countries} 个国家/地区 · {periodRange} · {group.points.length} 个观测点 · {group.rows.length} 条来源记录</p>
                        </div>
                        <span className="shrink-0 text-sm text-cyan-800 group-open:hidden">展开明细</span>
                        <span className="hidden shrink-0 text-sm text-cyan-800 group-open:inline">收起</span>
                      </summary>
                      <div className="border-t bg-slate-50/60 p-3">
                        <div className="max-h-80 overflow-auto rounded-xl border bg-white">
                          <table className="w-full min-w-[680px] text-left text-sm">
                            <thead className="sticky top-0 bg-slate-50 text-xs text-muted-foreground"><tr><th className="px-3 py-2 font-medium">国家/流向</th><th className="px-3 py-2 font-medium">期间</th><th className="px-3 py-2 font-medium">数值</th><th className="px-3 py-2 font-medium">来源</th></tr></thead>
                            <tbody>{group.points.map((point) => {
                              const row = point.rows[0];
                              return <tr key={point.key} className="border-t align-top"><td className="px-3 py-3">{row.reporter_code} · {row.flow === "import" ? "进口" : "出口"}</td><td className="whitespace-nowrap px-3 py-3 text-muted-foreground">{row.period}</td><td className="px-3 py-3"><div className="space-y-1.5">{point.rows.map((sourceRow) => <div key={sourceRow.id} className="flex flex-wrap items-start gap-x-2"><span className="min-w-28 text-xs text-muted-foreground">{sourceRow.source_name}</span><span className="font-medium tabular-nums">{sourceRow.data_status === "available" && sourceRow.value !== null ? `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(sourceRow.value)} ${sourceRow.unit}` : <span className="font-normal text-muted-foreground">{sourceRow.missing_reason || "数据缺失"}</span>}</span></div>)}</div></td><td className="px-3 py-3"><div className="flex flex-col items-start gap-1">{point.rows.map((sourceRow) => <a key={sourceRow.id} className="whitespace-nowrap text-cyan-800 underline" href={sourceRow.source_url} target="_blank" rel="noreferrer">{sourceRow.source_name}</a>)}</div></td></tr>;
                            })}</tbody>
                          </table>
                        </div>
                      </div>
                    </details>;
                  })}
                </section> : <section className="rounded-2xl border border-dashed bg-white p-8 text-center"><Database className="mx-auto size-8 text-cyan-800" /><p className="mt-3 font-medium">本地尚无对应贸易数据</p><p className="mt-1 text-sm text-muted-foreground">点击“补足建议等级”，结果会保存并供其他商机复用。</p></section>}
              </TabsContent>

              <TabsContent value="assessment" className="m-0 space-y-5">
                <section className="rounded-2xl border border-cyan-200 bg-cyan-50 p-5 shadow-sm">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2"><Badge className="bg-cyan-950">{DECISION_STATUS_LABELS[opportunityDecision.status]}</Badge><Badge variant="outline" className="bg-white">证据准备度 {opportunityDecision.readiness}%</Badge></div>
                      <h3 className="mt-3 text-xl font-semibold text-cyan-950">{opportunityDecision.headline}</h3>
                      <p className="mt-2 max-w-3xl text-sm leading-6 text-cyan-950">{opportunityDecision.summary}</p>
                      <p className="mt-3 text-sm font-medium text-cyan-950">下一道闸门：{opportunityDecision.nextGate}</p>
                      <p className="mt-2 flex items-start gap-2 text-sm text-amber-900"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{opportunityDecision.doNotDo}</p>
                    </div>
                    <Button onClick={() => void requestOpportunityValidation()} disabled={!selectedCanEdit || validationBusy || selectedValidationRequest?.status === "pending"}><Bot /> {selectedValidationRequest?.status === "pending" ? "公开证据采集中" : validationBusy ? "正在发送…" : "AI采集公开证据"}</Button>
                  </div>
                  {validationMessage && <p className="mt-4 rounded-xl border border-cyan-200 bg-white px-4 py-3 text-sm text-cyan-900">{validationMessage}</p>}
                  {selectedValidationRequest?.status === "completed" && selectedValidationRequest.summary && <p className="mt-4 rounded-xl border border-emerald-200 bg-white px-4 py-3 text-sm leading-6 text-emerald-900">最近公开证据结果：{selectedValidationRequest.summary}</p>}
                  {selectedValidationRequest?.status === "failed" && <p className="mt-4 rounded-xl border border-rose-200 bg-white px-4 py-3 text-sm text-rose-900">上次公开证据采集失败：{selectedValidationRequest.error || "未返回错误说明"}</p>}
                </section>

                <section className="rounded-2xl border bg-white p-5 shadow-sm">
                  <div><h3 className="text-lg font-semibold">外贸客户开发验证路径</h3><p className="mt-1 text-sm text-muted-foreground">先发现真实问题，再形成可销售方案；成本与合规过关后才索取 RFQ，首单完成后才评价供应商履约能力。点击卡片进入对应记录。</p></div>
                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    {OPPORTUNITY_VALIDATION_PLAN.map((step, index) => {
                      const done = isOpportunityValidationStepDone(step.key, selectedEvidence);
                      const prerequisiteKey = opportunityValidationPrerequisite(step.key, selectedEvidence);
                      const prerequisite = OPPORTUNITY_VALIDATION_PLAN.find((item) => item.key === prerequisiteKey);
                      const ownerLabel = step.owner === "assistant" ? "ChatGPT 可做" : step.owner === "user" ? "需要你确认" : "共同完成";
                      const actionLabel = prerequisite ? `先完成：${prerequisite.title}` : done ? "查看已入库证据" : step.key === "public_evidence" ? "开始采集公开证据" : "记录本阶段证据";
                      return <button type="button" key={step.key} onClick={() => openValidationStep(step.key)} className={`group rounded-xl border p-4 text-left transition hover:-translate-y-0.5 hover:border-cyan-300 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700 ${done ? "border-emerald-200 bg-emerald-50" : prerequisite ? "bg-slate-50/60" : "bg-slate-50"}`}>
                        <div className="flex items-start gap-3"><div className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${done ? "bg-emerald-600 text-white" : prerequisite ? "bg-slate-300 text-slate-700" : "bg-cyan-950 text-white"}`}>{done ? <CheckCircle2 className="size-4" /> : index + 1}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h4 className="font-medium">{step.title}</h4><Badge variant="outline" className="bg-white">{ownerLabel}</Badge></div><p className="mt-2 text-sm leading-6 text-muted-foreground">{step.description}</p><p className="mt-2 text-xs leading-5 text-cyan-900">通过标准：{step.acceptance}</p><span className={`mt-3 flex items-center gap-1 text-xs font-medium ${prerequisite ? "text-amber-800" : "text-cyan-800"}`}>{actionLabel}<ChevronRight className="size-3.5 transition-transform group-hover:translate-x-0.5" /></span></div></div>
                      </button>;
                    })}
                  </div>
                </section>

                <section className="rounded-2xl border bg-white p-5 shadow-sm">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div><h3 className="text-lg font-semibold">证据评分明细</h3><p className="mt-1 text-sm text-muted-foreground">分数用于解释结论，不要求你先手工填完；AI只采用本地贸易、画像矩阵和已入库证据。</p></div>
                    <Button variant="outline" onClick={generateAssessmentSuggestion}><Bot /> 采用本地证据建议</Button>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-1.5 text-xs"><Badge variant="outline">80–100 强</Badge><Badge variant="outline">60–79 可推进</Badge><Badge variant="outline">40–59 待验证</Badge><Badge variant="outline">0–39 偏弱</Badge><span className="ml-1 self-center text-muted-foreground">点击后仅更新有本地证据支持的项目；仍需你保存快照</span></div>
                  {assessmentSuggestion && <div className="mt-4 rounded-xl border border-cyan-200 bg-cyan-50 p-3 text-sm text-cyan-950"><p className="font-medium">{assessmentSuggestion.summary}</p><p className="mt-1 text-xs text-cyan-800">预评分只是建议；保存评估快照前仍由你最终确认。</p></div>}
                </section>

                <div className="grid gap-4 xl:grid-cols-3">
                  {SIGNAL_GROUPS.map((group) => <section key={group.title} className="rounded-2xl border bg-white p-5 shadow-sm">
                    <h3 className="font-semibold">{group.title}</h3>
                    <p className="mt-1 min-h-10 text-sm leading-5 text-muted-foreground">{group.description}</p>
                    <div className="mt-4 space-y-5">{group.fields.map((field) => {
                      const suggestedValue = automaticSuggestion?.signals[field] ?? null;
                      const suggested = suggestedValue !== null;
                      const known = signals[field] !== null;
                      const conflicts = suggested && known && suggestedValue !== signals[field];
                      return <label key={field} className="block space-y-1.5 text-sm font-medium">
                        <span className="flex items-center justify-between gap-2"><span>{SIGNAL_LABELS[field]}</span><Badge variant="outline" className={suggested ? "border-cyan-200 bg-cyan-50 text-cyan-900" : known ? "" : "border-amber-200 bg-amber-50 text-amber-900"}>{conflicts ? `本地建议 ${suggestedValue}` : suggested ? "已有本地建议" : known ? "人工录入" : "待补证据"}</Badge></span>
                        <div className="relative"><Input className="pr-14 text-base font-semibold tabular-nums" type="number" min="0" max="100" placeholder="未知" value={signals[field] ?? ""} onChange={(event) => setSignals({ ...signals, [field]: event.target.value === "" ? null : Number(event.target.value) })} /><span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-normal text-muted-foreground">/ 100</span></div>
                        <p className="text-xs font-normal leading-5 text-muted-foreground">{automaticSuggestion?.reasons[field] || OPPORTUNITY_SIGNAL_RESPONSIBILITIES[field].assistant}</p>
                        {conflicts && <p className="text-xs font-normal leading-5 text-cyan-800">当前保存值为 {signals[field]}；点击“采用本地证据建议”后更新为 {suggestedValue}，不会自动保存。</p>}
                        {!known && <p className="text-xs font-normal leading-5 text-amber-800">需要你：{OPPORTUNITY_SIGNAL_RESPONSIBILITIES[field].user}</p>}
                      </label>;
                    })}</div>
                  </section>)}
                </div>

                <section className="rounded-2xl border bg-white p-5 shadow-sm">
                  <label className="text-sm font-medium">本轮判断与下一步
                    <Textarea className="mt-2 min-h-28" value={assessmentRationale} onChange={(event) => setAssessmentRationale(event.target.value)} placeholder="记录本轮判断、矛盾证据和下一步验证方式" />
                  </label>
                  <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs text-muted-foreground">每次保存都会新增评估快照，不覆盖历史版本。</p>
                    <Button onClick={() => void saveAssessment()} disabled={!selectedCanEdit || busy}><TrendingUp /> 保存评估快照</Button>
                  </div>
                </section>
              </TabsContent>

              <TabsContent value="evidence" className="m-0 space-y-5">
                {activeValidationStep && <section className="rounded-2xl border border-cyan-200 bg-cyan-50 p-5 shadow-sm">
                  <div className="flex items-start gap-3"><div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-cyan-950 text-sm font-semibold text-white">{OPPORTUNITY_VALIDATION_PLAN.findIndex((step) => step.key === activeValidationStep.key) + 1}</div><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold text-cyan-950">正在记录：{activeValidationStep.title}</h3><Badge variant="outline" className="bg-white">{activeValidationStep.owner === "assistant" ? "ChatGPT 可做" : activeValidationStep.owner === "user" ? "需要你确认" : "共同完成"}</Badge></div><p className="mt-2 text-sm leading-6 text-cyan-950">{activeValidationStep.description}</p><p className="mt-2 text-xs leading-5 text-cyan-800">阶段通过标准：{activeValidationStep.acceptance}</p></div></div>
                </section>}
                <section className="rounded-2xl border bg-white p-5 shadow-sm">
                  <div><h3 className="text-lg font-semibold">新增证据</h3><p className="mt-1 text-sm text-muted-foreground">外部证据保留可核验链接；Odoo 内部证据可以只记录业务编号和结论。</p></div>
                  <div className="mt-5 grid gap-4 sm:grid-cols-2">
                    <label className="space-y-1.5 text-sm font-medium">证据类型<Select value={evidenceType} onValueChange={setEvidenceType}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="demand">市场需求</SelectItem><SelectItem value="buyer_discovery">客户发现访谈</SelectItem><SelectItem value="buyer">真实询盘/客户</SelectItem><SelectItem value="channel">销售渠道</SelectItem><SelectItem value="competition">竞争价格</SelectItem><SelectItem value="product_matrix">产品与报价矩阵</SelectItem><SelectItem value="supply">供应与报价</SelectItem><SelectItem value="compliance">合规物流</SelectItem><SelectItem value="fulfillment">首单履约结果</SelectItem><SelectItem value="internal">Odoo内部结果</SelectItem></SelectContent></Select></label>
                    <label className="space-y-1.5 text-sm font-medium">可信等级<Select value={sourceGrade} onValueChange={setSourceGrade}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="official">官方数据</SelectItem><SelectItem value="verified_buyer">已核实买家</SelectItem><SelectItem value="supplier_quote">供应商报价</SelectItem><SelectItem value="internal_odoo">Odoo内部记录</SelectItem><SelectItem value="marketplace">平台信号</SelectItem><SelectItem value="other">其他来源</SelectItem></SelectContent></Select></label>
                    <label className="space-y-1.5 text-sm font-medium">证据标题<Input value={evidenceTitle} onChange={(event) => setEvidenceTitle(event.target.value)} placeholder="例如：英国分销商公开采购目录" /></label>
                    <label className="space-y-1.5 text-sm font-medium">统计周期<Input value={evidencePeriod} onChange={(event) => setEvidencePeriod(event.target.value)} placeholder="例如 2025 或 2025-Q1" /></label>
                    <label className="space-y-1.5 text-sm font-medium sm:col-span-2">来源链接<Input type="url" value={evidenceUrl} onChange={(event) => setEvidenceUrl(event.target.value)} placeholder="https://... 可核验来源；Odoo 内部证据可留空" /></label>
                    <label className="space-y-1.5 text-sm font-medium">指标名称<Input value={metricName} onChange={(event) => setMetricName(event.target.value)} placeholder="例如 import_value_usd" /></label>
                    <label className="space-y-1.5 text-sm font-medium">指标值<Input value={metricValue} onChange={(event) => setMetricValue(event.target.value)} placeholder="填写与来源一致的原始值" /></label>
                    <label className="space-y-1.5 text-sm font-medium sm:col-span-2">证据摘要与限制<Textarea className="min-h-28" value={evidenceNote} onChange={(event) => setEvidenceNote(event.target.value)} placeholder="记录证据摘要、统计口径、未知项和使用限制" /></label>
                  </div>
                  <div className="mt-4 flex justify-end"><Button onClick={() => void saveEvidence()} disabled={!selectedCanEdit || busy || !evidenceTitle}><FileCheck2 /> 保存证据</Button></div>
                </section>

                <section className="rounded-2xl border bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between gap-3"><div><h3 className="font-semibold">证据时间线</h3><p className="mt-1 text-sm text-muted-foreground">共享档案可跨项目复用，客户反馈和内部评估只归属本项目；全部按版本累积。</p></div><Badge variant="outline">{selectedEvidence.length} 条</Badge></div>
                  {selectedEvidence.length ? <div className="mt-4 space-y-3">{selectedEvidence.map((item) => <article key={item.id} className="rounded-xl border p-4">
                    <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{EVIDENCE_TYPE_LABELS[item.evidence_type] ?? item.evidence_type}</Badge><Badge variant="outline">{SOURCE_GRADE_LABELS[item.source_grade] ?? item.source_grade}</Badge><Badge variant="secondary">{item.evidence_scope === "shared" ? "共享档案" : "本项目"}</Badge><span className="ml-auto text-xs text-muted-foreground">{formatDate(item.captured_at)}</span></div>
                    <p className="mt-3 break-words font-medium">{item.title}</p>
                    {item.note && <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">{item.note}</p>}
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">{item.period && <span>{item.period}</span>}{Object.entries(item.metrics).map(([key, value]) => <span key={key}>{key}: {String(value)}</span>)}{item.source_url && <a className="text-cyan-800 underline" href={item.source_url} target="_blank" rel="noreferrer">查看来源</a>}</div>
                  </article>)}</div> : <p className="mt-4 rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">暂无证据。建议先补一条官方贸易数据和一条真实买家证据。</p>}
                </section>
              </TabsContent>
            </div>
          </Tabs>}
        </SheetContent>
      </Sheet>
    </div>
  );
}
