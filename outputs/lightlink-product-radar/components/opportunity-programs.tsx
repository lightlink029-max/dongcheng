"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Ban, CheckCircle2, ChevronLeft, ChevronRight, ClipboardList, Plus, Search, Settings2, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

type Region = { code: string; name: string };
type Persona = { code: string; name: string; purchase_scenarios: string[]; sales_channels: string[] };
type Family = { code: string; name: string; track_code: string; track_name: string };
type Matrix = {
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

export type OpportunityProgramSeed = {
  personaCode: string;
  matrixIds?: string[];
  regionCode?: string;
  purchaseScenario?: string;
  salesChannel?: string;
  hypothesis?: string;
};

export type OpportunityProgram = {
  id: string;
  title: string;
  persona_code: string;
  persona_name: string;
  persona_version: number;
  region_code: string;
  region_name: string;
  purchase_scenario: string;
  sales_channel: string;
  hypothesis: string;
  project_scope_key: string;
  cycle_number: number;
  parent_program_id: string;
  max_family_count: number;
  status: string;
  current_round_number: number;
  customer_owner: string;
  supply_owner: string;
  next_review_at: string;
  next_action: string;
  active: boolean;
  version: number;
  updated_at: string;
  void_reason_code?: string;
  void_reason_note?: string;
  voided_at?: string | null;
  replaced_by_program_id?: string;
  current_phase?: string;
  family_count?: number;
  qualified_feedback_count?: number;
};

type OpportunityProgramPage = {
  items: OpportunityProgram[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

type OpportunityProgramDetail = {
  program: OpportunityProgram;
  rounds: OpportunityRound[];
  roundFamilies: OpportunityRoundFamily[];
  customerFeedback: OpportunityCustomerFeedback[];
};

export type OpportunityRound = {
  id: string;
  program_id: string;
  round_number: number;
  phase: "discovery" | "commercial" | "pilot";
  status: string;
  goal: string;
  decision: string;
  decision_note: string;
  due_at: string;
  started_at: string;
  completed_at: string | null;
};

export type OpportunityRoundFamily = {
  id: string;
  round_id: string;
  opportunity_id: string;
  matrix_id: string;
  matrix_role: string;
  matrix_score: number;
  matrix_evidence_status: string;
  matrix_rationale: string;
  product_family_code: string;
  product_family_name: string;
  track_code: string;
  track_name: string;
  priority_rank: number;
  status: "candidate" | "continue" | "adjust" | "pass";
  rationale: string;
};

export type OpportunityCustomerFeedback = {
  id: string;
  program_id: string;
  round_id: string;
  product_family_code: string;
  company_name: string;
  contact_role: string;
  feedback_status: string;
  scenario: string;
  current_solution: string;
  pain_points: string;
  must_have_specs: string;
  buying_trigger: string;
  purchase_cycle: string;
  price_behavior: string;
  rejection_reason: string;
  source_url: string;
  note: string;
  created_at: string;
};

export type OpportunityProgramData = {
  programs: OpportunityProgram[];
  rounds: OpportunityRound[];
  roundFamilies: OpportunityRoundFamily[];
  customerFeedback: OpportunityCustomerFeedback[];
  taxonomy: {
    regions: Region[];
    personaCategories: Persona[];
    productFamilies: Family[];
    personaMatrix: Matrix[];
  };
};

type ProgramDraft = {
  title: string;
  personaCode: string;
  regionCode: string;
  purchaseScenario: string;
  salesChannel: string;
  hypothesis: string;
  maxFamilyCount: number;
  matrixIds: string[];
  customerOwner: string;
  supplyOwner: string;
  nextReviewAt: string;
};

type FeedbackDraft = {
  productFamilyCode: string;
  companyName: string;
  contactRole: string;
  feedbackStatus: string;
  scenario: string;
  currentSolution: string;
  painPoints: string;
  mustHaveSpecs: string;
  buyingTrigger: string;
  purchaseCycle: string;
  priceBehavior: string;
  rejectionReason: string;
  sourceUrl: string;
  note: string;
};

const emptyProgramDraft: ProgramDraft = {
  title: "",
  personaCode: "",
  regionCode: "GLOBAL",
  purchaseScenario: "",
  salesChannel: "",
  hypothesis: "",
  maxFamilyCount: 5,
  matrixIds: [],
  customerOwner: "",
  supplyOwner: "",
  nextReviewAt: "",
};

const emptyFeedbackDraft: FeedbackDraft = {
  productFamilyCode: "",
  companyName: "",
  contactRole: "",
  feedbackStatus: "contacted",
  scenario: "",
  currentSolution: "",
  painPoints: "",
  mustHaveSpecs: "",
  buyingTrigger: "",
  purchaseCycle: "",
  priceBehavior: "",
  rejectionReason: "",
  sourceUrl: "",
  note: "",
};

const PHASE_LABELS: Record<string, string> = { discovery: "第一轮·价值发现", commercial: "第二轮·商业验证", pilot: "第三轮·首单履约" };
const PROGRAM_STATUS_LABELS: Record<string, string> = { round_active: "验证中", review_due: "待复盘", hold: "暂停", scaling: "进入常态开发", passed: "已Pass", archived: "已归档", voided: "已作废" };
const FAMILY_STATUS_LABELS: Record<string, string> = { candidate: "待验证", continue: "继续", adjust: "调整", pass: "Pass" };
const FEEDBACK_STATUS_LABELS: Record<string, string> = {
  contacted: "已联系", replied: "已回复", qualified: "有效访谈", no_need: "无需求", wrong_contact: "联系人错误",
  follow_up: "待跟进", rfq: "明确RFQ", sample: "样品请求", trial: "试单请求",
};
const DECISION_LABELS: Record<string, string> = { continue: "继续下一阶段", adjust: "调整后再验证", extend: "补充本轮", hold: "暂停观察", pass: "Pass归档" };
const MATRIX_ROLE_LABELS: Record<string, string> = { core: "核心常采", cross_sell: "跨品类加购", seasonal: "季节采购", test: "小单测试" };
const MATRIX_EVIDENCE_LABELS: Record<string, string> = { hypothesis: "待核实", partial: "部分证据", validated: "已验证" };
const VOID_REASON_LABELS: Record<string, string> = {
  duplicate: "重复项目", test_or_mistake: "测试或误建", wrong_scope: "画像/市场/场景错误",
  merged: "已合并到其他项目", invalid_data: "基础数据错误", other: "其他",
};

function normalizedScopePart(value: string) {
  return value.normalize("NFKC").trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

function programScopeKey(personaCode: string, regionCode: string, purchaseScenario: string, salesChannel: string) {
  return [personaCode, regionCode, purchaseScenario, salesChannel].map(normalizedScopePart).join("|");
}

async function postProgramAction(body: Record<string, unknown>) {
  const response = await fetch("/api/radar", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const result = await response.json() as OpportunityProgramData & { error?: string };
  if (!response.ok) throw new Error(result.error ?? "操作失败");
  return result;
}

function dateText(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("zh-CN");
}

export function OpportunityPrograms({ data, seed, onSeedConsumed, onOpenGlobalPersonas, onDataChange, onOpenOpportunity }: {
  data: OpportunityProgramData;
  seed?: OpportunityProgramSeed | null;
  onSeedConsumed?: () => void;
  onOpenGlobalPersonas: () => void;
  onDataChange: (data: OpportunityProgramData) => void;
  onOpenOpportunity: (opportunityId: string) => void;
}) {
  const consumedSeed = useRef<OpportunityProgramSeed | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState<ProgramDraft>(emptyProgramDraft);
  const [selectedProgramId, setSelectedProgramId] = useState<string | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackDraft>(emptyFeedbackDraft);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [decision, setDecision] = useState("continue");
  const [decisionNote, setDecisionNote] = useState("");
  const [decisionFamilyCodes, setDecisionFamilyCodes] = useState<string[]>([]);
  const [decisionDueAt, setDecisionDueAt] = useState("");
  const [decisionNextGoal, setDecisionNextGoal] = useState("");
  const [decisionNextAction, setDecisionNextAction] = useState("");
  const [confirmedByBoth, setConfirmedByBoth] = useState(false);
  const [familyDecisionOpen, setFamilyDecisionOpen] = useState(false);
  const [familyDecisionTarget, setFamilyDecisionTarget] = useState<OpportunityRoundFamily | null>(null);
  const [familyDecisionStatus, setFamilyDecisionStatus] = useState<OpportunityRoundFamily["status"]>("continue");
  const [familyDecisionRationale, setFamilyDecisionRationale] = useState("");
  const [familyDecisionConfirmed, setFamilyDecisionConfirmed] = useState(false);
  const [settingsMax, setSettingsMax] = useState(5);
  const [settingsCustomerOwner, setSettingsCustomerOwner] = useState("");
  const [settingsSupplyOwner, setSettingsSupplyOwner] = useState("");
  const [settingsNextReview, setSettingsNextReview] = useState("");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [statusFilter, setStatusFilter] = useState("active");
  const [phaseFilter, setPhaseFilter] = useState("all");
  const [regionFilter, setRegionFilter] = useState("all");
  const [personaFilter, setPersonaFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [dueFilter, setDueFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [pageRevision, setPageRevision] = useState(0);
  const [programPage, setProgramPage] = useState<OpportunityProgramPage>({
    items: data.programs.filter((item) => item.active && item.status !== "voided").slice(0, 10),
    page: 1, pageSize: 10,
    total: data.programs.filter((item) => item.active && item.status !== "voided").length,
    totalPages: Math.max(1, Math.ceil(data.programs.filter((item) => item.active && item.status !== "voided").length / 10)),
  });
  const [programDetail, setProgramDetail] = useState<OpportunityProgramDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidProgram, setVoidProgram] = useState<OpportunityProgram | null>(null);
  const [voidReasonCode, setVoidReasonCode] = useState("test_or_mistake");
  const [voidReasonNote, setVoidReasonNote] = useState("");
  const [replacementProgramId, setReplacementProgramId] = useState("");
  const [voidConfirmed, setVoidConfirmed] = useState(false);
  const [historyPhase, setHistoryPhase] = useState("all");
  const [historyStatus, setHistoryStatus] = useState("all");
  const [historyPage, setHistoryPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const selectedProgram = (programDetail?.program.id === selectedProgramId ? programDetail.program : null)
    ?? data.programs.find((item) => item.id === selectedProgramId)
    ?? programPage.items.find((item) => item.id === selectedProgramId) ?? null;
  const detailRounds = programDetail?.program.id === selectedProgramId ? programDetail.rounds : data.rounds;
  const detailRoundFamilies = programDetail?.program.id === selectedProgramId ? programDetail.roundFamilies : data.roundFamilies;
  const detailFeedback = programDetail?.program.id === selectedProgramId ? programDetail.customerFeedback : data.customerFeedback;
  const programRounds = selectedProgram ? detailRounds.filter((item) => item.program_id === selectedProgram.id).sort((a, b) => b.round_number - a.round_number) : [];
  const currentRound = selectedProgram ? programRounds.find((item) => item.round_number === selectedProgram.current_round_number) ?? null : null;
  const currentFamilies = currentRound ? detailRoundFamilies.filter((item) => item.round_id === currentRound.id).sort((a, b) => a.priority_rank - b.priority_rank) : [];
  const currentFeedback = currentRound ? detailFeedback.filter((item) => item.round_id === currentRound.id) : [];
  const qualifiedFeedback = currentFeedback.filter((item) => ["qualified", "rfq", "sample", "trial"].includes(item.feedback_status));
  const canEditCurrentRound = Boolean(selectedProgram?.active
    && selectedProgram.status !== "voided"
    && currentRound
    && ["active", "hold"].includes(currentRound.status));
  const filteredHistory = programRounds.filter((round) => (historyPhase === "all" || round.phase === historyPhase)
    && (historyStatus === "all" || round.status === historyStatus));
  const historyPageSize = 5;
  const historyTotalPages = Math.max(1, Math.ceil(filteredHistory.length / historyPageSize));
  const visibleHistory = filteredHistory.slice((Math.min(historyPage, historyTotalPages) - 1) * historyPageSize,
    Math.min(historyPage, historyTotalPages) * historyPageSize);

  const selectedPersona = data.taxonomy.personaCategories.find((item) => item.code === draft.personaCode);
  const rankedMatrixOptions = useMemo(() => {
    const candidates = data.taxonomy.personaMatrix
      .filter((item) => item.persona_code === draft.personaCode
        && item.product_family_code
        && (item.region_code === draft.regionCode || item.region_code === "GLOBAL"))
      .map((matrix) => ({ matrix, family: data.taxonomy.productFamilies.find((family) => family.code === matrix.product_family_code) }))
      .filter((item): item is { matrix: Matrix; family: Family } => Boolean(item.family));
    const bestRelationByFamily = new Map<string, { matrix: Matrix; family: Family }>();
    for (const candidate of candidates) {
      const current = bestRelationByFamily.get(candidate.family.code);
      const candidateIsMarketSpecific = candidate.matrix.region_code === draft.regionCode;
      const currentIsMarketSpecific = current?.matrix.region_code === draft.regionCode;
      if (!current
        || (candidateIsMarketSpecific && !currentIsMarketSpecific)
        || (candidateIsMarketSpecific === currentIsMarketSpecific
          && candidate.matrix.relevance_score > current.matrix.relevance_score)) {
        bestRelationByFamily.set(candidate.family.code, candidate);
      }
    }
    return [...bestRelationByFamily.values()]
      .sort((left, right) => right.matrix.relevance_score - left.matrix.relevance_score
        || left.family.name.localeCompare(right.family.name, "zh-CN"));
  }, [data.taxonomy.personaMatrix, data.taxonomy.productFamilies, draft.personaCode, draft.regionCode]);
  const draftScopeKey = programScopeKey(draft.personaCode, draft.regionCode, draft.purchaseScenario, draft.salesChannel);
  const duplicateProgram = data.programs.find((item) => item.active && item.status !== "voided"
    && (item.project_scope_key || programScopeKey(item.persona_code, item.region_code, item.purchase_scenario, item.sales_channel)) === draftScopeKey) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      view: "opportunity_programs", page: String(page), pageSize: String(pageSize), status: statusFilter,
      phase: phaseFilter, region: regionFilter, persona: personaFilter, due: dueFilter,
    });
    if (deferredSearch.trim()) params.set("q", deferredSearch.trim());
    if (ownerFilter.trim()) params.set("owner", ownerFilter.trim());
    void fetch(`/api/radar?${params.toString()}`, { signal: controller.signal })
      .then(async (response) => {
        const result = await response.json() as OpportunityProgramPage & { error?: string };
        if (!response.ok) throw new Error(result.error ?? "读取验证项目失败");
        setProgramPage(result);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setMessage(error instanceof Error ? error.message : "读取验证项目失败");
      });
    return () => controller.abort();
  }, [deferredSearch, dueFilter, ownerFilter, page, pageRevision, pageSize, personaFilter, phaseFilter, regionFilter, statusFilter]);

  useEffect(() => {
    if (!seed || consumedSeed.current === seed) return;
    const persona = data.taxonomy.personaCategories.find((item) => item.code === seed.personaCode);
    const seededMatrices = data.taxonomy.personaMatrix.filter((item) => seed.matrixIds?.includes(item.id));
    const regionCode = seed.regionCode
      || seededMatrices.find((item) => item.region_code !== "GLOBAL")?.region_code
      || "GLOBAL";
    const timeoutId = window.setTimeout(() => {
      consumedSeed.current = seed;
      if (!persona) {
        setMessage("所选全球画像已停用或不存在，请重新选择。");
        onSeedConsumed?.();
        return;
      }
      const applicableIds = seededMatrices
        .filter((item) => item.persona_code === persona.code && item.product_family_code
          && (item.region_code === regionCode || item.region_code === "GLOBAL"))
        .map((item) => item.id)
        .slice(0, emptyProgramDraft.maxFamilyCount);
      const purchaseScenario = seed.purchaseScenario
        || seededMatrices.flatMap((item) => item.sales_scenarios)[0]
        || persona.purchase_scenarios[0]
        || "";
      setDraft({
        ...emptyProgramDraft,
        personaCode: persona.code,
        regionCode,
        purchaseScenario,
        salesChannel: seed.salesChannel || persona.sales_channels[0] || "",
        hypothesis: seed.hypothesis || "",
        matrixIds: applicableIds,
      });
      setMessage("");
      setCreateOpen(true);
      onSeedConsumed?.();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [data.taxonomy.personaCategories, data.taxonomy.personaMatrix, onSeedConsumed, seed]);

  const toggleDraftMatrix = (id: string) => {
    setDraft((current) => {
      if (current.matrixIds.includes(id)) return { ...current, matrixIds: current.matrixIds.filter((item) => item !== id) };
      if (current.matrixIds.length >= current.maxFamilyCount) return current;
      return { ...current, matrixIds: [...current.matrixIds, id] };
    });
  };

  const loadProgramDetail = async (programId: string, silent = false) => {
    if (!silent) setDetailLoading(true);
    try {
      const response = await fetch(`/api/radar?view=opportunity_program_detail&programId=${encodeURIComponent(programId)}`);
      const result = await response.json() as OpportunityProgramDetail & { error?: string };
      if (!response.ok) throw new Error(result.error ?? "读取项目详情失败");
      setProgramDetail(result);
      return result;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取项目详情失败");
      return null;
    } finally {
      if (!silent) setDetailLoading(false);
    }
  };

  const applyProgramResult = (result: OpportunityProgramData) => {
    onDataChange(result);
    setPageRevision((current) => current + 1);
    if (selectedProgramId) void loadProgramDetail(selectedProgramId, true);
  };

  const createProgram = async () => {
    setBusy(true);
    setMessage("");
    try {
      const result = await postProgramAction({ action: "create_opportunity_program", ...draft });
      applyProgramResult(result);
      setCreateOpen(false);
      setMessage("验证项目已创建，第一轮已经开始。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "创建验证项目失败");
    } finally {
      setBusy(false);
    }
  };

  const reuseExistingProgram = async () => {
    if (!duplicateProgram) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await postProgramAction({
        action: "add_opportunity_program_matrices", programId: duplicateProgram.id, matrixIds: draft.matrixIds,
      });
      applyProgramResult(result);
      setCreateOpen(false);
      await openProgram(result.programs.find((item) => item.id === duplicateProgram.id) ?? duplicateProgram);
      setMessage("已复用原项目；新选择且尚未存在的产品矩阵已加入当前轮次，共享证据会自动复用。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "复用验证项目失败");
    } finally {
      setBusy(false);
    }
  };

  const openProgram = async (program: OpportunityProgram) => {
    setSelectedProgramId(program.id);
    setProgramDetail(null);
    setSettingsMax(program.max_family_count);
    setSettingsCustomerOwner(program.customer_owner);
    setSettingsSupplyOwner(program.supply_owner);
    setSettingsNextReview(program.next_review_at);
    setHistoryPhase("all");
    setHistoryStatus("all");
    setHistoryPage(1);
    setMessage("");
    const detail = await loadProgramDetail(program.id);
    if (detail) {
      setSettingsMax(detail.program.max_family_count);
      setSettingsCustomerOwner(detail.program.customer_owner);
      setSettingsSupplyOwner(detail.program.supply_owner);
      setSettingsNextReview(detail.program.next_review_at);
    }
  };

  const startVoid = (program: OpportunityProgram) => {
    setVoidProgram(program);
    setVoidReasonCode("test_or_mistake");
    setVoidReasonNote("");
    setReplacementProgramId("");
    setVoidConfirmed(false);
    setVoidOpen(true);
  };

  const submitVoid = async () => {
    if (!voidProgram) return;
    setBusy(true);
    try {
      const result = await postProgramAction({
        action: "void_opportunity_program", programId: voidProgram.id, version: voidProgram.version,
        reasonCode: voidReasonCode, reasonNote: voidReasonNote, replacedByProgramId: replacementProgramId,
      });
      applyProgramResult(result);
      setVoidOpen(false);
      if (selectedProgramId === voidProgram.id) setSelectedProgramId(null);
      setMessage("项目已作废并退出活动列表；产品家族档案、共享证据和历史记录均已保留。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "作废验证项目失败");
    } finally {
      setBusy(false);
    }
  };

  const saveSettings = async () => {
    if (!selectedProgram) return;
    setBusy(true);
    try {
      const result = await postProgramAction({
        action: "update_opportunity_program_settings", programId: selectedProgram.id, title: selectedProgram.title,
        maxFamilyCount: settingsMax, customerOwner: settingsCustomerOwner, supplyOwner: settingsSupplyOwner,
        nextReviewAt: settingsNextReview, nextAction: selectedProgram.next_action,
      });
      applyProgramResult(result);
      setMessage("项目设置已保存。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存项目设置失败");
    } finally {
      setBusy(false);
    }
  };

  const startFamilyDecision = (family: OpportunityRoundFamily, status: OpportunityRoundFamily["status"]) => {
    if (!canEditCurrentRound || status === "candidate") return;
    setFamilyDecisionTarget(family);
    setFamilyDecisionStatus(status);
    setFamilyDecisionRationale(family.rationale ?? "");
    setFamilyDecisionConfirmed(false);
    setFamilyDecisionOpen(true);
  };

  const changeFamilyStatus = async () => {
    if (!familyDecisionTarget || !canEditCurrentRound || familyDecisionStatus === "candidate") return;
    setBusy(true);
    try {
      applyProgramResult(await postProgramAction({
        action: "update_opportunity_round_family",
        familyId: familyDecisionTarget.id,
        status: familyDecisionStatus,
        rationale: familyDecisionRationale.trim(),
      }));
      setFamilyDecisionOpen(false);
      setMessage(`“${familyDecisionTarget.product_family_name}”已标记为${FAMILY_STATUS_LABELS[familyDecisionStatus]}；共享证据与历史记录均已保留。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "更新产品家族结论失败");
    } finally {
      setBusy(false);
    }
  };

  const startFeedback = () => {
    setFeedback({ ...emptyFeedbackDraft, productFamilyCode: currentFamilies[0]?.product_family_code ?? "" });
    setFeedbackOpen(true);
  };

  const saveFeedback = async () => {
    if (!selectedProgram || !currentRound) return;
    setBusy(true);
    try {
      applyProgramResult(await postProgramAction({ action: "add_opportunity_customer_feedback", programId: selectedProgram.id, roundId: currentRound.id, ...feedback }));
      setFeedbackOpen(false);
      setMessage("客户反馈已保存，并已按可信等级写入对应产品家族证据。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存客户反馈失败");
    } finally {
      setBusy(false);
    }
  };

  const startDecision = () => {
    setDecision("continue");
    setDecisionNote("");
    setDecisionFamilyCodes(currentFamilies.filter((item) => item.status !== "pass").map((item) => item.product_family_code));
    setDecisionDueAt(selectedProgram?.next_review_at ?? "");
    setDecisionNextGoal("");
    setDecisionNextAction("");
    setConfirmedByBoth(false);
    setDecisionOpen(true);
  };

  const toggleDecisionFamily = (code: string) => {
    setDecisionFamilyCodes((current) => current.includes(code) ? current.filter((item) => item !== code)
      : current.length >= (selectedProgram?.max_family_count ?? 5) ? current : [...current, code]);
  };

  const submitDecision = async () => {
    if (!selectedProgram) return;
    setBusy(true);
    try {
      const result = await postProgramAction({
        action: "decide_opportunity_round", programId: selectedProgram.id, decision, note: decisionNote,
        familyCodes: decisionFamilyCodes, dueAt: decisionDueAt, nextGoal: decisionNextGoal,
        nextAction: decisionNextAction, confirmedByBoth,
      });
      applyProgramResult(result);
      setDecisionOpen(false);
      setMessage(decision === "pass" ? "项目已Pass并保留全部历史。" : "本轮决策已保存。");
      if (decision === "pass") setSelectedProgramId(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存轮次决策失败");
    } finally {
      setBusy(false);
    }
  };

  return <section className="space-y-4">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div><h3 className="text-xl font-semibold">验证项目与轮次</h3><p className="mt-1 text-sm text-muted-foreground">每轮用真实证据决定继续、调整、补充或Pass；候选产品家族上限可配置，默认5个。</p></div>
      <Button onClick={onOpenGlobalPersonas}><Plus /> 从全球画像建立</Button>
    </div>
    {message && <p className="rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-900">{message}</p>}
    <section className="rounded-2xl border bg-white p-4 shadow-sm">
      <div className="grid gap-3 lg:grid-cols-[minmax(260px,2fr)_repeat(5,minmax(130px,1fr))]">
        <label className="relative"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input className="pl-9" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="搜索项目、画像、产品家族或场景" /></label>
        <Select value={statusFilter} onValueChange={(value) => { setStatusFilter(value); setPage(1); }}><SelectTrigger><SelectValue placeholder="项目状态" /></SelectTrigger><SelectContent><SelectItem value="active">活动项目</SelectItem><SelectItem value="round_active">验证中</SelectItem><SelectItem value="review_due">待复盘</SelectItem><SelectItem value="hold">暂停</SelectItem><SelectItem value="scaling">常态开发</SelectItem><SelectItem value="passed">已Pass</SelectItem><SelectItem value="voided">已作废</SelectItem><SelectItem value="all">全部状态</SelectItem></SelectContent></Select>
        <Select value={phaseFilter} onValueChange={(value) => { setPhaseFilter(value); setPage(1); }}><SelectTrigger><SelectValue placeholder="阶段" /></SelectTrigger><SelectContent><SelectItem value="all">全部阶段</SelectItem><SelectItem value="discovery">第一轮·价值发现</SelectItem><SelectItem value="commercial">第二轮·商业验证</SelectItem><SelectItem value="pilot">第三轮·首单履约</SelectItem></SelectContent></Select>
        <Select value={regionFilter} onValueChange={(value) => { setRegionFilter(value); setPage(1); }}><SelectTrigger><SelectValue placeholder="市场" /></SelectTrigger><SelectContent><SelectItem value="all">全部市场</SelectItem>{data.taxonomy.regions.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select>
        <Select value={personaFilter} onValueChange={(value) => { setPersonaFilter(value); setPage(1); }}><SelectTrigger><SelectValue placeholder="画像" /></SelectTrigger><SelectContent><SelectItem value="all">全部画像</SelectItem>{data.taxonomy.personaCategories.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select>
        <Select value={dueFilter} onValueChange={(value) => { setDueFilter(value); setPage(1); }}><SelectTrigger><SelectValue placeholder="复核日期" /></SelectTrigger><SelectContent><SelectItem value="all">全部复核日期</SelectItem><SelectItem value="overdue">已逾期</SelectItem><SelectItem value="next_7_days">7天内</SelectItem><SelectItem value="unset">未设置</SelectItem></SelectContent></Select>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3"><Input className="max-w-xs" value={ownerFilter} onChange={(event) => { setOwnerFilter(event.target.value); setPage(1); }} placeholder="按负责人筛选" /><span className="text-sm text-muted-foreground">找到 {programPage.total} 个项目</span><div className="ml-auto flex items-center gap-2"><Select value={String(pageSize)} onValueChange={(value) => { setPageSize(Number(value)); setPage(1); }}><SelectTrigger className="w-28"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="10">每页 10</SelectItem><SelectItem value="20">每页 20</SelectItem><SelectItem value="50">每页 50</SelectItem></SelectContent></Select><Button size="icon" variant="outline" disabled={programPage.page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}><ChevronLeft /><span className="sr-only">上一页</span></Button><span className="min-w-16 text-center text-sm">{programPage.page}/{programPage.totalPages}</span><Button size="icon" variant="outline" disabled={programPage.page >= programPage.totalPages} onClick={() => setPage((current) => current + 1)}><ChevronRight /><span className="sr-only">下一页</span></Button></div></div>
    </section>
    {programPage.items.length ? <div className="grid gap-4 xl:grid-cols-2">{programPage.items.map((program) => {
      const round = data.rounds.find((item) => item.program_id === program.id && item.round_number === program.current_round_number);
      const familyCount = program.family_count ?? (round ? data.roundFamilies.filter((item) => item.round_id === round.id).length : 0);
      const qualified = program.qualified_feedback_count ?? 0;
      const phase = program.current_phase || round?.phase;
      return <article key={program.id} className="rounded-2xl border bg-white p-5 shadow-sm transition hover:border-cyan-300 hover:shadow-md">
        <div className="flex items-start justify-between gap-4"><div><h4 className="font-semibold">{program.title}</h4><p className="mt-1 text-sm text-muted-foreground">{program.region_name} · {program.persona_name} · {program.purchase_scenario}</p></div><Badge className={program.status === "voided" ? "bg-slate-600" : "bg-cyan-950"}>{PROGRAM_STATUS_LABELS[program.status] ?? program.status}</Badge></div>
        <div className="mt-4 flex flex-wrap gap-2"><Badge variant="outline">{phase ? PHASE_LABELS[phase] : `第${program.current_round_number}轮`}</Badge><Badge variant="outline">产品家族 {familyCount}/{program.max_family_count}</Badge><Badge variant="outline">有效反馈 {qualified}</Badge>{program.cycle_number > 1 && <Badge variant="secondary">第 {program.cycle_number} 周期</Badge>}</div>
        <p className="mt-4 line-clamp-2 text-sm leading-6">{program.status === "voided" ? `作废原因：${VOID_REASON_LABELS[program.void_reason_code ?? ""] ?? program.void_reason_code ?? "—"}` : `下一步：${program.next_action || "补充本轮证据并复盘"}`}</p>
        <div className="mt-4 flex flex-wrap items-center gap-2"><span className="mr-auto text-xs text-muted-foreground">复核 {dateText(program.next_review_at)}</span>{program.status !== "voided" && <Button size="sm" variant="outline" onClick={() => startVoid(program)}><Ban /> 作废</Button>}<Button size="sm" onClick={() => void openProgram(program)}>进入项目<ArrowRight /></Button></div>
      </article>;
    })}</div> : <div className="rounded-2xl border border-dashed bg-white p-8 text-center"><ClipboardList className="mx-auto size-8 text-cyan-800" /><p className="mt-3 font-medium">{programPage.total ? "没有符合筛选条件的项目" : "还没有验证项目"}</p><p className="mt-1 text-sm text-muted-foreground">从全球画像选择关联产品矩阵开始第一轮；重复范围会提示复用已有项目。</p><Button className="mt-4" variant="outline" onClick={onOpenGlobalPersonas}>前往全球画像</Button></div>}

    <Dialog open={createOpen} onOpenChange={setCreateOpen}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader><DialogTitle>从全球画像建立验证项目</DialogTitle><DialogDescription>项目固定继承一个全球画像；第一轮可选择多条相互关联的产品矩阵关系。</DialogDescription></DialogHeader>
        <div className="grid gap-4 py-2 md:grid-cols-2">
          <label className="space-y-1.5 text-sm font-medium md:col-span-2">项目名称<Input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="留空则自动生成" /></label>
          <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-3"><p className="text-xs text-cyan-800">全球画像</p><p className="mt-1 font-medium text-cyan-950">{selectedPersona?.name ?? draft.personaCode}</p><p className="mt-1 text-xs text-cyan-800">画像在项目内固定；如需更换，请返回全球画像重新建立。</p></div>
          <label className="space-y-1.5 text-sm font-medium">目标市场<Select value={draft.regionCode} onValueChange={(value) => setDraft({ ...draft, regionCode: value, matrixIds: [] })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{data.taxonomy.regions.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
          <label className="space-y-1.5 text-sm font-medium">销售/采购场景<Input list="program-scenarios" value={draft.purchaseScenario} onChange={(event) => setDraft({ ...draft, purchaseScenario: event.target.value })} /><datalist id="program-scenarios">{selectedPersona?.purchase_scenarios.map((item) => <option key={item} value={item} />)}</datalist></label>
          <label className="space-y-1.5 text-sm font-medium">销售渠道<Input list="program-channels" value={draft.salesChannel} onChange={(event) => setDraft({ ...draft, salesChannel: event.target.value })} /><datalist id="program-channels">{selectedPersona?.sales_channels.map((item) => <option key={item} value={item} />)}</datalist></label>
          <label className="space-y-1.5 text-sm font-medium">市场与客户负责人<Input value={draft.customerOwner} onChange={(event) => setDraft({ ...draft, customerOwner: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm font-medium">产品与供应负责人<Input value={draft.supplyOwner} onChange={(event) => setDraft({ ...draft, supplyOwner: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm font-medium">每轮矩阵关系上限<Input type="number" min="1" max="20" value={draft.maxFamilyCount} onChange={(event) => setDraft({ ...draft, maxFamilyCount: Math.min(20, Math.max(1, Number(event.target.value) || 5)), matrixIds: draft.matrixIds.slice(0, Math.min(20, Math.max(1, Number(event.target.value) || 5))) })} /></label>
          <label className="space-y-1.5 text-sm font-medium">本轮复核日期<Input type="date" value={draft.nextReviewAt} onChange={(event) => setDraft({ ...draft, nextReviewAt: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm font-medium md:col-span-2">组合假设<Textarea value={draft.hypothesis} onChange={(event) => setDraft({ ...draft, hypothesis: event.target.value })} placeholder="说明该市场、场景和画像为什么可能持续采购这些产品家族" /></label>
          <div className="md:col-span-2"><div className="flex items-center justify-between"><div><p className="text-sm font-medium">关联产品矩阵</p><p className="mt-1 text-xs text-muted-foreground">只显示当前全球画像及目标市场可用的关系；项目会保留关系来源和创建时状态。</p></div><Badge variant="outline">已选 {draft.matrixIds.length}/{draft.maxFamilyCount}</Badge></div><div className="mt-3 grid gap-2 sm:grid-cols-2">{rankedMatrixOptions.map(({ matrix, family }) => {
            const selected = draft.matrixIds.includes(matrix.id);
            const disabled = !selected && draft.matrixIds.length >= draft.maxFamilyCount;
            return <button type="button" key={matrix.id} disabled={disabled} onClick={() => toggleDraftMatrix(matrix.id)} className={`rounded-xl border p-3 text-left text-sm transition ${selected ? "border-cyan-700 bg-cyan-50" : "bg-white hover:border-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"}`}><span className="font-medium">{family.name}</span><span className="mt-1 block text-xs text-muted-foreground">{family.track_name} · {MATRIX_ROLE_LABELS[matrix.family_role] ?? matrix.family_role} · 关系分 {matrix.relevance_score}</span><span className="mt-2 inline-flex rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">{MATRIX_EVIDENCE_LABELS[matrix.evidence_status] ?? matrix.evidence_status}</span></button>;
          })}{!rankedMatrixOptions.length && <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground sm:col-span-2">该画像在此市场尚未建立产品矩阵，请返回全球画像先补充关系。</div>}</div></div>
        </div>
        {duplicateProgram && <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"><p className="font-medium">已存在相同画像、市场、场景和渠道的活动项目：{duplicateProgram.title}</p><p className="mt-1">不能重复创建。你可以进入原项目，或把本次尚未存在的产品矩阵加入原项目当前轮次；底层共享证据会继续复用。</p><div className="mt-3 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => { setCreateOpen(false); void openProgram(duplicateProgram); }}>进入原项目</Button><Button size="sm" onClick={() => void reuseExistingProgram()} disabled={busy || !draft.matrixIds.length}>复用原项目并加入矩阵</Button></div></div>}
        {message && <p className="text-sm text-rose-700">{message}</p>}
        <DialogFooter><Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button><Button onClick={() => void createProgram()} disabled={busy || Boolean(duplicateProgram) || !draft.personaCode || !draft.purchaseScenario || !draft.salesChannel || !draft.matrixIds.length}>创建并开始第一轮</Button></DialogFooter>
      </DialogContent>
    </Dialog>

    <Sheet open={Boolean(selectedProgram)} onOpenChange={(open) => { if (!open) { setSelectedProgramId(null); setProgramDetail(null); } }}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-5xl">
        {selectedProgram && !currentRound && <div className="p-8 text-center"><ClipboardList className="mx-auto size-8 text-cyan-800" /><p className="mt-3 font-medium">{detailLoading ? "正在读取项目详情…" : "该项目没有可显示的轮次"}</p>{!detailLoading && <p className="mt-1 text-sm text-muted-foreground">请刷新列表；若项目已作废，历史轮次仍会保留。</p>}</div>}
        {selectedProgram && currentRound && <>
          <SheetHeader className="border-b p-6 text-left"><div className="flex flex-wrap items-start justify-between gap-3"><div><SheetTitle>{selectedProgram.title}</SheetTitle><SheetDescription className="mt-1">{selectedProgram.region_name} · {selectedProgram.persona_name} · {selectedProgram.purchase_scenario} · {selectedProgram.sales_channel}</SheetDescription></div><div className="flex gap-2"><Badge>{PHASE_LABELS[currentRound.phase]}</Badge><Badge variant="outline">第{currentRound.round_number}轮</Badge></div></div></SheetHeader>
          <div className="p-5"><Tabs defaultValue="overview"><TabsList className="grid w-full grid-cols-4"><TabsTrigger value="overview">概览</TabsTrigger><TabsTrigger value="families">产品家族</TabsTrigger><TabsTrigger value="customers">客户反馈</TabsTrigger><TabsTrigger value="history">轮次历史</TabsTrigger></TabsList>
            <TabsContent value="overview" className="space-y-4 pt-4">
              <section className="rounded-2xl border border-cyan-200 bg-cyan-50 p-5"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-xs font-medium text-cyan-800">本轮目标</p><p className="mt-2 leading-6 text-cyan-950">{currentRound.goal}</p><p className="mt-3 text-sm text-cyan-900">下一步：{selectedProgram.next_action || "补充证据并完成复盘"}</p></div><Button onClick={startDecision} disabled={!canEditCurrentRound}><CheckCircle2 /> 本轮复盘</Button></div>{!canEditCurrentRound && <p className="mt-4 rounded-xl border border-slate-200 bg-white/70 px-3 py-2 text-sm text-muted-foreground">本轮已结束或项目已作废，当前仅可查看历史与证据。</p>}</section>
              <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl border bg-white p-4"><p className="text-xs text-muted-foreground">候选产品家族</p><p className="mt-1 text-2xl font-semibold">{currentFamilies.length}/{selectedProgram.max_family_count}</p></div><div className="rounded-xl border bg-white p-4"><p className="text-xs text-muted-foreground">客户记录</p><p className="mt-1 text-2xl font-semibold">{currentFeedback.length}</p></div><div className="rounded-xl border bg-white p-4"><p className="text-xs text-muted-foreground">有效反馈/RFQ</p><p className="mt-1 text-2xl font-semibold">{qualifiedFeedback.length}</p></div></div>
              <section className="rounded-2xl border bg-white p-5"><div className="flex items-center gap-2"><Settings2 className="size-4 text-cyan-800" /><h3 className="font-semibold">项目设置</h3></div><div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="space-y-1.5 text-sm">每轮产品家族上限<Input type="number" min="1" max="20" value={settingsMax} disabled={!canEditCurrentRound} onChange={(event) => setSettingsMax(Math.min(20, Math.max(1, Number(event.target.value) || 5)))} /></label><label className="space-y-1.5 text-sm">复核日期<Input type="date" value={settingsNextReview} disabled={!canEditCurrentRound} onChange={(event) => setSettingsNextReview(event.target.value)} /></label><label className="space-y-1.5 text-sm">市场与客户负责人<Input value={settingsCustomerOwner} disabled={!canEditCurrentRound} onChange={(event) => setSettingsCustomerOwner(event.target.value)} /></label><label className="space-y-1.5 text-sm">产品与供应负责人<Input value={settingsSupplyOwner} disabled={!canEditCurrentRound} onChange={(event) => setSettingsSupplyOwner(event.target.value)} /></label></div><div className="mt-4 flex justify-end"><Button variant="outline" onClick={() => void saveSettings()} disabled={busy || !canEditCurrentRound}>保存设置</Button></div></section>
            </TabsContent>
            <TabsContent value="families" className="space-y-3 pt-4">{currentFamilies.map((family) => {
              const feedbackCount = currentFeedback.filter((item) => item.product_family_code === family.product_family_code).length;
              const qualifiedCount = currentFeedback.filter((item) => item.product_family_code === family.product_family_code && ["qualified", "rfq", "sample", "trial"].includes(item.feedback_status)).length;
              return <article key={family.id} className="rounded-2xl border bg-white p-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{family.product_family_name}</h3><Badge variant="outline">{FAMILY_STATUS_LABELS[family.status]}</Badge><Badge variant="secondary">{MATRIX_ROLE_LABELS[family.matrix_role] ?? family.matrix_role}</Badge></div><p className="mt-1 text-sm text-muted-foreground">{family.track_name} · 矩阵关系分 {family.matrix_score} · 客户记录 {feedbackCount} · 有效反馈 {qualifiedCount}</p></div><Button variant="outline" onClick={() => onOpenOpportunity(family.opportunity_id)}>查看证据</Button></div><div className="mt-4 flex flex-wrap gap-2"><Button size="sm" variant={family.status === "continue" ? "default" : "outline"} disabled={!canEditCurrentRound || busy} onClick={() => startFamilyDecision(family, "continue")}>继续</Button><Button size="sm" variant={family.status === "adjust" ? "default" : "outline"} disabled={!canEditCurrentRound || busy} onClick={() => startFamilyDecision(family, "adjust")}>调整</Button><Button size="sm" variant={family.status === "pass" ? "destructive" : "outline"} disabled={!canEditCurrentRound || busy} onClick={() => startFamilyDecision(family, "pass")}>Pass</Button></div></article>;
            })}</TabsContent>
            <TabsContent value="customers" className="space-y-4 pt-4"><div className="flex items-center justify-between"><div><h3 className="font-semibold">第一批客户与真实反馈</h3><p className="mt-1 text-sm text-muted-foreground">公开公司页面不计入有效反馈；只有真实回复、访谈、RFQ和样品/试单请求会提高证据成熟度。</p></div><Button onClick={startFeedback} disabled={!canEditCurrentRound}><Users /> 添加客户记录</Button></div>{currentFeedback.length ? <div className="space-y-3">{currentFeedback.map((item) => <article key={item.id} className="rounded-xl border bg-white p-4"><div className="flex flex-wrap items-center gap-2"><h4 className="font-medium">{item.company_name}</h4><Badge variant="outline">{FEEDBACK_STATUS_LABELS[item.feedback_status] ?? item.feedback_status}</Badge><span className="ml-auto text-xs text-muted-foreground">{dateText(item.created_at)}</span></div><p className="mt-1 text-sm text-muted-foreground">{currentFamilies.find((family) => family.product_family_code === item.product_family_code)?.product_family_name} {item.contact_role ? `· ${item.contact_role}` : ""}</p>{item.pain_points && <p className="mt-3 text-sm leading-6">痛点：{item.pain_points}</p>}{item.note && <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.note}</p>}</article>)}</div> : <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">尚未记录客户联系或反馈。</p>}</TabsContent>
            <TabsContent value="history" className="space-y-3 pt-4"><div className="flex flex-wrap items-center gap-3"><Select value={historyPhase} onValueChange={(value) => { setHistoryPhase(value); setHistoryPage(1); }}><SelectTrigger className="w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">全部阶段</SelectItem><SelectItem value="discovery">价值发现</SelectItem><SelectItem value="commercial">商业验证</SelectItem><SelectItem value="pilot">首单履约</SelectItem></SelectContent></Select><Select value={historyStatus} onValueChange={(value) => { setHistoryStatus(value); setHistoryPage(1); }}><SelectTrigger className="w-40"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">全部状态</SelectItem><SelectItem value="active">进行中</SelectItem><SelectItem value="hold">暂停</SelectItem><SelectItem value="completed">已结束</SelectItem><SelectItem value="voided">已作废</SelectItem></SelectContent></Select><span className="text-sm text-muted-foreground">共 {filteredHistory.length} 轮</span></div>{visibleHistory.map((round) => <article key={round.id} className="rounded-xl border bg-white p-4"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">第{round.round_number}轮 · {PHASE_LABELS[round.phase]}</h3><Badge variant="outline">{round.status === "completed" ? "已结束" : round.status === "hold" ? "暂停" : round.status === "voided" ? "已作废" : "进行中"}</Badge>{round.decision && <Badge>{DECISION_LABELS[round.decision] ?? round.decision}</Badge>}</div><p className="mt-2 text-sm leading-6">{round.goal}</p>{round.decision_note && <p className="mt-2 text-sm text-muted-foreground">复盘：{round.decision_note}</p>}</article>)}{!visibleHistory.length && <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">没有符合条件的轮次记录。</p>}<div className="flex items-center justify-end gap-2"><Button size="icon" variant="outline" disabled={historyPage <= 1} onClick={() => setHistoryPage((current) => Math.max(1, current - 1))}><ChevronLeft /><span className="sr-only">上一页</span></Button><span className="min-w-16 text-center text-sm">{Math.min(historyPage, historyTotalPages)}/{historyTotalPages}</span><Button size="icon" variant="outline" disabled={historyPage >= historyTotalPages} onClick={() => setHistoryPage((current) => current + 1)}><ChevronRight /><span className="sr-only">下一页</span></Button></div></TabsContent>
          </Tabs>{message && <p className="mt-4 rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-900">{message}</p>}</div>
        </>}
      </SheetContent>
    </Sheet>

    <Dialog open={voidOpen} onOpenChange={setVoidOpen}><DialogContent className="sm:max-w-xl"><DialogHeader><DialogTitle>作废验证项目</DialogTitle><DialogDescription>作废后项目退出活动列表，不能继续录入；历史轮次、客户反馈、产品家族档案和可复用共享证据不会删除。</DialogDescription></DialogHeader><div className="space-y-4 py-2"><div className="rounded-xl border bg-slate-50 p-3 text-sm font-medium">{voidProgram?.title}</div><label className="space-y-1.5 text-sm">作废原因<Select value={voidReasonCode} onValueChange={(value) => { setVoidReasonCode(value); setReplacementProgramId(""); }}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{Object.entries(VOID_REASON_LABELS).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></label>{["duplicate", "merged"].includes(voidReasonCode) && <label className="space-y-1.5 text-sm">替代项目<Select value={replacementProgramId} onValueChange={setReplacementProgramId}><SelectTrigger><SelectValue placeholder="请选择承接历史的活动项目" /></SelectTrigger><SelectContent>{data.programs.filter((item) => item.id !== voidProgram?.id && item.active && item.status !== "voided").map((item) => <SelectItem key={item.id} value={item.id}>{item.title}</SelectItem>)}</SelectContent></Select></label>}<label className="space-y-1.5 text-sm">说明<Textarea value={voidReasonNote} onChange={(event) => setVoidReasonNote(event.target.value)} placeholder="说明为什么作废，便于后续追溯" /></label><label className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950"><input className="mt-1" type="checkbox" checked={voidConfirmed} onChange={(event) => setVoidConfirmed(event.target.checked)} /><span>我确认作废的是这个项目。作废不会删除共享调研资产，但会终止当前轮次和待执行任务。</span></label></div><DialogFooter><Button variant="outline" onClick={() => setVoidOpen(false)}>取消</Button><Button variant="destructive" onClick={() => void submitVoid()} disabled={busy || !voidConfirmed || (["duplicate", "merged"].includes(voidReasonCode) && !replacementProgramId) || (voidReasonCode === "other" && !voidReasonNote.trim())}>确认作废</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={feedbackOpen} onOpenChange={setFeedbackOpen}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl"><DialogHeader><DialogTitle>添加客户联系或反馈</DialogTitle><DialogDescription>记录原始事实，不把公开页面或推测当作真实客户回复。</DialogDescription></DialogHeader><div className="grid gap-4 py-2 sm:grid-cols-2"><label className="space-y-1.5 text-sm">产品家族<Select value={feedback.productFamilyCode} onValueChange={(value) => setFeedback({ ...feedback, productFamilyCode: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{currentFamilies.map((item) => <SelectItem key={item.id} value={item.product_family_code}>{item.product_family_name}</SelectItem>)}</SelectContent></Select></label><label className="space-y-1.5 text-sm">客户状态<Select value={feedback.feedbackStatus} onValueChange={(value) => setFeedback({ ...feedback, feedbackStatus: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{Object.entries(FEEDBACK_STATUS_LABELS).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></label><label className="space-y-1.5 text-sm">客户公司<Input value={feedback.companyName} onChange={(event) => setFeedback({ ...feedback, companyName: event.target.value })} /></label><label className="space-y-1.5 text-sm">联系人角色<Input value={feedback.contactRole} onChange={(event) => setFeedback({ ...feedback, contactRole: event.target.value })} placeholder="采购/品类/技术/老板" /></label><label className="space-y-1.5 text-sm sm:col-span-2">采购或使用场景<Input value={feedback.scenario} onChange={(event) => setFeedback({ ...feedback, scenario: event.target.value })} /></label><label className="space-y-1.5 text-sm">当前方案<Input value={feedback.currentSolution} onChange={(event) => setFeedback({ ...feedback, currentSolution: event.target.value })} /></label><label className="space-y-1.5 text-sm">采购周期<Input value={feedback.purchaseCycle} onChange={(event) => setFeedback({ ...feedback, purchaseCycle: event.target.value })} /></label><label className="space-y-1.5 text-sm sm:col-span-2">真实痛点<Textarea value={feedback.painPoints} onChange={(event) => setFeedback({ ...feedback, painPoints: event.target.value })} /></label><label className="space-y-1.5 text-sm sm:col-span-2">必要规格<Textarea value={feedback.mustHaveSpecs} onChange={(event) => setFeedback({ ...feedback, mustHaveSpecs: event.target.value })} /></label><label className="space-y-1.5 text-sm">采购触发因素<Input value={feedback.buyingTrigger} onChange={(event) => setFeedback({ ...feedback, buyingTrigger: event.target.value })} /></label><label className="space-y-1.5 text-sm">价格关注方式<Input value={feedback.priceBehavior} onChange={(event) => setFeedback({ ...feedback, priceBehavior: event.target.value })} /></label><label className="space-y-1.5 text-sm">拒绝原因<Input value={feedback.rejectionReason} onChange={(event) => setFeedback({ ...feedback, rejectionReason: event.target.value })} /></label><label className="space-y-1.5 text-sm">原始来源链接<Input type="url" value={feedback.sourceUrl} onChange={(event) => setFeedback({ ...feedback, sourceUrl: event.target.value })} /></label><label className="space-y-1.5 text-sm sm:col-span-2">补充记录<Textarea value={feedback.note} onChange={(event) => setFeedback({ ...feedback, note: event.target.value })} /></label></div><DialogFooter><Button variant="outline" onClick={() => setFeedbackOpen(false)}>取消</Button><Button onClick={() => void saveFeedback()} disabled={busy || !feedback.productFamilyCode || !feedback.companyName}>保存记录</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={familyDecisionOpen} onOpenChange={(open) => { if (!busy) setFamilyDecisionOpen(open); }}><DialogContent className="sm:max-w-xl"><DialogHeader><DialogTitle>确认产品家族结论</DialogTitle><DialogDescription>此操作只更新当前轮次的结论，不会删除共享证据、客户记录或历史评估。</DialogDescription></DialogHeader><div className="space-y-4 py-2"><div className="rounded-xl border bg-slate-50 p-3"><p className="font-medium">{familyDecisionTarget?.product_family_name}</p><p className="mt-1 text-sm text-muted-foreground">将标记为：{FAMILY_STATUS_LABELS[familyDecisionStatus]}</p></div><label className="space-y-1.5 text-sm">判断依据{["adjust", "pass"].includes(familyDecisionStatus) ? "（必填）" : "（选填）"}<Textarea value={familyDecisionRationale} onChange={(event) => setFamilyDecisionRationale(event.target.value)} placeholder={familyDecisionStatus === "pass" ? "记录无需求、价格不成立或供应阻断等事实" : familyDecisionStatus === "adjust" ? "说明需要调整的市场、场景、规格或客户假设" : "说明继续验证的证据和下一步"} /></label>{familyDecisionStatus === "pass" && <label className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950"><input className="mt-1" type="checkbox" checked={familyDecisionConfirmed} onChange={(event) => setFamilyDecisionConfirmed(event.target.checked)} /><span>我确认仅将该产品家族在本轮标记为 Pass；已有证据仍保留并可被其他项目复用。</span></label>}</div><DialogFooter><Button variant="outline" onClick={() => setFamilyDecisionOpen(false)} disabled={busy}>取消</Button><Button variant={familyDecisionStatus === "pass" ? "destructive" : "default"} onClick={() => void changeFamilyStatus()} disabled={busy || !canEditCurrentRound || (["adjust", "pass"].includes(familyDecisionStatus) && !familyDecisionRationale.trim()) || (familyDecisionStatus === "pass" && !familyDecisionConfirmed)}>确认{FAMILY_STATUS_LABELS[familyDecisionStatus]}</Button></DialogFooter></DialogContent></Dialog>

    <Dialog open={decisionOpen} onOpenChange={setDecisionOpen}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl"><DialogHeader><DialogTitle>本轮复盘与决策</DialogTitle><DialogDescription>继续会生成新轮次并保留全部历史；Pass只归档，不删除数据。</DialogDescription></DialogHeader><div className="space-y-4 py-2"><label className="space-y-1.5 text-sm">本轮决策<Select value={decision} onValueChange={setDecision}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{Object.entries(DECISION_LABELS).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></label>{["continue", "adjust"].includes(decision) && <div><div className="flex items-center justify-between"><p className="text-sm font-medium">进入下一轮的产品家族</p><Badge variant="outline">{decisionFamilyCodes.length}/{selectedProgram?.max_family_count ?? 5}</Badge></div><div className="mt-2 space-y-2">{currentFamilies.map((family) => <label key={family.id} className="flex items-center gap-3 rounded-xl border p-3 text-sm"><input type="checkbox" checked={decisionFamilyCodes.includes(family.product_family_code)} onChange={() => toggleDecisionFamily(family.product_family_code)} /><span>{family.product_family_name}</span><Badge variant="outline" className="ml-auto">{FAMILY_STATUS_LABELS[family.status]}</Badge></label>)}</div></div>}<label className="space-y-1.5 text-sm">复盘结论<Textarea value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} placeholder={decision === "pass" ? "Pass原因（必填）" : "本轮学到了什么，为什么做这个决定"} /></label>{decision !== "pass" && <><label className="space-y-1.5 text-sm">下一轮目标<Input value={decisionNextGoal} onChange={(event) => setDecisionNextGoal(event.target.value)} placeholder="留空使用系统默认目标" /></label><label className="space-y-1.5 text-sm">下一步行动<Input value={decisionNextAction} onChange={(event) => setDecisionNextAction(event.target.value)} /></label><label className="space-y-1.5 text-sm">下次复核日期<Input type="date" value={decisionDueAt} onChange={(event) => setDecisionDueAt(event.target.value)} /></label></>}{decision === "continue" && <label className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950"><input className="mt-1" type="checkbox" checked={confirmedByBoth} onChange={(event) => setConfirmedByBoth(event.target.checked)} /><span>两位负责人已经共同确认进入下一阶段。正式报价和样品/首单投入仍需在对应阶段再次确认。</span></label>}</div><DialogFooter><Button variant="outline" onClick={() => setDecisionOpen(false)}>取消</Button><Button variant={decision === "pass" ? "destructive" : "default"} onClick={() => void submitDecision()} disabled={busy || (decision === "pass" && !decisionNote.trim()) || (decision === "continue" && !confirmedByBoth)}>保存本轮决策</Button></DialogFooter></DialogContent></Dialog>
  </section>;
}
