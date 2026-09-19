"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Archive,
  Bookmark,
  BookmarkCheck,
  Bot,
  CalendarClock,
  Check,
  ChevronsUpDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Database,
  Download,
  Eye,
  ExternalLink,
  FileUp,
  FlaskConical,
  History,
  ImageIcon,
  KeyRound,
  LayoutDashboard,
  ListFilter,
  Plus,
  Radar,
  Search,
  Sparkles,
  Target,
  Trash2,
  TrendingUp,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  LANGUAGE_CODES,
  LANGUAGE_OPTIONS,
  MARKET_CODES,
  MARKET_GROUPS,
  SUPPORTED_LANGUAGES,
  SUPPORTED_MARKETS,
  defaultLanguageForMarket,
  languageNameForCode,
  marketNameForCode,
} from "@/lib/markets";
import { CORE_PLATFORMS, VALID_PLATFORMS } from "@/lib/radar";
import { platformCredentialId } from "@/lib/platform-connections";
import {
  CHANNEL_FIT_FIELDS,
  SELECTION_GATE_FIELDS,
  SELECTION_SCORE_FIELDS,
  candidateHandoffReadiness,
  emptyCandidateSelectionAssessment,
  normalizeCandidateSelectionAssessment,
  type CandidateSelectionAssessment,
  type ChannelFitKey,
  type SelectionGateKey,
  type SelectionScoreKey,
} from "@/lib/candidate-selection";
import { buildProductFamilySummaries } from "@/lib/product-family";
import { matchesResearchCandidateFilters } from "@/lib/research-candidate-filters";
import { CHATGPT_TRADE_WORKFLOW, TRADE_SOURCE_AUTOMATION_LABELS, TRADE_SOURCE_CATALOG, USER_TRADE_RESPONSIBILITIES } from "@/lib/trade-source-catalog";
import { latestResearchReportRun } from "@/lib/research-versions";
import { IntelligenceStation } from "@/components/intelligence-station";
import { OpportunityCenter } from "@/components/opportunity-center";
import type { OpportunityProgramSeed } from "@/components/opportunity-programs";

type KeywordRow = {
  id: string;
  keyword: string;
  group: string;
  aliases: string[];
  heat: number | null;
  momentum: number | null;
  commercial: number | null;
  intent: number;
  competition: number | null;
  opportunity: number | null;
  confidence: number;
  lifecycle: "新兴" | "热门" | "成熟" | "观察" | "衰退";
  direction: "up" | "down" | "flat";
  status: "候选" | "观察" | "排除";
  rationale: string;
};

type ApiResult = {
  cluster_id: string;
  canonical_keyword: string;
  group_name: string;
  aliases: string[];
  category: string;
  market: string;
  language: string;
  cluster_status: "candidate" | "watching" | "excluded";
  attention_level: number | null;
  momentum: number | null;
  buyer_intent: number;
  commercial_validation: number | null;
  competition: number | null;
  heat: number | null;
  opportunity: number | null;
  confidence: number;
  lifecycle: string;
  rationale: string;
  anomaly_flags: string[];
  score_version: string;
  conservative_opportunity?: number | null;
  observation_count?: number;
  valid_observation_count?: number;
  platforms?: string[];
  image_url?: string | null;
  image_urls?: string[];
  images?: ApiProductImage[];
  keyword_zh?: string | null;
  purchase_price_min?: number | null;
  purchase_price_max?: number | null;
  purchase_price_currency?: string | null;
  purchase_price_unit?: string | null;
  geo_scopes?: string[];
};

type ApiProductImage = {
  url: string;
  platform: string;
  source_ref: string;
  verified_source: boolean;
};

type ApiSource = {
  platform: string;
  coverage: number;
  collected_at: string;
  statuses: string[];
  cluster_count: number;
  observation_count: number;
  source_kinds: string[];
  source_refs: string[];
};

type ApiHistory = {
  id: string;
  mode: string;
  query: string;
  market: string;
  language: string;
  window_days: number;
  status: string;
  is_demo: number;
  created_at: string;
  completed_at?: string | null;
  cluster_count: number;
  heat: number | null;
  opportunity: number | null;
  confidence: number | null;
  observation_count: number;
  valid_observation_count: number;
  platform_count: number;
  source_summary: Record<string, unknown>;
};

type ApiIntegration = {
  id: string;
  name: string;
  role: string;
  registerUrl: string;
  docsUrl: string;
  envVars: string[];
  cost: string;
  accessNote: string;
  publicMode?: string | null;
  automaticCollection: boolean;
  configured: boolean;
};

type ManagedCredentialStatus = {
  id: string;
  name: string;
  configured: boolean;
  source: "managed" | "environment" | "public" | null;
  storageReady: boolean;
  updatedAt: string | null;
  lastTestAt: string | null;
  lastTestStatus: "ok" | "error" | "rate_limited" | "unverified" | null;
  lastTestMessage: string;
  registerUrl: string;
  docsUrl: string;
  instructions: string;
  fields: Array<{
    id: string;
    label: string;
    type: "text" | "password" | "url";
    placeholder: string;
    required: boolean;
  }>;
  testable: boolean;
  publicAccess: boolean;
  healthStatus: "never_run" | "completed" | "no_data" | "failed" | "not_applicable";
  coverageCountries: string[];
  quotaSummary: string;
  updateFrequency: string;
  lastAttemptAt: string | null;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  lastErrorCategory: string;
  lastError: string;
  consecutiveFailures: number;
  resultCount: number;
  durationMs: number;
  retryCount: number;
};

const SOURCE_HEALTH_LABELS: Record<ManagedCredentialStatus["healthStatus"], string> = {
  never_run: "尚未实采",
  completed: "最近采集成功",
  no_data: "请求成功但无数据",
  failed: "最近采集失败",
  not_applicable: "当前监控不适用",
};

type ApiObservation = {
  id: string;
  cluster_id: string;
  platform: string;
  metric: string;
  current_value: number | null;
  previous_value: number | null;
  sample_n: number | null;
  unique_actor_n: number | null;
  coverage_days: number;
  source_kind: string;
  source_ref: string;
  geo_scope: string;
  status: string;
  missing_reason: string | null;
  collected_at: string;
};

type ApiRunDetail = {
  run: {
    id: string;
    mode: string;
    query: string;
    market: string;
    language: string;
    window_days: number;
    status: string;
    created_at: string;
    completed_at?: string | null;
    source_summary: Record<string, unknown>;
  };
  results: ApiResult[];
  observations: ApiObservation[];
};

type ApiWatch = {
  id: string;
  cluster_id: string;
  canonical_keyword: string;
  group_name: string;
  market: string;
  cadence_days: number;
  next_run_at: string | null;
  enabled: number;
};

type ResearchTemplate = {
  id: string;
  name: string;
  description: string;
};

type ResearchProject = {
  id: string;
  product_name: string;
  product_category: string;
  product_description: string;
  target_markets: string[];
  languages: string[];
  channels: string[];
  template_id: string;
  target_candidate_count: number;
  objectives: string;
  constraints: string;
  status: "planning" | "queued" | "researching" | "needs_review" | "completed" | "archived";
  current_stage: string;
  progress: number;
  summary: string;
  recommendation: "pending" | "go" | "test" | "hold" | "reject";
  scorecard: Record<string, number>;
  created_at: string;
  updated_at: string;
  last_researched_at?: string | null;
  run_count: number;
  evidence_count: number;
  candidate_count: number;
  latest_run_id?: string | null;
  latest_run_status?: string | null;
};

type ResearchRun = {
  id: string;
  project_id: string;
  status: string;
  request_payload: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  source_summary: Record<string, unknown>;
  created_at: string;
  completed_at?: string | null;
};

type ResearchEvidence = {
  id: string;
  run_id: string;
  section_key: string;
  source_type: string;
  source_title: string;
  source_url: string;
  market: string;
  status: string;
  excerpt: string;
  captured_at: string;
};

type ResearchCandidate = {
  id: string;
  project_id: string;
  name: string;
  track_category: string;
  subcategory: string;
  product_family: string;
  commercial_variant: string;
  image_urls: string[];
  image_source_ref: string;
  target_markets: string[];
  buyer_types: string[];
  price_band: string;
  moq: string;
  compliance: string[];
  risk_level: "low" | "medium" | "high" | "unknown";
  stage: "idea" | "research" | "sample" | "validation" | "shortlist" | "validated" | "rejected";
  score: number | null;
  rationale: string;
  evidence_status: "hypothesis" | "partial" | "validated";
  selection_assessment: CandidateSelectionAssessment;
  handoff_readiness: { ready: boolean; blockers: string[]; score: number; assessment: CandidateSelectionAssessment };
  odoo_sync_state: string;
  odoo_external_id: string;
  odoo_synced_at: string | null;
  updated_at: string;
};

type ResearchCandidateActivity = {
  id: string;
  project_id: string;
  candidate_id: string;
  from_stage: ResearchCandidate["stage"];
  to_stage: ResearchCandidate["stage"];
  note: string;
  evidence_url: string;
  next_action: string;
  follow_up_at: string;
  recommended_stage: ResearchCandidate["stage"] | "";
  created_by: "user" | "ai";
  created_at: string;
};

type ResearchMarketStatus = "hypothesis" | "partial" | "validated" | "rejected";

type ResearchMarketActivity = {
  id: string;
  project_id: string;
  market_code: string;
  from_status: ResearchMarketStatus;
  to_status: ResearchMarketStatus;
  note: string;
  evidence_url: string;
  next_action: string;
  follow_up_at: string;
  created_by: "user" | "ai";
  created_at: string;
};

type ResearchMarketHypothesis = Record<string, unknown> & {
  marketCode?: string;
  marketName?: string;
  validationStatus?: ResearchMarketStatus;
};

type ResearchBuyerProfile = {
  id: string;
  project_id: string;
  company_name: string;
  website: string;
  country: string;
  buyer_type: string;
  customer_groups: string[];
  sales_channels: string[];
  purchasing_scenarios: string[];
  seasonality: string;
  replenishment_cycle: string;
  order_requirements: string;
  source_url: string;
  profile_status: "hypothesis" | "qualified" | "validated" | "rejected";
  odoo_lead_id: number | null;
  created_by: "user" | "ai";
  updated_at: string;
};

type ResearchBuyerFamilyLink = {
  id: string;
  project_id: string;
  buyer_profile_id: string;
  track_category: string;
  product_family: string;
  relationship_score: number;
  family_role: "core" | "cross_sell" | "seasonal" | "test";
  sales_scenarios: string[];
  rationale: string;
  evidence_status: "hypothesis" | "partial" | "validated";
  created_by: "user" | "ai";
  updated_at: string;
};

type GlobalBuyerProfile = Omit<ResearchBuyerProfile, "project_id" | "odoo_lead_id"> & {
  source_project_count: number;
  last_verified_at?: string | null;
  persona_code: string;
  region_code: string;
};

type GlobalBuyerFamilyLink = Omit<ResearchBuyerFamilyLink, "project_id">;

type GlobalProductFamily = {
  track_category: string;
  product_family: string;
  candidate_count: number;
  project_count: number;
  target_markets: string[];
  buyer_types: string[];
  product_examples: string[];
};

type TradeRegion = {
  code: string;
  name: string;
  macro_region: string;
  m49_code: string;
  countries: string[];
  characteristics: string[];
  source_url: string;
  created_by: string;
  updated_at: string;
};

type BuyerPersonaCategory = {
  code: string;
  group_name: string;
  name: string;
  description: string;
  value_chain_role: string;
  customer_groups: string[];
  sales_channels: string[];
  purchase_scenarios: string[];
  buying_triggers: string[];
  order_characteristics: string[];
  compliance_focus: string[];
  source_refs: string[];
  version: number;
  last_reviewed_at: string | null;
  active: boolean;
  created_by: string;
  updated_at: string;
};

type BuyerPersonaProposal = {
  id: string;
  run_id: string;
  mode: "discover" | "enrich";
  target_code: string;
  persona_code: string;
  payload: Record<string, unknown>;
  source_refs: string[];
  rationale: string;
  status: "pending" | "applied" | "rejected";
  created_at: string;
  reviewed_at: string | null;
};

type BuyerPersonaChange = {
  id: string;
  entity_code: string;
  action: "create" | "update" | "delete" | "restore";
  origin: "user" | "ai_assistant" | string;
  run_id: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  created_at: string;
};

type ProductTrackMaster = {
  code: string;
  name: string;
  description: string;
  buyer_value: string;
  compliance_focus: string[];
  created_by: string;
  updated_at: string;
};

type ProductFamilyMaster = {
  code: string;
  track_code: string;
  track_name: string;
  name: string;
  description: string;
  use_scenarios: string[];
  compliance_tags: string[];
  keywords: string[];
  created_by: string;
  updated_at: string;
};

type PersonaProductMatrix = {
  id: string;
  persona_code: string;
  region_code: string;
  track_code: string;
  product_family_code: string;
  relevance_score: number;
  family_role: ResearchBuyerFamilyLink["family_role"];
  sales_scenarios: string[];
  seasonality: string;
  rationale: string;
  evidence_status: ResearchBuyerFamilyLink["evidence_status"];
  created_by: string;
  updated_at: string;
};

type GlobalBuyerLibrary = {
  profiles: GlobalBuyerProfile[];
  links: GlobalBuyerFamilyLink[];
  families: GlobalProductFamily[];
  taxonomy: {
    regions: TradeRegion[];
    personaCategories: BuyerPersonaCategory[];
    retiredPersonaCategories: BuyerPersonaCategory[];
    productTracks: ProductTrackMaster[];
    productFamilies: ProductFamilyMaster[];
    personaMatrix: PersonaProductMatrix[];
  };
  personaProposals: BuyerPersonaProposal[];
  personaChanges: BuyerPersonaChange[];
  stats: {
    profileCount: number;
    familyLinkCount: number;
    familyCount: number;
    marketCount: number;
    validatedCount: number;
    regionCount: number;
    personaCategoryCount: number;
    retiredPersonaCategoryCount: number;
    pendingPersonaProposalCount: number;
    trackCount: number;
    masterFamilyCount: number;
    personaMatrixCount: number;
  };
};

type ResearchBuyerDraft = {
  companyName: string;
  website: string;
  country: string;
  buyerType: string;
  personaCode: string;
  regionCode: string;
  customerGroups: string;
  salesChannels: string;
  purchasingScenarios: string;
  seasonality: string;
  replenishmentCycle: string;
  orderRequirements: string;
  sourceUrl: string;
  profileStatus: ResearchBuyerProfile["profile_status"];
  odooLeadId: string;
};

type ResearchBuyerFamilyDraft = {
  key: string;
  trackCategory: string;
  productFamily: string;
  enabled: boolean;
  relationshipScore: number;
  familyRole: ResearchBuyerFamilyLink["family_role"];
  salesScenarios: string;
  rationale: string;
  evidenceStatus: ResearchBuyerFamilyLink["evidence_status"];
};

type PersonaCategoryDraft = {
  code: string;
  groupName: string;
  name: string;
  description: string;
  valueChainRole: string;
  customerGroups: string;
  salesChannels: string;
  purchaseScenarios: string;
  buyingTriggers: string;
  orderCharacteristics: string;
  complianceFocus: string;
  sourceRefs: string;
};

type ProductTrackDraft = {
  code: string;
  name: string;
  description: string;
  buyerValue: string;
  complianceFocus: string;
};

type ProductFamilyMasterDraft = {
  code: string;
  trackCode: string;
  name: string;
  description: string;
  useScenarios: string;
  complianceTags: string;
  keywords: string;
};

type PersonaMatrixDraft = {
  personaCode: string;
  regionCode: string;
  trackCode: string;
  productFamilyCode: string;
  relevanceScore: number;
  familyRole: ResearchBuyerFamilyLink["family_role"];
  salesScenarios: string;
  seasonality: string;
  rationale: string;
  evidenceStatus: ResearchBuyerFamilyLink["evidence_status"];
};

type ResearchDashboardData = {
  projects: ResearchProject[];
  templates: ResearchTemplate[];
  sections: string[];
  buyerLibrary: GlobalBuyerLibrary;
};

type ResearchProjectDetail = {
  project: ResearchProject;
  runs: ResearchRun[];
  evidence: ResearchEvidence[];
  candidates: ResearchCandidate[];
  activities: ResearchCandidateActivity[];
  marketActivities: ResearchMarketActivity[];
  buyerProfiles: ResearchBuyerProfile[];
  buyerFamilyLinks: ResearchBuyerFamilyLink[];
  templates: ResearchTemplate[];
  sections: string[];
};

type ResearchDetailTab = "summary" | "buyers" | "tracks" | "pool" | "selection" | "markets" | "sections" | "evidence" | "versions";

type DashboardData = {
  empty: boolean;
  run?: {
    id: string;
    query: string;
    market: string;
    language: string;
    window_days: number;
    status: string;
    is_demo: number;
    mode?: string;
    created_at: string;
    source_summary?: Record<string, unknown>;
  };
  settings: Record<string, string>;
  integrations: ApiIntegration[];
  results: ApiResult[];
  sources: ApiSource[];
  history: ApiHistory[];
  observations?: ApiObservation[];
  watchlist: ApiWatch[];
  trend: Array<{ id: string; created_at: string; heat: number | null; opportunity: number | null }>;
};

type TaskCenterItem = {
  id: string;
  module: "discovery" | "research" | "personas" | "opportunities";
  task_type: CodexChannelId;
  task_label: string;
  title: string;
  subtitle: string;
  status: string;
  progress: number | null;
  result_count: number;
  target_id: string;
  created_at: string;
  completed_at: string | null;
  error: string;
};

type TaskCenterData = {
  items: TaskCenterItem[];
  stats: { total: number; pending: number; review: number; failed: number };
};

type CodexJob = {
  channelId?: CodexChannelId;
  channelTitle?: string;
  taskType?: "radar" | "research" | "candidate_assist" | "candidate_images" | "taxonomy_assist" | "trade_data" | "opportunity_validation";
  runId: string;
  projectId?: string;
  researchRunId?: string;
  query?: string;
  market?: string;
  language?: string;
  windowDays?: number;
  resultLimit?: number;
  mode?: "seed" | "discover" | "enrich";
  threadId: string;
  turnId: string | null;
  status: "starting" | "running" | "completed" | "interrupted" | "failed";
  progress?: number;
  phase?: string;
  completedItems?: number;
  startedAt: string;
  lastActivityAt?: string;
  completedAt?: string;
  error?: string;
};

type CodexChannelId = "radar" | "research" | "candidate_assist" | "candidate_images" | "taxonomy_assist" | "trade_data" | "opportunity_validation";

type CodexChannelLane = {
  id: CodexChannelId;
  title: string;
  ready: boolean;
  threadId: string | null;
  activeJob: CodexJob | null;
  lastJob: CodexJob | null;
};

type CodexChannelStatus = {
  ready: boolean;
  threadId: string | null;
  activeJob: CodexJob | null;
  lastJob: CodexJob | null;
  activeJobs?: CodexJob[];
  lastJobs?: CodexJob[];
  channels?: Partial<Record<CodexChannelId, CodexChannelLane>>;
  error?: string;
};

type WebMcpTool = {
  name: string;
  title: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations?: { readOnlyHint?: boolean; untrustedContentHint?: boolean };
  execute(input: unknown): unknown | Promise<unknown>;
};

type WebMcpContext = {
  registerTool(tool: WebMcpTool, options?: { signal?: AbortSignal }): void | Promise<void>;
};

function apiRowToKeyword(row: ApiResult): KeywordRow {
  return {
    id: row.cluster_id,
    keyword: row.canonical_keyword,
    group: row.group_name,
    aliases: row.aliases,
    heat: row.heat == null ? null : Math.round(row.heat),
    momentum: row.momentum == null ? null : Math.round(row.momentum),
    commercial: row.commercial_validation == null ? null : Math.round(row.commercial_validation),
    intent: Math.round(row.buyer_intent),
    competition: row.competition == null ? null : Math.round(row.competition),
    opportunity: row.opportunity == null ? null : Math.round(row.opportunity),
    confidence: Math.round(row.confidence),
    lifecycle: (["新兴", "热门", "成熟", "观察", "衰退"].includes(row.lifecycle) ? row.lifecycle : "观察") as KeywordRow["lifecycle"],
    direction: row.momentum == null || (row.momentum >= 45 && row.momentum <= 55) ? "flat" : row.momentum > 55 ? "up" : "down",
    status: row.cluster_status === "watching" ? "观察" : row.cluster_status === "excluded" ? "排除" : "候选",
    rationale: row.rationale,
  };
}

function relativeTime(value: string) {
  const age = Math.max(0, Date.now() - new Date(value).getTime());
  const hours = Math.floor(age / 3_600_000);
  if (hours < 1) return "刚刚";
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}

function elapsedTime(startedAt: string, completedAt?: string) {
  const elapsedSeconds = Math.max(0, Math.floor((new Date(completedAt ?? Date.now()).getTime() - new Date(startedAt).getTime()) / 1000));
  if (elapsedSeconds < 60) return `${elapsedSeconds} 秒`;
  const minutes = Math.floor(elapsedSeconds / 60);
  if (minutes < 60) return `${minutes} 分 ${elapsedSeconds % 60} 秒`;
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

function runStatusLabel(status: string, isDemo = false) {
  if (isDemo) return "演示";
  if (status === "complete") return "完成";
  if (status === "partial") return "已写回 · 部分来源可用";
  if (status === "failed") return "失败";
  if (status === "collecting") return "处理中";
  return "待采集";
}

function historyStatusKey(item: ApiHistory, isRunning: boolean) {
  if (isRunning) return "running";
  if (item.is_demo) return "demo";
  if (["complete", "partial"].includes(item.status)) return "finished";
  if (item.status === "failed") return "failed";
  return "waiting";
}

const HISTORY_STATUS_LABELS: Record<string, string> = {
  running: "执行中",
  finished: "已完成",
  waiting: "待采集",
  failed: "失败",
  demo: "演示",
};

const HISTORY_PAGE_SIZE = 8;
const CORE_PLATFORM_SET = new Set<string>(CORE_PLATFORMS);

function isSafeSourceUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function valueList(value: unknown) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function researchMarketLabel(value: string) {
  const normalized = value.trim().toUpperCase();
  return MARKET_CODES.includes(normalized) ? `${marketNameForCode(normalized)}（${normalized}）` : value;
}

function ProductImages({ images, legacySrc, alt, onPreview }: {
  images?: ApiProductImage[];
  legacySrc?: string | null;
  alt: string;
  onPreview?(index: number): void;
}) {
  const [failed, setFailed] = useState<string[]>([]);
  const candidates = (images?.length
    ? images
    : legacySrc
      ? [{ url: legacySrc, platform: "", source_ref: "", verified_source: false }]
      : [])
    .filter((image) => isSafeSourceUrl(image.url) && !failed.includes(image.url));
  if (candidates.length) {
    return (
      <button type="button" className="relative rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-600" onClick={() => onPreview?.(0)} aria-label={`放大查看${alt}，共 ${candidates.length} 张`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={candidates[0].url}
          alt={alt}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed((current) => [...current, candidates[0].url])}
          className="size-16 cursor-zoom-in rounded-lg border bg-white object-contain transition hover:border-cyan-500 hover:shadow-sm"
        />
        {candidates.length > 1 && <Badge className="absolute -bottom-1 -right-1 min-w-6 justify-center bg-cyan-950 px-1.5 text-[10px]">+{candidates.length - 1}</Badge>}
      </button>
    );
  }
  return (
    <div className="grid size-16 place-items-center rounded-lg border border-dashed bg-slate-50 text-center text-slate-400">
      <div><ImageIcon className="mx-auto size-5" /><p className="mt-1 text-[10px]">暂无图片</p></div>
    </div>
  );
}

const SOURCE_KIND_LABELS: Record<string, string> = {
  official_api: "官方 API",
  official_export: "官方导出",
  browser_sample: "浏览器抽样",
  open_source: "公开来源",
  manual_import: "手动导入",
  assistant: "AI 整理",
  demo: "演示",
};

const RUN_MODE_LABELS: Record<string, string> = {
  seed: "关键词扫描",
  discover: "热点发现",
  import: "未指定类型",
  assistant: "历史任务",
};

const PROCESSING_METHOD_LABELS: Record<string, string> = {
  assistant: "AI 整理",
  import: "文件导入",
  manual: "待采集 / 手工",
};

const RESEARCH_STAGE_META = [
  ["product_definition", "产品定义", "目标场景、关键规格、替代方案"],
  ["market_demand", "市场需求", "关键词、趋势、地域与季节"],
  ["competition_pricing", "竞品与价格", "价格带、差评空档、产品组合"],
  ["buyers_channels", "买家与渠道", "客户画像、采购触发、销售路径"],
  ["supply_moq", "供应与 MOQ", "工厂能力、样品、交期、变更控制"],
  ["compliance_logistics", "合规与物流", "准入、标签、运输与责任主体"],
  ["unit_economics", "单位经济", "采购价、运费、毛利与现金流"],
  ["recommendation_actions", "结论与行动", "进入建议、风险和下一步验证"],
] as const;

const RESEARCH_PLAYBOOK_META = [
  ["overview", "01 总览与边界", "预算、团队、目标与不做什么"],
  ["trackMap", "02 大赛道地图", "大类、细分领域和进入优先级"],
  ["candidatePool", "03 候选产品池", "按项目目标持续扩充并去重"],
  ["screening", "04 筛选机制", "评分、阶段、停止与继续条件"],
  ["marketMapping", "05 市场映射", "产品与具体国家买家对应关系"],
  ["roadmap180Days", "06 180 天路线", "30/60/90/180 天里程碑"],
  ["teamSop", "07 两人 SOP", "职责、周节奏与交接标准"],
  ["budgetAndQuoting", "08 预算与报价", "5 万元预算、成本与报价模型"],
  ["complianceSupplyChain", "09 合规供应链", "认证、MOQ、交期、物流和责任主体"],
  ["customerAcquisition", "10 获客与成交", "渠道、话术、样品、跟进和转化"],
  ["executionChecklist", "11 执行清单", "负责人、截止日、状态和复盘"],
] as const;

const RESEARCH_CHANNEL_OPTIONS = [
  ["google_trends", "Google 趋势"],
  ["social_content", "TikTok / Meta / Instagram"],
  ["alibaba", "Alibaba.com 供应"],
  ["amazon", "Amazon 市场"],
  ["ebay", "eBay 市场"],
  ["walmart", "Walmart 市场"],
  ["temu", "Temu 市场"],
  ["shein", "SHEIN 市场"],
  ["regional_commerce", "区域电商平台"],
  ["official_regulation", "官方法规"],
  ["buyer_websites", "买家与分销商网站"],
] as const;

const RESEARCH_STATUS_LABELS: Record<string, string> = {
  planning: "待开始",
  queued: "等待 Codex",
  researching: "调研中",
  needs_review: "待复核",
  completed: "已完成",
  archived: "已归档",
};

const TASK_MODULE_META = {
  discovery: { label: "产品机会雷达", view: "dashboard", note: "关键词、触发事件与市场信号" },
  research: { label: "历史调研任务", view: "intelligence", note: "旧任务不再作为独立业务入口" },
  personas: { label: "全球买家画像", view: "personas", note: "画像提案、审核与主数据" },
  opportunities: { label: "验证项目与轮次", view: "opportunities", note: "首轮验证、客户反馈与继续 / Pass 决策" },
} as const;

const TASK_STATUS_LABELS: Record<string, string> = {
  starting: "正在启动",
  running: "执行中",
  collecting: "执行中",
  researching: "执行中",
  pending: "等待执行",
  waiting_for_codex: "等待 Codex",
  waiting_for_data: "等待数据",
  queued: "排队中",
  review: "待人工审核",
  partial: "部分完成",
  complete: "已完成",
  completed: "已完成",
  failed: "失败",
  interrupted: "已中断",
};

function taskStatusGroup(status: string) {
  if (["starting", "running", "collecting", "researching", "pending", "waiting_for_codex", "waiting_for_data", "queued"].includes(status)) return "active";
  if (["review", "partial"].includes(status)) return "review";
  if (["failed", "interrupted"].includes(status)) return "failed";
  return "completed";
}

const RESEARCH_RECOMMENDATION_LABELS: Record<string, string> = {
  pending: "待结论",
  go: "建议进入",
  test: "小单验证",
  hold: "补证据后再定",
  reject: "暂不进入",
};

const RESEARCH_CANDIDATE_STAGE_LABELS: Record<string, string> = {
  idea: "想法池",
  research: "待调研",
  shortlist: "重点候选",
  sample: "样品中",
  validation: "验证中",
  validated: "已验证",
  rejected: "已排除",
};

const RESEARCH_CANDIDATE_NEXT_ACTIONS: Record<string, string> = {
  idea: "选择赛道和目标市场",
  research: "补需求、价格与合规证据",
  shortlist: "发 RFQ、询价并开发买家",
  sample: "采购样品并完成测试",
  validation: "买家访谈或小单验证",
  validated: "进入成交、交付与复购维护",
  rejected: "停止推进；需要时可恢复",
};

const RESEARCH_CANDIDATE_NEXT_STAGE: Partial<Record<ResearchCandidate["stage"], ResearchCandidate["stage"]>> = {
  idea: "research",
  research: "shortlist",
  shortlist: "sample",
  sample: "validation",
  validation: "validated",
};

const RESEARCH_CANDIDATE_STAGE_CHECKLISTS: Record<ResearchCandidate["stage"], string[]> = {
  idea: ["明确具体产品变体和用途", "选择优先国家及目标买家", "写明进入调研的理由"],
  research: ["核实公开需求或真实买家信号", "记录采购价、MOQ和目标售价", "核对认证、物流和知识产权门槛"],
  shortlist: ["向至少3家供应商发送统一RFQ", "建立首批目标买家名单", "完成样品、运费和毛利测算"],
  sample: ["采购至少2家可比样品", "记录功能、质量、包装和交期测试", "确认最终报价与问题整改"],
  validation: ["完成买家访谈或正式报价", "记录付费样品、小单或明确拒绝原因", "形成继续、调整或排除结论"],
  validated: ["锁定通过验证的SKU与供应商", "建立正式报价、合同和交付资料", "记录复购反馈并持续更新成本"],
  rejected: ["记录排除原因和证据", "保留重新启动条件", "停止继续投入时间和预算"],
};

const RESEARCH_CANDIDATE_STAGE_EXAMPLES: Record<ResearchCandidate["stage"], { note: string; nextAction: string }> = {
  idea: { note: "【示例，请替换为真实结果】已明确产品用途、核心变体、优先国家和目标买家；尚未验证需求与采购条件。", nextAction: "核实公开需求、采购价、MOQ和合规门槛" },
  research: { note: "【示例，请替换为真实结果】已查看目标市场买家/商品页面，并联系3家供应商；A厂报价、MOQ和交期已记录，认证与物流要求仍待核验。", nextAction: "补齐3家RFQ、目标售价、毛利和合规证据" },
  shortlist: { note: "【示例，请替换为真实结果】已完成3家供应商比价、首批买家名单和样品成本测算，准备选择2家供应商打样。", nextAction: "采购2家可比样品并建立测试表" },
  sample: { note: "【示例，请替换为真实结果】已收到样品并记录功能、质量、包装、交期和问题差异，最终供应商仍待确认。", nextAction: "完成整改复测并向目标买家发送正式报价" },
  validation: { note: "【示例，请替换为真实结果】已完成买家访谈/正式报价，记录了样品或小单反馈、拒绝原因和继续条件。", nextAction: "根据真实付费信号决定通过验证或排除" },
  validated: { note: "【示例，请替换为真实结果】SKU、供应商、报价和交付资料已经锁定，并取得可复核的买家验证结果。", nextAction: "执行成交、交付并跟踪复购与成本变化" },
  rejected: { note: "【示例，请替换为真实结果】因需求不足、毛利不达标或合规成本过高停止推进；已保存证据和重新启动条件。", nextAction: "保持归档，仅在触发条件满足时重新评估" },
};

const RESEARCH_RISK_LABELS: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  unknown: "待判断",
};

const RESEARCH_VALIDATION_LABELS: Record<string, string> = {
  hypothesis: "待验证假设",
  partial: "验证中",
  validated: "已验证",
  rejected: "已否定",
};

const RESEARCH_BUYER_STATUS_LABELS: Record<ResearchBuyerProfile["profile_status"], string> = {
  hypothesis: "待核实",
  qualified: "已初筛",
  validated: "已验证",
  rejected: "已排除",
};

const RESEARCH_FAMILY_ROLE_LABELS: Record<ResearchBuyerFamilyLink["family_role"], string> = {
  core: "核心常采",
  cross_sell: "跨品类加购",
  seasonal: "季节采购",
  test: "小单测试",
};

const RESEARCH_SECTION_LABELS = Object.fromEntries(RESEARCH_STAGE_META.map(([key, label]) => [key, label]));
const RESEARCH_DETAIL_TABS = new Set<ResearchDetailTab>(["summary", "buyers", "tracks", "pool", "selection", "markets", "sections", "evidence", "versions"]);

function researchProjectPath(projectId: string, tab: ResearchDetailTab = "summary") {
  const params = new URLSearchParams({ view: "research", projectId });
  if (tab !== "summary") params.set("tab", tab);
  return `/?${params.toString()}`;
}

function researchListPath() {
  return "/?view=research";
}

function researchBadgeClass(status: string) {
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (["queued", "researching"].includes(status)) return "border-amber-200 bg-amber-50 text-amber-800";
  if (status === "needs_review") return "border-violet-200 bg-violet-50 text-violet-800";
  if (status === "archived") return "border-slate-200 bg-slate-100 text-slate-600";
  return "border-cyan-200 bg-cyan-50 text-cyan-800";
}

function emptyResearchBuyerDraft(): ResearchBuyerDraft {
  return {
    companyName: "", website: "", country: "", buyerType: "", personaCode: "", regionCode: "", customerGroups: "", salesChannels: "",
    purchasingScenarios: "", seasonality: "", replenishmentCycle: "", orderRequirements: "",
    sourceUrl: "", profileStatus: "hypothesis", odooLeadId: "",
  };
}

function emptyPersonaCategoryDraft(): PersonaCategoryDraft {
  return { code: "", groupName: "", name: "", description: "", valueChainRole: "", customerGroups: "", salesChannels: "", purchaseScenarios: "", buyingTriggers: "", orderCharacteristics: "", complianceFocus: "", sourceRefs: "" };
}

function emptyProductTrackDraft(): ProductTrackDraft {
  return { code: "", name: "", description: "", buyerValue: "", complianceFocus: "" };
}

function emptyProductFamilyMasterDraft(): ProductFamilyMasterDraft {
  return { code: "", trackCode: "", name: "", description: "", useScenarios: "", complianceTags: "", keywords: "" };
}

function emptyPersonaMatrixDraft(): PersonaMatrixDraft {
  return { personaCode: "", regionCode: "GLOBAL", trackCode: "", productFamilyCode: "", relevanceScore: 70, familyRole: "test", salesScenarios: "", seasonality: "", rationale: "", evidenceStatus: "hypothesis" };
}

function splitResearchListInput(value: string) {
  return [...new Set(value.split(/[\n,，;；]+/).map((item) => item.trim()).filter(Boolean))];
}

const SOURCE_SHORT_LABELS: Record<string, string> = {
  "Alibaba.com": "阿里",
  Instagram: "Ins",
  "Meta Ads": "Meta",
  "Google Trends": "Google",
  Amazon: "Amazon",
  Temu: "Temu",
  SHEIN: "SHEIN",
  eBay: "eBay",
  Walmart: "Walmart",
  Etsy: "Etsy",
  AliExpress: "AliExpress",
  Shopee: "Shopee",
  Lazada: "Lazada",
  "Mercado Libre": "Mercado",
  Rakuten: "Rakuten",
};

function processingMethod(item: ApiHistory) {
  const collectionMode = String(item.source_summary.collectionMode ?? "");
  if (item.mode === "assistant" || collectionMode.startsWith("assistant") || item.source_summary.generator) return "assistant";
  if (item.mode === "import" || collectionMode.includes("import")) return "import";
  return "manual";
}

function taskTypeLabel(item: ApiHistory) {
  const preservedMode = String(item.source_summary.scanMode ?? item.mode);
  return RUN_MODE_LABELS[preservedMode] ?? "未指定类型";
}

function formatPurchasePrice(item: ApiResult) {
  if (item.purchase_price_min == null || item.purchase_price_max == null || !item.purchase_price_currency) return "—";
  const formatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
  const range = item.purchase_price_min === item.purchase_price_max
    ? formatter.format(item.purchase_price_min)
    : `${formatter.format(item.purchase_price_min)}–${formatter.format(item.purchase_price_max)}`;
  return `${item.purchase_price_currency} ${range}${item.purchase_price_unit ? `/${item.purchase_price_unit}` : ""}`;
}

const OBSERVATION_STATUS_LABELS: Record<string, string> = {
  ok: "有效",
  confirmed_zero: "确认 0",
  unsupported: "口径不支持",
  auth_failed: "需要授权",
  rate_limited: "接口限流",
  collection_error: "采集失败",
  geo_unavailable: "地区不可用",
};

function parseDelimited(text: string) {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
  if (!lines.length) return [];
  const delimiter = lines[0].includes("\t") ? "\t" : lines[0].includes(";") && !lines[0].includes(",") ? ";" : ",";
  const parseLine = (line: string) => {
    const cells: string[] = [];
    let cell = "";
    let quoted = false;
    for (let index = 0; index < line.length; index += 1) {
      const character = line[index];
      if (character === '"' && quoted && line[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (character === '"') {
        quoted = !quoted;
      } else if (character === delimiter && !quoted) {
        cells.push(cell.trim());
        cell = "";
      } else {
        cell += character;
      }
    }
    cells.push(cell.trim());
    return cells;
  };
  const headers = parseLine(lines[0]);
  return lines.slice(1).map((line) => Object.fromEntries(headers.map((header, index) => [header, parseLine(line)[index] ?? ""])));
}

const subscribeToBrowser = () => () => {};
const getBrowserSnapshot = () => true;
const getServerSnapshot = () => false;

function ScoreCell({ value, inverse = false }: { value: number | null; inverse?: boolean }) {
  if (value === null) return <span className="font-medium text-slate-400">—</span>;
  const tone = inverse
    ? value >= 75
      ? "text-rose-600"
      : value >= 55
        ? "text-amber-600"
        : "text-emerald-600"
    : value >= 80
      ? "text-emerald-600"
      : value >= 60
        ? "text-amber-600"
        : "text-slate-500";
  return <span className={`font-semibold tabular-nums ${tone}`}>{value}</span>;
}

function MiniStat({
  label,
  value,
  note,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  note: string;
  icon: typeof Activity;
  accent: string;
}) {
  return (
    <Card className="gap-3 border-slate-200/80 py-4 shadow-none">
      <CardContent className="px-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
          </div>
          <span className={`grid size-9 place-items-center rounded-lg ${accent}`}>
            <Icon className="size-4" aria-hidden="true" />
          </span>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{note}</p>
      </CardContent>
    </Card>
  );
}

function MarketSelect({ value, onValueChange }: { value: string; onValueChange(value: string): void }) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger aria-label="目标市场" className="h-11 w-full border-white/25 bg-white text-slate-950 focus-visible:border-cyan-300 focus-visible:ring-cyan-300/40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="max-h-[360px]">
        {MARKET_GROUPS.map((group) => (
          <SelectGroup key={group.label}>
            <SelectLabel>{group.label}</SelectLabel>
            {group.options.map((option) => (
              <SelectItem key={option.code} value={option.code}>{option.label} · {option.code}</SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}

function LanguageSelect({ value, onValueChange }: { value: string; onValueChange(value: string): void }) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger aria-label="关键词语言" className="h-11 w-full border-white/25 bg-white text-slate-950 focus-visible:border-cyan-300 focus-visible:ring-cyan-300/40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="max-h-[360px]">
        {LANGUAGE_OPTIONS.map((option) => (
          <SelectItem key={option.code} value={option.code}>{option.label} · {option.code.toUpperCase()}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ResearchMarketMultiSelect({ value, onValueChange }: { value: string[]; onValueChange(value: string[]): void }) {
  const toggleMarket = (code: string) => {
    if (code === "GLOBAL") {
      onValueChange(value.includes("GLOBAL") ? [] : ["GLOBAL"]);
      return;
    }
    const countryValues = value.filter((item) => item !== "GLOBAL");
    onValueChange(countryValues.includes(code)
      ? countryValues.filter((item) => item !== code)
      : [...countryValues, code]);
  };
  const label = value.includes("GLOBAL")
    ? "全球 · 多地区（GLOBAL）"
    : value.length === 0
      ? "选择一个或多个国家"
      : value.length <= 2
        ? value.map((item) => `${marketNameForCode(item)}（${item}）`).join("、")
        : `已选择 ${value.length} 个国家`;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-label="选择目标国家"
          className="mt-1.5 h-10 w-full justify-between bg-white px-3 font-normal"
        >
          <span className="truncate">{label}</span>
          <ChevronsUpDown className="ml-2 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(420px,calc(100vw-2rem))] p-0">
        <Command>
          <CommandInput placeholder="搜索国家、地区或代码" />
          <CommandList>
            <CommandEmpty>没有找到对应国家</CommandEmpty>
            {MARKET_GROUPS.map((group) => (
              <CommandGroup key={group.label} heading={group.label}>
                {group.options.map((option) => {
                  const selectedMarket = value.includes(option.code);
                  return (
                    <CommandItem
                      key={option.code}
                      value={`${option.label} ${option.code} ${group.label}`}
                      onSelect={() => toggleMarket(option.code)}
                    >
                      <Check className={selectedMarket ? "opacity-100" : "opacity-0"} aria-hidden="true" />
                      <span>{option.label}</span>
                      <span className="ml-auto text-xs text-muted-foreground">{option.code}</span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function ResearchLanguageMultiSelect({ value, onValueChange }: { value: string[]; onValueChange(value: string[]): void }) {
  const toggleLanguage = (code: string) => {
    onValueChange(value.includes(code)
      ? value.filter((item) => item !== code)
      : [...value, code]);
  };
  const label = value.length === 0
    ? "选择一种或多种语言"
    : value.length <= 2
      ? value.map((item) => `${languageNameForCode(item)}（${item.toUpperCase()}）`).join("、")
      : `已选择 ${value.length} 种语言`;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-label="选择研究语言"
          className="mt-1.5 h-10 w-full justify-between bg-white px-3 font-normal"
        >
          <span className="truncate">{label}</span>
          <ChevronsUpDown className="ml-2 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(360px,calc(100vw-2rem))] p-0">
        <Command>
          <CommandInput placeholder="搜索语言或代码" />
          <CommandList>
            <CommandEmpty>没有找到对应语言</CommandEmpty>
            <CommandGroup heading="研究语言">
              {LANGUAGE_OPTIONS.map((option) => {
                const selectedLanguage = value.includes(option.code);
                return (
                  <CommandItem
                    key={option.code}
                    value={`${option.label} ${option.code}`}
                    onSelect={() => toggleLanguage(option.code)}
                  >
                    <Check className={selectedLanguage ? "opacity-100" : "opacity-0"} aria-hidden="true" />
                    <span>{option.label}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{option.code.toUpperCase()}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

type ResearchFilterOption = { value: string; label: string; searchText?: string };

function ResearchFilterMultiSelect({
  value,
  onValueChange,
  options,
  allLabel,
  searchPlaceholder,
  ariaLabel,
  exclusiveValues = [],
}: {
  value: string[];
  onValueChange(value: string[]): void;
  options: ResearchFilterOption[];
  allLabel: string;
  searchPlaceholder: string;
  ariaLabel: string;
  exclusiveValues?: string[];
}) {
  const toggleValue = (nextValue: string) => {
    if (exclusiveValues.includes(nextValue)) {
      onValueChange(value.length === 1 && value[0] === nextValue ? [] : [nextValue]);
      return;
    }
    const selectableValues = value.filter((item) => !exclusiveValues.includes(item));
    onValueChange(selectableValues.includes(nextValue)
      ? selectableValues.filter((item) => item !== nextValue)
      : [...selectableValues, nextValue]);
  };
  const selectedLabels = options.filter((option) => value.includes(option.value)).map((option) => option.label);
  const displayLabel = selectedLabels.length === 0
    ? allLabel
    : selectedLabels.length === 1
      ? selectedLabels[0]
      : `已选 ${selectedLabels.length} 项`;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" role="combobox" aria-label={ariaLabel} className="h-10 w-full justify-between bg-white px-3 font-normal">
          <span className="truncate">{displayLabel}</span>
          <ChevronsUpDown className="ml-2 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(340px,calc(100vw-2rem))] p-0">
        <Command>
          <CommandInput placeholder={searchPlaceholder} />
          <CommandList>
            <CommandEmpty>没有找到匹配选项</CommandEmpty>
            <CommandGroup>
              <CommandItem value={`全部 ${allLabel}`} onSelect={() => onValueChange([])}>
                <Check className={value.length === 0 ? "opacity-100" : "opacity-0"} aria-hidden="true" />
                <span>{allLabel}</span>
              </CommandItem>
              {options.map((option) => (
                <CommandItem key={option.value} value={`${option.label} ${option.searchText ?? ""}`} onSelect={() => toggleValue(option.value)}>
                  <Check className={value.includes(option.value) ? "opacity-100" : "opacity-0"} aria-hidden="true" />
                  <span className="truncate">{option.label}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export default function Home() {
  const [query, setQuery] = useState("solar street light");
  const [market, setMarket] = useState("US");
  const [language, setLanguage] = useState("en");
  const [windowDays, setWindowDays] = useState("30");
  const [scanMode, setScanMode] = useState<"seed" | "discover">("seed");
  const [sortBy, setSortBy] = useState("opportunity");
  const [statusFilter, setStatusFilter] = useState("all");
  const [activeView, setActiveView] = useState<"intelligence" | "dashboard" | "research" | "personas" | "opportunities" | "history" | "watchlist" | "sources">("intelligence");
  const [selected, setSelected] = useState<KeywordRow | null>(null);
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const [scanMessage, setScanMessage] = useState("正在读取本地数据…");
  const [data, setData] = useState<DashboardData | null>(null);
  const [taskCenterData, setTaskCenterData] = useState<TaskCenterData | null>(null);
  const [taskSearch, setTaskSearch] = useState("");
  const [taskModule, setTaskModule] = useState("all");
  const [taskStatus, setTaskStatus] = useState("all");
  const [busy, setBusy] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [apiOpen, setApiOpen] = useState(false);
  const [managedCredentials, setManagedCredentials] = useState<ManagedCredentialStatus[]>([]);
  const [selectedCredentialId, setSelectedCredentialId] = useState<string | null>(null);
  const [credentialDrafts, setCredentialDrafts] = useState<Record<string, Record<string, string>>>({});
  const [credentialBusy, setCredentialBusy] = useState("");
  const [credentialMessage, setCredentialMessage] = useState("");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [codexChannelState, setCodexChannelState] = useState<"checking" | "ready" | "offline">("checking");
  const [codexChannel, setCodexChannel] = useState<CodexChannelStatus | null>(null);
  const [assistantRequest, setAssistantRequest] = useState("优先整理有明确采购意图、适合外贸供应的关键词；无法核验的平台数值保持为空。");
  const [resultLimit, setResultLimit] = useState("20");
  const [assistantMessage, setAssistantMessage] = useState("AI 会检索公开证据、整理成雷达字段并自动保存到历史。不会编造缺失数值。");
  const [importMessage, setImportMessage] = useState("支持 JSON、CSV 或 TSV；缺失值请留空，不要填 0。");
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [mergeSourceId, setMergeSourceId] = useState("");
  const [historySearch, setHistorySearch] = useState("");
  const [historyMode, setHistoryMode] = useState("all");
  const [historyMethod, setHistoryMethod] = useState("all");
  const [historyMarket, setHistoryMarket] = useState("all");
  const [historyLanguage, setHistoryLanguage] = useState("all");
  const [historyWindow, setHistoryWindow] = useState("all");
  const [historyStatus, setHistoryStatus] = useState("all");
  const [historyHasResults, setHistoryHasResults] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<ApiHistory | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState("");
  const [detailTarget, setDetailTarget] = useState<ApiHistory | null>(null);
  const [detailData, setDetailData] = useState<ApiRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [imagePreview, setImagePreview] = useState<{ images: ApiProductImage[]; index: number; alt: string } | null>(null);
  const [researchData, setResearchData] = useState<ResearchDashboardData | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchBusy, setResearchBusy] = useState(false);
  const [researchMessage, setResearchMessage] = useState("");
  const [researchSearch, setResearchSearch] = useState("");
  const [researchStatus, setResearchStatus] = useState("active");
  const [researchCreateOpen, setResearchCreateOpen] = useState(false);
  const [researchDetail, setResearchDetail] = useState<ResearchProjectDetail | null>(null);
  const [researchDetailProjectId, setResearchDetailProjectId] = useState<string | null>(null);
  const [researchDetailTab, setResearchDetailTab] = useState<ResearchDetailTab>("summary");
  const [researchDetailLoading, setResearchDetailLoading] = useState(false);
  const [researchDetailError, setResearchDetailError] = useState("");
  const [researchRunTarget, setResearchRunTarget] = useState<ResearchProject | null>(null);
  const [researchDeleteTarget, setResearchDeleteTarget] = useState<ResearchProject | null>(null);
  const [researchDeleteBusy, setResearchDeleteBusy] = useState(false);
  const [researchDeleteMessage, setResearchDeleteMessage] = useState("");
  const [researchProductName, setResearchProductName] = useState("");
  const [researchCategory, setResearchCategory] = useState("数码小家电");
  const [researchDescription, setResearchDescription] = useState("");
  const [researchMarkets, setResearchMarkets] = useState<string[]>(["GB", "US"]);
  const [researchLanguages, setResearchLanguages] = useState<string[]>(["en"]);
  const [researchTemplateId, setResearchTemplateId] = useState("portfolio_launch_plan");
  const [researchTargetCandidateCount, setResearchTargetCandidateCount] = useState("2000");
  const [researchChannels, setResearchChannels] = useState<string[]>(["google_trends", "alibaba", "amazon", "official_regulation", "buyer_websites"]);
  const [researchObjectives, setResearchObjectives] = useState("请建立可长期维护的外贸启动方案，按总览边界、大赛道地图、候选产品池、筛选机制、市场映射、180天路线、两人SOP、预算报价、合规供应链、获客成交和执行清单持续更新。候选产品按大赛道、细分领域和具体国家市场整理，分批扩充、自动去重，并保留可核验证据和未知项。");
  const [researchConstraints, setResearchConstraints] = useState("");
  const [researchRequestNote, setResearchRequestNote] = useState("优先免费、官方和公开可核验来源；不能核验的数值保持为空，并列出下一步补证据方法。");
  const [researchRunCandidateTarget, setResearchRunCandidateTarget] = useState("2000");
  const [researchRunMode, setResearchRunMode] = useState<"expand_candidates" | "review">("expand_candidates");
  const [researchRunBatchCount, setResearchRunBatchCount] = useState("100");
  const [researchPoolSearch, setResearchPoolSearch] = useState("");
  const [researchPoolBuyerTypes, setResearchPoolBuyerTypes] = useState<string[]>([]);
  const [researchPoolConditions, setResearchPoolConditions] = useState("");
  const [researchPoolTracks, setResearchPoolTracks] = useState<string[]>([]);
  const [researchPoolMarkets, setResearchPoolMarkets] = useState<string[]>([]);
  const [researchPoolRisks, setResearchPoolRisks] = useState<string[]>([]);
  const [researchPoolStages, setResearchPoolStages] = useState<string[]>(["active"]);
  const [researchPoolPage, setResearchPoolPage] = useState(1);
  const [researchCandidateActionTarget, setResearchCandidateActionTarget] = useState<ResearchCandidate | null>(null);
  const [researchCandidateActionStage, setResearchCandidateActionStage] = useState<ResearchCandidate["stage"]>("idea");
  const [researchCandidateActionNote, setResearchCandidateActionNote] = useState("");
  const [researchCandidateEvidenceUrl, setResearchCandidateEvidenceUrl] = useState("");
  const [researchCandidateNextAction, setResearchCandidateNextAction] = useState("");
  const [researchCandidateFollowUpAt, setResearchCandidateFollowUpAt] = useState("");
  const [researchCandidateActionBusy, setResearchCandidateActionBusy] = useState(false);
  const [researchSelectionTarget, setResearchSelectionTarget] = useState<ResearchCandidate | null>(null);
  const [researchSelectionDraft, setResearchSelectionDraft] = useState<CandidateSelectionAssessment | null>(null);
  const [researchSelectionFamily, setResearchSelectionFamily] = useState("");
  const [researchSelectionBusy, setResearchSelectionBusy] = useState(false);
  const [researchSelectionMessage, setResearchSelectionMessage] = useState("");
  const [researchBuyerTarget, setResearchBuyerTarget] = useState<ResearchBuyerProfile | null>(null);
  const [researchBuyerCreateOpen, setResearchBuyerCreateOpen] = useState(false);
  const [researchBuyerDraft, setResearchBuyerDraft] = useState<ResearchBuyerDraft>(emptyResearchBuyerDraft);
  const [researchBuyerBusy, setResearchBuyerBusy] = useState(false);
  const [researchBuyerMessage, setResearchBuyerMessage] = useState("");
  const [researchBuyerMatrixTarget, setResearchBuyerMatrixTarget] = useState<ResearchBuyerProfile | null>(null);
  const [researchBuyerFamilyDrafts, setResearchBuyerFamilyDrafts] = useState<ResearchBuyerFamilyDraft[]>([]);
  const [researchBuyerFamilySearch, setResearchBuyerFamilySearch] = useState("");
  const [researchBuyerMatrixBusy, setResearchBuyerMatrixBusy] = useState(false);
  const [globalBuyerLibraryOpen, setGlobalBuyerLibraryOpen] = useState(false);
  const [globalBuyerSearch, setGlobalBuyerSearch] = useState("");
  const [globalBuyerCountry, setGlobalBuyerCountry] = useState("all");
  const [globalBuyerTarget, setGlobalBuyerTarget] = useState<GlobalBuyerProfile | null>(null);
  const [globalBuyerCreateOpen, setGlobalBuyerCreateOpen] = useState(false);
  const [globalBuyerDraft, setGlobalBuyerDraft] = useState<ResearchBuyerDraft>(emptyResearchBuyerDraft);
  const [globalBuyerBusy, setGlobalBuyerBusy] = useState(false);
  const [globalBuyerMessage, setGlobalBuyerMessage] = useState("");
  const [globalBuyerMatrixTarget, setGlobalBuyerMatrixTarget] = useState<GlobalBuyerProfile | null>(null);
  const [globalBuyerFamilyDrafts, setGlobalBuyerFamilyDrafts] = useState<ResearchBuyerFamilyDraft[]>([]);
  const [globalBuyerFamilySearch, setGlobalBuyerFamilySearch] = useState("");
  const [globalBuyerMatrixBusy, setGlobalBuyerMatrixBusy] = useState(false);
  const [globalBuyerLibraryTab, setGlobalBuyerLibraryTab] = useState("personas");
  const [personaWorkspaceTab, setPersonaWorkspaceTab] = useState("active");
  const [globalTaxonomySearch, setGlobalTaxonomySearch] = useState("");
  const [personaGroupFilter, setPersonaGroupFilter] = useState("all");
  const [personaCoverageFilter, setPersonaCoverageFilter] = useState("all");
  const [personaRoleFilter, setPersonaRoleFilter] = useState("all");
  const [personaSort, setPersonaSort] = useState("group");
  const [personaDetailCode, setPersonaDetailCode] = useState<string | null>(null);
  const [opportunitySeed, setOpportunitySeed] = useState<OpportunityProgramSeed | null>(null);
  const [personaCategoryTarget, setPersonaCategoryTarget] = useState<BuyerPersonaCategory | null>(null);
  const [personaCategoryDraft, setPersonaCategoryDraft] = useState<PersonaCategoryDraft>(emptyPersonaCategoryDraft);
  const [personaCategoryEditorOpen, setPersonaCategoryEditorOpen] = useState(false);
  const [productTrackTarget, setProductTrackTarget] = useState<ProductTrackMaster | null>(null);
  const [productTrackDraft, setProductTrackDraft] = useState<ProductTrackDraft>(emptyProductTrackDraft);
  const [productTrackEditorOpen, setProductTrackEditorOpen] = useState(false);
  const [productFamilyTarget, setProductFamilyTarget] = useState<ProductFamilyMaster | null>(null);
  const [productFamilyDraft, setProductFamilyDraft] = useState<ProductFamilyMasterDraft>(emptyProductFamilyMasterDraft);
  const [productFamilyEditorOpen, setProductFamilyEditorOpen] = useState(false);
  const [personaMatrixTarget, setPersonaMatrixTarget] = useState<PersonaProductMatrix | null>(null);
  const [personaMatrixDraft, setPersonaMatrixDraft] = useState<PersonaMatrixDraft>(emptyPersonaMatrixDraft);
  const [personaMatrixEditorOpen, setPersonaMatrixEditorOpen] = useState(false);
  const [globalTaxonomyBusy, setGlobalTaxonomyBusy] = useState(false);
  const [personaDeleteTarget, setPersonaDeleteTarget] = useState<BuyerPersonaCategory | null>(null);
  const [personaAiOpen, setPersonaAiOpen] = useState(false);
  const [personaAiMode, setPersonaAiMode] = useState<"discover" | "enrich">("discover");
  const [personaAiTargetCode, setPersonaAiTargetCode] = useState("");
  const [personaAiRequestedCount, setPersonaAiRequestedCount] = useState("3");
  const [personaAiRequestNote, setPersonaAiRequestNote] = useState("补充稳定、可跨项目复用的批发买家业态，优先核实价值链角色、终端客群、销售渠道、采购场景、订单特点和合规关注；避免按单一公司或单一产品建类。");
  const [personaAiBusy, setPersonaAiBusy] = useState(false);
  const [personaAiMessage, setPersonaAiMessage] = useState("");
  const [researchCandidateAiBusy, setResearchCandidateAiBusy] = useState(false);
  const [researchCandidateAiMessage, setResearchCandidateAiMessage] = useState("");
  const [researchImageAssistBusy, setResearchImageAssistBusy] = useState(false);
  const [researchMarketActionTarget, setResearchMarketActionTarget] = useState<ResearchMarketHypothesis | null>(null);
  const [researchMarketActionStatus, setResearchMarketActionStatus] = useState<ResearchMarketStatus>("hypothesis");
  const [researchMarketActionNote, setResearchMarketActionNote] = useState("");
  const [researchMarketEvidenceUrl, setResearchMarketEvidenceUrl] = useState("");
  const [researchMarketNextAction, setResearchMarketNextAction] = useState("");
  const [researchMarketFollowUpAt, setResearchMarketFollowUpAt] = useState("");
  const [researchMarketActionBusy, setResearchMarketActionBusy] = useState(false);
  const [researchMarketActionMessage, setResearchMarketActionMessage] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const activeRunRef = useRef<string | null>(null);
  const mounted = useSyncExternalStore(subscribeToBrowser, getBrowserSnapshot, getServerSnapshot);

  const loadDashboard = useCallback(async () => {
    const response = await fetch("/api/radar", { cache: "no-store" });
    if (!response.ok) throw new Error("本地数据库暂时不可用");
    const next = (await response.json()) as DashboardData;
    setData(next);
    if (next.run) {
      setQuery(next.run.query);
      setMarket(next.run.market);
      setLanguage(next.run.language);
      setWindowDays(String(next.run.window_days));
      setScanMessage(
        next.run.is_demo
          ? "演示数据 · 不代表真实平台热度"
          : next.run.status === "waiting_for_data"
            ? "任务已建立 · 等待真实证据"
            : next.run.status === "partial"
              ? `部分来源可用 · ${relativeTime(next.run.created_at)}`
              : `最近扫描 · ${relativeTime(next.run.created_at)}`,
      );
    } else {
      setScanMessage("暂无任务 · 输入关键词开始分析");
    }
    setSavedIds(next.watchlist.map((row) => row.cluster_id));
  }, []);

  const loadManagedCredentials = useCallback(async () => {
    const response = await fetch("/api/radar?view=credential_statuses", { cache: "no-store" });
    const result = (await response.json()) as { credentials?: ManagedCredentialStatus[]; error?: string };
    if (!response.ok) throw new Error(result.error ?? "读取 API Key 状态失败");
    setManagedCredentials(result.credentials ?? []);
  }, []);

  const openCredentialManager = useCallback((provider: string) => {
    setCredentialMessage("");
    setSelectedCredentialId(provider);
    setApiOpen(true);
    void loadManagedCredentials().catch((error) => {
      setCredentialMessage(error instanceof Error ? error.message : "读取 API Key 状态失败");
    });
  }, [loadManagedCredentials]);

  const saveManagedCredential = useCallback(async (provider: string) => {
    const values = credentialDrafts[provider] ?? {};
    setCredentialBusy(`${provider}:save`);
    setCredentialMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "save_api_credential", provider, values }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "保存 API Key 失败");
      setCredentialDrafts((current) => ({ ...current, [provider]: {} }));
      setCredentialMessage("连接信息已加密保存；页面和接口不会回显原内容。");
      await loadManagedCredentials();
    } catch (error) {
      setCredentialMessage(error instanceof Error ? error.message : "保存 API Key 失败");
    } finally {
      setCredentialBusy("");
    }
  }, [credentialDrafts, loadManagedCredentials]);

  const testManagedCredential = useCallback(async (provider: string) => {
    setCredentialBusy(`${provider}:test`);
    setCredentialMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "test_api_credential", provider }),
      });
      const result = (await response.json()) as { message?: string; error?: string };
      if (!response.ok) throw new Error(result.error ?? "测试连接失败");
      setCredentialMessage(result.message ?? "连接测试完成");
      await loadManagedCredentials();
    } catch (error) {
      setCredentialMessage(error instanceof Error ? error.message : "测试连接失败");
    } finally {
      setCredentialBusy("");
    }
  }, [loadManagedCredentials]);

  const deleteManagedCredential = useCallback(async (provider: string) => {
    if (!window.confirm("确定删除已加密保存的连接信息？删除后无法恢复。")) return;
    setCredentialBusy(`${provider}:delete`);
    setCredentialMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "delete_api_credential", provider }),
      });
      const result = (await response.json()) as { environmentFallback?: boolean; error?: string };
      if (!response.ok) throw new Error(result.error ?? "删除连接信息失败");
      setCredentialMessage(result.environmentFallback
        ? "页面保存的密钥已删除；本机环境变量中的备用密钥仍会生效。"
        : "连接信息已删除。");
      await loadManagedCredentials();
    } catch (error) {
      setCredentialMessage(error instanceof Error ? error.message : "删除连接信息失败");
    } finally {
      setCredentialBusy("");
    }
  }, [loadManagedCredentials]);

  const loadResearch = useCallback(async () => {
    setResearchLoading(true);
    try {
      const response = await fetch("/api/radar?view=research", { cache: "no-store" });
      const next = (await response.json()) as ResearchDashboardData & { error?: string };
      if (!response.ok) throw new Error(next.error ?? "读取调研项目失败");
      setResearchData(next);
    } finally {
      setResearchLoading(false);
    }
  }, []);

  const loadTaskCenter = useCallback(async () => {
    const response = await fetch("/api/radar?view=task_center", { cache: "no-store" });
    const next = (await response.json()) as TaskCenterData & { error?: string };
    if (!response.ok) throw new Error(next.error ?? "读取全局任务失败");
    setTaskCenterData(next);
  }, []);

  const loadResearchProject = useCallback(async (projectId: string, resetPool = false) => {
    setResearchDetailProjectId(projectId);
    setResearchDetailLoading(true);
    setResearchDetailError("");
    if (resetPool) {
      setResearchPoolSearch("");
      setResearchPoolBuyerTypes([]);
      setResearchPoolConditions("");
      setResearchPoolTracks([]);
      setResearchPoolMarkets([]);
      setResearchPoolRisks([]);
      setResearchPoolStages(["active"]);
      setResearchPoolPage(1);
    }
    try {
      const response = await fetch(`/api/radar?view=research_project&projectId=${encodeURIComponent(projectId)}`, { cache: "no-store" });
      const result = (await response.json()) as ResearchProjectDetail & { error?: string };
      if (!response.ok) throw new Error(result.error ?? "读取调研明细失败");
      setResearchDetail(result);
    } catch (error) {
      setResearchDetail(null);
      setResearchDetailError(error instanceof Error ? error.message : "读取调研明细失败");
    } finally {
      setResearchDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    const applyLocation = () => {
      const params = new URLSearchParams(window.location.search);
      const requestedView = params.get("view");
      if (["research", "watchlist"].includes(String(requestedView))) {
        window.history.replaceState({ lightlinkView: "intelligence" }, "", "/");
        setActiveView("intelligence");
        setResearchDetailProjectId(null);
        setResearchDetail(null);
        setResearchDetailError("");
        return;
      }
      if (["intelligence", "dashboard", "personas", "opportunities", "history", "sources"].includes(String(requestedView))) {
        setActiveView(requestedView as typeof activeView);
      }
      setResearchDetailProjectId(null);
      setResearchDetail(null);
      setResearchDetailError("");
    };
    applyLocation();
    window.addEventListener("popstate", applyLocation);
    return () => window.removeEventListener("popstate", applyLocation);
  }, [loadResearchProject]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadDashboard().catch((error: Error) => setScanMessage(error.message));
      loadResearch().catch((error: Error) => setResearchMessage(error.message));
      loadTaskCenter().catch(() => undefined);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadDashboard, loadResearch, loadTaskCenter]);

  useEffect(() => {
    let cancelled = false;
    const checkChannel = async () => {
      try {
        const response = await fetch("http://127.0.0.1:8788/status", { cache: "no-store" });
        const next = (await response.json()) as CodexChannelStatus;
        if (cancelled) return;
        setCodexChannelState(response.ok && next.ready ? "ready" : "offline");
        setCodexChannel(next);
        const previousRunId = activeRunRef.current;
        const nextJobs = next.activeJobs ?? (next.activeJob ? [next.activeJob] : []);
        const activeRunSignature = nextJobs.map((job) => `${job.channelId ?? job.taskType}:${job.runId}`).sort().join("|");
        activeRunRef.current = activeRunSignature || null;
        if (nextJobs.length || previousRunId !== (activeRunSignature || null)) {
          await Promise.all([
            loadDashboard(),
            loadResearch(),
            loadTaskCenter(),
            researchDetailProjectId ? loadResearchProject(researchDetailProjectId) : Promise.resolve(),
          ]);
        }
      } catch {
        if (!cancelled) {
          setCodexChannelState("offline");
          setCodexChannel(null);
        }
      }
    };
    void checkChannel();
    const timer = window.setInterval(checkChannel, 4_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [loadDashboard, loadResearch, loadResearchProject, loadTaskCenter, researchDetailProjectId]);

  const liveRows = data ? data.results.map(apiRowToKeyword) : [];
  const sourceStatusByPlatform = new Map((data?.sources ?? []).map((source) => [source.platform, source]));
  const liveSources = data
    ? VALID_PLATFORMS.map((platform) => {
        const source = sourceStatusByPlatform.get(platform);
        const statuses = source?.statuses ?? ["missing"];
        return {
          name: platform,
          state: statuses.includes("missing")
            ? "未采集"
            : statuses.every((status) => ["ok", "confirmed_zero"].includes(status))
              ? "可用"
              : statuses.some((status) => ["ok", "confirmed_zero"].includes(status))
                ? "部分可用"
                : "无有效值",
          freshness: !source || statuses.includes("missing") ? "尚无数据" : relativeTime(source.collected_at),
          coverage: source?.coverage ?? 0,
          observationCount: source?.observation_count ?? 0,
          sourceKinds: source?.source_kinds ?? [],
        };
      })
    : [];
  const activeSourceCount = liveSources.filter((source) => source.state !== "未采集").length;
  const reportedActiveJobs = codexChannel?.activeJobs ?? (codexChannel?.activeJob ? [codexChannel.activeJob] : []);
  const activeJobs = reportedActiveJobs.filter((job) => {
    if ((job.taskType ?? "radar") === "radar") {
      const history = data?.history.find((item) => item.id === job.runId);
      return !history || !["complete", "partial", "failed"].includes(history.status) || (history.observation_count === 0 && history.status !== "failed");
    }
    if (job.taskType === "research") {
      const project = researchData?.projects.find((item) => item.id === job.projectId);
      return !project || !["completed", "needs_review", "archived"].includes(project.status);
    }
    return true;
  });
  const activeJob = activeJobs[0] ?? null;
  const jobChannelId = (job: CodexJob): CodexChannelId => job.channelId
    ?? (job.taskType && ["research", "candidate_assist", "candidate_images", "taxonomy_assist", "trade_data", "opportunity_validation"].includes(job.taskType) ? job.taskType as CodexChannelId : "radar");
  const activeJobFor = (channelId: CodexChannelId) => activeJobs.find((job) => jobChannelId(job) === channelId) ?? null;
  const radarChannelJob = activeJobFor("radar");
  const researchChannelJob = activeJobFor("research");
  const candidateAssistChannelJob = activeJobFor("candidate_assist");
  const candidateImagesChannelJob = activeJobFor("candidate_images");
  const taxonomyAssistChannelJob = activeJobFor("taxonomy_assist");
  const activeJobHistory = activeJob ? data?.history.find((item) => item.id === activeJob.runId) : undefined;
  const activeJobProgress = Math.min(99, Math.max(5, activeJob?.progress ?? 20));
  const activeTaskCount = activeJobs.length;
  const activeChannelSummary = activeJobs.map((job) => job.channelTitle?.replace("LightLink Radar ", "") ?? "AI任务").join("、");
  const activeJobView = activeJob?.taskType === "taxonomy_assist" ? "personas" : ["trade_data", "opportunity_validation"].includes(String(activeJob?.taskType)) ? "opportunities" : ["research", "candidate_assist", "candidate_images"].includes(String(activeJob?.taskType)) ? "intelligence" : "dashboard";
  const moduleForJob = (job: CodexJob): TaskCenterItem["module"] => job.taskType === "taxonomy_assist"
    ? "personas"
    : ["trade_data", "opportunity_validation"].includes(String(job.taskType))
      ? "opportunities"
      : ["research", "candidate_assist", "candidate_images"].includes(String(job.taskType))
        ? "research"
        : "discovery";
  const taskLabelForJob = (job: CodexJob) => ({
    radar: "关键词与热点扫描",
    research: "产品与市场调研",
    candidate_assist: "单产品 AI 调研",
    candidate_images: "候选产品图片采集",
    taxonomy_assist: "画像分类 AI 补充",
    trade_data: "贸易数据采集",
    opportunity_validation: "商机公开证据验证",
  }[jobChannelId(job)]);
  const taskItemMap = new Map((taskCenterData?.items ?? []).map((item) => [item.id, item]));
  const runtimeJobs = [
    ...(codexChannel?.lastJobs ?? (codexChannel?.lastJob ? [codexChannel.lastJob] : [])),
    ...activeJobs,
  ];
  for (const job of runtimeJobs) {
    const existing = taskItemMap.get(job.runId);
    taskItemMap.set(job.runId, {
      id: job.runId,
      module: existing?.module ?? moduleForJob(job),
      task_type: jobChannelId(job),
      task_label: existing?.task_label ?? taskLabelForJob(job),
      title: job.query ?? existing?.title ?? taskLabelForJob(job),
      subtitle: job.phase ?? existing?.subtitle ?? job.channelTitle?.replace("LightLink Radar ", "") ?? "Codex 自动通道",
      status: activeJobs.some((item) => item.runId === job.runId) ? "running" : job.status,
      progress: activeJobs.some((item) => item.runId === job.runId) ? Math.min(99, Math.max(5, job.progress ?? 20)) : job.status === "completed" ? 100 : job.progress ?? existing?.progress ?? null,
      result_count: existing?.result_count ?? 0,
      target_id: existing?.target_id ?? job.projectId ?? "",
      created_at: existing?.created_at ?? job.startedAt,
      completed_at: job.completedAt ?? existing?.completed_at ?? null,
      error: job.error ?? existing?.error ?? "",
    });
  }
  const allTaskItems = [...taskItemMap.values()].sort((left, right) => right.created_at.localeCompare(left.created_at));
  const normalizedTaskSearch = taskSearch.trim().toLocaleLowerCase();
  const filteredTaskItems = allTaskItems.filter((item) => {
    const searchText = `${item.title} ${item.subtitle} ${item.task_label} ${TASK_MODULE_META[item.module].label}`.toLocaleLowerCase();
    return (taskModule === "all" || item.module === taskModule)
      && (taskStatus === "all" || taskStatusGroup(item.status) === taskStatus)
      && (!normalizedTaskSearch || searchText.includes(normalizedTaskSearch));
  });
  const researchProjects = researchData?.projects ?? [];
  const normalizedResearchSearch = researchSearch.trim().toLocaleLowerCase();
  const filteredResearchProjects = researchProjects.filter((item) => {
    const searchText = [item.product_name, item.product_category, ...item.target_markets, ...item.languages].join(" ").toLocaleLowerCase();
    const statusMatches = researchStatus === "all"
      || (researchStatus === "active" && item.status !== "archived")
      || item.status === researchStatus;
    return statusMatches && (!normalizedResearchSearch || searchText.includes(normalizedResearchSearch));
  });
  const globalBuyerLibrary = researchData?.buyerLibrary;
  const globalBuyerProfiles = globalBuyerLibrary?.profiles ?? [];
  const globalBuyerLinks = globalBuyerLibrary?.links ?? [];
  const globalTradeRegions = globalBuyerLibrary?.taxonomy.regions ?? [];
  const globalPersonaCategories = globalBuyerLibrary?.taxonomy.personaCategories ?? [];
  const retiredGlobalPersonaCategories = globalBuyerLibrary?.taxonomy.retiredPersonaCategories ?? [];
  const globalPersonaProposals = globalBuyerLibrary?.personaProposals ?? [];
  const globalPersonaChanges = globalBuyerLibrary?.personaChanges ?? [];
  const globalProductTracks = globalBuyerLibrary?.taxonomy.productTracks ?? [];
  const globalProductFamilyMaster = globalBuyerLibrary?.taxonomy.productFamilies ?? [];
  const globalPersonaMatrix = globalBuyerLibrary?.taxonomy.personaMatrix ?? [];
  const personaGroups = [...new Set(globalPersonaCategories.map((item) => item.group_name))].sort((left, right) => left.localeCompare(right, "zh-CN"));
  const normalizedPersonaSearch = globalTaxonomySearch.trim().toLocaleLowerCase();
  const filteredPersonaCategories = globalPersonaCategories.filter((item) => {
    const matrixLinks = globalPersonaMatrix.filter((link) => link.persona_code === item.code);
    const familyLinks = matrixLinks.filter((link) => link.product_family_code);
    const buyerCount = globalBuyerProfiles.filter((buyer) => buyer.persona_code === item.code).length;
    const linkedProductText = matrixLinks.flatMap((link) => {
      const track = globalProductTracks.find((value) => value.code === link.track_code);
      const family = globalProductFamilyMaster.find((value) => value.code === link.product_family_code);
      return [track?.name ?? "", family?.name ?? ""];
    });
    const searchText = [
      item.code, item.name, item.group_name, item.description, item.value_chain_role,
      ...item.customer_groups, ...item.sales_channels, ...item.purchase_scenarios,
      ...item.buying_triggers, ...item.compliance_focus, ...linkedProductText,
    ].join(" ").toLocaleLowerCase();
    const coverageMatches = personaCoverageFilter === "all"
      || (personaCoverageFilter === "configured" && familyLinks.length > 0)
      || (personaCoverageFilter === "missing" && familyLinks.length === 0)
      || (personaCoverageFilter === "validated" && matrixLinks.some((link) => link.evidence_status === "validated"))
      || (personaCoverageFilter === "buyers" && buyerCount > 0);
    const roleMatches = personaRoleFilter === "all" || familyLinks.some((link) => link.family_role === personaRoleFilter);
    return (personaGroupFilter === "all" || item.group_name === personaGroupFilter)
      && coverageMatches
      && roleMatches
      && (!normalizedPersonaSearch || searchText.includes(normalizedPersonaSearch));
  }).sort((left, right) => {
    if (personaSort === "coverage") {
      const rightCount = globalPersonaMatrix.filter((link) => link.persona_code === right.code && link.product_family_code).length;
      const leftCount = globalPersonaMatrix.filter((link) => link.persona_code === left.code && link.product_family_code).length;
      return rightCount - leftCount || left.name.localeCompare(right.name, "zh-CN");
    }
    if (personaSort === "updated") return right.updated_at.localeCompare(left.updated_at);
    return left.group_name.localeCompare(right.group_name, "zh-CN") || left.name.localeCompare(right.name, "zh-CN");
  });
  const activePersonaFilterCount = [normalizedPersonaSearch, personaGroupFilter !== "all", personaCoverageFilter !== "all", personaRoleFilter !== "all", personaSort !== "group"].filter(Boolean).length;
  const personaDetail = personaDetailCode ? globalPersonaCategories.find((item) => item.code === personaDetailCode) ?? null : null;
  const personaDetailLinks = personaDetail ? globalPersonaMatrix.filter((link) => link.persona_code === personaDetail.code) : [];
  const personaDetailFamilyLinks = personaDetailLinks.filter((link) => link.product_family_code);
  const personaDetailTrackGroups = [...new Set(personaDetailLinks.map((link) => link.track_code))].map((trackCode) => {
    const track = globalProductTracks.find((item) => item.code === trackCode);
    const defaultLink = personaDetailLinks.find((link) => link.track_code === trackCode && !link.product_family_code);
    const familyLinks = personaDetailFamilyLinks
      .filter((link) => link.track_code === trackCode)
      .sort((left, right) => right.relevance_score - left.relevance_score);
    return { trackCode, track, defaultLink, familyLinks, score: defaultLink?.relevance_score ?? familyLinks[0]?.relevance_score ?? 0 };
  }).sort((left, right) => right.score - left.score);
  const globalBuyerCountries = [...new Set(globalBuyerProfiles.map((item) => item.country))].sort();
  const normalizedGlobalBuyerSearch = globalBuyerSearch.trim().toLocaleLowerCase();
  const filteredGlobalBuyers = globalBuyerProfiles.filter((buyer) => {
    const relatedLinks = globalBuyerLinks.filter((link) => link.buyer_profile_id === buyer.id);
    const personaItem = globalPersonaCategories.find((item) => item.code === buyer.persona_code);
    const regionItem = globalTradeRegions.find((item) => item.code === buyer.region_code);
    const searchText = [
      buyer.company_name,
      buyer.country,
      buyer.buyer_type,
      personaItem?.name ?? "",
      regionItem?.name ?? "",
      ...buyer.customer_groups,
      ...buyer.sales_channels,
      ...buyer.purchasing_scenarios,
      ...relatedLinks.flatMap((link) => [link.track_category, link.product_family, ...link.sales_scenarios]),
    ].join(" ").toLocaleLowerCase();
    return (globalBuyerCountry === "all" || buyer.country === globalBuyerCountry)
      && (!normalizedGlobalBuyerSearch || searchText.includes(normalizedGlobalBuyerSearch));
  });
  const historyMarkets = [...new Set((data?.history ?? []).map((item) => item.market))].sort();
  const historyLanguages = [...new Set((data?.history ?? []).map((item) => item.language))].sort();
  const normalizedHistorySearch = historySearch.trim().toLocaleLowerCase();
  const filteredHistory = (data?.history ?? []).filter((item) => {
    const isRunning = activeJob?.runId === item.id;
    const searchText = [
      item.query,
      item.market,
      marketNameForCode(item.market),
      item.language,
      languageNameForCode(item.language),
      taskTypeLabel(item),
      PROCESSING_METHOD_LABELS[processingMethod(item)] ?? processingMethod(item),
      runStatusLabel(item.status, Boolean(item.is_demo)),
    ]
      .join(" ")
      .toLocaleLowerCase();
    return (!normalizedHistorySearch || searchText.includes(normalizedHistorySearch))
      && (historyMode === "all" || String(item.source_summary.scanMode ?? item.mode) === historyMode)
      && (historyMethod === "all" || processingMethod(item) === historyMethod)
      && (historyMarket === "all" || item.market === historyMarket)
      && (historyLanguage === "all" || item.language === historyLanguage)
      && (historyWindow === "all" || item.window_days === Number(historyWindow))
      && (historyStatus === "all" || historyStatusKey(item, isRunning) === historyStatus)
      && (!historyHasResults || item.observation_count > 0);
  });
  const historyTotalPages = Math.max(1, Math.ceil(filteredHistory.length / HISTORY_PAGE_SIZE));
  const currentHistoryPage = Math.min(historyPage, historyTotalPages);
  const pagedHistory = filteredHistory.slice((currentHistoryPage - 1) * HISTORY_PAGE_SIZE, currentHistoryPage * HISTORY_PAGE_SIZE);
  const activeHistoryFilters = [
    normalizedHistorySearch ? `关键词：${historySearch.trim()}` : "",
    historyMode !== "all" ? `类型：${RUN_MODE_LABELS[historyMode] ?? historyMode}` : "",
    historyMethod !== "all" ? `处理：${PROCESSING_METHOD_LABELS[historyMethod] ?? historyMethod}` : "",
    historyMarket !== "all" ? `国家：${marketNameForCode(historyMarket)}（${historyMarket}）` : "",
    historyLanguage !== "all" ? `语种：${languageNameForCode(historyLanguage)}（${historyLanguage.toUpperCase()}）` : "",
    historyWindow !== "all" ? `周期：${historyWindow} 天` : "",
    historyStatus !== "all" ? `状态：${HISTORY_STATUS_LABELS[historyStatus]}` : "",
    historyHasResults ? "只看有结果" : "",
  ].filter(Boolean);
  const openAiIntegration = data?.integrations.find((item) => item.id === "openai");
  const chartData = data?.trend
    ? data.trend.map((point) => ({
        week: new Date(point.created_at).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" }),
        heat: point.heat == null ? null : Math.round(point.heat),
        opportunity: point.opportunity == null ? null : Math.round(point.opportunity),
      }))
    : [];

  const sortKey = sortBy as keyof Pick<KeywordRow, "opportunity" | "momentum" | "intent" | "heat">;
  const rows = liveRows
    .filter((row) => statusFilter === "all" || row.status === statusFilter)
    .sort((a, b) => (b[sortKey] ?? -1) - (a[sortKey] ?? -1));

  const selectedObservations = selected
    ? (data?.observations ?? []).filter((observation) => observation.cluster_id === selected.id)
    : [];
  const researchLatestRun = latestResearchReportRun(researchDetail?.runs);
  const researchPendingRun = researchDetail?.runs.find((run) => ["waiting_for_codex", "researching"].includes(run.status));
  const researchLatestReport = researchLatestRun?.result_payload ?? {};
  const researchReportSections = (researchLatestReport.sections && typeof researchLatestReport.sections === "object" && !Array.isArray(researchLatestReport.sections))
    ? researchLatestReport.sections as Record<string, Record<string, unknown>>
    : {};
  const researchScorecard = researchDetail?.project.scorecard ?? {};
  const researchPlaybook = researchLatestReport.playbook && typeof researchLatestReport.playbook === "object" && !Array.isArray(researchLatestReport.playbook)
    ? researchLatestReport.playbook as Record<string, Record<string, unknown>>
    : {};
  const researchTracks = recordArray(researchLatestReport.trackCategories);
  const researchMarketsReport = recordArray(researchLatestReport.marketHypotheses) as ResearchMarketHypothesis[];
  const researchMarketStatus = (marketItem: ResearchMarketHypothesis): ResearchMarketStatus => {
    const marketCode = String(marketItem.marketCode ?? "").toUpperCase();
    const latestActivity = (researchDetail?.marketActivities ?? []).find((item) => item.market_code === marketCode);
    const reportedStatus = String(latestActivity?.to_status ?? marketItem.validationStatus ?? "hypothesis");
    return ["hypothesis", "partial", "validated", "rejected"].includes(reportedStatus)
      ? reportedStatus as ResearchMarketStatus
      : "hypothesis";
  };
  const fallbackResearchCandidates: ResearchCandidate[] = recordArray(researchLatestReport.productPool).map((item, index) => {
    const assessment = emptyCandidateSelectionAssessment();
    const candidate = {
      id: String(item.id ?? `report-candidate-${index + 1}`),
      project_id: researchDetail?.project.id ?? "",
      name: String(item.name ?? ""),
      track_category: String(item.trackCategory ?? ""),
      subcategory: String(item.subcategory ?? ""),
      product_family: String(item.productFamily ?? item.subcategory ?? ""),
      commercial_variant: String(item.commercialVariant ?? ""),
      image_urls: valueList(item.imageUrls ?? (item.imageUrl ? [item.imageUrl] : [])).filter(isSafeSourceUrl).slice(0, 6),
      image_source_ref: isSafeSourceUrl(String(item.imageSourceRef ?? "")) ? String(item.imageSourceRef) : "",
      target_markets: valueList(item.targetMarkets),
      buyer_types: valueList(item.buyerTypes),
      price_band: String(item.priceBand ?? ""),
      moq: String(item.moq ?? ""),
      compliance: valueList(item.compliance),
      risk_level: ["low", "medium", "high", "unknown"].includes(String(item.riskLevel)) ? item.riskLevel as ResearchCandidate["risk_level"] : "unknown",
      stage: ["idea", "research", "sample", "validation", "shortlist", "validated", "rejected"].includes(String(item.stage)) ? item.stage as ResearchCandidate["stage"] : "idea",
      score: item.score === null || item.score === undefined || !Number.isFinite(Number(item.score)) ? null : Number(item.score),
      rationale: String(item.rationale ?? ""),
      evidence_status: ["hypothesis", "partial", "validated"].includes(String(item.evidenceStatus)) ? item.evidenceStatus as ResearchCandidate["evidence_status"] : "hypothesis",
      selection_assessment: assessment,
      odoo_sync_state: "not_synced",
      odoo_external_id: "",
      odoo_synced_at: null,
      updated_at: researchLatestRun?.completed_at ?? researchLatestRun?.created_at ?? "",
    };
    return { ...candidate, handoff_readiness: candidateHandoffReadiness(candidate, assessment) };
  }).filter((item) => item.name);
  const researchCandidates = researchDetail?.candidates?.length ? researchDetail.candidates : fallbackResearchCandidates;
  const researchProductFamilies = buildProductFamilySummaries(researchCandidates);
  const researchBuyerProfiles = researchDetail?.buyerProfiles ?? [];
  const researchBuyerFamilyLinks = researchDetail?.buyerFamilyLinks ?? [];
  const researchQualifiedBuyers = researchBuyerProfiles.filter((buyer) => ["qualified", "validated"].includes(buyer.profile_status));
  const researchValidatedBuyers = researchBuyerProfiles.filter((buyer) => buyer.profile_status === "validated");
  const researchLinkedFamilyKeys = new Set(researchBuyerFamilyLinks.map((link) => `${link.track_category}|${link.product_family}`.toLocaleLowerCase()));
  const researchAssessedCandidates = researchCandidates.filter((item) => item.selection_assessment.decision !== "unreviewed");
  const researchOdooReadyCandidates = researchCandidates.filter((item) => item.handoff_readiness.ready);
  const researchTrackOptions = [...new Set([
    ...researchCandidates.map((item) => item.track_category),
    ...researchTracks.map((item) => String(item.name ?? "")),
  ].filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
  const researchMarketOptions = [...new Set(researchCandidates.flatMap((item) => item.target_markets).filter(Boolean))].sort();
  const researchBuyerTypeOptions = [...new Set(researchCandidates.flatMap((item) => item.buyer_types).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
  const researchPoolFilters = {
    search: researchPoolSearch,
    buyerTypes: researchPoolBuyerTypes,
    conditions: researchPoolConditions,
    tracks: researchPoolTracks,
    markets: researchPoolMarkets,
    risks: researchPoolRisks,
    stages: researchPoolStages,
  };
  const filteredResearchCandidates = researchCandidates.filter((item) => matchesResearchCandidateFilters(item, researchPoolFilters));
  const activeResearchPoolFilterCount = [
    researchPoolSearch.trim(),
    researchPoolBuyerTypes.length > 0,
    researchPoolConditions.trim(),
    researchPoolTracks.length > 0,
    researchPoolMarkets.length > 0,
    researchPoolRisks.length > 0,
    !(researchPoolStages.length === 1 && researchPoolStages[0] === "active"),
  ].filter(Boolean).length;
  const researchPoolPageSize = 25;
  const researchPoolTotalPages = Math.max(1, Math.ceil(filteredResearchCandidates.length / researchPoolPageSize));
  const currentResearchPoolPage = Math.min(researchPoolPage, researchPoolTotalPages);
  const pagedResearchCandidates = filteredResearchCandidates.slice((currentResearchPoolPage - 1) * researchPoolPageSize, currentResearchPoolPage * researchPoolPageSize);

  const changeMarket = (nextMarket: string) => {
    setMarket(nextMarket);
    setLanguage(defaultLanguageForMarket(nextMarket));
  };

  const clearHistoryFilters = () => {
    setHistorySearch("");
    setHistoryMode("all");
    setHistoryMethod("all");
    setHistoryMarket("all");
    setHistoryLanguage("all");
    setHistoryWindow("all");
    setHistoryStatus("all");
    setHistoryHasResults(false);
    setHistoryPage(1);
  };

  const openRunDetail = async (item: ApiHistory) => {
    setDetailTarget(item);
    setDetailData(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const response = await fetch(`/api/radar?view=run_detail&runId=${encodeURIComponent(item.id)}`, { cache: "no-store" });
      const result = (await response.json()) as ApiRunDetail & { error?: string };
      if (!response.ok) throw new Error(result.error ?? "读取任务明细失败");
      setDetailData(result);
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "读取任务明细失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const deleteHistoryRun = async () => {
    if (!deleteTarget) return;
    if (activeJobs.some((job) => job.runId === deleteTarget.id)) {
      setDeleteMessage("执行中的任务不能删除，请等待任务完成。");
      return;
    }
    setDeleteBusy(true);
    setDeleteMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "delete_run", runId: deleteTarget.id }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "删除任务失败");
      if (pendingRunId === deleteTarget.id) setPendingRunId(null);
      setDeleteTarget(null);
      await loadDashboard();
    } catch (error) {
      setDeleteMessage(error instanceof Error ? error.message : "删除任务失败");
    } finally {
      setDeleteBusy(false);
    }
  };

  const navigateToView = (view: typeof activeView) => {
    setActiveView(view);
    setResearchDetailProjectId(null);
    setResearchDetail(null);
    setResearchDetailError("");
    const path = view === "intelligence" ? "/" : `/?view=${view}`;
    window.history.pushState({ lightlinkView: view }, "", path);
    if (view === "sources") void loadManagedCredentials();
  };

  const openResearchProject = async (project: ResearchProject) => {
    setActiveView("research");
    setResearchMessage("");
    setResearchDetailTab("summary");
    window.history.pushState({ lightlinkResearchDetail: true }, "", researchProjectPath(project.id));
    window.scrollTo({ top: 0 });
    await loadResearchProject(project.id, true);
  };

  const openTaskOwner = async (item: TaskCenterItem) => {
    if (item.module === "research") {
      const project = researchProjects.find((value) => value.id === item.target_id);
      if (project) {
        await openResearchProject(project);
        return;
      }
    }
    if (item.module === "personas") {
      setPersonaWorkspaceTab(taskStatusGroup(item.status) === "review" ? "proposals" : "history");
    }
    navigateToView(TASK_MODULE_META[item.module].view);
    if (item.module === "discovery") {
      const run = data?.history.find((value) => value.id === item.id);
      if (run) await openRunDetail(run);
    }
  };

  const showCreatedResearchProject = (detail: ResearchProjectDetail) => {
    setActiveView("research");
    setResearchDetail(detail);
    setResearchDetailProjectId(detail.project.id);
    setResearchDetailTab("summary");
    setResearchDetailError("");
    window.history.pushState({ lightlinkResearchDetail: true }, "", researchProjectPath(detail.project.id));
    window.scrollTo({ top: 0 });
  };

  const returnToResearchList = () => {
    if (window.history.state?.lightlinkResearchDetail) {
      window.history.back();
      return;
    }
    window.history.replaceState({ lightlinkView: "research" }, "", researchListPath());
    setActiveView("research");
    setResearchDetailProjectId(null);
    setResearchDetail(null);
    setResearchDetailError("");
    window.scrollTo({ top: 0 });
  };

  const selectResearchDetailTab = (tab: string) => {
    if (!researchDetailProjectId || !RESEARCH_DETAIL_TABS.has(tab as ResearchDetailTab)) return;
    const nextTab = tab as ResearchDetailTab;
    setResearchDetailTab(nextTab);
    window.history.replaceState(
      { ...(window.history.state ?? {}) },
      "",
      researchProjectPath(researchDetailProjectId, nextTab),
    );
  };

  const dispatchResearchProject = async (
    project: ResearchProject,
    targetCandidateCount = project.target_candidate_count,
    runMode: "expand_candidates" | "review" = "review",
    requestedCandidateCount = 0,
  ) => {
    const response = await fetch("/api/radar", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "create_research_run", projectId: project.id, requestNote: researchRequestNote, targetCandidateCount, runMode, requestedCandidateCount }),
    });
    const task = (await response.json()) as { projectId?: string; runId?: string; dispatchTask?: Record<string, unknown>; error?: string };
    if (!response.ok || !task.projectId || !task.runId || !task.dispatchTask) throw new Error(task.error ?? "建立调研版本失败");
    const channelResponse = await fetch("http://127.0.0.1:8788/dispatch", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        taskType: "research",
        projectId: task.projectId,
        researchRunId: task.runId,
        ...task.dispatchTask,
      }),
    });
    const channelResult = (await channelResponse.json()) as { accepted?: boolean; threadId?: string; error?: string };
    if (!channelResponse.ok || !channelResult.accepted) {
      await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "fail_research_run",
          projectId: task.projectId,
          researchRunId: task.runId,
          error: channelResult.error ?? "Codex 自动通道未响应",
        }),
      }).catch(() => undefined);
      throw new Error(channelResult.error ?? "Codex 自动通道未响应；本次版本已标记失败，可直接重试。");
    }
    setCodexChannelState("ready");
  };

  const resetResearchCreateForm = () => {
    setResearchProductName("");
    setResearchCategory("数码小家电");
    setResearchDescription("");
    setResearchMarkets(["GB", "US"]);
    setResearchLanguages(["en"]);
    setResearchTemplateId("portfolio_launch_plan");
    setResearchTargetCandidateCount("2000");
    setResearchObjectives("请建立可长期维护的外贸启动方案，按总览边界、大赛道地图、候选产品池、筛选机制、市场映射、180天路线、两人SOP、预算报价、合规供应链、获客成交和执行清单持续更新。候选产品按大赛道、细分领域和具体国家市场整理，分批扩充、自动去重，并保留可核验证据和未知项。");
    setResearchConstraints("");
  };

  const createResearchProject = async (startImmediately = false) => {
    const researchBrief = researchObjectives.trim();
    const productName = researchProductName.trim() || "多品类产品外贸调研";
    const targetCandidateCount = Number(researchTargetCandidateCount);
    if (!researchBrief) {
      setResearchMessage("请填写给 Codex / ChatGPT 的完整任务");
      return;
    }
    if (!Number.isInteger(targetCandidateCount) || targetCandidateCount < 1 || targetCandidateCount > 2000) {
      setResearchMessage("候选产品目标数量必须是 1–2000 的整数");
      return;
    }
    setResearchBusy(true);
    setResearchMessage(startImmediately ? "正在保存项目并发送给 AI…" : "正在建立可持续调研项目…");
    let projectSaved = false;
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "create_research_project",
          productName,
          productCategory: researchCategory,
          productDescription: researchDescription,
          targetMarkets: researchMarkets,
          languages: researchLanguages,
          channels: researchChannels,
          templateId: researchTemplateId,
          targetCandidateCount,
          objectives: researchBrief,
          constraints: researchConstraints,
        }),
      });
      const result = (await response.json()) as ResearchProjectDetail & { error?: string };
      if (!response.ok) throw new Error(result.error ?? "建立调研项目失败");
      projectSaved = true;
      setResearchCreateOpen(false);
      resetResearchCreateForm();
      if (startImmediately) {
        await dispatchResearchProject(result.project, targetCandidateCount, "expand_candidates", Math.min(100, targetCandidateCount));
        setResearchMessage(`“${result.project.product_name}”已保存并发送给 Codex / ChatGPT；结果会写回项目首版。`);
      } else {
        showCreatedResearchProject(result);
        setResearchMessage("项目已保存。可继续补充资料，或交给 Codex / ChatGPT 开始首轮调研。");
      }
      await loadResearch();
    } catch (error) {
      const message = error instanceof Error ? error.message : "建立调研项目失败";
      setResearchMessage(projectSaved ? `项目已保存，但 AI 任务发送失败：${message}` : message);
      if (projectSaved) await loadResearch().catch(() => undefined);
    } finally {
      setResearchBusy(false);
    }
  };

  const openResearchRunDialog = (project: ResearchProject, mode?: "expand_candidates" | "review") => {
    const currentCount = Number(project.candidate_count || (researchDetail?.project.id === project.id ? researchDetail.candidates.length : 0));
    const targetCount = Number(project.target_candidate_count || 2000);
    const nextMode = mode ?? (currentCount < targetCount ? "expand_candidates" : "review");
    setResearchMessage("");
    setResearchRunMode(nextMode);
    setResearchRunCandidateTarget(String(targetCount));
    setResearchRunBatchCount(String(Math.min(100, Math.max(1, targetCount - currentCount))));
    setResearchRunTarget(project);
  };

  const startResearchProject = async (project: ResearchProject, targetCandidateCount: number, runMode: "expand_candidates" | "review", requestedCandidateCount: number) => {
    setResearchBusy(true);
    setResearchMessage("正在建立调研版本并发送给 Codex…");
    try {
      await dispatchResearchProject(project, targetCandidateCount, runMode, requestedCandidateCount);
      setResearchMessage(runMode === "expand_candidates"
        ? `“${project.product_name}”已发送到 Codex，本轮将补充最多 ${requestedCandidateCount} 个新候选并写回产品池。`
        : `“${project.product_name}”已发送到 Codex；结果会写回当前项目的新版本。`);
      await loadResearch();
      if (researchDetailProjectId === project.id) await loadResearchProject(project.id);
      return true;
    } catch (error) {
      setResearchMessage(error instanceof Error ? error.message : "发送调研任务失败");
      await loadResearch().catch(() => undefined);
      return false;
    } finally {
      setResearchBusy(false);
    }
  };

  const confirmResearchRun = async () => {
    if (!researchRunTarget) return;
    const targetCandidateCount = Number(researchRunCandidateTarget);
    if (!Number.isInteger(targetCandidateCount) || targetCandidateCount < 1 || targetCandidateCount > 2000) {
      setResearchMessage("候选产品目标数量必须是 1–2000 的整数");
      return;
    }
    const currentCount = Number(researchRunTarget.candidate_count || (researchDetail?.project.id === researchRunTarget.id ? researchDetail.candidates.length : 0));
    const requestedCandidateCount = researchRunMode === "expand_candidates" ? Number(researchRunBatchCount) : 0;
    if (researchRunMode === "expand_candidates" && targetCandidateCount <= currentCount) {
      setResearchMessage(`当前已有 ${currentCount} 个候选，请把项目目标提高到 ${currentCount + 1} 以上。`);
      return;
    }
    if (researchRunMode === "expand_candidates" && (!Number.isInteger(requestedCandidateCount) || requestedCandidateCount < 1 || requestedCandidateCount > 300)) {
      setResearchMessage("本轮新增数量必须是 1–300 的整数");
      return;
    }
    const started = await startResearchProject(researchRunTarget, targetCandidateCount, researchRunMode, requestedCandidateCount);
    if (started) setResearchRunTarget(null);
  };

  const setResearchArchived = async (project: ResearchProject, archived: boolean) => {
    setResearchBusy(true);
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "set_research_project_archived", projectId: project.id, archived }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "更新项目状态失败");
      setResearchMessage(archived ? "项目已归档，历史报告和证据仍然保留。" : "项目已恢复，可继续调研。");
      await loadResearch();
      if (researchDetailProjectId === project.id) await loadResearchProject(project.id);
    } catch (error) {
      setResearchMessage(error instanceof Error ? error.message : "更新项目状态失败");
    } finally {
      setResearchBusy(false);
    }
  };

  const deleteResearchProject = async () => {
    if (!researchDeleteTarget) return;
    setResearchDeleteBusy(true);
    setResearchDeleteMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "delete_research_project", projectId: researchDeleteTarget.id }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "删除调研项目失败");
      const deletedProjectId = researchDeleteTarget.id;
      setResearchDeleteTarget(null);
      await loadResearch();
      if (researchDetailProjectId === deletedProjectId) {
        window.history.replaceState({ lightlinkView: "research" }, "", researchListPath());
        setResearchDetailProjectId(null);
        setResearchDetail(null);
        setResearchDetailError("");
      }
      setResearchMessage("项目及其版本、证据和候选产品已删除。");
    } catch (error) {
      setResearchDeleteMessage(error instanceof Error ? error.message : "删除调研项目失败");
    } finally {
      setResearchDeleteBusy(false);
    }
  };

  const updateResearchCandidateStage = async (
    candidate: ResearchCandidate,
    stage: ResearchCandidate["stage"],
    activity?: { note?: string; evidenceUrl?: string; nextAction?: string; followUpAt?: string },
  ) => {
    if (!researchDetail) return;
    setResearchBusy(true);
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "update_research_candidate",
          projectId: researchDetail.project.id,
          candidateId: candidate.id,
          stage,
          note: activity?.note,
          evidenceUrl: activity?.evidenceUrl,
          nextAction: activity?.nextAction,
          followUpAt: activity?.followUpAt,
        }),
      });
      const result = (await response.json()) as { error?: string; activity?: ResearchCandidateActivity };
      if (!response.ok) throw new Error(result.error ?? "更新候选产品失败");
      setResearchDetail((current) => current ? {
        ...current,
        candidates: current.candidates.map((item) => item.id === candidate.id ? { ...item, stage } : item),
        activities: result.activity ? [result.activity, ...current.activities] : current.activities,
      } : current);
      setResearchCandidateActionTarget((current) => current?.id === candidate.id ? { ...current, stage } : current);
      setResearchMessage(`“${candidate.name}”已更新为${RESEARCH_CANDIDATE_STAGE_LABELS[stage]}。`);
      return true;
    } catch (error) {
      setResearchMessage(error instanceof Error ? error.message : "更新候选产品失败");
      return false;
    } finally {
      setResearchBusy(false);
    }
  };

  const openResearchCandidateAction = (candidate: ResearchCandidate) => {
    setResearchCandidateActionTarget(candidate);
    setResearchCandidateActionStage(candidate.stage);
    setResearchCandidateActionNote("");
    setResearchCandidateEvidenceUrl("");
    setResearchCandidateNextAction(RESEARCH_CANDIDATE_NEXT_ACTIONS[candidate.stage]);
    setResearchCandidateFollowUpAt("");
    setResearchCandidateAiMessage("");
  };

  const saveResearchCandidateAction = async (stageOverride?: ResearchCandidate["stage"]) => {
    if (!researchCandidateActionTarget) return;
    const stage = stageOverride ?? researchCandidateActionStage;
    setResearchCandidateActionBusy(true);
    const saved = await updateResearchCandidateStage(researchCandidateActionTarget, stage, {
      note: researchCandidateActionNote.trim(),
      evidenceUrl: researchCandidateEvidenceUrl.trim(),
      nextAction: researchCandidateNextAction.trim(),
      followUpAt: researchCandidateFollowUpAt,
    });
    setResearchCandidateActionBusy(false);
    if (saved) setResearchCandidateActionTarget(null);
  };

  const openResearchSelection = (candidate: ResearchCandidate) => {
    setResearchSelectionTarget(candidate);
    setResearchSelectionDraft(normalizeCandidateSelectionAssessment(candidate.selection_assessment));
    setResearchSelectionFamily(candidate.product_family || candidate.subcategory || "");
    setResearchSelectionMessage("");
  };

  const saveResearchSelection = async () => {
    if (!researchDetail || !researchSelectionTarget || !researchSelectionDraft) return;
    setResearchSelectionBusy(true);
    setResearchSelectionMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "update_research_candidate_assessment",
          projectId: researchDetail.project.id,
          candidateId: researchSelectionTarget.id,
          productFamily: researchSelectionFamily,
          assessment: researchSelectionDraft,
        }),
      });
      const result = (await response.json()) as { candidate?: ResearchCandidate; error?: string };
      if (!response.ok || !result.candidate) throw new Error(result.error ?? "保存选品评估失败");
      setResearchDetail((current) => current ? {
        ...current,
        candidates: current.candidates.map((item) => item.id === result.candidate?.id ? result.candidate : item),
      } : current);
      setResearchSelectionTarget(result.candidate);
      setResearchSelectionDraft(result.candidate.selection_assessment);
      setResearchSelectionMessage(result.candidate.handoff_readiness.ready
        ? "评估已保存。该候选现已达到 Odoo 移交门槛，但仍需在 Odoo 内完成正式审批。"
        : `评估已保存；还需补充：${result.candidate.handoff_readiness.blockers.slice(0, 3).join("、")}`);
      setResearchMessage(`“${result.candidate.name}”的标准选品评估已保存。`);
    } catch (error) {
      setResearchSelectionMessage(error instanceof Error ? error.message : "保存选品评估失败");
    } finally {
      setResearchSelectionBusy(false);
    }
  };

  const exportResearchCandidateToOdoo = (candidate: ResearchCandidate) => {
    if (!researchDetail) return;
    if (!candidate.handoff_readiness.ready) {
      openResearchSelection(candidate);
      setResearchSelectionMessage(`尚不能移交：${candidate.handoff_readiness.blockers.slice(0, 4).join("、")}`);
      return;
    }
    const params = new URLSearchParams({
      view: "research_odoo_handoff",
      projectId: researchDetail.project.id,
      candidateId: candidate.id,
    });
    window.open(`/api/radar?${params.toString()}`, "_blank", "noopener,noreferrer");
  };

  const openNewResearchBuyer = () => {
    setResearchBuyerTarget(null);
    setResearchBuyerDraft(emptyResearchBuyerDraft());
    setResearchBuyerMessage("");
    setResearchBuyerCreateOpen(true);
  };

  const openEditResearchBuyer = (buyer: ResearchBuyerProfile) => {
    setResearchBuyerTarget(buyer);
    setResearchBuyerDraft({
      companyName: buyer.company_name,
      website: buyer.website,
      country: buyer.country,
      buyerType: buyer.buyer_type,
      personaCode: "",
      regionCode: "",
      customerGroups: buyer.customer_groups.join("、"),
      salesChannels: buyer.sales_channels.join("、"),
      purchasingScenarios: buyer.purchasing_scenarios.join("\n"),
      seasonality: buyer.seasonality,
      replenishmentCycle: buyer.replenishment_cycle,
      orderRequirements: buyer.order_requirements,
      sourceUrl: buyer.source_url,
      profileStatus: buyer.profile_status,
      odooLeadId: buyer.odoo_lead_id ? String(buyer.odoo_lead_id) : "",
    });
    setResearchBuyerMessage("");
    setResearchBuyerCreateOpen(true);
  };

  const saveResearchBuyer = async () => {
    if (!researchDetail) return;
    setResearchBuyerBusy(true);
    setResearchBuyerMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "upsert_research_buyer_profile",
          projectId: researchDetail.project.id,
          buyerId: researchBuyerTarget?.id,
          ...researchBuyerDraft,
          customerGroups: splitResearchListInput(researchBuyerDraft.customerGroups),
          salesChannels: splitResearchListInput(researchBuyerDraft.salesChannels),
          purchasingScenarios: splitResearchListInput(researchBuyerDraft.purchasingScenarios),
        }),
      });
      const result = (await response.json()) as { buyer?: ResearchBuyerProfile; error?: string };
      if (!response.ok || !result.buyer) throw new Error(result.error ?? "保存买家画像失败");
      const savedBuyer = result.buyer;
      setResearchDetail((current) => current ? {
        ...current,
        buyerProfiles: current.buyerProfiles.some((item) => item.id === savedBuyer.id)
          ? current.buyerProfiles.map((item) => item.id === savedBuyer.id ? savedBuyer : item)
          : [savedBuyer, ...current.buyerProfiles],
      } : current);
      setResearchBuyerCreateOpen(false);
      setResearchBuyerMessage("");
      setResearchMessage(`真实买家“${savedBuyer.company_name}”的画像已保存。`);
    } catch (error) {
      setResearchBuyerMessage(error instanceof Error ? error.message : "保存买家画像失败");
    } finally {
      setResearchBuyerBusy(false);
    }
  };

  const openResearchBuyerMatrix = (buyer: ResearchBuyerProfile) => {
    const existing = new Map((researchDetail?.buyerFamilyLinks ?? []).filter((link) => link.buyer_profile_id === buyer.id)
      .map((link) => [`${link.track_category}|${link.product_family}`.toLocaleLowerCase(), link]));
    setResearchBuyerFamilyDrafts(researchProductFamilies.map((family) => {
      const key = `${family.track}|${family.name}`.toLocaleLowerCase();
      const link = existing.get(key);
      const matchingCandidates = researchCandidates.filter((candidate) => family.candidateIds.includes(candidate.id) && candidate.buyer_types.includes(buyer.buyer_type));
      return {
        key,
        trackCategory: family.track,
        productFamily: family.name,
        enabled: Boolean(link),
        relationshipScore: link?.relationship_score ?? Math.min(85, matchingCandidates.length ? 50 + matchingCandidates.length * 5 : 30),
        familyRole: link?.family_role ?? "test",
        salesScenarios: link?.sales_scenarios.join("、") ?? buyer.purchasing_scenarios.join("、"),
        rationale: link?.rationale ?? "",
        evidenceStatus: link?.evidence_status ?? "hypothesis",
      };
    }));
    setResearchBuyerMatrixTarget(buyer);
    setResearchBuyerFamilySearch("");
    setResearchBuyerMessage("");
  };

  const saveResearchBuyerMatrix = async () => {
    if (!researchDetail || !researchBuyerMatrixTarget) return;
    setResearchBuyerMatrixBusy(true);
    setResearchBuyerMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "update_research_buyer_family_matrix",
          projectId: researchDetail.project.id,
          buyerId: researchBuyerMatrixTarget.id,
          links: researchBuyerFamilyDrafts.filter((item) => item.enabled).map((item) => ({
            ...item,
            salesScenarios: splitResearchListInput(item.salesScenarios),
          })),
        }),
      });
      const result = (await response.json()) as { links?: ResearchBuyerFamilyLink[]; error?: string };
      if (!response.ok || !result.links) throw new Error(result.error ?? "保存产品家族矩阵失败");
      const savedLinks = result.links;
      setResearchDetail((current) => current ? {
        ...current,
        buyerFamilyLinks: [...current.buyerFamilyLinks.filter((link) => link.buyer_profile_id !== researchBuyerMatrixTarget.id), ...savedLinks],
      } : current);
      setResearchBuyerMatrixTarget(null);
      setResearchMessage(`“${researchBuyerMatrixTarget.company_name}”已关联 ${savedLinks.length} 个产品家族。`);
    } catch (error) {
      setResearchBuyerMessage(error instanceof Error ? error.message : "保存产品家族矩阵失败");
    } finally {
      setResearchBuyerMatrixBusy(false);
    }
  };

  const openNewGlobalBuyer = () => {
    setGlobalBuyerTarget(null);
    setGlobalBuyerDraft(emptyResearchBuyerDraft());
    setGlobalBuyerMessage("");
    setGlobalBuyerCreateOpen(true);
  };

  const openEditGlobalBuyer = (buyer: GlobalBuyerProfile) => {
    setGlobalBuyerTarget(buyer);
    setGlobalBuyerDraft({
      companyName: buyer.company_name,
      website: buyer.website,
      country: buyer.country,
      buyerType: buyer.buyer_type,
      personaCode: buyer.persona_code,
      regionCode: buyer.region_code,
      customerGroups: buyer.customer_groups.join("、"),
      salesChannels: buyer.sales_channels.join("、"),
      purchasingScenarios: buyer.purchasing_scenarios.join("\n"),
      seasonality: buyer.seasonality,
      replenishmentCycle: buyer.replenishment_cycle,
      orderRequirements: buyer.order_requirements,
      sourceUrl: buyer.source_url,
      profileStatus: buyer.profile_status,
      odooLeadId: "",
    });
    setGlobalBuyerMessage("");
    setGlobalBuyerCreateOpen(true);
  };

  const saveGlobalBuyer = async () => {
    setGlobalBuyerBusy(true);
    setGlobalBuyerMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "upsert_global_buyer_profile",
          buyerId: globalBuyerTarget?.id,
          ...globalBuyerDraft,
          customerGroups: splitResearchListInput(globalBuyerDraft.customerGroups),
          salesChannels: splitResearchListInput(globalBuyerDraft.salesChannels),
          purchasingScenarios: splitResearchListInput(globalBuyerDraft.purchasingScenarios),
        }),
      });
      const result = (await response.json()) as { buyer?: GlobalBuyerProfile; error?: string };
      if (!response.ok || !result.buyer) throw new Error(result.error ?? "保存全球买家画像失败");
      setGlobalBuyerCreateOpen(false);
      setGlobalBuyerMessage(`“${result.buyer.company_name}”已保存到全球买家知识库。`);
      await loadResearch();
    } catch (error) {
      setGlobalBuyerMessage(error instanceof Error ? error.message : "保存全球买家画像失败");
    } finally {
      setGlobalBuyerBusy(false);
    }
  };

  const openGlobalBuyerMatrix = (buyer: GlobalBuyerProfile) => {
    const existing = new Map(globalBuyerLinks.filter((link) => link.buyer_profile_id === buyer.id)
      .map((link) => [`${link.track_category}|${link.product_family}`.toLocaleLowerCase(), link]));
    setGlobalBuyerFamilyDrafts(globalProductFamilyMaster.map((family) => {
      const key = `${family.track_name}|${family.name}`.toLocaleLowerCase();
      const link = existing.get(key);
      const affinity = globalPersonaMatrix.find((item) => item.persona_code === buyer.persona_code
        && item.track_code === family.track_code
        && [buyer.region_code, "GLOBAL"].includes(item.region_code));
      return {
        key,
        trackCategory: family.track_name,
        productFamily: family.name,
        enabled: Boolean(link),
        relationshipScore: link?.relationship_score ?? affinity?.relevance_score ?? 30,
        familyRole: link?.family_role ?? affinity?.family_role ?? "test",
        salesScenarios: link?.sales_scenarios.join("、") ?? affinity?.sales_scenarios.join("、") ?? buyer.purchasing_scenarios.join("、"),
        rationale: link?.rationale ?? affinity?.rationale ?? "",
        evidenceStatus: link?.evidence_status ?? "hypothesis",
      };
    }));
    setGlobalBuyerMatrixTarget(buyer);
    setGlobalBuyerFamilySearch("");
    setGlobalBuyerMessage("");
  };

  const saveGlobalBuyerMatrix = async () => {
    if (!globalBuyerMatrixTarget) return;
    setGlobalBuyerMatrixBusy(true);
    setGlobalBuyerMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "update_global_buyer_family_matrix",
          buyerId: globalBuyerMatrixTarget.id,
          links: globalBuyerFamilyDrafts.filter((item) => item.enabled).map((item) => ({
            ...item,
            salesScenarios: splitResearchListInput(item.salesScenarios),
          })),
        }),
      });
      const result = (await response.json()) as { links?: GlobalBuyerFamilyLink[]; error?: string };
      if (!response.ok || !result.links) throw new Error(result.error ?? "保存全球产品家族矩阵失败");
      setGlobalBuyerMatrixTarget(null);
      setGlobalBuyerMessage(`“${globalBuyerMatrixTarget.company_name}”已关联 ${result.links.length} 个共享产品家族。`);
      await loadResearch();
    } catch (error) {
      setGlobalBuyerMessage(error instanceof Error ? error.message : "保存全球产品家族矩阵失败");
    } finally {
      setGlobalBuyerMatrixBusy(false);
    }
  };

  const saveTaxonomyRecord = async (payload: Record<string, unknown>, close: () => void, successMessage: string) => {
    setGlobalTaxonomyBusy(true);
    setGlobalBuyerMessage("");
    try {
      const response = await fetch("/api/radar", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
      const result = (await response.json()) as GlobalBuyerLibrary & { error?: string };
      if (!response.ok || result.error) throw new Error(result.error ?? "保存分类主数据失败");
      close();
      setGlobalBuyerMessage(successMessage);
      await loadResearch();
    } catch (error) {
      setGlobalBuyerMessage(error instanceof Error ? error.message : "保存分类主数据失败");
    } finally {
      setGlobalTaxonomyBusy(false);
    }
  };

  const openPersonaCategoryEditor = (item?: BuyerPersonaCategory) => {
    setPersonaCategoryTarget(item ?? null);
    setPersonaCategoryDraft(item ? {
      code: item.code, groupName: item.group_name, name: item.name, description: item.description,
      valueChainRole: item.value_chain_role, customerGroups: item.customer_groups.join("、"),
      salesChannels: item.sales_channels.join("、"), purchaseScenarios: item.purchase_scenarios.join("、"),
      buyingTriggers: item.buying_triggers.join("、"), orderCharacteristics: item.order_characteristics.join("、"),
      complianceFocus: item.compliance_focus.join("、"), sourceRefs: item.source_refs.join("\n"),
    } : emptyPersonaCategoryDraft());
    setGlobalBuyerMessage("");
    setPersonaCategoryEditorOpen(true);
  };

  const savePersonaCategory = () => saveTaxonomyRecord({
    action: "upsert_buyer_persona_category", ...personaCategoryDraft,
    customerGroups: splitResearchListInput(personaCategoryDraft.customerGroups),
    salesChannels: splitResearchListInput(personaCategoryDraft.salesChannels),
    purchaseScenarios: splitResearchListInput(personaCategoryDraft.purchaseScenarios),
    buyingTriggers: splitResearchListInput(personaCategoryDraft.buyingTriggers),
    orderCharacteristics: splitResearchListInput(personaCategoryDraft.orderCharacteristics),
    complianceFocus: splitResearchListInput(personaCategoryDraft.complianceFocus),
    sourceRefs: splitResearchListInput(personaCategoryDraft.sourceRefs),
  }, () => setPersonaCategoryEditorOpen(false), `画像分类“${personaCategoryDraft.name}”已保存。`);

  const setPersonaCategoryActive = async (item: BuyerPersonaCategory, active: boolean) => {
    setGlobalTaxonomyBusy(true);
    setGlobalBuyerMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "set_buyer_persona_category_active", code: item.code, active }),
      });
      const result = (await response.json()) as GlobalBuyerLibrary & { error?: string };
      if (!response.ok || result.error) throw new Error(result.error ?? "更新画像分类状态失败");
      setPersonaDeleteTarget(null);
      setGlobalBuyerMessage(active ? `画像分类“${item.name}”已恢复。` : `画像分类“${item.name}”已从在用分类中删除；历史引用和版本仍然保留。`);
      await loadResearch();
    } catch (error) {
      setGlobalBuyerMessage(error instanceof Error ? error.message : "更新画像分类状态失败");
    } finally {
      setGlobalTaxonomyBusy(false);
    }
  };

  const openPersonaAiAssistant = (item?: BuyerPersonaCategory) => {
    setPersonaAiMode(item ? "enrich" : "discover");
    setPersonaAiTargetCode(item?.code ?? "");
    setPersonaAiRequestedCount(item ? "1" : "3");
    setPersonaAiMessage("");
    setPersonaAiOpen(true);
  };

  const dispatchPersonaAiAssistant = async () => {
    if (taxonomyAssistChannelJob) {
      setPersonaAiMessage("画像分类通道已有任务执行中，其他调研通道不受影响。");
      return;
    }
    const requestedCount = Math.max(1, Math.min(10, Number(personaAiRequestedCount) || 3));
    setPersonaAiBusy(true);
    setPersonaAiMessage("正在发送给 ChatGPT / Codex 画像分类通道…");
    try {
      const response = await fetch("http://127.0.0.1:8788/dispatch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          taskType: "taxonomy_assist",
          runId: crypto.randomUUID(),
          mode: personaAiMode,
          personaCode: personaAiMode === "enrich" ? personaAiTargetCode : "",
          requestedCount,
          requestNote: personaAiRequestNote,
        }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "画像分类任务发送失败");
      setPersonaAiOpen(false);
      setGlobalBuyerMessage("AI画像任务已发送。完成后会进入“AI待审核”，不会直接覆盖正式分类。");
    } catch (error) {
      setPersonaAiMessage(error instanceof Error ? error.message : "画像分类任务发送失败");
    } finally {
      setPersonaAiBusy(false);
    }
  };

  const reviewPersonaProposal = async (proposal: BuyerPersonaProposal, decision: "apply" | "reject") => {
    setGlobalTaxonomyBusy(true);
    setGlobalBuyerMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "review_buyer_persona_proposal", proposalId: proposal.id, decision }),
      });
      const result = (await response.json()) as GlobalBuyerLibrary & { error?: string };
      if (!response.ok || result.error) throw new Error(result.error ?? "审核AI画像建议失败");
      setGlobalBuyerMessage(decision === "apply" ? `AI建议“${String(proposal.payload.name ?? proposal.persona_code)}”已应用并形成新版本。` : "AI画像建议已驳回，审核记录仍然保留。");
      await loadResearch();
    } catch (error) {
      setGlobalBuyerMessage(error instanceof Error ? error.message : "审核AI画像建议失败");
    } finally {
      setGlobalTaxonomyBusy(false);
    }
  };

  const openProductTrackEditor = (item?: ProductTrackMaster) => {
    setProductTrackTarget(item ?? null);
    setProductTrackDraft(item ? { code: item.code, name: item.name, description: item.description, buyerValue: item.buyer_value, complianceFocus: item.compliance_focus.join("、") } : emptyProductTrackDraft());
    setGlobalBuyerMessage("");
    setProductTrackEditorOpen(true);
  };

  const saveProductTrack = () => saveTaxonomyRecord({
    action: "upsert_product_track", ...productTrackDraft,
    complianceFocus: splitResearchListInput(productTrackDraft.complianceFocus),
  }, () => setProductTrackEditorOpen(false), `产品赛道“${productTrackDraft.name}”已保存。`);

  const openProductFamilyEditor = (item?: ProductFamilyMaster, trackCode = "") => {
    setProductFamilyTarget(item ?? null);
    setProductFamilyDraft(item ? {
      code: item.code, trackCode: item.track_code, name: item.name, description: item.description,
      useScenarios: item.use_scenarios.join("、"), complianceTags: item.compliance_tags.join("、"), keywords: item.keywords.join("、"),
    } : { ...emptyProductFamilyMasterDraft(), trackCode });
    setGlobalBuyerMessage("");
    setProductFamilyEditorOpen(true);
  };

  const saveProductFamilyMaster = () => saveTaxonomyRecord({
    action: "upsert_product_family_master", ...productFamilyDraft,
    useScenarios: splitResearchListInput(productFamilyDraft.useScenarios),
    complianceTags: splitResearchListInput(productFamilyDraft.complianceTags),
    keywords: splitResearchListInput(productFamilyDraft.keywords),
  }, () => setProductFamilyEditorOpen(false), `产品家族“${productFamilyDraft.name}”已保存。`);

  const openPersonaMatrixEditor = (item?: PersonaProductMatrix) => {
    setPersonaMatrixTarget(item ?? null);
    setPersonaMatrixDraft(item ? {
      personaCode: item.persona_code, regionCode: item.region_code, trackCode: item.track_code,
      productFamilyCode: item.product_family_code, relevanceScore: item.relevance_score,
      familyRole: item.family_role, salesScenarios: item.sales_scenarios.join("、"), seasonality: item.seasonality,
      rationale: item.rationale, evidenceStatus: item.evidence_status,
    } : emptyPersonaMatrixDraft());
    setGlobalBuyerMessage("");
    setPersonaMatrixEditorOpen(true);
  };

  const openNewPersonaMatrixForPersona = (personaCode: string, trackCode = "") => {
    setPersonaMatrixTarget(null);
    setPersonaMatrixDraft({ ...emptyPersonaMatrixDraft(), personaCode, trackCode });
    setGlobalBuyerMessage("");
    setPersonaMatrixEditorOpen(true);
  };

  const openValidationProgramFromPersona = (persona: BuyerPersonaCategory, link?: PersonaProductMatrix) => {
    const family = link ? globalProductFamilyMaster.find((item) => item.code === link.product_family_code) : null;
    const buyerRegion = globalBuyerProfiles.find((buyer) => buyer.persona_code === persona.code && buyer.region_code && buyer.region_code !== "GLOBAL")?.region_code;
    const regionCode = link && link.region_code !== "GLOBAL" ? link.region_code : buyerRegion ?? "GLOBAL";
    const regionName = globalTradeRegions.find((region) => region.code === regionCode)?.name ?? "全球";
    const purchaseScenario = link?.sales_scenarios[0] || persona.purchase_scenarios[0] || "验证持续采购需求";
    const salesChannel = persona.sales_channels[0] || "B2B直接开发";
    setOpportunitySeed({
      personaCode: persona.code,
      regionCode,
      matrixIds: link ? [link.id] : [],
      purchaseScenario,
      salesChannel,
      hypothesis: `${regionName}的${persona.name}在“${purchaseScenario}”场景下，可能通过${salesChannel}持续采购${family ? family.name : "一组关联产品家族"}；需要用本地贸易数据、真实买家反馈和供应报价验证。`,
    });
    setPersonaDetailCode(null);
    setGlobalBuyerLibraryOpen(false);
    setActiveView("opportunities");
    window.history.pushState({ lightlinkView: "opportunities", validationProgramPrefill: true }, "", "/?view=opportunities");
    window.scrollTo({ top: 0 });
  };

  const consumeOpportunitySeed = useCallback(() => setOpportunitySeed(null), []);

  const savePersonaMatrix = () => saveTaxonomyRecord({
    action: "upsert_persona_product_matrix", ...personaMatrixDraft,
    salesScenarios: splitResearchListInput(personaMatrixDraft.salesScenarios),
  }, () => setPersonaMatrixEditorOpen(false), "画像—产品关系已保存。" );

  const openRealBuyerResearch = () => {
    if (!researchDetail) return;
    setResearchRequestNote("本轮以真实批发买家为起点：优先查找有公开官网或采购/经销证据的进口商、批发商、分销商和专业零售商；为每家建立买家画像、终端客群、销售渠道、采购场景、季节性、补货周期与订单要求，再关联跨赛道产品家族矩阵。公司和关系必须附直接来源链接；无法核验保持待核实，不得猜测采购额或私人联系方式。候选产品只作为家族矩阵末端补充。 ");
    openResearchRunDialog(researchDetail.project, "review");
  };

  const fillResearchCandidateExample = () => {
    if (!researchCandidateActionTarget) return;
    const example = RESEARCH_CANDIDATE_STAGE_EXAMPLES[researchCandidateActionTarget.stage];
    setResearchCandidateActionNote(example.note);
    setResearchCandidateNextAction(example.nextAction);
    setResearchCandidateAiMessage("已填入示例，请把方括号提示和示例数据替换为你的真实结果后再保存。");
  };

  const dispatchResearchCandidateAssist = async () => {
    if (!researchDetail || !researchCandidateActionTarget) return;
    if (candidateAssistChannelJob) {
      setResearchCandidateAiMessage("产品调研通道已有任务执行中；关键词、整项目调研和图片通道不受影响。");
      return;
    }
    setResearchCandidateAiBusy(true);
    setResearchCandidateAiMessage("正在发送给 Codex / ChatGPT…");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "create_candidate_assist",
          projectId: researchDetail.project.id,
          candidateId: researchCandidateActionTarget.id,
          requestNote: researchCandidateActionNote.trim(),
        }),
      });
      const task = (await response.json()) as { dispatchTask?: Record<string, unknown>; error?: string };
      if (!response.ok || !task.dispatchTask) throw new Error(task.error ?? "建立AI辅助任务失败");
      const channelResponse = await fetch("http://127.0.0.1:8788/dispatch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ taskType: "candidate_assist", ...task.dispatchTask }),
      });
      const channelResult = (await channelResponse.json()) as { accepted?: boolean; error?: string };
      if (!channelResponse.ok || !channelResult.accepted) throw new Error(channelResult.error ?? "Codex 自动通道未响应");
      setCodexChannelState("ready");
      setResearchCandidateAiMessage("AI正在核实需求、价格、MOQ、合规、买家和产品图片；完成后建议会出现在下方历史记录中，不会自动改变阶段。");
    } catch (error) {
      setResearchCandidateAiMessage(error instanceof Error ? error.message : "AI辅助调研发送失败");
    } finally {
      setResearchCandidateAiBusy(false);
    }
  };

  const dispatchCandidateImageAssist = async () => {
    if (!researchDetail || candidateImagesChannelJob) return;
    const candidates = pagedResearchCandidates.filter((item) => !item.image_urls.some(isSafeSourceUrl)).slice(0, 25);
    if (!candidates.length) {
      setResearchMessage("当前页产品都已有图片，无需补图。");
      return;
    }
    setResearchImageAssistBusy(true);
    setResearchMessage(`正在为当前页 ${candidates.length} 个缺图产品建立AI补图任务…`);
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "create_candidate_image_assist", projectId: researchDetail.project.id, candidateIds: candidates.map((item) => item.id) }),
      });
      const task = (await response.json()) as { dispatchTask?: Record<string, unknown>; error?: string };
      if (!response.ok || !task.dispatchTask) throw new Error(task.error ?? "建立AI补图任务失败");
      const channelResponse = await fetch("http://127.0.0.1:8788/dispatch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ taskType: "candidate_images", ...task.dispatchTask }),
      });
      const channelResult = (await channelResponse.json()) as { accepted?: boolean; error?: string };
      if (!channelResponse.ok || !channelResult.accepted) throw new Error(channelResult.error ?? "Codex 自动通道未响应");
      setCodexChannelState("ready");
      setResearchMessage(`已发送 ${candidates.length} 个产品给AI补图；优先商品页原图，也接受带落地链接的匹配搜索缩略图。`);
    } catch (error) {
      setResearchMessage(error instanceof Error ? error.message : "AI补图任务发送失败");
    } finally {
      setResearchImageAssistBusy(false);
    }
  };

  const openResearchMarketAction = (marketItem: ResearchMarketHypothesis) => {
    const status = researchMarketStatus(marketItem);
    setResearchMarketActionTarget(marketItem);
    setResearchMarketActionStatus(status);
    setResearchMarketActionNote("");
    setResearchMarketEvidenceUrl("");
    setResearchMarketNextAction(status === "hypothesis" ? "找到3个真实买家信号并核对价格与合规门槛" : "补充下一条可核验证据");
    setResearchMarketFollowUpAt("");
    setResearchMarketActionMessage("");
  };

  const fillResearchMarketExample = () => {
    setResearchMarketActionNote("【示例，请替换为真实结果】已找到目标买家/商品页，并记录需求场景、售价或采购条件；当前证据不足以推断整体市场规模。");
    setResearchMarketNextAction("联系3个目标买家，记录回复、目标价格、采购量和拒绝原因");
    setResearchMarketActionMessage("示例仅用于说明填写方式，请替换为真实证据后再保存。");
  };

  const saveResearchMarketAction = async () => {
    if (!researchDetail || !researchMarketActionTarget) return;
    const marketCode = String(researchMarketActionTarget.marketCode ?? "").toUpperCase();
    setResearchMarketActionBusy(true);
    setResearchMarketActionMessage("");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "update_research_market",
          projectId: researchDetail.project.id,
          marketCode,
          fromStatus: researchMarketStatus(researchMarketActionTarget),
          status: researchMarketActionStatus,
          note: researchMarketActionNote.trim(),
          evidenceUrl: researchMarketEvidenceUrl.trim(),
          nextAction: researchMarketNextAction.trim(),
          followUpAt: researchMarketFollowUpAt,
        }),
      });
      const result = (await response.json()) as { error?: string; activity?: ResearchMarketActivity };
      if (!response.ok || !result.activity) throw new Error(result.error ?? "保存市场验证记录失败");
      setResearchDetail((current) => current ? { ...current, marketActivities: [result.activity as ResearchMarketActivity, ...current.marketActivities] } : current);
      setResearchMessage(`${String(researchMarketActionTarget.marketName ?? marketCode)} 已更新为${RESEARCH_VALIDATION_LABELS[researchMarketActionStatus]}。`);
      setResearchMarketActionTarget(null);
    } catch (error) {
      setResearchMarketActionMessage(error instanceof Error ? error.message : "保存市场验证记录失败");
    } finally {
      setResearchMarketActionBusy(false);
    }
  };

  const runScan = async (mode: "seed" | "discover" = "seed") => {
    const trimmed = query.trim();
    if (!trimmed) {
      setScanMessage(mode === "discover" ? "请输入产品类目" : "请输入关键词");
      return;
    }
    setBusy(true);
    setScanMessage("正在创建采集任务…");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "create_scan", mode, query: trimmed, market, language, windowDays: Number(windowDays) }),
      });
      const result = (await response.json()) as { runId?: string; error?: string };
      if (!response.ok) throw new Error(result.error ?? "创建任务失败");
      setPendingRunId(result.runId ?? null);
      setScanMessage(`已创建“${trimmed}”任务 · 等待真实证据`);
      setImportOpen(true);
      await loadDashboard();
    } catch (error) {
      setScanMessage(error instanceof Error ? error.message : "创建任务失败");
    } finally {
      setBusy(false);
    }
  };

  const runAssistant = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      setAssistantMessage(scanMode === "discover" ? "请先输入产品类目" : "请先输入关键词");
      return;
    }
    if (!openAiIntegration?.configured && !apiKey.trim()) {
      setAssistantMessage("还没有 OpenAI API Key。可在下方临时填写，或优先使用无需网页密钥的 Codex 通道。");
      return;
    }
    setBusy(true);
    setAssistantMessage("正在扩词、检索公开证据并校验数据，通常需要几十秒…");
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "assistant_generate",
          query: trimmed,
          market,
          language,
          windowDays: Number(windowDays),
          scanMode,
          resultLimit: Number(resultLimit),
          requestNote: assistantRequest,
          apiKey: apiKey.trim() || undefined,
        }),
      });
      const result = (await response.json()) as { importedRows?: number; summary?: string; error?: string };
      if (!response.ok) throw new Error(result.error ?? "AI 整理失败");
      setAssistantMessage(`已生成并保存 ${result.importedRows ?? 0} 条观测。${result.summary ?? ""}`);
      setScanMessage("AI 整理结果已入库，可在机会发现、数据来源和全局任务中心中查看");
      await loadDashboard();
      window.setTimeout(() => setAssistantOpen(false), 1200);
    } catch (error) {
      setAssistantMessage(error instanceof Error ? error.message : "AI 整理失败");
    } finally {
      setBusy(false);
    }
  };

  const prepareCodexTask = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      setAssistantMessage(scanMode === "discover" ? "请先输入产品类目" : "请先输入关键词");
      return;
    }
    if (radarChannelJob) {
      setAssistantMessage("关键词雷达通道已有任务执行中；产品调研、整项目调研和图片采集仍可并行使用。");
      return;
    }
    setBusy(true);
    setAssistantMessage("正在建立 Codex 可读取的雷达任务…");
    try {
      const currentRun = data?.run;
      let runId = "";
      if (
        currentRun
        && !currentRun.is_demo
        && currentRun.query === trimmed
        && currentRun.market === market
        && currentRun.language === language
        && Number(currentRun.window_days) === Number(windowDays)
        && currentRun.status === "waiting_for_data"
      ) {
        runId = currentRun.id;
      }
      if (!runId) {
        const response = await fetch("/api/radar", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            action: "create_scan",
            mode: scanMode,
            query: trimmed,
            market,
            language,
            windowDays: Number(windowDays),
          }),
        });
        const result = (await response.json()) as { runId?: string; error?: string };
        if (!response.ok || !result.runId) throw new Error(result.error ?? "建立 Codex 任务失败");
        runId = result.runId;
      }
      setPendingRunId(runId);
      const channelResponse = await fetch("http://127.0.0.1:8788/dispatch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          runId,
          query: trimmed,
          market,
          language,
          windowDays: Number(windowDays),
          resultLimit: Number(resultLimit),
          mode: scanMode,
          requestNote: assistantRequest,
        }),
      });
      const channelResult = (await channelResponse.json()) as { accepted?: boolean; threadId?: string; error?: string };
      if (!channelResponse.ok || !channelResult.accepted) {
        throw new Error(channelResult.error ?? "Codex 自动通道未响应，请重新启动雷达");
      }
      setCodexChannelState("ready");
      setScanMessage(`已发送“${trimmed}”到 Codex · 正在整理`);
      setAssistantMessage(`已发送到独立的“LightLink Radar 关键词雷达”任务（${channelResult.threadId?.slice(0, 8) ?? "已接收"}）。其他 AI 通道可以同时工作；完成后结果会写回工作台和历史记录。`);
      await loadDashboard();
    } catch (error) {
      setAssistantMessage(error instanceof Error ? error.message : "发送 Codex 任务失败");
    } finally {
      setBusy(false);
    }
  };

  const toggleSaved = async (id: string) => {
    const shouldWatch = !savedIds.includes(id);
    setSavedIds((current) => shouldWatch ? [...current, id] : current.filter((item) => item !== id));
    const response = await fetch("/api/radar", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        action: "set_cluster_status",
        clusterId: id,
        status: shouldWatch ? "watching" : "candidate",
        cadenceDays: 7,
      }),
    });
    if (!response.ok) {
      setScanMessage("观察状态保存失败，请重试");
      setSavedIds((current) => shouldWatch ? current.filter((item) => item !== id) : [...current, id]);
      return;
    }
    await loadDashboard();
  };

  const splitAlias = async (alias: string) => {
    if (!selected) return;
    setBusy(true);
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "split_cluster", clusterId: selected.id, alias }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "拆分失败");
      setScanMessage(`已将“${alias}”拆成独立词簇`);
      setSelected(null);
      await loadDashboard();
    } catch (error) {
      setScanMessage(error instanceof Error ? error.message : "拆分失败");
    } finally {
      setBusy(false);
    }
  };

  const mergeIntoSelected = async () => {
    if (!selected || !mergeSourceId) return;
    const source = liveRows.find((row) => row.id === mergeSourceId);
    setBusy(true);
    try {
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "merge_clusters", targetId: selected.id, sourceId: mergeSourceId }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "合并失败");
      setScanMessage(`已将“${source?.keyword ?? "所选词簇"}”并入“${selected.keyword}”`);
      setMergeSourceId("");
      setSelected(null);
      await loadDashboard();
    } catch (error) {
      setScanMessage(error instanceof Error ? error.message : "合并失败");
    } finally {
      setBusy(false);
    }
  };

  const importFile = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setImportMessage("请选择 JSON、CSV 或 TSV 文件");
      return;
    }
    setBusy(true);
    setImportMessage("正在校验并写入本地数据库…");
    try {
      const text = await file.text();
      const parsed = file.name.toLowerCase().endsWith(".json") ? JSON.parse(text) : parseDelimited(text);
      const rawRows = Array.isArray(parsed) ? parsed : parsed.rows;
      if (!Array.isArray(rawRows)) throw new Error("文件中没有 rows 数组");
      const rowsForApi = rawRows.map((raw: Record<string, unknown>) => ({
        keyword: raw.keyword ?? raw["关键词"],
        groupName: raw.groupName ?? raw["词簇"],
        aliases: raw.aliases,
        category: raw.category ?? raw["类目"],
        keywordZh: raw.keywordZh ?? raw["中文品名"] ?? raw["中文翻译"],
        imageUrl: raw.imageUrl ?? raw["产品图片"] ?? raw["图片链接"],
        imageUrls: raw.imageUrls ?? raw["全部产品图片"] ?? raw["图片链接列表"],
        imageSourceRef: raw.imageSourceRef ?? raw["图片来源"],
        purchasePriceMin: raw.purchasePriceMin ?? raw["采购价最低"],
        purchasePriceMax: raw.purchasePriceMax ?? raw["采购价最高"],
        purchasePriceCurrency: raw.purchasePriceCurrency ?? raw["采购价币种"],
        purchasePriceUnit: raw.purchasePriceUnit ?? raw["采购价单位"],
        platform: raw.platform ?? raw["平台"],
        metric: raw.metric ?? raw["指标"],
        currentValue: raw.currentValue ?? raw["当前值"],
        previousValue: raw.previousValue ?? raw["前期值"],
        sampleN: raw.sampleN ?? raw["样本量"],
        uniqueActorN: raw.uniqueActorN ?? raw["独立主体数"],
        coverageDays: raw.coverageDays ?? raw["覆盖天数"] ?? Number(windowDays),
        sourceKind: raw.sourceKind ?? raw["来源类型"] ?? "manual_import",
        sourceRef: raw.sourceRef ?? raw["来源链接"],
        geoScope: raw.geoScope ?? raw["地区"] ?? market,
        status: raw.status ?? raw["状态"] ?? "ok",
        missingReason: raw.missingReason ?? raw["缺失原因"],
        collectedAt: raw.collectedAt ?? raw["采集时间"] ?? new Date().toISOString(),
      }));
      const response = await fetch("/api/radar", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "import_observations",
          runId: pendingRunId ?? (
            data?.run && !data.run.is_demo && data.run.query === query && data.run.market === market &&
            data.run.language === language && Number(data.run.window_days) === Number(windowDays)
              ? data.run.id
              : null
          ),
          query,
          market,
          language,
          windowDays: Number(windowDays),
          rows: rowsForApi,
        }),
      });
      const result = (await response.json()) as { importedRows?: number; error?: string };
      if (!response.ok) throw new Error(result.error ?? "导入失败");
      setImportMessage(`已导入 ${result.importedRows ?? rowsForApi.length} 行并完成评分`);
      setPendingRunId(null);
      await loadDashboard();
      setTimeout(() => setImportOpen(false), 700);
    } catch (error) {
      setImportMessage(error instanceof Error ? error.message : "导入失败");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const context = (document as Document & { modelContext?: WebMcpContext }).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const register = (tool: WebMcpTool) => {
      try {
        void Promise.resolve(context.registerTool(tool, { signal: lifecycle.signal })).catch(() => undefined);
      } catch {
        // WebMCP is optional; the visible interface remains fully functional.
      }
    };
    const inputObject = (input: unknown) => input && typeof input === "object" && !Array.isArray(input)
      ? input as Record<string, unknown>
      : {};

    register({
      name: "read_radar_summary",
      title: "读取产品机会雷达",
      description: "读取当前扫描、来源状态、观察列表和最高机会关键词，不修改数据。",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true, untrustedContentHint: true },
      execute() {
        return {
          run: data?.run ?? null,
          sources: data?.sources ?? [],
          watchlist: data?.watchlist ?? [],
          topResults: (data?.results ?? []).slice(0, 10),
        };
      },
    });

    register({
      name: "start_radar_scan",
      title: "建立产品雷达采集任务",
      description: "为关键词扫描或类目热点发现建立待采集任务，并在工作台打开证据导入入口。此操作不会虚构平台数据。",
      inputSchema: {
        type: "object",
        properties: {
          mode: { type: "string", enum: ["seed", "discover"] },
          query: { type: "string", minLength: 2 },
          market: { type: "string", enum: MARKET_CODES },
          language: { type: "string", enum: LANGUAGE_CODES },
          windowDays: { type: "integer", enum: [7, 30, 90] },
        },
        required: ["mode", "query", "market", "language", "windowDays"],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      async execute(input) {
        const candidate = inputObject(input);
        const mode = candidate.mode === "discover" ? "discover" : candidate.mode === "seed" ? "seed" : null;
        const nextQuery = String(candidate.query ?? "").trim();
        const nextMarket = String(candidate.market ?? "").toUpperCase();
        const nextLanguage = String(candidate.language ?? "").toLowerCase();
        const nextWindow = Number(candidate.windowDays);
        if (!mode || nextQuery.length < 2 || !SUPPORTED_MARKETS.has(nextMarket) || !SUPPORTED_LANGUAGES.has(nextLanguage) || ![7, 30, 90].includes(nextWindow)) {
          throw new Error("扫描参数无效");
        }
        const response = await fetch("/api/radar", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ action: "create_scan", mode, query: nextQuery, market: nextMarket, language: nextLanguage, windowDays: nextWindow }),
        });
        const result = await response.json() as { runId?: string; status?: string; error?: string };
        if (!response.ok || !result.runId) throw new Error(result.error ?? "创建采集任务失败");
        setQuery(nextQuery);
        setMarket(nextMarket);
        setLanguage(nextLanguage);
        setWindowDays(String(nextWindow));
        setPendingRunId(result.runId);
        setScanMessage(`已建立“${nextQuery}”任务 · 等待真实证据`);
        setImportOpen(true);
        await loadDashboard();
        return { runId: result.runId, status: result.status, nextStep: "collect_or_import_observations" };
      },
    });

    register({
      name: "import_radar_observations",
      title: "写入产品雷达证据",
      description: "把已采集的平台观测增量写入指定任务，校验后重新聚类和评分。失败、缺失与确认零必须分别标记。",
      inputSchema: {
        type: "object",
        properties: {
          runId: { type: "string" },
          query: { type: "string", minLength: 2 },
          market: { type: "string", enum: MARKET_CODES },
          language: { type: "string", enum: LANGUAGE_CODES },
          windowDays: { type: "integer", enum: [7, 30, 90] },
          scanMode: { type: "string", enum: ["seed", "discover"] },
          resultLimit: { type: "integer", enum: [10, 15, 20] },
          rows: {
            type: "array",
            minItems: 1,
            maxItems: 1000,
            items: {
              type: "object",
              properties: {
                keyword: { type: "string" },
                groupName: { type: "string" },
                aliases: { type: "array", items: { type: "string" } },
                category: { type: "string" },
                keywordZh: { type: ["string", "null"] },
                imageUrl: { type: ["string", "null"] },
                imageUrls: { type: "array", maxItems: 6, items: { type: "string" } },
                imageSourceRef: { type: ["string", "null"] },
                purchasePriceMin: { type: ["number", "null"], minimum: 0 },
                purchasePriceMax: { type: ["number", "null"], minimum: 0 },
                purchasePriceCurrency: { type: ["string", "null"], pattern: "^[A-Z]{3}$" },
                purchasePriceUnit: { type: ["string", "null"], maxLength: 40 },
                platform: { type: "string", enum: VALID_PLATFORMS },
                metric: { type: "string", enum: ["attention", "commercial", "competition"] },
                currentValue: { type: ["number", "null"], minimum: 0 },
                previousValue: { type: ["number", "null"], minimum: 0 },
                sampleN: { type: ["integer", "null"], minimum: 0 },
                uniqueActorN: { type: ["integer", "null"], minimum: 0 },
                coverageDays: { type: "integer", enum: [7, 30, 90] },
                sourceKind: { type: "string", enum: ["official_api", "official_export", "browser_sample", "open_source", "manual_import", "assistant"] },
                sourceRef: { type: "string" },
                geoScope: { type: "string" },
                status: { type: "string", enum: ["ok", "confirmed_zero", "unsupported", "auth_failed", "rate_limited", "collection_error", "geo_unavailable"] },
                missingReason: { type: ["string", "null"] },
                collectedAt: { type: "string" },
              },
              required: ["keyword", "platform", "metric", "currentValue", "coverageDays", "sourceKind", "geoScope", "status", "collectedAt"],
              additionalProperties: true,
            },
          },
        },
        required: ["query", "market", "language", "windowDays", "rows"],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: true },
      async execute(input) {
        const candidate = inputObject(input);
        if (!Array.isArray(candidate.rows) || candidate.rows.length === 0) throw new Error("rows 不能为空");
        const response = await fetch("/api/radar", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            action: "import_observations",
            runId: candidate.runId ?? pendingRunId ?? (data?.run?.is_demo ? null : data?.run?.id),
            query: candidate.query ?? query,
            market: candidate.market ?? market,
            language: candidate.language ?? language,
            windowDays: candidate.windowDays ?? Number(windowDays),
            scanMode: candidate.scanMode ?? scanMode,
            resultLimit: candidate.resultLimit ?? Number(resultLimit),
            rows: candidate.rows,
            origin: "assistant",
          }),
        });
        const result = await response.json() as { runId?: string; importedRows?: number; totalRows?: number; scores?: number; error?: string };
        if (!response.ok) throw new Error(result.error ?? "证据写入失败");
        setPendingRunId(null);
        setImportOpen(false);
        setScanMessage(`已增量写入 ${result.importedRows ?? candidate.rows.length} 行真实证据`);
        await loadDashboard();
        return result;
      },
    });

    register({
      name: "set_radar_keyword_status",
      title: "管理关键词状态",
      description: "把一个关键词簇设为候选、观察或排除；观察状态只记录建议复查日期，不会自动发送通知。",
      inputSchema: {
        type: "object",
        properties: {
          clusterId: { type: "string", minLength: 1 },
          status: { type: "string", enum: ["candidate", "watching", "excluded"] },
          cadenceDays: { type: "integer", minimum: 1, maximum: 365 },
        },
        required: ["clusterId", "status"],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      async execute(input) {
        const candidate = inputObject(input);
        const response = await fetch("/api/radar", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            action: "set_cluster_status",
            clusterId: candidate.clusterId,
            status: candidate.status,
            cadenceDays: candidate.cadenceDays ?? 7,
          }),
        });
        const result = await response.json() as { clusterId?: string; status?: string; error?: string };
        if (!response.ok) throw new Error(result.error ?? "状态保存失败");
        setSelected(null);
        setScanMessage("关键词状态已更新");
        await loadDashboard();
        return result;
      },
    });

    return () => lifecycle.abort();
  }, [data, language, loadDashboard, market, pendingRunId, query, resultLimit, scanMode, windowDays]);

  const selectedCredential = managedCredentials.find((credential) => credential.id === selectedCredentialId) ?? null;

  const viewTitle = {
    intelligence: ["外贸情报站", "监控采购触发、市场信号和验证闭环"],
    dashboard: ["产品机会雷达", "从注意力、B2B、贸易与竞争信号发现候选机会"],
    research: ["历史产品调研", "旧调研记录只读保留，不再从这里创建验证项目"],
    personas: ["全球买家画像", "独立维护画像分类、采购场景、产品矩阵与真实买家"],
    opportunities: ["验证项目与轮次", "用真实客户、供应、利润与履约结果决定继续或 Pass"],
    history: ["全局任务中心", "汇总各模块执行状态；详细结果回到所属模块处理"],
    watchlist: ["观察列表", "只跟踪你真正关心的产品词"],
    sources: ["数据来源", "检查覆盖率、新鲜度和采集异常"],
  }[activeView];

  const sidebar = (
    <aside className="radar-sidebar border-b px-5 py-5 text-white lg:border-b-0 lg:border-r lg:px-4 lg:py-6">
      <div className="flex items-center justify-between lg:block">
        <div className="flex items-center gap-3 px-1">
          <span className="radar-mark grid size-10 place-items-center rounded-xl">
            <Radar className="size-5" aria-hidden="true" />
          </span>
          <div>
            <p className="text-base font-semibold tracking-tight">LightLink Intelligence</p>
            <p className="text-xs text-cyan-100/65">外贸情报站</p>
          </div>
        </div>

        <nav className="mt-0 hidden space-y-1 lg:mt-9 lg:block" aria-label="主要导航">
          <button className={`radar-nav ${activeView === "intelligence" ? "radar-nav-active" : ""}`} type="button" onClick={() => navigateToView("intelligence")}>
            <LayoutDashboard aria-hidden="true" /> 情报总览
          </button>
          <button className={`radar-nav ${activeView === "dashboard" ? "radar-nav-active" : ""}`} type="button" onClick={() => navigateToView("dashboard")}>
            <Radar aria-hidden="true" /> 产品机会雷达
          </button>
          <button className={`radar-nav ${activeView === "personas" ? "radar-nav-active" : ""}`} type="button" onClick={() => navigateToView("personas")}>
            <Target aria-hidden="true" /> 全球买家画像
            <span className="ml-auto rounded-full bg-white/10 px-2 py-0.5 text-xs">{globalBuyerLibrary?.stats.personaCategoryCount ?? 0}</span>
          </button>
          <button className={`radar-nav ${activeView === "opportunities" ? "radar-nav-active" : ""}`} type="button" onClick={() => navigateToView("opportunities")}>
            <TrendingUp aria-hidden="true" /> 验证项目与轮次
          </button>
          <button className={`radar-nav ${activeView === "history" ? "radar-nav-active" : ""}`} type="button" onClick={() => navigateToView("history")}>
            <History aria-hidden="true" /> 全局任务中心
            <span className={`ml-auto rounded-full px-2 py-0.5 text-xs ${activeTaskCount ? "bg-cyan-300 text-cyan-950" : "bg-white/10"}`}>{allTaskItems.length}</span>
          </button>
          <button className={`radar-nav ${activeView === "sources" ? "radar-nav-active" : ""}`} type="button" onClick={() => navigateToView("sources")}>
            <Database aria-hidden="true" /> 数据来源
          </button>
        </nav>
      </div>

      <button type="button" onClick={() => activeJob ? navigateToView(activeJobView) : setAssistantOpen(true)} className="mt-6 hidden w-full rounded-xl border border-white/10 bg-white/[0.045] p-3 text-left transition hover:bg-white/[0.08] lg:block">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Bot className="size-4 text-cyan-300" aria-hidden="true" /> {activeJob ? `${activeTaskCount} 个通道执行中` : codexChannelState === "ready" ? "7 条 Codex 通道已连接" : "Codex 自动通道待启动"}
        </div>
        <p className="mt-2 text-xs leading-5 text-cyan-50/60">
          {activeJob ? `${activeChannelSummary} · ${activeJob.query ?? activeJobHistory?.query ?? "雷达任务"}` : "关键词、项目、单产品、图片、画像、贸易数据和商机验证可分通道并行处理。"}
        </p>
      </button>

      <div className="mt-auto hidden pt-8 lg:block">
        <p className="px-3 pt-3 text-[11px] text-cyan-50/35">本地优先 · 可在线迁移</p>
      </div>
    </aside>
  );

  return (
    <main className="min-h-screen bg-background text-foreground">
      {!researchDetailProjectId && (
      <div className="mx-auto grid min-h-screen max-w-[1600px] lg:grid-cols-[232px_minmax(0,1fr)]">
        {sidebar}

        <section className="min-w-0">
          <header className="flex min-h-16 items-center justify-between border-b border-border/80 bg-card/80 px-4 backdrop-blur md:px-7">
            <div>
              <h1 className="text-lg font-semibold tracking-tight">{viewTitle[0]}</h1>
              <p className="hidden text-xs text-muted-foreground sm:block">{viewTitle[1]}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className={activeJob ? "gap-2 border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100" : "gap-2 border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"}
                onClick={() => navigateToView(activeJobView)}
              >
                <span className={`size-2 rounded-full ${activeJob ? "animate-pulse bg-amber-500" : "bg-emerald-500"}`} />
                {activeJob ? `${activeTaskCount} 个通道执行中 · ${activeJobProgress}%` : "当前无执行任务"}
              </Button>
              <Badge variant="outline" className="hidden gap-1.5 border-emerald-200 bg-emerald-50 text-emerald-700 xl:inline-flex">
                <span className="size-1.5 rounded-full bg-emerald-500" /> {activeSourceCount} / {liveSources.length || VALID_PLATFORMS.length} 个来源已检查
              </Badge>
              <Button variant="outline" size="sm" className="hidden sm:inline-flex" onClick={() => setImportOpen(true)}>
                <FileUp /> 导入数据
              </Button>
            </div>
          </header>

          <nav className="grid grid-cols-6 border-b bg-card lg:hidden" aria-label="移动端导航">
            {([
              ["intelligence", "情报"],
              ["dashboard", "雷达"],
              ["personas", "画像"],
              ["opportunities", "验证"],
              ["history", `任务中心 ${allTaskItems.length}`],
              ["sources", "来源"],
            ] as const).map(([view, label]) => (
              <button
                key={view}
                type="button"
                className={`px-2 py-3 text-xs font-medium ${activeView === view ? "border-b-2 border-cyan-700 text-cyan-800" : "text-muted-foreground"}`}
                onClick={() => navigateToView(view)}
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="space-y-5 p-4 md:p-7">
            {activeJob && activeView !== activeJobView && (
              <button
                type="button"
                className="flex w-full flex-wrap items-center gap-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-left transition hover:bg-amber-100/80"
                onClick={() => navigateToView(activeJobView)}
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-amber-100 text-amber-700">
                  <Activity className="size-5 animate-pulse" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-amber-950">
                    {activeJob.query ?? activeJobHistory?.query ?? "雷达任务"} · {activeJob.phase ?? "正在处理"}
                  </span>
                  <span className="mt-1 block text-xs text-amber-800/75">{activeJob.channelTitle?.replace("LightLink Radar ", "") ?? "AI任务"} · 已运行 {elapsedTime(activeJob.startedAt)}{activeTaskCount > 1 ? ` · 另有 ${activeTaskCount - 1} 个通道并行` : ""}</span>
                </span>
                <span className="min-w-32">
                  <span className="mb-1 block text-right text-xs font-medium tabular-nums text-amber-800">{activeJobProgress}%</span>
                  <Progress value={activeJobProgress} className="h-1.5 bg-amber-100 [&_[data-slot=progress-indicator]]:bg-amber-500" />
                </span>
                <ChevronRight className="size-4 text-amber-700" aria-hidden="true" />
              </button>
            )}

            {activeView === "intelligence" && <IntelligenceStation
              onOpenRadar={() => navigateToView("dashboard")}
              onOpenPrograms={() => navigateToView("opportunities")}
              onOpenSources={() => navigateToView("sources")}
            />}

            {activeView === "dashboard" && (
              <>
            <Card className="gap-0 border-cyan-200 bg-cyan-50/70 py-0 shadow-none">
              <CardContent className="grid gap-3 p-4 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-center">
                <div className="flex items-start gap-3">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-cyan-800 text-xs font-semibold text-white">1</span>
                  <div><p className="text-sm font-medium">输入产品词或类目</p><p className="mt-0.5 text-xs text-muted-foreground">例如“电子产品”或具体商品词</p></div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-cyan-800 text-xs font-semibold text-white">2</span>
                  <div><p className="text-sm font-medium">选择获取数据方式</p><p className="mt-0.5 text-xs text-muted-foreground">免费导入、Codex Skill 或 API 直连</p></div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-cyan-800 text-xs font-semibold text-white">3</span>
                  <div><p className="text-sm font-medium">查看机会与来源</p><p className="mt-0.5 text-xs text-muted-foreground">结果自动进入榜单和历史</p></div>
                </div>
                <Button variant="ghost" size="sm" className="justify-self-start text-cyan-900" onClick={() => navigateToView("sources")}>查看数据来源 <ChevronRight /></Button>
              </CardContent>
            </Card>

            <Card className="radar-command overflow-hidden border-0 py-0 shadow-none">
              <CardContent className="p-4 md:p-5">
                <Tabs value={scanMode} onValueChange={(value) => setScanMode(value as "seed" | "discover")}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <TabsList className="h-11 gap-1 rounded-xl border border-white/20 bg-slate-950/25 p-1 shadow-inner">
                      <TabsTrigger
                        value="seed"
                        className="h-9 rounded-lg px-4 text-cyan-50/80 hover:bg-white/10 hover:text-white focus-visible:ring-cyan-300 focus-visible:ring-offset-2 focus-visible:ring-offset-cyan-950 data-[state=active]:border-cyan-100 data-[state=active]:bg-cyan-50 data-[state=active]:font-semibold data-[state=active]:text-cyan-950 data-[state=active]:shadow-md data-[state=active]:ring-1 data-[state=active]:ring-white/90"
                      >
                        <Search /> 关键词扫描
                      </TabsTrigger>
                      <TabsTrigger
                        value="discover"
                        className="h-9 rounded-lg px-4 text-cyan-50/80 hover:bg-white/10 hover:text-white focus-visible:ring-cyan-300 focus-visible:ring-offset-2 focus-visible:ring-offset-cyan-950 data-[state=active]:border-cyan-100 data-[state=active]:bg-cyan-50 data-[state=active]:font-semibold data-[state=active]:text-cyan-950 data-[state=active]:shadow-md data-[state=active]:ring-1 data-[state=active]:ring-white/90"
                      >
                        <Sparkles /> 热点发现
                      </TabsTrigger>
                    </TabsList>
                    <p className="text-xs text-cyan-50/65">{scanMessage}</p>
                  </div>

                  <TabsContent value="seed" className="mt-4">
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-[minmax(240px,1fr)_150px_130px_110px_auto_auto]">
                      <div className="relative sm:col-span-2 xl:col-span-1">
                        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                        <Input
                          value={query}
                          onChange={(event) => setQuery(event.target.value)}
                          onKeyDown={(event) => event.key === "Enter" && setAssistantOpen(true)}
                          className="h-11 cursor-text border-white/25 bg-white pl-9 text-slate-950 caret-cyan-700 shadow-none placeholder:text-slate-400 hover:border-cyan-300 focus-visible:border-cyan-300 focus-visible:ring-cyan-300/40"
                          placeholder="输入多语种关键词；多个词用逗号分隔"
                          aria-label="关键词"
                          autoComplete="off"
                        />
                      </div>
                      <MarketSelect value={market} onValueChange={changeMarket} />
                      <LanguageSelect value={language} onValueChange={setLanguage} />
                      <Select value={windowDays} onValueChange={setWindowDays}>
                        <SelectTrigger aria-label="分析周期" className="h-11 w-full border-white/25 bg-white text-slate-950">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="7">近 7 天</SelectItem>
                          <SelectItem value="30">近 30 天</SelectItem>
                          <SelectItem value="90">近 90 天</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button disabled={busy} className="h-11 bg-cyan-300 px-5 text-slate-950 hover:bg-cyan-200" onClick={() => setAssistantOpen(true)}>
                        <Sparkles /> AI 整理并入库
                      </Button>
                      <Button disabled={busy} variant="outline" className="h-11 border-white/50 bg-white/10 px-5 text-white hover:bg-white/20 hover:text-white" onClick={() => { setPendingRunId(null); setImportOpen(true); }}>
                        <FileUp /> 免费导入
                      </Button>
                    </div>
                    <p className="mt-2 text-xs text-cyan-50/60">支持全球与 50+ 个主要国家和地区、29 种关键词语言；可混合输入并用逗号分隔。</p>
                  </TabsContent>

                  <TabsContent value="discover" className="mt-4">
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-[minmax(240px,1fr)_150px_130px_110px_auto_auto]">
                      <div className="relative sm:col-span-2 xl:col-span-1">
                        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                        <Input
                          value={query}
                          onChange={(event) => setQuery(event.target.value)}
                          onKeyDown={(event) => event.key === "Enter" && setAssistantOpen(true)}
                          className="h-11 cursor-text border-white/25 bg-white pl-9 text-slate-950 caret-cyan-700 shadow-none placeholder:text-slate-400 hover:border-cyan-300 focus-visible:border-cyan-300 focus-visible:ring-cyan-300/40"
                          placeholder="输入类目，例如：户外照明"
                          aria-label="产品类目"
                          autoComplete="off"
                        />
                      </div>
                      <MarketSelect value={market} onValueChange={changeMarket} />
                      <LanguageSelect value={language} onValueChange={setLanguage} />
                      <Select value={windowDays} onValueChange={setWindowDays}>
                        <SelectTrigger aria-label="分析周期" className="h-11 w-full border-white/25 bg-white text-slate-950 focus-visible:border-cyan-300 focus-visible:ring-cyan-300/40">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="7">近 7 天</SelectItem>
                          <SelectItem value="30">近 30 天</SelectItem>
                          <SelectItem value="90">近 90 天</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button disabled={busy} className="h-11 bg-cyan-300 px-5 text-slate-950 hover:bg-cyan-200" onClick={() => setAssistantOpen(true)}>
                        <Sparkles /> AI 发现并入库
                      </Button>
                      <Button disabled={busy} variant="outline" className="h-11 border-white/50 bg-white/10 px-5 text-white hover:bg-white/20 hover:text-white" onClick={() => { setPendingRunId(null); setImportOpen(true); }}>
                        <FileUp /> 免费导入
                      </Button>
                    </div>
                    <p className="mt-2 text-xs text-cyan-50/60">AI 可整理关键词和公开证据；免费方式可直接导入平台导出。系统不会自动编造热词数值。</p>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>

            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              <MiniStat label="关键词簇" value={String(rows.length)} note="同义词和语言变体已合并" icon={ListFilter} accent="bg-cyan-50 text-cyan-700" />
              <MiniStat label="快速增长" value={String(rows.filter((row) => row.momentum !== null && row.momentum >= 75).length)} note="基于前后期真实变化" icon={TrendingUp} accent="bg-emerald-50 text-emerald-700" />
              <MiniStat label="高机会" value={String(rows.filter((row) => row.opportunity !== null && row.opportunity >= 70 && row.confidence >= 60).length)} note="需同时满足置信度门槛" icon={Target} accent="bg-amber-50 text-amber-700" />
              <MiniStat label="正在观察" value={String(data?.watchlist.length ?? savedIds.length)} note="默认建议 7 天后复查" icon={CalendarClock} accent="bg-violet-50 text-violet-700" />
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,.75fr)]">
              <Card className="gap-4 border-slate-200/80 py-5 shadow-none">
                <CardHeader className="px-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <CardTitle className="text-base">产品概念趋势</CardTitle>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {data?.run ? `${data.run.query} · ${marketNameForCode(data.run.market)}（${data.run.market}） · ${languageNameForCode(data.run.language)}（${data.run.language.toUpperCase()}） · ${data.run.window_days} 天窗口` : "正在读取本地快照"}
                      </p>
                    </div>
                    <Badge variant="secondary" className="gap-1 bg-emerald-50 text-emerald-700">
                      {data?.run?.is_demo ? "演示快照" : chartData.length > 1 ? `${chartData.length} 个真实快照` : "趋势待积累"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="h-[245px] px-2 pr-5">
                  {mounted && chartData.length > 1 ? <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} initialDimension={{ width: 800, height: 245 }}>
                    <AreaChart data={chartData} margin={{ top: 10, right: 4, bottom: 0, left: -20 }}>
                      <defs>
                        <linearGradient id="heatFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#0e7490" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#0e7490" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dbe4e7" />
                      <XAxis dataKey="week" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#64748b" }} />
                      <YAxis domain={[0, 100]} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#64748b" }} />
                      <ChartTooltip contentStyle={{ borderRadius: 10, border: "1px solid #dbe4e7", fontSize: 12 }} />
                      <Area type="monotone" dataKey="heat" name="热度" stroke="#0e7490" strokeWidth={2.5} fill="url(#heatFill)" />
                      <Area type="monotone" dataKey="opportunity" name="机会" stroke="#d97706" strokeWidth={2} fill="transparent" />
                    </AreaChart>
                  </ResponsiveContainer> : (
                    <div className="grid h-full place-items-center px-6 text-center">
                      <div>
                        <History className="mx-auto size-8 text-slate-300" />
                        <p className="mt-3 text-sm font-medium">至少需要 2 次真实扫描才能显示趋势</p>
                        <p className="mt-1 text-xs text-muted-foreground">系统不会用演示数值补齐历史曲线。</p>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="gap-4 border-slate-200/80 py-5 shadow-none">
                <CardHeader className="px-5">
                  <CardTitle className="text-base">数据来源状态</CardTitle>
                  <p className="text-xs text-muted-foreground">失败不会被当作低热度</p>
                </CardHeader>
                <CardContent className="space-y-4 px-5">
                  {liveSources.map((source) => (
                    <div key={source.name}>
                      <div className="mb-1.5 flex items-center justify-between gap-3 text-sm">
                        <div className="flex items-center gap-2">
                          <span className={`size-2 rounded-full ${source.state === "可用" ? "bg-emerald-500" : source.state === "部分可用" ? "bg-amber-400" : source.state === "无有效值" ? "bg-rose-400" : "bg-slate-300"}`} />
                          <span className="font-medium">{source.name}</span>
                          <span className="text-xs text-muted-foreground">{source.state}</span>
                        </div>
                        <span className="text-xs text-muted-foreground">{source.freshness}</span>
                      </div>
                      <Progress value={source.coverage} className="h-1.5 bg-slate-100 [&_[data-slot=progress-indicator]]:bg-cyan-700" />
                    </div>
                  ))}
                  <Button variant="outline" className="mt-1 w-full justify-between" onClick={() => navigateToView("sources")}>
                    管理来源 <ChevronRight />
                  </Button>
                </CardContent>
              </Card>
            </div>

            <Card className="gap-0 overflow-hidden border-slate-200/80 py-0 shadow-none">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 md:px-5">
                <div>
                  <h2 className="font-semibold">关键词机会榜</h2>
                  <p className="text-xs text-muted-foreground">相对指数，不代表平台真实搜索量</p>
                </div>
                <div className="flex items-center gap-2">
                  <Select value={sortBy} onValueChange={setSortBy}>
                    <SelectTrigger size="sm" className="w-[142px]">
                      <ListFilter /> <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="opportunity">机会最高</SelectItem>
                      <SelectItem value="momentum">增长最快</SelectItem>
                      <SelectItem value="intent">采购意图</SelectItem>
                      <SelectItem value="heat">当前最热</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger size="sm" className="w-[112px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部状态</SelectItem>
                      <SelectItem value="候选">候选</SelectItem>
                      <SelectItem value="观察">观察</SelectItem>
                      <SelectItem value="排除">排除</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button variant="outline" size="sm" asChild>
                    <a href="/api/radar?view=export&format=csv" download><Download /> 导出数据</a>
                  </Button>
                </div>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50/70 hover:bg-slate-50/70">
                    <TableHead className="w-[32%] pl-5">关键词簇</TableHead>
                    <TableHead>热度</TableHead>
                    <TableHead>增长动量</TableHead>
                    <TableHead>采购意图</TableHead>
                    <TableHead>竞争度</TableHead>
                    <TableHead>机会</TableHead>
                    <TableHead>置信度</TableHead>
                    <TableHead className="pr-5 text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="h-44 text-center">
                        <p className="font-medium">当前任务还没有可评分的证据</p>
                        <p className="mt-1 text-sm text-muted-foreground">导入真实平台观测后，机会榜会自动出现。</p>
                        <Button className="mt-4" size="sm" variant="outline" onClick={() => setImportOpen(true)}>
                          <FileUp /> 导入证据
                        </Button>
                      </TableCell>
                    </TableRow>
                  )}
                  {rows.map((row) => {
                    const isSaved = savedIds.includes(row.id);
                    return (
                      <TableRow key={row.id} className="cursor-pointer" onClick={() => setSelected(row)}>
                        <TableCell className="pl-5">
                          <div className="flex items-center gap-3">
                            <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${row.direction === "up" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                              {row.direction === "up" ? <ArrowUpRight className="size-4" /> : row.direction === "down" ? <ArrowDownRight className="size-4" /> : <Activity className="size-4" />}
                            </span>
                            <div className="min-w-0">
                              <p className="truncate font-medium">{row.keyword}</p>
                              <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                                <span>{row.group}</span>
                                <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">{row.lifecycle}</Badge>
                              </div>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell><ScoreCell value={row.heat} /></TableCell>
                        <TableCell><ScoreCell value={row.momentum} /></TableCell>
                        <TableCell><ScoreCell value={row.intent} /></TableCell>
                        <TableCell><ScoreCell value={row.competition} inverse /></TableCell>
                        <TableCell>
                          {row.opportunity === null ? (
                            <Badge variant="outline" className="font-normal text-slate-500">待补证据</Badge>
                          ) : (
                            <span className="inline-flex min-w-9 justify-center rounded-md bg-cyan-950 px-2 py-1 font-semibold text-white tabular-nums">{row.opportunity}</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Progress value={row.confidence} className="h-1.5 w-12 bg-slate-100 [&_[data-slot=progress-indicator]]:bg-cyan-700" />
                            <span className="text-xs tabular-nums text-muted-foreground">{row.confidence}%</span>
                          </div>
                        </TableCell>
                        <TableCell className="pr-5 text-right">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={isSaved ? "移出观察" : "加入观察"}
                            onClick={(event) => {
                              event.stopPropagation();
                              toggleSaved(row.id);
                            }}
                          >
                            {isSaved ? <BookmarkCheck className="text-cyan-700" /> : <Bookmark />}
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </Card>
              </>
            )}

            {activeView === "opportunities" && <OpportunityCenter
              seed={opportunitySeed}
              onSeedConsumed={consumeOpportunitySeed}
              onOpenSources={() => navigateToView("sources")}
              onOpenGlobalPersonas={() => { setGlobalBuyerLibraryTab("personas"); setGlobalBuyerLibraryOpen(true); }}
            />}

            {activeView === "research" && (
              <div className="space-y-5">
                <Card className="overflow-hidden border-cyan-200 bg-gradient-to-br from-cyan-950 via-cyan-900 to-teal-800 py-0 text-white shadow-none">
                  <CardContent className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(360px,.9fr)] lg:items-center lg:p-6">
                    <div>
                      <div className="flex items-center gap-2 text-cyan-200">
                        <FlaskConical className="size-4" aria-hidden="true" />
                        <span className="text-xs font-semibold uppercase tracking-[0.16em]">Research Workspace</span>
                      </div>
                      <h2 className="mt-3 text-2xl font-semibold tracking-tight">一个产品，一个持续更新的调研档案</h2>
                      <p className="mt-2 max-w-2xl text-sm leading-6 text-cyan-50/75">
                        保存市场范围、证据、评分、结论和每次复查版本。Codex / ChatGPT 负责采集与整理，原始来源和未知项仍然可追溯。
                      </p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button className="bg-cyan-300 text-cyan-950 hover:bg-cyan-200" onClick={() => setResearchCreateOpen(true)}>
                          <Plus /> 新建调研项目
                        </Button>
                        <Button variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white" onClick={() => void loadResearch()}>
                          刷新项目库
                        </Button>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        ["长期项目", researchProjects.filter((item) => item.status !== "archived").length, "持续保存，不是一次性问答"],
                        ["研究版本", researchProjects.reduce((sum, item) => sum + Number(item.run_count || 0), 0), "每次复查形成新版本"],
                        ["有效证据", researchProjects.reduce((sum, item) => sum + Number(item.evidence_count || 0), 0), "来源链接与市场可追溯"],
                        ["待复核", researchProjects.filter((item) => item.status === "needs_review").length, "需要人工判断的结论"],
                      ].map(([label, value, note]) => (
                        <div key={String(label)} className="rounded-xl border border-white/10 bg-white/[0.07] p-3">
                          <p className="text-xs text-cyan-100/65">{label}</p>
                          <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
                          <p className="mt-1 text-[11px] leading-4 text-cyan-50/55">{note}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                <Card className="gap-4 border-cyan-200/80 bg-cyan-50/30 py-5 shadow-none">
                  <CardHeader className="px-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2"><Database className="size-4 text-cyan-800" /><CardTitle className="text-base">全球外贸批发客户画像</CardTitle></div>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">以“地区 → 画像分类 → 采购场景 → 产品赛道 → 产品家族”为共享主数据；真实公司是画像实例，不再由旧候选产品反向定义分类。</p>
                      </div>
                      <div className="flex gap-2">
                        <Button variant="outline" size="sm" onClick={openNewGlobalBuyer}><Plus /> 新增真实买家</Button>
                        <Button size="sm" onClick={() => navigateToView("personas")}><Eye /> 进入独立画像库</Button>
                      </div>
                    </div>
                    {globalBuyerMessage && <p className="mt-2 rounded-lg bg-white px-3 py-2 text-xs text-cyan-900">{globalBuyerMessage}</p>}
                  </CardHeader>
                  <CardContent className="space-y-4 px-5">
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-6">
                      {[
                        ["外贸地区", globalBuyerLibrary?.stats.regionCount ?? 0, "UN M49 业务分区"],
                        ["画像分类", globalBuyerLibrary?.stats.personaCategoryCount ?? 0, "按价值链和业态"],
                        ["产品赛道", globalBuyerLibrary?.stats.trackCount ?? 0, "稳定分类主干"],
                        ["产品家族", globalBuyerLibrary?.stats.masterFamilyCount ?? 0, "不等于单一SKU"],
                        ["画像矩阵", globalBuyerLibrary?.stats.personaMatrixCount ?? 0, "地区与赛道关系"],
                        ["真实买家公司", globalBuyerLibrary?.stats.profileCount ?? 0, "公司与公开来源"],
                      ].map(([label, value, note]) => <div key={String(label)} className="rounded-xl border bg-white p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-xl font-semibold tabular-nums">{value}</p><p className="mt-1 text-[11px] text-muted-foreground">{note}</p></div>)}
                    </div>
                    <div className="grid gap-2 lg:grid-cols-3">
                      {globalPersonaCategories.slice(0, 6).map((personaItem) => <button key={personaItem.code} type="button" className="rounded-xl border bg-white p-3 text-left transition hover:border-cyan-300 hover:bg-cyan-50/30" onClick={() => { setGlobalTaxonomySearch(personaItem.name); navigateToView("personas"); }}><div className="flex items-start justify-between gap-2"><div><p className="font-medium">{personaItem.name}</p><p className="mt-1 text-xs text-muted-foreground">{personaItem.group_name} · {personaItem.value_chain_role}</p></div><Badge variant="outline">{personaItem.code}</Badge></div><p className="mt-3 line-clamp-2 text-xs leading-5 text-muted-foreground">{personaItem.description}</p></button>)}
                    </div>
                  </CardContent>
                </Card>

                <Card className="gap-4 border-slate-200/80 py-5 shadow-none">
                  <CardHeader className="px-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <CardTitle className="text-base">标准研究路径</CardTitle>
                        <p className="mt-1 text-xs text-muted-foreground">基于外贸启动手册拆成八个可复用章节；缺少证据时保留未知，不补造数值。</p>
                      </div>
                      <Badge variant="outline">五维 100 分决策卡</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="grid gap-2 px-5 sm:grid-cols-2 xl:grid-cols-4">
                    {RESEARCH_STAGE_META.map(([key, label, note], index) => (
                      <div key={key} className="rounded-xl border bg-slate-50/70 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="grid size-6 place-items-center rounded-full bg-cyan-100 text-xs font-semibold text-cyan-800">{index + 1}</span>
                          <span className="text-[10px] text-muted-foreground">{key}</span>
                        </div>
                        <p className="mt-3 text-sm font-medium">{label}</p>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">{note}</p>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card className="gap-0 border-slate-200/80 py-0 shadow-none">
                  <CardHeader className="border-b px-5 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <CardTitle className="text-base">调研项目库</CardTitle>
                        <p className="mt-1 text-xs text-muted-foreground">按产品持续积累；新一轮调研不会覆盖旧版本。</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Input className="w-56" value={researchSearch} onChange={(event) => setResearchSearch(event.target.value)} placeholder="搜索产品、类目或市场" />
                        <Select value={researchStatus} onValueChange={setResearchStatus}>
                          <SelectTrigger className="w-36" aria-label="调研项目状态"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="active">进行中与已完成</SelectItem>
                            <SelectItem value="all">全部项目</SelectItem>
                            <SelectItem value="planning">待开始</SelectItem>
                            <SelectItem value="queued">等待 Codex</SelectItem>
                            <SelectItem value="needs_review">待复核</SelectItem>
                            <SelectItem value="completed">已完成</SelectItem>
                            <SelectItem value="archived">已归档</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    {researchMessage && <p className="mt-3 rounded-lg bg-cyan-50 px-3 py-2 text-xs text-cyan-900">{researchMessage}</p>}
                  </CardHeader>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="pl-5">产品项目</TableHead>
                        <TableHead>市场 / 语言</TableHead>
                        <TableHead>模板</TableHead>
                        <TableHead>版本 / 证据</TableHead>
                        <TableHead>进度</TableHead>
                        <TableHead>建议</TableHead>
                        <TableHead className="pr-5 text-right">操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredResearchProjects.map((project) => {
                        const projectJob = activeJobs.find((job) => ["research", "candidate_assist", "candidate_images"].includes(String(job.taskType)) && job.projectId === project.id);
                        const isCurrentResearch = Boolean(projectJob);
                        const displayProgress = projectJob ? Math.min(99, Math.max(5, projectJob.progress ?? 20)) : Number(project.progress || 0);
                        const templateName = researchData?.templates.find((item) => item.id === project.template_id)?.name ?? project.template_id;
                        return (
                          <TableRow key={project.id} className="cursor-pointer align-top" onClick={() => void openResearchProject(project)}>
                            <TableCell className="pl-5">
                              <div className="min-w-52">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-medium">{project.product_name}</span>
                                  <Badge variant="outline" className={researchBadgeClass(isCurrentResearch ? "researching" : project.status)}>
                                    {isCurrentResearch ? "Codex 调研中" : RESEARCH_STATUS_LABELS[project.status] ?? project.status}
                                  </Badge>
                                </div>
                                <p className="mt-1 text-xs text-muted-foreground">{project.product_category || "未分类"} · 更新于 {relativeTime(project.updated_at)}</p>
                              </div>
                            </TableCell>
                            <TableCell>
                              <div className="flex max-w-56 flex-wrap gap-1">
                                {project.target_markets.map((item) => <Badge key={item} variant="outline">{marketNameForCode(item)}（{item}）</Badge>)}
                                {project.languages.map((item) => <Badge key={item} variant="secondary">{languageNameForCode(item)}（{item.toUpperCase()}）</Badge>)}
                              </div>
                            </TableCell>
                            <TableCell className="max-w-48 text-sm text-slate-600">{templateName}</TableCell>
                            <TableCell>
                              <p className="font-medium tabular-nums">{project.run_count || 0} 个版本</p>
                              <p className="mt-1 text-xs text-muted-foreground">{project.evidence_count || 0} 条证据 · {project.candidate_count || 0} 个候选产品</p>
                            </TableCell>
                            <TableCell>
                              <div className="w-28">
                                <div className="mb-1 flex justify-between text-xs"><span>{RESEARCH_SECTION_LABELS[project.current_stage] ?? "准备"}</span><span>{displayProgress}%</span></div>
                                <Progress value={displayProgress} className="h-1.5" />
                              </div>
                            </TableCell>
                            <TableCell><Badge variant="outline">{RESEARCH_RECOMMENDATION_LABELS[project.recommendation] ?? project.recommendation}</Badge></TableCell>
                            <TableCell className="pr-5 text-right">
                              <div className="flex justify-end gap-2">
                                <Button variant="outline" size="sm" asChild>
                                  <a
                                    href={researchProjectPath(project.id)}
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                                      event.preventDefault();
                                      void openResearchProject(project);
                                    }}
                                  >
                                    <Eye /> 查看
                                  </a>
                                </Button>
                                {project.status !== "archived" && (
                                  <Button size="sm" disabled={researchBusy || Boolean(researchChannelJob)} onClick={(event) => { event.stopPropagation(); openResearchRunDialog(project); }}>
                                    {project.run_count ? <Plus /> : <Bot />} {project.run_count ? "补充 / 复查" : "开始调研"}
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-rose-700 hover:bg-rose-50 hover:text-rose-800"
                                  aria-label={`删除${project.product_name}`}
                                  onClick={(event) => { event.stopPropagation(); setResearchDeleteMessage(""); setResearchDeleteTarget(project); }}
                                >
                                  <Trash2 /> 删除
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                      {!filteredResearchProjects.length && (
                        <TableRow>
                          <TableCell colSpan={7} className="h-48 text-center">
                            <FlaskConical className="mx-auto size-8 text-slate-300" />
                            <p className="mt-3 text-sm font-medium">{researchLoading ? "正在读取调研项目…" : "还没有符合条件的调研项目"}</p>
                            <p className="mt-1 text-xs text-muted-foreground">建立第一个产品档案后，可反复交给 Codex / ChatGPT 更新。</p>
                            {!researchLoading && <Button className="mt-4" size="sm" onClick={() => setResearchCreateOpen(true)}><Plus /> 新建项目</Button>}
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </Card>
              </div>
            )}

            {activeView === "personas" && (
              <div className="space-y-5">
                <Card className="overflow-hidden border-cyan-200 bg-gradient-to-br from-cyan-950 via-cyan-900 to-teal-800 py-0 text-white shadow-none">
                  <CardContent className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(380px,.9fr)] lg:items-center lg:p-6">
                    <div>
                      <div className="flex items-center gap-2 text-cyan-200"><Target className="size-4" /><span className="text-xs font-semibold uppercase tracking-[0.16em]">Buyer Intelligence Master Data</span></div>
                      <h2 className="mt-3 text-2xl font-semibold tracking-tight">全球外贸批发客户画像</h2>
                      <p className="mt-2 max-w-2xl text-sm leading-6 text-cyan-50/75">独立维护“地区 → 画像分类 → 采购场景 → 产品赛道 → 产品家族”。调研项目只复用，不反向覆盖主数据；AI建议必须人工审核后才生效。</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button className="bg-cyan-300 text-cyan-950 hover:bg-cyan-200" onClick={() => openPersonaCategoryEditor()}><Plus /> 新增画像</Button>
                        <Button variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white" disabled={Boolean(taxonomyAssistChannelJob)} onClick={() => openPersonaAiAssistant()}><Bot /> {taxonomyAssistChannelJob ? "AI画像通道处理中" : "AI补充画像"}</Button>
                        <Button variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white" onClick={() => { setGlobalBuyerLibraryTab("products"); setGlobalBuyerLibraryOpen(true); }}><Database /> 产品家族与关系矩阵</Button>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        ["在用画像", globalBuyerLibrary?.stats.personaCategoryCount ?? 0, "供新项目复用"],
                        ["AI待审核", globalBuyerLibrary?.stats.pendingPersonaProposalCount ?? 0, "人工确认后生效"],
                        ["已停用", globalBuyerLibrary?.stats.retiredPersonaCategoryCount ?? 0, "可恢复、历史保留"],
                        ["变更记录", globalPersonaChanges.length, "新增、更新与删除可追溯"],
                      ].map(([label, value, note]) => <div key={String(label)} className="rounded-xl border border-white/10 bg-white/[0.07] p-3"><p className="text-xs text-cyan-100/65">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p><p className="mt-1 text-[11px] leading-4 text-cyan-50/55">{note}</p></div>)}
                    </div>
                  </CardContent>
                </Card>

                {globalBuyerMessage && <p role="status" className="rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-950">{globalBuyerMessage}</p>}

                <Card className="gap-0 py-0 shadow-none">
                  <Tabs value={personaWorkspaceTab} onValueChange={setPersonaWorkspaceTab}>
                    <CardHeader className="border-b px-5 py-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <TabsList className="h-auto">
                          <TabsTrigger value="active">在用画像 {globalPersonaCategories.length}</TabsTrigger>
                          <TabsTrigger value="proposals">AI待审核 {globalPersonaProposals.filter((item) => item.status === "pending").length}</TabsTrigger>
                          <TabsTrigger value="retired">已停用 {retiredGlobalPersonaCategories.length}</TabsTrigger>
                          <TabsTrigger value="history">变更记录</TabsTrigger>
                        </TabsList>
                        {personaWorkspaceTab !== "active" && <Input className="w-full sm:w-80" value={globalTaxonomySearch} onChange={(event) => setGlobalTaxonomySearch(event.target.value)} placeholder="搜索画像、代码或变更记录" />}
                      </div>
                      {personaWorkspaceTab === "active" && <div className="mt-4 space-y-3">
                        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-[minmax(300px,1.6fr)_minmax(180px,.8fr)_minmax(180px,.8fr)_minmax(170px,.7fr)_minmax(170px,.7fr)]">
                          <Input value={globalTaxonomySearch} onChange={(event) => setGlobalTaxonomySearch(event.target.value)} placeholder="搜索画像、客群、场景、赛道或产品家族" />
                          <Select value={personaGroupFilter} onValueChange={setPersonaGroupFilter}><SelectTrigger><SelectValue placeholder="全部分类组" /></SelectTrigger><SelectContent><SelectItem value="all">全部分类组</SelectItem>{personaGroups.map((group) => <SelectItem key={group} value={group}>{group}</SelectItem>)}</SelectContent></Select>
                          <Select value={personaCoverageFilter} onValueChange={setPersonaCoverageFilter}><SelectTrigger><SelectValue placeholder="全部覆盖状态" /></SelectTrigger><SelectContent><SelectItem value="all">全部覆盖状态</SelectItem><SelectItem value="configured">已有家族矩阵</SelectItem><SelectItem value="missing">待补家族矩阵</SelectItem><SelectItem value="validated">含已验证关系</SelectItem><SelectItem value="buyers">已有真实买家</SelectItem></SelectContent></Select>
                          <Select value={personaRoleFilter} onValueChange={setPersonaRoleFilter}><SelectTrigger><SelectValue placeholder="全部产品角色" /></SelectTrigger><SelectContent><SelectItem value="all">全部产品角色</SelectItem><SelectItem value="core">核心常采</SelectItem><SelectItem value="cross_sell">跨品类加购</SelectItem><SelectItem value="seasonal">季节采购</SelectItem><SelectItem value="test">小单测试</SelectItem></SelectContent></Select>
                          <Select value={personaSort} onValueChange={setPersonaSort}><SelectTrigger><SelectValue placeholder="排序" /></SelectTrigger><SelectContent><SelectItem value="group">分类组与名称</SelectItem><SelectItem value="coverage">家族覆盖最多</SelectItem><SelectItem value="updated">最近更新</SelectItem></SelectContent></Select>
                        </div>
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><span>找到 {filteredPersonaCategories.length} / {globalPersonaCategories.length} 个画像；点击画像即可查看完整产品矩阵。</span>{activePersonaFilterCount > 0 && <Button size="sm" variant="ghost" className="h-7" onClick={() => { setGlobalTaxonomySearch(""); setPersonaGroupFilter("all"); setPersonaCoverageFilter("all"); setPersonaRoleFilter("all"); setPersonaSort("group"); }}>重置 {activePersonaFilterCount} 个条件</Button>}</div>
                      </div>}
                    </CardHeader>

                    <TabsContent value="active" className="m-0 p-5">
                      <div className="grid gap-3 xl:grid-cols-2">
                        {filteredPersonaCategories.map((item) => {
                          const companyCount = globalBuyerProfiles.filter((buyer) => buyer.persona_code === item.code).length;
                          const matrixLinks = globalPersonaMatrix.filter((link) => link.persona_code === item.code);
                          const familyLinks = matrixLinks.filter((link) => link.product_family_code);
                          const trackCodes = [...new Set(matrixLinks.map((link) => link.track_code))];
                          return <div key={item.code} className="overflow-hidden rounded-xl border bg-white transition hover:border-cyan-300 hover:shadow-sm"><button type="button" className="block w-full p-4 text-left" onClick={() => setPersonaDetailCode(item.code)}><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{item.name}</h3><Badge variant="secondary">{item.group_name}</Badge><Badge variant="outline">{item.code}</Badge></div><p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{item.description}</p></div><span className="inline-flex items-center gap-1 text-xs font-medium text-cyan-800">查看产品矩阵 <ChevronRight className="size-3.5" /></span></div><div className="mt-3 grid grid-cols-3 gap-2"><div className="rounded-lg bg-slate-50 p-2.5"><p className="text-[11px] text-muted-foreground">产品赛道</p><p className="mt-1 font-medium tabular-nums">{trackCodes.length}</p></div><div className="rounded-lg bg-slate-50 p-2.5"><p className="text-[11px] text-muted-foreground">产品家族</p><p className="mt-1 font-medium tabular-nums">{familyLinks.length}</p></div><div className="rounded-lg bg-slate-50 p-2.5"><p className="text-[11px] text-muted-foreground">真实买家</p><p className="mt-1 font-medium tabular-nums">{companyCount}</p></div></div><div className="mt-3 flex flex-wrap gap-1">{trackCodes.slice(0, 3).map((trackCode) => <Badge key={trackCode} variant="outline" className="font-normal">{globalProductTracks.find((track) => track.code === trackCode)?.name ?? trackCode}</Badge>)}{trackCodes.length > 3 && <Badge variant="secondary">+{trackCodes.length - 3} 赛道</Badge>}</div></button><div className="flex flex-wrap items-center justify-between gap-2 border-t bg-slate-50/60 px-4 py-2.5"><span className="text-xs text-muted-foreground">v{item.version} · {relativeTime(item.updated_at)}</span><div className="flex flex-wrap gap-1"><Button size="sm" variant="ghost" onClick={() => openPersonaAiAssistant(item)}><Bot /> AI复核</Button><Button size="sm" variant="ghost" onClick={() => openPersonaCategoryEditor(item)}>更新</Button><Button size="sm" variant="ghost" className="text-rose-700 hover:bg-rose-50 hover:text-rose-800" onClick={() => setPersonaDeleteTarget(item)}><Trash2 /> 删除</Button></div></div></div>;
                        })}
                      </div>
                      {!filteredPersonaCategories.length && <div className="rounded-xl border border-dashed py-16 text-center"><Search className="mx-auto size-8 text-slate-300" /><p className="mt-3 text-sm font-medium">没有符合条件的画像</p><p className="mt-1 text-xs text-muted-foreground">减少筛选条件，或重置后从全部画像重新查找。</p><Button className="mt-4" size="sm" variant="outline" onClick={() => { setGlobalTaxonomySearch(""); setPersonaGroupFilter("all"); setPersonaCoverageFilter("all"); setPersonaRoleFilter("all"); setPersonaSort("group"); }}>重置筛选</Button></div>}
                    </TabsContent>

                    <TabsContent value="proposals" className="m-0 p-5">
                      <div className="space-y-3">
                        {globalPersonaProposals.filter((proposal) => proposal.status === "pending").map((proposal) => <div key={proposal.id} className="rounded-xl border border-amber-200 bg-amber-50/40 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{String(proposal.payload.name ?? proposal.persona_code)}</h3><Badge variant="outline">{proposal.persona_code}</Badge><Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">AI待审核</Badge></div><p className="mt-2 text-sm leading-6 text-muted-foreground">{String(proposal.payload.description ?? "")}</p><p className="mt-2 text-xs text-amber-900">建议理由：{proposal.rationale || "等待人工复核分类边界与来源"}</p></div><div className="flex gap-2"><Button size="sm" variant="outline" disabled={globalTaxonomyBusy} onClick={() => void reviewPersonaProposal(proposal, "reject")}>驳回</Button><Button size="sm" disabled={globalTaxonomyBusy} onClick={() => void reviewPersonaProposal(proposal, "apply")}><Check /> 应用建议</Button></div></div><div className="mt-3 flex flex-wrap gap-2">{proposal.source_refs.map((url, index) => <a key={url} className="text-xs text-cyan-800 underline underline-offset-2" href={url} target="_blank" rel="noreferrer">来源 {index + 1}</a>)}</div></div>)}
                        {!globalPersonaProposals.some((item) => item.status === "pending") && <div className="rounded-xl border border-dashed py-16 text-center"><Bot className="mx-auto size-8 text-slate-300" /><p className="mt-3 text-sm font-medium">暂无待审核AI建议</p><p className="mt-1 text-xs text-muted-foreground">点击“AI补充画像”后，结果会先进入这里，不会自动修改正式分类。</p></div>}
                      </div>
                    </TabsContent>

                    <TabsContent value="retired" className="m-0 p-5">
                      <div className="grid gap-3 xl:grid-cols-2">{retiredGlobalPersonaCategories.map((item) => <div key={item.code} className="rounded-xl border bg-slate-50 p-4"><div className="flex items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium text-slate-700">{item.name}</h3><Badge variant="outline">{item.code}</Badge><Badge variant="secondary">已停用</Badge></div><p className="mt-2 text-sm text-muted-foreground">{item.description}</p></div><Button size="sm" variant="outline" disabled={globalTaxonomyBusy} onClick={() => void setPersonaCategoryActive(item, true)}><Archive /> 恢复</Button></div></div>)}</div>
                      {!retiredGlobalPersonaCategories.length && <div className="rounded-xl border border-dashed py-16 text-center text-sm text-muted-foreground">没有已停用的画像分类。</div>}
                    </TabsContent>

                    <TabsContent value="history" className="m-0 p-5">
                      <div className="space-y-2">{globalPersonaChanges.filter((item) => !globalTaxonomySearch.trim() || item.entity_code.toLocaleLowerCase().includes(globalTaxonomySearch.trim().toLocaleLowerCase())).map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3"><div><p className="text-sm font-medium">{item.entity_code} · {{ create: "新增", update: "更新", delete: "删除/停用", restore: "恢复" }[item.action] ?? item.action}</p><p className="mt-1 text-xs text-muted-foreground">{item.origin === "ai_assistant" ? "AI建议经人工应用" : "人工维护"} · {new Date(item.created_at).toLocaleString("zh-CN")}</p></div>{item.run_id && <Badge variant="outline">任务 {item.run_id.slice(0, 8)}</Badge>}</div>)}{!globalPersonaChanges.length && <div className="rounded-xl border border-dashed py-16 text-center text-sm text-muted-foreground">新的画像维护操作会记录在这里。</div>}</div>
                    </TabsContent>
                  </Tabs>
                </Card>
              </div>
            )}

            {activeView === "history" && (
              <div className="space-y-5">
                <Card className="gap-4 border-cyan-200 bg-cyan-50/60 py-5 shadow-none">
                  <CardContent className="px-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-cyan-950">任务在所属模块执行，全局中心只负责监控与追溯</p>
                        <p className="mt-1 text-sm text-cyan-900/70">点击任务会回到机会发现、产品调研、买家画像或商机验证；详细结果不在这里重复维护。</p>
                      </div>
                      <Badge className={activeTaskCount ? "bg-amber-100 text-amber-800 hover:bg-amber-100" : "bg-emerald-100 text-emerald-800 hover:bg-emerald-100"}>{activeTaskCount ? `${activeTaskCount} 个任务执行中` : "当前无执行任务"}</Badge>
                    </div>
                  </CardContent>
                </Card>

                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  {(Object.entries(TASK_MODULE_META) as Array<[TaskCenterItem["module"], (typeof TASK_MODULE_META)[TaskCenterItem["module"]]]>).map(([key, meta]) => {
                    const moduleTasks = allTaskItems.filter((item) => item.module === key);
                    const moduleActive = moduleTasks.filter((item) => taskStatusGroup(item.status) === "active").length;
                    const moduleReview = moduleTasks.filter((item) => taskStatusGroup(item.status) === "review").length;
                    return <Card key={key} className="gap-3 py-4 shadow-none"><CardContent className="px-4"><div className="flex items-start justify-between gap-2"><div><p className="font-medium">{meta.label}</p><p className="mt-1 text-xs text-muted-foreground">{meta.note}</p></div><Badge variant="outline">{moduleTasks.length}</Badge></div><div className="mt-4 flex items-center justify-between text-xs text-muted-foreground"><span>{moduleActive ? `${moduleActive} 执行中` : "无执行中任务"}{moduleReview ? ` · ${moduleReview} 需关注` : ""}</span><Button variant="ghost" size="xs" onClick={() => navigateToView(meta.view)}>进入模块 <ChevronRight /></Button></div></CardContent></Card>;
                  })}
                </div>

                <Card className="gap-0 overflow-hidden py-0 shadow-none">
                  <CardHeader className="border-b px-5 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div><CardTitle className="text-base">跨模块任务记录</CardTitle><p className="mt-1 text-xs text-muted-foreground">数据库记录与 7 条 Codex 通道状态合并展示；运行中的进度每 4 秒更新。</p></div>
                      <Badge variant="outline">{filteredTaskItems.length} / {allTaskItems.length} 条</Badge>
                    </div>
                    <div className="mt-3 grid gap-2 md:grid-cols-[minmax(220px,1fr)_180px_180px]">
                      <div className="relative"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" /><Input className="pl-9" value={taskSearch} onChange={(event) => setTaskSearch(event.target.value)} placeholder="搜索任务、项目或模块" /></div>
                      <Select value={taskModule} onValueChange={setTaskModule}><SelectTrigger><SelectValue placeholder="全部模块" /></SelectTrigger><SelectContent><SelectItem value="all">全部模块</SelectItem>{(Object.entries(TASK_MODULE_META) as Array<[TaskCenterItem["module"], (typeof TASK_MODULE_META)[TaskCenterItem["module"]]]>).map(([key, meta]) => <SelectItem key={key} value={key}>{meta.label}</SelectItem>)}</SelectContent></Select>
                      <Select value={taskStatus} onValueChange={setTaskStatus}><SelectTrigger><SelectValue placeholder="全部状态" /></SelectTrigger><SelectContent><SelectItem value="all">全部状态</SelectItem><SelectItem value="active">执行中 / 等待</SelectItem><SelectItem value="review">待审核 / 部分完成</SelectItem><SelectItem value="completed">已完成</SelectItem><SelectItem value="failed">失败 / 中断</SelectItem></SelectContent></Select>
                    </div>
                  </CardHeader>
                  <Table><TableHeader><TableRow className="bg-slate-50/70"><TableHead className="pl-5">所属模块 / 任务</TableHead><TableHead>内容</TableHead><TableHead>状态</TableHead><TableHead>时间</TableHead><TableHead className="pr-5 text-right">处理</TableHead></TableRow></TableHeader><TableBody>
                    {filteredTaskItems.slice(0, 100).map((item) => {
                      const statusGroup = taskStatusGroup(item.status);
                      return <TableRow key={`${item.task_type}-${item.id}`}><TableCell className="pl-5"><Badge variant="outline">{TASK_MODULE_META[item.module].label}</Badge><p className="mt-2 text-xs text-muted-foreground">{item.task_label}</p></TableCell><TableCell><p className="max-w-lg font-medium">{item.title}</p><p className="mt-1 max-w-lg truncate text-xs text-muted-foreground">{item.error || item.subtitle || (item.result_count ? `${item.result_count} 条结果` : "等待结果")}</p></TableCell><TableCell><Badge className={statusGroup === "active" ? "bg-amber-100 text-amber-800 hover:bg-amber-100" : statusGroup === "failed" ? "bg-rose-100 text-rose-800 hover:bg-rose-100" : statusGroup === "review" ? "bg-cyan-100 text-cyan-800 hover:bg-cyan-100" : "bg-emerald-100 text-emerald-800 hover:bg-emerald-100"}>{TASK_STATUS_LABELS[item.status] ?? item.status}</Badge>{item.progress != null && statusGroup === "active" && <div className="mt-2 w-28"><Progress value={item.progress} className="h-1.5" /><p className="mt-1 text-right text-[10px] text-muted-foreground">{item.progress}%</p></div>}</TableCell><TableCell><p className="text-sm">{relativeTime(item.created_at)}</p><p className="mt-1 text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString("zh-CN")}</p></TableCell><TableCell className="pr-5 text-right"><Button variant="outline" size="sm" onClick={() => void openTaskOwner(item)}>进入模块 <ChevronRight /></Button></TableCell></TableRow>;
                    })}
                    {!filteredTaskItems.length && <TableRow><TableCell colSpan={5} className="h-36 text-center"><p className="font-medium">没有符合条件的任务</p><p className="mt-1 text-xs text-muted-foreground">清空筛选或先从对应模块建立任务。</p></TableCell></TableRow>}
                  </TableBody></Table>
                </Card>
              </div>
            )}

            {activeView === "dashboard" && (
              <div className="space-y-5">
                <Card className="gap-4 border-slate-200/80 py-5 shadow-none">
                  <CardHeader className="px-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <CardTitle className="text-base">机会发现趋势</CardTitle>
                        <p className="mt-1 text-xs text-muted-foreground">本模块只展示关键词与热点扫描形成的真实历史点；数据不足时不补造曲线。</p>
                      </div>
                      <Badge variant="outline">{data?.history.length ?? 0} 条记录</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="h-[330px] px-2 pr-5">
                    {mounted && chartData.length > 1 ? <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} initialDimension={{ width: 800, height: 330 }}>
                      <AreaChart data={chartData} margin={{ top: 12, right: 8, bottom: 0, left: -18 }}>
                        <defs>
                          <linearGradient id="historyHeatFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#0e7490" stopOpacity={0.28} />
                            <stop offset="95%" stopColor="#0e7490" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dbe4e7" />
                        <XAxis dataKey="week" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#64748b" }} />
                        <YAxis domain={[0, 100]} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#64748b" }} />
                        <ChartTooltip contentStyle={{ borderRadius: 10, border: "1px solid #dbe4e7", fontSize: 12 }} />
                        <Area type="monotone" dataKey="heat" name="热度" stroke="#0e7490" strokeWidth={2.5} fill="url(#historyHeatFill)" />
                        <Area type="monotone" dataKey="opportunity" name="机会" stroke="#d97706" strokeWidth={2} fill="transparent" />
                      </AreaChart>
                    </ResponsiveContainer> : (
                      <div className="grid h-full place-items-center text-center">
                        <div>
                          <History className="mx-auto size-8 text-slate-300" />
                          <p className="mt-3 text-sm font-medium">历史点不足</p>
                          <p className="mt-1 text-xs text-muted-foreground">完成下一次同口径扫描后，这里会显示真实变化。</p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card className="gap-0 overflow-hidden border-slate-200/80 py-0 shadow-none">
                  <div className="border-b px-5 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h2 className="font-semibold">机会发现扫描记录</h2>
                        <p className="text-xs text-muted-foreground">这里只管理关键词扫描与热点发现；调研、画像和商机任务在各自模块查看。</p>
                      </div>
                      <Badge variant="outline">{filteredHistory.length} / {data?.history.length ?? 0} 条</Badge>
                    </div>
                    <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-[minmax(220px,1.4fr)_repeat(6,minmax(118px,0.72fr))_auto]">
                      <div className="relative">
                        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
                        <Input
                          aria-label="搜索历史任务"
                          className="pl-9"
                          value={historySearch}
                          onChange={(event) => { setHistorySearch(event.target.value); setHistoryPage(1); }}
                          placeholder="搜索任务词、市场或方式"
                        />
                      </div>
                      <Select value={historyMode} onValueChange={(value) => { setHistoryMode(value); setHistoryPage(1); }}>
                        <SelectTrigger aria-label="按任务类型筛选"><SelectValue placeholder="全部类型" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部类型</SelectItem>
                          <SelectItem value="seed">关键词扫描</SelectItem>
                          <SelectItem value="discover">热点发现</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select value={historyMethod} onValueChange={(value) => { setHistoryMethod(value); setHistoryPage(1); }}>
                        <SelectTrigger aria-label="按处理方式筛选"><SelectValue placeholder="全部处理方式" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部处理方式</SelectItem>
                          <SelectItem value="assistant">AI 整理</SelectItem>
                          <SelectItem value="import">文件导入</SelectItem>
                          <SelectItem value="manual">待采集 / 手工</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select value={historyMarket} onValueChange={(value) => { setHistoryMarket(value); setHistoryPage(1); }}>
                        <SelectTrigger aria-label="按市场筛选"><SelectValue placeholder="全部市场" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部市场</SelectItem>
                          {historyMarkets.map((item) => <SelectItem key={item} value={item}>{marketNameForCode(item)}（{item}）</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Select value={historyLanguage} onValueChange={(value) => { setHistoryLanguage(value); setHistoryPage(1); }}>
                        <SelectTrigger aria-label="按语言筛选"><SelectValue placeholder="全部语言" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部语言</SelectItem>
                          {historyLanguages.map((item) => <SelectItem key={item} value={item}>{languageNameForCode(item)}（{item.toUpperCase()}）</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Select value={historyWindow} onValueChange={(value) => { setHistoryWindow(value); setHistoryPage(1); }}>
                        <SelectTrigger aria-label="按周期筛选"><SelectValue placeholder="全部周期" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部周期</SelectItem>
                          <SelectItem value="7">近 7 天</SelectItem>
                          <SelectItem value="30">近 30 天</SelectItem>
                          <SelectItem value="90">近 90 天</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select value={historyStatus} onValueChange={(value) => { setHistoryStatus(value); setHistoryPage(1); }}>
                        <SelectTrigger aria-label="按状态筛选"><SelectValue placeholder="全部状态" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部状态</SelectItem>
                          <SelectItem value="running">执行中</SelectItem>
                          <SelectItem value="finished">已完成</SelectItem>
                          <SelectItem value="waiting">待采集</SelectItem>
                          <SelectItem value="failed">失败</SelectItem>
                          <SelectItem value="demo">演示</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button
                        variant={historyHasResults ? "secondary" : "outline"}
                        onClick={() => { setHistoryHasResults((value) => !value); setHistoryPage(1); }}
                        aria-pressed={historyHasResults}
                      >
                        <ListFilter /> 只看有结果
                      </Button>
                    </div>
                    <div className="mt-3 flex min-h-6 flex-wrap items-center gap-2">
                      {activeHistoryFilters.length ? (
                        <>
                          <span className="text-xs text-muted-foreground">当前条件</span>
                          {activeHistoryFilters.map((item) => <Badge key={item} variant="secondary">{item}</Badge>)}
                          <Button variant="ghost" size="xs" onClick={clearHistoryFilters}>清空筛选</Button>
                        </>
                      ) : <span className="text-xs text-muted-foreground">当前显示全部任务</span>}
                    </div>
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-50/70 hover:bg-slate-50/70">
                        <TableHead className="pl-5">扫描内容</TableHead>
                        <TableHead>扫描条件</TableHead>
                        <TableHead>结果 / 证据</TableHead>
                        <TableHead>平均评分</TableHead>
                        <TableHead>状态</TableHead>
                        <TableHead className="text-right">查看</TableHead>
                        <TableHead className="text-right">下载</TableHead>
                        <TableHead className="pr-5 text-right">操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {pagedHistory.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={8} className="h-36 text-center">
                            <p className="font-medium">没有符合当前条件的任务</p>
                            <Button className="mt-2" variant="ghost" size="sm" onClick={clearHistoryFilters}>清空筛选</Button>
                          </TableCell>
                        </TableRow>
                      )}
                      {pagedHistory.map((item) => {
                        const isRunning = activeJob?.runId === item.id;
                        const canDownload = item.observation_count > 0 && ["complete", "partial"].includes(item.status);
                        return <TableRow key={item.id}>
                          <TableCell className="pl-5">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="font-medium">{item.query}</p>
                              <Badge variant="outline" className="text-[10px]">{taskTypeLabel(item)}</Badge>
                            </div>
                            <p className="text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString("zh-CN")}</p>
                            {Boolean(item.source_summary.assistantSummary) && <p className="mt-1 max-w-md truncate text-xs text-cyan-800">{String(item.source_summary.assistantSummary)}</p>}
                            {!item.source_summary.assistantSummary && Boolean(item.source_summary.generator) && <p className="mt-1 text-xs text-cyan-800">由 {String(item.source_summary.generator)} 整理</p>}
                          </TableCell>
                          <TableCell>
                            <div className="flex max-w-xs flex-wrap gap-1.5">
                              <Badge variant="outline">国家：{marketNameForCode(item.market)}（{item.market}）</Badge>
                              <Badge variant="outline">语种：{languageNameForCode(item.language)}（{item.language.toUpperCase()}）</Badge>
                              <Badge variant="outline">近 {item.window_days} 天</Badge>
                              <Badge variant="secondary">任务：{taskTypeLabel(item)}</Badge>
                              <Badge variant="secondary">处理：{PROCESSING_METHOD_LABELS[processingMethod(item)] ?? processingMethod(item)}</Badge>
                            </div>
                          </TableCell>
                          <TableCell>
                            <p>{item.cluster_count} 个词簇</p>
                            <p className="text-xs text-muted-foreground">{item.valid_observation_count}/{item.observation_count} 条有效 · {item.platform_count} 个平台</p>
                          </TableCell>
                          <TableCell>
                            <p>热度 {item.heat == null ? "—" : Math.round(item.heat)}</p>
                            <p className="text-xs text-muted-foreground">机会 {item.opportunity == null ? "—" : Math.round(item.opportunity)}</p>
                          </TableCell>
                          <TableCell>
                            <Badge variant={isRunning || item.status === "complete" ? "secondary" : "outline"} className={isRunning ? "border-amber-200 bg-amber-50 text-amber-800" : ""}>
                              {isRunning ? `执行中 · ${activeJobProgress}%` : runStatusLabel(item.status, Boolean(item.is_demo))}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={item.cluster_count === 0}
                              title={item.cluster_count === 0 ? "任务有结果后可查看" : "在线查看结果明细"}
                              onClick={() => void openRunDetail(item)}
                            >
                              <Eye /> 查看明细
                            </Button>
                          </TableCell>
                          <TableCell className="text-right">
                            {canDownload ? (
                              <Button variant="outline" size="sm" asChild>
                                <a href={`/api/radar?view=export&format=csv&runId=${encodeURIComponent(item.id)}`} download><Download /> 下载 CSV</a>
                              </Button>
                            ) : <span className="text-xs text-muted-foreground">完成后可下载</span>}
                          </TableCell>
                          <TableCell className="pr-5 text-right">
                            <div className="flex items-center justify-end">
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                disabled={isRunning}
                                title={isRunning ? "执行中的任务不能删除" : "删除任务"}
                                aria-label={`删除任务 ${item.query}`}
                                onClick={() => { setDeleteMessage(""); setDeleteTarget(item); }}
                              >
                                <Trash2 className="text-slate-500" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      })}
                    </TableBody>
                  </Table>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-3">
                    <p className="text-xs text-muted-foreground">
                      {filteredHistory.length
                        ? `显示 ${(currentHistoryPage - 1) * HISTORY_PAGE_SIZE + 1}–${Math.min(currentHistoryPage * HISTORY_PAGE_SIZE, filteredHistory.length)}，共 ${filteredHistory.length} 条`
                        : "共 0 条"}
                    </p>
                    <div className="flex items-center gap-2">
                      <Button variant="outline" size="sm" disabled={currentHistoryPage <= 1} onClick={() => setHistoryPage(Math.max(1, currentHistoryPage - 1))}>
                        <ChevronLeft /> 上一页
                      </Button>
                      <span className="min-w-16 text-center text-sm tabular-nums">{currentHistoryPage} / {historyTotalPages}</span>
                      <Button variant="outline" size="sm" disabled={currentHistoryPage >= historyTotalPages} onClick={() => setHistoryPage(Math.min(historyTotalPages, currentHistoryPage + 1))}>
                        下一页 <ChevronRight />
                      </Button>
                    </div>
                  </div>
                </Card>
              </div>
            )}

            {activeView === "watchlist" && (
              <div className="space-y-5">
                <Card className="gap-4 border-slate-200/80 py-5 shadow-none">
                  <CardHeader className="px-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <CardTitle className="text-base">观察中的关键词簇</CardTitle>
                        <p className="mt-1 text-xs text-muted-foreground">记录建议复查日期；当前版本不会自动采集或发送通知</p>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => navigateToView("dashboard")}>
                        <Search /> 去机会榜选择
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="px-5">
                    {(data?.watchlist.length ?? 0) === 0 ? (
                      <div className="grid min-h-52 place-items-center rounded-xl border border-dashed bg-slate-50/50 p-8 text-center">
                        <div>
                          <Bookmark className="mx-auto size-8 text-slate-400" />
                          <p className="mt-3 font-medium">还没有观察项</p>
                          <p className="mt-1 text-sm text-muted-foreground">在机会榜点击书签即可加入，不需要审批。</p>
                        </div>
                      </div>
                    ) : (
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {data!.watchlist.map((item) => (
                          <div key={item.id} className="rounded-xl border bg-white p-4">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="font-medium">{item.canonical_keyword}</p>
                                <p className="mt-1 text-xs text-muted-foreground">{item.group_name} · {item.market}</p>
                              </div>
                              <Badge variant="secondary">每 {item.cadence_days} 天</Badge>
                            </div>
                            <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs text-muted-foreground">
                              <span>建议复查：{item.next_run_at ? new Date(item.next_run_at).toLocaleDateString("zh-CN") : "待安排"}</span>
                              <Button variant="ghost" size="sm" onClick={() => toggleSaved(item.cluster_id)}>移出观察</Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}

            {activeView === "sources" && (
              <div className="space-y-5">
                <Card className="gap-3 border-cyan-200 bg-cyan-50/60 py-4 shadow-none">
                  <CardContent className="px-5">
                    <div>
                      <p className="font-medium">数据渠道与责任分工</p>
                      <p className="mt-1 text-sm text-muted-foreground">官方贸易数据、本地销售数据和平台信号分层保存；直接点击下方对应数据源完成配置。</p>
                    </div>
                  </CardContent>
                </Card>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card className="gap-3 border-cyan-200 bg-cyan-50/50 py-5 shadow-none"><CardHeader className="px-5"><CardTitle className="flex items-center gap-2 text-base"><Bot className="size-5 text-cyan-800" /> ChatGPT 自动完成</CardTitle></CardHeader><CardContent className="space-y-2 px-5">{CHATGPT_TRADE_WORKFLOW.map((item) => <p key={item} className="text-sm leading-6 text-cyan-950">✓ {item}</p>)}<p className="pt-2 text-xs text-cyan-800">贸易数据通道通过本机 Codex 工作，不需要在网页重复填写 OpenAI API Key。</p></CardContent></Card>
                  <Card className="gap-3 py-5 shadow-none"><CardHeader className="px-5"><CardTitle className="flex items-center gap-2 text-base"><Target className="size-5 text-cyan-800" /> 你只需要处理 3 类事项</CardTitle></CardHeader><CardContent className="space-y-2 px-5">{USER_TRADE_RESPONSIBILITIES.map((item) => <p key={item} className="text-sm leading-6 text-muted-foreground">• {item}</p>)}<p className="pt-2 text-xs font-medium text-cyan-800">其余查找、整理、去重、保存和趋势摘要交给 ChatGPT。</p></CardContent></Card>
                </div>

                <Card className="gap-4 border-slate-200/80 py-5 shadow-none">
                  <CardHeader className="px-5"><CardTitle className="text-base">商机贸易与销售数据渠道</CardTitle><p className="text-sm text-muted-foreground">点击来源可查看官方入口；每张卡明确哪些可以自动、哪些只需你做一次设置。</p></CardHeader>
                  <CardContent className="grid gap-3 px-5 md:grid-cols-2 xl:grid-cols-4">
                    {TRADE_SOURCE_CATALOG.map((source) => {
                      const credential = managedCredentials.find((item) => item.id === source.id);
                      return (
                        <div key={source.id} className="flex flex-col rounded-xl border bg-white p-4 transition hover:border-cyan-300 hover:shadow-sm">
                          <div className="flex items-start justify-between gap-2">
                            <div><h3 className="font-medium">{source.name}</h3><p className="mt-1 text-xs text-muted-foreground">{source.scope}</p></div>
                            <Badge variant={credential?.configured ? "secondary" : source.automation === "automatic" ? "secondary" : "outline"}>
                              {credential?.source === "managed" ? "已加密配置" : credential?.source === "environment" ? "环境变量配置" : credential?.source === "public" ? "公开可用" : TRADE_SOURCE_AUTOMATION_LABELS[source.automation]}
                            </Badge>
                          </div>
                          <p className="mt-3 text-xs leading-5"><span className="font-medium text-cyan-900">ChatGPT：</span>{source.chatgptCanDo}</p>
                          <p className="mt-2 text-xs leading-5 text-muted-foreground"><span className="font-medium text-slate-800">你：</span>{source.userMustDo}</p>
                          {credential && (
                            <div className="mt-3 rounded-lg bg-slate-50 p-2.5 text-xs leading-5 text-slate-700">
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge variant={credential.healthStatus === "completed" ? "secondary" : "outline"}>{SOURCE_HEALTH_LABELS[credential.healthStatus]}</Badge>
                                {credential.lastAttemptAt && <span>最近执行 {new Date(credential.lastAttemptAt).toLocaleString("zh-CN")}</span>}
                              </div>
                              {credential.lastAttemptAt && <p className="mt-1">结果 {credential.resultCount} 条 · {credential.durationMs} ms · 重试 {credential.retryCount} 次</p>}
                              {credential.coverageCountries.length > 0 && <p>覆盖：{credential.coverageCountries.join("、")}</p>}
                              {credential.updateFrequency && <p>更新：{credential.updateFrequency}</p>}
                              {credential.quotaSummary && <p>配额：{credential.quotaSummary}</p>}
                              {credential.lastError && <p className="text-rose-700">{credential.lastErrorCategory || "错误"}：{credential.lastError}</p>}
                            </div>
                          )}
                          <div className="mt-auto flex flex-wrap items-center gap-2 border-t pt-3 text-xs">
                            <span className="text-muted-foreground">{source.freeAccess}</span>
                            {credential ? (
                              <Button size="sm" className="ml-auto" onClick={() => openCredentialManager(source.id)}>
                                <KeyRound /> {credential.publicAccess ? "查看接入" : credential.configured ? "管理连接" : "配置连接"}
                              </Button>
                            ) : (
                              <span className="ml-auto font-medium text-cyan-800">使用下方导入</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>

                <div className="border-t pt-5"><h2 className="font-semibold">趋势、竞争与商品数据渠道</h2><p className="mt-1 text-sm text-muted-foreground">以下是关键词热度、广告、海外电商商品和图片来源，不等同于真实成交额。</p></div>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  {liveSources.map((source) => {
                    if (source.name === "Alibaba.com") return null;
                    const connectionId = platformCredentialId(source.name);
                    const credential = connectionId ? managedCredentials.find((item) => item.id === connectionId) : null;
                    const connectionLabel = source.name === "Google Trends"
                      ? "配置 Keyword Planner"
                      : credential?.configured
                        ? "管理 API"
                        : "配置 API";
                    return (
                    <Card key={source.name} className="gap-3 border-slate-200/80 py-4 shadow-none">
                      <CardContent className="flex h-full flex-col px-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium">{source.name}</p>
                            <p className="mt-0.5 text-[10px] text-muted-foreground">{CORE_PLATFORM_SET.has(source.name) ? "核心评分来源" : "补充电商来源"}</p>
                          </div>
                          <Badge variant={source.state === "可用" ? "secondary" : "outline"}>{source.state}</Badge>
                        </div>
                        <div className="mt-4 flex items-end justify-between">
                          <span className="text-2xl font-semibold tabular-nums">{source.coverage}%</span>
                          <span className="text-xs text-muted-foreground">{source.freshness}</span>
                        </div>
                        <Progress value={source.coverage} className="mt-2 h-1.5 bg-slate-100 [&_[data-slot=progress-indicator]]:bg-cyan-700" />
                        <p className="mt-3 text-xs leading-5 text-muted-foreground">
                          {source.observationCount} 条观测
                          {source.sourceKinds.length > 0
                            ? ` · ${source.sourceKinds.map((kind) => SOURCE_KIND_LABELS[kind] ?? kind).join("、")}`
                            : " · 尚无来源明细"}
                        </p>
                        {connectionId && (
                          <div className="mt-3 flex items-center justify-between gap-2 border-t pt-3">
                            <span className="text-xs text-muted-foreground">
                              {credential?.source === "managed" ? "凭证已加密" : credential?.source === "environment" ? "环境变量已配置" : "API 尚未配置"}
                            </span>
                            <Button variant="outline" size="sm" onClick={() => openCredentialManager(connectionId)}>
                              <KeyRound /> {connectionLabel}
                            </Button>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                    );
                  })}
                </div>

                <Card className="gap-4 border-slate-200/80 py-5 shadow-none">
                  <CardHeader className="px-5">
                    <CardTitle className="text-base">采集与导入</CardTitle>
                    <p className="text-sm text-muted-foreground">优先使用官方接口或导出，其次浏览器抽样；认证失败和限流不会自动重试。</p>
                  </CardHeader>
                  <CardContent className="grid gap-4 px-5 md:grid-cols-3">
                    <button type="button" className="rounded-xl border p-4 text-left transition hover:bg-slate-50" onClick={() => setAssistantOpen(true)}>
                      <Bot className="size-5 text-cyan-700" />
                      <h3 className="mt-3 font-medium">AI 整理并入库</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">调用已配置的 OpenAI API，整理关键词和公开证据；API 通常按量计费。</p>
                    </button>
                    <button type="button" className="rounded-xl border p-4 text-left transition hover:bg-slate-50" onClick={() => setImportOpen(true)}>
                      <FileUp className="size-5 text-cyan-700" />
                      <h3 className="mt-3 font-medium">导入 CSV / JSON</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">适合平台导出、第三方工具结果或手工补充证据。</p>
                    </button>
                    <div className="rounded-xl border p-4">
                      <Database className="size-5 text-cyan-700" />
                      <h3 className="mt-3 font-medium">本地证据库</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">保存原始值、来源、时间、地区、状态和评分版本，后续可迁移上线。</p>
                    </div>
                  </CardContent>
                </Card>

                <Card className="gap-0 overflow-hidden border-slate-200/80 py-0 shadow-none">
                  <div className="border-b px-5 py-4">
                    <h2 className="font-semibold">本次数据来源明细</h2>
                    <p className="text-xs text-muted-foreground">显示原始来源类型、链接、采集时间和失败原因</p>
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-50/70 hover:bg-slate-50/70">
                        <TableHead className="pl-5">平台 / 指标</TableHead>
                        <TableHead>来源类型</TableHead>
                        <TableHead>地区 / 时间</TableHead>
                        <TableHead>状态</TableHead>
                        <TableHead className="pr-5">证据或原因</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(data?.observations ?? []).length === 0 && (
                        <TableRow><TableCell colSpan={5} className="h-28 text-center text-muted-foreground">暂无来源明细。可先免费导入官方导出文件，或使用 AI 整理。</TableCell></TableRow>
                      )}
                      {(data?.observations ?? []).map((observation) => (
                        <TableRow key={observation.id}>
                          <TableCell className="pl-5"><p className="font-medium">{observation.platform}</p><p className="text-xs text-muted-foreground">{observation.metric}</p></TableCell>
                          <TableCell>{SOURCE_KIND_LABELS[observation.source_kind] ?? observation.source_kind}</TableCell>
                          <TableCell><p>{marketNameForCode(observation.geo_scope)}（{observation.geo_scope}） · {observation.coverage_days} 天</p><p className="text-xs text-muted-foreground">{new Date(observation.collected_at).toLocaleString("zh-CN")}</p></TableCell>
                          <TableCell><Badge variant={["ok", "confirmed_zero"].includes(observation.status) ? "secondary" : "outline"}>{OBSERVATION_STATUS_LABELS[observation.status] ?? observation.status}</Badge></TableCell>
                          <TableCell className="max-w-sm pr-5 text-xs">
                            {isSafeSourceUrl(observation.source_ref) && (
                              <a className="inline-flex items-center gap-1 font-medium text-cyan-800 hover:underline" href={observation.source_ref} target="_blank" rel="noreferrer">打开来源 <ExternalLink className="size-3" /></a>
                            )}
                            <p className="mt-1 leading-5 text-muted-foreground">{observation.missing_reason ?? (isSafeSourceUrl(observation.source_ref) ? "来源已记录" : "未提供来源链接")}</p>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Card>
              </div>
            )}
          </div>
        </section>
      </div>
      )}

      <Sheet
        open={detailTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDetailTarget(null);
            setDetailData(null);
            setDetailError("");
          }
        }}
      >
        <SheetContent className="w-[94vw] overflow-y-auto sm:max-w-[1500px]">
          <SheetHeader className="border-b p-5 pr-12">
            <SheetTitle className="text-xl">在线结果明细</SheetTitle>
            <SheetDescription>
              {detailTarget
                ? `${detailTarget.query} · 国家：${marketNameForCode(detailTarget.market)}（${detailTarget.market}） · 语种：${languageNameForCode(detailTarget.language)}（${detailTarget.language.toUpperCase()}） · 近 ${detailTarget.window_days} 天`
                : "任务明细"}
            </SheetDescription>
          </SheetHeader>
          <div className="p-5">
            {detailLoading && (
              <div className="grid min-h-72 place-items-center text-center">
                <div><Activity className="mx-auto size-8 animate-pulse text-cyan-700" /><p className="mt-3 text-sm">正在读取任务结果…</p></div>
              </div>
            )}
            {!detailLoading && detailError && (
              <div className="grid min-h-72 place-items-center text-center">
                <div>
                  <CircleAlert className="mx-auto size-8 text-amber-600" />
                  <p className="mt-3 font-medium">{detailError}</p>
                  {detailTarget && <Button className="mt-3" variant="outline" onClick={() => void openRunDetail(detailTarget)}>重新读取</Button>}
                </div>
              </div>
            )}
            {!detailLoading && detailData && (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-4">
                  {[
                    ["关键词簇", detailData.results.length],
                    ["有效证据", detailData.observations.filter((item) => ["ok", "confirmed_zero"].includes(item.status)).length],
                    ["来源平台", new Set(detailData.observations.map((item) => item.platform)).size],
                    ["中文品名", detailData.results.filter((item) => Boolean(item.keyword_zh)).length],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="rounded-xl border bg-slate-50 p-3">
                      <p className="text-xs text-muted-foreground">{label}</p>
                      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
                    </div>
                  ))}
                </div>
                {detailData.results.length === 0 ? (
                  <div className="grid min-h-64 place-items-center rounded-xl border border-dashed text-center">
                    <div><History className="mx-auto size-8 text-slate-300" /><p className="mt-3 font-medium">当前任务还没有结果明细</p></div>
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-xl border">
                    <Table className="min-w-[1420px]">
                      <TableHeader>
                        <TableRow className="bg-slate-50/80 hover:bg-slate-50/80">
                          <TableHead className="pl-4">图片</TableHead>
                          <TableHead>中文品名 / 原关键词</TableHead>
                          <TableHead>词簇 / 类目</TableHead>
                          {detailData.run.market === "GLOBAL" && <TableHead>数据国家</TableHead>}
                          <TableHead>采购价范围</TableHead>
                          <TableHead className="text-center">热度</TableHead>
                          <TableHead className="text-center">机会</TableHead>
                          <TableHead className="text-center">采购意图</TableHead>
                          <TableHead className="text-center">竞争度</TableHead>
                          <TableHead className="text-center">置信度</TableHead>
                          <TableHead className="pr-4">来源证据</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {detailData.results.map((item) => {
                          const evidence = detailData.observations.filter((observation) => observation.cluster_id === item.cluster_id);
                          return (
                            <TableRow key={item.cluster_id} className="h-20">
                              <TableCell className="pl-4">
                                <ProductImages
                                  images={item.images}
                                  legacySrc={item.image_url}
                                  alt={`${item.keyword_zh ?? item.canonical_keyword} 产品图`}
                                  onPreview={(index) => {
                                    const images = item.images?.length
                                      ? item.images
                                      : item.image_url
                                        ? [{ url: item.image_url, platform: "", source_ref: "", verified_source: false }]
                                        : [];
                                    if (images.length) setImagePreview({ images, index, alt: `${item.keyword_zh ?? item.canonical_keyword} 产品图` });
                                  }}
                                />
                              </TableCell>
                              <TableCell className="max-w-[260px]">
                                <div className="flex items-center gap-1.5">
                                  <p className="truncate font-semibold" title={item.keyword_zh ?? "待补充中文翻译"}>{item.keyword_zh ?? "待补充中文翻译"}</p>
                                  <Badge variant="secondary" className="shrink-0 text-[10px]">{item.lifecycle}</Badge>
                                </div>
                                <p className="mt-1 truncate text-xs text-muted-foreground" title={item.canonical_keyword}>{item.canonical_keyword}</p>
                              </TableCell>
                              {detailData.run.market === "GLOBAL" && (
                                <TableCell className="max-w-[220px]">
                                  <div className="flex flex-wrap gap-1">
                                    {(item.geo_scopes ?? []).length
                                      ? item.geo_scopes?.map((scope) => <Badge key={scope} variant="outline">{marketNameForCode(scope)}（{scope}）</Badge>)
                                      : <span className="text-sm text-muted-foreground">—</span>}
                                  </div>
                                </TableCell>
                              )}
                              <TableCell className="whitespace-nowrap text-sm font-medium tabular-nums">{formatPurchasePrice(item)}</TableCell>
                              <TableCell className="max-w-[260px]">
                                <p className="truncate text-sm" title={item.group_name}>{item.group_name}</p>
                                <p className="mt-1 truncate text-xs text-muted-foreground" title={[item.category, ...(item.aliases ?? [])].join(" · ")}>
                                  {item.category}{(item.aliases ?? []).length ? ` · ${(item.aliases ?? []).length} 个变体` : ""}
                                </p>
                              </TableCell>
                              {[item.heat, item.opportunity, item.buyer_intent, item.competition].map((value, index) => (
                                <TableCell key={index} className="text-center font-semibold tabular-nums">{value == null ? "—" : Math.round(Number(value))}</TableCell>
                              ))}
                              <TableCell className="text-center">
                                <Badge variant="outline">{Math.round(item.confidence)}%</Badge>
                              </TableCell>
                              <TableCell className="pr-4">
                                <p className="mb-1.5 text-xs text-muted-foreground">{item.valid_observation_count ?? 0}/{item.observation_count ?? 0} 条有效</p>
                                <div className="flex items-center gap-1">
                                  {evidence.map((observation) => {
                                    const valid = ["ok", "confirmed_zero"].includes(observation.status);
                                    const shortName = SOURCE_SHORT_LABELS[observation.platform] ?? observation.platform;
                                    const className = `rounded-md border px-1.5 py-1 text-[10px] font-medium ${valid ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-500"}`;
                                    const title = `${observation.platform} · ${marketNameForCode(observation.geo_scope)}（${observation.geo_scope}） · ${OBSERVATION_STATUS_LABELS[observation.status] ?? observation.status} · 当前值 ${observation.current_value ?? "—"}`;
                                    return isSafeSourceUrl(observation.source_ref)
                                      ? <a key={observation.id} className={className} title={title} href={observation.source_ref} target="_blank" rel="noreferrer">{shortName}</a>
                                      : <span key={observation.id} className={className} title={title}>{shortName}</span>;
                                  })}
                                </div>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>

      <Dialog open={imagePreview !== null} onOpenChange={(open) => !open && setImagePreview(null)}>
        <DialogContent className="max-h-[92vh] max-w-5xl overflow-hidden bg-slate-950 p-3 text-white">
          <DialogHeader className="sr-only">
            <DialogTitle>{imagePreview?.alt ?? "产品图片"}</DialogTitle>
            <DialogDescription>产品图片放大预览与原始来源</DialogDescription>
          </DialogHeader>
          {imagePreview && (
            <div className="relative flex min-h-[70vh] flex-col items-center justify-center gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imagePreview.images[imagePreview.index].url}
                alt={`${imagePreview.alt} ${imagePreview.index + 1}`}
                referrerPolicy="no-referrer"
                className="mx-auto max-h-[76vh] max-w-full rounded-lg object-contain"
              />
              {imagePreview.images.length > 1 && (
                <>
                  <Button
                    type="button"
                    size="icon"
                    variant="secondary"
                    className="absolute left-3 top-1/2 -translate-y-1/2"
                    onClick={() => setImagePreview((current) => current ? { ...current, index: (current.index - 1 + current.images.length) % current.images.length } : null)}
                    aria-label="上一张图片"
                  ><ChevronLeft /></Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="secondary"
                    className="absolute right-3 top-1/2 -translate-y-1/2"
                    onClick={() => setImagePreview((current) => current ? { ...current, index: (current.index + 1) % current.images.length } : null)}
                    aria-label="下一张图片"
                  ><ChevronRight /></Button>
                </>
              )}
              <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-slate-200">
                <span>{imagePreview.index + 1} / {imagePreview.images.length}</span>
                {imagePreview.images[imagePreview.index].platform && <Badge variant="secondary">{imagePreview.images[imagePreview.index].platform}</Badge>}
                <Badge variant="outline" className="border-slate-500 text-slate-100">
                  {imagePreview.images[imagePreview.index].verified_source ? "图片来源已记录" : "历史图片来源待核验"}
                </Badge>
                {isSafeSourceUrl(imagePreview.images[imagePreview.index].source_ref) && (
                  <a className="inline-flex items-center gap-1 font-medium text-cyan-300 hover:underline" href={imagePreview.images[imagePreview.index].source_ref} target="_blank" rel="noreferrer">
                    打开原商品页 <ExternalLink className="size-3" />
                  </a>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {selected && (
            <>
              <SheetHeader className="border-b p-5 pr-12">
                <div className="mb-2 flex items-center gap-2">
                  <Badge className="bg-cyan-950">机会 {selected.opportunity ?? "待补证据"}</Badge>
                  <Badge variant="outline">置信度 {selected.confidence}%</Badge>
                </div>
                <SheetTitle className="text-xl">{selected.keyword}</SheetTitle>
                <SheetDescription>{selected.group} · {data?.run?.market ?? "—"} · {data?.run?.language?.toUpperCase() ?? "—"} · 近 {data?.run?.window_days ?? "—"} 天</SheetDescription>
              </SheetHeader>
              <div className="space-y-6 p-5">
                <section>
                  <h3 className="text-sm font-semibold">规则解释（可由 AI 补充）</h3>
                  <p className="mt-2 rounded-xl bg-cyan-50 p-4 text-sm leading-6 text-cyan-950">{selected.rationale}</p>
                </section>
                <section>
                  <h3 className="mb-3 text-sm font-semibold">五维证据</h3>
                  <div className="space-y-3">
                    {[
                      ["当前热度", selected.heat],
                      ["增长动量", selected.momentum],
                      ["商业验证", selected.commercial],
                      ["采购意图", selected.intent],
                      ["供应竞争", selected.competition],
                    ].map(([label, value]) => (
                      <div key={String(label)}>
                        <div className="mb-1 flex justify-between text-sm"><span>{label}</span><span className="font-medium tabular-nums">{value ?? "—"}</span></div>
                        <Progress value={value === null ? 0 : Number(value)} className="h-1.5 bg-slate-100 [&_[data-slot=progress-indicator]]:bg-cyan-700" />
                      </div>
                    ))}
                  </div>
                </section>
                <section>
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold">关键词变体</h3>
                    <span className="text-xs text-muted-foreground">拆分仅影响后续导入</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selected.aliases.length === 0 && <span className="text-sm text-muted-foreground">暂无变体</span>}
                    {selected.aliases.map((alias) => (
                      <span key={alias} className="inline-flex items-center overflow-hidden rounded-md border bg-slate-50 text-xs">
                        <span className="px-2 py-1">{alias}</span>
                        <button type="button" disabled={busy} className="border-l px-2 py-1 text-cyan-800 hover:bg-cyan-50" onClick={() => splitAlias(alias)}>
                          拆分
                        </button>
                      </span>
                    ))}
                  </div>
                </section>
                <section>
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold">原始证据</h3>
                    <span className="text-xs text-muted-foreground">评分版本 {data?.results.find((row) => row.cluster_id === selected.id)?.score_version ?? "v1.0"}</span>
                  </div>
                  <div className="space-y-2">
                    {selectedObservations.length === 0 && (
                      <div className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">暂无原始证据</div>
                    )}
                    {selectedObservations.map((observation) => {
                      const successful = ["ok", "confirmed_zero"].includes(observation.status);
                      const metricLabel = { attention: "关注度", commercial: "商业验证", competition: "供应竞争" }[observation.metric] ?? observation.metric;
                      const stateLabel = {
                        ok: "有效",
                        confirmed_zero: "确认 0",
                        unsupported: "不支持",
                        auth_failed: "认证失败",
                        rate_limited: "限流",
                        collection_error: "采集失败",
                        geo_unavailable: "地区不可用",
                      }[observation.status] ?? observation.status;
                      return (
                      <div key={observation.id} className="rounded-lg border p-3 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            {successful ? <Check className="size-4 text-emerald-600" /> : <CircleAlert className="size-4 text-amber-600" />}
                            <span className="font-medium">{observation.platform}</span>
                            <span className="text-xs text-muted-foreground">{metricLabel}</span>
                          </div>
                          <Badge variant={successful ? "secondary" : "outline"}>{stateLabel}</Badge>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                          <span>当前 {observation.current_value ?? "—"} · 前期 {observation.previous_value ?? "—"}</span>
                          <span>{relativeTime(observation.collected_at)}</span>
                        </div>
                        {!successful && observation.missing_reason && <p className="mt-2 text-xs text-amber-800">{observation.missing_reason}</p>}
                      </div>
                    )})}
                  </div>
                </section>
                <section className="rounded-xl border p-4">
                  <h3 className="text-sm font-semibold">合并重复词簇</h3>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">把另一个词簇作为当前词的变体；历史快照保留，后续导入按新规则归类。</p>
                  <div className="mt-3 flex gap-2">
                    <Select value={mergeSourceId} onValueChange={setMergeSourceId}>
                      <SelectTrigger className="min-w-0 flex-1"><SelectValue placeholder="选择要并入的词簇" /></SelectTrigger>
                      <SelectContent>
                        {liveRows.filter((row) => row.id !== selected.id && row.status !== "排除").map((row) => (
                          <SelectItem key={row.id} value={row.id}>{row.keyword}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button variant="outline" disabled={busy || !mergeSourceId} onClick={mergeIntoSelected}>合并</Button>
                  </div>
                </section>
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
                  <div className="flex items-center gap-2 font-medium"><CircleAlert className="size-4" /> 产品门槛尚未验证</div>
                  <p className="mt-1">热度只代表值得测试；毛利、认证、物流、MOQ 与供应稳定性仍需单独核验。</p>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      {researchDetailProjectId && (
        <div className="mx-auto grid min-h-screen max-w-[1920px] lg:grid-cols-[232px_minmax(0,1fr)]">
          {sidebar}
          <section className="min-w-0 bg-slate-50/60">
          <header className="sticky top-0 z-20 border-b bg-white/95 px-4 py-3 backdrop-blur md:px-7">
            <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <Button variant="outline" size="sm" onClick={returnToResearchList}><ChevronLeft /> 返回项目库</Button>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{researchDetail?.project.product_name ?? "产品与市场调研"}</p>
                  <p className="text-xs text-muted-foreground">独立详情页 · 可刷新、复制链接并使用浏览器前进/后退</p>
                </div>
              </div>
              {researchDetail && (
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className={researchBadgeClass(researchDetail.project.status)}>
                    {RESEARCH_STATUS_LABELS[researchDetail.project.status] ?? researchDetail.project.status}
                  </Badge>
                  <Button variant="outline" size="sm" asChild><a href={`/api/radar?view=research_export&projectId=${encodeURIComponent(researchDetail.project.id)}`} download><Download /> 导出 Markdown</a></Button>
                </div>
              )}
            </div>
          </header>
          <div className="mx-auto max-w-[1680px] space-y-5 p-4 md:p-6">
            {researchDetailLoading && !researchDetail && (
              <div className="grid min-h-[60vh] place-items-center rounded-2xl border bg-white text-center">
                <div><Activity className="mx-auto size-8 animate-pulse text-cyan-700" /><p className="mt-3 text-sm">正在读取调研项目…</p></div>
              </div>
            )}
            {!researchDetailLoading && researchDetailError && (
              <div className="grid min-h-[60vh] place-items-center rounded-2xl border bg-white text-center">
                <div className="max-w-md px-5"><CircleAlert className="mx-auto size-9 text-amber-600" /><h1 className="mt-3 text-lg font-semibold">无法打开调研项目</h1><p className="mt-2 text-sm text-muted-foreground">{researchDetailError}</p><div className="mt-4 flex justify-center gap-2"><Button variant="outline" onClick={returnToResearchList}>返回项目库</Button><Button onClick={() => void loadResearchProject(researchDetailProjectId)}>重新读取</Button></div></div>
              </div>
            )}
            {researchDetail && (
            <div className="space-y-5 rounded-2xl border bg-white p-4 shadow-sm md:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h1 className="text-2xl font-semibold tracking-tight">{researchDetail.project.product_name}</h1>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {researchDetail.project.product_category || "未分类"} · {researchDetail.project.target_markets.map((item) => `${marketNameForCode(item)}（${item}）`).join("、")}
                  </p>
                </div>
                <Badge variant="outline" className={researchBadgeClass(researchDetail.project.status)}>
                  {RESEARCH_STATUS_LABELS[researchDetail.project.status] ?? researchDetail.project.status}
                </Badge>
              </div>
              {researchMessage && <p className="rounded-lg bg-cyan-50 px-3 py-2 text-xs text-cyan-900">{researchMessage}</p>}
              {researchPendingRun && researchLatestRun && (
                <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
                  新一轮正在处理中；当前继续显示上一份已完成版本，完成后再增量合并，不会清空原有赛道、市场或产品。
                </p>
              )}

              <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-4">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <label className="min-w-0 flex-1 text-xs font-medium text-cyan-950">
                    本轮补充要求
                    <Input className="mt-1.5 bg-white" value={researchRequestNote} onChange={(event) => setResearchRequestNote(event.target.value)} maxLength={2000} />
                  </label>
                  {researchDetail.runs.length ? (
                    <div className="flex flex-wrap gap-2">
                      <Button disabled={researchBusy || Boolean(researchChannelJob) || researchDetail.project.status === "archived"} onClick={() => openResearchRunDialog(researchDetail.project, "expand_candidates")}>
                        <Plus /> 补充候选产品
                      </Button>
                      <Button variant="outline" className="bg-white" disabled={researchBusy || Boolean(researchChannelJob) || researchDetail.project.status === "archived"} onClick={() => openResearchRunDialog(researchDetail.project, "review")}>
                        <Bot /> 复查更新
                      </Button>
                    </div>
                  ) : (
                    <Button disabled={researchBusy || Boolean(researchChannelJob) || researchDetail.project.status === "archived"} onClick={() => openResearchRunDialog(researchDetail.project, "expand_candidates")}>
                      <Bot /> 开始首轮 AI 调研
                    </Button>
                  )}
                </div>
                <p className="mt-2 text-xs leading-5 text-cyan-900/70">使用独立“项目调研”通道；每次执行都会新增一个版本，且不影响关键词、单产品或图片任务。</p>
              </div>

              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                {[
                  ["合规安全", researchScorecard.complianceSafety, 25],
                  ["市场买家", researchScorecard.marketBuyer, 20],
                  ["单位经济", researchScorecard.unitEconomics, 20],
                  ["供应稳定", researchScorecard.supplyStability, 20],
                  ["销售表达", researchScorecard.salesExpression, 15],
                  ["总分", researchScorecard.total, 100],
                ].map(([label, value, max]) => (
                  <div key={String(label)} className="rounded-xl border bg-slate-50 p-3">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="mt-1 text-xl font-semibold tabular-nums">{value == null ? "—" : String(value)}<span className="text-xs font-normal text-muted-foreground"> / {max}</span></p>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  ["赛道大类", researchTracks.length, `当前覆盖 ${researchTracks.length} 个`],
                  ["细分领域", new Set(researchCandidates.map((item) => item.subcategory).filter(Boolean)).size, "来自当前候选产品"],
                  ["候选产品池", researchCandidates.length, `目标 ${researchDetail.project.target_candidate_count.toLocaleString("zh-CN")} · 待补 ${Math.max(0, researchDetail.project.target_candidate_count - researchCandidates.length).toLocaleString("zh-CN")}`],
                  ["对应市场", researchMarketsReport.length, `已覆盖 ${researchMarketsReport.length} 个国家/地区`],
                ].map(([label, value, note]) => (
                  <div key={String(label)} className="rounded-xl border border-cyan-100 bg-cyan-50/50 p-3">
                    <p className="text-xs text-cyan-900/65">{label}</p>
                    <p className="mt-1 text-2xl font-semibold tabular-nums text-cyan-950">{value}</p>
                    <p className="mt-1 text-[11px] text-cyan-900/55">{note}</p>
                  </div>
                ))}
              </div>

              <Tabs value={researchDetailTab} onValueChange={selectResearchDetailTab}>
                <TabsList className="grid h-auto w-full grid-cols-3 sm:grid-cols-9">
                  <TabsTrigger value="summary">启动方案</TabsTrigger>
                  <TabsTrigger value="buyers">买家画像</TabsTrigger>
                  <TabsTrigger value="tracks">赛道大类</TabsTrigger>
                  <TabsTrigger value="pool">产品池</TabsTrigger>
                  <TabsTrigger value="selection">选品准入</TabsTrigger>
                  <TabsTrigger value="markets">对应市场</TabsTrigger>
                  <TabsTrigger value="sections">研究章节</TabsTrigger>
                  <TabsTrigger value="evidence">来源证据</TabsTrigger>
                  <TabsTrigger value="versions">历史版本</TabsTrigger>
                </TabsList>
                <TabsContent value="summary" className="mt-4 space-y-4">
                  <div className="rounded-xl border p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="font-medium">在线外贸启动方案</h3>
                        <p className="mt-1 text-xs text-muted-foreground">每轮 AI 调研形成新版本；当前页面始终展示最新方案，旧版和来源可追溯。</p>
                      </div>
                      <Badge variant="outline">{RESEARCH_RECOMMENDATION_LABELS[researchDetail.project.recommendation] ?? researchDetail.project.recommendation}</Badge>
                    </div>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">{researchDetail.project.summary || "尚未完成首轮调研。项目范围已保存，可随时交给 Codex / ChatGPT 执行。"}</p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border p-4">
                      <h3 className="font-medium">主要风险</h3>
                      <ul className="mt-3 space-y-2 text-sm text-slate-700">
                        {(Array.isArray(researchLatestReport.risks) ? researchLatestReport.risks : []).map((item, index) => <li key={index}>• {String(item)}</li>)}
                        {!Array.isArray(researchLatestReport.risks) && <li className="text-muted-foreground">等待首轮调研</li>}
                      </ul>
                    </div>
                    <div className="rounded-xl border p-4">
                      <h3 className="font-medium">下一步行动</h3>
                      <ol className="mt-3 space-y-2 text-sm text-slate-700">
                        {(Array.isArray(researchLatestReport.actionPlan) ? researchLatestReport.actionPlan : []).map((item, index) => <li key={index}>{index + 1}. {String(item)}</li>)}
                        {!Array.isArray(researchLatestReport.actionPlan) && <li className="text-muted-foreground">等待首轮调研</li>}
                      </ol>
                    </div>
                  </div>
                  <div className="rounded-xl border p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="font-medium">持续维护的 11 个模块</h3>
                        <p className="mt-1 text-xs text-muted-foreground">赛道、产品、市场和人工筛选状态长期保存；每轮 AI 只增量补充、复查和形成新版本。</p>
                      </div>
                      <Badge variant="outline">在线文档</Badge>
                    </div>
                    <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {RESEARCH_PLAYBOOK_META.map(([key, label, note]) => {
                        const hasStructuredData = ["trackMap", "candidatePool", "marketMapping", "screening"].includes(key)
                          ? (key === "trackMap" ? researchTracks.length > 0 : key === "candidatePool" || key === "screening" ? researchCandidates.length > 0 : researchMarketsReport.length > 0)
                          : Boolean(researchPlaybook[key]?.summary || valueList(researchPlaybook[key]?.items).length);
                        return (
                          <div key={key} className="rounded-lg border bg-slate-50/70 p-3">
                            <div className="flex items-center justify-between gap-2">
                              <p className="text-sm font-medium">{label}</p>
                              <span className={`size-2 rounded-full ${hasStructuredData ? "bg-emerald-500" : "bg-slate-300"}`} aria-label={hasStructuredData ? "已有内容" : "待补充"} />
                            </div>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">{note}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {RESEARCH_PLAYBOOK_META.slice(5).map(([key, label, note]) => {
                      const section = researchPlaybook[key] ?? {};
                      const items = valueList(section.items);
                      return (
                        <div key={key} className="rounded-xl border p-4">
                          <h3 className="font-medium">{label}</h3>
                          <p className="mt-1 text-xs text-muted-foreground">{note}</p>
                          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700">{String(section.summary ?? "下一轮 AI 调研会补充本模块，并在后续版本持续更新。")}</p>
                          {items.length > 0 && <ol className="mt-3 space-y-1 text-sm text-slate-700">{items.map((item, index) => <li key={index}>{index + 1}. {item}</li>)}</ol>}
                        </div>
                      );
                    })}
                  </div>
                </TabsContent>
                <TabsContent value="buyers" className="mt-4 space-y-4">
                  <div className="rounded-xl border border-cyan-200 bg-cyan-50/60 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-medium text-cyan-950">买家先行：围绕持续采购场景组织产品</h3>
                        <p className="mt-1 text-xs leading-5 text-cyan-900/75">真实批发买家 → 买家画像 → 销售/采购场景 → 产品家族矩阵 → 单一候选产品。没有公司和直接来源的泛化类型，不算真实买家。</p>
                      </div>
                      <div className="flex flex-wrap gap-2"><Button variant="outline" className="bg-white" disabled={researchBusy || Boolean(researchChannelJob)} onClick={openRealBuyerResearch}><Bot /> AI 调研真实买家</Button><Button onClick={openNewResearchBuyer}><Plus /> 新增真实买家</Button></div>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-4">
                      {[
                        ["真实买家画像", researchBuyerProfiles.length, "必须有公司、国家和公开来源"],
                        ["已初筛", researchQualifiedBuyers.length, "公开业务与采购场景基本匹配"],
                        ["人工已验证", researchValidatedBuyers.length, "需人工接触或一手证据确认"],
                        ["已关联家族", researchLinkedFamilyKeys.size, `共 ${researchBuyerFamilyLinks.length} 条买家—家族关系`],
                      ].map(([label, value, note]) => <div key={String(label)} className="rounded-lg border border-cyan-100 bg-white p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p><p className="mt-1 text-[10px] leading-4 text-muted-foreground">{note}</p></div>)}
                    </div>
                  </div>

                  <div className="grid gap-4 lg:grid-cols-2">
                    {researchBuyerProfiles.map((buyer) => {
                      const links = researchBuyerFamilyLinks.filter((link) => link.buyer_profile_id === buyer.id);
                      const linkedCandidates = researchCandidates.filter((candidate) => links.some((link) => link.track_category === candidate.track_category && link.product_family === candidate.product_family));
                      return <div key={buyer.id} className="rounded-xl border p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{buyer.company_name}</h3><Badge variant={buyer.profile_status === "validated" ? "default" : "outline"}>{RESEARCH_BUYER_STATUS_LABELS[buyer.profile_status]}</Badge>{buyer.created_by === "ai" && <Badge variant="secondary"><Bot /> AI发现</Badge>}</div><p className="mt-1 text-xs text-muted-foreground">{buyer.country} · {buyer.buyer_type}{buyer.odoo_lead_id ? ` · Odoo CRM #${buyer.odoo_lead_id}` : ""}</p></div>
                          <div className="flex shrink-0 gap-1"><Button size="sm" variant="outline" onClick={() => openEditResearchBuyer(buyer)}>编辑画像</Button><Button size="sm" onClick={() => openResearchBuyerMatrix(buyer)}>家族矩阵</Button></div>
                        </div>
                        <dl className="mt-3 grid gap-x-3 gap-y-2 text-xs leading-5 sm:grid-cols-[84px_1fr]">
                          <dt className="text-muted-foreground">终端客群</dt><dd>{buyer.customer_groups.join("、") || "待补充"}</dd>
                          <dt className="text-muted-foreground">销售渠道</dt><dd>{buyer.sales_channels.join("、") || "待补充"}</dd>
                          <dt className="text-muted-foreground">采购场景</dt><dd>{buyer.purchasing_scenarios.join("、") || "待补充"}</dd>
                          <dt className="text-muted-foreground">季节特点</dt><dd>{buyer.seasonality || "待补充"}</dd>
                          <dt className="text-muted-foreground">补货周期</dt><dd>{buyer.replenishment_cycle || "待补充"}</dd>
                          <dt className="text-muted-foreground">订单要求</dt><dd>{buyer.order_requirements || "待补充"}</dd>
                        </dl>
                        <div className="mt-3 rounded-lg bg-slate-50 p-3"><div className="flex items-center justify-between gap-2"><p className="text-xs font-medium">产品家族矩阵</p><span className="text-[11px] text-muted-foreground">{links.length} 个家族 · {linkedCandidates.length} 个候选单品</span></div><div className="mt-2 flex flex-wrap gap-1">{links.slice(0, 8).map((link) => <Badge key={link.id} variant={link.family_role === "core" ? "default" : "secondary"} className="text-[10px]">{RESEARCH_FAMILY_ROLE_LABELS[link.family_role]} · {link.product_family} · {link.relationship_score}</Badge>)}{!links.length && <span className="text-xs text-muted-foreground">尚未建立关系，先配置该买家的核心常采与跨品类加购家族。</span>}</div></div>
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs"><a className="inline-flex items-center gap-1 text-cyan-800 underline" href={buyer.source_url} target="_blank" rel="noreferrer">查看买家来源 <ExternalLink className="size-3" /></a><span className="text-muted-foreground">{buyer.website ? "官网已记录" : "官网待补充"} · 更新于 {relativeTime(buyer.updated_at)}</span></div>
                      </div>;
                    })}
                  </div>
                  {!researchBuyerProfiles.length && <div className="rounded-xl border border-dashed p-12 text-center"><p className="font-medium">还没有真实批发买家画像</p><p className="mt-2 text-sm text-muted-foreground">点击“AI 调研真实买家”从公开来源建立待核实画像，或手动录入你已经接触的买家公司。</p><div className="mt-4 flex justify-center gap-2"><Button variant="outline" onClick={openRealBuyerResearch}><Bot /> AI 调研</Button><Button onClick={openNewResearchBuyer}><Plus /> 手动新增</Button></div></div>}
                </TabsContent>
                <TabsContent value="tracks" className="mt-4 space-y-3">
                  <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border bg-slate-50/70 p-4">
                    <div>
                      <h3 className="font-medium">大赛道地图</h3>
                      <p className="mt-1 text-xs text-muted-foreground">按大类 → 细分领域 → 产品 → 市场逐层展开；优先级和证据状态会随复查更新。</p>
                    </div>
                    <Badge variant="outline">已覆盖 {researchTracks.length} 个赛道</Badge>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {researchTracks.map((track, index) => {
                      const name = String(track.name ?? `赛道 ${index + 1}`);
                      const subcategories = valueList(track.subcategories);
                      const targetMarkets = valueList(track.targetMarkets);
                      const buyerTypes = valueList(track.buyerTypes);
                      const productCount = researchCandidates.filter((item) => item.track_category === name).length;
                      return (
                        <button
                          key={String(track.id ?? `${name}-${index}`)}
                          type="button"
                          className="group rounded-xl border p-4 text-left transition-colors hover:border-cyan-300 hover:bg-cyan-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-600"
                          onClick={() => {
                            setResearchPoolSearch("");
                            setResearchPoolBuyerTypes([]);
                            setResearchPoolConditions("");
                            setResearchPoolTracks([name]);
                            setResearchPoolMarkets([]);
                            setResearchPoolRisks([]);
                            setResearchPoolStages([]);
                            setResearchPoolPage(1);
                            selectResearchDetailTab("pool");
                          }}
                          aria-label={`查看${name}的${productCount}个候选产品`}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <h3 className="font-medium">{name}</h3>
                              <p className="mt-1 text-xs text-muted-foreground">{productCount} 个候选产品 · {subcategories.length} 个细分领域 · 点击查看</p>
                            </div>
                            <div className="flex items-center gap-1">
                              <Badge variant="outline">{String(track.priority ?? "medium") === "high" ? "高优先" : String(track.priority ?? "medium") === "low" ? "低优先" : "中优先"}</Badge>
                              <Badge variant="secondary">{RESEARCH_VALIDATION_LABELS[String(track.evidenceStatus)] ?? "待验证假设"}</Badge>
                              <ChevronRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                            </div>
                          </div>
                          <p className="mt-3 text-sm leading-6 text-slate-700">{String(track.description ?? "暂无赛道说明")}</p>
                          {subcategories.length > 0 && <div className="mt-3 flex flex-wrap gap-1">{subcategories.map((item) => <Badge key={item} variant="outline">{item}</Badge>)}</div>}
                          {targetMarkets.length > 0 && <p className="mt-3 text-xs leading-5 text-muted-foreground">对应市场：{targetMarkets.map(researchMarketLabel).join("、")}</p>}
                          {buyerTypes.length > 0 && <p className="mt-1 text-xs leading-5 text-muted-foreground">典型买家：{buyerTypes.join("、")}</p>}
                        </button>
                      );
                    })}
                  </div>
                  {!researchTracks.length && <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">当前版本还没有结构化赛道。点击“补充候选产品”后，AI 会按产品、赛道、细分领域和国家市场写回。</div>}
                </TabsContent>
                <TabsContent value="pool" className="mt-4 space-y-3">
                  <div className="rounded-xl border p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-medium">{researchDetail.project.target_candidate_count.toLocaleString("zh-CN")} 个候选产品池</h3>
                        <p className="mt-1 text-xs text-muted-foreground">AI 分批扩充并自动去重；你的重点、验证、样品和排除状态不会被后续 AI 覆盖。</p>
                      </div>
                      <div className="min-w-52">
                        <div className="mb-1 flex justify-between text-xs"><span>{researchCandidates.length} / {researchDetail.project.target_candidate_count}</span><span>{Math.min(100, Math.round(researchCandidates.length / researchDetail.project.target_candidate_count * 100))}%</span></div>
                        <Progress value={Math.min(100, researchCandidates.length / researchDetail.project.target_candidate_count * 100)} className="h-2" />
                        <div className="mt-2 grid grid-cols-2 gap-2">
                          <Button size="sm" disabled={researchBusy || Boolean(researchChannelJob) || researchDetail.project.status === "archived"} onClick={() => openResearchRunDialog(researchDetail.project, "expand_candidates")}><Plus /> 补充产品</Button>
                          <Button size="sm" variant="outline" disabled={researchImageAssistBusy || Boolean(candidateImagesChannelJob) || researchDetail.project.status === "archived"} onClick={() => void dispatchCandidateImageAssist()}><ImageIcon /> {researchImageAssistBusy ? "发送中…" : candidateImagesChannelJob ? "图片通道忙碌" : "AI补本页图片"}</Button>
                        </div>
                        <p className="mt-1 text-[10px] text-muted-foreground">已有图片 {researchCandidates.filter((item) => item.image_urls.some(isSafeSourceUrl)).length} / {researchCandidates.length}；接受商品页原图或带落地链接的匹配搜索缩略图。</p>
                      </div>
                    </div>
                    <div className="mt-4 rounded-lg border bg-slate-50/70 p-3">
                      <p className="text-xs font-medium">产品推进顺序</p>
                      <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                        {(["idea", "research", "shortlist", "sample", "validation", "validated"] as const).map((stage, index) => (
                          <div key={stage} className="flex items-center gap-1">
                            {index > 0 && <ChevronRight className="size-3" aria-hidden="true" />}
                            <Badge variant="outline" className="bg-white">{RESEARCH_CANDIDATE_STAGE_LABELS[stage]}</Badge>
                            <span>{RESEARCH_CANDIDATE_NEXT_ACTIONS[stage]}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="mt-4 rounded-xl border bg-slate-50/70 p-3 sm:p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="flex size-8 items-center justify-center rounded-lg border bg-white text-cyan-700"><ListFilter className="size-4" aria-hidden="true" /></span>
                          <div><p className="text-sm font-medium">筛选候选产品</p><p className="text-[11px] text-muted-foreground">产品信息与采购条件分开筛选，结果更准确</p></div>
                        </div>
                        <Badge variant={activeResearchPoolFilterCount ? "default" : "secondary"}>{activeResearchPoolFilterCount ? `${activeResearchPoolFilterCount} 个自定义条件` : "默认显示未排除产品"}</Badge>
                      </div>
                      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(180px,1.2fr)_minmax(180px,1.2fr)_repeat(5,minmax(135px,0.8fr))]">
                        <label className="space-y-1.5">
                          <span className="text-xs font-medium text-slate-600">产品关键词</span>
                          <span className="relative block"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" /><Input className="bg-white pl-9" value={researchPoolSearch} onChange={(event) => { setResearchPoolSearch(event.target.value); setResearchPoolPage(1); }} placeholder="名称、赛道或细分领域" /></span>
                        </label>
                        <label className="space-y-1.5">
                          <span className="text-xs font-medium text-slate-600">采购条件</span>
                          <span className="relative block"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" /><Input className="bg-white pl-9" value={researchPoolConditions} onChange={(event) => { setResearchPoolConditions(event.target.value); setResearchPoolPage(1); }} placeholder="价格、MOQ 或合规" /></span>
                        </label>
                        <div className="space-y-1.5"><p className="text-xs font-medium text-slate-600">买家类型</p><ResearchFilterMultiSelect value={researchPoolBuyerTypes} onValueChange={(value) => { setResearchPoolBuyerTypes(value); setResearchPoolPage(1); }} options={researchBuyerTypeOptions.map((item) => ({ value: item, label: item }))} allLabel="全部买家类型" searchPlaceholder="搜索买家类型" ariaLabel="产品池买家类型筛选" /></div>
                        <div className="space-y-1.5"><p className="text-xs font-medium text-slate-600">赛道</p><ResearchFilterMultiSelect value={researchPoolTracks} onValueChange={(value) => { setResearchPoolTracks(value); setResearchPoolPage(1); }} options={researchTrackOptions.map((item) => ({ value: item, label: item }))} allLabel="全部赛道" searchPlaceholder="搜索赛道" ariaLabel="产品池赛道筛选" /></div>
                        <div className="space-y-1.5"><p className="text-xs font-medium text-slate-600">市场</p><ResearchFilterMultiSelect value={researchPoolMarkets} onValueChange={(value) => { setResearchPoolMarkets(value); setResearchPoolPage(1); }} options={researchMarketOptions.map((item) => ({ value: item, label: researchMarketLabel(item), searchText: item }))} allLabel="全部市场" searchPlaceholder="搜索国家或代码" ariaLabel="产品池市场筛选" /></div>
                        <div className="space-y-1.5"><p className="text-xs font-medium text-slate-600">风险</p><ResearchFilterMultiSelect value={researchPoolRisks} onValueChange={(value) => { setResearchPoolRisks(value); setResearchPoolPage(1); }} options={Object.entries(RESEARCH_RISK_LABELS).map(([value, label]) => ({ value, label: `${label}风险` }))} allLabel="全部风险" searchPlaceholder="搜索风险" ariaLabel="产品池风险筛选" /></div>
                        <div className="space-y-1.5"><p className="text-xs font-medium text-slate-600">阶段</p><ResearchFilterMultiSelect value={researchPoolStages} onValueChange={(value) => { setResearchPoolStages(value); setResearchPoolPage(1); }} options={[{ value: "active", label: "未排除产品" }, ...Object.entries(RESEARCH_CANDIDATE_STAGE_LABELS).map(([value, label]) => ({ value, label }))]} allLabel="全部阶段" searchPlaceholder="搜索阶段" ariaLabel="产品池阶段筛选" exclusiveValues={["active"]} /></div>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                        <p className="text-xs text-muted-foreground">找到 <span className="font-semibold text-slate-800">{filteredResearchCandidates.length}</span> 个 · 第 {currentResearchPoolPage} / {researchPoolTotalPages} 页 · 每页 25 个</p>
                        <Button size="sm" variant="ghost" disabled={!activeResearchPoolFilterCount} onClick={() => { setResearchPoolSearch(""); setResearchPoolBuyerTypes([]); setResearchPoolConditions(""); setResearchPoolTracks([]); setResearchPoolMarkets([]); setResearchPoolRisks([]); setResearchPoolStages(["active"]); setResearchPoolPage(1); }}>重置筛选</Button>
                      </div>
                    </div>
                  </div>
                  <div className="overflow-hidden rounded-xl border [&_[data-slot=table-container]]:overflow-x-auto lg:[&_[data-slot=table-container]]:overflow-x-hidden">
                    <Table className="min-w-[860px] table-fixed text-xs lg:min-w-0">
                      <colgroup>
                        <col className="w-[27%]" />
                        <col className="w-[12%]" />
                        <col className="w-[14%]" />
                        <col className="w-[27%]" />
                        <col className="w-[6%]" />
                        <col className="w-[11%]" />
                        <col className="w-[3%]" />
                      </colgroup>
                      <TableHeader><TableRow className="bg-slate-50/70"><TableHead className="h-9 px-2">候选产品</TableHead><TableHead className="h-9 px-2">赛道 / 细分</TableHead><TableHead className="h-9 px-2">对应市场</TableHead><TableHead className="h-9 px-2">买家 / 条件</TableHead><TableHead className="h-9 px-1 text-center">风险</TableHead><TableHead className="h-9 px-1">阶段</TableHead><TableHead className="h-9 px-1 text-right">评分</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {pagedResearchCandidates.map((candidate) => {
                          const persistedCandidate = researchDetail.candidates.some((item) => item.id === candidate.id);
                          const buyerSummary = candidate.buyer_types.join("、") || "买家待判断";
                          const conditionSummary = `${candidate.price_band || "价格待验证"}${candidate.moq ? ` · MOQ ${candidate.moq}` : ""}`;
                          const candidateImages: ApiProductImage[] = candidate.image_urls.filter(isSafeSourceUrl).map((url) => ({
                            url,
                            platform: "产品调研",
                            source_ref: candidate.image_source_ref,
                            verified_source: isSafeSourceUrl(candidate.image_source_ref),
                          }));
                          return (
                            <TableRow key={candidate.id} className="align-top">
                              <TableCell className="overflow-hidden px-2 py-2 whitespace-normal">
                                <div className="flex min-w-0 gap-2">
                                  <div className="shrink-0"><ProductImages images={candidateImages} alt={`${candidate.name}产品图`} onPreview={(index) => candidateImages.length && setImagePreview({ images: candidateImages, index, alt: `${candidate.name}产品图` })} /></div>
                                  <div className="min-w-0 flex-1">
                                    <p className="truncate font-medium" title={candidate.name}>{candidate.name}</p>
                                    {candidate.commercial_variant && <p className="mt-0.5 truncate text-[11px] text-muted-foreground" title={candidate.commercial_variant}>{candidate.commercial_variant}</p>}
                                    {candidate.rationale && <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-muted-foreground" title={candidate.rationale}>{candidate.rationale}</p>}
                                  </div>
                                </div>
                              </TableCell>
                              <TableCell className="overflow-hidden px-2 py-2 whitespace-normal"><p className="truncate" title={candidate.track_category || "未分类"}>{candidate.track_category || "未分类"}</p><p className="mt-0.5 truncate text-[11px] text-muted-foreground" title={candidate.product_family || candidate.subcategory || "未归组"}>家族：{candidate.product_family || candidate.subcategory || "未归组"}</p></TableCell>
                              <TableCell className="px-2 py-2 whitespace-normal"><div className="flex flex-wrap gap-1">{candidate.target_markets.map((item) => <Badge key={item} variant="outline" className="h-5 px-1.5 text-[10px]">{researchMarketLabel(item)}</Badge>)}</div></TableCell>
                              <TableCell className="overflow-hidden px-2 py-2 whitespace-normal"><p className="truncate leading-4" title={buyerSummary}>{buyerSummary}</p><p className="mt-0.5 truncate text-[11px] leading-4 text-muted-foreground" title={conditionSummary}>{conditionSummary}</p></TableCell>
                              <TableCell className="px-1 py-2 text-center whitespace-normal"><Badge variant="outline" className="h-5 px-1.5 text-[10px]">{RESEARCH_RISK_LABELS[candidate.risk_level] ?? candidate.risk_level}</Badge></TableCell>
                              <TableCell className="px-1 py-2 whitespace-normal">
                                <Badge variant="secondary" className="h-6 px-2 text-[10px]">{RESEARCH_CANDIDATE_STAGE_LABELS[candidate.stage]}</Badge>
                                <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted-foreground" title={RESEARCH_CANDIDATE_NEXT_ACTIONS[candidate.stage]}>{RESEARCH_CANDIDATE_NEXT_ACTIONS[candidate.stage]}</p>
                                <div className="mt-1 flex flex-wrap gap-1"><Button className="h-6 px-1.5 text-[10px]" size="sm" variant="outline" disabled={researchBusy || !persistedCandidate} onClick={() => openResearchCandidateAction(candidate)}><CalendarClock /> 推进</Button><Button className="h-6 px-1.5 text-[10px]" size="sm" variant={candidate.handoff_readiness.ready ? "default" : "outline"} disabled={!persistedCandidate} onClick={() => openResearchSelection(candidate)}><Target /> 评估</Button></div>
                              </TableCell>
                              <TableCell className="px-1 py-2 text-right font-semibold whitespace-normal tabular-nums">{candidate.score ?? "—"}</TableCell>
                            </TableRow>
                          );
                        })}
                        {!pagedResearchCandidates.length && <TableRow><TableCell colSpan={7} className="h-32 text-center text-muted-foreground">暂无符合条件的候选产品。下一轮 AI 调研会按赛道和市场分批扩充产品池。</TableCell></TableRow>}
                      </TableBody>
                    </Table>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs text-muted-foreground">产品池为候选假设，不等于已验证需求；进入重点候选前需补足市场、利润和合规证据。</p>
                    <div className="flex gap-2"><Button variant="outline" size="sm" disabled={currentResearchPoolPage <= 1} onClick={() => setResearchPoolPage((page) => Math.max(1, page - 1))}><ChevronLeft /> 上一页</Button><Button variant="outline" size="sm" disabled={currentResearchPoolPage >= researchPoolTotalPages} onClick={() => setResearchPoolPage((page) => Math.min(researchPoolTotalPages, page + 1))}>下一页 <ChevronRight /></Button></div>
                  </div>
                </TabsContent>
                <TabsContent value="selection" className="mt-4 space-y-4">
                  <div className="rounded-xl border border-cyan-200 bg-cyan-50/60 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-medium text-cyan-950">标准选品与 Odoo 移交流程</h3>
                        <p className="mt-1 text-xs leading-5 text-cyan-900/75">大赛道 → 细分领域 → 产品家族 → 候选款式 → 人工评分与硬门槛 → Odoo 产品建档。这里的“可移交”不等于可发布。</p>
                      </div>
                      <Badge variant="outline" className="border-cyan-300 bg-white">规则版本 v1 · 70 分门槛</Badge>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-4">
                      {[
                        ["产品家族", researchProductFamilies.length, "复用买家、渠道与供应链判断"],
                        ["已完成人工评估", researchAssessedCandidates.length, `共 ${researchCandidates.length} 个候选`],
                        ["达到移交门槛", researchOdooReadyCandidates.length, "评分、字段和五项硬门槛均通过"],
                        ["真实买家", researchBuyerProfiles.length, `已建立 ${researchBuyerFamilyLinks.length} 条买家—家族关系`],
                      ].map(([label, value, note]) => (
                        <div key={String(label)} className="rounded-lg border border-cyan-100 bg-white p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p><p className="mt-1 text-[10px] leading-4 text-muted-foreground">{note}</p></div>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="rounded-xl border p-4">
                      <div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">产品家族地图</h3><p className="mt-1 text-xs text-muted-foreground">同一家族共享需求、买家、渠道、供应商与合规研究，单品只记录差异。</p></div><Badge variant="secondary">{researchProductFamilies.length} 个</Badge></div>
                      <div className="mt-3 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                        {researchProductFamilies.map((family) => (
                          <div key={family.key} className="rounded-lg border bg-slate-50/60 p-3">
                            <div className="flex items-start justify-between gap-2"><div><p className="font-medium">{family.name}</p><p className="mt-0.5 text-[11px] text-muted-foreground">{family.track} / {family.subcategory}</p></div><Badge variant="outline">{family.candidateCount} 款</Badge></div>
                            <p className="mt-2 line-clamp-2 text-xs text-slate-600">买家：{family.buyerTypes.join("、") || "待定义"}</p>
                            <p className="mt-1 text-[11px] text-muted-foreground">市场：{family.markets.map(researchMarketLabel).join("、") || "待验证"}</p>
                          </div>
                        ))}
                        {!researchProductFamilies.length && <p className="py-10 text-center text-sm text-muted-foreground">还没有可归组的候选产品。</p>}
                      </div>
                    </div>

                    <div className="rounded-xl border p-4">
                      <div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">真实买家—产品家族矩阵</h3><p className="mt-1 text-xs text-muted-foreground">只展示已建立公司画像和公开来源的买家；关系分用于排序验证，不代表真实采购额。</p></div><Button size="sm" variant="outline" onClick={() => selectResearchDetailTab("buyers")}>维护买家画像</Button></div>
                      <div className="mt-3 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                        {researchBuyerProfiles.slice(0, 50).map((buyer) => {
                          const links = researchBuyerFamilyLinks.filter((link) => link.buyer_profile_id === buyer.id);
                          const candidateCount = researchCandidates.filter((candidate) => links.some((link) => link.track_category === candidate.track_category && link.product_family === candidate.product_family)).length;
                          return <div key={buyer.id} className="rounded-lg border p-3">
                            <div className="flex items-start justify-between gap-3"><div><p className="font-medium">{buyer.company_name}</p><p className="mt-0.5 text-[11px] text-muted-foreground">{buyer.country} · {buyer.buyer_type} · {links.length} 个家族 · {candidateCount} 个候选单品</p></div><Badge variant={buyer.profile_status === "validated" ? "default" : "outline"}>{RESEARCH_BUYER_STATUS_LABELS[buyer.profile_status]}</Badge></div>
                            <div className="mt-2 flex flex-wrap gap-1">{links.slice(0, 8).map((link) => <Badge key={link.id} variant={link.family_role === "core" ? "default" : "secondary"} className="text-[10px]">{RESEARCH_FAMILY_ROLE_LABELS[link.family_role]} · {link.product_family} · {link.relationship_score}</Badge>)}</div>
                            <p className="mt-2 line-clamp-2 text-[11px] text-muted-foreground">采购场景：{buyer.purchasing_scenarios.join("、") || "待补充"}</p>
                          </div>;
                        })}
                        {!researchBuyerProfiles.length && <div className="py-10 text-center"><p className="text-sm text-muted-foreground">尚未建立真实买家画像，不再从候选产品虚构买家关系。</p><Button className="mt-3" size="sm" onClick={() => selectResearchDetailTab("buyers")}>去建立买家画像</Button></div>}
                      </div>
                    </div>
                  </div>

                  <div className="overflow-hidden rounded-xl border">
                    <div className="flex flex-wrap items-start justify-between gap-2 border-b bg-slate-50/70 p-4"><div><h3 className="font-medium">候选准入队列</h3><p className="mt-1 text-xs text-muted-foreground">100 分选品卡 + 3 个渠道适配分 + 5 项硬门槛；未通过时导出按钮会显示具体阻塞项。</p></div><Badge variant="outline">显示前 50 个</Badge></div>
                    <Table className="text-xs">
                      <TableHeader><TableRow><TableHead>候选产品 / 家族</TableHead><TableHead>人工决策</TableHead><TableHead>选品分</TableHead><TableHead>Odoo 移交</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {[...researchCandidates].sort((a, b) => Number(b.handoff_readiness.ready) - Number(a.handoff_readiness.ready) || b.handoff_readiness.score - a.handoff_readiness.score).slice(0, 50).map((candidate) => (
                          <TableRow key={candidate.id}>
                            <TableCell><p className="font-medium">{candidate.name}</p><p className="mt-0.5 text-[11px] text-muted-foreground">{candidate.track_category || "未分类"} / {candidate.product_family || candidate.subcategory || "未归组"}</p></TableCell>
                            <TableCell><Badge variant="outline">{{ unreviewed: "未评估", research: "继续调研", shortlist: "进入短名单", ready: "可移交", blocked: "暂停" }[candidate.selection_assessment.decision]}</Badge></TableCell>
                            <TableCell className="font-semibold tabular-nums">{candidate.selection_assessment.decision === "unreviewed" ? "—" : `${candidate.handoff_readiness.score}/100`}</TableCell>
                            <TableCell>{candidate.handoff_readiness.ready ? <Badge className="bg-emerald-700">可移交，非可发布</Badge> : <p className="max-w-64 line-clamp-2 text-[11px] text-muted-foreground" title={candidate.handoff_readiness.blockers.join("；")}>{candidate.handoff_readiness.blockers.slice(0, 2).join("；")}</p>}</TableCell>
                            <TableCell><div className="flex justify-end gap-1"><Button size="sm" variant="outline" onClick={() => openResearchSelection(candidate)}><Target /> 评估</Button><Button size="sm" disabled={!candidate.handoff_readiness.ready} onClick={() => exportResearchCandidateToOdoo(candidate)}><Download /> Odoo 包</Button></div></TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </TabsContent>
                <TabsContent value="markets" className="mt-4 space-y-3">
                  <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border bg-slate-50/70 p-4">
                    <div>
                      <h3 className="font-medium">产品与需求市场映射</h3>
                      <p className="mt-1 text-xs text-muted-foreground">从“哪个国家最好”改为验证“这个国家的哪些买家，为什么愿意为哪些产品付费”。</p>
                      <p className="mt-2 text-xs text-cyan-800">操作：打开“处理验证” → 记录真实买家/价格/合规证据 → 先设为验证中；证据充分后再标记已验证或已否定。</p>
                    </div>
                    <Badge variant="outline">{researchMarketsReport.length} 个市场假设</Badge>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {researchMarketsReport.map((marketItem, index) => {
                      const marketCode = String(marketItem.marketCode ?? "");
                      const marketName = String(marketItem.marketName ?? "") || researchMarketLabel(marketCode);
                      const buyerTypes = valueList(marketItem.buyerTypes);
                      const complianceFocus = valueList(marketItem.complianceFocus);
                      const recommendedTracks = valueList(marketItem.recommendedTracks);
                      const linkedProducts = researchCandidates.filter((item) => item.target_markets.includes(marketCode)).length;
                      const currentStatus = researchMarketStatus(marketItem);
                      return (
                        <div key={`${marketCode}-${index}`} className="rounded-xl border p-4">
                          <div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">{marketName}{marketCode && !marketName.includes(marketCode) ? `（${marketCode}）` : ""}</h3><p className="mt-1 text-xs text-muted-foreground">关联 {linkedProducts} 个候选产品</p></div><div className="flex flex-wrap justify-end gap-2"><Badge variant="secondary">{RESEARCH_VALIDATION_LABELS[currentStatus]}</Badge><Button size="sm" variant="outline" onClick={() => openResearchMarketAction(marketItem)}>处理验证</Button></div></div>
                          <p className="mt-3 text-sm leading-6 text-slate-700">{String(marketItem.demandHypothesis ?? "暂无需求假设")}</p>
                          <dl className="mt-3 grid gap-2 text-xs leading-5 sm:grid-cols-[72px_1fr]">
                            <dt className="text-muted-foreground">典型买家</dt><dd>{buyerTypes.join("、") || "待判断"}</dd>
                            <dt className="text-muted-foreground">进入方式</dt><dd>{String(marketItem.entryMode ?? "待判断")}</dd>
                            <dt className="text-muted-foreground">合规重点</dt><dd>{complianceFocus.join("、") || "待判断"}</dd>
                            <dt className="text-muted-foreground">推荐赛道</dt><dd>{recommendedTracks.join("、") || "待判断"}</dd>
                          </dl>
                        </div>
                      );
                    })}
                  </div>
                  {!researchMarketsReport.length && <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">当前版本还没有结构化市场假设。下一轮 AI 调研会按具体国家、买家类型、进入方式和合规重点补齐。</div>}
                </TabsContent>
                <TabsContent value="sections" className="mt-4 space-y-3">
                  {RESEARCH_STAGE_META.map(([key, label, note], index) => {
                    const section = researchReportSections[key] ?? {};
                    const findings = Array.isArray(section.findings) ? section.findings : [];
                    const unknowns = Array.isArray(section.unknowns) ? section.unknowns : [];
                    return (
                      <div key={key} className="rounded-xl border p-4">
                        <div className="flex items-start gap-3">
                          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-cyan-100 text-xs font-semibold text-cyan-800">{index + 1}</span>
                          <div className="min-w-0">
                            <h3 className="font-medium">{label}</h3>
                            <p className="mt-1 text-xs text-muted-foreground">{note}</p>
                            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700">{String(section.summary ?? "暂无本章节结论")}</p>
                            {findings.length > 0 && <ul className="mt-3 space-y-1 text-sm text-slate-700">{findings.map((item, itemIndex) => <li key={itemIndex}>• {String(item)}</li>)}</ul>}
                            {unknowns.length > 0 && <p className="mt-3 text-xs text-amber-700">待补证据：{unknowns.map(String).join("；")}</p>}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </TabsContent>
                <TabsContent value="evidence" className="mt-4 space-y-2">
                  {researchDetail.evidence.map((item) => (
                    <div key={item.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border p-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate text-sm font-medium">{item.source_title || item.source_type}</p>
                          <Badge variant="outline">{RESEARCH_SECTION_LABELS[item.section_key] ?? item.section_key}</Badge>
                          {item.market && <Badge variant="secondary">{item.market}</Badge>}
                        </div>
                        <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.excerpt || "未提供摘录"}</p>
                      </div>
                      {isSafeSourceUrl(item.source_url) ? <Button variant="outline" size="sm" asChild><a href={item.source_url} target="_blank" rel="noreferrer">查看来源 <ExternalLink /></a></Button> : <Badge variant="outline">{item.status}</Badge>}
                    </div>
                  ))}
                  {!researchDetail.evidence.length && <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">完成首轮调研后，这里会列出可追溯来源。</div>}
                </TabsContent>
                <TabsContent value="versions" className="mt-4 space-y-2">
                  {researchDetail.runs.map((run, index) => (
                    <div key={run.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3">
                      <div>
                        <p className="text-sm font-medium">第 {researchDetail.runs.length - index} 版 · {RESEARCH_STATUS_LABELS[run.status] ?? run.status}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{new Date(run.created_at).toLocaleString("zh-CN")} · {Number(run.source_summary.evidenceCount ?? 0)} 条证据</p>
                      </div>
                      {index === 0 && <Badge variant="secondary">当前版本</Badge>}
                    </div>
                  ))}
                  {!researchDetail.runs.length && <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">尚未执行调研。</div>}
                </TabsContent>
              </Tabs>

              <div className="flex flex-wrap justify-between gap-2 border-t pt-4">
                <div className="flex flex-wrap gap-2">
                  <Button variant="ghost" disabled={researchBusy} onClick={() => void setResearchArchived(researchDetail.project, researchDetail.project.status !== "archived")}>
                    <Archive /> {researchDetail.project.status === "archived" ? "恢复项目" : "归档项目"}
                  </Button>
                  <Button variant="ghost" className="text-rose-700 hover:bg-rose-50 hover:text-rose-800" disabled={researchBusy} onClick={() => { setResearchDeleteMessage(""); setResearchDeleteTarget(researchDetail.project); }}>
                    <Trash2 /> 删除项目
                  </Button>
                </div>
                <Button variant="outline" onClick={returnToResearchList}><ChevronLeft /> 返回项目库</Button>
              </div>
            </div>
            )}
          </div>
          </section>
        </div>
      )}

      <Sheet open={Boolean(researchMarketActionTarget)} onOpenChange={(open) => { if (!open && !researchMarketActionBusy) setResearchMarketActionTarget(null); }}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          {researchMarketActionTarget && (
            <div className="space-y-5 p-5 pt-2">
              <SheetHeader className="px-0 text-left">
                <SheetTitle className="text-xl">市场假设验证</SheetTitle>
                <SheetDescription>{String(researchMarketActionTarget.marketName ?? researchMarketActionTarget.marketCode ?? "目标市场")} · 把假设逐步变成有来源、可复查的结论</SheetDescription>
              </SheetHeader>

              <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-4">
                <p className="text-sm font-medium text-cyan-950">建议按这个顺序处理</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  {["找3个真实买家或需求信号", "记录售价、采购量和进入门槛", "附来源后再确认或否定"].map((item) => <div key={item} className="flex gap-2 rounded-lg bg-white/80 p-2 text-xs leading-5"><Check className="mt-0.5 size-4 shrink-0 text-cyan-700" />{item}</div>)}
                </div>
                <p className="mt-3 text-xs leading-5 text-cyan-800">“待验证”不是错误，而是尚未取得足够证据；先改成“验证中”，只有结论和可访问链接都齐全时才标记“已验证”。</p>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-slate-50 p-4">
                <div><p className="font-medium">填写辅助</p><p className="mt-1 text-xs text-muted-foreground">示例不会自动保存，必须替换为真实结果。</p></div>
                <Button size="sm" variant="outline" onClick={fillResearchMarketExample}><Sparkles /> 填入示例</Button>
              </div>

              <label className="block text-sm font-medium">验证状态
                <Select value={researchMarketActionStatus} onValueChange={(value) => setResearchMarketActionStatus(value as ResearchMarketStatus)}>
                  <SelectTrigger className="mt-1.5" aria-label="市场验证状态"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="hypothesis">待验证假设</SelectItem>
                    <SelectItem value="partial">验证中</SelectItem>
                    <SelectItem value="validated">已验证（必须有结论和链接）</SelectItem>
                    <SelectItem value="rejected">已否定（必须写原因）</SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <label className="block text-sm font-medium">本次验证记录
                <Textarea className="mt-1.5 min-h-28" value={researchMarketActionNote} onChange={(event) => setResearchMarketActionNote(event.target.value)} placeholder="记录买家是谁、为什么有需求、价格/采购量、回复或拒绝原因；未知项明确写未知。" maxLength={2000} />
              </label>
              <label className="block text-sm font-medium">证据链接
                <Input className="mt-1.5" type="url" value={researchMarketEvidenceUrl} onChange={(event) => setResearchMarketEvidenceUrl(event.target.value)} placeholder="https://… 买家网站、商品页、法规或趋势来源" maxLength={1000} />
                <span className="mt-1 block text-xs font-normal text-muted-foreground">标记“已验证”时必须提供可访问链接；仅凭 AI 描述不能算验证完成。</span>
              </label>
              <div className="grid gap-4 sm:grid-cols-[1fr_180px]">
                <label className="block text-sm font-medium">下一步计划
                  <Input className="mt-1.5" value={researchMarketNextAction} onChange={(event) => setResearchMarketNextAction(event.target.value)} placeholder="下一次要完成的具体动作" maxLength={500} />
                </label>
                <label className="block text-sm font-medium">跟进日期（可选）
                  <Input className="mt-1.5" type="date" value={researchMarketFollowUpAt} onChange={(event) => setResearchMarketFollowUpAt(event.target.value)} />
                </label>
              </div>
              {researchMarketActionMessage && <p className="text-sm text-amber-700">{researchMarketActionMessage}</p>}

              <div className="rounded-xl border p-4">
                <h3 className="font-medium">历史验证记录</h3>
                <div className="mt-3 space-y-3">
                  {(researchDetail?.marketActivities ?? []).filter((item) => item.market_code === String(researchMarketActionTarget.marketCode ?? "").toUpperCase()).slice(0, 20).map((item) => (
                    <div key={item.id} className="border-l-2 border-cyan-200 pl-3 text-sm">
                      <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{RESEARCH_VALIDATION_LABELS[item.from_status]} → {RESEARCH_VALIDATION_LABELS[item.to_status]}</span><span className="text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString("zh-CN")}</span></div>
                      {item.note && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{item.note}</p>}
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">{item.next_action && <span>下一步：{item.next_action}</span>}{item.follow_up_at && <span>跟进：{item.follow_up_at}</span>}{item.evidence_url && <a className="inline-flex items-center gap-1 text-cyan-800 underline" href={item.evidence_url} target="_blank" rel="noreferrer">查看证据 <ExternalLink className="size-3" /></a>}</div>
                    </div>
                  ))}
                  {!(researchDetail?.marketActivities ?? []).some((item) => item.market_code === String(researchMarketActionTarget.marketCode ?? "").toUpperCase()) && <p className="text-sm text-muted-foreground">还没有验证记录。建议先以“验证中”保存第一条真实证据。</p>}
                </div>
              </div>

              <div className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t bg-background py-3">
                <Button variant="outline" disabled={researchMarketActionBusy} onClick={() => setResearchMarketActionTarget(null)}>取消</Button>
                <Button disabled={researchMarketActionBusy} onClick={() => void saveResearchMarketAction()}><Check /> {researchMarketActionBusy ? "正在保存…" : "保存验证记录"}</Button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      <Sheet open={Boolean(researchCandidateActionTarget)} onOpenChange={(open) => { if (!open && !researchCandidateActionBusy) setResearchCandidateActionTarget(null); }}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          {researchCandidateActionTarget && (
            <div className="space-y-5 p-5 pt-2">
              <SheetHeader className="px-0 text-left">
                <SheetTitle className="text-xl">产品推进操作</SheetTitle>
                <SheetDescription>{researchCandidateActionTarget.name} · {researchCandidateActionTarget.track_category || "未分类"} / {researchCandidateActionTarget.subcategory || "未细分"}</SheetDescription>
              </SheetHeader>

              <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs text-cyan-800">当前阶段</p>
                    <p className="mt-1 font-semibold text-cyan-950">{RESEARCH_CANDIDATE_STAGE_LABELS[researchCandidateActionTarget.stage]}</p>
                  </div>
                  <Badge variant="outline" className="bg-white">下一步：{RESEARCH_CANDIDATE_NEXT_ACTIONS[researchCandidateActionTarget.stage]}</Badge>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-3">
                  {RESEARCH_CANDIDATE_STAGE_CHECKLISTS[researchCandidateActionTarget.stage].map((item) => (
                    <div key={item} className="flex gap-2 rounded-lg bg-white/80 p-2 text-xs leading-5"><Check className="mt-0.5 size-4 shrink-0 text-cyan-700" />{item}</div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border bg-slate-50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">Codex / ChatGPT 辅助</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">“填入示例”只生成可编辑模板；“AI辅助调研”使用独立产品调研通道，核实需求、价格、MOQ、合规、买家和图片并写入历史，不会阻塞其他通道，也不会自动改变阶段。</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={fillResearchCandidateExample}><Sparkles /> 填入示例</Button>
                    <Button size="sm" disabled={researchCandidateAiBusy || Boolean(candidateAssistChannelJob) || codexChannelState !== "ready"} onClick={() => void dispatchResearchCandidateAssist()}><Bot /> {researchCandidateAiBusy ? "发送中…" : candidateAssistChannelJob ? "产品调研通道忙碌" : "AI辅助调研"}</Button>
                  </div>
                </div>
                {researchCandidateAiMessage && <p className="mt-3 text-xs leading-5 text-cyan-800">{researchCandidateAiMessage}</p>}
              </div>

              <label className="block text-sm font-medium">操作完成后阶段
                <Select value={researchCandidateActionStage} onValueChange={(value) => setResearchCandidateActionStage(value as ResearchCandidate["stage"])}>
                  <SelectTrigger className="mt-1.5" aria-label="操作完成后阶段"><SelectValue /></SelectTrigger>
                  <SelectContent>{Object.entries(RESEARCH_CANDIDATE_STAGE_LABELS).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent>
                </Select>
              </label>
              <label className="block text-sm font-medium">本次操作记录
                <Textarea className="mt-1.5 min-h-24" value={researchCandidateActionNote} onChange={(event) => setResearchCandidateActionNote(event.target.value)} placeholder="例如：已向3家供应商发送RFQ，收到2家回复；A厂MOQ 100件，样品费30美元。" maxLength={2000} />
              </label>
              <label className="block text-sm font-medium">证据或文件链接（可选）
                <Input className="mt-1.5" type="url" value={researchCandidateEvidenceUrl} onChange={(event) => setResearchCandidateEvidenceUrl(event.target.value)} placeholder="https://… 商品页、报价单或公开来源" maxLength={1000} />
              </label>
              <div className="grid gap-4 sm:grid-cols-[1fr_180px]">
                <label className="block text-sm font-medium">下一步计划
                  <Input className="mt-1.5" value={researchCandidateNextAction} onChange={(event) => setResearchCandidateNextAction(event.target.value)} placeholder="下一次要完成的具体动作" maxLength={500} />
                </label>
                <label className="block text-sm font-medium">跟进日期（可选）
                  <Input className="mt-1.5" type="date" value={researchCandidateFollowUpAt} onChange={(event) => setResearchCandidateFollowUpAt(event.target.value)} />
                </label>
              </div>

              <div className="rounded-xl border p-4">
                <h3 className="font-medium">历史操作记录</h3>
                <div className="mt-3 space-y-3">
                  {(researchDetail?.activities ?? []).filter((item) => item.candidate_id === researchCandidateActionTarget.id).slice(0, 20).map((item) => (
                    <div key={item.id} className="border-l-2 border-cyan-200 pl-3 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{RESEARCH_CANDIDATE_STAGE_LABELS[item.from_stage]} → {RESEARCH_CANDIDATE_STAGE_LABELS[item.to_stage]}</span>
                        {item.created_by === "ai" && <Badge variant="secondary" className="h-5 px-1.5 text-[10px]"><Bot /> AI建议</Badge>}
                        <span className="text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString("zh-CN")}</span>
                      </div>
                      {item.note && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{item.note}</p>}
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                        {item.next_action && <span>下一步：{item.next_action}</span>}
                        {item.follow_up_at && <span>跟进：{item.follow_up_at}</span>}
                        {item.evidence_url && <a className="inline-flex items-center gap-1 text-cyan-800 underline" href={item.evidence_url} target="_blank" rel="noreferrer">查看证据 <ExternalLink className="size-3" /></a>}
                      </div>
                      {item.created_by === "ai" && item.recommended_stage && (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <Badge variant="outline">建议：{RESEARCH_CANDIDATE_STAGE_LABELS[item.recommended_stage]}</Badge>
                          <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={() => {
                            setResearchCandidateActionStage(item.recommended_stage as ResearchCandidate["stage"]);
                            if (item.next_action) setResearchCandidateNextAction(item.next_action);
                            setResearchCandidateAiMessage("已填入AI推荐阶段和下一步，检查无误后再点击保存。AI不会自动提交。");
                          }}>采纳建议</Button>
                        </div>
                      )}
                    </div>
                  ))}
                  {!(researchDetail?.activities ?? []).some((item) => item.candidate_id === researchCandidateActionTarget.id) && <p className="text-sm text-muted-foreground">还没有操作记录。完成本次填写后会自动保存到这里。</p>}
                </div>
              </div>

              <div className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t bg-background py-3">
                <Button variant="outline" disabled={researchCandidateActionBusy || researchBusy} onClick={() => setResearchCandidateActionTarget(null)}>取消</Button>
                <Button variant="outline" disabled={researchCandidateActionBusy || researchBusy} onClick={() => void saveResearchCandidateAction()}><Check /> {researchCandidateActionBusy ? "正在保存…" : "保存记录"}</Button>
                {(() => {
                  const nextStage = RESEARCH_CANDIDATE_NEXT_STAGE[researchCandidateActionTarget.stage];
                  return nextStage ? <Button disabled={researchCandidateActionBusy || researchBusy} onClick={() => void saveResearchCandidateAction(nextStage)}><ChevronRight /> 保存并进入{RESEARCH_CANDIDATE_STAGE_LABELS[nextStage]}</Button> : null;
                })()}
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      <Dialog open={Boolean(researchSelectionTarget && researchSelectionDraft)} onOpenChange={(open) => { if (!open && !researchSelectionBusy) { setResearchSelectionTarget(null); setResearchSelectionDraft(null); setResearchSelectionMessage(""); } }}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-4xl">
          {researchSelectionTarget && researchSelectionDraft && (() => {
            const previewCandidate = { ...researchSelectionTarget, product_family: researchSelectionFamily };
            const readiness = candidateHandoffReadiness(previewCandidate, researchSelectionDraft);
            return <>
              <DialogHeader>
                <DialogTitle>标准选品评估</DialogTitle>
                <DialogDescription>{researchSelectionTarget.name} · 评估结果用于筛选与 Odoo 移交，不会自动创建产品、报价或订单。</DialogDescription>
              </DialogHeader>

              <div className="grid gap-4 sm:grid-cols-[1fr_200px]">
                <label className="text-sm font-medium">产品家族
                  <Input className="mt-1.5" value={researchSelectionFamily} onChange={(event) => setResearchSelectionFamily(event.target.value)} placeholder="例如：USB桌面风扇家族" maxLength={120} />
                  <span className="mt-1 block text-xs font-normal text-muted-foreground">同一家族共享买家、渠道、供应链和合规研究；候选名称保留具体款式差异。</span>
                </label>
                <label className="text-sm font-medium">人工决策
                  <Select value={researchSelectionDraft.decision} onValueChange={(value) => setResearchSelectionDraft((current) => current ? { ...current, decision: value as CandidateSelectionAssessment["decision"] } : current)}>
                    <SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="unreviewed">未评估</SelectItem><SelectItem value="research">继续调研</SelectItem><SelectItem value="shortlist">进入短名单</SelectItem><SelectItem value="ready">可移交 Odoo</SelectItem><SelectItem value="blocked">暂停 / 阻塞</SelectItem></SelectContent>
                  </Select>
                </label>
              </div>

              <div className="rounded-xl border p-4">
                <div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">100 分选品评分卡</h3><p className="mt-1 text-xs text-muted-foreground">分数是人工判断的结构化记录；未知项留空，不用 0 伪装证据。</p></div><Badge variant={readiness.score >= 70 ? "default" : "outline"}>{readiness.score} / 100</Badge></div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {(Object.entries(SELECTION_SCORE_FIELDS) as Array<[SelectionScoreKey, { label: string; max: number }]>).map(([key, meta]) => (
                    <label key={key} className="text-xs font-medium text-slate-600">{meta.label}（0–{meta.max}）
                      <Input className="mt-1 bg-white" type="number" min={0} max={meta.max} value={researchSelectionDraft.scorecard[key] ?? ""} onChange={(event) => setResearchSelectionDraft((current) => current ? { ...current, scorecard: { ...current.scorecard, [key]: event.target.value === "" ? null : Math.min(meta.max, Math.max(0, Number(event.target.value))) } } : current)} />
                    </label>
                  ))}
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-xl border p-4">
                  <h3 className="font-medium">渠道适配度（0–100）</h3>
                  <p className="mt-1 text-xs text-muted-foreground">不是三个渠道都做；用评分决定主渠道、验证渠道与暂缓渠道。</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
                    {(Object.entries(CHANNEL_FIT_FIELDS) as Array<[ChannelFitKey, string]>).map(([key, label]) => (
                      <label key={key} className="grid grid-cols-[1fr_90px] items-center gap-3 text-sm"><span>{label}</span><Input type="number" min={0} max={100} value={researchSelectionDraft.channelFit[key] ?? ""} onChange={(event) => setResearchSelectionDraft((current) => current ? { ...current, channelFit: { ...current.channelFit, [key]: event.target.value === "" ? null : Math.min(100, Math.max(0, Number(event.target.value))) } } : current)} /></label>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border p-4">
                  <h3 className="font-medium">五项硬门槛</h3>
                  <p className="mt-1 text-xs text-muted-foreground">全部通过才允许生成 Odoo 移交包。</p>
                  <div className="mt-3 space-y-2">
                    {(Object.entries(SELECTION_GATE_FIELDS) as Array<[SelectionGateKey, string]>).map(([key, label]) => (
                      <label key={key} className="flex cursor-pointer items-start gap-2 rounded-lg border p-2 text-sm hover:bg-slate-50"><input className="mt-0.5 size-4 accent-cyan-800" type="checkbox" checked={researchSelectionDraft.gates[key]} onChange={(event) => setResearchSelectionDraft((current) => current ? { ...current, gates: { ...current.gates, [key]: event.target.checked } } : current)} /><span>{label}</span></label>
                    ))}
                  </div>
                </div>
              </div>

              <label className="text-sm font-medium">评估备注
                <Textarea className="mt-1.5 min-h-20" value={researchSelectionDraft.note} onChange={(event) => setResearchSelectionDraft((current) => current ? { ...current, note: event.target.value } : current)} placeholder="记录评分依据、关键假设、客户画像或必须复核的问题" maxLength={2000} />
              </label>

              <div className={`rounded-xl border p-4 ${readiness.ready ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
                <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium">{readiness.ready ? "已达到 Odoo 移交门槛" : "尚未达到 Odoo 移交门槛"}</p><Badge variant="outline" className="bg-white">{readiness.blockers.length} 个阻塞项</Badge></div>
                {readiness.blockers.length > 0 && <ul className="mt-2 grid gap-1 text-xs text-slate-700 sm:grid-cols-2">{readiness.blockers.map((blocker) => <li key={blocker}>• {blocker}</li>)}</ul>}
                <p className="mt-2 text-xs text-muted-foreground">移交包只承载已核验数据和证据链；进入 Odoo 后仍需由正式审批流程决定是否建档、报价和上架。</p>
              </div>
              {researchSelectionMessage && <p className="text-sm text-cyan-800">{researchSelectionMessage}</p>}

              <DialogFooter className="gap-2">
                <Button variant="outline" disabled={researchSelectionBusy} onClick={() => { setResearchSelectionTarget(null); setResearchSelectionDraft(null); }}>取消</Button>
                <Button variant="outline" disabled={researchSelectionBusy} onClick={() => void saveResearchSelection()}><Check /> {researchSelectionBusy ? "保存中…" : "保存评估"}</Button>
                <Button disabled={!researchSelectionTarget.handoff_readiness.ready || researchSelectionBusy} onClick={() => exportResearchCandidateToOdoo(researchSelectionTarget)}><Download /> 导出 Odoo 移交包</Button>
              </DialogFooter>
            </>;
          })()}
        </DialogContent>
      </Dialog>

      <Dialog open={globalBuyerLibraryOpen} onOpenChange={setGlobalBuyerLibraryOpen}>
        <DialogContent className="max-h-[94vh] overflow-hidden sm:max-w-7xl">
          <DialogHeader>
            <DialogTitle>全球外贸批发客户画像</DialogTitle>
            <DialogDescription>地区 → 画像分类 → 销售/采购场景 → 产品赛道 → 产品家族 → 真实买家实例。分类主数据独立于项目，人工维护不会被后续 AI 覆盖。</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
            {[
              ["外贸地区", globalBuyerLibrary?.stats.regionCount ?? 0],
              ["画像分类", globalBuyerLibrary?.stats.personaCategoryCount ?? 0],
              ["产品赛道", globalBuyerLibrary?.stats.trackCount ?? 0],
              ["产品家族", globalBuyerLibrary?.stats.masterFamilyCount ?? 0],
              ["画像矩阵", globalBuyerLibrary?.stats.personaMatrixCount ?? 0],
              ["真实买家", globalBuyerLibrary?.stats.profileCount ?? 0],
            ].map(([label, value]) => <div key={String(label)} className="rounded-xl border bg-slate-50 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></div>)}
          </div>
          {globalBuyerMessage && <p role="status" className="rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs text-cyan-950">{globalBuyerMessage}</p>}
          <Tabs value={globalBuyerLibraryTab} onValueChange={setGlobalBuyerLibraryTab} className="min-h-0 flex-1">
            <TabsList className="grid h-auto w-full grid-cols-5">
              <TabsTrigger value="personas">画像分类</TabsTrigger>
              <TabsTrigger value="regions">地区</TabsTrigger>
              <TabsTrigger value="products">产品赛道与家族</TabsTrigger>
              <TabsTrigger value="matrix">关系矩阵</TabsTrigger>
              <TabsTrigger value="buyers">真实买家</TabsTrigger>
            </TabsList>

            <TabsContent value="personas" className="mt-3 space-y-3">
              <div className="flex flex-wrap gap-2"><Input className="min-w-64 flex-1" value={globalTaxonomySearch} onChange={(event) => setGlobalTaxonomySearch(event.target.value)} placeholder="搜索画像名称、分类组、客群、采购场景" /><Button variant="outline" disabled={Boolean(taxonomyAssistChannelJob)} onClick={() => openPersonaAiAssistant()}><Bot /> AI补充</Button><Button onClick={() => openPersonaCategoryEditor()}><Plus /> 新增画像分类</Button></div>
              <div className="max-h-[53vh] grid gap-3 overflow-y-auto pr-1 lg:grid-cols-2">
                {globalPersonaCategories.filter((item) => !globalTaxonomySearch.trim() || `${item.name} ${item.group_name} ${item.description} ${item.customer_groups.join(" ")} ${item.purchase_scenarios.join(" ")}`.toLocaleLowerCase().includes(globalTaxonomySearch.trim().toLocaleLowerCase())).map((item) => {
                  const companyCount = globalBuyerProfiles.filter((buyer) => buyer.persona_code === item.code).length;
                  const matrixCount = globalPersonaMatrix.filter((link) => link.persona_code === item.code).length;
                  return <div key={item.code} className="rounded-xl border p-4"><div className="flex items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{item.name}</h3><Badge variant="secondary">{item.group_name}</Badge><Badge variant="outline">{item.code}</Badge></div><p className="mt-2 text-sm leading-6 text-muted-foreground">{item.description}</p></div><div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => openPersonaAiAssistant(item)}><Bot /> AI复核</Button><Button size="sm" variant="outline" onClick={() => openPersonaCategoryEditor(item)}>维护</Button><Button size="sm" variant="ghost" className="text-rose-700" onClick={() => setPersonaDeleteTarget(item)}><Trash2 /></Button></div></div><div className="mt-3 grid gap-2 sm:grid-cols-2"><div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-muted-foreground">价值链角色</p><p className="mt-1 text-sm">{item.value_chain_role}</p></div><div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-muted-foreground">已关联</p><p className="mt-1 text-sm">{matrixCount} 条矩阵 · {companyCount} 家真实公司</p></div></div><div className="mt-3 flex flex-wrap gap-1">{item.purchase_scenarios.map((value) => <Badge key={value} variant="outline" className="font-normal">{value}</Badge>)}</div></div>;
                })}
              </div>
            </TabsContent>

            <TabsContent value="regions" className="mt-3 space-y-3">
              <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-3 text-xs leading-5 text-cyan-950">地区采用 UN M49 地理骨架并转成外贸业务分区；国家代码用于项目匹配，地区名称不参与真实需求判断。</div>
              <div className="max-h-[56vh] grid gap-3 overflow-y-auto pr-1 lg:grid-cols-2 xl:grid-cols-3">
                {globalTradeRegions.map((item) => <div key={item.code} className="rounded-xl border p-4"><div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">{item.name}</h3><p className="mt-1 text-xs text-muted-foreground">{item.macro_region} · M49 {item.m49_code}</p></div><Badge variant="outline">{item.code}</Badge></div><div className="mt-3 flex flex-wrap gap-1">{item.countries.map((country) => <Badge key={country} variant="secondary" className="font-normal">{marketNameForCode(country)} · {country}</Badge>)}{item.code === "GLOBAL" && <Badge variant="secondary">所有地区</Badge>}</div><p className="mt-3 text-xs leading-5 text-muted-foreground">{item.characteristics.join("；")}</p></div>)}
              </div>
            </TabsContent>

            <TabsContent value="products" className="mt-3 space-y-3">
              <div className="flex flex-wrap gap-2"><Input className="min-w-64 flex-1" value={globalTaxonomySearch} onChange={(event) => setGlobalTaxonomySearch(event.target.value)} placeholder="搜索产品赛道、家族、场景或合规标签" /><Button variant="outline" onClick={() => openProductTrackEditor()}><Plus /> 新增赛道</Button><Button onClick={() => openProductFamilyEditor()}><Plus /> 新增产品家族</Button></div>
              <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-3 text-xs leading-5 text-cyan-950">家族数量按赛道实际采购复杂度设置，不采用固定配额。只有用途、买家决策、合规、替代关系、物流或售后要求存在实质差异时才拆成独立家族；候选规格与款式继续放在产品池。</div>
              <div className="max-h-[55vh] space-y-3 overflow-y-auto pr-1">
                {globalProductTracks.filter((trackItem) => {
                  const families = globalProductFamilyMaster.filter((familyItem) => familyItem.track_code === trackItem.code);
                  const text = `${trackItem.name} ${trackItem.description} ${trackItem.buyer_value} ${families.flatMap((item) => [item.name, ...item.keywords, ...item.use_scenarios]).join(" ")}`.toLocaleLowerCase();
                  return !globalTaxonomySearch.trim() || text.includes(globalTaxonomySearch.trim().toLocaleLowerCase());
                }).map((trackItem) => {
                  const families = globalProductFamilyMaster.filter((item) => item.track_code === trackItem.code);
                  return <div key={trackItem.code} className="rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><h3 className="font-medium">{trackItem.name}</h3><Badge variant="outline">{trackItem.code}</Badge><Badge variant="secondary">{families.length} 个家族</Badge></div><p className="mt-1 text-sm text-muted-foreground">{trackItem.description}</p><p className="mt-2 text-xs text-cyan-900">买家价值：{trackItem.buyer_value}</p></div><div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => openProductTrackEditor(trackItem)}>维护赛道</Button><Button size="sm" onClick={() => openProductFamilyEditor(undefined, trackItem.code)}><Plus /> 家族</Button></div></div><div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{families.map((familyItem) => <button type="button" key={familyItem.code} className="rounded-lg border bg-slate-50 p-3 text-left hover:border-cyan-300" onClick={() => openProductFamilyEditor(familyItem)}><div className="flex items-center justify-between gap-2"><p className="text-sm font-medium">{familyItem.name}</p><span className="text-[10px] text-muted-foreground">{familyItem.code}</span></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{familyItem.description}</p></button>)}</div></div>;
                })}
              </div>
            </TabsContent>

            <TabsContent value="matrix" className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center gap-2"><Input className="min-w-64 flex-1" value={globalTaxonomySearch} onChange={(event) => setGlobalTaxonomySearch(event.target.value)} placeholder="搜索画像、地区、赛道或产品家族" /><Button onClick={() => openPersonaMatrixEditor()}><Plus /> 新增关系</Button></div>
              <div className="max-h-[56vh] space-y-2 overflow-y-auto pr-1">
                {globalPersonaMatrix.filter((item) => {
                  const personaItem = globalPersonaCategories.find((value) => value.code === item.persona_code);
                  const regionItem = globalTradeRegions.find((value) => value.code === item.region_code);
                  const trackItem = globalProductTracks.find((value) => value.code === item.track_code);
                  const familyItem = globalProductFamilyMaster.find((value) => value.code === item.product_family_code);
                  return !globalTaxonomySearch.trim() || `${personaItem?.name} ${regionItem?.name} ${trackItem?.name} ${familyItem?.name}`.toLocaleLowerCase().includes(globalTaxonomySearch.trim().toLocaleLowerCase());
                }).map((item) => {
                  const personaItem = globalPersonaCategories.find((value) => value.code === item.persona_code);
                  const regionItem = globalTradeRegions.find((value) => value.code === item.region_code);
                  const trackItem = globalProductTracks.find((value) => value.code === item.track_code);
                  const familyItem = globalProductFamilyMaster.find((value) => value.code === item.product_family_code);
                  return <button type="button" key={item.id} className="grid w-full items-center gap-3 rounded-xl border p-3 text-left hover:border-cyan-300 md:grid-cols-[1.3fr_1fr_1.2fr_100px_120px]" onClick={() => openPersonaMatrixEditor(item)}><div><p className="font-medium">{personaItem?.name ?? item.persona_code}</p><p className="mt-1 text-xs text-muted-foreground">{personaItem?.group_name}</p></div><div><p className="text-sm">{regionItem?.name ?? item.region_code}</p><p className="mt-1 text-xs text-muted-foreground">{item.region_code}</p></div><div><p className="text-sm">{trackItem?.name ?? item.track_code}</p><p className="mt-1 text-xs text-muted-foreground">{familyItem?.name || "赛道默认关系"}</p></div><Badge variant="secondary">{RESEARCH_FAMILY_ROLE_LABELS[item.family_role]}</Badge><div className="text-right"><p className="text-lg font-semibold tabular-nums">{item.relevance_score}</p><p className="text-[10px] text-muted-foreground">{RESEARCH_VALIDATION_LABELS[item.evidence_status]}</p></div></button>;
                })}
              </div>
            </TabsContent>

            <TabsContent value="buyers" className="mt-3 space-y-3">
              <div className="flex flex-wrap gap-2"><Input className="min-w-64 flex-1" value={globalBuyerSearch} onChange={(event) => setGlobalBuyerSearch(event.target.value)} placeholder="搜索公司、画像分类、采购场景或产品家族" /><Select value={globalBuyerCountry} onValueChange={setGlobalBuyerCountry}><SelectTrigger className="w-44"><SelectValue placeholder="全部市场" /></SelectTrigger><SelectContent><SelectItem value="all">全部市场</SelectItem>{globalBuyerCountries.map((country) => <SelectItem key={country} value={country}>{marketNameForCode(country)}（{country}）</SelectItem>)}</SelectContent></Select><Button onClick={openNewGlobalBuyer}><Plus /> 新增真实买家</Button></div>
              <div className="max-h-[53vh] space-y-2 overflow-y-auto pr-1">
                {filteredGlobalBuyers.map((buyer) => {
                  const links = globalBuyerLinks.filter((link) => link.buyer_profile_id === buyer.id);
                  const personaItem = globalPersonaCategories.find((item) => item.code === buyer.persona_code);
                  const regionItem = globalTradeRegions.find((item) => item.code === buyer.region_code);
                  return <div key={buyer.id} className="rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{buyer.company_name}</h3><Badge variant={buyer.profile_status === "validated" ? "default" : "outline"}>{RESEARCH_BUYER_STATUS_LABELS[buyer.profile_status]}</Badge>{buyer.created_by === "ai" && <Badge variant="secondary"><Bot /> AI 初筛</Badge>}</div><p className="mt-1 text-xs text-muted-foreground">{marketNameForCode(buyer.country)} · {regionItem?.name ?? buyer.region_code} · {personaItem?.name ?? buyer.buyer_type} · 来源于 {buyer.source_project_count} 个项目</p></div><div className="flex gap-2"><Button size="sm" variant="outline" asChild><a href={buyer.source_url} target="_blank" rel="noreferrer">来源 <ExternalLink /></a></Button><Button size="sm" variant="outline" onClick={() => openEditGlobalBuyer(buyer)}>维护画像</Button><Button size="sm" onClick={() => openGlobalBuyerMatrix(buyer)}>公司产品矩阵</Button></div></div><div className="mt-3 grid gap-3 lg:grid-cols-2"><div><p className="text-xs font-medium text-muted-foreground">销售 / 采购场景</p><div className="mt-1 flex flex-wrap gap-1">{buyer.purchasing_scenarios.map((value) => <Badge key={value} variant="outline" className="font-normal">{value}</Badge>)}</div></div><div><p className="text-xs font-medium text-muted-foreground">公司级家族覆盖</p><div className="mt-1 flex flex-wrap gap-1">{links.slice(0, 8).map((link) => <Badge key={link.id} variant="secondary" className="font-normal">{link.product_family} · {RESEARCH_FAMILY_ROLE_LABELS[link.family_role]}</Badge>)}{links.length > 8 && <Badge variant="outline">+{links.length - 8}</Badge>}{!links.length && <span className="text-xs text-muted-foreground">先继承分类矩阵，再补公司级差异</span>}</div></div></div></div>;
                })}
                {!filteredGlobalBuyers.length && <div className="rounded-xl border border-dashed py-12 text-center text-sm text-muted-foreground">没有符合条件的真实买家公司。</div>}
              </div>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      <Sheet open={Boolean(personaDetail)} onOpenChange={(open) => { if (!open) setPersonaDetailCode(null); }}>
        <SheetContent className="w-[96vw] overflow-y-auto p-0 sm:max-w-5xl">
          {personaDetail && <>
            <SheetHeader className="border-b bg-slate-50 p-5 pr-12 text-left">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><Badge variant="secondary">{personaDetail.group_name}</Badge><Badge variant="outline">{personaDetail.code}</Badge><Badge variant="outline">v{personaDetail.version}</Badge></div>
                  <SheetTitle className="mt-2 text-xl">{personaDetail.name}</SheetTitle>
                  <SheetDescription className="mt-1 max-w-3xl leading-6">{personaDetail.description}</SheetDescription>
                </div>
                <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => openPersonaAiAssistant(personaDetail)}><Bot /> AI复核</Button><Button size="sm" variant="outline" onClick={() => openPersonaCategoryEditor(personaDetail)}>维护画像</Button><Button size="sm" variant="outline" onClick={() => openNewPersonaMatrixForPersona(personaDetail.code)}><Plus /> 新增矩阵关系</Button><Button size="sm" onClick={() => openValidationProgramFromPersona(personaDetail)} disabled={!personaDetailFamilyLinks.length}><TrendingUp /> 建立验证项目</Button></div>
              </div>
            </SheetHeader>

            <div className="space-y-5 p-5">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ["产品赛道", personaDetailTrackGroups.length, "按采购方向分组"],
                  ["产品家族", personaDetailFamilyLinks.length, "可直接维护关系"],
                  ["已验证关系", personaDetailLinks.filter((link) => link.evidence_status === "validated").length, "须由人工证据确认"],
                  ["真实买家", globalBuyerProfiles.filter((buyer) => buyer.persona_code === personaDetail.code).length, "公司级实例"],
                ].map(([label, value, note]) => <div key={String(label)} className="rounded-xl border bg-white p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-xl font-semibold tabular-nums">{value}</p><p className="mt-1 text-[11px] text-muted-foreground">{note}</p></div>)}
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                <div className="rounded-xl border p-4"><p className="text-xs font-medium text-muted-foreground">价值链角色与终端客群</p><p className="mt-2 text-sm font-medium">{personaDetail.value_chain_role}</p><div className="mt-3 flex flex-wrap gap-1">{personaDetail.customer_groups.map((value) => <Badge key={value} variant="outline" className="font-normal">{value}</Badge>)}</div></div>
                <div className="rounded-xl border p-4"><p className="text-xs font-medium text-muted-foreground">销售渠道与采购场景</p><div className="mt-2 flex flex-wrap gap-1">{personaDetail.sales_channels.map((value) => <Badge key={value} variant="secondary" className="font-normal">{value}</Badge>)}</div><div className="mt-3 flex flex-wrap gap-1">{personaDetail.purchase_scenarios.map((value) => <Badge key={value} variant="outline" className="font-normal">{value}</Badge>)}</div></div>
              </div>

              <div>
                <div className="flex flex-wrap items-end justify-between gap-2"><div><h3 className="font-medium">关联产品矩阵</h3><p className="mt-1 text-xs text-muted-foreground">按赛道查看默认优先级，再查看核心常采、跨品类加购、季节采购和小单测试家族。点击任一关系即可维护。</p></div><Badge variant="outline">{personaDetailLinks.length} 条关系</Badge></div>
                <div className="mt-3 space-y-3">
                  {personaDetailTrackGroups.map(({ trackCode, track, defaultLink, familyLinks, score }) => <div key={trackCode} className="rounded-xl border bg-white p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><h4 className="font-medium">{track?.name ?? trackCode}</h4><Badge variant="outline">{trackCode}</Badge><Badge variant="secondary">{familyLinks.length} 个家族</Badge></div><p className="mt-1 text-xs leading-5 text-muted-foreground">{track?.buyer_value || track?.description || "等待补充赛道说明"}</p></div><div className="flex items-center gap-2"><div className="text-right"><p className="text-lg font-semibold tabular-nums">{score}</p><p className="text-[10px] text-muted-foreground">赛道关系分</p></div>{defaultLink ? <Button size="sm" variant="outline" onClick={() => openPersonaMatrixEditor(defaultLink)}>维护赛道关系</Button> : <Button size="sm" variant="outline" onClick={() => openNewPersonaMatrixForPersona(personaDetail.code, trackCode)}><Plus /> 赛道关系</Button>}</div></div><div className="mt-3 grid gap-2 sm:grid-cols-2">{familyLinks.map((link) => {
                    const family = globalProductFamilyMaster.find((item) => item.code === link.product_family_code);
                    return <div key={link.id} className="overflow-hidden rounded-lg border bg-slate-50 transition hover:border-cyan-300"><button type="button" className="block w-full p-3 text-left hover:bg-cyan-50/40" onClick={() => openPersonaMatrixEditor(link)}><div className="flex items-start justify-between gap-2"><div><p className="text-sm font-medium">{family?.name ?? link.product_family_code}</p><p className="mt-1 text-[11px] text-muted-foreground">{family?.description || link.product_family_code}</p></div><span className="text-sm font-semibold tabular-nums">{link.relevance_score}</span></div><div className="mt-2 flex flex-wrap gap-1"><Badge variant={link.family_role === "core" ? "default" : "secondary"}>{RESEARCH_FAMILY_ROLE_LABELS[link.family_role]}</Badge><Badge variant="outline">{RESEARCH_VALIDATION_LABELS[link.evidence_status]}</Badge>{link.region_code !== "GLOBAL" && <Badge variant="outline">{globalTradeRegions.find((region) => region.code === link.region_code)?.name ?? link.region_code}</Badge>}</div></button><div className="flex items-center justify-between border-t bg-white px-3 py-2"><span className="text-[11px] text-muted-foreground">以此关系为起点，还可继续选择关联矩阵</span><Button size="sm" onClick={() => family && openValidationProgramFromPersona(personaDetail, link)} disabled={!family}><TrendingUp /> 组合验证</Button></div></div>;
                  })}{!familyLinks.length && <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground sm:col-span-2">这个赛道只有默认关系，尚未细化到具体产品家族。<Button size="sm" variant="link" onClick={() => openNewPersonaMatrixForPersona(personaDetail.code, trackCode)}>现在补充</Button></div>}</div></div>)}
                  {!personaDetailTrackGroups.length && <div className="rounded-xl border border-dashed py-12 text-center"><Database className="mx-auto size-8 text-slate-300" /><p className="mt-3 text-sm font-medium">尚未建立产品矩阵</p><p className="mt-1 text-xs text-muted-foreground">先添加一个赛道默认关系，再根据真实采购组合细化到产品家族。</p><Button className="mt-4" size="sm" onClick={() => openNewPersonaMatrixForPersona(personaDetail.code)}><Plus /> 新增第一条关系</Button></div>}
                </div>
              </div>

              <div className="grid gap-3 lg:grid-cols-3"><div className="rounded-xl border p-4"><p className="text-xs font-medium text-muted-foreground">采购触发</p><div className="mt-2 flex flex-wrap gap-1">{personaDetail.buying_triggers.map((value) => <Badge key={value} variant="outline" className="font-normal">{value}</Badge>)}</div></div><div className="rounded-xl border p-4"><p className="text-xs font-medium text-muted-foreground">订单特点</p><div className="mt-2 flex flex-wrap gap-1">{personaDetail.order_characteristics.map((value) => <Badge key={value} variant="outline" className="font-normal">{value}</Badge>)}</div></div><div className="rounded-xl border p-4"><p className="text-xs font-medium text-muted-foreground">合规关注</p><div className="mt-2 flex flex-wrap gap-1">{personaDetail.compliance_focus.map((value) => <Badge key={value} variant="outline" className="font-normal">{value}</Badge>)}</div></div></div>
            </div>
          </>}
        </SheetContent>
      </Sheet>

      <Dialog open={personaAiOpen} onOpenChange={(open) => { if (!personaAiBusy) setPersonaAiOpen(open); }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>AI补充 / 复核买家画像</DialogTitle><DialogDescription>任务使用独立画像分类通道。ChatGPT / Codex 只生成带来源的待审核建议，必须由你应用后才进入正式分类。</DialogDescription></DialogHeader>
          <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-3 text-xs leading-5 text-cyan-950">AI不会删除画像、不会覆盖人工字段，也不会把泛化分类关系描述成真实采购意向。每条建议必须保留公开来源。</div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">任务模式<Select value={personaAiMode} onValueChange={(value) => { const next = value as "discover" | "enrich"; setPersonaAiMode(next); if (next === "discover") setPersonaAiTargetCode(""); }}><SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="discover">发现缺失画像分类</SelectItem><SelectItem value="enrich">复核并补充现有画像</SelectItem></SelectContent></Select></label>
            <label className="text-sm font-medium">本轮建议数量<Input className="mt-1.5" type="number" min={1} max={10} value={personaAiRequestedCount} disabled={personaAiMode === "enrich"} onChange={(event) => setPersonaAiRequestedCount(event.target.value)} /></label>
            {personaAiMode === "enrich" && <label className="text-sm font-medium sm:col-span-2">目标画像<Select value={personaAiTargetCode || undefined} onValueChange={setPersonaAiTargetCode}><SelectTrigger className="mt-1.5"><SelectValue placeholder="选择要复核的画像" /></SelectTrigger><SelectContent>{globalPersonaCategories.map((item) => <SelectItem key={item.code} value={item.code}>{item.name} · {item.code}</SelectItem>)}</SelectContent></Select></label>}
            <label className="text-sm font-medium sm:col-span-2">补充要求<Textarea className="mt-1.5 min-h-28" value={personaAiRequestNote} onChange={(event) => setPersonaAiRequestNote(event.target.value)} maxLength={1500} /></label>
          </div>
          {personaAiMessage && <p role="alert" className="text-sm text-rose-700">{personaAiMessage}</p>}
          <DialogFooter><Button variant="outline" disabled={personaAiBusy} onClick={() => setPersonaAiOpen(false)}>取消</Button><Button disabled={personaAiBusy || personaAiMode === "enrich" && !personaAiTargetCode || Boolean(taxonomyAssistChannelJob)} onClick={() => void dispatchPersonaAiAssistant()}><Bot /> {personaAiBusy ? "发送中…" : "发送到AI画像通道"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(personaDeleteTarget)} onOpenChange={(open) => { if (!open && !globalTaxonomyBusy) setPersonaDeleteTarget(null); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>确认删除这个画像分类？</DialogTitle><DialogDescription>{personaDeleteTarget ? `“${personaDeleteTarget.name}”将从在用分类中移除。` : ""}</DialogDescription></DialogHeader>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-950">这是可恢复的软删除：历史版本、真实买家公司和关系矩阵不会被物理删除；后续新项目不再使用该画像。你可以在“已停用”中恢复。</div>
          {personaDeleteTarget && <div className="grid grid-cols-2 gap-2"><div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-muted-foreground">关系矩阵</p><p className="mt-1 font-medium">{globalPersonaMatrix.filter((item) => item.persona_code === personaDeleteTarget.code).length} 条保留</p></div><div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-muted-foreground">真实买家</p><p className="mt-1 font-medium">{globalBuyerProfiles.filter((item) => item.persona_code === personaDeleteTarget.code).length} 家保留</p></div></div>}
          <DialogFooter><Button variant="outline" disabled={globalTaxonomyBusy} onClick={() => setPersonaDeleteTarget(null)}>取消</Button><Button variant="destructive" disabled={globalTaxonomyBusy || !personaDeleteTarget} onClick={() => personaDeleteTarget && void setPersonaCategoryActive(personaDeleteTarget, false)}><Trash2 /> {globalTaxonomyBusy ? "删除中…" : "确认删除"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={personaCategoryEditorOpen} onOpenChange={(open) => { if (!globalTaxonomyBusy) setPersonaCategoryEditorOpen(open); }}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-4xl">
          <DialogHeader><DialogTitle>{personaCategoryTarget ? "维护买家画像分类" : "新增买家画像分类"}</DialogTitle><DialogDescription>分类描述的是稳定业态和价值链角色，不填写具体公司名、采购额或未经验证的需求。</DialogDescription></DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">稳定代码<Input className="mt-1.5" value={personaCategoryDraft.code} disabled={Boolean(personaCategoryTarget)} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, code: event.target.value.toUpperCase() }))} placeholder="例如 ELEC_MRO_DIST" /></label>
            <label className="text-sm font-medium">分类组<Input className="mt-1.5" value={personaCategoryDraft.groupName} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, groupName: event.target.value }))} placeholder="例如 电子与专业分销" /></label>
            <label className="text-sm font-medium">画像分类名称<Input className="mt-1.5" value={personaCategoryDraft.name} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, name: event.target.value }))} placeholder="例如 电子电气与工贸用品分销商" /></label>
            <label className="text-sm font-medium">价值链角色<Input className="mt-1.5" value={personaCategoryDraft.valueChainRole} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, valueChainRole: event.target.value }))} placeholder="例如 工业与工贸分销" /></label>
            <label className="text-sm font-medium sm:col-span-2">定义<Textarea className="mt-1.5 min-h-20" value={personaCategoryDraft.description} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, description: event.target.value }))} /></label>
            <label className="text-sm font-medium">终端客群<Textarea className="mt-1.5 min-h-20" value={personaCategoryDraft.customerGroups} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, customerGroups: event.target.value }))} placeholder="工厂、安装商、维修团队" /></label>
            <label className="text-sm font-medium">销售渠道<Textarea className="mt-1.5 min-h-20" value={personaCategoryDraft.salesChannels} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, salesChannels: event.target.value }))} placeholder="MRO目录、仓储、技术销售" /></label>
            <label className="text-sm font-medium">采购场景<Textarea className="mt-1.5 min-h-20" value={personaCategoryDraft.purchaseScenarios} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, purchaseScenarios: event.target.value }))} /></label>
            <label className="text-sm font-medium">采购触发条件<Textarea className="mt-1.5 min-h-20" value={personaCategoryDraft.buyingTriggers} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, buyingTriggers: event.target.value }))} /></label>
            <label className="text-sm font-medium">订单特点<Textarea className="mt-1.5 min-h-20" value={personaCategoryDraft.orderCharacteristics} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, orderCharacteristics: event.target.value }))} /></label>
            <label className="text-sm font-medium">合规关注<Textarea className="mt-1.5 min-h-20" value={personaCategoryDraft.complianceFocus} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, complianceFocus: event.target.value }))} /></label>
            <label className="text-sm font-medium sm:col-span-2">分类依据 / 公开来源<Textarea className="mt-1.5 min-h-20" value={personaCategoryDraft.sourceRefs} onChange={(event) => setPersonaCategoryDraft((current) => ({ ...current, sourceRefs: event.target.value }))} placeholder="每行一个可直接打开的 http/https 链接；AI补充画像时必须提供来源" /></label>
          </div>
          {globalBuyerMessage && <p role="alert" className="text-sm text-rose-700">{globalBuyerMessage}</p>}
          <DialogFooter><Button variant="outline" disabled={globalTaxonomyBusy} onClick={() => setPersonaCategoryEditorOpen(false)}>取消</Button><Button disabled={globalTaxonomyBusy} onClick={() => void savePersonaCategory()}><Check /> 保存画像分类</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={productTrackEditorOpen} onOpenChange={(open) => { if (!globalTaxonomyBusy) setProductTrackEditorOpen(open); }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>{productTrackTarget ? "维护产品赛道" : "新增产品赛道"}</DialogTitle><DialogDescription>赛道是稳定的大类主干；具体产品、规格和款式应放在产品家族与候选池。</DialogDescription></DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">稳定代码<Input className="mt-1.5" value={productTrackDraft.code} disabled={Boolean(productTrackTarget)} onChange={(event) => setProductTrackDraft((current) => ({ ...current, code: event.target.value.toUpperCase() }))} placeholder="例如 ELECTRICAL_MRO" /></label>
            <label className="text-sm font-medium">赛道名称<Input className="mt-1.5" value={productTrackDraft.name} onChange={(event) => setProductTrackDraft((current) => ({ ...current, name: event.target.value }))} /></label>
            <label className="text-sm font-medium sm:col-span-2">赛道定义<Textarea className="mt-1.5 min-h-20" value={productTrackDraft.description} onChange={(event) => setProductTrackDraft((current) => ({ ...current, description: event.target.value }))} /></label>
            <label className="text-sm font-medium">对买家的持续价值<Textarea className="mt-1.5 min-h-20" value={productTrackDraft.buyerValue} onChange={(event) => setProductTrackDraft((current) => ({ ...current, buyerValue: event.target.value }))} /></label>
            <label className="text-sm font-medium">合规关注<Textarea className="mt-1.5 min-h-20" value={productTrackDraft.complianceFocus} onChange={(event) => setProductTrackDraft((current) => ({ ...current, complianceFocus: event.target.value }))} /></label>
          </div>
          {globalBuyerMessage && <p role="alert" className="text-sm text-rose-700">{globalBuyerMessage}</p>}
          <DialogFooter><Button variant="outline" disabled={globalTaxonomyBusy} onClick={() => setProductTrackEditorOpen(false)}>取消</Button><Button disabled={globalTaxonomyBusy} onClick={() => void saveProductTrack()}><Check /> 保存产品赛道</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={productFamilyEditorOpen} onOpenChange={(open) => { if (!globalTaxonomyBusy) setProductFamilyEditorOpen(open); }}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader><DialogTitle>{productFamilyTarget ? "维护产品家族" : "新增产品家族"}</DialogTitle><DialogDescription>家族共享买家、用途、供应链和合规判断；具体功率、接口、包装和价格是候选产品差异。</DialogDescription></DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">稳定代码<Input className="mt-1.5" value={productFamilyDraft.code} disabled={Boolean(productFamilyTarget)} onChange={(event) => setProductFamilyDraft((current) => ({ ...current, code: event.target.value.toUpperCase() }))} placeholder="例如 MRO_CONNECT" /></label>
            <label className="text-sm font-medium">所属赛道<Select value={productFamilyDraft.trackCode || undefined} onValueChange={(value) => setProductFamilyDraft((current) => ({ ...current, trackCode: value }))}><SelectTrigger className="mt-1.5"><SelectValue placeholder="选择产品赛道" /></SelectTrigger><SelectContent>{globalProductTracks.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="text-sm font-medium">家族名称<Input className="mt-1.5" value={productFamilyDraft.name} onChange={(event) => setProductFamilyDraft((current) => ({ ...current, name: event.target.value }))} /></label>
            <label className="text-sm font-medium">检索关键词<Input className="mt-1.5" value={productFamilyDraft.keywords} onChange={(event) => setProductFamilyDraft((current) => ({ ...current, keywords: event.target.value }))} /></label>
            <label className="text-sm font-medium sm:col-span-2">家族定义<Textarea className="mt-1.5 min-h-20" value={productFamilyDraft.description} onChange={(event) => setProductFamilyDraft((current) => ({ ...current, description: event.target.value }))} /></label>
            <label className="text-sm font-medium">使用 / 销售场景<Textarea className="mt-1.5 min-h-20" value={productFamilyDraft.useScenarios} onChange={(event) => setProductFamilyDraft((current) => ({ ...current, useScenarios: event.target.value }))} /></label>
            <label className="text-sm font-medium">合规标签<Textarea className="mt-1.5 min-h-20" value={productFamilyDraft.complianceTags} onChange={(event) => setProductFamilyDraft((current) => ({ ...current, complianceTags: event.target.value }))} /></label>
          </div>
          {globalBuyerMessage && <p role="alert" className="text-sm text-rose-700">{globalBuyerMessage}</p>}
          <DialogFooter><Button variant="outline" disabled={globalTaxonomyBusy} onClick={() => setProductFamilyEditorOpen(false)}>取消</Button><Button disabled={globalTaxonomyBusy} onClick={() => void saveProductFamilyMaster()}><Check /> 保存产品家族</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={personaMatrixEditorOpen} onOpenChange={(open) => { if (!globalTaxonomyBusy) setPersonaMatrixEditorOpen(open); }}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader><DialogTitle>{personaMatrixTarget ? "维护画像—产品关系" : "新增画像—产品关系"}</DialogTitle><DialogDescription>默认建立画像分类与赛道的关系；只有确有必要时再指定到单个产品家族。关系分用于研究排序，不代表采购金额。</DialogDescription></DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">画像分类<Select value={personaMatrixDraft.personaCode || undefined} disabled={Boolean(personaMatrixTarget)} onValueChange={(value) => setPersonaMatrixDraft((current) => ({ ...current, personaCode: value }))}><SelectTrigger className="mt-1.5"><SelectValue placeholder="选择画像分类" /></SelectTrigger><SelectContent>{globalPersonaCategories.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="text-sm font-medium">适用地区<Select value={personaMatrixDraft.regionCode} disabled={Boolean(personaMatrixTarget)} onValueChange={(value) => setPersonaMatrixDraft((current) => ({ ...current, regionCode: value }))}><SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger><SelectContent>{globalTradeRegions.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="text-sm font-medium">产品赛道<Select value={personaMatrixDraft.trackCode || undefined} disabled={Boolean(personaMatrixTarget)} onValueChange={(value) => setPersonaMatrixDraft((current) => ({ ...current, trackCode: value, productFamilyCode: "" }))}><SelectTrigger className="mt-1.5"><SelectValue placeholder="选择产品赛道" /></SelectTrigger><SelectContent>{globalProductTracks.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="text-sm font-medium">产品家族覆盖（可选）<Select value={personaMatrixDraft.productFamilyCode || "__all__"} disabled={Boolean(personaMatrixTarget)} onValueChange={(value) => setPersonaMatrixDraft((current) => ({ ...current, productFamilyCode: value === "__all__" ? "" : value }))}><SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="__all__">整个赛道</SelectItem>{globalProductFamilyMaster.filter((item) => item.track_code === personaMatrixDraft.trackCode).map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="text-sm font-medium">关系分<Input className="mt-1.5" type="number" min={0} max={100} value={personaMatrixDraft.relevanceScore} onChange={(event) => setPersonaMatrixDraft((current) => ({ ...current, relevanceScore: Math.max(0, Math.min(100, Number(event.target.value) || 0)) }))} /></label>
            <label className="text-sm font-medium">家族角色<Select value={personaMatrixDraft.familyRole} onValueChange={(value) => setPersonaMatrixDraft((current) => ({ ...current, familyRole: value as ResearchBuyerFamilyLink["family_role"] }))}><SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="core">核心常采</SelectItem><SelectItem value="cross_sell">跨品类加购</SelectItem><SelectItem value="seasonal">季节采购</SelectItem><SelectItem value="test">小单测试</SelectItem></SelectContent></Select></label>
            <label className="text-sm font-medium">销售 / 采购场景<Textarea className="mt-1.5 min-h-20" value={personaMatrixDraft.salesScenarios} onChange={(event) => setPersonaMatrixDraft((current) => ({ ...current, salesScenarios: event.target.value }))} /></label>
            <label className="text-sm font-medium">季节性<Input className="mt-1.5" value={personaMatrixDraft.seasonality} onChange={(event) => setPersonaMatrixDraft((current) => ({ ...current, seasonality: event.target.value }))} /></label>
            <label className="text-sm font-medium sm:col-span-2">关系依据与补证方法<Textarea className="mt-1.5 min-h-24" value={personaMatrixDraft.rationale} onChange={(event) => setPersonaMatrixDraft((current) => ({ ...current, rationale: event.target.value }))} /></label>
            <label className="text-sm font-medium">证据状态<Select value={personaMatrixDraft.evidenceStatus} onValueChange={(value) => setPersonaMatrixDraft((current) => ({ ...current, evidenceStatus: value as ResearchBuyerFamilyLink["evidence_status"] }))}><SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="hypothesis">待验证假设</SelectItem><SelectItem value="partial">验证中</SelectItem><SelectItem value="validated">人工已验证</SelectItem></SelectContent></Select></label>
          </div>
          {globalBuyerMessage && <p role="alert" className="text-sm text-rose-700">{globalBuyerMessage}</p>}
          <DialogFooter><Button variant="outline" disabled={globalTaxonomyBusy} onClick={() => setPersonaMatrixEditorOpen(false)}>取消</Button><Button disabled={globalTaxonomyBusy} onClick={() => void savePersonaMatrix()}><Check /> 保存关系</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={globalBuyerCreateOpen} onOpenChange={(open) => { if (!globalBuyerBusy) { setGlobalBuyerCreateOpen(open); if (!open) setGlobalBuyerTarget(null); } }}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader><DialogTitle>{globalBuyerTarget ? "维护全球买家画像" : "新增全球批发买家"}</DialogTitle><DialogDescription>这是跨项目共享的主数据。必须记录真实组织和公开来源；AI 初筛不能代替询盘、访谈或订单验证。</DialogDescription></DialogHeader>
          <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-3 text-xs leading-5 text-cyan-950">画像保存后会成为未来调研项目的可复用起点。修改共享数据不会覆盖项目内已经形成的人工结论。</div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">公司 / 组织名<Input className="mt-1.5" value={globalBuyerDraft.companyName} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, companyName: event.target.value }))} maxLength={160} /></label>
            <label className="text-sm font-medium">国家 / 地区<Input className="mt-1.5" value={globalBuyerDraft.country} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, country: event.target.value }))} placeholder="例如：GB" maxLength={80} /></label>
            <label className="text-sm font-medium">画像分类<Select value={globalBuyerDraft.personaCode || undefined} onValueChange={(value) => setGlobalBuyerDraft((current) => ({ ...current, personaCode: value }))}><SelectTrigger className="mt-1.5"><SelectValue placeholder="选择标准画像分类" /></SelectTrigger><SelectContent>{globalPersonaCategories.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="text-sm font-medium">外贸地区<Select value={globalBuyerDraft.regionCode || undefined} onValueChange={(value) => setGlobalBuyerDraft((current) => ({ ...current, regionCode: value }))}><SelectTrigger className="mt-1.5"><SelectValue placeholder="按国家选择或自动判断" /></SelectTrigger><SelectContent>{globalTradeRegions.map((item) => <SelectItem key={item.code} value={item.code}>{item.name}</SelectItem>)}</SelectContent></Select></label>
            <label className="text-sm font-medium">公司自述 / 原始买家类型<Input className="mt-1.5" value={globalBuyerDraft.buyerType} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, buyerType: event.target.value }))} placeholder="例如：Industrial supplies distributor" maxLength={160} /></label>
            <label className="text-sm font-medium">画像状态<Select value={globalBuyerDraft.profileStatus} onValueChange={(value) => setGlobalBuyerDraft((current) => ({ ...current, profileStatus: value as ResearchBuyerProfile["profile_status"] }))}><SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="hypothesis">待核实</SelectItem><SelectItem value="qualified">已初筛</SelectItem><SelectItem value="validated">人工已验证</SelectItem><SelectItem value="rejected">已排除</SelectItem></SelectContent></Select></label>
            <label className="text-sm font-medium sm:col-span-2">公开来源链接（必填）<Input className="mt-1.5" type="url" value={globalBuyerDraft.sourceUrl} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, sourceUrl: event.target.value }))} placeholder="https://... 公司官网、公开采购页或可信名录" /></label>
            <label className="text-sm font-medium sm:col-span-2">公司官网（可选）<Input className="mt-1.5" type="url" value={globalBuyerDraft.website} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, website: event.target.value }))} /></label>
            <label className="text-sm font-medium">服务的终端客群<Textarea className="mt-1.5 min-h-20" value={globalBuyerDraft.customerGroups} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, customerGroups: event.target.value }))} /></label>
            <label className="text-sm font-medium">主要销售渠道<Textarea className="mt-1.5 min-h-20" value={globalBuyerDraft.salesChannels} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, salesChannels: event.target.value }))} /></label>
            <label className="text-sm font-medium sm:col-span-2">销售 / 采购场景<Textarea className="mt-1.5 min-h-24" value={globalBuyerDraft.purchasingScenarios} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, purchasingScenarios: event.target.value }))} /></label>
            <label className="text-sm font-medium">季节特点<Input className="mt-1.5" value={globalBuyerDraft.seasonality} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, seasonality: event.target.value }))} maxLength={1000} /></label>
            <label className="text-sm font-medium">补货 / 采购周期<Input className="mt-1.5" value={globalBuyerDraft.replenishmentCycle} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, replenishmentCycle: event.target.value }))} maxLength={500} /></label>
            <label className="text-sm font-medium sm:col-span-2">订单与供应要求<Textarea className="mt-1.5 min-h-20" value={globalBuyerDraft.orderRequirements} onChange={(event) => setGlobalBuyerDraft((current) => ({ ...current, orderRequirements: event.target.value }))} maxLength={2000} /></label>
          </div>
          {globalBuyerMessage && <p role="alert" className="text-sm text-rose-700">{globalBuyerMessage}</p>}
          <DialogFooter><Button variant="outline" disabled={globalBuyerBusy} onClick={() => setGlobalBuyerCreateOpen(false)}>取消</Button><Button disabled={globalBuyerBusy} onClick={() => void saveGlobalBuyer()}><Check /> {globalBuyerBusy ? "保存中…" : "保存到共享知识库"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(globalBuyerMatrixTarget)} onOpenChange={(open) => { if (!open && !globalBuyerMatrixBusy) setGlobalBuyerMatrixTarget(null); }}>
        <DialogContent className="max-h-[94vh] overflow-hidden sm:max-w-6xl">
          <DialogHeader><DialogTitle>全球买家—产品家族矩阵</DialogTitle><DialogDescription>{globalBuyerMatrixTarget ? `${globalBuyerMatrixTarget.company_name} · ${globalBuyerMatrixTarget.country}` : ""}。共享矩阵会被后续项目按市场和品类匹配，但不会自动升级为已验证采购关系。</DialogDescription></DialogHeader>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">关系分用于研究优先级排序，不代表采购额。矩阵关联的是稳定产品家族，具体单品仍在项目候选池内验证。</div>
          <Input value={globalBuyerFamilySearch} onChange={(event) => setGlobalBuyerFamilySearch(event.target.value)} placeholder="搜索赛道或产品家族" />
          <div className="max-h-[58vh] space-y-2 overflow-y-auto pr-1">
            {globalBuyerFamilyDrafts.filter((draft) => !globalBuyerFamilySearch.trim() || `${draft.trackCategory} ${draft.productFamily}`.toLocaleLowerCase().includes(globalBuyerFamilySearch.trim().toLocaleLowerCase())).map((draft) => (
              <div key={draft.key} className={`rounded-xl border p-3 ${draft.enabled ? "border-cyan-300 bg-cyan-50/40" : "bg-slate-50/50"}`}>
                <div className="grid items-start gap-3 lg:grid-cols-[150px_minmax(160px,1fr)_110px_150px_150px]">
                  <Button type="button" variant={draft.enabled ? "default" : "outline"} className="justify-start" onClick={() => setGlobalBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, enabled: !item.enabled } : item))}>{draft.enabled ? <Check /> : <Plus />}{draft.enabled ? "已关联" : "关联家族"}</Button>
                  <div><p className="text-sm font-medium">{draft.productFamily}</p><p className="mt-1 text-[11px] text-muted-foreground">{draft.trackCategory}</p></div>
                  <label className="text-xs font-medium">关系分<Input className="mt-1 h-9 bg-white" type="number" min={0} max={100} value={draft.relationshipScore} disabled={!draft.enabled} onChange={(event) => setGlobalBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, relationshipScore: Math.max(0, Math.min(100, Number(event.target.value) || 0)) } : item))} /></label>
                  <label className="text-xs font-medium">家族角色<Select value={draft.familyRole} disabled={!draft.enabled} onValueChange={(value) => setGlobalBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, familyRole: value as ResearchBuyerFamilyLink["family_role"] } : item))}><SelectTrigger className="mt-1 h-9 bg-white"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="core">核心常采</SelectItem><SelectItem value="cross_sell">跨品类加购</SelectItem><SelectItem value="seasonal">季节采购</SelectItem><SelectItem value="test">小单测试</SelectItem></SelectContent></Select></label>
                  <label className="text-xs font-medium">证据状态<Select value={draft.evidenceStatus} disabled={!draft.enabled} onValueChange={(value) => setGlobalBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, evidenceStatus: value as ResearchBuyerFamilyLink["evidence_status"] } : item))}><SelectTrigger className="mt-1 h-9 bg-white"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="hypothesis">待核实</SelectItem><SelectItem value="partial">部分证据</SelectItem><SelectItem value="validated">人工已验证</SelectItem></SelectContent></Select></label>
                </div>
                {draft.enabled && <div className="mt-3 grid gap-3 lg:grid-cols-2"><label className="text-xs font-medium">销售 / 采购场景<Input className="mt-1 bg-white" value={draft.salesScenarios} onChange={(event) => setGlobalBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, salesScenarios: event.target.value } : item))} /></label><label className="text-xs font-medium">关联理由与补证方法<Input className="mt-1 bg-white" value={draft.rationale} onChange={(event) => setGlobalBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, rationale: event.target.value } : item))} maxLength={1200} /></label></div>}
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3"><p className="text-xs text-muted-foreground">已选 {globalBuyerFamilyDrafts.filter((item) => item.enabled).length} / {globalBuyerFamilyDrafts.length} 个共享家族。</p>{globalBuyerMessage && <p role="alert" className="text-sm text-rose-700">{globalBuyerMessage}</p>}</div>
          <DialogFooter><Button variant="outline" disabled={globalBuyerMatrixBusy} onClick={() => setGlobalBuyerMatrixTarget(null)}>取消</Button><Button disabled={globalBuyerMatrixBusy} onClick={() => void saveGlobalBuyerMatrix()}><Check /> {globalBuyerMatrixBusy ? "保存中…" : "保存共享矩阵"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={researchBuyerCreateOpen} onOpenChange={(open) => { if (!researchBuyerBusy) { setResearchBuyerCreateOpen(open); if (!open) { setResearchBuyerTarget(null); setResearchBuyerMessage(""); } } }}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{researchBuyerTarget ? "维护真实买家画像" : "新增真实批发买家"}</DialogTitle>
            <DialogDescription>只记录可证明存在的具体公司或组织。公开来源可证明公司和业务场景，实际需求、采购量与复购周期仍需联系买家后人工确认。</DialogDescription>
          </DialogHeader>
          <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-3 text-xs leading-5 text-cyan-950">最低可用画像 = 公司名 + 国家/地区 + 买家类型 + 可直接打开的来源。AI 发现的记录最高只能到“已初筛”；“已验证”必须由你根据询盘、通话、会议或订单人工设置。</div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">公司 / 组织名<Input className="mt-1.5" value={researchBuyerDraft.companyName} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, companyName: event.target.value }))} placeholder="例如：ABC Wholesale Ltd" maxLength={160} /></label>
            <label className="text-sm font-medium">国家 / 地区<Input className="mt-1.5" value={researchBuyerDraft.country} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, country: event.target.value }))} placeholder="例如：GB 或 United Kingdom" maxLength={80} /></label>
            <label className="text-sm font-medium">买家类型<Input className="mt-1.5" value={researchBuyerDraft.buyerType} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, buyerType: event.target.value }))} placeholder="进口商、专业批发商、区域分销商…" maxLength={160} /></label>
            <label className="text-sm font-medium">画像状态
              <Select value={researchBuyerDraft.profileStatus} onValueChange={(value) => setResearchBuyerDraft((current) => ({ ...current, profileStatus: value as ResearchBuyerProfile["profile_status"] }))}>
                <SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="hypothesis">待核实</SelectItem><SelectItem value="qualified">已初筛</SelectItem><SelectItem value="validated">人工已验证</SelectItem><SelectItem value="rejected">已排除</SelectItem></SelectContent>
              </Select>
            </label>
            <label className="text-sm font-medium sm:col-span-2">公开来源链接（必填）<Input className="mt-1.5" type="url" value={researchBuyerDraft.sourceUrl} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, sourceUrl: event.target.value }))} placeholder="https://... 公司官网、公开采购页、展会名录或可核验商业目录" /></label>
            <label className="text-sm font-medium">公司官网（可选）<Input className="mt-1.5" type="url" value={researchBuyerDraft.website} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, website: event.target.value }))} placeholder="https://company.example" /></label>
            <label className="text-sm font-medium">Odoo CRM 线索 ID（可选）<Input className="mt-1.5" type="number" min={1} value={researchBuyerDraft.odooLeadId} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, odooLeadId: event.target.value }))} placeholder="仅关联已存在的线索" /></label>
            <label className="text-sm font-medium">服务的终端客群<Textarea className="mt-1.5 min-h-20" value={researchBuyerDraft.customerGroups} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, customerGroups: event.target.value }))} placeholder="礼品企业、学校、办公用户（换行或逗号分隔）" /></label>
            <label className="text-sm font-medium">主要销售渠道<Textarea className="mt-1.5 min-h-20" value={researchBuyerDraft.salesChannels} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, salesChannels: event.target.value }))} placeholder="区域经销网络、B2B 网站、线下门店…" /></label>
            <label className="text-sm font-medium sm:col-span-2">销售 / 采购场景<Textarea className="mt-1.5 min-h-24" value={researchBuyerDraft.purchasingScenarios} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, purchasingScenarios: event.target.value }))} placeholder="例如：学校开学季礼赠；办公室季节补货；企业定制项目" /></label>
            <label className="text-sm font-medium">季节特点<Input className="mt-1.5" value={researchBuyerDraft.seasonality} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, seasonality: event.target.value }))} placeholder="月份、节日、旺季或不明显" maxLength={1000} /></label>
            <label className="text-sm font-medium">补货 / 采购周期<Input className="mt-1.5" value={researchBuyerDraft.replenishmentCycle} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, replenishmentCycle: event.target.value }))} placeholder="待访谈确认；或公开证据中的周期" maxLength={500} /></label>
            <label className="text-sm font-medium sm:col-span-2">订单与供应要求<Textarea className="mt-1.5 min-h-20" value={researchBuyerDraft.orderRequirements} onChange={(event) => setResearchBuyerDraft((current) => ({ ...current, orderRequirements: event.target.value }))} placeholder="MOQ、定制、包装、交期、认证、付款方式；无证据的保持待核实" maxLength={2000} /></label>
          </div>
          {researchBuyerMessage && <p role="alert" className="text-sm text-rose-700">{researchBuyerMessage}</p>}
          <DialogFooter><Button variant="outline" disabled={researchBuyerBusy} onClick={() => setResearchBuyerCreateOpen(false)}>取消</Button><Button disabled={researchBuyerBusy} onClick={() => void saveResearchBuyer()}><Check /> {researchBuyerBusy ? "保存中…" : "保存买家画像"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(researchBuyerMatrixTarget)} onOpenChange={(open) => { if (!open && !researchBuyerMatrixBusy) { setResearchBuyerMatrixTarget(null); setResearchBuyerMessage(""); } }}>
        <DialogContent className="max-h-[94vh] overflow-hidden sm:max-w-6xl">
          <DialogHeader>
            <DialogTitle>买家—销售场景—产品家族矩阵</DialogTitle>
            <DialogDescription>{researchBuyerMatrixTarget ? `${researchBuyerMatrixTarget.company_name} · ${researchBuyerMatrixTarget.country} · ${researchBuyerMatrixTarget.buyer_type}` : ""}。先选定稳定采购场景，再关联核心常采、跨品类加购、季节采购或小单测试家族。</DialogDescription>
          </DialogHeader>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">关系分是 0–100 的机会排序，不是预测采购额。公开信息只能支持“待核实/部分证据”；必须有买家询盘、访谈、样品或订单证据才标记“已验证”。</div>
          <Input value={researchBuyerFamilySearch} onChange={(event) => setResearchBuyerFamilySearch(event.target.value)} placeholder="搜索赛道或产品家族" />
          <div className="max-h-[58vh] space-y-2 overflow-y-auto pr-1">
            {researchBuyerFamilyDrafts.filter((draft) => !researchBuyerFamilySearch.trim() || `${draft.trackCategory} ${draft.productFamily}`.toLocaleLowerCase().includes(researchBuyerFamilySearch.trim().toLocaleLowerCase())).map((draft) => (
              <div key={draft.key} className={`rounded-xl border p-3 ${draft.enabled ? "border-cyan-300 bg-cyan-50/40" : "bg-slate-50/50"}`}>
                <div className="grid items-start gap-3 lg:grid-cols-[150px_minmax(160px,1fr)_110px_150px_150px]">
                  <Button type="button" variant={draft.enabled ? "default" : "outline"} className="justify-start" onClick={() => setResearchBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, enabled: !item.enabled } : item))}>{draft.enabled ? <Check /> : <Plus />}{draft.enabled ? "已关联" : "关联家族"}</Button>
                  <div><p className="text-sm font-medium">{draft.productFamily}</p><p className="mt-1 text-[11px] text-muted-foreground">{draft.trackCategory}</p></div>
                  <label className="text-xs font-medium">关系分<Input className="mt-1 h-9 bg-white" type="number" min={0} max={100} value={draft.relationshipScore} disabled={!draft.enabled} onChange={(event) => setResearchBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, relationshipScore: Math.max(0, Math.min(100, Number(event.target.value) || 0)) } : item))} /></label>
                  <label className="text-xs font-medium">家族角色<Select value={draft.familyRole} disabled={!draft.enabled} onValueChange={(value) => setResearchBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, familyRole: value as ResearchBuyerFamilyLink["family_role"] } : item))}><SelectTrigger className="mt-1 h-9 bg-white"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="core">核心常采</SelectItem><SelectItem value="cross_sell">跨品类加购</SelectItem><SelectItem value="seasonal">季节采购</SelectItem><SelectItem value="test">小单测试</SelectItem></SelectContent></Select></label>
                  <label className="text-xs font-medium">证据状态<Select value={draft.evidenceStatus} disabled={!draft.enabled} onValueChange={(value) => setResearchBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, evidenceStatus: value as ResearchBuyerFamilyLink["evidence_status"] } : item))}><SelectTrigger className="mt-1 h-9 bg-white"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="hypothesis">待核实</SelectItem><SelectItem value="partial">部分证据</SelectItem><SelectItem value="validated">已验证</SelectItem></SelectContent></Select></label>
                </div>
                {draft.enabled && <div className="mt-3 grid gap-3 lg:grid-cols-2"><label className="text-xs font-medium">对应销售 / 采购场景<Input className="mt-1 bg-white" value={draft.salesScenarios} onChange={(event) => setResearchBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, salesScenarios: event.target.value } : item))} placeholder="换行或逗号分隔" /></label><label className="text-xs font-medium">关联理由与补证方法<Input className="mt-1 bg-white" value={draft.rationale} onChange={(event) => setResearchBuyerFamilyDrafts((current) => current.map((item) => item.key === draft.key ? { ...item, rationale: event.target.value } : item))} placeholder="为什么匹配；下一步向买家确认什么" maxLength={1200} /></label></div>}
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3"><p className="text-xs text-muted-foreground">已选 {researchBuyerFamilyDrafts.filter((item) => item.enabled).length} / {researchBuyerFamilyDrafts.length} 个家族。本次保存会精确更新该买家的矩阵，不会改动候选产品。</p>{researchBuyerMessage && <p role="alert" className="text-sm text-rose-700">{researchBuyerMessage}</p>}</div>
          <DialogFooter><Button variant="outline" disabled={researchBuyerMatrixBusy} onClick={() => setResearchBuyerMatrixTarget(null)}>取消</Button><Button disabled={researchBuyerMatrixBusy} onClick={() => void saveResearchBuyerMatrix()}><Check /> {researchBuyerMatrixBusy ? "保存中…" : "保存产品家族矩阵"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(researchRunTarget)} onOpenChange={(open) => { if (!open && !researchBusy) setResearchRunTarget(null); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{researchRunMode === "expand_candidates" ? "补充候选产品" : "确认复查这个项目？"}</DialogTitle>
            <DialogDescription>
              {researchRunTarget
                ? `项目“${researchRunTarget.product_name}”确认后会立即发送给 Codex / ChatGPT。当前已有 ${researchRunTarget.candidate_count || researchDetail?.candidates.length || 0} 个候选。`
                : "确认后会立即建立调研任务。"}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-4 text-sm leading-6 text-cyan-950">
            {researchRunMode === "expand_candidates"
              ? "本轮会优先新增不重复的具体产品，并补充赛道、市场、图片和来源。已有候选及人工阶段不会被覆盖。"
              : "本轮会复查已有结论、来源和产品状态；只有发现真实新方向时才增加候选。"}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button type="button" variant={researchRunMode === "expand_candidates" ? "default" : "outline"} onClick={() => setResearchRunMode("expand_candidates")}><Plus /> 补充产品池</Button>
            <Button type="button" variant={researchRunMode === "review" ? "default" : "outline"} onClick={() => setResearchRunMode("review")}><Bot /> 复查已有内容</Button>
          </div>
          <label className="text-sm font-medium">
            本项目候选产品目标数量
            <Input
              className="mt-1.5"
              type="number"
              min={1}
              max={2000}
              step={1}
              value={researchRunCandidateTarget}
              onChange={(event) => setResearchRunCandidateTarget(event.target.value)}
            />
            <span className="mt-1 block text-xs font-normal text-muted-foreground">可在每次复查时调整；已有候选不会因调低目标而删除。</span>
          </label>
          {researchRunMode === "expand_candidates" && (
            <label className="text-sm font-medium">
              本轮计划新增数量
              <Input
                className="mt-1.5"
                type="number"
                min={1}
                max={300}
                step={1}
                value={researchRunBatchCount}
                onChange={(event) => setResearchRunBatchCount(event.target.value)}
              />
              <span className="mt-1 block text-xs font-normal text-muted-foreground">每轮 1–300 个；建议先补充 50–100 个，完成后再继续下一轮。</span>
            </label>
          )}
          {researchMessage && <p className="text-xs text-muted-foreground">{researchMessage}</p>}
          <DialogFooter>
            <Button variant="outline" disabled={researchBusy} onClick={() => setResearchRunTarget(null)}>取消</Button>
            <Button disabled={researchBusy || Boolean(researchChannelJob)} onClick={() => void confirmResearchRun()}><Bot /> {researchBusy ? "正在发送…" : researchChannelJob ? "项目调研通道忙碌" : researchRunMode === "expand_candidates" ? "开始补充" : "开始复查"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(researchDeleteTarget)} onOpenChange={(open) => { if (!open && !researchDeleteBusy) setResearchDeleteTarget(null); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>确认永久删除这个调研项目？</DialogTitle>
            <DialogDescription>
              {researchDeleteTarget ? `将删除“${researchDeleteTarget.product_name}”。此操作无法撤销。` : "此操作无法撤销。"}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-900">
            项目的全部调研版本、来源证据和候选产品池会一起删除。正在执行中的项目不会被删除。
          </div>
          {researchDeleteMessage && <p className="text-xs text-rose-700">{researchDeleteMessage}</p>}
          <DialogFooter>
            <Button variant="outline" disabled={researchDeleteBusy} onClick={() => setResearchDeleteTarget(null)}>取消</Button>
            <Button variant="destructive" disabled={researchDeleteBusy} onClick={() => void deleteResearchProject()}><Trash2 /> {researchDeleteBusy ? "正在删除…" : "确认永久删除"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={researchCreateOpen} onOpenChange={setResearchCreateOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>建立产品与市场调研项目</DialogTitle>
            <DialogDescription>可直接写完整经营要求并一键交给 Codex / ChatGPT。项目、每轮报告和来源证据都会持续保存。</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">项目主题 / 产品方向（可选）<Input className="mt-1.5" value={researchProductName} onChange={(event) => setResearchProductName(event.target.value)} placeholder="留空时自动命名为“多品类产品外贸调研”" maxLength={120} /></label>
            <label className="text-sm font-medium">产品大类<Input className="mt-1.5" value={researchCategory} onChange={(event) => setResearchCategory(event.target.value)} placeholder="例如：小家电、数码、医疗电子" maxLength={120} /></label>
            <div className="sm:col-span-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label htmlFor="research-ai-brief" className="text-sm font-medium">给 Codex / ChatGPT 的完整任务</label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setResearchProductName("电子类产品外贸启动方案");
                    setResearchCategory("小家电、数码、医疗电子");
                    setResearchMarkets(["GLOBAL"]);
                    setResearchObjectives("我准备做电子类产品外贸，包括小家电、数码类和医疗电子等产品。请建立一份可长期维护、可以落地执行的在线外贸启动方案，前期总预算控制在人民币5万元以内，由2人执行。按11个模块持续更新：总览与边界、大赛道地图、候选产品池、筛选机制、市场映射、180天路线、两人SOP、预算与报价、合规供应链、获客与成交、执行清单。产品池按大赛道、细分领域和具体国家市场分批扩充、自动去重；每款产品说明需求证据、客户类型、竞争价格带、采购与MOQ、合规物流、预算投入、风险、优先级和验证阶段。不能核验的数据保持未知，不得为凑数编造。");
                    setResearchConstraints("前期总预算不超过人民币5万元；团队2人；优先低门槛、可小批量验证、现金周转快的产品。医疗电子必须单独说明法规和准入门槛。");
                  }}
                >
                  <Sparkles /> 填入外贸方案示例
                </Button>
              </div>
              <Textarea
                id="research-ai-brief"
                className="mt-1.5 min-h-32"
                value={researchObjectives}
                onChange={(event) => setResearchObjectives(event.target.value)}
                placeholder="例如：我准备做电子类产品外贸……预算5万元以内，由2人执行；请按产品大类和国家/地区给出尽可能多的判断和落地计划。"
                maxLength={6000}
              />
              <p className="mt-1 text-xs text-muted-foreground">预算、人数、品类、国家、目标客户、渠道和输出格式都可以直接写在这里。</p>
            </div>
            <label className="text-sm font-medium sm:col-span-2">已有产品或资源说明（可选）<Textarea className="mt-1.5 min-h-20" value={researchDescription} onChange={(event) => setResearchDescription(event.target.value)} placeholder="已有供应链、擅长产品、认证、客户资源、目标客单或差异点" maxLength={2000} /></label>
            <label className="text-sm font-medium">目标国家<ResearchMarketMultiSelect value={researchMarkets} onValueChange={setResearchMarkets} /><span className="mt-1 block text-xs font-normal text-muted-foreground">可跨地区选择多个国家；选择“全球”时按多地区研究。</span></label>
            <label className="text-sm font-medium">研究语言<ResearchLanguageMultiSelect value={researchLanguages} onValueChange={setResearchLanguages} /><span className="mt-1 block text-xs font-normal text-muted-foreground">可搜索并选择多种语言；系统会保存标准语言代码。</span></label>
            <label className="text-sm font-medium">调研模板
              <Select value={researchTemplateId} onValueChange={setResearchTemplateId}>
                <SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger>
                <SelectContent>{(researchData?.templates ?? []).map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
              </Select>
            </label>
            <label className="text-sm font-medium">候选产品目标数量
              <Input
                className="mt-1.5"
                type="number"
                min={1}
                max={2000}
                step={1}
                value={researchTargetCandidateCount}
                onChange={(event) => setResearchTargetCandidateCount(event.target.value)}
              />
              <span className="mt-1 block text-xs font-normal text-muted-foreground">1–2000 个；数量较大时 AI 会分轮补充并自动去重。</span>
            </label>
            <div className="sm:col-span-2 rounded-xl border border-cyan-200 bg-cyan-50 p-3">
              <div className="flex items-start gap-2"><Database className="mt-0.5 size-4 shrink-0 text-cyan-800" /><div><p className="text-sm font-medium text-cyan-950">自动复用全球商业分类与真实买家证据</p><p className="mt-1 text-xs leading-5 text-cyan-900/75">系统先按目标国家匹配 {globalBuyerLibrary?.stats.regionCount ?? 0} 个地区，再从 {globalBuyerLibrary?.stats.personaCategoryCount ?? 0} 个画像分类、{globalBuyerLibrary?.stats.trackCount ?? 0} 个赛道、{globalBuyerLibrary?.stats.masterFamilyCount ?? 0} 个产品家族和 {globalBuyerLibrary?.stats.profileCount ?? 0} 家真实公司中生成研究起点；分类关系仍需用当前项目证据重新验证。</p></div></div>
            </div>
            <div className="sm:col-span-2">
              <p className="text-sm font-medium">优先数据与证据渠道</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {RESEARCH_CHANNEL_OPTIONS.map(([id, label]) => {
                  const selectedChannel = researchChannels.includes(id);
                  return <Button key={id} type="button" size="sm" variant={selectedChannel ? "default" : "outline"} onClick={() => setResearchChannels((current) => selectedChannel ? current.filter((item) => item !== id) : [...current, id])}>{selectedChannel && <Check />} {label}</Button>;
                })}
              </div>
            </div>
            <label className="text-sm font-medium sm:col-span-2">已知约束（可选）<Textarea className="mt-1.5 min-h-20" value={researchConstraints} onChange={(event) => setResearchConstraints(event.target.value)} placeholder="预算、MOQ、认证、交期、不能做的功能或渠道" maxLength={2000} /></label>
          </div>
          {researchMessage && <p className="text-sm text-cyan-800">{researchMessage}</p>}
          <DialogFooter>
            <Button variant="outline" disabled={researchBusy} onClick={() => setResearchCreateOpen(false)}>取消</Button>
            <Button variant="outline" disabled={researchBusy || !researchObjectives.trim()} onClick={() => void createResearchProject(false)}><Plus /> 仅保存项目</Button>
            <Button disabled={researchBusy || !researchObjectives.trim() || Boolean(researchChannelJob)} onClick={() => void createResearchProject(true)}><Bot /> {researchBusy ? "正在处理…" : researchChannelJob ? "项目调研通道忙碌" : "保存并让 AI 开始调研"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deleteBusy) {
            setDeleteTarget(null);
            setDeleteMessage("");
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>删除这条任务记录？</DialogTitle>
            <DialogDescription>
              删除后，该任务的历史记录、观测证据和评分会一起清理，且无法恢复。
            </DialogDescription>
          </DialogHeader>
          {deleteTarget && (
            <div className="rounded-xl border bg-slate-50 p-4">
              <p className="font-medium">{deleteTarget.query}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge variant="outline">国家：{marketNameForCode(deleteTarget.market)}（{deleteTarget.market}）</Badge>
                <Badge variant="outline">语种：{languageNameForCode(deleteTarget.language)}（{deleteTarget.language.toUpperCase()}）</Badge>
                <Badge variant="outline">近 {deleteTarget.window_days} 天</Badge>
                <Badge variant="secondary">任务：{taskTypeLabel(deleteTarget)}</Badge>
                <Badge variant="secondary">处理：{PROCESSING_METHOD_LABELS[processingMethod(deleteTarget)] ?? processingMethod(deleteTarget)}</Badge>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                {deleteTarget.cluster_count} 个词簇 · {deleteTarget.observation_count} 条观测 · {new Date(deleteTarget.created_at).toLocaleString("zh-CN")}
              </p>
            </div>
          )}
          {deleteMessage && <p role="alert" className="text-sm text-destructive">{deleteMessage}</p>}
          <DialogFooter>
            <Button variant="outline" disabled={deleteBusy} onClick={() => setDeleteTarget(null)}>取消</Button>
            <Button variant="destructive" disabled={deleteBusy} onClick={deleteHistoryRun}>
              <Trash2 /> {deleteBusy ? "正在删除…" : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={assistantOpen} onOpenChange={setAssistantOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>选择 AI 整理通道</DialogTitle>
            <DialogDescription>
              处理“{query || "尚未填写"}” · {marketNameForCode(market)}（{market}） · {languageNameForCode(language)}（{language.toUpperCase()}） · 近 {windowDays} 天。AI 是处理方式，任务仍保留为“{scanMode === "discover" ? "热点发现" : "关键词扫描"}”。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-[160px_1fr] sm:items-center">
              <label htmlFor="result-limit" className="text-sm font-medium">目标关键词簇数量</label>
              <div className="flex flex-wrap items-center gap-3">
                <Select value={resultLimit} onValueChange={setResultLimit}>
                  <SelectTrigger id="result-limit" className="w-36" aria-label="目标关键词簇数量"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="10">10 个</SelectItem>
                    <SelectItem value="15">15 个</SelectItem>
                    <SelectItem value="20">20 个</SelectItem>
                  </SelectContent>
                </Select>
                <span className="text-xs text-muted-foreground">默认 20；平台与结果越多，整理时间越长。</span>
              </div>
            </div>
            <label className="block text-sm font-medium">
              整理要求（可选）
              <textarea
                value={assistantRequest}
                onChange={(event) => setAssistantRequest(event.target.value)}
                className="mt-2 min-h-24 w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                maxLength={1000}
              />
            </label>
            <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-cyan-950">Codex 关键词雷达通道（推荐）</p>
                  <p className="mt-1 text-xs leading-5 text-cyan-900/75">无需在网页填写 OpenAI API Key。本任务只占用关键词雷达通道，不会阻塞产品调研、整项目调研或图片采集。</p>
                </div>
                <Badge variant="outline" className="border-cyan-300 bg-white text-cyan-800">
                  {codexChannelState === "ready" ? "自动通道已连接" : codexChannelState === "checking" ? "正在检测" : "重启雷达后启用"}
                </Badge>
              </div>
              <Button className="mt-3 bg-cyan-800 text-white hover:bg-cyan-700" disabled={busy || !query.trim() || Boolean(radarChannelJob)} onClick={prepareCodexTask}>
                <Bot /> {busy ? "正在发送…" : radarChannelJob ? "关键词雷达通道忙碌" : "直接发送到 Codex"}
              </Button>
              <p className="mt-2 text-xs text-cyan-900/70">发送后可在 Codex 任务列表打开“LightLink Radar 关键词雷达”查看过程；结果自动写回本页。</p>
            </div>
            <div className="border-t pt-4">
              <p className="text-sm font-medium">OpenAI API 直连（可选）</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">适合以后在线部署并在网页内直接完成。API 通常按量计费。</p>
              {!openAiIntegration?.configured && (
                <label className="mt-3 block text-sm font-medium">
                  OpenAI API Key（仅保留在本页内存，本次请求使用）
                  <Input className="mt-2" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="sk-…" autoComplete="off" />
                </label>
              )}
            </div>
            <p className="text-sm leading-6 text-muted-foreground">{assistantMessage}</p>
          </div>
          <DialogFooter className="sm:justify-between">
            <Button variant="ghost" onClick={() => { setAssistantOpen(false); void runScan(scanMode); }}>只建立待采集任务</Button>
            <Button disabled={busy || !query.trim()} onClick={runAssistant}><Sparkles /> {busy ? "正在整理…" : "使用 OpenAI API"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={apiOpen} onOpenChange={setApiOpen}>
        <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{selectedCredential?.name ?? "数据源连接"}</DialogTitle>
            <DialogDescription>
              连接信息只提交给本机服务端并整体加密保存；保存后页面、接口和日志均不回显原内容。
            </DialogDescription>
          </DialogHeader>
          {selectedCredential ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-cyan-200 bg-cyan-50/60 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <KeyRound className="size-4 text-cyan-800" />
                      <Badge variant={selectedCredential.configured ? "secondary" : "outline"}>
                        {selectedCredential.source === "managed" ? "已加密保存" : selectedCredential.source === "environment" ? "环境变量已配置" : selectedCredential.source === "public" ? "公开接口已可用" : "未配置"}
                      </Badge>
                      {selectedCredential.lastTestStatus && (
                        <Badge variant="outline" className={selectedCredential.lastTestStatus === "ok" ? "border-emerald-300 text-emerald-800" : "border-amber-300 text-amber-800"}>
                          {selectedCredential.lastTestStatus === "ok"
                            ? "连接正常"
                            : selectedCredential.lastTestStatus === "rate_limited"
                              ? "配额受限"
                              : selectedCredential.lastTestStatus === "unverified"
                                ? "待实采验证"
                                : "测试失败"}
                        </Badge>
                      )}
                    </div>
                    <p className="mt-2 text-sm leading-6 text-cyan-950">{selectedCredential.instructions}</p>
                    {selectedCredential.updatedAt && <p className="mt-1 text-xs text-muted-foreground">最近更新：{new Date(selectedCredential.updatedAt).toLocaleString("zh-CN")}</p>}
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" asChild><a href={selectedCredential.registerUrl} target="_blank" rel="noreferrer">官方入口 <ExternalLink /></a></Button>
                    <Button variant="ghost" size="sm" asChild><a href={selectedCredential.docsUrl} target="_blank" rel="noreferrer">说明 <ExternalLink /></a></Button>
                  </div>
                </div>
                {!selectedCredential.storageReady && !selectedCredential.publicAccess && (
                  <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">密钥保险箱将在重新启动 LightLink 时自动初始化。请重启后再保存。</p>
                )}
              </div>

              {selectedCredential.publicAccess ? (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-950">
                  该来源使用官方公开接口，不需要申请或保存 API Key，系统可直接调用。
                </div>
              ) : (
                <div className="space-y-3 rounded-xl border p-4">
                  {selectedCredential.configured && <p className="text-xs leading-5 text-muted-foreground">已保存内容不会回显。更新时请重新填写所有必填项，保存后输入框会自动清空。</p>}
                  {selectedCredential.fields.map((field) => (
                    <label key={field.id} className="block text-sm font-medium text-slate-700">
                      {field.label}{!field.required && <span className="ml-1 font-normal text-muted-foreground">（可选）</span>}
                      <Input
                        className="mt-1.5"
                        type={field.type === "password" ? "password" : field.type}
                        value={credentialDrafts[selectedCredential.id]?.[field.id] ?? ""}
                        onChange={(event) => setCredentialDrafts((current) => ({
                          ...current,
                          [selectedCredential.id]: {
                            ...(current[selectedCredential.id] ?? {}),
                            [field.id]: event.target.value,
                          },
                        }))}
                        placeholder={selectedCredential.configured ? `${field.placeholder}（重新填写后更新）` : field.placeholder}
                        autoComplete="new-password"
                        spellCheck={false}
                      />
                    </label>
                  ))}
                </div>
              )}

              {!selectedCredential.publicAccess && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    disabled={!selectedCredential.storageReady || selectedCredential.fields.some((field) => field.required && !credentialDrafts[selectedCredential.id]?.[field.id]?.trim()) || Boolean(credentialBusy)}
                    onClick={() => void saveManagedCredential(selectedCredential.id)}
                  >
                    <KeyRound /> {credentialBusy === `${selectedCredential.id}:save` ? "正在保存…" : selectedCredential.configured ? "更新连接" : "加密保存"}
                  </Button>
                  {selectedCredential.testable && (
                    <Button variant="outline" size="sm" disabled={!selectedCredential.configured || Boolean(credentialBusy)} onClick={() => void testManagedCredential(selectedCredential.id)}>
                      {credentialBusy === `${selectedCredential.id}:test` ? "正在测试…" : "测试连接"}
                    </Button>
                  )}
                  {selectedCredential.source === "managed" && (
                    <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700" disabled={Boolean(credentialBusy)} onClick={() => void deleteManagedCredential(selectedCredential.id)}>
                      <Trash2 /> 删除
                    </Button>
                  )}
                </div>
              )}
              {selectedCredential.lastTestMessage && <p className="text-xs leading-5 text-muted-foreground">{selectedCredential.lastTestMessage}</p>}
              {credentialMessage && <p role="status" className="rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm text-cyan-950">{credentialMessage}</p>}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">正在读取数据源配置…</p>
          )}
          <DialogFooter>
            <Button onClick={() => setApiOpen(false)}>完成</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>导入采集证据</DialogTitle>
            <DialogDescription>
              每行是一条平台观测。系统会增量合并、严格校验，并用固定公式重新计算评分。
            </DialogDescription>
          </DialogHeader>
          {pendingRunId && (
            <div className="rounded-lg border border-cyan-200 bg-cyan-50 p-3 text-sm text-cyan-950">
              <div className="flex items-center gap-2 font-medium"><Bot className="size-4" /> AI 采集任务已建立</div>
              <p className="mt-1 text-xs leading-5">任务编号 {pendingRunId.slice(0, 8)}。可让 ChatGPT 采集后写回，也可直接导入平台导出文件。</p>
            </div>
          )}
          <div className="space-y-3">
            <Input ref={fileRef} type="file" accept=".json,.csv,.tsv,text/csv,application/json" aria-label="选择数据文件" />
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>{importMessage}</span>
              <a className="font-medium text-cyan-800 hover:underline" href="/import-template.csv" download>
                下载字段模板
              </a>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">
              必填字段：keyword、platform、metric、coverageDays、sourceKind、geoScope、status、collectedAt。
              metric 使用 attention、commercial 或 competition；可选 keywordZh、imageUrl（兼容单图）或 imageUrls + imageSourceRef（最多 6 张）、purchasePriceMin / Max / Currency / Unit 用于中文品名、可追溯产品图片和采购价范围。
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)}>稍后处理</Button>
            <Button disabled={busy} onClick={importFile}><FileUp /> 校验并导入</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
