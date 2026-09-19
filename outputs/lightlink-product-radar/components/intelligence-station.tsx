"use client";

import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { Activity, Archive, Bot, CalendarClock, CalendarPlus, Check, Database, Eye, FileUp, Globe2, Pause, Play, Plus, RefreshCw, Search, Settings2, Target, TrendingUp, Users, XCircle, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  MONITOR_SIMULATION_SCENARIOS,
  TRIGGER_CATEGORY_LABELS,
  type MarketSignalType,
  type MonitorSimulationScenario,
  type MonitorSimulationStepStatus,
  type TriggerCategory,
} from "@/lib/intelligence-station";

type Monitor = {
  id: string;
  name: string;
  region_code: string;
  region_name: string;
  trigger_type: string;
  trigger_name: string;
  persona_code: string;
  persona_name: string;
  product_family_code: string;
  product_family_name: string;
  keywords: string[];
  signal_types: MarketSignalType[];
  commodity_codes: string[];
  source_ids: string[];
  cadence_days: number;
  status: "active" | "paused" | "archived";
  last_run_at: string | null;
  next_run_at: string | null;
  signal_count: number;
  latest_signal_at: string | null;
  latest_run_status: string | null;
};

type Signal = {
  id: string;
  signal_type: MarketSignalType;
  source_name: string;
  source_url: string;
  region_name: string;
  product_family_name: string;
  period: string;
  metric: string;
  value: number | null;
  unit: string;
  direction: string;
  confidence: number;
  evidence_grade: string;
  data_status: string;
  title: string;
  summary: string;
  collected_at: string;
};

type SignalLayer = {
  id: MarketSignalType;
  name: string;
  description: string;
  decisionUse: string;
  warning: string;
};

type TriggerDefinition = {
  id: string;
  category: TriggerCategory;
  name: string;
  description: string;
  defaultSignalTypes: MarketSignalType[];
};

type MonitorRun = {
  id: string;
  monitor_id: string;
  monitor_name: string;
  status: "running" | "waiting_for_data" | "completed" | "failed";
  trigger_reason: string;
  signal_count: number;
  error: string;
  error_category: string;
  duration_ms: number;
  retry_count: number;
  created_at: string;
  completed_at: string | null;
  result_json: {
    simulation?: boolean;
    scenario?: MonitorSimulationScenario;
    readyForReview?: boolean;
    blockers?: string[];
    nextAction?: string;
    isolation?: string;
    assessment?: { readyForReview?: boolean; opportunityType?: string; blockers?: string[] };
    pipelineSteps?: Array<{ id: string; name: string; status: MonitorSimulationStepStatus; detail: string }>;
  };
};

type SourceHealth = {
  source_id: string;
  monitor_id: string;
  monitor_name: string;
  status: "never_run" | "completed" | "no_data" | "failed" | "not_applicable";
  coverage_countries: string[];
  quota_summary: string;
  update_frequency: string;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error_category: string;
  last_error: string;
  consecutive_failures: number;
  result_count: number;
  duration_ms: number;
  retry_count: number;
};

type MonitorSimulationResult = {
  id: string;
  monitorId: string;
  monitorName: string;
  simulation: true;
  scenario: MonitorSimulationScenario;
  runStatus: "completed" | "waiting_for_data" | "failed";
  assessment: { readyForReview: boolean; opportunityType: string; blockers: string[] };
  pipelineSteps: Array<{ id: string; name: string; status: MonitorSimulationStepStatus; detail: string }>;
  nextAction: string;
  isolation: string;
};

type OpportunityCandidate = {
  id: string;
  monitor_name: string;
  title: string;
  opportunity_type: string;
  status: "pending_review" | "accepted" | "observing" | "passed" | "merged";
  evidence_count: number;
  source_count: number;
  summary: string;
  rationale: string;
  next_action: string;
  review_note: string;
  region_name: string;
  product_family_name: string;
  updated_at: string;
};

type IntelligenceEvent = {
  id: string;
  name: string;
  region_code: string;
  region_name: string;
  trigger_type: string;
  starts_at: string;
  ends_at: string | null;
  procurement_lead_days: number;
  delivery_cutoff: string | null;
  source_name: string;
  source_url: string;
  notes: string;
};

type ActionItem = {
  type: "candidate_review" | "data_required" | "run_failed";
  id: string;
  title: string;
  detail: string;
};

type IntelligenceData = {
  monitors: Monitor[];
  signals: Signal[];
  runs: MonitorRun[];
  candidates: OpportunityCandidate[];
  events: IntelligenceEvent[];
  sourceHealth: SourceHealth[];
  actionItems: ActionItem[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  stats: {
    totalMonitors: number;
    activeMonitors: number;
    dueMonitors: number;
    coveredRegions: number;
    availableSignals: number;
    actionableSignals: number;
    pendingCandidates: number;
    waitingRuns: number;
    failedRuns: number;
    upcomingEvents: number;
  };
  taxonomy: {
    regions: Array<{ code: string; name: string }>;
    personas: Array<{ code: string; name: string }>;
    productFamilies: Array<{ code: string; name: string; track_code: string }>;
  };
  signalLayers: SignalLayer[];
  triggerCatalog: TriggerDefinition[];
};

type MonitorDraft = {
  name: string;
  regionCode: string;
  triggerType: string;
  personaCode: string;
  productFamilyCode: string;
  keywords: string;
  commodityCodes: string;
  sourceIds: string[];
  cadenceDays: string;
};

const emptyDraft: MonitorDraft = {
  name: "",
  regionCode: "GLOBAL",
  triggerType: "daily_replenishment",
  personaCode: "none",
  productFamilyCode: "none",
  keywords: "",
  commodityCodes: "",
  sourceIds: ["un_comtrade", "eurostat_comext", "uk_hmrc"],
  cadenceDays: "7",
};

const MONITOR_STATUS_LABELS: Record<string, string> = { active: "监控中", paused: "已暂停", archived: "已归档" };
const RUN_STATUS_LABELS: Record<string, string> = { running: "执行中", waiting_for_data: "等待授权/导入", completed: "已完成", failed: "执行失败" };
const CANDIDATE_STATUS_LABELS: Record<string, string> = { pending_review: "待复核", accepted: "已接受", observing: "继续观察", passed: "已 Pass", merged: "已合并" };
const OPPORTUNITY_TYPE_LABELS: Record<string, string> = { short_term: "短期机会候选", long_term: "长期机会候选", blue_ocean_candidate: "蓝海假设候选", growth_red_ocean: "增长型红海候选", observe: "继续观察" };
const SIMULATION_STEP_STATUS_LABELS: Record<MonitorSimulationStepStatus, string> = { completed: "已完成", ready: "可进入", waiting: "等待人工", blocked: "未通过", failed: "模拟失败", not_started: "未开始" };
const SOURCE_NAMES: Record<string, string> = { un_comtrade: "UN Comtrade", eurostat_comext: "Eurostat", uk_hmrc: "UK HMRC" };
const SOURCE_HEALTH_LABELS: Record<string, string> = { never_run: "尚未运行", completed: "成功", no_data: "无数据", failed: "失败", not_applicable: "不适用" };

type EventDraft = { name: string; regionCode: string; triggerType: string; startsAt: string; endsAt: string; procurementLeadDays: string; deliveryCutoff: string; sourceName: string; sourceUrl: string; notes: string };

const emptyEventDraft: EventDraft = {
  name: "",
  regionCode: "GLOBAL",
  triggerType: "sports_event",
  startsAt: "",
  endsAt: "",
  procurementLeadDays: "60",
  deliveryCutoff: "",
  sourceName: "",
  sourceUrl: "",
  notes: "",
};

function dateText(value: string | null) {
  if (!value) return "尚未执行";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function postAction<T extends Record<string, unknown> = Record<string, unknown>>(body: Record<string, unknown>) {
  const response = await fetch("/api/radar", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const result = await response.json() as T & { ok?: boolean; error?: string };
  if (!response.ok || !result.ok) throw new Error(result.error ?? "操作失败");
  return result;
}

export function IntelligenceStation({ onOpenRadar, onOpenPrograms, onOpenSources }: {
  onOpenRadar(): void;
  onOpenPrograms(): void;
  onOpenSources(): void;
}) {
  const [data, setData] = useState<IntelligenceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [formMessage, setFormMessage] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState<MonitorDraft>(emptyDraft);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [status, setStatus] = useState("active");
  const [region, setRegion] = useState("all");
  const [trigger, setTrigger] = useState("all");
  const [page, setPage] = useState(1);
  const [importOpen, setImportOpen] = useState(false);
  const [importMonitorId, setImportMonitorId] = useState("");
  const [importText, setImportText] = useState("");
  const [eventOpen, setEventOpen] = useState(false);
  const [eventDraft, setEventDraft] = useState<EventDraft>(emptyEventDraft);
  const [simulationOpen, setSimulationOpen] = useState(false);
  const [simulationMonitor, setSimulationMonitor] = useState<Monitor | null>(null);
  const [simulationScenario, setSimulationScenario] = useState<MonitorSimulationScenario>("candidate_ready");
  const [simulationResult, setSimulationResult] = useState<MonitorSimulationResult | null>(null);
  const [sourceConfigOpen, setSourceConfigOpen] = useState(false);
  const [sourceConfigMonitor, setSourceConfigMonitor] = useState<Monitor | null>(null);
  const [sourceConfigCodes, setSourceConfigCodes] = useState("");
  const [sourceConfigIds, setSourceConfigIds] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ view: "intelligence_station", page: String(page), pageSize: "12", status, region, trigger });
      if (deferredQuery.trim()) params.set("q", deferredQuery.trim());
      const response = await fetch(`/api/radar?${params.toString()}`, { cache: "no-store" });
      const result = await response.json() as IntelligenceData & { error?: string };
      if (!response.ok) throw new Error(result.error ?? "读取情报站失败");
      setData(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取情报站失败");
    } finally {
      setLoading(false);
    }
  }, [deferredQuery, page, region, status, trigger]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const triggersByCategory = useMemo(() => {
    const grouped = new Map<TriggerCategory, TriggerDefinition[]>();
    for (const item of data?.triggerCatalog ?? []) grouped.set(item.category, [...(grouped.get(item.category) ?? []), item]);
    return [...grouped.entries()];
  }, [data?.triggerCatalog]);
  const selectedTrigger = data?.triggerCatalog.find((item) => item.id === draft.triggerType) ?? null;
  const openCreate = () => {
    setFormMessage("");
    setCreateOpen(true);
  };

  async function createMonitor() {
    if (!draft.regionCode || !draft.triggerType || (!draft.productFamilyCode || draft.productFamilyCode === "none") && !draft.keywords.trim()) {
      setFormMessage("请选择地区和触发事件，并填写关键词或选择产品家族。");
      return;
    }
    setFormMessage("");
    setBusy(true);
    try {
      await postAction({
        action: "create_market_signal_monitor",
        name: draft.name,
        regionCode: draft.regionCode,
        triggerType: draft.triggerType,
        triggerName: selectedTrigger?.name,
        personaCode: draft.personaCode === "none" ? "" : draft.personaCode,
        productFamilyCode: draft.productFamilyCode === "none" ? "" : draft.productFamilyCode,
        keywords: draft.keywords.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean),
        commodityCodes: draft.commodityCodes.split(/[，,\s]+/).map((item) => item.trim()).filter(Boolean),
        sourceIds: draft.sourceIds,
        signalTypes: selectedTrigger?.defaultSignalTypes ?? [],
        cadenceDays: Number(draft.cadenceDays),
      });
      setCreateOpen(false);
      setDraft(emptyDraft);
      setFormMessage("");
      setMessage("监控规则已建立。系统会先复用本地证据，再按来源权限补充新数据。");
      setPage(1);
      await load();
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "建立监控失败");
    } finally {
      setBusy(false);
    }
  }

  function toggleDraftSource(sourceId: string) {
    setDraft((current) => ({
      ...current,
      sourceIds: current.sourceIds.includes(sourceId)
        ? current.sourceIds.filter((item) => item !== sourceId)
        : [...current.sourceIds, sourceId],
    }));
  }

  function openSourceConfig(item: Monitor) {
    setSourceConfigMonitor(item);
    setSourceConfigCodes(item.commodity_codes.join(", "));
    setSourceConfigIds(item.source_ids.length ? item.source_ids : ["un_comtrade", "eurostat_comext", "uk_hmrc"]);
    setFormMessage("");
    setSourceConfigOpen(true);
  }

  function toggleSourceConfig(sourceId: string) {
    setSourceConfigIds((current) => current.includes(sourceId)
      ? current.filter((item) => item !== sourceId)
      : [...current, sourceId]);
  }

  async function saveSourceConfig() {
    if (!sourceConfigMonitor) return;
    setBusy(true);
    setFormMessage("");
    try {
      const result = await postAction<{ commodityCodes?: string[] }>({
        action: "update_market_signal_monitor_sources",
        monitorId: sourceConfigMonitor.id,
        commodityCodes: sourceConfigCodes.split(/[，,\s]+/).map((item) => item.trim()).filter(Boolean),
        sourceIds: sourceConfigIds,
      });
      setSourceConfigOpen(false);
      setMessage(`“${sourceConfigMonitor.name}”已确认 HS/CN ${result.commodityCodes?.join("、") || ""}，并进入待执行队列。`);
      await load();
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "保存来源口径失败");
    } finally {
      setBusy(false);
    }
  }

  async function changeMonitorStatus(item: Monitor, nextStatus: "active" | "paused" | "archived") {
    if (nextStatus === "archived" && !window.confirm(`归档“${item.name}”？历史信号会保留，监控将停止。`)) return;
    setBusy(true);
    try {
      await postAction({ action: "set_market_signal_monitor_status", monitorId: item.id, status: nextStatus });
      setMessage(nextStatus === "active" ? "监控已恢复。" : nextStatus === "paused" ? "监控已暂停，已有信号仍然保留。" : "监控已归档，历史信号未删除。");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "更新监控状态失败");
    } finally {
      setBusy(false);
    }
  }

  async function executeMonitor(item: Monitor) {
    setBusy(true);
    try {
      const result = await postAction<{ signalCount?: number; status?: string; sources?: Array<{ sourceId: string; status: string; errorMessage?: string }> }>({ action: "execute_market_signal_monitor", monitorId: item.id, triggerReason: "manual" });
      setMessage(result.status === "failed"
        ? `“${item.name}”执行结束，但来源失败：${result.sources?.filter((source) => source.status === "failed").map((source) => `${SOURCE_NAMES[source.sourceId] ?? source.sourceId}（${source.errorMessage || "请查看来源健康状态"}）`).join("；") || "请查看来源健康状态"}`
        : result.status === "waiting_for_data"
        ? `“${item.name}”已建立运行记录，但本地暂无可复用证据。请到统一数据源中心授权，或导入可核验证据。`
        : `“${item.name}”已完成：关联 ${result.signalCount ?? 0} 条去重信号。`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "执行监控失败");
    } finally {
      setBusy(false);
    }
  }

  async function executeDueMonitors() {
    setBusy(true);
    try {
      const result = await postAction<{ processed?: number }>({ action: "run_due_market_signal_monitors", limit: 20 });
      setMessage(result.processed ? `已执行 ${result.processed} 条到期监控；缺少授权或数据的运行会进入待处理事项。` : "当前没有到期监控。");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "执行到期监控失败");
    } finally {
      setBusy(false);
    }
  }

  function openSimulation(item: Monitor) {
    setSimulationMonitor(item);
    setSimulationScenario("candidate_ready");
    setSimulationResult(null);
    setFormMessage("");
    setSimulationOpen(true);
  }

  async function runSimulation() {
    if (!simulationMonitor) return;
    setBusy(true);
    setFormMessage("");
    try {
      const result = await postAction<MonitorSimulationResult>({
        action: "simulate_market_signal_monitor",
        monitorId: simulationMonitor.id,
        scenario: simulationScenario,
      });
      setSimulationResult(result);
      setMessage(`“${simulationMonitor.name}”灰度测试已完成。模拟数据保持隔离，不影响正式信号和评分。`);
      await load();
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "灰度测试失败");
    } finally {
      setBusy(false);
    }
  }

  function openImport(item?: Monitor) {
    const monitorId = item?.id ?? data?.monitors.find((monitor) => monitor.status === "active")?.id ?? "";
    setImportMonitorId(monitorId);
    setImportText(`[
  {
    "signalType": "b2b_demand",
    "sourceId": "authorized_export",
    "sourceName": "填写平台或官方来源",
    "sourceUrl": "https://example.com/source",
    "period": "2026-09",
    "metric": "rfq_count",
    "value": null,
    "unit": "count",
    "direction": "rising",
    "confidence": 70,
    "evidenceGrade": "primary",
    "dataStatus": "available",
    "title": "填写可核验的信号标题",
    "summary": "说明口径、样本和限制",
    "collectedAt": "${new Date().toISOString()}"
  }
]`);
    setFormMessage("");
    setImportOpen(true);
  }

  async function importSignals() {
    let signals: unknown;
    try {
      signals = JSON.parse(importText);
      if (!Array.isArray(signals)) throw new Error("导入内容必须是 JSON 数组");
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "JSON 格式无效");
      return;
    }
    if (!importMonitorId) {
      setFormMessage("请选择要关联的活动监控。");
      return;
    }
    setBusy(true);
    setFormMessage("");
    try {
      const result = await postAction<{ imported?: number }>({ action: "import_market_signals", monitorId: importMonitorId, signals });
      setImportOpen(false);
      setMessage(`已导入并去重 ${result.imported ?? 0} 条信号；同一事实的后续更新会保留版本，不会重复计数。`);
      await load();
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "导入信号失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveEvent() {
    setBusy(true);
    setFormMessage("");
    try {
      await postAction({ action: "upsert_intelligence_event", ...eventDraft, procurementLeadDays: Number(eventDraft.procurementLeadDays) });
      setEventOpen(false);
      setEventDraft(emptyEventDraft);
      setMessage("事件已加入日历；匹配地区和触发类型的监控下次执行时会复用它。事件本身不会被当作采购需求。");
      await load();
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : "保存事件失败");
    } finally {
      setBusy(false);
    }
  }

  async function archiveEvent(item: IntelligenceEvent) {
    if (!window.confirm(`归档事件“${item.name}”？既有信号和运行历史会保留。`)) return;
    setBusy(true);
    try {
      await postAction({ action: "set_intelligence_event_status", id: item.id, status: "archived" });
      setMessage("事件已归档，历史证据未删除。");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "归档事件失败");
    } finally {
      setBusy(false);
    }
  }

  async function reviewCandidate(item: OpportunityCandidate, nextStatus: "accepted" | "observing" | "passed") {
    const reviewNote = nextStatus === "passed" ? window.prompt("请填写 Pass 原因，便于后续避免重复调研：", item.review_note || "") : "";
    if (nextStatus === "passed" && !reviewNote?.trim()) return;
    setBusy(true);
    try {
      await postAction({ action: "review_intelligence_candidate", id: item.id, status: nextStatus, reviewNote: reviewNote ?? "" });
      setMessage(nextStatus === "accepted"
        ? "候选已接受。系统不会自动建项目；请进入“验证项目与轮次”，从全球画像选择相关产品矩阵建立第一轮。"
        : nextStatus === "observing" ? "候选保留观察，后续信号继续归入同一监控。" : "候选已 Pass；原因和全部证据仍可追溯。"
      );
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "复核候选失败");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <div className="rounded-2xl border bg-white p-8 text-center text-muted-foreground">正在读取外贸情报站…</div>;

  return (
    <div className="space-y-5">
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-cyan-950 via-cyan-900 to-teal-800 p-7 text-white shadow-sm">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200">Foreign Trade Intelligence Station</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">从采购触发信号到真实客户验证</h2>
            <p className="mt-3 text-sm leading-6 text-cyan-100">持续监控目标地区的事件、搜索、B2B采购、进口贸易、竞争供给和法规变化；先形成画像与产品矩阵，再用真实客户、报价、样品和履约决定是否进入下一轮。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white" onClick={onOpenSources}><Database /> 数据来源</Button>
            <Button variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white" onClick={onOpenRadar}><TrendingUp /> 产品机会雷达</Button>
            <Button variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white" onClick={() => openImport()}><FileUp /> 导入证据</Button>
            <Button className="bg-cyan-300 text-cyan-950 hover:bg-cyan-200" onClick={openCreate}><Plus /> 新建监控</Button>
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        {([
          { label: "活动监控", value: data?.stats.activeMonitors ?? 0, Icon: Activity },
          { label: "覆盖地区", value: data?.stats.coveredRegions ?? 0, Icon: Globe2 },
          { label: "待执行", value: data?.stats.dueMonitors ?? 0, Icon: CalendarClock },
          { label: "有效信号", value: data?.stats.availableSignals ?? 0, Icon: Database },
          { label: "可行动信号", value: data?.stats.actionableSignals ?? 0, Icon: Target },
          { label: "待复核机会", value: data?.stats.pendingCandidates ?? 0, Icon: Check },
        ] satisfies Array<{ label: string; value: number; Icon: LucideIcon }>).map(({ label, value, Icon }) => <Card key={label}><CardContent className="flex items-center gap-3 p-4"><div className="rounded-xl bg-cyan-50 p-2 text-cyan-800"><Icon className="size-5" /></div><div><p className="text-xs text-muted-foreground">{label}</p><p className="text-2xl font-semibold tabular-nums">{value}</p></div></CardContent></Card>)}
      </div>

      {message && <p className="rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-950">{message}</p>}

      <Card className="gap-4 py-5 shadow-none">
        <CardHeader className="px-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div><CardTitle className="text-lg">监控规则</CardTitle><p className="mt-1 text-sm text-muted-foreground">监控先产生候选信号，不会自动创建验证项目或给出虚假高分。</p></div>
             <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => void executeDueMonitors()} disabled={busy || !(data?.stats.dueMonitors ?? 0)}><Play /> 执行到期监控</Button><Button variant="outline" onClick={() => void load()} disabled={loading}><RefreshCw className={loading ? "animate-spin" : ""} /> 刷新</Button><Button onClick={openCreate}><Plus /> 新建监控</Button></div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 px-5">
          <div className="grid gap-2 lg:grid-cols-[minmax(260px,1fr)_180px_180px_180px]">
            <div className="relative"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input className="pl-9" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索事件、关键词、画像或产品家族" /></div>
            <Select value={status} onValueChange={(value) => { setStatus(value); setPage(1); }}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="active">监控中</SelectItem><SelectItem value="paused">已暂停</SelectItem><SelectItem value="archived">已归档</SelectItem><SelectItem value="all">全部状态</SelectItem></SelectContent></Select>
            <Select value={region} onValueChange={(value) => { setRegion(value); setPage(1); }}><SelectTrigger><SelectValue placeholder="全部地区" /></SelectTrigger><SelectContent><SelectItem value="all">全部地区</SelectItem>{data?.taxonomy.regions.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select>
            <Select value={trigger} onValueChange={(value) => { setTrigger(value); setPage(1); }}><SelectTrigger><SelectValue placeholder="全部事件" /></SelectTrigger><SelectContent><SelectItem value="all">全部事件</SelectItem>{triggersByCategory.map(([category, items]) => <SelectGroup key={category}><SelectLabel>{TRIGGER_CATEGORY_LABELS[category]}</SelectLabel>{items.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectGroup>)}</SelectContent></Select>
          </div>

          {data?.monitors.length ? <div className="grid gap-3 lg:grid-cols-2">
            {data.monitors.map((item) => <article key={item.id} className="rounded-2xl border bg-white p-4">
              <div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold">{item.name}</h3><p className="mt-1 text-sm text-muted-foreground">{item.region_name || item.region_code} · {item.trigger_name}</p></div><Badge variant={item.status === "active" ? "secondary" : "outline"}>{MONITOR_STATUS_LABELS[item.status] ?? item.status}</Badge></div>
              <div className="mt-3 flex flex-wrap gap-1.5">{item.persona_name && <Badge variant="outline"><Users /> {item.persona_name}</Badge>}{item.product_family_name && <Badge variant="outline">{item.product_family_name}</Badge>}{item.signal_types.map((type) => <Badge key={type} variant="outline">{data.signalLayers.find((layer) => layer.id === type)?.name ?? type}</Badge>)}</div>
              {item.keywords.length > 0 && <p className="mt-3 text-sm leading-6 text-slate-700">关键词：{item.keywords.join("、")}</p>}
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>HS/CN：{item.commodity_codes.length ? item.commodity_codes.join("、") : "待确认"}</span>
                <span>官方来源：{item.source_ids.length ? item.source_ids.map((sourceId) => SOURCE_NAMES[sourceId] ?? sourceId).join("、") : "待配置"}</span>
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
                <span>每 {item.cadence_days} 天 · {item.signal_count} 条信号 · 最近 {dateText(item.latest_signal_at)}{item.latest_run_status ? ` · ${RUN_STATUS_LABELS[item.latest_run_status] ?? item.latest_run_status}` : ""}</span>
                <div className="flex flex-wrap gap-1">
                  {item.status !== "archived" && <Button size="sm" variant="outline" disabled={busy} onClick={() => openSimulation(item)}><Activity /> 灰度测试</Button>}
                  {item.status !== "archived" && <Button size="sm" variant="outline" disabled={busy} onClick={() => openSourceConfig(item)}><Settings2 /> 来源口径</Button>}
                  {item.status === "active" && <Button size="sm" variant="outline" disabled={busy} onClick={() => void executeMonitor(item)}><Play /> 立即执行</Button>}
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => openImport(item)}><FileUp /> 导入</Button>
                  {item.status === "active" ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void changeMonitorStatus(item, "paused")}><Pause /> 暂停</Button> : item.status === "paused" ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void changeMonitorStatus(item, "active")}><Play /> 恢复</Button> : null}
                  {item.status !== "archived" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void changeMonitorStatus(item, "archived")}><Archive /> 归档</Button>}
                </div>
              </div>
            </article>)}
           </div> : <div className="rounded-2xl border border-dashed p-8 text-center"><Target className="mx-auto size-8 text-cyan-800" /><p className="mt-3 font-medium">尚无符合条件的监控规则</p><p className="mt-1 text-sm text-muted-foreground">先选择目标地区和采购触发事件，再用关键词或产品家族限定范围。</p><Button className="mt-4" onClick={openCreate}><Plus /> 建立第一条监控</Button></div>}

          {(data?.totalPages ?? 1) > 1 && <div className="flex items-center justify-between border-t pt-4 text-sm"><span className="text-muted-foreground">共 {data?.total ?? 0} 条，第 {data?.page ?? 1}/{data?.totalPages ?? 1} 页</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={(data?.page ?? 1) <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</Button><Button variant="outline" size="sm" disabled={(data?.page ?? 1) >= (data?.totalPages ?? 1)} onClick={() => setPage((value) => value + 1)}>下一页</Button></div></div>}
        </CardContent>
      </Card>

      {(data?.actionItems.length ?? 0) > 0 && <Card className="gap-4 border-amber-200 bg-amber-50/40 py-5 shadow-none">
        <CardHeader className="px-5"><CardTitle className="text-lg">待处理事项</CardTitle><p className="text-sm text-muted-foreground">只列需要人工决策、授权/导入或处理失败的项目；没有变化时不制造提醒。</p></CardHeader>
        <CardContent className="grid gap-3 px-5 md:grid-cols-2 xl:grid-cols-3">{data?.actionItems.map((item) => <div key={`${item.type}:${item.id}`} className="rounded-xl border bg-white p-4"><div className="flex items-center gap-2"><Badge variant="outline">{item.type === "candidate_review" ? "人工复核" : item.type === "data_required" ? "等待数据" : "执行失败"}</Badge><p className="truncate font-medium">{item.title}</p></div><p className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</p>{item.type === "data_required" && <Button className="mt-3" size="sm" variant="outline" onClick={onOpenSources}>前往统一数据源中心</Button>}</div>)}</CardContent>
      </Card>}

      <Card className="gap-4 py-5 shadow-none">
        <CardHeader className="px-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><CardTitle className="text-lg">来源运行健康</CardTitle><p className="mt-1 text-sm text-muted-foreground">按“来源 × 监控”保留最近执行、覆盖范围、配额、耗时和失败原因；无数据、权限失败与确认零严格区分。</p></div><Button variant="outline" onClick={onOpenSources}><Settings2 /> 管理连接</Button></div></CardHeader>
        <CardContent className="px-5">{data?.sourceHealth.length ? <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.sourceHealth.map((item) => <article key={`${item.monitor_id}:${item.source_id}`} className="rounded-xl border p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{SOURCE_NAMES[item.source_id] ?? item.source_id}</p><p className="mt-1 text-xs text-muted-foreground">{item.monitor_name}</p></div><Badge variant={item.status === "completed" ? "secondary" : "outline"}>{SOURCE_HEALTH_LABELS[item.status] ?? item.status}</Badge></div><div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground"><span>结果 {item.result_count} 条</span><span>耗时 {item.duration_ms} ms</span><span>重试 {item.retry_count} 次</span><span>连续失败 {item.consecutive_failures} 次</span></div><p className="mt-3 text-xs leading-5 text-slate-700">覆盖：{item.coverage_countries.length ? item.coverage_countries.join("、") : "当前范围无覆盖"} · {item.update_frequency || "更新频率待确认"}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">最近执行：{dateText(item.last_attempt_at)} · 最近成功：{dateText(item.last_success_at)}</p>{item.last_error && <p className="mt-2 rounded-lg bg-rose-50 p-2 text-xs leading-5 text-rose-800">{item.last_error_category || "失败"}：{item.last_error}</p>}<p className="mt-2 text-xs text-muted-foreground">{item.quota_summary}</p></article>)}</div> : <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">尚无真实来源运行记录。先确认监控的 HS/CN 编码，再点击“立即执行”。</div>}</CardContent>
      </Card>

      <Card className="gap-4 py-5 shadow-none">
        <CardHeader className="px-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><CardTitle className="text-lg">机会候选人工复核</CardTitle><p className="mt-1 text-sm text-muted-foreground">只有跨来源、跨证据类型且包含贸易/采购/内部结果的监控才会出现在这里；分类是待验证假设，不是结论。</p></div><Button variant="outline" onClick={onOpenPrograms}>验证项目与轮次</Button></div></CardHeader>
        <CardContent className="px-5">{data?.candidates.length ? <div className="grid gap-3 lg:grid-cols-2">{data.candidates.map((item) => <article key={item.id} className="rounded-2xl border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">{item.title}</h3><p className="mt-1 text-xs text-muted-foreground">{item.monitor_name} · 更新 {dateText(item.updated_at)}</p></div><div className="flex gap-1"><Badge variant="outline">{OPPORTUNITY_TYPE_LABELS[item.opportunity_type] ?? item.opportunity_type}</Badge><Badge variant={item.status === "pending_review" ? "secondary" : "outline"}>{CANDIDATE_STATUS_LABELS[item.status] ?? item.status}</Badge></div></div><p className="mt-3 text-sm leading-6">{item.summary}</p><p className="mt-2 text-xs leading-5 text-muted-foreground">{item.rationale}</p><div className="mt-3 flex flex-wrap gap-2 text-xs"><Badge variant="outline">可靠证据 {item.evidence_count}</Badge><Badge variant="outline">独立来源 {item.source_count}</Badge>{item.product_family_name && <Badge variant="outline">{item.product_family_name}</Badge>}</div><p className="mt-3 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-700">下一步：{item.next_action}</p><div className="mt-3 flex flex-wrap gap-2"><Button size="sm" disabled={busy} onClick={() => void reviewCandidate(item, "accepted")}><Check /> 接受候选</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => void reviewCandidate(item, "observing")}><Eye /> 继续观察</Button><Button size="sm" variant="ghost" className="text-rose-700" disabled={busy} onClick={() => void reviewCandidate(item, "passed")}><XCircle /> Pass</Button></div>{item.review_note && <p className="mt-2 text-xs text-muted-foreground">复核备注：{item.review_note}</p>}</article>)}</div> : <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">尚无达到人工复核门槛的候选。事件或热度信号不会单独生成机会。</div>}</CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="gap-4 py-5 shadow-none"><CardHeader className="px-5"><div className="flex items-center justify-between gap-3"><div><CardTitle className="text-lg">事件日历</CardTitle><p className="mt-1 text-sm text-muted-foreground">记录可核验的采购窗口；事件只是触发信号，仍需贸易或采购证据交叉验证。</p></div><Button variant="outline" onClick={() => { setFormMessage(""); setEventOpen(true); }}><CalendarPlus /> 新增事件</Button></div></CardHeader><CardContent className="px-5">{data?.events.length ? <div className="space-y-3">{data.events.slice(0, 8).map((item) => <article key={item.id} className="rounded-xl border p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{item.name}</p><p className="mt-1 text-xs text-muted-foreground">{item.region_name || item.region_code} · {data.triggerCatalog.find((triggerItem) => triggerItem.id === item.trigger_type)?.name ?? item.trigger_type} · {dateText(item.starts_at)}</p></div><Button size="sm" variant="ghost" disabled={busy} onClick={() => void archiveEvent(item)}><Archive /> 归档</Button></div><p className="mt-2 text-xs leading-5 text-slate-700">采购提前期 {item.procurement_lead_days} 天{item.delivery_cutoff ? ` · 最晚交付 ${dateText(item.delivery_cutoff)}` : ""}</p><a className="mt-2 inline-block text-xs text-cyan-800 underline" href={item.source_url} target="_blank" rel="noreferrer">{item.source_name}</a></article>)}</div> : <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">尚无事件。可录入返校季、赛事、法规生效日、展会或供应中断等有来源的窗口。</div>}</CardContent></Card>
        <Card className="gap-4 py-5 shadow-none"><CardHeader className="px-5"><CardTitle className="text-lg">监控运行历史</CardTitle><p className="text-sm text-muted-foreground">每次运行单独留痕；灰度运行与正式信号隔离，等待数据不等于失败。</p></CardHeader><CardContent className="px-5">{data?.runs.length ? <div className="space-y-3">{data.runs.slice(0, 10).map((run) => <article key={run.id} className="rounded-xl border p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{run.monitor_name}</p><p className="mt-1 text-xs text-muted-foreground">{run.trigger_reason === "schedule" ? "定时执行" : run.trigger_reason === "simulation" ? "灰度模拟" : "人工执行"} · {dateText(run.created_at)}</p></div><div className="flex gap-1">{run.result_json.simulation && <Badge variant="outline">隔离测试</Badge>}<Badge variant={run.status === "completed" ? "secondary" : "outline"}>{RUN_STATUS_LABELS[run.status] ?? run.status}</Badge></div></div><p className="mt-2 text-xs text-muted-foreground">{run.result_json.simulation ? `模拟 ${run.signal_count} 条证据` : `关联 ${run.signal_count} 条去重信号`} · {run.duration_ms} ms · 重试 {run.retry_count} 次{run.error_category ? ` · ${run.error_category}` : ""}{run.error ? ` · ${run.error}` : ""}</p>{run.result_json.blockers?.length ? <p className="mt-2 text-xs leading-5 text-amber-800">仍缺：{run.result_json.blockers.join("；")}</p> : null}</article>)}</div> : <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">尚无运行记录。执行监控后会记录来源计划、结果、缺口和错误。</div>}</CardContent></Card>
      </div>

      <Card className="gap-4 py-5 shadow-none">
        <CardHeader className="px-5"><CardTitle className="text-lg">七层市场信号</CardTitle><p className="text-sm text-muted-foreground">不同证据回答不同问题，不能混成一个“热度分”。</p></CardHeader>
        <CardContent className="grid gap-3 px-5 md:grid-cols-2 xl:grid-cols-4">{data?.signalLayers.map((layer) => <div key={layer.id} className="rounded-2xl border p-4"><div className="flex items-center justify-between gap-2"><h3 className="font-semibold">{layer.name}</h3><Badge variant="outline">{data.signals.filter((signal) => signal.signal_type === layer.id).length}</Badge></div><p className="mt-2 text-sm leading-6 text-muted-foreground">{layer.description}</p><p className="mt-3 text-xs leading-5 text-cyan-900">用于：{layer.decisionUse}</p><p className="mt-2 text-xs leading-5 text-amber-800">边界：{layer.warning}</p></div>)}</CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,.75fr)]">
        <Card className="gap-4 py-5 shadow-none"><CardHeader className="px-5"><div className="flex items-center justify-between gap-3"><div><CardTitle className="text-lg">最近信号</CardTitle><p className="mt-1 text-sm text-muted-foreground">只有来源、地区、期间和状态完整的证据才进入判断。</p></div><Button variant="outline" onClick={onOpenRadar}>查看雷达</Button></div></CardHeader><CardContent className="px-5">{data?.signals.length ? <div className="space-y-3">{data.signals.slice(0, 8).map((signal) => <article key={signal.id} className="rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="font-medium">{signal.title}</p><p className="mt-1 text-xs text-muted-foreground">{signal.source_name} · {signal.region_name || "未指定地区"} · {dateText(signal.collected_at)}</p></div><Badge variant="outline">{data.signalLayers.find((layer) => layer.id === signal.signal_type)?.name ?? signal.signal_type}</Badge></div>{signal.summary && <p className="mt-3 text-sm leading-6 text-slate-700">{signal.summary}</p>}</article>)}</div> : <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">尚无统一信号记录。建立监控后，官方贸易、平台导入和内部业务结果会按层进入这里。</div>}</CardContent></Card>
        <Card className="gap-4 py-5 shadow-none"><CardHeader className="px-5"><CardTitle className="flex items-center gap-2 text-lg"><Bot className="size-5 text-cyan-800" /> 第一轮决策链</CardTitle></CardHeader><CardContent className="space-y-3 px-5">{["信号触发：发现地区与采购时机", "市场核验：进口规模、增长、竞争和法规", "画像匹配：买家关注点、场景与渠道", "矩阵筛选：默认最多 5 个关联产品家族", "真实验证：客户回复、同规格报价和合规利润", "轮次决策：继续、调整、补证据、暂停或 Pass"].map((item, index) => <div key={item} className="flex gap-3 rounded-xl border p-3"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-cyan-950 text-xs font-semibold text-white">{index + 1}</span><p className="text-sm leading-6">{item}</p></div>)}<Button className="mt-2 w-full" onClick={onOpenPrograms}>进入验证项目与轮次</Button></CardContent></Card>
      </div>

      <Card className="gap-4 border-cyan-200 bg-cyan-50/40 py-5 shadow-none"><CardHeader className="px-5"><CardTitle className="text-lg">统一数据源与连接中心</CardTitle><p className="text-sm text-muted-foreground">贸易数据、B2B 平台、搜索、内容平台和内部业务只维护一份连接状态。情报站按监控范围引用，不再复制第二套来源卡片。</p></CardHeader><CardContent className="flex flex-wrap items-center justify-between gap-3 px-5"><p className="max-w-3xl text-sm leading-6 text-cyan-950">P0 先验证官方贸易与内部结果；P1 验证采购和供应；P2 只用于发现注意力变化。未授权来源会明确停在“等待授权/导入”，不会显示为采集成功。</p><Button onClick={onOpenSources}><Database /> 管理全部数据源</Button></CardContent></Card>

      <Dialog open={simulationOpen} onOpenChange={(open) => { if (!busy) { setSimulationOpen(open); if (!open) setFormMessage(""); } }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>监控灰度测试台</DialogTitle>
            <DialogDescription>对“{simulationMonitor?.name ?? "当前监控"}”运行隔离场景。使用与正式监控相同的证据闸门，但不写入正式信号、机会候选、评分或验证项目。</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <label className="space-y-1.5 text-sm">测试场景<Select value={simulationScenario} onValueChange={(value) => { setSimulationScenario(value as MonitorSimulationScenario); setSimulationResult(null); }}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{MONITOR_SIMULATION_SCENARIOS.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <p className="rounded-xl border bg-slate-50 p-3 text-sm leading-6 text-muted-foreground">{MONITOR_SIMULATION_SCENARIOS.find((item) => item.id === simulationScenario)?.description}</p>
            {simulationResult && (
              <div className="space-y-3 rounded-2xl border border-cyan-200 bg-cyan-50/40 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2"><div><p className="font-medium">模拟结果</p><p className="mt-1 text-sm text-muted-foreground">{simulationResult.nextAction}</p></div><Badge variant={simulationResult.assessment.readyForReview ? "secondary" : "outline"}>{simulationResult.assessment.readyForReview ? OPPORTUNITY_TYPE_LABELS[simulationResult.assessment.opportunityType] ?? "达到候选门槛" : "未进入候选"}</Badge></div>
                <div className="space-y-2">{simulationResult.pipelineSteps.map((step, index) => <div key={step.id} className="flex gap-3 rounded-xl border bg-white p-3"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-cyan-950 text-xs font-semibold text-white">{index + 1}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">{step.name}</p><Badge variant="outline">{SIMULATION_STEP_STATUS_LABELS[step.status]}</Badge></div><p className="mt-1 text-xs leading-5 text-muted-foreground">{step.detail}</p></div></div>)}</div>
                <p className="text-xs leading-5 text-cyan-900">{simulationResult.isolation}</p>
              </div>
            )}
          </div>
          {formMessage && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{formMessage}</p>}
          <DialogFooter><Button variant="outline" onClick={() => setSimulationOpen(false)} disabled={busy}>关闭</Button><Button onClick={() => void runSimulation()} disabled={busy}>{busy ? "正在模拟…" : simulationResult ? "重新测试" : "开始灰度测试"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={sourceConfigOpen} onOpenChange={(open) => { if (!busy) { setSourceConfigOpen(open); if (!open) setFormMessage(""); } }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>确认官方来源与商品口径</DialogTitle><DialogDescription>为“{sourceConfigMonitor?.name ?? "当前监控"}”配置真实查询范围。商品编码是官方贸易接口的必要条件；保存后监控会进入待执行队列。</DialogDescription></DialogHeader>
          <div className="space-y-4 py-2">
            <label className="space-y-1.5 text-sm">HS/CN 编码（逗号、空格或换行分隔）<Textarea value={sourceConfigCodes} onChange={(event) => setSourceConfigCodes(event.target.value)} placeholder="例如：85, 8517, 8471；支持 2/4/6/8 位，最多 12 个" /><p className="text-xs leading-5 text-muted-foreground">产品可能对应多个编码时，应先确认业务口径。系统不会用关键词猜测并直接写入正式数据。</p></label>
            <div className="space-y-2"><p className="text-sm">启用的官方来源</p><div className="grid gap-2 sm:grid-cols-3">{Object.entries(SOURCE_NAMES).map(([sourceId, name]) => <Button key={sourceId} type="button" variant={sourceConfigIds.includes(sourceId) ? "default" : "outline"} className="justify-start" onClick={() => toggleSourceConfig(sourceId)}>{sourceConfigIds.includes(sourceId) && <Check />} {name}</Button>)}</div></div>
            <div className="rounded-xl border bg-slate-50 p-3 text-xs leading-5 text-slate-700">UN Comtrade 覆盖监控中的国家；Eurostat 只查询其支持的欧洲报告国；HMRC 仅适用于英国或全球监控。不适用会单独标记，不会记为失败。</div>
          </div>
          {formMessage && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{formMessage}</p>}
          <DialogFooter><Button variant="outline" onClick={() => setSourceConfigOpen(false)} disabled={busy}>取消</Button><Button onClick={() => void saveSourceConfig()} disabled={busy}>{busy ? "正在保存…" : "保存并等待执行"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={(open) => { if (!busy) { setCreateOpen(open); if (open) setFormMessage(""); } }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader><DialogTitle>建立市场信号监控</DialogTitle><DialogDescription>监控规则用于持续发现候选，不会自动生成验证项目。相同地区、事件、画像和产品范围只能有一条活动记录。</DialogDescription></DialogHeader>
          <div className="grid gap-4 py-2 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm">监控名称（可选）<Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：英国返校季办公用品" /></label>
            <label className="space-y-1.5 text-sm">目标地区<Select value={draft.regionCode} onValueChange={(value) => setDraft({ ...draft, regionCode: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{data?.taxonomy.regions.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="space-y-1.5 text-sm sm:col-span-2">采购触发事件<Select value={draft.triggerType} onValueChange={(value) => setDraft({ ...draft, triggerType: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{triggersByCategory.map(([category, items]) => <SelectGroup key={category}><SelectLabel>{TRIGGER_CATEGORY_LABELS[category]}</SelectLabel>{items.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectGroup>)}</SelectContent></Select>{selectedTrigger && <p className="text-xs leading-5 text-muted-foreground">{selectedTrigger.description}</p>}</label>
            <label className="space-y-1.5 text-sm">关联画像（可后补）<Select value={draft.personaCode} onValueChange={(value) => setDraft({ ...draft, personaCode: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">暂不限定画像</SelectItem>{data?.taxonomy.personas.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="space-y-1.5 text-sm">关联产品家族（可后补）<Select value={draft.productFamilyCode} onValueChange={(value) => setDraft({ ...draft, productFamilyCode: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">先从事件发现产品</SelectItem>{data?.taxonomy.productFamilies.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="space-y-1.5 text-sm sm:col-span-2">监控关键词（逗号或换行分隔）<Textarea value={draft.keywords} onChange={(event) => setDraft({ ...draft, keywords: event.target.value })} placeholder="产品、用途、事件、采购词；若已选择产品家族可留空" /></label>
            <label className="space-y-1.5 text-sm sm:col-span-2">HS/CN 编码（可后补）<Input value={draft.commodityCodes} onChange={(event) => setDraft({ ...draft, commodityCodes: event.target.value })} placeholder="例如：85, 8517, 8471；支持 2/4/6/8 位" /><p className="text-xs leading-5 text-muted-foreground">未填写时可以先建立监控和做灰度测试，但正式官方贸易采集会等待你确认编码。</p></label>
            <div className="space-y-2 sm:col-span-2"><p className="text-sm">官方贸易来源</p><div className="grid gap-2 sm:grid-cols-3">{Object.entries(SOURCE_NAMES).map(([sourceId, name]) => <Button key={sourceId} type="button" variant={draft.sourceIds.includes(sourceId) ? "default" : "outline"} className="justify-start" onClick={() => toggleDraftSource(sourceId)}>{draft.sourceIds.includes(sourceId) && <Check />} {name}</Button>)}</div></div>
            <label className="space-y-1.5 text-sm">复查频率<Select value={draft.cadenceDays} onValueChange={(value) => setDraft({ ...draft, cadenceDays: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="1">每天</SelectItem><SelectItem value="3">每 3 天</SelectItem><SelectItem value="7">每 7 天</SelectItem><SelectItem value="14">每 14 天</SelectItem><SelectItem value="30">每 30 天</SelectItem></SelectContent></Select></label>
            <div className="rounded-xl border bg-slate-50 p-3 text-sm"><p className="font-medium">默认采集层</p><div className="mt-2 flex flex-wrap gap-1.5">{selectedTrigger?.defaultSignalTypes.map((type) => <Badge key={type} variant="outline">{data?.signalLayers.find((layer) => layer.id === type)?.name ?? type}</Badge>)}</div></div>
          </div>
          {formMessage && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{formMessage}</p>}
          <DialogFooter><Button variant="outline" onClick={() => setCreateOpen(false)} disabled={busy}>取消</Button><Button onClick={() => void createMonitor()} disabled={busy}>{busy ? "正在保存…" : "建立监控"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={importOpen} onOpenChange={(open) => { if (!busy) { setImportOpen(open); if (!open) setFormMessage(""); } }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader><DialogTitle>导入可核验市场信号</DialogTitle><DialogDescription>用于已授权的平台导出、官方公开数据或人工核验记录。系统按来源、地区、产品、期间和指标去重，并保留每次更新版本。</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <label className="space-y-1.5 text-sm">关联活动监控<Select value={importMonitorId} onValueChange={setImportMonitorId}><SelectTrigger><SelectValue placeholder="选择监控" /></SelectTrigger><SelectContent>{data?.monitors.filter((item) => item.status === "active").map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="space-y-1.5 text-sm">JSON 信号数组<Textarea className="min-h-80 font-mono text-xs" value={importText} onChange={(event) => setImportText(event.target.value)} spellCheck={false} /></label>
            <div className="rounded-xl border bg-slate-50 p-3 text-xs leading-5 text-slate-700">外部证据必须包含可打开的 http/https 来源链接。缺失或受阻记录必须说明原因且不能填写数值；只有 attention/event 不会生成机会候选。</div>
          </div>
          {formMessage && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{formMessage}</p>}
          <DialogFooter><Button variant="outline" onClick={() => setImportOpen(false)} disabled={busy}>取消</Button><Button onClick={() => void importSignals()} disabled={busy}>{busy ? "正在导入…" : "校验、去重并导入"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={eventOpen} onOpenChange={(open) => { if (!busy) { setEventOpen(open); if (!open) setFormMessage(""); } }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader><DialogTitle>新增采购触发事件</DialogTitle><DialogDescription>记录时间窗口、采购提前期和原始来源。相同名称、地区、类型和日期会更新原事件，不会重复建立。</DialogDescription></DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm sm:col-span-2">事件名称<Input value={eventDraft.name} onChange={(event) => setEventDraft({ ...eventDraft, name: event.target.value })} placeholder="例如：2027 女足世界杯" /></label>
            <label className="space-y-1.5 text-sm">地区<Select value={eventDraft.regionCode} onValueChange={(value) => setEventDraft({ ...eventDraft, regionCode: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{data?.taxonomy.regions.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="space-y-1.5 text-sm">触发类型<Select value={eventDraft.triggerType} onValueChange={(value) => setEventDraft({ ...eventDraft, triggerType: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{triggersByCategory.map(([category, items]) => <SelectGroup key={category}><SelectLabel>{TRIGGER_CATEGORY_LABELS[category]}</SelectLabel>{items.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectGroup>)}</SelectContent></Select></label>
            <label className="space-y-1.5 text-sm">开始时间<Input type="datetime-local" value={eventDraft.startsAt} onChange={(event) => setEventDraft({ ...eventDraft, startsAt: event.target.value })} /></label>
            <label className="space-y-1.5 text-sm">结束时间（可选）<Input type="datetime-local" value={eventDraft.endsAt} onChange={(event) => setEventDraft({ ...eventDraft, endsAt: event.target.value })} /></label>
            <label className="space-y-1.5 text-sm">建议采购提前期（天）<Input type="number" min={0} max={730} value={eventDraft.procurementLeadDays} onChange={(event) => setEventDraft({ ...eventDraft, procurementLeadDays: event.target.value })} /></label>
            <label className="space-y-1.5 text-sm">最晚交付时间（可选）<Input type="datetime-local" value={eventDraft.deliveryCutoff} onChange={(event) => setEventDraft({ ...eventDraft, deliveryCutoff: event.target.value })} /></label>
            <label className="space-y-1.5 text-sm">来源名称<Input value={eventDraft.sourceName} onChange={(event) => setEventDraft({ ...eventDraft, sourceName: event.target.value })} placeholder="赛事官网、政府公告、法规原文" /></label>
            <label className="space-y-1.5 text-sm">来源链接<Input type="url" value={eventDraft.sourceUrl} onChange={(event) => setEventDraft({ ...eventDraft, sourceUrl: event.target.value })} placeholder="https://…" /></label>
            <label className="space-y-1.5 text-sm sm:col-span-2">说明与采购影响<Textarea value={eventDraft.notes} onChange={(event) => setEventDraft({ ...eventDraft, notes: event.target.value })} placeholder="记录可能影响的场景和限制，不要把事件直接写成采购需求。" /></label>
          </div>
          {formMessage && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{formMessage}</p>}
          <DialogFooter><Button variant="outline" onClick={() => setEventOpen(false)} disabled={busy}>取消</Button><Button onClick={() => void saveEvent()} disabled={busy}>{busy ? "正在保存…" : "保存事件"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
