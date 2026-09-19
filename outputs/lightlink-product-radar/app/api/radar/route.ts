import { getRawDb } from "@/db";
import { env } from "cloudflare:workers";
import { DEMO_OBSERVATIONS } from "@/lib/demo";
import {
  MARKET_CODES,
  SUPPORTED_LANGUAGES,
  SUPPORTED_MARKETS,
  defaultLanguageForMarket,
  marketNameForCode,
} from "@/lib/markets";
import {
  COMMERCE_PLATFORMS,
  CORE_PLATFORMS,
  SCORE_VERSION,
  VALID_PLATFORMS,
  computeScores,
  expandSeedKeyword,
  normalizeKeyword,
  safeCsvCell,
  splitKeywords,
  type IncomingObservation,
} from "@/lib/radar";
import { latestResearchReportRun, mergeResearchReports } from "@/lib/research-versions";
import {
  candidateHandoffReadiness,
  normalizeCandidateSelectionAssessment,
} from "@/lib/candidate-selection";
import { buildProjectBuyerKnowledge } from "@/lib/buyer-library";
import {
  OPPORTUNITY_SIGNAL_FIELDS,
  computeOpportunityScores,
  normalizeOpportunitySignals,
  type OpportunityEvidenceGrade,
} from "@/lib/opportunity";
import {
  TRADE_COLLECTION_POLICIES,
  isTradeCacheFresh,
  normalizeTradeCollectionLevel,
  normalizeTradeObservation,
  tradeCollectionLevelForOpportunityStatus,
  tradeCoverageLevel,
  tradeCoverageSatisfies,
} from "@/lib/trade-data";
import {
  BUYER_PERSONA_SEEDS,
  PERSONA_FAMILY_AFFINITY_SEEDS,
  PERSONA_TRACK_AFFINITY_SEEDS,
  PRODUCT_FAMILY_SEEDS,
  PRODUCT_TRACK_SEEDS,
  TRADE_REGION_SEEDS,
  regionCodeForCountry,
  suggestPersonaCode,
} from "@/lib/commercial-taxonomy";
import {
  decryptCredential,
  encryptCredential,
  parseEncryptedCredential,
} from "@/lib/credential-vault";
import {
  INTELLIGENCE_SOURCE_CATALOG,
  MARKET_SIGNAL_LAYERS,
  MONITOR_SIMULATION_SCENARIOS,
  TRIGGER_CATALOG,
  assessSignalOpportunity,
  marketSignalFingerprint,
  monitorScopeKey,
  simulateMonitorScenario,
  triggerById,
  type AssessableMarketSignal,
  type MarketSignalType,
  type MonitorSimulationScenario,
} from "@/lib/intelligence-station";
import {
  collectOfficialTradeSignals,
  normalizeCommodityCodes,
  type OfficialTradeConnectorResult,
} from "@/lib/intelligence-connectors";

export const dynamic = "force-dynamic";

type JsonRecord = Record<string, unknown>;

function asObject(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function jsonArray(value: unknown) {
  try {
    return Array.isArray(value) ? value : JSON.parse(String(value ?? "[]"));
  } catch {
    return [];
  }
}

function jsonObject(value: unknown) {
  try {
    return asObject(typeof value === "string" ? JSON.parse(value) : value);
  } catch {
    return {};
  }
}

function nowIso() {
  return new Date().toISOString();
}

const RESEARCH_TEMPLATES = [
  {
    id: "portfolio_launch_plan",
    name: "多品类外贸启动方案",
    description: "适合预算、团队和品类范围已经明确的创业调研，输出产品大类 × 国家地区矩阵、预算分配和执行计划。",
  },
  {
    id: "battery_gadget_export",
    name: "数码小家电外贸启动",
    description: "适合带电池、芯片或低压电子产品，重点核验合规、供应链、价格与买家渠道。",
  },
  {
    id: "general_validation",
    name: "通用产品机会验证",
    description: "适合多数外贸产品，从需求、竞争、供应、利润和可执行性形成进入建议。",
  },
  {
    id: "buyer_competition",
    name: "买家与竞争专项",
    description: "聚焦目标买家、渠道结构、竞品价格带、差评空档和采购触发条件。",
  },
] as const;

const RESEARCH_SECTIONS = [
  "product_definition",
  "market_demand",
  "competition_pricing",
  "buyers_channels",
  "supply_moq",
  "compliance_logistics",
  "unit_economics",
  "recommendation_actions",
] as const;

const RESEARCH_CHANNELS = new Set([
  "google_trends",
  "social_content",
  "alibaba",
  "amazon",
  "ebay",
  "walmart",
  "temu",
  "shein",
  "regional_commerce",
  "official_regulation",
  "buyer_websites",
]);

let researchSchemaReady = false;
let intelligenceSchemaReady = false;

async function seedCommercialTaxonomy() {
  const db = getRawDb();
  const timestamp = nowIso();
  const statements: D1PreparedStatement[] = [];
  for (const item of TRADE_REGION_SEEDS) {
    statements.push(db.prepare(`INSERT OR IGNORE INTO trade_regions
      (code, name, macro_region, m49_code, countries, characteristics, source_url, active, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'system_seed', ?, ?)`)
      .bind(item.code, item.name, item.macroRegion, item.m49Code, JSON.stringify(item.countries),
        JSON.stringify(item.characteristics), item.sourceUrl, timestamp, timestamp));
  }
  for (const item of BUYER_PERSONA_SEEDS) {
    statements.push(db.prepare(`INSERT OR IGNORE INTO buyer_persona_categories
      (code, group_name, name, description, value_chain_role, customer_groups, sales_channels,
       purchase_scenarios, buying_triggers, order_characteristics, compliance_focus, source_refs, version,
       last_reviewed_at, active, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, 'system_seed', ?, ?)`)
      .bind(item.code, item.groupName, item.name, item.description, item.valueChainRole,
        JSON.stringify(item.customerGroups), JSON.stringify(item.salesChannels), JSON.stringify(item.purchaseScenarios),
        JSON.stringify(item.buyingTriggers), JSON.stringify(item.orderCharacteristics), JSON.stringify(item.complianceFocus),
        JSON.stringify(item.sourceRefs), timestamp, timestamp, timestamp));
    statements.push(db.prepare(`UPDATE buyer_persona_categories SET source_refs = ?, last_reviewed_at = ?
      WHERE code = ? AND created_by = 'system_seed' AND (source_refs = '' OR source_refs = '[]')`)
      .bind(JSON.stringify(item.sourceRefs), timestamp, item.code));
  }
  for (const item of PRODUCT_TRACK_SEEDS) {
    statements.push(db.prepare(`INSERT OR IGNORE INTO product_tracks
      (code, name, description, buyer_value, compliance_focus, active, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, 1, 'system_seed', ?, ?)`)
      .bind(item.code, item.name, item.description, item.buyerValue, JSON.stringify(item.complianceFocus), timestamp, timestamp));
  }
  for (const item of PRODUCT_FAMILY_SEEDS) {
    statements.push(db.prepare(`INSERT OR IGNORE INTO product_family_master
      (code, track_code, name, description, use_scenarios, compliance_tags, keywords, active, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'system_seed', ?, ?)`)
      .bind(item.code, item.trackCode, item.name, item.description, JSON.stringify(item.useScenarios),
        JSON.stringify(item.complianceTags), JSON.stringify(item.keywords), timestamp, timestamp));
  }
  for (const item of PERSONA_TRACK_AFFINITY_SEEDS) {
    statements.push(db.prepare(`INSERT OR IGNORE INTO persona_product_matrix
      (id, persona_code, region_code, track_code, product_family_code, relevance_score, family_role,
       sales_scenarios, seasonality, rationale, evidence_status, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, '', ?, ?, '[]', '', ?, 'hypothesis', 'system_seed', ?, ?)`)
      .bind(`${item.personaCode}:${item.regionCode}:${item.trackCode}:*`, item.personaCode, item.regionCode,
        item.trackCode, item.relevanceScore, item.familyRole, item.rationale, timestamp, timestamp));
  }
  for (const item of PERSONA_FAMILY_AFFINITY_SEEDS) {
    statements.push(db.prepare(`INSERT OR IGNORE INTO persona_product_matrix
      (id, persona_code, region_code, track_code, product_family_code, relevance_score, family_role,
       sales_scenarios, seasonality, rationale, evidence_status, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '', ?, 'hypothesis', 'system_seed', ?, ?)`)
      .bind(`${item.personaCode}:${item.regionCode}:${item.trackCode}:${item.productFamilyCode}`,
        item.personaCode, item.regionCode, item.trackCode, item.productFamilyCode,
        item.relevanceScore, item.familyRole, item.rationale, timestamp, timestamp));
  }
  for (let index = 0; index < statements.length; index += 100) await db.batch(statements.slice(index, index + 100));

  const desiredMatrixIds = new Set([
    ...PERSONA_TRACK_AFFINITY_SEEDS.map((item) => `${item.personaCode}:${item.regionCode}:${item.trackCode}:*`),
    ...PERSONA_FAMILY_AFFINITY_SEEDS.map((item) => `${item.personaCode}:${item.regionCode}:${item.trackCode}:${item.productFamilyCode}`),
  ]);
  const seededRows = await db.prepare("SELECT id FROM persona_product_matrix WHERE created_by = 'system_seed'").all<{ id: string }>();
  const staleStatements = seededRows.results
    .filter((row) => !desiredMatrixIds.has(String(row.id)))
    .map((row) => db.prepare("DELETE FROM persona_product_matrix WHERE id = ? AND created_by = 'system_seed'").bind(row.id));
  for (let index = 0; index < staleStatements.length; index += 100) await db.batch(staleStatements.slice(index, index + 100));
}

async function classifyUnmappedGlobalBuyers() {
  const db = getRawDb();
  const rows = await db.prepare(`SELECT id, country, buyer_type, customer_groups, sales_channels, purchasing_scenarios
    FROM global_buyer_profiles
    WHERE persona_code = '' OR region_code = ''`).all<JsonRecord>();
  if (!rows.results.length) return;
  const statements = rows.results.map((row) => db.prepare(`UPDATE global_buyer_profiles
    SET persona_code = CASE WHEN persona_code = '' THEN ? ELSE persona_code END,
        region_code = CASE WHEN region_code = '' THEN ? ELSE region_code END
    WHERE id = ?`).bind(
      suggestPersonaCode(String(row.buyer_type ?? ""), ...stringList(row.customer_groups), ...stringList(row.sales_channels), ...stringList(row.purchasing_scenarios)),
      regionCodeForCountry(String(row.country ?? "")),
      row.id,
    ));
  for (let index = 0; index < statements.length; index += 100) await db.batch(statements.slice(index, index + 100));
}

function stringList(value: unknown, maxItems = 30): string[] {
  return [...new Set<string>(jsonArray(value).map((item: unknown) => String(item).trim()).filter(Boolean))].slice(0, maxItems);
}

function boundedNumber(value: unknown, min: number, max: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : 0;
}

function boundedOptionalNumber(value: unknown, min: number, max: number) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : null;
}

function reportText(value: unknown, maxLength = 500) {
  return String(value ?? "").trim().slice(0, maxLength);
}

async function ensureResearchSchema() {
  if (researchSchemaReady) return;
  const db = getRawDb();
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS research_projects (
      id text PRIMARY KEY NOT NULL,
      product_name text NOT NULL,
      product_category text DEFAULT '' NOT NULL,
      product_description text DEFAULT '' NOT NULL,
      target_markets text DEFAULT '[]' NOT NULL,
      languages text DEFAULT '[]' NOT NULL,
      channels text DEFAULT '[]' NOT NULL,
      template_id text DEFAULT 'general_validation' NOT NULL,
      target_candidate_count integer DEFAULT 2000 NOT NULL,
      objectives text DEFAULT '' NOT NULL,
      constraints text DEFAULT '' NOT NULL,
      status text DEFAULT 'planning' NOT NULL,
      current_stage text DEFAULT 'product_definition' NOT NULL,
      progress integer DEFAULT 10 NOT NULL,
      summary text DEFAULT '' NOT NULL,
      recommendation text DEFAULT 'pending' NOT NULL,
      scorecard text DEFAULT '{}' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      last_researched_at text
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_projects_updated_at ON research_projects (updated_at)"),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_projects_status ON research_projects (status)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS research_runs (
      id text PRIMARY KEY NOT NULL,
      project_id text NOT NULL,
      status text DEFAULT 'waiting_for_codex' NOT NULL,
      request_payload text DEFAULT '{}' NOT NULL,
      result_payload text DEFAULT '{}' NOT NULL,
      source_summary text DEFAULT '{}' NOT NULL,
      codex_thread_id text,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      completed_at text,
      FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_runs_project_created ON research_runs (project_id, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS research_evidence (
      id text PRIMARY KEY NOT NULL,
      project_id text NOT NULL,
      run_id text NOT NULL,
      section_key text NOT NULL,
      source_type text DEFAULT 'public_web' NOT NULL,
      source_title text DEFAULT '' NOT NULL,
      source_url text DEFAULT '' NOT NULL,
      market text DEFAULT '' NOT NULL,
      status text DEFAULT 'available' NOT NULL,
      excerpt text DEFAULT '' NOT NULL,
      metrics text DEFAULT '{}' NOT NULL,
      captured_at text NOT NULL,
      FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE,
      FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_evidence_project_run ON research_evidence (project_id, run_id)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS research_candidates (
      id text PRIMARY KEY NOT NULL,
      project_id text NOT NULL,
      fingerprint text NOT NULL,
      name text NOT NULL,
      track_category text DEFAULT '' NOT NULL,
      subcategory text DEFAULT '' NOT NULL,
      product_family text DEFAULT '' NOT NULL,
      commercial_variant text DEFAULT '' NOT NULL,
      image_urls text DEFAULT '[]' NOT NULL,
      image_source_ref text DEFAULT '' NOT NULL,
      target_markets text DEFAULT '[]' NOT NULL,
      buyer_types text DEFAULT '[]' NOT NULL,
      price_band text DEFAULT '' NOT NULL,
      moq text DEFAULT '' NOT NULL,
      compliance text DEFAULT '[]' NOT NULL,
      risk_level text DEFAULT 'unknown' NOT NULL,
      stage text DEFAULT 'idea' NOT NULL,
      score real,
      rationale text DEFAULT '' NOT NULL,
      evidence_status text DEFAULT 'hypothesis' NOT NULL,
      selection_assessment text DEFAULT '{}' NOT NULL,
      odoo_sync_state text DEFAULT 'not_synced' NOT NULL,
      odoo_external_id text DEFAULT '' NOT NULL,
      odoo_synced_at text,
      source_run_id text,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE(project_id, fingerprint),
      FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE,
      FOREIGN KEY (source_run_id) REFERENCES research_runs(id) ON DELETE SET NULL
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_candidates_project_stage ON research_candidates (project_id, stage)"),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_candidates_project_track ON research_candidates (project_id, track_category)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS research_candidate_activities (
      id text PRIMARY KEY NOT NULL,
      project_id text NOT NULL,
      candidate_id text NOT NULL,
      from_stage text DEFAULT '' NOT NULL,
      to_stage text DEFAULT '' NOT NULL,
      note text DEFAULT '' NOT NULL,
      evidence_url text DEFAULT '' NOT NULL,
      next_action text DEFAULT '' NOT NULL,
      follow_up_at text DEFAULT '' NOT NULL,
      recommended_stage text DEFAULT '' NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE,
      FOREIGN KEY (candidate_id) REFERENCES research_candidates(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_candidate_activities_candidate_created ON research_candidate_activities (candidate_id, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS research_market_activities (
      id text PRIMARY KEY NOT NULL,
      project_id text NOT NULL,
      market_code text NOT NULL,
      from_status text DEFAULT 'hypothesis' NOT NULL,
      to_status text DEFAULT 'hypothesis' NOT NULL,
      note text DEFAULT '' NOT NULL,
      evidence_url text DEFAULT '' NOT NULL,
      next_action text DEFAULT '' NOT NULL,
      follow_up_at text DEFAULT '' NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_market_activities_project_market_created ON research_market_activities (project_id, market_code, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS research_buyer_profiles (
      id text PRIMARY KEY NOT NULL,
      project_id text NOT NULL,
      company_name text NOT NULL,
      website text DEFAULT '' NOT NULL,
      country text DEFAULT '' NOT NULL,
      buyer_type text DEFAULT '' NOT NULL,
      customer_groups text DEFAULT '[]' NOT NULL,
      sales_channels text DEFAULT '[]' NOT NULL,
      purchasing_scenarios text DEFAULT '[]' NOT NULL,
      seasonality text DEFAULT '' NOT NULL,
      replenishment_cycle text DEFAULT '' NOT NULL,
      order_requirements text DEFAULT '' NOT NULL,
      source_url text DEFAULT '' NOT NULL,
      profile_status text DEFAULT 'hypothesis' NOT NULL,
      odoo_lead_id integer,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE(project_id, company_name, country),
      FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_buyer_profiles_project_status ON research_buyer_profiles (project_id, profile_status)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS research_buyer_family_links (
      id text PRIMARY KEY NOT NULL,
      project_id text NOT NULL,
      buyer_profile_id text NOT NULL,
      track_category text DEFAULT '' NOT NULL,
      product_family text NOT NULL,
      relationship_score integer DEFAULT 0 NOT NULL,
      family_role text DEFAULT 'test' NOT NULL,
      sales_scenarios text DEFAULT '[]' NOT NULL,
      rationale text DEFAULT '' NOT NULL,
      evidence_status text DEFAULT 'hypothesis' NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE(buyer_profile_id, track_category, product_family),
      FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE,
      FOREIGN KEY (buyer_profile_id) REFERENCES research_buyer_profiles(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_research_buyer_family_links_buyer ON research_buyer_family_links (buyer_profile_id, relationship_score)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS global_buyer_profiles (
      id text PRIMARY KEY NOT NULL,
      company_name text NOT NULL,
      website text DEFAULT '' NOT NULL,
      country text DEFAULT '' NOT NULL,
      buyer_type text DEFAULT '' NOT NULL,
      customer_groups text DEFAULT '[]' NOT NULL,
      sales_channels text DEFAULT '[]' NOT NULL,
      purchasing_scenarios text DEFAULT '[]' NOT NULL,
      seasonality text DEFAULT '' NOT NULL,
      replenishment_cycle text DEFAULT '' NOT NULL,
      order_requirements text DEFAULT '' NOT NULL,
      source_url text DEFAULT '' NOT NULL,
      profile_status text DEFAULT 'hypothesis' NOT NULL,
      created_by text DEFAULT 'ai' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      last_verified_at text,
      UNIQUE(company_name, country)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_global_buyer_profiles_country_status ON global_buyer_profiles (country, profile_status)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS global_buyer_family_links (
      id text PRIMARY KEY NOT NULL,
      buyer_profile_id text NOT NULL,
      track_category text DEFAULT '' NOT NULL,
      product_family text NOT NULL,
      relationship_score integer DEFAULT 0 NOT NULL,
      family_role text DEFAULT 'test' NOT NULL,
      sales_scenarios text DEFAULT '[]' NOT NULL,
      rationale text DEFAULT '' NOT NULL,
      evidence_status text DEFAULT 'hypothesis' NOT NULL,
      created_by text DEFAULT 'ai' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE(buyer_profile_id, track_category, product_family),
      FOREIGN KEY (buyer_profile_id) REFERENCES global_buyer_profiles(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_global_buyer_family_links_buyer ON global_buyer_family_links (buyer_profile_id, relationship_score)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS global_buyer_project_refs (
      buyer_profile_id text NOT NULL,
      project_id text NOT NULL,
      project_buyer_profile_id text NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      PRIMARY KEY (buyer_profile_id, project_id),
      FOREIGN KEY (buyer_profile_id) REFERENCES global_buyer_profiles(id) ON DELETE CASCADE,
      FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS trade_regions (
      code text PRIMARY KEY NOT NULL,
      name text NOT NULL,
      macro_region text DEFAULT '' NOT NULL,
      m49_code text DEFAULT '' NOT NULL,
      countries text DEFAULT '[]' NOT NULL,
      characteristics text DEFAULT '[]' NOT NULL,
      source_url text DEFAULT '' NOT NULL,
      active integer DEFAULT 1 NOT NULL,
      created_by text DEFAULT 'system_seed' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS buyer_persona_categories (
      code text PRIMARY KEY NOT NULL,
      group_name text DEFAULT '' NOT NULL,
      name text NOT NULL,
      description text DEFAULT '' NOT NULL,
      value_chain_role text DEFAULT '' NOT NULL,
      customer_groups text DEFAULT '[]' NOT NULL,
      sales_channels text DEFAULT '[]' NOT NULL,
      purchase_scenarios text DEFAULT '[]' NOT NULL,
      buying_triggers text DEFAULT '[]' NOT NULL,
      order_characteristics text DEFAULT '[]' NOT NULL,
      compliance_focus text DEFAULT '[]' NOT NULL,
      source_refs text DEFAULT '[]' NOT NULL,
      version integer DEFAULT 1 NOT NULL,
      last_reviewed_at text,
      active integer DEFAULT 1 NOT NULL,
      created_by text DEFAULT 'system_seed' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS buyer_persona_ai_proposals (
      id text PRIMARY KEY NOT NULL,
      run_id text NOT NULL,
      mode text DEFAULT 'discover' NOT NULL,
      target_code text DEFAULT '' NOT NULL,
      persona_code text NOT NULL,
      payload text DEFAULT '{}' NOT NULL,
      source_refs text DEFAULT '[]' NOT NULL,
      rationale text DEFAULT '' NOT NULL,
      status text DEFAULT 'pending' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      reviewed_at text
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_buyer_persona_ai_proposals_status ON buyer_persona_ai_proposals (status, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS commercial_taxonomy_change_log (
      id text PRIMARY KEY NOT NULL,
      entity_type text NOT NULL,
      entity_code text NOT NULL,
      action text NOT NULL,
      origin text DEFAULT 'user' NOT NULL,
      run_id text DEFAULT '' NOT NULL,
      before_json text DEFAULT '{}' NOT NULL,
      after_json text DEFAULT '{}' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_commercial_taxonomy_change_log_entity ON commercial_taxonomy_change_log (entity_type, entity_code, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS product_tracks (
      code text PRIMARY KEY NOT NULL,
      name text NOT NULL,
      description text DEFAULT '' NOT NULL,
      buyer_value text DEFAULT '' NOT NULL,
      compliance_focus text DEFAULT '[]' NOT NULL,
      active integer DEFAULT 1 NOT NULL,
      created_by text DEFAULT 'system_seed' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS product_family_master (
      code text PRIMARY KEY NOT NULL,
      track_code text NOT NULL,
      name text NOT NULL,
      description text DEFAULT '' NOT NULL,
      use_scenarios text DEFAULT '[]' NOT NULL,
      compliance_tags text DEFAULT '[]' NOT NULL,
      keywords text DEFAULT '[]' NOT NULL,
      active integer DEFAULT 1 NOT NULL,
      created_by text DEFAULT 'system_seed' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (track_code) REFERENCES product_tracks(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_product_family_master_track ON product_family_master (track_code, active)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS persona_product_matrix (
      id text PRIMARY KEY NOT NULL,
      persona_code text NOT NULL,
      region_code text DEFAULT 'GLOBAL' NOT NULL,
      track_code text NOT NULL,
      product_family_code text DEFAULT '' NOT NULL,
      relevance_score integer DEFAULT 0 NOT NULL,
      family_role text DEFAULT 'test' NOT NULL,
      sales_scenarios text DEFAULT '[]' NOT NULL,
      seasonality text DEFAULT '' NOT NULL,
      rationale text DEFAULT '' NOT NULL,
      evidence_status text DEFAULT 'hypothesis' NOT NULL,
      created_by text DEFAULT 'system_seed' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE(persona_code, region_code, track_code, product_family_code),
      FOREIGN KEY (persona_code) REFERENCES buyer_persona_categories(code),
      FOREIGN KEY (region_code) REFERENCES trade_regions(code),
      FOREIGN KEY (track_code) REFERENCES product_tracks(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_persona_product_matrix_persona_region ON persona_product_matrix (persona_code, region_code, relevance_score)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_dossiers (
      id text PRIMARY KEY NOT NULL,
      scope_key text UNIQUE NOT NULL,
      region_code text NOT NULL,
      track_code text NOT NULL,
      product_family_code text NOT NULL,
      status text DEFAULT 'active' NOT NULL,
      version integer DEFAULT 1 NOT NULL,
      last_reviewed_at text DEFAULT '' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE(region_code, product_family_code),
      FOREIGN KEY (region_code) REFERENCES trade_regions(code),
      FOREIGN KEY (track_code) REFERENCES product_tracks(code),
      FOREIGN KEY (product_family_code) REFERENCES product_family_master(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_dossiers_family_region ON opportunity_dossiers (product_family_code, region_code, status)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_cases (
      id text PRIMARY KEY NOT NULL,
      fingerprint text UNIQUE NOT NULL,
      dossier_id text DEFAULT '' NOT NULL,
      title text NOT NULL,
      persona_code text NOT NULL,
      persona_version integer DEFAULT 1 NOT NULL,
      region_code text NOT NULL,
      track_code text NOT NULL,
      product_family_code text NOT NULL,
      purchase_scenario text NOT NULL,
      sales_channel text NOT NULL,
      hypothesis text DEFAULT '' NOT NULL,
      status text DEFAULT 'hypothesis' NOT NULL,
      owner_name text DEFAULT '' NOT NULL,
      next_review_at text DEFAULT '' NOT NULL,
      next_action text DEFAULT '' NOT NULL,
      active integer DEFAULT 1 NOT NULL,
      version integer DEFAULT 1 NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (persona_code) REFERENCES buyer_persona_categories(code),
      FOREIGN KEY (region_code) REFERENCES trade_regions(code),
      FOREIGN KEY (track_code) REFERENCES product_tracks(code),
      FOREIGN KEY (product_family_code) REFERENCES product_family_master(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_cases_status_review ON opportunity_cases (active, status, next_review_at, updated_at)"),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_cases_matrix ON opportunity_cases (persona_code, region_code, product_family_code)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_assessments (
      id text PRIMARY KEY NOT NULL,
      opportunity_id text NOT NULL,
      signals text DEFAULT '{}' NOT NULL,
      scores text DEFAULT '{}' NOT NULL,
      rationale text DEFAULT '' NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (opportunity_id) REFERENCES opportunity_cases(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_assessments_case_created ON opportunity_assessments (opportunity_id, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_evidence (
      id text PRIMARY KEY NOT NULL,
      opportunity_id text NOT NULL,
      dossier_id text DEFAULT '' NOT NULL,
      evidence_scope text DEFAULT 'project' NOT NULL,
      evidence_type text NOT NULL,
      source_grade text DEFAULT 'other' NOT NULL,
      title text NOT NULL,
      source_url text DEFAULT '' NOT NULL,
      note text DEFAULT '' NOT NULL,
      market_code text DEFAULT '' NOT NULL,
      period text DEFAULT '' NOT NULL,
      metrics text DEFAULT '{}' NOT NULL,
      evidence_status text DEFAULT 'available' NOT NULL,
      captured_at text NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (opportunity_id) REFERENCES opportunity_cases(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_evidence_case_captured ON opportunity_evidence (opportunity_id, captured_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_change_log (
      id text PRIMARY KEY NOT NULL,
      opportunity_id text NOT NULL,
      action text NOT NULL,
      origin text DEFAULT 'user' NOT NULL,
      before_json text DEFAULT '{}' NOT NULL,
      after_json text DEFAULT '{}' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_change_log_case_created ON opportunity_change_log (opportunity_id, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS trade_data_refresh_requests (
      id text PRIMARY KEY NOT NULL,
      opportunity_id text NOT NULL,
      product_family_code text NOT NULL,
      region_code text NOT NULL,
      status text DEFAULT 'pending' NOT NULL,
      force_refresh integer DEFAULT 0 NOT NULL,
      collection_level text DEFAULT 'baseline' NOT NULL,
      trigger_reason text DEFAULT 'manual' NOT NULL,
      request_note text DEFAULT '' NOT NULL,
      requested_by text DEFAULT 'user' NOT NULL,
      error text DEFAULT '' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      completed_at text,
      FOREIGN KEY (opportunity_id) REFERENCES opportunity_cases(id) ON DELETE CASCADE,
      FOREIGN KEY (product_family_code) REFERENCES product_family_master(code),
      FOREIGN KEY (region_code) REFERENCES trade_regions(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_trade_data_refresh_requests_case_created ON trade_data_refresh_requests (opportunity_id, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_validation_requests (
      id text PRIMARY KEY NOT NULL,
      opportunity_id text NOT NULL,
      status text DEFAULT 'pending' NOT NULL,
      trigger_reason text DEFAULT 'manual' NOT NULL,
      request_note text DEFAULT '' NOT NULL,
      requested_by text DEFAULT 'user' NOT NULL,
      summary text DEFAULT '' NOT NULL,
      suggested_next_action text DEFAULT '' NOT NULL,
      error text DEFAULT '' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      completed_at text,
      FOREIGN KEY (opportunity_id) REFERENCES opportunity_cases(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_validation_requests_case_created ON opportunity_validation_requests (opportunity_id, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_programs (
      id text PRIMARY KEY NOT NULL,
      title text NOT NULL,
      persona_code text NOT NULL,
      persona_version integer DEFAULT 1 NOT NULL,
      region_code text NOT NULL,
      purchase_scenario text NOT NULL,
      sales_channel text NOT NULL,
      project_scope_key text DEFAULT '' NOT NULL,
      cycle_number integer DEFAULT 1 NOT NULL,
      parent_program_id text DEFAULT '' NOT NULL,
      hypothesis text DEFAULT '' NOT NULL,
      max_family_count integer DEFAULT 5 NOT NULL,
      status text DEFAULT 'round_active' NOT NULL,
      current_round_number integer DEFAULT 1 NOT NULL,
      customer_owner text DEFAULT '' NOT NULL,
      supply_owner text DEFAULT '' NOT NULL,
      next_review_at text DEFAULT '' NOT NULL,
      next_action text DEFAULT '' NOT NULL,
      active integer DEFAULT 1 NOT NULL,
      version integer DEFAULT 1 NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      void_reason_code text DEFAULT '' NOT NULL,
      void_reason_note text DEFAULT '' NOT NULL,
      voided_at text DEFAULT '' NOT NULL,
      voided_by text DEFAULT '' NOT NULL,
      replaced_by_program_id text DEFAULT '' NOT NULL,
      FOREIGN KEY (persona_code) REFERENCES buyer_persona_categories(code),
      FOREIGN KEY (region_code) REFERENCES trade_regions(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_programs_status_review ON opportunity_programs (active, status, next_review_at, updated_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_rounds (
      id text PRIMARY KEY NOT NULL,
      program_id text NOT NULL,
      round_number integer NOT NULL,
      phase text DEFAULT 'discovery' NOT NULL,
      status text DEFAULT 'active' NOT NULL,
      goal text DEFAULT '' NOT NULL,
      decision text DEFAULT '' NOT NULL,
      decision_note text DEFAULT '' NOT NULL,
      due_at text DEFAULT '' NOT NULL,
      started_at text NOT NULL,
      completed_at text,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE(program_id, round_number),
      FOREIGN KEY (program_id) REFERENCES opportunity_programs(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_rounds_program_number ON opportunity_rounds (program_id, round_number DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_round_families (
      id text PRIMARY KEY NOT NULL,
      round_id text NOT NULL,
      opportunity_id text NOT NULL,
      matrix_id text NOT NULL,
      matrix_role text DEFAULT 'test' NOT NULL,
      matrix_score integer DEFAULT 0 NOT NULL,
      matrix_evidence_status text DEFAULT 'hypothesis' NOT NULL,
      matrix_rationale text DEFAULT '' NOT NULL,
      product_family_code text NOT NULL,
      priority_rank integer DEFAULT 0 NOT NULL,
      status text DEFAULT 'candidate' NOT NULL,
      rationale text DEFAULT '' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE(round_id, product_family_code),
      FOREIGN KEY (round_id) REFERENCES opportunity_rounds(id) ON DELETE CASCADE,
      FOREIGN KEY (opportunity_id) REFERENCES opportunity_cases(id),
      FOREIGN KEY (matrix_id) REFERENCES persona_product_matrix(id),
      FOREIGN KEY (product_family_code) REFERENCES product_family_master(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_round_families_round_rank ON opportunity_round_families (round_id, priority_rank)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS opportunity_customer_feedback (
      id text PRIMARY KEY NOT NULL,
      program_id text NOT NULL,
      round_id text NOT NULL,
      product_family_code text NOT NULL,
      company_name text NOT NULL,
      contact_role text DEFAULT '' NOT NULL,
      feedback_status text DEFAULT 'contacted' NOT NULL,
      scenario text DEFAULT '' NOT NULL,
      current_solution text DEFAULT '' NOT NULL,
      pain_points text DEFAULT '' NOT NULL,
      must_have_specs text DEFAULT '' NOT NULL,
      buying_trigger text DEFAULT '' NOT NULL,
      purchase_cycle text DEFAULT '' NOT NULL,
      price_behavior text DEFAULT '' NOT NULL,
      rejection_reason text DEFAULT '' NOT NULL,
      source_url text DEFAULT '' NOT NULL,
      note text DEFAULT '' NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (program_id) REFERENCES opportunity_programs(id) ON DELETE CASCADE,
      FOREIGN KEY (round_id) REFERENCES opportunity_rounds(id) ON DELETE CASCADE,
      FOREIGN KEY (product_family_code) REFERENCES product_family_master(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_customer_feedback_round_family ON opportunity_customer_feedback (round_id, product_family_code, created_at DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS trade_data_observations (
      id text PRIMARY KEY NOT NULL,
      fingerprint text UNIQUE NOT NULL,
      refresh_request_id text DEFAULT '' NOT NULL,
      opportunity_id text DEFAULT '' NOT NULL,
      product_family_code text NOT NULL,
      region_code text NOT NULL,
      reporter_code text NOT NULL,
      partner_code text DEFAULT 'WORLD' NOT NULL,
      classification text DEFAULT 'HS' NOT NULL,
      commodity_code text NOT NULL,
      commodity_label text NOT NULL,
      flow text NOT NULL,
      period text NOT NULL,
      frequency text NOT NULL,
      metric text NOT NULL,
      value real,
      unit text DEFAULT 'USD' NOT NULL,
      source_name text NOT NULL,
      source_url text NOT NULL,
      source_grade text DEFAULT 'ai_verified' NOT NULL,
      data_status text DEFAULT 'available' NOT NULL,
      missing_reason text DEFAULT '' NOT NULL,
      collected_at text NOT NULL,
      created_by text DEFAULT 'ai_assistant' NOT NULL,
      raw_record text DEFAULT '{}' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (product_family_code) REFERENCES product_family_master(code),
      FOREIGN KEY (region_code) REFERENCES trade_regions(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_trade_data_observations_lookup ON trade_data_observations (product_family_code, region_code, period, flow, metric, collected_at)"),
  ]);
  const projectColumns = await db.prepare("PRAGMA table_info(research_projects)").all<{ name: string }>();
  if (!projectColumns.results.some((column) => column.name === "target_candidate_count")) {
    await db.prepare("ALTER TABLE research_projects ADD COLUMN target_candidate_count integer DEFAULT 2000 NOT NULL").run();
  }
  const candidateColumns = await db.prepare("PRAGMA table_info(research_candidates)").all<{ name: string }>();
  if (!candidateColumns.results.some((column) => column.name === "image_urls")) {
    await db.prepare("ALTER TABLE research_candidates ADD COLUMN image_urls text DEFAULT '[]' NOT NULL").run();
  }
  if (!candidateColumns.results.some((column) => column.name === "image_source_ref")) {
    await db.prepare("ALTER TABLE research_candidates ADD COLUMN image_source_ref text DEFAULT '' NOT NULL").run();
  }
  if (!candidateColumns.results.some((column) => column.name === "product_family")) {
    await db.prepare("ALTER TABLE research_candidates ADD COLUMN product_family text DEFAULT '' NOT NULL").run();
  }
  if (!candidateColumns.results.some((column) => column.name === "selection_assessment")) {
    await db.prepare("ALTER TABLE research_candidates ADD COLUMN selection_assessment text DEFAULT '{}' NOT NULL").run();
  }
  if (!candidateColumns.results.some((column) => column.name === "odoo_sync_state")) {
    await db.prepare("ALTER TABLE research_candidates ADD COLUMN odoo_sync_state text DEFAULT 'not_synced' NOT NULL").run();
  }
  if (!candidateColumns.results.some((column) => column.name === "odoo_external_id")) {
    await db.prepare("ALTER TABLE research_candidates ADD COLUMN odoo_external_id text DEFAULT '' NOT NULL").run();
  }
  if (!candidateColumns.results.some((column) => column.name === "odoo_synced_at")) {
    await db.prepare("ALTER TABLE research_candidates ADD COLUMN odoo_synced_at text").run();
  }
  const tradeRequestColumns = await db.prepare("PRAGMA table_info(trade_data_refresh_requests)").all<{ name: string }>();
  if (!tradeRequestColumns.results.some((column) => column.name === "collection_level")) {
    await db.prepare("ALTER TABLE trade_data_refresh_requests ADD COLUMN collection_level text DEFAULT 'baseline' NOT NULL").run();
  }
  if (!tradeRequestColumns.results.some((column) => column.name === "trigger_reason")) {
    await db.prepare("ALTER TABLE trade_data_refresh_requests ADD COLUMN trigger_reason text DEFAULT 'manual' NOT NULL").run();
  }
  const opportunityColumns = await db.prepare("PRAGMA table_info(opportunity_cases)").all<{ name: string }>();
  if (!opportunityColumns.results.some((column) => column.name === "program_id")) {
    await db.prepare("ALTER TABLE opportunity_cases ADD COLUMN program_id text DEFAULT '' NOT NULL").run();
  }
  if (!opportunityColumns.results.some((column) => column.name === "dossier_id")) {
    await db.prepare("ALTER TABLE opportunity_cases ADD COLUMN dossier_id text DEFAULT '' NOT NULL").run();
  }
  const programColumns = await db.prepare("PRAGMA table_info(opportunity_programs)").all<{ name: string }>();
  for (const [name, definition] of [
    ["persona_version", "integer DEFAULT 1 NOT NULL"],
    ["project_scope_key", "text DEFAULT '' NOT NULL"],
    ["cycle_number", "integer DEFAULT 1 NOT NULL"],
    ["parent_program_id", "text DEFAULT '' NOT NULL"],
    ["void_reason_code", "text DEFAULT '' NOT NULL"],
    ["void_reason_note", "text DEFAULT '' NOT NULL"],
    ["voided_at", "text DEFAULT '' NOT NULL"],
    ["voided_by", "text DEFAULT '' NOT NULL"],
    ["replaced_by_program_id", "text DEFAULT '' NOT NULL"],
  ] as const) {
    if (!programColumns.results.some((column) => column.name === name)) {
      await db.prepare(`ALTER TABLE opportunity_programs ADD COLUMN ${name} ${definition}`).run();
    }
  }
  const evidenceColumns = await db.prepare("PRAGMA table_info(opportunity_evidence)").all<{ name: string }>();
  if (!evidenceColumns.results.some((column) => column.name === "dossier_id")) {
    await db.prepare("ALTER TABLE opportunity_evidence ADD COLUMN dossier_id text DEFAULT '' NOT NULL").run();
  }
  if (!evidenceColumns.results.some((column) => column.name === "evidence_scope")) {
    await db.prepare("ALTER TABLE opportunity_evidence ADD COLUMN evidence_scope text DEFAULT 'project' NOT NULL").run();
  }
  const roundFamilyColumns = await db.prepare("PRAGMA table_info(opportunity_round_families)").all<{ name: string }>();
  for (const [name, definition] of [
    ["matrix_id", "text DEFAULT '' NOT NULL"],
    ["matrix_role", "text DEFAULT 'test' NOT NULL"],
    ["matrix_score", "integer DEFAULT 0 NOT NULL"],
    ["matrix_evidence_status", "text DEFAULT 'hypothesis' NOT NULL"],
    ["matrix_rationale", "text DEFAULT '' NOT NULL"],
  ] as const) {
    if (!roundFamilyColumns.results.some((column) => column.name === name)) {
      await db.prepare(`ALTER TABLE opportunity_round_families ADD COLUMN ${name} ${definition}`).run();
    }
  }
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_round_families_matrix ON opportunity_round_families (matrix_id)").run();
  await db.batch([
    db.prepare(`INSERT OR IGNORE INTO opportunity_dossiers
      (id, scope_key, region_code, track_code, product_family_code, status, version, created_at, updated_at)
      SELECT 'dossier:' || lower(region_code) || ':' || lower(product_family_code),
        lower(region_code) || '|' || lower(product_family_code), region_code, track_code,
        product_family_code, 'active', 1, MIN(created_at), MAX(updated_at)
      FROM opportunity_cases GROUP BY region_code, product_family_code, track_code`),
    db.prepare(`UPDATE opportunity_cases SET dossier_id =
      'dossier:' || lower(region_code) || ':' || lower(product_family_code) WHERE dossier_id = ''`),
    db.prepare(`UPDATE opportunity_evidence SET dossier_id = COALESCE(
      (SELECT c.dossier_id FROM opportunity_cases c WHERE c.id = opportunity_evidence.opportunity_id), '')
      WHERE dossier_id = ''`),
    db.prepare(`UPDATE opportunity_evidence SET evidence_scope = CASE
      WHEN evidence_type IN ('demand', 'channel', 'competition', 'product_matrix', 'supply', 'compliance') THEN 'shared'
      ELSE 'project' END`),
    db.prepare(`UPDATE opportunity_programs SET project_scope_key =
      lower(persona_code) || '|' || lower(region_code) || '|' || lower(trim(purchase_scenario)) || '|' || lower(trim(sales_channel))
      WHERE project_scope_key = ''`),
  ]);
  await db.prepare("CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunity_programs_active_scope ON opportunity_programs (project_scope_key) WHERE active = 1 AND status != 'voided'").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_programs_page ON opportunity_programs (status, updated_at DESC, id)").run();
  await db.prepare("CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunity_cases_program_family ON opportunity_cases (program_id, product_family_code) WHERE program_id != ''").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_cases_dossier ON opportunity_cases (dossier_id, active, updated_at DESC)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_opportunity_evidence_dossier ON opportunity_evidence (dossier_id, evidence_scope, captured_at DESC)").run();
  const activityColumns = await db.prepare("PRAGMA table_info(research_candidate_activities)").all<{ name: string }>();
  if (!activityColumns.results.some((column) => column.name === "recommended_stage")) {
    await db.prepare("ALTER TABLE research_candidate_activities ADD COLUMN recommended_stage text DEFAULT '' NOT NULL").run();
  }
  if (!activityColumns.results.some((column) => column.name === "created_by")) {
    await db.prepare("ALTER TABLE research_candidate_activities ADD COLUMN created_by text DEFAULT 'user' NOT NULL").run();
  }
  const globalBuyerColumns = await db.prepare("PRAGMA table_info(global_buyer_profiles)").all<{ name: string }>();
  if (!globalBuyerColumns.results.some((column) => column.name === "persona_code")) {
    await db.prepare("ALTER TABLE global_buyer_profiles ADD COLUMN persona_code text DEFAULT '' NOT NULL").run();
  }
  if (!globalBuyerColumns.results.some((column) => column.name === "region_code")) {
    await db.prepare("ALTER TABLE global_buyer_profiles ADD COLUMN region_code text DEFAULT '' NOT NULL").run();
  }
  const personaColumns = await db.prepare("PRAGMA table_info(buyer_persona_categories)").all<{ name: string }>();
  if (!personaColumns.results.some((column) => column.name === "source_refs")) {
    await db.prepare("ALTER TABLE buyer_persona_categories ADD COLUMN source_refs text DEFAULT '[]' NOT NULL").run();
  }
  if (!personaColumns.results.some((column) => column.name === "version")) {
    await db.prepare("ALTER TABLE buyer_persona_categories ADD COLUMN version integer DEFAULT 1 NOT NULL").run();
  }
  if (!personaColumns.results.some((column) => column.name === "last_reviewed_at")) {
    await db.prepare("ALTER TABLE buyer_persona_categories ADD COLUMN last_reviewed_at text").run();
  }
  await seedCommercialTaxonomy();
  await db.batch([
    db.prepare(`INSERT OR IGNORE INTO global_buyer_profiles
      (id, company_name, website, country, buyer_type, customer_groups, sales_channels, purchasing_scenarios,
       seasonality, replenishment_cycle, order_requirements, source_url, profile_status, created_by, created_at, updated_at, last_verified_at)
      SELECT id, company_name, website, country, buyer_type, customer_groups, sales_channels, purchasing_scenarios,
             seasonality, replenishment_cycle, order_requirements, source_url, profile_status, created_by, created_at, updated_at,
             CASE WHEN profile_status = 'validated' THEN updated_at ELSE NULL END
        FROM research_buyer_profiles`),
    db.prepare(`INSERT OR IGNORE INTO global_buyer_project_refs (buyer_profile_id, project_id, project_buyer_profile_id, created_at)
      SELECT g.id, p.project_id, p.id, p.created_at
        FROM research_buyer_profiles p
        JOIN global_buyer_profiles g ON g.company_name = p.company_name AND g.country = p.country`),
    db.prepare(`INSERT OR IGNORE INTO global_buyer_family_links
      (id, buyer_profile_id, track_category, product_family, relationship_score, family_role,
       sales_scenarios, rationale, evidence_status, created_by, created_at, updated_at)
      SELECT l.id, g.id, l.track_category, l.product_family, l.relationship_score, l.family_role,
             l.sales_scenarios, l.rationale, l.evidence_status, l.created_by, l.created_at, l.updated_at
        FROM research_buyer_family_links l
        JOIN research_buyer_profiles p ON p.id = l.buyer_profile_id
        JOIN global_buyer_profiles g ON g.company_name = p.company_name AND g.country = p.country`),
  ]);
  await classifyUnmappedGlobalBuyers();
  researchSchemaReady = true;
}

async function ensureIntelligenceSchema() {
  if (intelligenceSchemaReady) return;
  await ensureResearchSchema();
  const db = getRawDb();
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS market_signal_monitors (
      id text PRIMARY KEY NOT NULL,
      scope_key text NOT NULL,
      name text NOT NULL,
      region_code text NOT NULL,
      trigger_type text NOT NULL,
      trigger_name text NOT NULL,
      persona_code text DEFAULT '' NOT NULL,
      product_family_code text DEFAULT '' NOT NULL,
      keywords text DEFAULT '[]' NOT NULL,
      signal_types text DEFAULT '[]' NOT NULL,
      commodity_codes text DEFAULT '[]' NOT NULL,
      source_ids text DEFAULT '[]' NOT NULL,
      cadence_days integer DEFAULT 7 NOT NULL,
      status text DEFAULT 'active' NOT NULL,
      last_run_at text,
      next_run_at text,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      archived_at text
    )`),
    db.prepare("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_signal_monitors_scope ON market_signal_monitors (scope_key)"),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_market_signal_monitors_status_next ON market_signal_monitors (status, next_run_at, updated_at DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS market_signals (
      id text PRIMARY KEY NOT NULL,
      fingerprint text NOT NULL,
      monitor_id text DEFAULT '' NOT NULL,
      signal_type text NOT NULL,
      source_id text NOT NULL,
      source_name text NOT NULL,
      source_url text DEFAULT '' NOT NULL,
      region_code text NOT NULL,
      persona_code text DEFAULT '' NOT NULL,
      product_family_code text DEFAULT '' NOT NULL,
      commodity_code text DEFAULT '' NOT NULL,
      period text DEFAULT '' NOT NULL,
      metric text DEFAULT '' NOT NULL,
      value real,
      unit text DEFAULT '' NOT NULL,
      direction text DEFAULT 'unknown' NOT NULL,
      confidence integer DEFAULT 0 NOT NULL,
      evidence_grade text DEFAULT 'supporting' NOT NULL,
      data_status text DEFAULT 'available' NOT NULL,
      missing_reason text DEFAULT '' NOT NULL,
      title text NOT NULL,
      summary text DEFAULT '' NOT NULL,
      raw_json text DEFAULT '{}' NOT NULL,
      collected_at text NOT NULL,
      expires_at text,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (monitor_id) REFERENCES market_signal_monitors(id) ON DELETE SET DEFAULT
    )`),
    db.prepare("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_signals_fingerprint ON market_signals (fingerprint)"),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_market_signals_lookup ON market_signals (region_code, product_family_code, signal_type, collected_at DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS market_signal_monitor_refs (
      signal_id text NOT NULL,
      monitor_id text NOT NULL,
      first_seen_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      last_seen_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      PRIMARY KEY (signal_id, monitor_id),
      FOREIGN KEY (signal_id) REFERENCES market_signals(id) ON DELETE CASCADE,
      FOREIGN KEY (monitor_id) REFERENCES market_signal_monitors(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_market_signal_monitor_refs_monitor ON market_signal_monitor_refs (monitor_id, last_seen_at DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS market_signal_versions (
      id text PRIMARY KEY NOT NULL,
      signal_id text NOT NULL,
      fingerprint text NOT NULL,
      version_hash text NOT NULL,
      payload_json text DEFAULT '{}' NOT NULL,
      collected_at text NOT NULL,
      imported_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      UNIQUE (fingerprint, version_hash),
      FOREIGN KEY (signal_id) REFERENCES market_signals(id) ON DELETE CASCADE
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS market_signal_runs (
      id text PRIMARY KEY NOT NULL,
      monitor_id text NOT NULL,
      status text DEFAULT 'running' NOT NULL,
      trigger_reason text DEFAULT 'manual' NOT NULL,
      source_plan text DEFAULT '[]' NOT NULL,
      result_json text DEFAULT '{}' NOT NULL,
      requested_at text NOT NULL,
      started_at text NOT NULL,
      completed_at text,
      signal_count integer DEFAULT 0 NOT NULL,
      duration_ms integer DEFAULT 0 NOT NULL,
      retry_count integer DEFAULT 0 NOT NULL,
      error_category text DEFAULT '' NOT NULL,
      error text DEFAULT '' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (monitor_id) REFERENCES market_signal_monitors(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_market_signal_runs_monitor ON market_signal_runs (monitor_id, created_at DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS market_signal_source_runs (
      id text PRIMARY KEY NOT NULL,
      run_id text NOT NULL,
      monitor_id text NOT NULL,
      source_id text NOT NULL,
      status text NOT NULL,
      error_category text DEFAULT '' NOT NULL,
      error_message text DEFAULT '' NOT NULL,
      coverage_countries text DEFAULT '[]' NOT NULL,
      result_count integer DEFAULT 0 NOT NULL,
      duration_ms integer DEFAULT 0 NOT NULL,
      retry_count integer DEFAULT 0 NOT NULL,
      quota_summary text DEFAULT '' NOT NULL,
      update_frequency text DEFAULT '' NOT NULL,
      started_at text NOT NULL,
      completed_at text NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (run_id) REFERENCES market_signal_runs(id) ON DELETE CASCADE,
      FOREIGN KEY (monitor_id) REFERENCES market_signal_monitors(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_market_signal_source_runs_run ON market_signal_source_runs (run_id, source_id)"),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_market_signal_source_runs_source ON market_signal_source_runs (source_id, created_at DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS intelligence_source_health (
      source_id text NOT NULL,
      monitor_id text NOT NULL,
      status text DEFAULT 'never_run' NOT NULL,
      coverage_countries text DEFAULT '[]' NOT NULL,
      quota_summary text DEFAULT '' NOT NULL,
      update_frequency text DEFAULT '' NOT NULL,
      last_attempt_at text,
      last_success_at text,
      last_failure_at text,
      last_error_category text DEFAULT '' NOT NULL,
      last_error text DEFAULT '' NOT NULL,
      consecutive_failures integer DEFAULT 0 NOT NULL,
      result_count integer DEFAULT 0 NOT NULL,
      duration_ms integer DEFAULT 0 NOT NULL,
      retry_count integer DEFAULT 0 NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      PRIMARY KEY (source_id, monitor_id),
      FOREIGN KEY (monitor_id) REFERENCES market_signal_monitors(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_intelligence_source_health_source ON intelligence_source_health (source_id, updated_at DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS intelligence_events (
      id text PRIMARY KEY NOT NULL,
      fingerprint text UNIQUE NOT NULL,
      name text NOT NULL,
      region_code text NOT NULL,
      trigger_type text NOT NULL,
      starts_at text NOT NULL,
      ends_at text,
      procurement_lead_days integer DEFAULT 0 NOT NULL,
      delivery_cutoff text,
      source_name text NOT NULL,
      source_url text NOT NULL,
      notes text DEFAULT '' NOT NULL,
      status text DEFAULT 'active' NOT NULL,
      created_by text DEFAULT 'user' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      archived_at text,
      FOREIGN KEY (region_code) REFERENCES trade_regions(code)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_intelligence_events_window ON intelligence_events (status, starts_at, region_code, trigger_type)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS intelligence_opportunity_candidates (
      id text PRIMARY KEY NOT NULL,
      monitor_id text UNIQUE NOT NULL,
      region_code text NOT NULL,
      persona_code text DEFAULT '' NOT NULL,
      product_family_code text DEFAULT '' NOT NULL,
      trigger_type text NOT NULL,
      title text NOT NULL,
      opportunity_type text DEFAULT 'observe' NOT NULL,
      status text DEFAULT 'pending_review' NOT NULL,
      evidence_count integer DEFAULT 0 NOT NULL,
      source_count integer DEFAULT 0 NOT NULL,
      signal_ids text DEFAULT '[]' NOT NULL,
      summary text DEFAULT '' NOT NULL,
      rationale text DEFAULT '' NOT NULL,
      blockers text DEFAULT '[]' NOT NULL,
      next_action text DEFAULT '' NOT NULL,
      review_note text DEFAULT '' NOT NULL,
      reviewed_at text,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      updated_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      FOREIGN KEY (monitor_id) REFERENCES market_signal_monitors(id) ON DELETE CASCADE
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_intelligence_candidates_status ON intelligence_opportunity_candidates (status, updated_at DESC)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS market_signal_project_refs (
      signal_id text NOT NULL,
      program_id text NOT NULL,
      round_id text DEFAULT '' NOT NULL,
      created_at text DEFAULT CURRENT_TIMESTAMP NOT NULL,
      PRIMARY KEY (signal_id, program_id, round_id),
      FOREIGN KEY (signal_id) REFERENCES market_signals(id) ON DELETE CASCADE,
      FOREIGN KEY (program_id) REFERENCES opportunity_programs(id) ON DELETE CASCADE
    )`),
  ]);
  const monitorColumns = await db.prepare("PRAGMA table_info(market_signal_monitors)").all<{ name: string }>();
  if (!monitorColumns.results.some((column) => column.name === "commodity_codes")) {
    await db.prepare("ALTER TABLE market_signal_monitors ADD COLUMN commodity_codes text DEFAULT '[]' NOT NULL").run();
  }
  if (!monitorColumns.results.some((column) => column.name === "source_ids")) {
    await db.prepare("ALTER TABLE market_signal_monitors ADD COLUMN source_ids text DEFAULT '[]' NOT NULL").run();
  }
  const runColumns = await db.prepare("PRAGMA table_info(market_signal_runs)").all<{ name: string }>();
  if (!runColumns.results.some((column) => column.name === "duration_ms")) {
    await db.prepare("ALTER TABLE market_signal_runs ADD COLUMN duration_ms integer DEFAULT 0 NOT NULL").run();
  }
  if (!runColumns.results.some((column) => column.name === "retry_count")) {
    await db.prepare("ALTER TABLE market_signal_runs ADD COLUMN retry_count integer DEFAULT 0 NOT NULL").run();
  }
  if (!runColumns.results.some((column) => column.name === "error_category")) {
    await db.prepare("ALTER TABLE market_signal_runs ADD COLUMN error_category text DEFAULT '' NOT NULL").run();
  }
  await db.prepare(`INSERT OR IGNORE INTO market_signal_monitor_refs (signal_id, monitor_id, first_seen_at, last_seen_at)
    SELECT id, monitor_id, created_at, collected_at FROM market_signals WHERE monitor_id <> ''`).run();
  intelligenceSchemaReady = true;
}

function parseMarketSignalMonitor(row: JsonRecord) {
  return {
    ...row,
    cadence_days: Math.max(1, Math.min(90, Number(row.cadence_days) || 7)),
    signal_count: Number(row.signal_count ?? 0),
    keywords: stringList(row.keywords, 30),
    signal_types: stringList(row.signal_types, 10),
    commodity_codes: stringList(row.commodity_codes, 12),
    source_ids: stringList(row.source_ids, 12),
  };
}

function parseMarketSignal(row: JsonRecord) {
  return {
    ...row,
    data_status: String(row.data_status ?? "missing"),
    evidence_grade: String(row.evidence_grade ?? "supporting"),
    value: row.value === null || row.value === undefined ? null : Number(row.value),
    confidence: boundedNumber(row.confidence, 0, 100),
    raw_json: jsonObject(row.raw_json),
  };
}

function parseMarketSignalRun(row: JsonRecord) {
  return {
    ...row,
    id: String(row.id),
    status: String(row.status),
    trigger_reason: String(row.trigger_reason ?? "manual"),
    monitor_name: String(row.monitor_name ?? ""),
    error: String(row.error ?? ""),
    source_plan: jsonArray(row.source_plan),
    result_json: jsonObject(row.result_json),
    signal_count: Number(row.signal_count ?? 0),
    duration_ms: Number(row.duration_ms ?? 0),
    retry_count: Number(row.retry_count ?? 0),
    error_category: String(row.error_category ?? ""),
  };
}

function parseIntelligenceCandidate(row: JsonRecord) {
  return {
    ...row,
    id: String(row.id),
    status: String(row.status),
    title: String(row.title),
    next_action: String(row.next_action ?? ""),
    evidence_count: Number(row.evidence_count ?? 0),
    source_count: Number(row.source_count ?? 0),
    signal_ids: stringList(row.signal_ids, 500),
    blockers: stringList(row.blockers, 30),
  };
}

function intelligenceSourcePlan(signalTypes: string[]) {
  const wanted = new Set(signalTypes);
  return INTELLIGENCE_SOURCE_CATALOG
    .filter((source) => source.signalTypes.some((type) => wanted.has(type)))
    .map((source) => ({
      id: source.id,
      name: source.name,
      priority: source.priority,
      access: source.access,
      sourceUrl: source.sourceUrl,
      signalTypes: source.signalTypes.filter((type) => wanted.has(type)),
    }));
}

function sourceIdFromTradeObservation(row: JsonRecord) {
  const source = String(row.source_name ?? "").toLocaleLowerCase();
  if (source.includes("comtrade")) return "un_comtrade";
  if (source.includes("eurostat")) return "eurostat_comext";
  if (source.includes("census") || source.includes("usitc")) return "us_census";
  if (source.includes("hmrc") || source.includes("uk trade")) return "uk_hmrc";
  if (source.includes("canada")) return "canada_trade";
  if (source.includes("japan")) return "japan_customs";
  if (source.includes("australia") || source.includes("abs")) return "australia_abs";
  if (source.includes("china") || source.includes("海关")) return "china_customs";
  if (source.includes("wto")) return "wto_data";
  if (source.includes("world bank") || source.includes("wits")) return "world_bank_wits";
  return "national_statistics";
}

async function payloadHash(value: unknown) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

type MarketSignalInput = {
  signalType: MarketSignalType;
  sourceId: string;
  sourceName: string;
  sourceUrl: string;
  regionCode: string;
  personaCode: string;
  productFamilyCode: string;
  commodityCode: string;
  period: string;
  metric: string;
  value: number | null;
  unit: string;
  direction: string;
  confidence: number;
  evidenceGrade: string;
  dataStatus: string;
  missingReason: string;
  title: string;
  summary: string;
  collectedAt: string;
  expiresAt: string | null;
  externalId: string;
  raw: JsonRecord;
};

async function upsertMarketSignal(monitorId: string, input: MarketSignalInput) {
  const db = getRawDb();
  const fingerprint = marketSignalFingerprint({
    sourceId: input.sourceId,
    signalType: input.signalType,
    regionCode: input.regionCode,
    personaCode: input.personaCode,
    productFamilyCode: input.productFamilyCode,
    commodityCode: input.commodityCode,
    period: input.period,
    metric: input.metric,
    externalId: input.externalId,
  });
  const normalizedPayload = { ...input, fingerprint };
  const versionHash = await payloadHash(normalizedPayload);
  const existing = await db.prepare("SELECT id FROM market_signals WHERE fingerprint = ?").bind(fingerprint).first<{ id: string }>();
  const signalId = existing?.id ?? crypto.randomUUID();
  if (existing) {
    await db.prepare(`UPDATE market_signals SET
      signal_type = ?, source_id = ?, source_name = ?, source_url = ?, region_code = ?, persona_code = ?,
      product_family_code = ?, commodity_code = ?, period = ?, metric = ?, value = ?, unit = ?, direction = ?,
      confidence = ?, evidence_grade = ?, data_status = ?, missing_reason = ?, title = ?, summary = ?, raw_json = ?,
      collected_at = ?, expires_at = ? WHERE id = ?`)
      .bind(input.signalType, input.sourceId, input.sourceName, input.sourceUrl, input.regionCode, input.personaCode,
        input.productFamilyCode, input.commodityCode, input.period, input.metric, input.value, input.unit, input.direction,
        input.confidence, input.evidenceGrade, input.dataStatus, input.missingReason, input.title, input.summary,
        JSON.stringify(input.raw), input.collectedAt, input.expiresAt, signalId).run();
  } else {
    await db.prepare(`INSERT INTO market_signals
      (id, fingerprint, monitor_id, signal_type, source_id, source_name, source_url, region_code, persona_code,
       product_family_code, commodity_code, period, metric, value, unit, direction, confidence, evidence_grade,
       data_status, missing_reason, title, summary, raw_json, collected_at, expires_at, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(signalId, fingerprint, monitorId, input.signalType, input.sourceId, input.sourceName, input.sourceUrl,
        input.regionCode, input.personaCode, input.productFamilyCode, input.commodityCode, input.period, input.metric,
        input.value, input.unit, input.direction, input.confidence, input.evidenceGrade, input.dataStatus,
        input.missingReason, input.title, input.summary, JSON.stringify(input.raw), input.collectedAt, input.expiresAt, nowIso()).run();
  }
  const timestamp = nowIso();
  await db.prepare(`INSERT INTO market_signal_monitor_refs (signal_id, monitor_id, first_seen_at, last_seen_at)
    VALUES (?, ?, ?, ?) ON CONFLICT(signal_id, monitor_id) DO UPDATE SET last_seen_at = excluded.last_seen_at`)
    .bind(signalId, monitorId, timestamp, timestamp).run();
  await db.prepare(`INSERT OR IGNORE INTO market_signal_versions
    (id, signal_id, fingerprint, version_hash, payload_json, collected_at, imported_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)`)
    .bind(crypto.randomUUID(), signalId, fingerprint, versionHash, JSON.stringify(normalizedPayload), input.collectedAt, timestamp).run();
  return signalId;
}

async function persistOfficialConnectorResult(
  runId: string,
  monitorId: string,
  result: OfficialTradeConnectorResult,
  startedAt: string,
  completedAt: string,
) {
  const db = getRawDb();
  const successfulRequest = result.status === "completed" || result.status === "no_data";
  const failedRequest = result.status === "failed";
  await db.batch([
    db.prepare(`INSERT INTO market_signal_source_runs
      (id, run_id, monitor_id, source_id, status, error_category, error_message, coverage_countries,
       result_count, duration_ms, retry_count, quota_summary, update_frequency, started_at, completed_at, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(crypto.randomUUID(), runId, monitorId, result.sourceId, result.status, result.errorCategory,
        result.errorMessage, JSON.stringify(result.coverageCountries), result.resultCount, result.durationMs,
        result.retryCount, result.quotaSummary, result.updateFrequency, startedAt, completedAt, completedAt),
    db.prepare(`INSERT INTO intelligence_source_health
      (source_id, monitor_id, status, coverage_countries, quota_summary, update_frequency,
       last_attempt_at, last_success_at, last_failure_at, last_error_category, last_error,
       consecutive_failures, result_count, duration_ms, retry_count, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(source_id, monitor_id) DO UPDATE SET
        status = excluded.status,
        coverage_countries = excluded.coverage_countries,
        quota_summary = excluded.quota_summary,
        update_frequency = excluded.update_frequency,
        last_attempt_at = excluded.last_attempt_at,
        last_success_at = CASE WHEN ? THEN excluded.last_success_at ELSE intelligence_source_health.last_success_at END,
        last_failure_at = CASE WHEN ? THEN excluded.last_failure_at ELSE intelligence_source_health.last_failure_at END,
        last_error_category = excluded.last_error_category,
        last_error = excluded.last_error,
        consecutive_failures = CASE WHEN ? THEN intelligence_source_health.consecutive_failures + 1 WHEN ? THEN 0 ELSE intelligence_source_health.consecutive_failures END,
        result_count = excluded.result_count,
        duration_ms = excluded.duration_ms,
        retry_count = excluded.retry_count,
        updated_at = excluded.updated_at`)
      .bind(result.sourceId, monitorId, result.status, JSON.stringify(result.coverageCountries), result.quotaSummary,
        result.updateFrequency, completedAt, successfulRequest ? completedAt : null, failedRequest ? completedAt : null,
        result.errorCategory, result.errorMessage, failedRequest ? 1 : 0, result.resultCount, result.durationMs,
        result.retryCount, completedAt, successfulRequest ? 1 : 0, failedRequest ? 1 : 0,
        failedRequest ? 1 : 0, successfulRequest ? 1 : 0),
  ]);
}

async function refreshIntelligenceCandidate(monitor: JsonRecord) {
  const db = getRawDb();
  const rows = await db.prepare(`SELECT s.id, s.signal_type, s.source_id, s.data_status, s.evidence_grade,
      s.direction, s.period, s.confidence
    FROM market_signal_monitor_refs mr JOIN market_signals s ON s.id = mr.signal_id
    WHERE mr.monitor_id = ? ORDER BY s.collected_at DESC LIMIT 500`).bind(monitor.id).all<JsonRecord>();
  const assessment = assessSignalOpportunity(rows.results.map((row): AssessableMarketSignal => ({
    id: String(row.id),
    signalType: String(row.signal_type) as MarketSignalType,
    sourceId: String(row.source_id),
    dataStatus: String(row.data_status),
    evidenceGrade: String(row.evidence_grade),
    direction: String(row.direction ?? "unknown"),
    period: String(row.period ?? ""),
    confidence: Number(row.confidence ?? 0),
  })));
  if (!assessment.readyForReview) return assessment;
  const timestamp = nowIso();
  const opportunityLabels: Record<string, string> = {
    short_term: "短期事件机会候选",
    long_term: "长期增长机会候选",
    blue_ocean_candidate: "蓝海假设候选",
    growth_red_ocean: "增长型红海候选",
    observe: "继续观察",
  };
  const title = `${String(monitor.region_name || monitor.region_code)} · ${String(monitor.trigger_name)} · ${String(monitor.product_family_name || monitor.name)}`;
  const summary = `${assessment.sourceCount} 个独立来源、${assessment.signalTypeCount} 类可靠证据达到人工复核门槛。`;
  const rationale = `${opportunityLabels[assessment.opportunityType]}；这只是跨来源初筛，不代表真实采购、可成交价格或供应履约已经成立。`;
  const nextAction = "人工核对信号口径；确认后再从全球画像选择关联产品矩阵并建立第一轮验证项目。";
  await db.prepare(`INSERT INTO intelligence_opportunity_candidates
    (id, monitor_id, region_code, persona_code, product_family_code, trigger_type, title, opportunity_type,
     status, evidence_count, source_count, signal_ids, summary, rationale, blockers, next_action, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, ?, ?, ?, '[]', ?, ?, ?)
    ON CONFLICT(monitor_id) DO UPDATE SET opportunity_type = excluded.opportunity_type,
      evidence_count = excluded.evidence_count, source_count = excluded.source_count, signal_ids = excluded.signal_ids,
      summary = excluded.summary, rationale = excluded.rationale, blockers = excluded.blockers,
      next_action = excluded.next_action, updated_at = excluded.updated_at`)
    .bind(crypto.randomUUID(), monitor.id, monitor.region_code, monitor.persona_code, monitor.product_family_code,
      monitor.trigger_type, title, assessment.opportunityType, assessment.evidenceCount, assessment.sourceCount,
      JSON.stringify(assessment.signalIds), summary, rationale, nextAction, timestamp, timestamp).run();
  return assessment;
}

async function executeMarketSignalMonitor(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const monitorId = reportText(payload.monitorId, 100);
  const triggerReason = reportText(payload.triggerReason, 30) || "manual";
  const monitor = await db.prepare(`SELECT m.*, r.name AS region_name, p.name AS persona_name,
      r.countries AS region_countries, f.name AS product_family_name FROM market_signal_monitors m
      LEFT JOIN trade_regions r ON r.code = m.region_code
      LEFT JOIN buyer_persona_categories p ON p.code = m.persona_code
      LEFT JOIN product_family_master f ON f.code = m.product_family_code WHERE m.id = ?`)
    .bind(monitorId).first<JsonRecord>();
  if (!monitor) throw new Error("未找到监控规则");
  if (monitor.status !== "active") throw new Error("只有活动监控可以执行");
  const runId = crypto.randomUUID();
  const timestamp = nowIso();
  const runStartedMs = Date.now();
  const selectedSourceIds = stringList(monitor.source_ids, 12);
  const sourcePlan = intelligenceSourcePlan(stringList(monitor.signal_types, 10))
    .filter((source) => !selectedSourceIds.length || selectedSourceIds.includes(String(source.id)) || source.id === "national_statistics");
  await db.prepare(`INSERT INTO market_signal_runs
    (id, monitor_id, status, trigger_reason, source_plan, requested_at, started_at, created_at, updated_at)
    VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?)`)
    .bind(runId, monitorId, triggerReason, JSON.stringify(sourcePlan), timestamp, timestamp, timestamp, timestamp).run();
  const signalIds = new Set<string>();
  const connectorResults: OfficialTradeConnectorResult[] = [];
  try {
    if (stringList(monitor.signal_types, 10).includes("official_trade")) {
      const credential: Record<string, string> = await readManagedCredential("un_comtrade").catch(() => ({} as Record<string, string>));
      connectorResults.push(...await collectOfficialTradeSignals({
        regionCode: String(monitor.region_code),
        countryCodes: stringList(monitor.region_countries, 60),
        commodityCodes: stringList(monitor.commodity_codes, 12),
        sourceIds: selectedSourceIds,
        unComtradeApiKey: credential.apiKey ?? "",
      }));
      const connectorCompletedAt = nowIso();
      for (const result of connectorResults) {
        await persistOfficialConnectorResult(runId, monitorId, result, timestamp, connectorCompletedAt);
        for (const observation of result.observations) {
          signalIds.add(await upsertMarketSignal(monitorId, {
            signalType: "official_trade",
            sourceId: observation.sourceId,
            sourceName: observation.sourceName,
            sourceUrl: observation.sourceUrl,
            regionCode: String(monitor.region_code),
            // Official trade facts belong to a region + commodity + period, not to one buyer persona
            // or project family. Monitor references provide the business context without duplicating facts.
            personaCode: "",
            productFamilyCode: "",
            commodityCode: observation.commodityCode,
            period: observation.period,
            metric: observation.metric,
            value: observation.value,
            unit: observation.unit,
            direction: "unknown",
            confidence: 90,
            evidenceGrade: "official",
            dataStatus: "available",
            missingReason: "",
            title: observation.title,
            summary: `${observation.summary} 报告国/地区：${observation.reporterCode}。`,
            collectedAt: connectorCompletedAt,
            expiresAt: new Date(Date.now() + 180 * 86_400_000).toISOString(),
            externalId: `${observation.reporterCode}:${observation.flow}`,
            raw: observation.raw,
          }));
        }
      }
    }
    if (monitor.product_family_code) {
      const tradeRows = await db.prepare(`SELECT * FROM trade_data_observations
        WHERE product_family_code = ? AND (? = 'GLOBAL' OR region_code = ?)
        ORDER BY collected_at DESC LIMIT 200`)
        .bind(monitor.product_family_code, monitor.region_code, monitor.region_code).all<JsonRecord>();
      for (const row of tradeRows.results) {
        const sourceGrade = String(row.source_grade ?? "");
        const sourceId = sourceIdFromTradeObservation(row);
        signalIds.add(await upsertMarketSignal(monitorId, {
          signalType: "official_trade",
          sourceId,
          sourceName: String(row.source_name),
          sourceUrl: String(row.source_url),
          regionCode: String(row.region_code),
          personaCode: String(monitor.persona_code ?? ""),
          productFamilyCode: String(row.product_family_code),
          commodityCode: String(row.commodity_code),
          period: String(row.period),
          metric: String(row.metric),
          value: row.value === null || row.value === undefined ? null : Number(row.value),
          unit: String(row.unit ?? ""),
          direction: "unknown",
          confidence: sourceGrade.startsWith("official") ? 85 : 50,
          evidenceGrade: sourceGrade.startsWith("official") ? "official" : "supporting",
          dataStatus: String(row.data_status ?? "missing"),
          missingReason: String(row.missing_reason ?? ""),
          title: `${String(row.commodity_label)} · ${String(row.period)} ${String(row.metric)}`,
          summary: `${String(row.flow)}；来源口径 ${String(row.classification)} ${String(row.commodity_code)}。`,
          collectedAt: String(row.collected_at),
          expiresAt: null,
          externalId: `${String(row.reporter_code)}:${String(row.flow)}`,
          raw: jsonObject(row.raw_record),
        }));
      }
    }
    const eventRows = await db.prepare(`SELECT * FROM intelligence_events
      WHERE status = 'active' AND trigger_type = ? AND (region_code = ? OR region_code = 'GLOBAL' OR ? = 'GLOBAL')
        AND datetime(starts_at) >= datetime('now', '-30 days')
      ORDER BY datetime(starts_at) LIMIT 100`)
      .bind(monitor.trigger_type, monitor.region_code, monitor.region_code).all<JsonRecord>();
    for (const row of eventRows.results) {
      signalIds.add(await upsertMarketSignal(monitorId, {
        signalType: "event",
        sourceId: "event_calendar",
        sourceName: String(row.source_name),
        sourceUrl: String(row.source_url),
        regionCode: String(row.region_code),
        personaCode: String(monitor.persona_code ?? ""),
        productFamilyCode: String(monitor.product_family_code ?? ""),
        commodityCode: "",
        period: String(row.starts_at).slice(0, 10),
        metric: "event_window",
        value: null,
        unit: "",
        direction: "unknown",
        confidence: 70,
        evidenceGrade: "primary",
        dataStatus: "available",
        missingReason: "",
        title: String(row.name),
        summary: String(row.notes ?? ""),
        collectedAt: String(row.updated_at ?? row.created_at),
        expiresAt: row.ends_at ? String(row.ends_at) : null,
        externalId: String(row.id),
        raw: { startsAt: row.starts_at, endsAt: row.ends_at, procurementLeadDays: row.procurement_lead_days, deliveryCutoff: row.delivery_cutoff },
      }));
    }
    const assessment = await refreshIntelligenceCandidate(monitor);
    const failedConnectors = connectorResults.filter((result) => result.status === "failed");
    const status = signalIds.size ? "completed" : failedConnectors.length ? "failed" : "waiting_for_data";
    const completedAt = nowIso();
    const nextRunAt = new Date(Date.now() + Math.max(1, Number(monitor.cadence_days) || 7) * 86_400_000).toISOString();
    const durationMs = Date.now() - runStartedMs;
    const retryCount = connectorResults.reduce((sum, result) => sum + result.retryCount, 0);
    const errorCategory = failedConnectors.map((result) => result.errorCategory).filter(Boolean).join(",");
    const errorMessage = failedConnectors.map((result) => `${result.sourceName}：${result.errorMessage}`).join("；");
    const resultJson = {
      ...assessment,
      sources: connectorResults.map((result) => ({
        sourceId: result.sourceId,
        sourceName: result.sourceName,
        status: result.status,
        errorCategory: result.errorCategory,
        errorMessage: result.errorMessage,
        coverageCountries: result.coverageCountries,
        resultCount: result.resultCount,
        durationMs: result.durationMs,
        retryCount: result.retryCount,
      })),
    };
    await db.batch([
      db.prepare(`UPDATE market_signal_runs SET status = ?, result_json = ?, completed_at = ?, signal_count = ?,
        duration_ms = ?, retry_count = ?, error_category = ?, error = ?, updated_at = ? WHERE id = ?`)
        .bind(status, JSON.stringify(resultJson), completedAt, signalIds.size, durationMs, retryCount,
          errorCategory, errorMessage, completedAt, runId),
      db.prepare("UPDATE market_signal_monitors SET last_run_at = ?, next_run_at = ?, updated_at = ? WHERE id = ?")
        .bind(completedAt, nextRunAt, completedAt, monitorId),
    ]);
    return { ok: true, id: runId, status, signalCount: signalIds.size, assessment, sourcePlan, sources: resultJson.sources };
  } catch (error) {
    const failedAt = nowIso();
    const message = error instanceof Error ? error.message : "执行监控失败";
    const nextRunAt = new Date(Date.now() + Math.max(1, Number(monitor.cadence_days) || 7) * 86_400_000).toISOString();
    await db.batch([
      db.prepare("UPDATE market_signal_runs SET status = 'failed', error_category = 'unknown', error = ?, completed_at = ?, duration_ms = ?, updated_at = ? WHERE id = ?")
        .bind(message, failedAt, Date.now() - runStartedMs, failedAt, runId),
      db.prepare("UPDATE market_signal_monitors SET last_run_at = ?, next_run_at = ?, updated_at = ? WHERE id = ?")
        .bind(failedAt, nextRunAt, failedAt, monitorId),
    ]);
    throw error;
  }
}

async function simulateMarketSignalMonitor(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const monitorId = reportText(payload.monitorId, 100);
  const scenario = reportText(payload.scenario, 40) as MonitorSimulationScenario;
  if (!MONITOR_SIMULATION_SCENARIOS.some((item) => item.id === scenario)) throw new Error("请选择有效的灰度测试场景");
  const monitor = await db.prepare("SELECT id, name, status, signal_types FROM market_signal_monitors WHERE id = ?")
    .bind(monitorId).first<JsonRecord>();
  if (!monitor) throw new Error("未找到监控规则");
  if (monitor.status === "archived") throw new Error("已归档监控不能执行灰度测试");
  const runId = crypto.randomUUID();
  const timestamp = nowIso();
  const simulation = simulateMonitorScenario(scenario);
  const result = {
    ...simulation,
    generatedAt: timestamp,
    isolation: "灰度数据仅保存在运行记录中，不写入正式信号、机会候选、评分或验证项目。",
  };
  const error = scenario === "source_failure" ? "灰度模拟：来源连接失败" : "";
  await db.prepare(`INSERT INTO market_signal_runs
    (id, monitor_id, status, trigger_reason, source_plan, result_json, requested_at, started_at,
     completed_at, signal_count, error, created_at, updated_at)
    VALUES (?, ?, ?, 'simulation', ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(runId, monitorId, simulation.runStatus, JSON.stringify(intelligenceSourcePlan(stringList(monitor.signal_types, 10))),
      JSON.stringify(result), timestamp, timestamp, timestamp, simulation.signals.length, error, timestamp, timestamp).run();
  return { ok: true, id: runId, monitorId, monitorName: String(monitor.name), ...result };
}

async function runDueMarketSignalMonitors(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const limit = Math.round(boundedNumber(payload.limit || 10, 1, 20));
  const rows = await db.prepare(`SELECT id FROM market_signal_monitors
    WHERE status = 'active' AND (next_run_at IS NULL OR next_run_at = '' OR datetime(next_run_at) <= datetime('now'))
    ORDER BY datetime(next_run_at), updated_at LIMIT ?`).bind(limit).all<{ id: string }>();
  const results = [];
  for (const row of rows.results) {
    try {
      results.push(await executeMarketSignalMonitor({ monitorId: row.id, triggerReason: "schedule" }));
    } catch (error) {
      results.push({ ok: false, monitorId: row.id, error: error instanceof Error ? error.message : "执行失败" });
    }
  }
  return { ok: true, processed: rows.results.length, results };
}

function validEvidenceUrl(value: string) {
  try {
    return ["http:", "https:"].includes(new URL(value).protocol);
  } catch {
    return false;
  }
}

async function importMarketSignals(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const monitorId = reportText(payload.monitorId, 100);
  const monitor = await db.prepare(`SELECT m.*, r.name AS region_name, f.name AS product_family_name
    FROM market_signal_monitors m LEFT JOIN trade_regions r ON r.code = m.region_code
    LEFT JOIN product_family_master f ON f.code = m.product_family_code WHERE m.id = ?`).bind(monitorId).first<JsonRecord>();
  if (!monitor) throw new Error("未找到监控规则");
  const rawSignals = jsonArray(payload.signals).slice(0, 500);
  if (!rawSignals.length) throw new Error("至少导入一条信号");
  const validTypes = new Set(MARKET_SIGNAL_LAYERS.map((layer) => layer.id));
  const validStatuses = new Set(["available", "missing", "blocked"]);
  const validGrades = new Set(["official", "primary", "supporting", "internal"]);
  const validDirections = new Set(["rising", "stable", "falling", "limited", "unknown"]);
  const signalIds = new Set<string>();
  for (let index = 0; index < rawSignals.length; index += 1) {
    const item = asObject(rawSignals[index]);
    const signalType = reportText(item.signalType ?? item.signal_type, 40) as MarketSignalType;
    const sourceId = reportText(item.sourceId ?? item.source_id, 100);
    const sourceName = reportText(item.sourceName ?? item.source_name, 160);
    const sourceUrl = reportText(item.sourceUrl ?? item.source_url, 1000);
    const dataStatus = reportText(item.dataStatus ?? item.data_status, 30) || "available";
    const evidenceGrade = reportText(item.evidenceGrade ?? item.evidence_grade, 30) || "supporting";
    const direction = reportText(item.direction, 30) || "unknown";
    const missingReason = reportText(item.missingReason ?? item.missing_reason, 500);
    const title = reportText(item.title, 240);
    const collectedAtRaw = reportText(item.collectedAt ?? item.collected_at, 80);
    const collectedAtDate = new Date(collectedAtRaw);
    if (!validTypes.has(signalType)) throw new Error(`第 ${index + 1} 条的信号类型无效`);
    if (!sourceId || !sourceName || !validEvidenceUrl(sourceUrl)) throw new Error(`第 ${index + 1} 条必须提供来源标识、名称和可打开的 http/https 链接`);
    if (!validStatuses.has(dataStatus)) throw new Error(`第 ${index + 1} 条的数据状态无效`);
    if (!validGrades.has(evidenceGrade)) throw new Error(`第 ${index + 1} 条的证据等级无效`);
    if (!validDirections.has(direction)) throw new Error(`第 ${index + 1} 条的趋势方向无效`);
    if (!title || Number.isNaN(collectedAtDate.getTime())) throw new Error(`第 ${index + 1} 条必须提供标题和有效采集时间`);
    if (dataStatus !== "available" && !missingReason) throw new Error(`第 ${index + 1} 条缺失或受阻时必须说明原因`);
    if (dataStatus !== "available" && item.value !== null && item.value !== undefined && item.value !== "") throw new Error(`第 ${index + 1} 条缺失或受阻时不能填写数值`);
    const numericValue = item.value === null || item.value === undefined || item.value === "" ? null : Number(item.value);
    if (numericValue !== null && !Number.isFinite(numericValue)) throw new Error(`第 ${index + 1} 条数值无效`);
    signalIds.add(await upsertMarketSignal(monitorId, {
      signalType,
      sourceId,
      sourceName,
      sourceUrl,
      regionCode: reportText(item.regionCode ?? item.region_code, 50).toUpperCase() || String(monitor.region_code),
      personaCode: reportText(item.personaCode ?? item.persona_code, 80) || String(monitor.persona_code ?? ""),
      productFamilyCode: reportText(item.productFamilyCode ?? item.product_family_code, 80) || String(monitor.product_family_code ?? ""),
      commodityCode: reportText(item.commodityCode ?? item.commodity_code, 80),
      period: reportText(item.period, 80),
      metric: reportText(item.metric, 120) || "observation",
      value: numericValue,
      unit: reportText(item.unit, 40),
      direction,
      confidence: Math.round(boundedNumber(item.confidence ?? 50, 0, 100)),
      evidenceGrade,
      dataStatus,
      missingReason,
      title,
      summary: reportText(item.summary, 1200),
      collectedAt: collectedAtDate.toISOString(),
      expiresAt: item.expiresAt || item.expires_at ? new Date(String(item.expiresAt ?? item.expires_at)).toISOString() : null,
      externalId: reportText(item.externalId ?? item.external_id, 160),
      raw: asObject(item.raw ?? item.raw_json),
    }));
  }
  const assessment = await refreshIntelligenceCandidate(monitor);
  return { ok: true, imported: signalIds.size, assessment };
}

async function upsertIntelligenceEvent(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const id = reportText(payload.id, 100) || crypto.randomUUID();
  const name = reportText(payload.name, 200);
  const regionCode = reportText(payload.regionCode, 50).toUpperCase();
  const triggerType = reportText(payload.triggerType, 80);
  const startsAt = new Date(String(payload.startsAt ?? ""));
  const endsAt = payload.endsAt ? new Date(String(payload.endsAt)) : null;
  const sourceName = reportText(payload.sourceName, 160);
  const sourceUrl = reportText(payload.sourceUrl, 1000);
  if (!name || !regionCode || !triggerById(triggerType) || Number.isNaN(startsAt.getTime())) throw new Error("请填写事件名称、地区、事件类型和有效开始时间");
  if (endsAt && (Number.isNaN(endsAt.getTime()) || endsAt < startsAt)) throw new Error("结束时间不能早于开始时间");
  if (!sourceName || !validEvidenceUrl(sourceUrl)) throw new Error("事件必须提供可核验的来源名称和 http/https 链接");
  const region = await db.prepare("SELECT code FROM trade_regions WHERE code = ? AND active = 1").bind(regionCode).first();
  if (!region) throw new Error("事件地区不存在或已停用");
  const leadDays = Math.round(boundedNumber(payload.procurementLeadDays, 0, 730));
  const deliveryCutoff = payload.deliveryCutoff ? new Date(String(payload.deliveryCutoff)) : null;
  if (deliveryCutoff && Number.isNaN(deliveryCutoff.getTime())) throw new Error("交付截止时间无效");
  const fingerprint = [name, regionCode, triggerType, startsAt.toISOString().slice(0, 10)].map((value) => String(value).trim().toLocaleLowerCase()).join("|");
  const timestamp = nowIso();
  await db.prepare(`INSERT INTO intelligence_events
    (id, fingerprint, name, region_code, trigger_type, starts_at, ends_at, procurement_lead_days,
     delivery_cutoff, source_name, source_url, notes, status, created_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'user', ?, ?)
    ON CONFLICT(fingerprint) DO UPDATE SET ends_at = excluded.ends_at,
      procurement_lead_days = excluded.procurement_lead_days, delivery_cutoff = excluded.delivery_cutoff,
      source_name = excluded.source_name, source_url = excluded.source_url, notes = excluded.notes,
      status = 'active', archived_at = NULL, updated_at = excluded.updated_at`)
    .bind(id, fingerprint, name, regionCode, triggerType, startsAt.toISOString(), endsAt?.toISOString() ?? null,
      leadDays, deliveryCutoff?.toISOString() ?? null, sourceName, sourceUrl, reportText(payload.notes, 1500), timestamp, timestamp).run();
  const savedEvent = await db
    .prepare("SELECT id FROM intelligence_events WHERE fingerprint = ?")
    .bind(fingerprint)
    .first<{ id: string }>();
  return { ok: true, id: savedEvent?.id ?? id };
}

async function setIntelligenceEventStatus(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const id = reportText(payload.id, 100);
  const status = reportText(payload.status, 20);
  if (!id || !["active", "archived"].includes(status)) throw new Error("事件状态参数无效");
  const timestamp = nowIso();
  const result = await db.prepare(`UPDATE intelligence_events SET status = ?, archived_at = CASE WHEN ? = 'archived' THEN ? ELSE NULL END,
    updated_at = ? WHERE id = ?`).bind(status, status, timestamp, timestamp, id).run();
  if (!result.meta.changes) throw new Error("未找到事件");
  return { ok: true, id, status };
}

async function reviewIntelligenceCandidate(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const id = reportText(payload.id, 100);
  const status = reportText(payload.status, 30);
  const reviewNote = reportText(payload.reviewNote, 1000);
  if (!id || !["accepted", "observing", "passed", "merged"].includes(status)) throw new Error("候选复核状态无效");
  if (["passed", "merged"].includes(status) && !reviewNote) throw new Error("Pass 或合并候选时必须填写原因");
  const timestamp = nowIso();
  const result = await db.prepare(`UPDATE intelligence_opportunity_candidates
    SET status = ?, review_note = ?, reviewed_at = ?, updated_at = ? WHERE id = ?`)
    .bind(status, reviewNote, timestamp, timestamp, id).run();
  if (!result.meta.changes) throw new Error("未找到机会候选");
  return { ok: true, id, status };
}

async function readIntelligenceStation(url: URL) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const page = Math.max(1, Math.floor(Number(url.searchParams.get("page")) || 1));
  const pageSize = Math.round(boundedNumber(Number(url.searchParams.get("pageSize")) || 12, 6, 30));
  const query = reportText(url.searchParams.get("q"), 120).toLocaleLowerCase();
  const status = String(url.searchParams.get("status") ?? "active");
  const regionCode = String(url.searchParams.get("region") ?? "all");
  const triggerType = String(url.searchParams.get("trigger") ?? "all");
  const conditions: string[] = [];
  const bindings: unknown[] = [];
  if (query) {
    conditions.push("lower(m.name || ' ' || m.trigger_name || ' ' || m.keywords || ' ' || COALESCE(p.name, '') || ' ' || COALESCE(f.name, '')) LIKE ?");
    bindings.push(`%${query}%`);
  }
  if (status !== "all") {
    conditions.push("m.status = ?");
    bindings.push(status);
  }
  if (regionCode !== "all") {
    conditions.push("m.region_code = ?");
    bindings.push(regionCode);
  }
  if (triggerType !== "all") {
    conditions.push("m.trigger_type = ?");
    bindings.push(triggerType);
  }
  const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
  const countRow = await db.prepare(`SELECT COUNT(*) AS count
    FROM market_signal_monitors m
    LEFT JOIN buyer_persona_categories p ON p.code = m.persona_code
    LEFT JOIN product_family_master f ON f.code = m.product_family_code ${where}`)
    .bind(...bindings).first<{ count: number }>();
  const total = Number(countRow?.count ?? 0);
  const monitorRows = await db.prepare(`SELECT m.*, r.name AS region_name, p.name AS persona_name,
      f.name AS product_family_name,
      (SELECT COUNT(*) FROM market_signal_monitor_refs mr WHERE mr.monitor_id = m.id) AS signal_count,
      (SELECT MAX(s.collected_at) FROM market_signal_monitor_refs mr JOIN market_signals s ON s.id = mr.signal_id WHERE mr.monitor_id = m.id) AS latest_signal_at,
      (SELECT status FROM market_signal_runs run WHERE run.monitor_id = m.id AND run.trigger_reason != 'simulation' ORDER BY run.created_at DESC LIMIT 1) AS latest_run_status
    FROM market_signal_monitors m
    LEFT JOIN trade_regions r ON r.code = m.region_code
    LEFT JOIN buyer_persona_categories p ON p.code = m.persona_code
    LEFT JOIN product_family_master f ON f.code = m.product_family_code
    ${where}
    ORDER BY CASE m.status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
             CASE WHEN m.next_run_at IS NULL OR m.next_run_at = '' THEN 0 ELSE 1 END,
             m.next_run_at, m.updated_at DESC, m.id
    LIMIT ? OFFSET ?`).bind(...bindings, pageSize, (page - 1) * pageSize).all<JsonRecord>();
  const [signalRows, statsRow, regions, personas, families, runRows, candidateRows, eventRows, sourceHealthRows] = await Promise.all([
    db.prepare(`SELECT s.*, r.name AS region_name, p.name AS persona_name, f.name AS product_family_name
      FROM market_signals s
      LEFT JOIN trade_regions r ON r.code = s.region_code
      LEFT JOIN buyer_persona_categories p ON p.code = s.persona_code
      LEFT JOIN product_family_master f ON f.code = s.product_family_code
      ORDER BY s.collected_at DESC, s.id LIMIT 100`).all<JsonRecord>(),
    db.prepare(`SELECT
      COUNT(*) AS total_monitors,
      SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_monitors,
      SUM(CASE WHEN status = 'active' AND (next_run_at IS NULL OR next_run_at = '' OR datetime(next_run_at) <= datetime('now')) THEN 1 ELSE 0 END) AS due_monitors,
      COUNT(DISTINCT CASE WHEN status = 'active' THEN region_code END) AS covered_regions
      FROM market_signal_monitors`).first<JsonRecord>(),
    db.prepare("SELECT code, name FROM trade_regions WHERE active = 1 ORDER BY CASE code WHEN 'GLOBAL' THEN 0 ELSE 1 END, macro_region, name").all<JsonRecord>(),
    db.prepare("SELECT code, name FROM buyer_persona_categories WHERE active = 1 ORDER BY group_name, name").all<JsonRecord>(),
    db.prepare("SELECT code, name, track_code FROM product_family_master WHERE active = 1 ORDER BY track_code, name").all<JsonRecord>(),
    db.prepare(`SELECT run.*, m.name AS monitor_name FROM market_signal_runs run
      JOIN market_signal_monitors m ON m.id = run.monitor_id ORDER BY run.created_at DESC LIMIT 30`).all<JsonRecord>(),
    db.prepare(`SELECT c.*, r.name AS region_name, p.name AS persona_name, f.name AS product_family_name,
      m.name AS monitor_name FROM intelligence_opportunity_candidates c
      JOIN market_signal_monitors m ON m.id = c.monitor_id
      LEFT JOIN trade_regions r ON r.code = c.region_code
      LEFT JOIN buyer_persona_categories p ON p.code = c.persona_code
      LEFT JOIN product_family_master f ON f.code = c.product_family_code
      ORDER BY CASE c.status WHEN 'pending_review' THEN 0 WHEN 'accepted' THEN 1 WHEN 'observing' THEN 2 ELSE 3 END,
        c.updated_at DESC LIMIT 100`).all<JsonRecord>(),
    db.prepare(`SELECT e.*, r.name AS region_name FROM intelligence_events e
      LEFT JOIN trade_regions r ON r.code = e.region_code
      WHERE e.status = 'active' ORDER BY datetime(e.starts_at), e.name LIMIT 100`).all<JsonRecord>(),
    db.prepare(`SELECT h.*, m.name AS monitor_name FROM intelligence_source_health h
      JOIN market_signal_monitors m ON m.id = h.monitor_id
      ORDER BY h.updated_at DESC, h.source_id LIMIT 100`).all<JsonRecord>(),
  ]);
  const signals = signalRows.results.map(parseMarketSignal);
  const runs = runRows.results.map(parseMarketSignalRun);
  const productionRuns = runs.filter((item) => item.trigger_reason !== "simulation");
  const candidates = candidateRows.results.map(parseIntelligenceCandidate);
  const events = eventRows.results;
  return {
    monitors: monitorRows.results.map(parseMarketSignalMonitor),
    signals,
    runs,
    candidates,
    events,
    sourceHealth: sourceHealthRows.results.map((row) => ({
      ...row,
      coverage_countries: stringList(row.coverage_countries, 60),
      result_count: Number(row.result_count ?? 0),
      duration_ms: Number(row.duration_ms ?? 0),
      retry_count: Number(row.retry_count ?? 0),
      consecutive_failures: Number(row.consecutive_failures ?? 0),
    })),
    page,
    pageSize,
    total,
    totalPages: Math.max(1, Math.ceil(total / pageSize)),
    stats: {
      totalMonitors: Number(statsRow?.total_monitors ?? 0),
      activeMonitors: Number(statsRow?.active_monitors ?? 0),
      dueMonitors: Number(statsRow?.due_monitors ?? 0),
      coveredRegions: Number(statsRow?.covered_regions ?? 0),
      availableSignals: signals.filter((item) => item.data_status === "available").length,
      actionableSignals: signals.filter((item) => item.data_status === "available" && Number(item.confidence) >= 60 && ["primary", "official", "internal"].includes(String(item.evidence_grade))).length,
      pendingCandidates: candidates.filter((item) => item.status === "pending_review").length,
      waitingRuns: productionRuns.filter((item) => item.status === "waiting_for_data").length,
      failedRuns: productionRuns.filter((item) => item.status === "failed").length,
      upcomingEvents: events.filter((item) => new Date(String(item.starts_at)).getTime() >= Date.now()).length,
    },
    taxonomy: { regions: regions.results, personas: personas.results, productFamilies: families.results },
    signalLayers: MARKET_SIGNAL_LAYERS,
    triggerCatalog: TRIGGER_CATALOG,
    sourceCatalog: INTELLIGENCE_SOURCE_CATALOG,
    actionItems: [
      ...candidates.filter((item) => item.status === "pending_review").map((item) => ({ type: "candidate_review", id: item.id, title: item.title, detail: item.next_action })),
      ...productionRuns.filter((item) => item.status === "waiting_for_data").slice(0, 10).map((item) => ({ type: "data_required", id: item.id, title: item.monitor_name, detail: "本地暂无可复用证据，请到统一数据源中心完成授权或导入。" })),
      ...productionRuns.filter((item) => item.status === "failed").slice(0, 10).map((item) => ({ type: "run_failed", id: item.id, title: item.monitor_name, detail: item.error })),
    ],
  };
}

async function createMarketSignalMonitor(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const regionCode = reportText(payload.regionCode, 50).toUpperCase();
  const triggerType = reportText(payload.triggerType, 80);
  const trigger = triggerById(triggerType);
  const triggerName = reportText(payload.triggerName || trigger?.name, 120);
  const personaCode = reportText(payload.personaCode, 80);
  const productFamilyCode = reportText(payload.productFamilyCode, 80);
  const keywords = stringList(payload.keywords, 30);
  const commodityCodes = normalizeCommodityCodes(stringList(payload.commodityCodes, 12));
  const allowedSourceIds = new Set(["un_comtrade", "eurostat_comext", "uk_hmrc"]);
  const sourceIds = stringList(payload.sourceIds, 12).filter((item) => allowedSourceIds.has(item));
  const requestedSignalTypes = stringList(payload.signalTypes, 10);
  const validSignalTypes = new Set(MARKET_SIGNAL_LAYERS.map((item) => item.id));
  const signalTypes = (requestedSignalTypes.length ? requestedSignalTypes : trigger?.defaultSignalTypes ?? [])
    .filter((item) => validSignalTypes.has(item as never));
  const cadenceDays = Math.max(1, Math.min(90, Math.round(Number(payload.cadenceDays) || 7)));
  if (!regionCode || !trigger || !triggerName) throw new Error("请选择地区和触发事件");
  if (!keywords.length && !productFamilyCode) throw new Error("至少填写一个监控关键词或选择产品家族");
  const [region, persona, family] = await Promise.all([
    db.prepare("SELECT code FROM trade_regions WHERE code = ? AND active = 1").bind(regionCode).first(),
    personaCode ? db.prepare("SELECT code FROM buyer_persona_categories WHERE code = ? AND active = 1").bind(personaCode).first() : Promise.resolve({ code: "" }),
    productFamilyCode ? db.prepare("SELECT code FROM product_family_master WHERE code = ? AND active = 1").bind(productFamilyCode).first() : Promise.resolve({ code: "" }),
  ]);
  if (!region) throw new Error("目标地区不存在或已停用");
  if (personaCode && !persona) throw new Error("买家画像不存在或已停用");
  if (productFamilyCode && !family) throw new Error("产品家族不存在或已停用");
  const scopeKey = monitorScopeKey({ regionCode, triggerType, triggerName, personaCode, productFamilyCode });
  const existing = await db.prepare("SELECT id, status FROM market_signal_monitors WHERE scope_key = ?").bind(scopeKey).first<JsonRecord>();
  if (existing) throw new Error(existing.status === "archived" ? "相同监控已归档，请恢复原记录" : "相同地区、事件、画像和产品范围的监控已经存在");
  const id = crypto.randomUUID();
  const timestamp = nowIso();
  const name = reportText(payload.name, 160) || `${triggerName} · ${regionCode}`;
  await db.prepare(`INSERT INTO market_signal_monitors
    (id, scope_key, name, region_code, trigger_type, trigger_name, persona_code, product_family_code,
     keywords, signal_types, commodity_codes, source_ids, cadence_days, status, next_run_at, created_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, 'user', ?, ?)`)
    .bind(id, scopeKey, name, regionCode, triggerType, triggerName, personaCode, productFamilyCode,
      JSON.stringify(keywords), JSON.stringify(signalTypes), JSON.stringify(commodityCodes), JSON.stringify(sourceIds),
      cadenceDays, timestamp, timestamp, timestamp).run();
  return { ok: true, id };
}

async function updateMarketSignalMonitorSources(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const monitorId = reportText(payload.monitorId, 100);
  const commodityCodes = normalizeCommodityCodes(stringList(payload.commodityCodes, 12));
  const allowedSourceIds = new Set(["un_comtrade", "eurostat_comext", "uk_hmrc"]);
  const sourceIds = stringList(payload.sourceIds, 12).filter((item) => allowedSourceIds.has(item));
  if (!monitorId) throw new Error("缺少监控规则");
  if (!commodityCodes.length) throw new Error("至少确认一个 2、4、6 或 8 位 HS/CN 编码");
  if (!sourceIds.length) throw new Error("至少选择一个官方贸易来源");
  const timestamp = nowIso();
  const result = await db.prepare(`UPDATE market_signal_monitors
    SET commodity_codes = ?, source_ids = ?, next_run_at = ?, updated_at = ?
    WHERE id = ? AND status <> 'archived'`)
    .bind(JSON.stringify(commodityCodes), JSON.stringify(sourceIds), timestamp, timestamp, monitorId).run();
  if (!result.meta.changes) throw new Error("未找到可配置的监控规则");
  return { ok: true, id: monitorId, commodityCodes, sourceIds };
}

async function setMarketSignalMonitorStatus(payload: JsonRecord) {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const monitorId = reportText(payload.monitorId, 100);
  const status = reportText(payload.status, 20);
  if (!monitorId || !["active", "paused", "archived"].includes(status)) throw new Error("监控状态参数无效");
  const timestamp = nowIso();
  const result = await db.prepare(`UPDATE market_signal_monitors
    SET status = ?, archived_at = CASE WHEN ? = 'archived' THEN ? ELSE NULL END,
        next_run_at = CASE WHEN ? = 'active' AND (next_run_at IS NULL OR next_run_at = '') THEN ? ELSE next_run_at END,
        updated_at = ? WHERE id = ?`)
    .bind(status, status, timestamp, status, timestamp, timestamp, monitorId).run();
  if (!result.meta.changes) throw new Error("未找到监控规则");
  return { ok: true, id: monitorId, status };
}

function parseResearchProject(row: JsonRecord) {
  return {
    ...row,
    target_candidate_count: Math.max(1, Math.min(2000, Math.round(Number(row.target_candidate_count) || 2000))),
    target_markets: stringList(row.target_markets),
    languages: stringList(row.languages),
    channels: stringList(row.channels),
    scorecard: jsonObject(row.scorecard),
  };
}

function parseResearchCandidate(row: JsonRecord) {
  const candidate = {
    ...row,
    product_family: String(row.product_family || row.subcategory || ""),
    image_urls: stringList(row.image_urls, 6),
    image_source_ref: String(row.image_source_ref ?? ""),
    target_markets: stringList(row.target_markets, 100),
    buyer_types: stringList(row.buyer_types, 50),
    compliance: stringList(row.compliance, 50),
    score: row.score === null || row.score === undefined ? null : Number(row.score),
    selection_assessment: normalizeCandidateSelectionAssessment(jsonObject(row.selection_assessment)),
    odoo_sync_state: String(row.odoo_sync_state ?? "not_synced"),
    odoo_external_id: String(row.odoo_external_id ?? ""),
    odoo_synced_at: row.odoo_synced_at ? String(row.odoo_synced_at) : null,
  };
  return { ...candidate, handoff_readiness: candidateHandoffReadiness(candidate, candidate.selection_assessment) };
}

function parseResearchBuyerProfile(row: JsonRecord) {
  return {
    ...row,
    customer_groups: stringList(row.customer_groups, 50),
    sales_channels: stringList(row.sales_channels, 30),
    purchasing_scenarios: stringList(row.purchasing_scenarios, 50),
    odoo_lead_id: row.odoo_lead_id === null || row.odoo_lead_id === undefined ? null : Number(row.odoo_lead_id),
  };
}

function parseResearchBuyerFamilyLink(row: JsonRecord) {
  return {
    ...row,
    relationship_score: boundedNumber(row.relationship_score, 0, 100),
    sales_scenarios: stringList(row.sales_scenarios, 50),
  };
}

async function readGlobalBuyerLibrary() {
  const db = getRawDb();
  const [profiles, links, candidateFamilies, regions, personaCategories, productTracks, productFamilies, personaMatrix, personaProposals, personaChanges] = await Promise.all([
    db.prepare(`SELECT g.*,
      (SELECT COUNT(*) FROM global_buyer_project_refs r WHERE r.buyer_profile_id = g.id) AS source_project_count
      FROM global_buyer_profiles g
      ORDER BY CASE g.profile_status WHEN 'validated' THEN 0 WHEN 'qualified' THEN 1 WHEN 'hypothesis' THEN 2 ELSE 3 END,
               g.updated_at DESC LIMIT 2000`).all<JsonRecord>(),
    db.prepare("SELECT * FROM global_buyer_family_links ORDER BY relationship_score DESC, updated_at DESC LIMIT 10000").all<JsonRecord>(),
    db.prepare(`SELECT project_id, name, track_category,
      COALESCE(NULLIF(product_family, ''), subcategory) AS product_family,
      target_markets, buyer_types
      FROM research_candidates
      WHERE COALESCE(NULLIF(product_family, ''), subcategory) != ''
      ORDER BY updated_at DESC LIMIT 10000`).all<JsonRecord>(),
    db.prepare("SELECT * FROM trade_regions WHERE active = 1 ORDER BY CASE code WHEN 'GLOBAL' THEN 0 ELSE 1 END, macro_region, name").all<JsonRecord>(),
    db.prepare("SELECT * FROM buyer_persona_categories ORDER BY active DESC, group_name, name").all<JsonRecord>(),
    db.prepare("SELECT * FROM product_tracks WHERE active = 1 ORDER BY name").all<JsonRecord>(),
    db.prepare(`SELECT f.*, t.name AS track_name
      FROM product_family_master f JOIN product_tracks t ON t.code = f.track_code
      WHERE f.active = 1 AND t.active = 1 ORDER BY t.name, f.name`).all<JsonRecord>(),
    db.prepare("SELECT * FROM persona_product_matrix ORDER BY relevance_score DESC, persona_code, track_code").all<JsonRecord>(),
    db.prepare("SELECT * FROM buyer_persona_ai_proposals ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC LIMIT 200").all<JsonRecord>(),
    db.prepare("SELECT * FROM commercial_taxonomy_change_log WHERE entity_type = 'buyer_persona' ORDER BY created_at DESC LIMIT 200").all<JsonRecord>(),
  ]);
  const familyMap = new Map<string, {
    track_category: string;
    product_family: string;
    candidate_count: number;
    project_ids: Set<string>;
    target_markets: Set<string>;
    buyer_types: Set<string>;
    product_examples: string[];
  }>();
  for (const row of candidateFamilies.results) {
    const trackCategory = reportText(row.track_category, 120);
    const productFamily = reportText(row.product_family, 120);
    const key = `${trackCategory}|${productFamily}`.toLocaleLowerCase();
    const current = familyMap.get(key) ?? {
      track_category: trackCategory,
      product_family: productFamily,
      candidate_count: 0,
      project_ids: new Set<string>(),
      target_markets: new Set<string>(),
      buyer_types: new Set<string>(),
      product_examples: [],
    };
    current.candidate_count += 1;
    current.project_ids.add(String(row.project_id ?? ""));
    for (const market of stringList(row.target_markets, 100)) current.target_markets.add(market);
    for (const buyerType of stringList(row.buyer_types, 50)) current.buyer_types.add(buyerType);
    const example = reportText(row.name, 160);
    if (example && current.product_examples.length < 5 && !current.product_examples.includes(example)) current.product_examples.push(example);
    familyMap.set(key, current);
  }
  const parsedProfiles = profiles.results.map((row) => ({
    id: String(row.id),
    company_name: String(row.company_name ?? ""),
    website: String(row.website ?? ""),
    country: String(row.country ?? ""),
    buyer_type: String(row.buyer_type ?? ""),
    persona_code: String(row.persona_code ?? ""),
    region_code: String(row.region_code ?? ""),
    customer_groups: stringList(row.customer_groups, 50),
    sales_channels: stringList(row.sales_channels, 30),
    purchasing_scenarios: stringList(row.purchasing_scenarios, 50),
    seasonality: String(row.seasonality ?? ""),
    replenishment_cycle: String(row.replenishment_cycle ?? ""),
    order_requirements: String(row.order_requirements ?? ""),
    source_url: String(row.source_url ?? ""),
    profile_status: String(row.profile_status ?? "hypothesis"),
    created_by: String(row.created_by ?? "ai"),
    created_at: String(row.created_at ?? ""),
    updated_at: String(row.updated_at ?? ""),
    last_verified_at: row.last_verified_at ? String(row.last_verified_at) : null,
    source_project_count: Number(row.source_project_count ?? 0),
  }));
  const parsedLinks = links.results.map((row) => ({
    id: String(row.id),
    buyer_profile_id: String(row.buyer_profile_id),
    track_category: String(row.track_category ?? ""),
    product_family: String(row.product_family ?? ""),
    relationship_score: boundedNumber(row.relationship_score, 0, 100),
    family_role: String(row.family_role ?? "test"),
    sales_scenarios: stringList(row.sales_scenarios, 50),
    rationale: String(row.rationale ?? ""),
    evidence_status: String(row.evidence_status ?? "hypothesis"),
    created_by: String(row.created_by ?? "ai"),
    created_at: String(row.created_at ?? ""),
    updated_at: String(row.updated_at ?? ""),
  }));
  const families = [...familyMap.values()].map((item) => ({
    track_category: item.track_category,
    product_family: item.product_family,
    candidate_count: item.candidate_count,
    project_count: item.project_ids.size,
    target_markets: [...item.target_markets],
    buyer_types: [...item.buyer_types],
    product_examples: item.product_examples,
  })).sort((a, b) => b.candidate_count - a.candidate_count || a.product_family.localeCompare(b.product_family, "zh-CN"));
  const parsedRegions = regions.results.map((row) => ({
    code: String(row.code), name: String(row.name), macro_region: String(row.macro_region ?? ""),
    m49_code: String(row.m49_code ?? ""), countries: stringList(row.countries, 250),
    characteristics: stringList(row.characteristics, 30), source_url: String(row.source_url ?? ""),
    created_by: String(row.created_by ?? "system_seed"), updated_at: String(row.updated_at ?? ""),
  }));
  const parsedPersonaCategories = personaCategories.results.map((row) => ({
    code: String(row.code), group_name: String(row.group_name ?? ""), name: String(row.name),
    description: String(row.description ?? ""), value_chain_role: String(row.value_chain_role ?? ""),
    customer_groups: stringList(row.customer_groups, 50), sales_channels: stringList(row.sales_channels, 50),
    purchase_scenarios: stringList(row.purchase_scenarios, 50), buying_triggers: stringList(row.buying_triggers, 50),
    order_characteristics: stringList(row.order_characteristics, 50), compliance_focus: stringList(row.compliance_focus, 50),
    source_refs: stringList(row.source_refs, 30), version: Math.max(1, Number(row.version ?? 1)),
    last_reviewed_at: row.last_reviewed_at ? String(row.last_reviewed_at) : null,
    active: Number(row.active ?? 1) === 1,
    created_by: String(row.created_by ?? "system_seed"), updated_at: String(row.updated_at ?? ""),
  }));
  const parsedProductTracks = productTracks.results.map((row) => ({
    code: String(row.code), name: String(row.name), description: String(row.description ?? ""),
    buyer_value: String(row.buyer_value ?? ""), compliance_focus: stringList(row.compliance_focus, 50),
    created_by: String(row.created_by ?? "system_seed"), updated_at: String(row.updated_at ?? ""),
  }));
  const parsedProductFamilies = productFamilies.results.map((row) => ({
    code: String(row.code), track_code: String(row.track_code), track_name: String(row.track_name ?? ""),
    name: String(row.name), description: String(row.description ?? ""), use_scenarios: stringList(row.use_scenarios, 50),
    compliance_tags: stringList(row.compliance_tags, 50), keywords: stringList(row.keywords, 50),
    created_by: String(row.created_by ?? "system_seed"), updated_at: String(row.updated_at ?? ""),
  }));
  const parsedPersonaMatrix = personaMatrix.results.map((row) => ({
    id: String(row.id), persona_code: String(row.persona_code), region_code: String(row.region_code ?? "GLOBAL"),
    track_code: String(row.track_code), product_family_code: String(row.product_family_code ?? ""),
    relevance_score: boundedNumber(row.relevance_score, 0, 100), family_role: String(row.family_role ?? "test"),
    sales_scenarios: stringList(row.sales_scenarios, 50), seasonality: String(row.seasonality ?? ""),
    rationale: String(row.rationale ?? ""), evidence_status: String(row.evidence_status ?? "hypothesis"),
    created_by: String(row.created_by ?? "system_seed"), updated_at: String(row.updated_at ?? ""),
  }));
  const parsedPersonaProposals = personaProposals.results.map((row) => ({
    id: String(row.id), run_id: String(row.run_id), mode: String(row.mode ?? "discover"),
    target_code: String(row.target_code ?? ""), persona_code: String(row.persona_code),
    payload: jsonObject(row.payload), source_refs: stringList(row.source_refs, 30),
    rationale: String(row.rationale ?? ""), status: String(row.status ?? "pending"),
    created_at: String(row.created_at ?? ""), reviewed_at: row.reviewed_at ? String(row.reviewed_at) : null,
  }));
  const parsedPersonaChanges = personaChanges.results.map((row) => ({
    id: String(row.id), entity_code: String(row.entity_code), action: String(row.action),
    origin: String(row.origin ?? "user"), run_id: String(row.run_id ?? ""),
    before: jsonObject(row.before_json), after: jsonObject(row.after_json), created_at: String(row.created_at ?? ""),
  }));
  const activePersonaCategories = parsedPersonaCategories.filter((item) => item.active);
  return {
    profiles: parsedProfiles,
    links: parsedLinks,
    families,
    taxonomy: {
      regions: parsedRegions,
      personaCategories: activePersonaCategories,
      retiredPersonaCategories: parsedPersonaCategories.filter((item) => !item.active),
      productTracks: parsedProductTracks,
      productFamilies: parsedProductFamilies,
      personaMatrix: parsedPersonaMatrix,
    },
    personaProposals: parsedPersonaProposals,
    personaChanges: parsedPersonaChanges,
    stats: {
      profileCount: parsedProfiles.length,
      familyLinkCount: parsedLinks.length,
      familyCount: families.length,
      marketCount: new Set(parsedProfiles.map((item) => String(item.country))).size,
      validatedCount: parsedProfiles.filter((item) => item.profile_status === "validated").length,
      regionCount: parsedRegions.filter((item) => item.code !== "GLOBAL").length,
      personaCategoryCount: activePersonaCategories.length,
      retiredPersonaCategoryCount: parsedPersonaCategories.length - activePersonaCategories.length,
      pendingPersonaProposalCount: parsedPersonaProposals.filter((item) => item.status === "pending").length,
      trackCount: parsedProductTracks.length,
      masterFamilyCount: parsedProductFamilies.length,
      personaMatrixCount: parsedPersonaMatrix.length,
    },
  };
}

const OPPORTUNITY_EVIDENCE_TYPES = new Set(["demand", "buyer", "buyer_discovery", "channel", "competition", "product_matrix", "supply", "compliance", "fulfillment", "internal"]);
const OPPORTUNITY_EVIDENCE_GRADES = new Set<OpportunityEvidenceGrade>(["official", "verified_buyer", "supplier_quote", "internal_odoo", "marketplace", "other"]);
const OPPORTUNITY_ORIGINS = new Set(["user", "ai_assistant", "odoo"]);
const OPPORTUNITY_ROUND_PHASES = new Set(["discovery", "commercial", "pilot"]);
const OPPORTUNITY_ROUND_DECISIONS = new Set(["continue", "adjust", "extend", "hold", "pass"]);
const OPPORTUNITY_FAMILY_STATUSES = new Set(["candidate", "continue", "adjust", "pass"]);
const OPPORTUNITY_FEEDBACK_STATUSES = new Set(["contacted", "replied", "qualified", "no_need", "wrong_contact", "follow_up", "rfq", "sample", "trial"]);
const OPPORTUNITY_SHARED_EVIDENCE_TYPES = new Set(["demand", "channel", "competition", "product_matrix", "supply", "compliance"]);
const OPPORTUNITY_VOID_REASONS = new Set(["duplicate", "test_or_mistake", "wrong_scope", "merged", "invalid_data", "other"]);

function normalizedOpportunityScopePart(value: unknown) {
  return String(value ?? "").normalize("NFKC").trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

function opportunityProgramScopeKey(input: { personaCode: string; regionCode: string; purchaseScenario: string; salesChannel: string }) {
  return [input.personaCode, input.regionCode, input.purchaseScenario, input.salesChannel]
    .map(normalizedOpportunityScopePart).join("|");
}

function opportunityDossierIdentity(regionCode: string, productFamilyCode: string) {
  const normalizedRegion = normalizedOpportunityScopePart(regionCode);
  const normalizedFamily = normalizedOpportunityScopePart(productFamilyCode);
  return { id: `dossier:${normalizedRegion}:${normalizedFamily}`, scopeKey: `${normalizedRegion}|${normalizedFamily}` };
}

function opportunityEvidenceScope(evidenceType: string) {
  return OPPORTUNITY_SHARED_EVIDENCE_TYPES.has(evidenceType) ? "shared" : "project";
}

function opportunityOrigin(payload: JsonRecord) {
  const origin = String(payload.origin ?? "user");
  return OPPORTUNITY_ORIGINS.has(origin) ? origin : "user";
}

function opportunityFingerprint(input: {
  personaCode: string;
  regionCode: string;
  productFamilyCode: string;
  purchaseScenario: string;
  salesChannel: string;
}) {
  return [input.personaCode, input.regionCode, input.productFamilyCode, input.purchaseScenario, input.salesChannel]
    .map((item) => item.trim().toLocaleLowerCase())
    .join("|");
}

async function readOpportunityCenter() {
  await ensureResearchSchema();
  const db = getRawDb();
  const [library, cases, assessments, evidence, changes, tradeData, tradeRequests, validationRequests, programs, rounds, roundFamilies, customerFeedback] = await Promise.all([
    readGlobalBuyerLibrary(),
    db.prepare(`SELECT c.*, p.name AS persona_name, r.name AS region_name,
      t.name AS track_name, f.name AS product_family_name
      FROM opportunity_cases c
      JOIN buyer_persona_categories p ON p.code = c.persona_code
      JOIN trade_regions r ON r.code = c.region_code
      JOIN product_tracks t ON t.code = c.track_code
      JOIN product_family_master f ON f.code = c.product_family_code
      ORDER BY c.active DESC, CASE c.status WHEN 'pilot' THEN 0 WHEN 'qualified' THEN 1 WHEN 'validating' THEN 2 ELSE 3 END,
               c.updated_at DESC LIMIT 2000`).all<JsonRecord>(),
    db.prepare("SELECT * FROM opportunity_assessments ORDER BY created_at DESC LIMIT 10000").all<JsonRecord>(),
    db.prepare("SELECT * FROM opportunity_evidence ORDER BY captured_at DESC, created_at DESC LIMIT 20000").all<JsonRecord>(),
    db.prepare("SELECT * FROM opportunity_change_log ORDER BY created_at DESC LIMIT 1000").all<JsonRecord>(),
    db.prepare("SELECT * FROM trade_data_observations ORDER BY collected_at DESC, created_at DESC LIMIT 20000").all<JsonRecord>(),
    db.prepare("SELECT * FROM trade_data_refresh_requests ORDER BY created_at DESC LIMIT 2000").all<JsonRecord>(),
    db.prepare("SELECT * FROM opportunity_validation_requests ORDER BY created_at DESC LIMIT 2000").all<JsonRecord>(),
    db.prepare(`SELECT p.*, b.name AS persona_name, r.name AS region_name
      FROM opportunity_programs p
      JOIN buyer_persona_categories b ON b.code = p.persona_code
      JOIN trade_regions r ON r.code = p.region_code
      ORDER BY p.active DESC, p.updated_at DESC LIMIT 1000`).all<JsonRecord>(),
    db.prepare("SELECT * FROM opportunity_rounds ORDER BY program_id, round_number DESC LIMIT 5000").all<JsonRecord>(),
    db.prepare(`SELECT rf.*, f.name AS product_family_name, f.track_code, t.name AS track_name
      FROM opportunity_round_families rf
      JOIN product_family_master f ON f.code = rf.product_family_code
      JOIN product_tracks t ON t.code = f.track_code
      ORDER BY rf.round_id, rf.priority_rank, rf.created_at LIMIT 10000`).all<JsonRecord>(),
    db.prepare("SELECT * FROM opportunity_customer_feedback ORDER BY created_at DESC LIMIT 20000").all<JsonRecord>(),
  ]);
  const evidenceByCase = new Map<string, JsonRecord[]>();
  const sharedEvidenceByDossier = new Map<string, JsonRecord[]>();
  for (const row of evidence.results) {
    const opportunityId = String(row.opportunity_id);
    evidenceByCase.set(opportunityId, [...(evidenceByCase.get(opportunityId) ?? []), row]);
    const dossierId = String(row.dossier_id ?? "");
    if (dossierId && String(row.evidence_scope) === "shared") {
      sharedEvidenceByDossier.set(dossierId, [...(sharedEvidenceByDossier.get(dossierId) ?? []), row]);
    }
  }
  const latestAssessmentByCase = new Map<string, JsonRecord>();
  for (const row of assessments.results) {
    const opportunityId = String(row.opportunity_id);
    if (!latestAssessmentByCase.has(opportunityId)) latestAssessmentByCase.set(opportunityId, row);
  }
  const parsedCases = cases.results.map((row) => {
    const opportunityId = String(row.id);
    const directEvidence = evidenceByCase.get(opportunityId) ?? [];
    const sharedEvidence = sharedEvidenceByDossier.get(String(row.dossier_id ?? "")) ?? [];
    const caseEvidence = [...new Map([...directEvidence, ...sharedEvidence].map((item) => [String(item.id), item])).values()];
    const latestAssessment = latestAssessmentByCase.get(opportunityId);
    const signals = normalizeOpportunitySignals(latestAssessment ? jsonObject(latestAssessment.signals) : {});
    const evidenceGrades = caseEvidence
      .filter((item) => String(item.evidence_status) === "available")
      .map((item) => String(item.source_grade))
      .filter((grade): grade is OpportunityEvidenceGrade => OPPORTUNITY_EVIDENCE_GRADES.has(grade as OpportunityEvidenceGrade));
    const scores = computeOpportunityScores(signals, evidenceGrades);
    return {
      ...row,
      status: String(row.status ?? "hypothesis"),
      active: Number(row.active ?? 1) === 1,
      version: Math.max(1, Number(row.version ?? 1)),
      signals,
      scores,
      latest_assessment: latestAssessment ? {
        id: String(latestAssessment.id), rationale: String(latestAssessment.rationale ?? ""),
        created_by: String(latestAssessment.created_by ?? "user"), created_at: String(latestAssessment.created_at ?? ""),
      } : null,
      evidence_count: caseEvidence.length,
      last_evidence_at: caseEvidence[0] ? String(caseEvidence[0].captured_at ?? caseEvidence[0].created_at ?? "") : null,
    };
  });
  const parsedEvidence = evidence.results.map((row) => ({
    ...row,
    metrics: jsonObject(row.metrics),
  }));
  return {
    cases: parsedCases,
    evidence: parsedEvidence,
    tradeData: tradeData.results.map((row) => ({ ...row, value: row.value === null ? null : Number(row.value) })),
    tradeRequests: tradeRequests.results.map((row) => ({ ...row, force_refresh: Number(row.force_refresh ?? 0) === 1 })),
    validationRequests: validationRequests.results,
    programs: programs.results.map((row) => ({
      ...row,
      active: Number(row.active ?? 1) === 1,
      persona_version: Math.max(1, Number(row.persona_version ?? 1)),
      cycle_number: Math.max(1, Number(row.cycle_number ?? 1)),
      max_family_count: Math.max(1, Number(row.max_family_count ?? 5)),
      current_round_number: Math.max(1, Number(row.current_round_number ?? 1)),
      version: Math.max(1, Number(row.version ?? 1)),
    })),
    rounds: rounds.results.map((row) => ({ ...row, round_number: Math.max(1, Number(row.round_number ?? 1)) })),
    roundFamilies: roundFamilies.results.map((row) => ({
      ...row,
      priority_rank: Number(row.priority_rank ?? 0),
      matrix_score: Number(row.matrix_score ?? 0),
    })),
    customerFeedback: customerFeedback.results,
    changes: changes.results.map((row) => ({ ...row, before: jsonObject(row.before_json), after: jsonObject(row.after_json) })),
    taxonomy: library.taxonomy,
    stats: {
      total: parsedCases.length,
      active: parsedCases.filter((item) => item.active).length,
      validating: parsedCases.filter((item) => item.active && item.status === "validating").length,
      qualified: parsedCases.filter((item) => item.active && ["qualified", "pilot"].includes(String(item.status))).length,
      needsEvidence: parsedCases.filter((item) => item.active && item.scores.confidence < 50).length,
      archived: parsedCases.filter((item) => !item.active).length,
      localTradeObservations: tradeData.results.length,
      programs: programs.results.length,
      activePrograms: programs.results.filter((item) => Number(item.active ?? 1) === 1).length,
      validatingPrograms: programs.results.filter((item) => Number(item.active ?? 1) === 1 && ["round_active", "review_due"].includes(String(item.status))).length,
      scalingPrograms: programs.results.filter((item) => String(item.status) === "scaling").length,
      reviewDuePrograms: programs.results.filter((item) => Number(item.active ?? 1) === 1 && String(item.next_review_at ?? "") !== "" && String(item.next_review_at) < nowIso().slice(0, 10)).length,
      voidedPrograms: programs.results.filter((item) => String(item.status) === "voided").length,
    },
  };
}

async function readOpportunityProgramPage(url: URL) {
  await ensureResearchSchema();
  const page = Math.max(1, Math.floor(Number(url.searchParams.get("page")) || 1));
  const pageSize = Math.round(boundedNumber(Number(url.searchParams.get("pageSize")) || 20, 10, 50));
  const query = reportText(url.searchParams.get("q"), 120).toLocaleLowerCase();
  const status = String(url.searchParams.get("status") ?? "active");
  const phase = String(url.searchParams.get("phase") ?? "all");
  const regionCode = String(url.searchParams.get("region") ?? "all");
  const personaCode = String(url.searchParams.get("persona") ?? "all");
  const owner = reportText(url.searchParams.get("owner"), 120).toLocaleLowerCase();
  const due = String(url.searchParams.get("due") ?? "all");
  const allowedStatuses = new Set(["active", "round_active", "review_due", "hold", "scaling", "passed", "voided", "all"]);
  const allowedPhases = new Set(["all", "discovery", "commercial", "pilot"]);
  const where: string[] = [];
  const bindings: Array<string | number> = [];
  const selectedStatus = allowedStatuses.has(status) ? status : "active";
  if (selectedStatus === "active") where.push("p.active = 1 AND p.status != 'voided'");
  else if (selectedStatus !== "all") { where.push("p.status = ?"); bindings.push(selectedStatus); }
  if (allowedPhases.has(phase) && phase !== "all") { where.push("cr.phase = ?"); bindings.push(phase); }
  if (regionCode !== "all") { where.push("p.region_code = ?"); bindings.push(regionCode); }
  if (personaCode !== "all") { where.push("p.persona_code = ?"); bindings.push(personaCode); }
  if (owner) {
    where.push("(lower(p.customer_owner) LIKE ? OR lower(p.supply_owner) LIKE ?)");
    bindings.push(`%${owner}%`, `%${owner}%`);
  }
  const today = nowIso().slice(0, 10);
  if (due === "overdue") { where.push("p.next_review_at != '' AND p.next_review_at < ?"); bindings.push(today); }
  if (due === "next_7_days") {
    const nextWeek = new Date(`${today}T00:00:00.000Z`);
    nextWeek.setUTCDate(nextWeek.getUTCDate() + 7);
    where.push("p.next_review_at >= ? AND p.next_review_at <= ?");
    bindings.push(today, nextWeek.toISOString().slice(0, 10));
  }
  if (due === "unset") where.push("p.next_review_at = ''");
  if (query) {
    const like = `%${query}%`;
    where.push(`(lower(p.title) LIKE ? OR lower(b.name) LIKE ? OR lower(r.name) LIKE ?
      OR lower(p.purchase_scenario) LIKE ? OR lower(p.sales_channel) LIKE ?
      OR EXISTS (SELECT 1 FROM opportunity_rounds qr
        JOIN opportunity_round_families qrf ON qrf.round_id = qr.id
        JOIN product_family_master qf ON qf.code = qrf.product_family_code
        WHERE qr.program_id = p.id AND lower(qf.name) LIKE ?))`);
    bindings.push(like, like, like, like, like, like);
  }
  const fromSql = `FROM opportunity_programs p
    JOIN buyer_persona_categories b ON b.code = p.persona_code
    JOIN trade_regions r ON r.code = p.region_code
    LEFT JOIN opportunity_rounds cr ON cr.program_id = p.id AND cr.round_number = p.current_round_number`;
  const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const db = getRawDb();
  const totalRow = await db.prepare(`SELECT COUNT(*) AS count ${fromSql} ${whereSql}`)
    .bind(...bindings).first<JsonRecord>();
  const total = Number(totalRow?.count ?? 0);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const rows = await db.prepare(`SELECT p.*, b.name AS persona_name, r.name AS region_name,
      cr.id AS current_round_id, cr.phase AS current_phase, cr.status AS current_round_status,
      (SELECT COUNT(*) FROM opportunity_round_families rf WHERE rf.round_id = cr.id) AS family_count,
      (SELECT COUNT(*) FROM opportunity_customer_feedback cf WHERE cf.round_id = cr.id
        AND cf.feedback_status IN ('qualified', 'rfq', 'sample', 'trial')) AS qualified_feedback_count
    ${fromSql} ${whereSql}
    ORDER BY p.updated_at DESC, p.id DESC LIMIT ? OFFSET ?`)
    .bind(...bindings, pageSize, (safePage - 1) * pageSize).all<JsonRecord>();
  return {
    items: rows.results.map((row) => ({
      ...row,
      active: Number(row.active ?? 1) === 1,
      persona_version: Math.max(1, Number(row.persona_version ?? 1)),
      cycle_number: Math.max(1, Number(row.cycle_number ?? 1)),
      max_family_count: Math.max(1, Number(row.max_family_count ?? 5)),
      current_round_number: Math.max(1, Number(row.current_round_number ?? 1)),
      family_count: Number(row.family_count ?? 0),
      qualified_feedback_count: Number(row.qualified_feedback_count ?? 0),
      version: Math.max(1, Number(row.version ?? 1)),
    })),
    page: safePage,
    pageSize,
    total,
    totalPages,
  };
}

async function readOpportunityProgramDetail(programId: string | null) {
  await ensureResearchSchema();
  const id = String(programId ?? "").trim();
  if (!id) throw new Error("缺少验证项目编号");
  const db = getRawDb();
  const [program, rounds, roundFamilies, customerFeedback] = await Promise.all([
    db.prepare(`SELECT p.*, b.name AS persona_name, r.name AS region_name
      FROM opportunity_programs p
      JOIN buyer_persona_categories b ON b.code = p.persona_code
      JOIN trade_regions r ON r.code = p.region_code
      WHERE p.id = ?`).bind(id).first<JsonRecord>(),
    db.prepare("SELECT * FROM opportunity_rounds WHERE program_id = ? ORDER BY round_number DESC")
      .bind(id).all<JsonRecord>(),
    db.prepare(`SELECT rf.*, f.name AS product_family_name, f.track_code, t.name AS track_name
      FROM opportunity_round_families rf
      JOIN opportunity_rounds r ON r.id = rf.round_id
      JOIN product_family_master f ON f.code = rf.product_family_code
      JOIN product_tracks t ON t.code = f.track_code
      WHERE r.program_id = ?
      ORDER BY r.round_number DESC, rf.priority_rank, rf.created_at`).bind(id).all<JsonRecord>(),
    db.prepare("SELECT * FROM opportunity_customer_feedback WHERE program_id = ? ORDER BY created_at DESC")
      .bind(id).all<JsonRecord>(),
  ]);
  if (!program) throw new Error("没有找到验证项目");
  return {
    program: {
      ...program,
      active: Number(program.active ?? 1) === 1,
      persona_version: Math.max(1, Number(program.persona_version ?? 1)),
      cycle_number: Math.max(1, Number(program.cycle_number ?? 1)),
      max_family_count: Math.max(1, Number(program.max_family_count ?? 5)),
      current_round_number: Math.max(1, Number(program.current_round_number ?? 1)),
      version: Math.max(1, Number(program.version ?? 1)),
    },
    rounds: rounds.results.map((row) => ({ ...row, round_number: Math.max(1, Number(row.round_number ?? 1)) })),
    roundFamilies: roundFamilies.results.map((row) => ({
      ...row,
      priority_rank: Number(row.priority_rank ?? 0),
      matrix_score: Number(row.matrix_score ?? 0),
    })),
    customerFeedback: customerFeedback.results,
  };
}

async function createOpportunityProgram(payload: JsonRecord) {
  await ensureResearchSchema();
  const personaCode = taxonomyCode(payload.personaCode, "买家画像");
  const regionCode = taxonomyCode(payload.regionCode, "地区");
  const purchaseScenario = reportText(payload.purchaseScenario, 200);
  const salesChannel = reportText(payload.salesChannel, 160);
  const matrixIds = [...new Set(Array.isArray(payload.matrixIds) ? payload.matrixIds.map((item) => reportText(item, 240)).filter(Boolean) : [])];
  const maxFamilyCount = Math.round(boundedNumber(Number(payload.maxFamilyCount) || 5, 1, 20));
  if (!purchaseScenario || !salesChannel) throw new Error("请填写销售场景和销售渠道");
  if (!matrixIds.length) throw new Error("请至少选择1条关联产品矩阵");
  if (matrixIds.length > maxFamilyCount) throw new Error(`本轮最多选择${maxFamilyCount}条产品矩阵关系`);
  const nextReviewAt = String(payload.nextReviewAt ?? "").trim();
  if (nextReviewAt && !/^\d{4}-\d{2}-\d{2}$/.test(nextReviewAt)) throw new Error("复核日期格式无效");

  const db = getRawDb();
  const [persona, region] = await Promise.all([
    db.prepare("SELECT code, name, version FROM buyer_persona_categories WHERE code = ? AND active = 1").bind(personaCode).first<JsonRecord>(),
    db.prepare("SELECT code, name FROM trade_regions WHERE code = ? AND active = 1").bind(regionCode).first<JsonRecord>(),
  ]);
  if (!persona || !region) throw new Error("请选择有效的画像和地区");
  const projectScopeKey = opportunityProgramScopeKey({ personaCode, regionCode, purchaseScenario, salesChannel });
  const duplicateProgram = await db.prepare(`SELECT id, title, status FROM opportunity_programs
    WHERE project_scope_key = ? AND active = 1 AND status != 'voided' LIMIT 1`)
    .bind(projectScopeKey).first<JsonRecord>();
  if (duplicateProgram) {
    throw new Error(`相同画像、市场、场景和渠道已有活动项目“${String(duplicateProgram.title)}”，请复用该项目并追加产品矩阵`);
  }
  const matrices: JsonRecord[] = [];
  const selectedFamilyCodes = new Set<string>();
  for (const matrixId of matrixIds) {
    const matrix = await db.prepare(`SELECT m.*, f.name AS family_name, f.track_code AS family_track_code, t.name AS track_name
      FROM persona_product_matrix m
      JOIN product_family_master f ON f.code = m.product_family_code
      JOIN product_tracks t ON t.code = f.track_code
      WHERE m.id = ? AND m.persona_code = ? AND m.product_family_code != ''
        AND f.active = 1 AND t.active = 1`).bind(matrixId, personaCode).first<JsonRecord>();
    if (!matrix) throw new Error("所选产品矩阵不存在、已停用或不属于该全球画像");
    if (!["GLOBAL", regionCode].includes(String(matrix.region_code))) throw new Error("所选产品矩阵不适用于当前目标市场");
    const productFamilyCode = String(matrix.product_family_code);
    if (selectedFamilyCodes.has(productFamilyCode)) throw new Error("同一产品家族只能选择一条矩阵关系");
    selectedFamilyCodes.add(productFamilyCode);
    matrices.push(matrix);
  }

  const programId = crypto.randomUUID();
  const roundId = crypto.randomUUID();
  const timestamp = nowIso();
  const origin = opportunityOrigin(payload);
  const title = reportText(payload.title, 180) || `${String(region.name)} · ${String(persona.name)} · ${purchaseScenario}`;
  const roundGoal = reportText(payload.roundGoal, 600) || "用真实客户反馈决定候选产品家族继续、调整或Pass。";
  const statements: D1PreparedStatement[] = [
    db.prepare(`INSERT INTO opportunity_programs
      (id, title, persona_code, persona_version, region_code, purchase_scenario, sales_channel, project_scope_key,
       cycle_number, parent_program_id, hypothesis,
       max_family_count, status, current_round_number, customer_owner, supply_owner,
       next_review_at, next_action, active, version, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, '', ?, ?, 'round_active', 1, ?, ?, ?, ?, 1, 1, ?, ?, ?)`)
      .bind(programId, title, personaCode, Math.max(1, Number(persona.version ?? 1)), regionCode, purchaseScenario, salesChannel,
        projectScopeKey, reportText(payload.hypothesis, 2000), maxFamilyCount, reportText(payload.customerOwner, 120),
        reportText(payload.supplyOwner, 120), nextReviewAt,
        reportText(payload.nextAction, 500) || "核实第一批目标客户并记录有效反馈", origin, timestamp, timestamp),
    db.prepare(`INSERT INTO opportunity_rounds
      (id, program_id, round_number, phase, status, goal, decision, decision_note, due_at,
       started_at, completed_at, created_by, created_at)
      VALUES (?, ?, 1, 'discovery', 'active', ?, '', '', ?, ?, NULL, ?, ?)`)
      .bind(roundId, programId, roundGoal, nextReviewAt, timestamp, origin, timestamp),
  ];

  for (const [index, matrix] of matrices.entries()) {
    const productFamilyCode = String(matrix.product_family_code);
    const dossier = opportunityDossierIdentity(regionCode, productFamilyCode);
    const fingerprint = `${programId}:${opportunityFingerprint({ personaCode, regionCode, productFamilyCode, purchaseScenario, salesChannel })}`;
    const opportunityId = crypto.randomUUID();
    statements.push(db.prepare(`INSERT INTO opportunity_dossiers
      (id, scope_key, region_code, track_code, product_family_code, status, version, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, 'active', 1, ?, ?)
      ON CONFLICT(scope_key) DO UPDATE SET status = 'active', updated_at = excluded.updated_at`)
      .bind(dossier.id, dossier.scopeKey, regionCode, String(matrix.family_track_code), productFamilyCode, timestamp, timestamp));
    statements.push(db.prepare(`INSERT INTO opportunity_cases
      (id, fingerprint, dossier_id, title, persona_code, region_code, track_code, product_family_code,
       purchase_scenario, sales_channel, hypothesis, status, owner_name, next_review_at,
       next_action, active, version, created_by, created_at, updated_at, program_id)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'hypothesis', ?, ?, ?, 1, 1, ?, ?, ?, ?)`)
      .bind(opportunityId, fingerprint, dossier.id, `${String(region.name)} · ${String(persona.name)} · ${String(matrix.family_name)}`,
        personaCode, regionCode, String(matrix.family_track_code), productFamilyCode, purchaseScenario, salesChannel,
        reportText(payload.hypothesis, 2000), reportText(payload.customerOwner, 120), nextReviewAt,
        "补充公开证据并核实第一批目标客户", origin, timestamp, timestamp, programId));
    statements.push(db.prepare(`INSERT INTO opportunity_round_families
      (id, round_id, opportunity_id, matrix_id, matrix_role, matrix_score, matrix_evidence_status,
       matrix_rationale, product_family_code, priority_rank, status, rationale, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', '', ?, ?)`)
      .bind(crypto.randomUUID(), roundId, opportunityId, String(matrix.id), String(matrix.family_role ?? "test"),
        Math.round(boundedNumber(matrix.relevance_score, 0, 100)), String(matrix.evidence_status ?? "hypothesis"),
        String(matrix.rationale ?? ""), productFamilyCode, index + 1, timestamp, timestamp));
  }
  await db.batch(statements);
  return readOpportunityCenter();
}

async function addOpportunityProgramMatrices(payload: JsonRecord) {
  await ensureResearchSchema();
  const programId = String(payload.programId ?? "").trim();
  const matrixIds = [...new Set(Array.isArray(payload.matrixIds) ? payload.matrixIds.map((item) => reportText(item, 240)).filter(Boolean) : [])];
  if (!programId || !matrixIds.length) throw new Error("请选择需要复用到已有项目的产品矩阵");
  const db = getRawDb();
  const program = await db.prepare(`SELECT p.*, b.name AS persona_name, r.name AS region_name
    FROM opportunity_programs p
    JOIN buyer_persona_categories b ON b.code = p.persona_code
    JOIN trade_regions r ON r.code = p.region_code
    WHERE p.id = ?`).bind(programId).first<JsonRecord>();
  if (!program || Number(program.active ?? 0) !== 1 || !["round_active", "review_due", "hold"].includes(String(program.status))) {
    throw new Error("只有正在验证或暂停的项目可以追加产品矩阵");
  }
  const round = await db.prepare(`SELECT * FROM opportunity_rounds
    WHERE program_id = ? AND round_number = ?`).bind(programId, Number(program.current_round_number)).first<JsonRecord>();
  if (!round || !["active", "hold"].includes(String(round.status))) throw new Error("当前轮次不可追加产品矩阵");
  const currentFamilies = await db.prepare("SELECT product_family_code FROM opportunity_round_families WHERE round_id = ?")
    .bind(String(round.id)).all<JsonRecord>();
  const existingCodes = new Set(currentFamilies.results.map((item) => String(item.product_family_code)));
  const availableSlots = Number(program.max_family_count ?? 5) - existingCodes.size;
  if (availableSlots <= 0) throw new Error("当前轮次已达到产品矩阵上限");
  const timestamp = nowIso();
  const origin = opportunityOrigin(payload);
  const statements: D1PreparedStatement[] = [];
  let added = 0;
  for (const matrixId of matrixIds) {
    const matrix = await db.prepare(`SELECT m.*, f.name AS family_name, f.track_code AS family_track_code
      FROM persona_product_matrix m
      JOIN product_family_master f ON f.code = m.product_family_code
      JOIN product_tracks t ON t.code = f.track_code
      WHERE m.id = ? AND m.persona_code = ? AND m.product_family_code != ''
        AND f.active = 1 AND t.active = 1`).bind(matrixId, String(program.persona_code)).first<JsonRecord>();
    if (!matrix) throw new Error("所选产品矩阵不存在、已停用或不属于该全球画像");
    if (!["GLOBAL", String(program.region_code)].includes(String(matrix.region_code))) throw new Error("所选产品矩阵不适用于当前目标市场");
    const productFamilyCode = String(matrix.product_family_code);
    if (existingCodes.has(productFamilyCode)) continue;
    if (added >= availableSlots) throw new Error(`当前轮次最多还能添加${availableSlots}个产品家族`);
    existingCodes.add(productFamilyCode);
    added += 1;
    const dossier = opportunityDossierIdentity(String(program.region_code), productFamilyCode);
    statements.push(db.prepare(`INSERT INTO opportunity_dossiers
      (id, scope_key, region_code, track_code, product_family_code, status, version, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, 'active', 1, ?, ?)
      ON CONFLICT(scope_key) DO UPDATE SET status = 'active', updated_at = excluded.updated_at`)
      .bind(dossier.id, dossier.scopeKey, String(program.region_code), String(matrix.family_track_code), productFamilyCode, timestamp, timestamp));
    const existingCase = await db.prepare(`SELECT id FROM opportunity_cases
      WHERE program_id = ? AND product_family_code = ?`).bind(programId, productFamilyCode).first<JsonRecord>();
    const opportunityId = existingCase ? String(existingCase.id) : crypto.randomUUID();
    if (existingCase) {
      statements.push(db.prepare(`UPDATE opportunity_cases SET dossier_id = ?, active = 1, status = 'hypothesis',
        next_action = '补充公开证据并核实第一批目标客户', updated_at = ?, version = version + 1 WHERE id = ?`)
        .bind(dossier.id, timestamp, opportunityId));
    } else {
      const fingerprint = `${programId}:${opportunityFingerprint({
        personaCode: String(program.persona_code), regionCode: String(program.region_code), productFamilyCode,
        purchaseScenario: String(program.purchase_scenario), salesChannel: String(program.sales_channel),
      })}`;
      statements.push(db.prepare(`INSERT INTO opportunity_cases
        (id, fingerprint, dossier_id, title, persona_code, region_code, track_code, product_family_code,
         purchase_scenario, sales_channel, hypothesis, status, owner_name, next_review_at,
         next_action, active, version, created_by, created_at, updated_at, program_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'hypothesis', ?, ?, ?, 1, 1, ?, ?, ?, ?)`)
        .bind(opportunityId, fingerprint, dossier.id,
          `${String(program.region_name)} · ${String(program.persona_name)} · ${String(matrix.family_name)}`,
          String(program.persona_code), String(program.region_code), String(matrix.family_track_code), productFamilyCode,
          String(program.purchase_scenario), String(program.sales_channel), String(program.hypothesis ?? ""),
          String(program.customer_owner ?? ""), String(program.next_review_at ?? ""),
          "补充公开证据并核实第一批目标客户", origin, timestamp, timestamp, programId));
    }
    statements.push(db.prepare(`INSERT INTO opportunity_round_families
      (id, round_id, opportunity_id, matrix_id, matrix_role, matrix_score, matrix_evidence_status,
       matrix_rationale, product_family_code, priority_rank, status, rationale, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', '', ?, ?)`)
      .bind(crypto.randomUUID(), String(round.id), opportunityId, String(matrix.id), String(matrix.family_role ?? "test"),
        Math.round(boundedNumber(matrix.relevance_score, 0, 100)), String(matrix.evidence_status ?? "hypothesis"),
        String(matrix.rationale ?? ""), productFamilyCode, existingCodes.size, timestamp, timestamp));
  }
  if (!added) throw new Error("所选产品矩阵已经全部存在于该项目当前轮次");
  statements.push(db.prepare(`UPDATE opportunity_programs SET updated_at = ?, version = version + 1,
    next_action = CASE WHEN next_action = '' THEN '核实第一批目标客户并记录有效反馈' ELSE next_action END WHERE id = ?`)
    .bind(timestamp, programId));
  await db.batch(statements);
  return readOpportunityCenter();
}

async function voidOpportunityProgram(payload: JsonRecord) {
  await ensureResearchSchema();
  const programId = String(payload.programId ?? "").trim();
  const reasonCode = String(payload.reasonCode ?? "");
  const reasonNote = reportText(payload.reasonNote, 1200);
  const replacedByProgramId = String(payload.replacedByProgramId ?? "").trim();
  if (!OPPORTUNITY_VOID_REASONS.has(reasonCode)) throw new Error("请选择有效的作废原因");
  if (["duplicate", "merged"].includes(reasonCode) && !replacedByProgramId) throw new Error("重复或合并项目必须选择替代项目");
  if (reasonCode === "other" && !reasonNote) throw new Error("请填写作废说明");
  const db = getRawDb();
  const program = await db.prepare("SELECT * FROM opportunity_programs WHERE id = ?").bind(programId).first<JsonRecord>();
  if (!program) throw new Error("没有找到验证项目");
  if (String(program.status) === "voided") throw new Error("该项目已经作废");
  if (payload.version !== undefined && Number(payload.version) !== Number(program.version)) throw new Error("项目已被其他操作更新，请刷新后重试");
  if (replacedByProgramId) {
    if (replacedByProgramId === programId) throw new Error("替代项目不能是当前项目");
    const replacement = await db.prepare("SELECT id FROM opportunity_programs WHERE id = ? AND status != 'voided'")
      .bind(replacedByProgramId).first<JsonRecord>();
    if (!replacement) throw new Error("替代项目不存在或已经作废");
  }
  const timestamp = nowIso();
  const origin = opportunityOrigin(payload);
  await db.batch([
    db.prepare(`UPDATE opportunity_programs SET status = 'voided', active = 0, next_action = '',
      void_reason_code = ?, void_reason_note = ?, voided_at = ?, voided_by = ?, replaced_by_program_id = ?,
      version = version + 1, updated_at = ? WHERE id = ?`)
      .bind(reasonCode, reasonNote, timestamp, origin, replacedByProgramId, timestamp, programId),
    db.prepare(`UPDATE opportunity_rounds SET status = 'voided', decision = 'void', decision_note = ?, completed_at = ?
      WHERE program_id = ? AND status IN ('active', 'hold')`).bind(reasonNote || reasonCode, timestamp, programId),
    db.prepare("UPDATE opportunity_cases SET status = 'archived', active = 0, updated_at = ? WHERE program_id = ?")
      .bind(timestamp, programId),
    db.prepare(`UPDATE trade_data_refresh_requests SET status = 'failed', error = 'parent_project_voided', completed_at = ?
      WHERE status = 'pending' AND opportunity_id IN (SELECT id FROM opportunity_cases WHERE program_id = ?)`)
      .bind(timestamp, programId),
    db.prepare(`UPDATE opportunity_validation_requests SET status = 'failed', error = 'parent_project_voided', completed_at = ?
      WHERE status = 'pending' AND opportunity_id IN (SELECT id FROM opportunity_cases WHERE program_id = ?)`)
      .bind(timestamp, programId),
  ]);
  return readOpportunityCenter();
}

async function updateOpportunityProgramSettings(payload: JsonRecord) {
  await ensureResearchSchema();
  const programId = String(payload.programId ?? "").trim();
  const maxFamilyCount = Math.round(boundedNumber(Number(payload.maxFamilyCount) || 5, 1, 20));
  const db = getRawDb();
  const program = await db.prepare("SELECT * FROM opportunity_programs WHERE id = ?").bind(programId).first<JsonRecord>();
  if (!program) throw new Error("没有找到验证项目");
  if (String(program.status) === "voided" || Number(program.active ?? 0) !== 1) throw new Error("已作废或归档的项目不能修改设置");
  const round = await db.prepare("SELECT id FROM opportunity_rounds WHERE program_id = ? AND round_number = ?")
    .bind(programId, Number(program.current_round_number)).first<JsonRecord>();
  const familyCount = round ? await db.prepare("SELECT COUNT(*) AS count FROM opportunity_round_families WHERE round_id = ?")
    .bind(String(round.id)).first<JsonRecord>() : null;
  if (Number(familyCount?.count ?? 0) > maxFamilyCount) throw new Error("当前轮次的产品家族数量已经超过新的上限");
  const nextReviewAt = String(payload.nextReviewAt ?? program.next_review_at ?? "").trim();
  if (nextReviewAt && !/^\d{4}-\d{2}-\d{2}$/.test(nextReviewAt)) throw new Error("复核日期格式无效");
  await db.prepare(`UPDATE opportunity_programs SET title = ?, max_family_count = ?, customer_owner = ?, supply_owner = ?,
    next_review_at = ?, next_action = ?, version = version + 1, updated_at = ? WHERE id = ?`)
    .bind(reportText(payload.title, 180) || String(program.title), maxFamilyCount,
      reportText(payload.customerOwner, 120), reportText(payload.supplyOwner, 120), nextReviewAt,
      reportText(payload.nextAction, 500), nowIso(), programId).run();
  return readOpportunityCenter();
}

async function updateOpportunityRoundFamily(payload: JsonRecord) {
  await ensureResearchSchema();
  const familyId = String(payload.familyId ?? "").trim();
  const status = String(payload.status ?? "candidate");
  if (!OPPORTUNITY_FAMILY_STATUSES.has(status)) throw new Error("产品家族状态无效");
  const db = getRawDb();
  const family = await db.prepare(`SELECT rf.id, r.status AS round_status, r.program_id
    FROM opportunity_round_families rf JOIN opportunity_rounds r ON r.id = rf.round_id WHERE rf.id = ?`)
    .bind(familyId).first<JsonRecord>();
  if (!family) throw new Error("没有找到本轮产品家族");
  if (!["active", "hold"].includes(String(family.round_status))) throw new Error("已结束的轮次不能修改产品家族结论");
  const timestamp = nowIso();
  await db.batch([
    db.prepare("UPDATE opportunity_round_families SET status = ?, rationale = ?, updated_at = ? WHERE id = ?")
      .bind(status, reportText(payload.rationale, 1000), timestamp, familyId),
    db.prepare("UPDATE opportunity_programs SET updated_at = ?, version = version + 1 WHERE id = ?")
      .bind(timestamp, String(family.program_id)),
  ]);
  return readOpportunityCenter();
}

async function addOpportunityCustomerFeedback(payload: JsonRecord) {
  await ensureResearchSchema();
  const programId = String(payload.programId ?? "").trim();
  const roundId = String(payload.roundId ?? "").trim();
  const productFamilyCode = taxonomyCode(payload.productFamilyCode, "产品家族");
  const companyName = reportText(payload.companyName, 200);
  const feedbackStatus = String(payload.feedbackStatus ?? "contacted");
  if (!companyName || !OPPORTUNITY_FEEDBACK_STATUSES.has(feedbackStatus)) throw new Error("请填写客户公司并选择有效状态");
  const db = getRawDb();
  const roundFamily = await db.prepare(`SELECT rf.opportunity_id, r.status AS round_status
    FROM opportunity_round_families rf JOIN opportunity_rounds r ON r.id = rf.round_id
    WHERE rf.round_id = ? AND r.program_id = ? AND rf.product_family_code = ?`)
    .bind(roundId, programId, productFamilyCode).first<JsonRecord>();
  if (!roundFamily) throw new Error("该产品家族不在当前验证轮次中");
  if (!["active", "hold"].includes(String(roundFamily.round_status))) throw new Error("已结束的轮次不能新增客户反馈");
  const sourceInput = String(payload.sourceUrl ?? "").trim();
  const sourceUrl = sourceInput ? safeImageUrl(sourceInput) : "";
  if (sourceInput && !sourceUrl) throw new Error("来源链接必须是有效的 http 或 https 地址");
  const origin = opportunityOrigin(payload);
  const timestamp = nowIso();
  const feedbackId = crypto.randomUUID();
  const statements: D1PreparedStatement[] = [
    db.prepare(`INSERT INTO opportunity_customer_feedback
      (id, program_id, round_id, product_family_code, company_name, contact_role, feedback_status,
       scenario, current_solution, pain_points, must_have_specs, buying_trigger, purchase_cycle,
       price_behavior, rejection_reason, source_url, note, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(feedbackId, programId, roundId, productFamilyCode, companyName, reportText(payload.contactRole, 160),
        feedbackStatus, reportText(payload.scenario, 600), reportText(payload.currentSolution, 600),
        reportText(payload.painPoints, 1200), reportText(payload.mustHaveSpecs, 1200),
        reportText(payload.buyingTrigger, 600), reportText(payload.purchaseCycle, 300),
        reportText(payload.priceBehavior, 600), reportText(payload.rejectionReason, 600), sourceUrl,
        reportText(payload.note, 2000), origin, timestamp, timestamp),
    db.prepare("UPDATE opportunity_programs SET updated_at = ?, version = version + 1 WHERE id = ?").bind(timestamp, programId),
    db.prepare("UPDATE opportunity_cases SET updated_at = ? WHERE id = ?").bind(timestamp, String(roundFamily.opportunity_id)),
  ];
  if (["qualified", "rfq", "sample", "trial"].includes(feedbackStatus)) {
    const evidenceType = feedbackStatus === "qualified" ? "buyer_discovery" : "buyer";
    const metricKey = feedbackStatus === "qualified" ? "qualified_discovery_count"
      : feedbackStatus === "rfq" ? "rfq_count" : feedbackStatus === "sample" ? "sample_request_count" : "trial_order_count";
    const note = [
      reportText(payload.scenario, 600) && `场景：${reportText(payload.scenario, 600)}`,
      reportText(payload.painPoints, 1200) && `痛点：${reportText(payload.painPoints, 1200)}`,
      reportText(payload.mustHaveSpecs, 1200) && `必要规格：${reportText(payload.mustHaveSpecs, 1200)}`,
      reportText(payload.note, 2000),
    ].filter(Boolean).join("\n");
    statements.push(db.prepare(`INSERT INTO opportunity_evidence
      (id, opportunity_id, evidence_type, source_grade, title, source_url, note, market_code,
       period, metrics, evidence_status, captured_at, created_by, created_at)
      VALUES (?, ?, ?, 'verified_buyer', ?, ?, ?, '', '', ?, 'available', ?, ?, ?)`)
      .bind(crypto.randomUUID(), String(roundFamily.opportunity_id), evidenceType,
        `${companyName} · ${feedbackStatus}`, sourceUrl, note, JSON.stringify({ [metricKey]: 1, feedback_id: feedbackId }),
        timestamp, origin, timestamp));
  }
  await db.batch(statements);
  return readOpportunityCenter();
}

async function decideOpportunityRound(payload: JsonRecord) {
  await ensureResearchSchema();
  const programId = String(payload.programId ?? "").trim();
  const decision = String(payload.decision ?? "");
  if (!OPPORTUNITY_ROUND_DECISIONS.has(decision)) throw new Error("请选择有效的本轮决策");
  const note = reportText(payload.note, 2000);
  if (decision === "pass" && !note) throw new Error("Pass前请记录原因，方便后续复用经验");
  if (decision === "continue" && payload.confirmedByBoth !== true) throw new Error("进入下一阶段前需要两位负责人共同确认");
  const db = getRawDb();
  const program = await db.prepare("SELECT * FROM opportunity_programs WHERE id = ?").bind(programId).first<JsonRecord>();
  if (!program) throw new Error("没有找到验证项目");
  const round = await db.prepare("SELECT * FROM opportunity_rounds WHERE program_id = ? AND round_number = ?")
    .bind(programId, Number(program.current_round_number)).first<JsonRecord>();
  if (!round) throw new Error("没有找到当前验证轮次");
  if (!["active", "hold"].includes(String(round.status))) throw new Error("当前轮次已经结束");
  const dueAt = String(payload.dueAt ?? program.next_review_at ?? "").trim();
  if (dueAt && !/^\d{4}-\d{2}-\d{2}$/.test(dueAt)) throw new Error("复核日期格式无效");
  const timestamp = nowIso();

  if (decision === "extend") {
    await db.batch([
      db.prepare("UPDATE opportunity_rounds SET goal = ?, decision_note = ?, due_at = ?, status = 'active' WHERE id = ?")
        .bind(reportText(payload.nextGoal, 600) || String(round.goal), note, dueAt, String(round.id)),
      db.prepare("UPDATE opportunity_programs SET status = 'round_active', next_review_at = ?, next_action = ?, version = version + 1, updated_at = ? WHERE id = ?")
        .bind(dueAt, reportText(payload.nextAction, 500) || "补足本轮最低验证动作", timestamp, programId),
    ]);
    return readOpportunityCenter();
  }
  if (decision === "hold") {
    await db.batch([
      db.prepare("UPDATE opportunity_rounds SET decision = 'hold', decision_note = ?, due_at = ?, status = 'hold' WHERE id = ?")
        .bind(note, dueAt, String(round.id)),
      db.prepare("UPDATE opportunity_programs SET status = 'hold', next_review_at = ?, next_action = ?, version = version + 1, updated_at = ? WHERE id = ?")
        .bind(dueAt, reportText(payload.nextAction, 500) || "到期后复核", timestamp, programId),
    ]);
    return readOpportunityCenter();
  }
  if (decision === "pass") {
    await db.batch([
      db.prepare("UPDATE opportunity_rounds SET decision = 'pass', decision_note = ?, status = 'completed', completed_at = ? WHERE id = ?")
        .bind(note, timestamp, String(round.id)),
      db.prepare("UPDATE opportunity_programs SET status = 'passed', active = 0, next_action = '', version = version + 1, updated_at = ? WHERE id = ?")
        .bind(timestamp, programId),
      db.prepare("UPDATE opportunity_cases SET status = 'archived', active = 0, updated_at = ? WHERE program_id = ?")
        .bind(timestamp, programId),
    ]);
    return readOpportunityCenter();
  }

  const selectedFamilyCodes = [...new Set(Array.isArray(payload.familyCodes) ? payload.familyCodes.map((item) => String(item).trim()).filter(Boolean) : [])];
  if (!selectedFamilyCodes.length) throw new Error("请选择进入下一轮的产品家族");
  if (selectedFamilyCodes.length > Number(program.max_family_count ?? 5)) throw new Error(`下一轮最多选择${Number(program.max_family_count ?? 5)}个产品家族`);
  const currentFamilies = await db.prepare("SELECT * FROM opportunity_round_families WHERE round_id = ? ORDER BY priority_rank")
    .bind(String(round.id)).all<JsonRecord>();
  const currentByCode = new Map(currentFamilies.results.map((item) => [String(item.product_family_code), item]));
  if (selectedFamilyCodes.some((code) => !currentByCode.has(code))) throw new Error("下一轮只能继承本轮已有产品家族");
  const phase = String(round.phase);
  if (!OPPORTUNITY_ROUND_PHASES.has(phase)) throw new Error("当前轮次阶段无效");
  const nextPhase = decision === "adjust" ? phase : phase === "discovery" ? "commercial" : phase === "commercial" ? "pilot" : "scaling";
  const statements: D1PreparedStatement[] = [];
  for (const family of currentFamilies.results) {
    const selected = selectedFamilyCodes.includes(String(family.product_family_code));
    statements.push(db.prepare("UPDATE opportunity_round_families SET status = ?, updated_at = ? WHERE id = ?")
      .bind(selected ? decision : "pass", timestamp, String(family.id)));
    if (!selected) {
      statements.push(db.prepare("UPDATE opportunity_cases SET status = 'archived', active = 0, updated_at = ? WHERE id = ?")
        .bind(timestamp, String(family.opportunity_id)));
    }
  }
  statements.push(db.prepare("UPDATE opportunity_rounds SET decision = ?, decision_note = ?, status = 'completed', completed_at = ? WHERE id = ?")
    .bind(decision, note, timestamp, String(round.id)));
  if (nextPhase === "scaling") {
    statements.push(db.prepare("UPDATE opportunity_programs SET status = 'scaling', next_action = ?, version = version + 1, updated_at = ? WHERE id = ?")
      .bind(reportText(payload.nextAction, 500) || "转入常态客户开发与订单复盘", timestamp, programId));
    await db.batch(statements);
    return readOpportunityCenter();
  }

  const nextRoundNumber = Number(round.round_number) + 1;
  const nextRoundId = crypto.randomUUID();
  const defaultGoal = nextPhase === "commercial"
    ? "形成产品报价矩阵，验证供应、落地成本、合规和真实RFQ。"
    : nextPhase === "pilot"
      ? "用受控样品或首单验证质量、交期、实际毛利和回款。"
      : "根据反馈修正假设并完成下一轮验证。";
  statements.push(db.prepare(`INSERT INTO opportunity_rounds
    (id, program_id, round_number, phase, status, goal, decision, decision_note, due_at,
     started_at, completed_at, created_by, created_at)
    VALUES (?, ?, ?, ?, 'active', ?, '', '', ?, ?, NULL, ?, ?)`)
    .bind(nextRoundId, programId, nextRoundNumber, nextPhase, reportText(payload.nextGoal, 600) || defaultGoal,
      dueAt, timestamp, opportunityOrigin(payload), timestamp));
  selectedFamilyCodes.forEach((code, index) => {
    const previous = currentByCode.get(code)!;
    statements.push(db.prepare(`INSERT INTO opportunity_round_families
      (id, round_id, opportunity_id, matrix_id, matrix_role, matrix_score, matrix_evidence_status,
       matrix_rationale, product_family_code, priority_rank, status, rationale, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', '', ?, ?)`)
      .bind(crypto.randomUUID(), nextRoundId, String(previous.opportunity_id), String(previous.matrix_id),
        String(previous.matrix_role), Number(previous.matrix_score), String(previous.matrix_evidence_status),
        String(previous.matrix_rationale), code, index + 1, timestamp, timestamp));
  });
  statements.push(db.prepare(`UPDATE opportunity_programs SET status = 'round_active', current_round_number = ?,
    next_review_at = ?, next_action = ?, version = version + 1, updated_at = ? WHERE id = ?`)
    .bind(nextRoundNumber, dueAt, reportText(payload.nextAction, 500) || defaultGoal, timestamp, programId));
  await db.batch(statements);
  return readOpportunityCenter();
}

async function addOpportunityEvidence(payload: JsonRecord) {
  await ensureResearchSchema();
  const opportunityId = String(payload.opportunityId ?? "").trim();
  const evidenceType = String(payload.evidenceType ?? "");
  const sourceGrade = String(payload.sourceGrade ?? "other") as OpportunityEvidenceGrade;
  const origin = opportunityOrigin(payload);
  const title = reportText(payload.title, 240);
  if (!OPPORTUNITY_EVIDENCE_TYPES.has(evidenceType) || !OPPORTUNITY_EVIDENCE_GRADES.has(sourceGrade) || !title) {
    throw new Error("请完整填写证据类型、来源等级和标题");
  }
  const db = getRawDb();
  const opportunity = await db.prepare("SELECT id, dossier_id FROM opportunity_cases WHERE id = ? AND active = 1").bind(opportunityId).first<JsonRecord>();
  if (!opportunity) throw new Error("没有找到可维护的商机");
  const sourceInput = String(payload.sourceUrl ?? "").trim();
  const sourceUrl = sourceInput ? safeImageUrl(sourceInput) : "";
  if (sourceInput && !sourceUrl) throw new Error("证据链接必须是有效的 http 或 https 地址");
  if (sourceGrade !== "internal_odoo" && !sourceUrl) throw new Error("外部证据必须提供可核验来源链接");
  const capturedAt = String(payload.capturedAt ?? "").trim() || nowIso();
  const timestamp = nowIso();
  const evidenceScope = opportunityEvidenceScope(evidenceType);
  const dossierId = evidenceScope === "shared" ? String(opportunity.dossier_id ?? "") : "";
  if (evidenceScope === "shared" && dossierId) {
    const duplicate = await db.prepare(`SELECT id FROM opportunity_evidence
      WHERE dossier_id = ? AND evidence_scope = 'shared' AND evidence_type = ? AND source_url = ? AND title = ? LIMIT 1`)
      .bind(dossierId, evidenceType, sourceUrl, title).first<JsonRecord>();
    if (duplicate) throw new Error("该共享档案已经存在相同来源和标题的证据");
  }
  await db.batch([
    db.prepare(`INSERT INTO opportunity_evidence
      (id, opportunity_id, dossier_id, evidence_scope, evidence_type, source_grade, title, source_url, note, market_code,
       period, metrics, evidence_status, captured_at, created_by, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(crypto.randomUUID(), opportunityId, dossierId, evidenceScope, evidenceType, sourceGrade, title, sourceUrl,
        reportText(payload.note, 2000), reportText(payload.marketCode, 20).toUpperCase(),
        reportText(payload.period, 40), JSON.stringify(asObject(payload.metrics)),
        ["available", "missing", "blocked"].includes(String(payload.evidenceStatus)) ? String(payload.evidenceStatus) : "available",
        capturedAt, origin, timestamp),
    db.prepare("UPDATE opportunity_cases SET updated_at = ? WHERE id = ?").bind(timestamp, opportunityId),
  ]);
  return readOpportunityCenter();
}

async function addOpportunityAssessment(payload: JsonRecord) {
  await ensureResearchSchema();
  const opportunityId = String(payload.opportunityId ?? "").trim();
  const origin = opportunityOrigin(payload);
  const signals = normalizeOpportunitySignals(payload.signals);
  if (!OPPORTUNITY_SIGNAL_FIELDS.some((field) => signals[field] !== null)) throw new Error("请至少填写一项验证指标");
  const db = getRawDb();
  const opportunity = await db.prepare("SELECT id, dossier_id FROM opportunity_cases WHERE id = ? AND active = 1").bind(opportunityId).first<JsonRecord>();
  if (!opportunity) throw new Error("没有找到可维护的商机");
  const evidenceRows = await db.prepare(`SELECT source_grade FROM opportunity_evidence
    WHERE evidence_status = 'available' AND (opportunity_id = ? OR (dossier_id = ? AND evidence_scope = 'shared'))`)
    .bind(opportunityId, String(opportunity.dossier_id ?? "")).all<JsonRecord>();
  const grades = evidenceRows.results.map((row) => String(row.source_grade)).filter((grade): grade is OpportunityEvidenceGrade => OPPORTUNITY_EVIDENCE_GRADES.has(grade as OpportunityEvidenceGrade));
  const scores = computeOpportunityScores(signals, grades);
  const timestamp = nowIso();
  await db.batch([
    db.prepare(`INSERT INTO opportunity_assessments
      (id, opportunity_id, signals, scores, rationale, created_by, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)`)
      .bind(crypto.randomUUID(), opportunityId, JSON.stringify(signals), JSON.stringify(scores), reportText(payload.rationale, 2000), origin, timestamp),
    db.prepare("UPDATE opportunity_cases SET updated_at = ?, version = version + 1 WHERE id = ?").bind(timestamp, opportunityId),
  ]);
  return readOpportunityCenter();
}

async function readTradeDataCache(opportunityId: string | null) {
  await ensureResearchSchema();
  const id = String(opportunityId ?? "").trim();
  if (!id) throw new Error("缺少商机编号");
  const db = getRawDb();
  const opportunity = await db.prepare(`SELECT c.*, p.name AS persona_name, r.name AS region_name, r.countries,
      f.name AS product_family_name, f.keywords, t.name AS track_name
      FROM opportunity_cases c
      JOIN buyer_persona_categories p ON p.code = c.persona_code
      JOIN trade_regions r ON r.code = c.region_code
      JOIN product_family_master f ON f.code = c.product_family_code
      JOIN product_tracks t ON t.code = c.track_code
      WHERE c.id = ?`).bind(id).first<JsonRecord>();
  if (!opportunity) throw new Error("没有找到该商机");
  const [observations, requests] = await Promise.all([
    db.prepare(`SELECT * FROM trade_data_observations
      WHERE product_family_code = ? AND (region_code = ? OR region_code = 'GLOBAL')
      ORDER BY collected_at DESC, period DESC LIMIT 5000`)
      .bind(opportunity.product_family_code, opportunity.region_code).all<JsonRecord>(),
    db.prepare("SELECT * FROM trade_data_refresh_requests WHERE opportunity_id = ? ORDER BY created_at DESC LIMIT 100")
      .bind(id).all<JsonRecord>(),
  ]);
  const latestCollectedAt = observations.results.find((row) => String(row.data_status) === "available")?.collected_at;
  return {
    opportunity: {
      id: String(opportunity.id), personaCode: String(opportunity.persona_code), personaName: String(opportunity.persona_name),
      status: String(opportunity.status), active: Number(opportunity.active ?? 0) === 1,
      regionCode: String(opportunity.region_code), regionName: String(opportunity.region_name), countries: jsonArray(opportunity.countries),
      trackCode: String(opportunity.track_code), trackName: String(opportunity.track_name),
      productFamilyCode: String(opportunity.product_family_code), productFamilyName: String(opportunity.product_family_name),
      keywords: jsonArray(opportunity.keywords), purchaseScenario: String(opportunity.purchase_scenario), salesChannel: String(opportunity.sales_channel),
    },
    observations: observations.results.map((row) => ({ ...row, period: String(row.period), value: row.value === null ? null : Number(row.value) })),
    requests: requests.results.map((row) => ({ ...row, force_refresh: Number(row.force_refresh ?? 0) === 1 })),
    cache: {
      availableCount: observations.results.filter((row) => String(row.data_status) === "available").length,
      latestCollectedAt: latestCollectedAt ? String(latestCollectedAt) : null,
      fresh: isTradeCacheFresh(latestCollectedAt ? String(latestCollectedAt) : null),
      coverageLevel: tradeCoverageLevel(observations.results),
      policy: "local_first_120_days",
    },
  };
}

async function createTradeDataRequest(payload: JsonRecord) {
  await ensureResearchSchema();
  const opportunityId = String(payload.opportunityId ?? "").trim();
  const forceRefresh = payload.forceRefresh === true;
  const cache = await readTradeDataCache(opportunityId);
  if (!cache.opportunity.active) throw new Error("已归档商机不能启动贸易数据补采");
  const collectionLevel = normalizeTradeCollectionLevel(payload.collectionLevel
    ?? tradeCollectionLevelForOpportunityStatus(cache.opportunity.status));
  const triggerReason = reportText(payload.triggerReason, 80) || "manual";
  if (cache.cache.fresh && tradeCoverageSatisfies(cache.cache.coverageLevel, collectionLevel) && !forceRefresh) {
    return { reuseLocal: true, collectionLevel, cache };
  }
  const existingPending = await getRawDb().prepare("SELECT id, collection_level, created_at FROM trade_data_refresh_requests WHERE opportunity_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1")
    .bind(opportunityId).first<JsonRecord>();
  if (existingPending) {
    return { reuseLocal: false, pending: true, runId: String(existingPending.id), collectionLevel: String(existingPending.collection_level), createdAt: String(existingPending.created_at) };
  }
  if (triggerReason === "manual" && payload.confirmed !== true) {
    throw new Error("请先确认补采范围后再启动贸易数据任务");
  }
  const runId = crypto.randomUUID();
  const timestamp = nowIso();
  await getRawDb().prepare(`INSERT INTO trade_data_refresh_requests
    (id, opportunity_id, product_family_code, region_code, status, force_refresh, collection_level, trigger_reason, request_note, requested_by, created_at)
    VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)`)
    .bind(runId, opportunityId, cache.opportunity.productFamilyCode, cache.opportunity.regionCode, forceRefresh ? 1 : 0,
      collectionLevel, triggerReason, reportText(payload.requestNote, 1000), opportunityOrigin(payload), timestamp).run();
  return {
    reuseLocal: false,
    request: {
      runId,
      opportunityId,
      personaCode: cache.opportunity.personaCode,
      personaName: cache.opportunity.personaName,
      regionCode: cache.opportunity.regionCode,
      regionName: cache.opportunity.regionName,
      countries: cache.opportunity.countries,
      trackCode: cache.opportunity.trackCode,
      trackName: cache.opportunity.trackName,
      productFamilyCode: cache.opportunity.productFamilyCode,
      productFamilyName: cache.opportunity.productFamilyName,
      keywords: cache.opportunity.keywords,
      purchaseScenario: cache.opportunity.purchaseScenario,
      salesChannel: cache.opportunity.salesChannel,
      collectionLevel,
      collectionPolicy: TRADE_COLLECTION_POLICIES[collectionLevel],
      triggerReason,
      existingPeriods: [...new Set(cache.observations.map((row) => String(row.period)))].slice(0, 24),
      requestNote: reportText(payload.requestNote, 1000),
    },
  };
}

async function importTradeData(payload: JsonRecord) {
  await ensureResearchSchema();
  const runId = String(payload.runId ?? "").trim();
  const db = getRawDb();
  const request = await db.prepare(`SELECT r.*, c.dossier_id
    FROM trade_data_refresh_requests r
    JOIN opportunity_cases c ON c.id = r.opportunity_id
    WHERE r.id = ? AND r.status = 'pending'`).bind(runId).first<JsonRecord>();
  if (!request) throw new Error("没有找到待写回的贸易数据任务");
  const rows = Array.isArray(payload.observations) ? payload.observations.slice(0, 500).map(asObject) : [];
  if (!rows.length) throw new Error("贸易数据结果没有 observations");
  const normalizedRows = rows.map(normalizeTradeObservation);
  const timestamp = nowIso();
  const statements: D1PreparedStatement[] = [];
  for (let index = 0; index < normalizedRows.length; index += 1) {
    const row = normalizedRows[index];
    const raw = rows[index];
    const fingerprint = [request.product_family_code, request.region_code, row.reporterCode, row.partnerCode,
      row.classification, row.commodityCode, row.flow, row.period, row.frequency, row.metric,
      row.value ?? "missing", row.status, row.sourceUrl].join("|").toLocaleLowerCase();
    statements.push(db.prepare(`INSERT OR IGNORE INTO trade_data_observations
      (id, fingerprint, refresh_request_id, opportunity_id, product_family_code, region_code, reporter_code,
       partner_code, classification, commodity_code, commodity_label, flow, period, frequency, metric, value,
       unit, source_name, source_url, source_grade, data_status, missing_reason, collected_at, created_by, raw_record, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ai_assistant', ?, ?)`)
      .bind(crypto.randomUUID(), fingerprint, runId, request.opportunity_id, request.product_family_code, request.region_code,
        row.reporterCode, row.partnerCode, row.classification, row.commodityCode, row.commodityLabel, row.flow,
        row.period, row.frequency, row.metric, row.value, row.unit, row.sourceName, row.sourceUrl, row.sourceGrade,
        row.status, row.missingReason, row.collectedAt, JSON.stringify(raw), timestamp));
  }
  const availableRows = normalizedRows.filter((row) => row.status === "available");
  statements.push(db.prepare("UPDATE trade_data_refresh_requests SET status = 'completed', error = '', completed_at = ? WHERE id = ?")
    .bind(timestamp, runId));
  statements.push(db.prepare("UPDATE opportunity_cases SET updated_at = ? WHERE id = ?").bind(timestamp, request.opportunity_id));
  if (availableRows.length) {
    const official = availableRows.some((row) => ["official", "official_export"].includes(row.sourceGrade));
    const periods = [...new Set(availableRows.map((row) => row.period))].sort();
    const evidenceTitle = `本地贸易数据 · ${availableRows[0].commodityLabel}`;
    const evidenceUrl = availableRows[0].sourceUrl;
    const evidencePeriod = periods.join("、");
    statements.push(db.prepare(`INSERT INTO opportunity_evidence
      (id, opportunity_id, dossier_id, evidence_scope, evidence_type, source_grade, title, source_url, note, market_code,
       period, metrics, evidence_status, captured_at, created_by, created_at)
      SELECT ?, ?, ?, 'shared', 'demand', ?, ?, ?, ?, ?, ?, ?, 'available', ?, 'ai_assistant', ?
      WHERE NOT EXISTS (
        SELECT 1 FROM opportunity_evidence
        WHERE dossier_id = ? AND evidence_scope = 'shared' AND evidence_type = 'demand'
          AND source_url = ? AND title = ? AND period = ?
      )`)
      .bind(crypto.randomUUID(), request.opportunity_id, request.dossier_id, official ? "official" : "other",
        evidenceTitle, evidenceUrl,
        `本轮按“${TRADE_COLLECTION_POLICIES[normalizeTradeCollectionLevel(request.collection_level)].label}”新增 ${availableRows.length} 条贸易观测；仅作为进出口需求证据，不等同于终端销售额。`, request.region_code,
        evidencePeriod, JSON.stringify({ observation_count: availableRows.length, collection_level: normalizeTradeCollectionLevel(request.collection_level), sources: [...new Set(availableRows.map((row) => row.sourceName))] }),
        timestamp, timestamp, request.dossier_id, evidenceUrl, evidenceTitle, evidencePeriod));
  }
  for (let index = 0; index < statements.length; index += 100) await db.batch(statements.slice(index, index + 100));
  return { imported: normalizedRows.length, available: availableRows.length, cache: await readTradeDataCache(String(request.opportunity_id)) };
}

async function failTradeDataRequest(payload: JsonRecord) {
  await ensureResearchSchema();
  const runId = String(payload.runId ?? "").trim();
  await getRawDb().prepare("UPDATE trade_data_refresh_requests SET status = 'failed', error = ?, completed_at = ? WHERE id = ? AND status = 'pending'")
    .bind(reportText(payload.error, 1000) || "AI贸易数据任务未完成", nowIso(), runId).run();
  return { runId, status: "failed" };
}

async function readOpportunityValidationContext(opportunityId: string | null) {
  const id = String(opportunityId ?? "").trim();
  if (!id) throw new Error("缺少商机编号");
  const center = await readOpportunityCenter();
  const opportunity = (center.cases as Array<JsonRecord & { active: boolean }>).find((item) => String(item.id) === id);
  if (!opportunity) throw new Error("没有找到该商机");
  const dossierId = String(opportunity.dossier_id ?? "");
  const evidence = (center.evidence as Array<JsonRecord & { metrics: JsonRecord }>).filter((item) =>
    String(item.opportunity_id) === id
    || (String(item.evidence_scope) === "shared" && dossierId && String(item.dossier_id) === dossierId));
  const tradeData = (center.tradeData as Array<JsonRecord & { value: number | null }>).filter((item) => String(item.product_family_code) === String(opportunity.product_family_code)
    && [String(opportunity.region_code), "GLOBAL"].includes(String(item.region_code)));
  const matrix = (center.taxonomy.personaMatrix as JsonRecord[]).filter((item) => String(item.persona_code) === String(opportunity.persona_code)
    && String(item.product_family_code) === String(opportunity.product_family_code)
    && [String(opportunity.region_code), "GLOBAL"].includes(String(item.region_code)));
  return {
    opportunity,
    evidence,
    tradeData,
    matrix,
    requests: (center.validationRequests as JsonRecord[]).filter((item) => String(item.opportunity_id) === id),
  };
}

async function createOpportunityValidationRequest(payload: JsonRecord) {
  await ensureResearchSchema();
  const opportunityId = String(payload.opportunityId ?? "").trim();
  const context = await readOpportunityValidationContext(opportunityId);
  if (!context.opportunity.active) throw new Error("已归档商机不能启动公开证据采集");
  const db = getRawDb();
  const existingPending = await db.prepare("SELECT id, created_at FROM opportunity_validation_requests WHERE opportunity_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1")
    .bind(opportunityId).first<JsonRecord>();
  if (existingPending) return { pending: true, runId: String(existingPending.id), createdAt: String(existingPending.created_at) };
  const runId = crypto.randomUUID();
  const timestamp = nowIso();
  const requestNote = reportText(payload.requestNote, 1200);
  await db.prepare(`INSERT INTO opportunity_validation_requests
    (id, opportunity_id, status, trigger_reason, request_note, requested_by, created_at)
    VALUES (?, ?, 'pending', ?, ?, ?, ?)`).bind(runId, opportunityId,
      reportText(payload.triggerReason, 80) || "manual", requestNote, opportunityOrigin(payload), timestamp).run();
  const region = centerValue(context.opportunity.region_code);
  const regionMaster = (await readGlobalBuyerLibrary()).taxonomy.regions.find((item: JsonRecord) => String(item.code) === region);
  return {
    pending: false,
    request: {
      runId,
      opportunityId,
      title: centerValue(context.opportunity.title),
      personaCode: centerValue(context.opportunity.persona_code),
      personaName: centerValue(context.opportunity.persona_name),
      regionCode: region,
      regionName: centerValue(context.opportunity.region_name),
      countries: regionMaster ? jsonArray(regionMaster.countries) : [],
      trackCode: centerValue(context.opportunity.track_code),
      trackName: centerValue(context.opportunity.track_name),
      productFamilyCode: centerValue(context.opportunity.product_family_code),
      productFamilyName: centerValue(context.opportunity.product_family_name),
      purchaseScenario: centerValue(context.opportunity.purchase_scenario),
      salesChannel: centerValue(context.opportunity.sales_channel),
      hypothesis: centerValue(context.opportunity.hypothesis),
      existingEvidenceTypes: [...new Set(context.evidence.map((item) => String(item.evidence_type)))],
      requestNote,
    },
  };
}

function centerValue(value: unknown) {
  return String(value ?? "").trim();
}

function opportunityEvidenceMetrics(value: unknown) {
  const input = asObject(value);
  return Object.fromEntries(Object.entries(input).slice(0, 20).flatMap(([key, raw]) => {
    const normalizedKey = key.trim().toLocaleLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 64);
    if (!normalizedKey || !["string", "number", "boolean"].includes(typeof raw)) return [];
    return [[normalizedKey, typeof raw === "string" ? raw.slice(0, 500) : raw]];
  }));
}

async function importOpportunityValidation(payload: JsonRecord) {
  await ensureResearchSchema();
  const runId = String(payload.runId ?? "").trim();
  const report = asObject(payload.report ?? payload);
  const db = getRawDb();
  const request = await db.prepare(`SELECT r.*, c.dossier_id
    FROM opportunity_validation_requests r
    JOIN opportunity_cases c ON c.id = r.opportunity_id
    WHERE r.id = ? AND r.status = 'pending'`)
    .bind(runId).first<JsonRecord>();
  if (!request) throw new Error("没有找到待写回的商机公开证据任务");
  const rawRows = Array.isArray(report.evidence) ? report.evidence.slice(0, 60).map(asObject) : [];
  const rows = rawRows.flatMap((item) => {
    const evidenceType = String(item.evidenceType ?? item.evidence_type ?? "");
    const requestedGrade = String(item.sourceGrade ?? item.source_grade ?? "other");
    const sourceGrade = ["official", "marketplace", "other"].includes(requestedGrade) ? requestedGrade : "other";
    const title = reportText(item.title, 240);
    const sourceUrl = String(item.sourceUrl ?? item.source_url ?? "").trim();
    let validUrl = false;
    try { validUrl = ["http:", "https:"].includes(new URL(sourceUrl).protocol); } catch { validUrl = false; }
    if (!OPPORTUNITY_EVIDENCE_TYPES.has(evidenceType) || !title || !validUrl) return [];
    const capturedAtRaw = reportText(item.capturedAt ?? item.captured_at, 40);
    const capturedAt = capturedAtRaw && !Number.isNaN(Date.parse(capturedAtRaw)) ? new Date(capturedAtRaw).toISOString() : nowIso();
    return [{
      evidenceType,
      sourceGrade,
      title,
      sourceUrl,
      note: reportText(item.note, 2000),
      marketCode: reportText(item.marketCode ?? item.market_code, 24).toUpperCase(),
      period: reportText(item.period, 120),
      metrics: opportunityEvidenceMetrics(item.metrics),
      capturedAt,
    }];
  });
  if (!rows.length) throw new Error("公开证据任务没有返回可核验的 http/https 来源");
  const timestamp = nowIso();
  const statements: D1PreparedStatement[] = rows.map((item) => {
    const evidenceScope = opportunityEvidenceScope(item.evidenceType);
    const dossierId = evidenceScope === "shared" ? String(request.dossier_id ?? "") : "";
    const duplicateScope = evidenceScope === "shared" ? dossierId : String(request.opportunity_id);
    const duplicateColumn = evidenceScope === "shared" ? "dossier_id" : "opportunity_id";
    return db.prepare(`INSERT INTO opportunity_evidence
      (id, opportunity_id, dossier_id, evidence_scope, evidence_type, source_grade, title, source_url, note, market_code,
       period, metrics, evidence_status, captured_at, created_by, created_at)
      SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?, 'ai_assistant', ?
      WHERE NOT EXISTS (
        SELECT 1 FROM opportunity_evidence
        WHERE ${duplicateColumn} = ? AND evidence_scope = ? AND evidence_type = ? AND source_url = ? AND title = ?
      )`).bind(crypto.randomUUID(), request.opportunity_id, dossierId, evidenceScope, item.evidenceType, item.sourceGrade,
        item.title, item.sourceUrl, item.note, item.marketCode, item.period, JSON.stringify(item.metrics), item.capturedAt,
        timestamp, duplicateScope, evidenceScope, item.evidenceType, item.sourceUrl, item.title);
  });
  const summary = reportText(report.summary, 2000);
  const suggestedNextAction = reportText(report.suggestedNextAction ?? report.nextAction, 500);
  statements.push(db.prepare(`UPDATE opportunity_validation_requests
    SET status = 'completed', summary = ?, suggested_next_action = ?, error = '', completed_at = ? WHERE id = ?`)
    .bind(summary, suggestedNextAction, timestamp, runId));
  statements.push(db.prepare(`UPDATE opportunity_cases SET updated_at = ?, version = version + 1,
    next_action = CASE WHEN next_action = '' THEN ? ELSE next_action END WHERE id = ?`)
    .bind(timestamp, suggestedNextAction, request.opportunity_id));
  await db.batch(statements);
  return { imported: rows.length, context: await readOpportunityValidationContext(String(request.opportunity_id)) };
}

async function failOpportunityValidationRequest(payload: JsonRecord) {
  await ensureResearchSchema();
  const runId = String(payload.runId ?? "").trim();
  await getRawDb().prepare(`UPDATE opportunity_validation_requests
    SET status = 'failed', error = ?, completed_at = ? WHERE id = ? AND status = 'pending'`)
    .bind(reportText(payload.error, 1000) || "AI公开证据任务未完成", nowIso(), runId).run();
  return { runId, status: "failed" };
}

async function syncProjectBuyerKnowledge(projectId: string) {
  const db = getRawDb();
  const [profiles, links] = await Promise.all([
    db.prepare("SELECT * FROM research_buyer_profiles WHERE project_id = ?").bind(projectId).all<JsonRecord>(),
    db.prepare("SELECT * FROM research_buyer_family_links WHERE project_id = ?").bind(projectId).all<JsonRecord>(),
  ]);
  if (!profiles.results.length) return { profileCount: 0, familyLinkCount: 0 };
  const timestamp = nowIso();
  const globalIdByProjectBuyer = new Map<string, string>();
  const statements: D1PreparedStatement[] = [];
  for (const row of profiles.results) {
    const existing = await db.prepare("SELECT id FROM global_buyer_profiles WHERE company_name = ? AND country = ?")
      .bind(String(row.company_name), String(row.country)).first<JsonRecord>();
    const globalId = String(existing?.id ?? crypto.randomUUID());
    globalIdByProjectBuyer.set(String(row.id), globalId);
    statements.push(db.prepare(`INSERT INTO global_buyer_profiles
      (id, company_name, website, country, buyer_type, persona_code, region_code, customer_groups, sales_channels, purchasing_scenarios,
       seasonality, replenishment_cycle, order_requirements, source_url, profile_status, created_by,
       created_at, updated_at, last_verified_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(company_name, country) DO UPDATE SET
        website = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.website ELSE excluded.website END,
        buyer_type = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.buyer_type ELSE excluded.buyer_type END,
        persona_code = CASE WHEN global_buyer_profiles.created_by = 'user' AND global_buyer_profiles.persona_code != '' THEN global_buyer_profiles.persona_code ELSE excluded.persona_code END,
        region_code = CASE WHEN global_buyer_profiles.created_by = 'user' AND global_buyer_profiles.region_code != '' THEN global_buyer_profiles.region_code ELSE excluded.region_code END,
        customer_groups = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.customer_groups ELSE excluded.customer_groups END,
        sales_channels = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.sales_channels ELSE excluded.sales_channels END,
        purchasing_scenarios = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.purchasing_scenarios ELSE excluded.purchasing_scenarios END,
        seasonality = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.seasonality ELSE excluded.seasonality END,
        replenishment_cycle = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.replenishment_cycle ELSE excluded.replenishment_cycle END,
        order_requirements = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.order_requirements ELSE excluded.order_requirements END,
        source_url = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.source_url ELSE excluded.source_url END,
        profile_status = CASE WHEN global_buyer_profiles.created_by = 'user' THEN global_buyer_profiles.profile_status ELSE excluded.profile_status END,
        created_by = CASE WHEN global_buyer_profiles.created_by = 'user' THEN 'user' ELSE excluded.created_by END,
        updated_at = excluded.updated_at,
        last_verified_at = COALESCE(excluded.last_verified_at, global_buyer_profiles.last_verified_at)`)
      .bind(globalId, row.company_name, row.website, row.country, row.buyer_type,
        suggestPersonaCode(String(row.buyer_type ?? ""), ...stringList(row.customer_groups), ...stringList(row.sales_channels), ...stringList(row.purchasing_scenarios)),
        regionCodeForCountry(String(row.country ?? "")), row.customer_groups, row.sales_channels,
        row.purchasing_scenarios, row.seasonality, row.replenishment_cycle, row.order_requirements, row.source_url,
        row.profile_status, row.created_by, row.created_at, timestamp,
        row.profile_status === "validated" ? timestamp : null));
    statements.push(db.prepare(`INSERT INTO global_buyer_project_refs
      (buyer_profile_id, project_id, project_buyer_profile_id, created_at) VALUES (?, ?, ?, ?)
      ON CONFLICT(buyer_profile_id, project_id) DO UPDATE SET project_buyer_profile_id = excluded.project_buyer_profile_id`)
      .bind(globalId, projectId, row.id, timestamp));
  }
  for (const row of links.results) {
    const globalBuyerId = globalIdByProjectBuyer.get(String(row.buyer_profile_id));
    if (!globalBuyerId) continue;
    statements.push(db.prepare(`INSERT INTO global_buyer_family_links
      (id, buyer_profile_id, track_category, product_family, relationship_score, family_role,
       sales_scenarios, rationale, evidence_status, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(buyer_profile_id, track_category, product_family) DO UPDATE SET
        relationship_score = CASE WHEN global_buyer_family_links.created_by = 'user' THEN global_buyer_family_links.relationship_score ELSE excluded.relationship_score END,
        family_role = CASE WHEN global_buyer_family_links.created_by = 'user' THEN global_buyer_family_links.family_role ELSE excluded.family_role END,
        sales_scenarios = CASE WHEN global_buyer_family_links.created_by = 'user' THEN global_buyer_family_links.sales_scenarios ELSE excluded.sales_scenarios END,
        rationale = CASE WHEN global_buyer_family_links.created_by = 'user' THEN global_buyer_family_links.rationale ELSE excluded.rationale END,
        evidence_status = CASE WHEN global_buyer_family_links.created_by = 'user' THEN global_buyer_family_links.evidence_status ELSE excluded.evidence_status END,
        updated_at = excluded.updated_at`)
      .bind(crypto.randomUUID(), globalBuyerId, row.track_category, row.product_family, row.relationship_score,
        row.family_role, row.sales_scenarios, row.rationale, row.evidence_status, row.created_by, row.created_at, timestamp));
  }
  for (let index = 0; index < statements.length; index += 100) await db.batch(statements.slice(index, index + 100));
  return { profileCount: profiles.results.length, familyLinkCount: links.results.length };
}

const INTEGRATION_CATALOG = [
  {
    id: "tiktok",
    name: "TikTok",
    role: "内容热度来源",
    registerUrl: "https://developers.tiktok.com/signup?from_subscription_prompt=true",
    docsUrl: "https://developers.tiktok.com/docs/en/get-started",
    envVars: ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_ACCESS_TOKEN"],
    required: ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"],
    cost: "开发者注册免费；部分数据产品需申请和审核",
    accessNote: "通用开发者 API 不等于全站关键词热度接口，当前优先使用公开证据或官方导出。",
    automaticCollection: false,
  },
  {
    id: "meta",
    name: "Meta Ads / Facebook",
    role: "广告商业验证来源",
    registerUrl: "https://developers.facebook.com/",
    docsUrl: "https://developers.facebook.com/docs/marketing-apis/",
    envVars: ["META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN"],
    required: ["META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN"],
    cost: "开发者注册免费；接口权限和可见数据取决于应用与账户授权",
    accessNote: "Marketing API 主要读取已授权广告资产，不提供任意关键词的全站搜索量。",
    automaticCollection: false,
  },
  {
    id: "instagram",
    name: "Instagram",
    role: "内容互动来源",
    registerUrl: "https://developers.facebook.com/",
    docsUrl: "https://developers.facebook.com/docs/instagram-platform/",
    envVars: ["META_APP_ID", "META_APP_SECRET", "INSTAGRAM_ACCESS_TOKEN"],
    required: ["META_APP_ID", "META_APP_SECRET", "INSTAGRAM_ACCESS_TOKEN"],
    cost: "开发者注册免费；需 Meta 应用、专业账户及相应权限",
    accessNote: "官方 API 以已授权账户数据为主，当前优先使用官方导出和合规抽样。",
    automaticCollection: false,
  },
  {
    id: "alibaba",
    name: "Alibaba.com",
    role: "供应竞争来源",
    registerUrl: "https://open.alibaba.com/",
    docsUrl: "https://open.alibaba.com/",
    envVars: ["ALIBABA_APP_KEY", "ALIBABA_APP_SECRET"],
    required: ["ALIBABA_APP_KEY", "ALIBABA_APP_SECRET"],
    cost: "开放平台注册入口免费；具体接口与数据权限以审核结果为准",
    accessNote: "没有可用权限时，可先导入官方导出或带来源链接的人工采集数据。",
    automaticCollection: false,
  },
  {
    id: "google",
    name: "Google Trends / Keyword Planner",
    role: "关键词搜索趋势与搜索需求来源",
    registerUrl: "https://developers.google.com/search/apis/trends",
    docsUrl: "https://developers.google.com/google-ads/api/docs/keyword-planning/generate-keyword-ideas",
    envVars: ["GOOGLE_TRENDS_ACCESS_TOKEN", "GOOGLE_ADS_CUSTOMER_ID", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"],
    required: ["GOOGLE_TRENDS_ACCESS_TOKEN"],
    configuredGroups: [
      ["GOOGLE_TRENDS_ACCESS_TOKEN"],
      ["GOOGLE_ADS_CUSTOMER_ID", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"],
    ],
    cost: "Google Trends 页面与 CSV 导出免费；Trends API alpha 需申请，Google Ads API 需账户授权",
    accessNote: "当前优先导入 Google Trends 官方 CSV 或带来源链接的公开数据；获得 API alpha 或 Google Ads 权限后可继续接入自动采集。",
    automaticCollection: false,
  },
  {
    id: "amazon",
    name: "Amazon SP-API",
    role: "商品目录、图片、排名与报价来源",
    registerUrl: "https://developer-docs.amazon.com/sp-api/docs/registering-your-application",
    docsUrl: "https://developer-docs.amazon.com/sp-api/docs/catalog-items-api-v2022-04-01-reference",
    envVars: ["AMAZON_SP_API_CLIENT_ID", "AMAZON_SP_API_CLIENT_SECRET", "AMAZON_SP_API_REFRESH_TOKEN", "AMAZON_MARKETPLACE_ID"],
    required: ["AMAZON_SP_API_CLIENT_ID", "AMAZON_SP_API_CLIENT_SECRET", "AMAZON_SP_API_REFRESH_TOKEN"],
    cost: "开放平台申请通常免费；需要卖家账户、应用审核和授权",
    accessNote: "Catalog Items API 支持按关键词搜索目录，可返回商品属性、图片和销售排名；它不等于全站关键词搜索量。",
    automaticCollection: false,
  },
  {
    id: "temu",
    name: "Temu Partner Platform",
    role: "商品、价格与店铺授权数据来源",
    registerUrl: "https://partner.temu.com/documentation",
    docsUrl: "https://partner.temu.com/documentation?menu_code=38e79b35d2cb463d85619c1c786dd303&sub_menu_code=8311de2b2d434e4d805e88413ab815d8",
    envVars: ["TEMU_APP_KEY", "TEMU_APP_SECRET", "TEMU_ACCESS_TOKEN"],
    required: ["TEMU_APP_KEY", "TEMU_APP_SECRET", "TEMU_ACCESS_TOKEN"],
    cost: "开放平台注册入口免费；API 需要应用审核及卖家授权",
    accessNote: "官方接口主要提供已授权店铺的商品、订单和履约数据；公开页面证据可导入，但不能宣称为全平台销量。",
    automaticCollection: false,
  },
  {
    id: "shein",
    name: "SHEIN Open Platform",
    role: "商品、价格与商家授权数据来源",
    registerUrl: "https://open.sheincorp.com/zh",
    docsUrl: "https://open.sheincorp.com/documents/apidoc/detail/3001291",
    envVars: ["SHEIN_APP_ID", "SHEIN_APP_SECRET", "SHEIN_ACCESS_TOKEN"],
    required: ["SHEIN_APP_ID", "SHEIN_APP_SECRET", "SHEIN_ACCESS_TOKEN"],
    cost: "账号申请入口免费；需创建应用、审核并获得商家授权",
    accessNote: "官方开放能力面向授权商家的商品与履约业务；公开商品页只能作为可追溯样本，不能替代官方关键词热度。",
    automaticCollection: false,
  },
  {
    id: "ebay",
    name: "eBay Browse API",
    role: "关键词商品、价格与在售竞争来源",
    registerUrl: "https://developer.ebay.com/",
    docsUrl: "https://developer.ebay.com/develop/api/buy",
    envVars: ["EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"],
    required: ["EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"],
    cost: "开发者计划可免费加入；Browse API 需要应用访问令牌",
    accessNote: "Browse API 支持按关键词检索公开商品及价格；数据按站点和授权范围返回。",
    automaticCollection: false,
  },
  {
    id: "walmart",
    name: "Walmart Marketplace API",
    role: "商品目录、价格与关键词匹配来源",
    registerUrl: "https://developer.walmart.com/",
    docsUrl: "https://developer.walmart.com/us-marketplace/reference/getsearchresult",
    envVars: ["WALMART_CLIENT_ID", "WALMART_CLIENT_SECRET", "WALMART_ACCESS_TOKEN"],
    required: ["WALMART_CLIENT_ID", "WALMART_CLIENT_SECRET"],
    cost: "开发入口免费；需要 Marketplace 卖家账户和访问凭证",
    accessNote: "Item Search 支持按关键词搜索 Walmart 商品目录，适合商品与价格验证，不等同关键词搜索量。",
    automaticCollection: false,
  },
  {
    id: "etsy",
    name: "Etsy Open API",
    role: "手工、家居与创意商品公开市场来源",
    registerUrl: "https://www.etsy.com/developers/register",
    docsUrl: "https://developers.etsy.com/documentation/reference/",
    envVars: ["ETSY_API_KEY", "ETSY_SHARED_SECRET", "ETSY_ACCESS_TOKEN"],
    required: ["ETSY_API_KEY", "ETSY_SHARED_SECRET"],
    cost: "应用注册通常免费；部分能力需要 OAuth 授权",
    accessNote: "Open API 可读取获准范围内的商品数据；公开商品页可作为抽样证据并保留直接链接。",
    automaticCollection: false,
  },
  {
    id: "aliexpress",
    name: "AliExpress Open Platform",
    role: "跨境商品、价格与供应竞争来源",
    registerUrl: "https://open.aliexpress.com/",
    docsUrl: "https://developer.alibaba.com/docs/doc.htm?articleId=120688&docType=1&treeId=727",
    envVars: ["ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET", "ALIEXPRESS_ACCESS_TOKEN"],
    required: ["ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET"],
    cost: "开放平台注册免费；具体接口需应用审核及权限",
    accessNote: "优先使用官方开放平台或联盟授权数据；公开商品页只能作为可追溯样本。",
    automaticCollection: false,
  },
  {
    id: "shopee",
    name: "Shopee Open Platform",
    role: "东南亚商品、价格与店铺授权数据来源",
    registerUrl: "https://open.shopee.com/",
    docsUrl: "https://open.shopee.com/documents",
    envVars: ["SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY", "SHOPEE_ACCESS_TOKEN"],
    required: ["SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY"],
    cost: "开放平台注册入口免费；需合作伙伴审核和卖家授权",
    accessNote: "官方 API 主要面向授权店铺；公开页面证据需保留站点、国家和采集时间。",
    automaticCollection: false,
  },
  {
    id: "lazada",
    name: "Lazada Open Platform",
    role: "东南亚商品、价格与卖家授权数据来源",
    registerUrl: "https://open.lazada.com/",
    docsUrl: "https://open.lazada.com/doc/doc.htm",
    envVars: ["LAZADA_APP_KEY", "LAZADA_APP_SECRET", "LAZADA_ACCESS_TOKEN"],
    required: ["LAZADA_APP_KEY", "LAZADA_APP_SECRET"],
    cost: "开放平台注册入口免费；应用类别决定可用接口",
    accessNote: "开放平台按国家站点提供商品、订单等授权数据；本雷达只读取可核验的商品与价格证据。",
    automaticCollection: false,
  },
  {
    id: "mercado_libre",
    name: "Mercado Libre Developers",
    role: "拉美商品、价格与市场供给来源",
    registerUrl: "https://developers.mercadolibre.com/",
    docsUrl: "https://developers.mercadolibre.com.mx/es_ar/como-empezar/items-y-busquedas",
    envVars: ["MERCADOLIBRE_CLIENT_ID", "MERCADOLIBRE_CLIENT_SECRET", "MERCADOLIBRE_ACCESS_TOKEN"],
    required: ["MERCADOLIBRE_CLIENT_ID", "MERCADOLIBRE_CLIENT_SECRET"],
    cost: "开发者注册入口免费；接口可见范围受应用和站点政策限制",
    accessNote: "按拉美国家站点记录商品与价格；遇到搜索权限限制时保留失败状态，不自动改用爬取。",
    automaticCollection: false,
  },
  {
    id: "rakuten",
    name: "Rakuten Web Service",
    role: "日本商品、价格、评价与关键词结果来源",
    registerUrl: "https://webservice.rakuten.co.jp/",
    docsUrl: "https://webservice.rakuten.co.jp/documentation/ichiba-item-search",
    envVars: ["RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY"],
    required: ["RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY"],
    cost: "应用注册和测试入口免费；受官方调用频率限制",
    accessNote: "Ichiba Item Search API 支持按关键词返回商品数、价格与图片，适合日本市场的公开商品验证。",
    automaticCollection: false,
  },
  {
    id: "openai",
    name: "OpenAI",
    role: "AI 整理服务",
    registerUrl: "https://platform.openai.com/signup",
    docsUrl: "https://developers.openai.com/api/docs/guides/structured-outputs",
    envVars: ["OPENAI_API_KEY", "OPENAI_MODEL"],
    required: ["OPENAI_API_KEY"],
    cost: "API 通常按量计费；仅在主动点击 AI 整理时调用",
    accessNote: "用于扩词、检索公开证据、结构化和入库，不会把缺失数据补成 0。",
    automaticCollection: true,
  },
] as const;

const PUBLIC_ACCESS_NOTES: Record<string, string> = {
  alibaba: "公开搜索页和商品页可免 API 密钥抽样；精确接口数据仍需开放平台授权。",
  google: "Google Trends 网页与 CSV 可免 API 密钥使用；自动 API 仍需 alpha 或 Google Ads 授权。",
  amazon: "Amazon 前台搜索/商品页可免 API 密钥抽样；SP-API 仍需注册、应用和卖家授权。",
  temu: "Temu 前台商品页可免 API 密钥抽样；Partner API 仍需应用和卖家授权。",
  shein: "SHEIN 前台商品页可免 API 密钥抽样；Open Platform 仍需应用和商家授权。",
  ebay: "eBay 前台搜索/商品页可免 API 密钥抽样；Browse API 仍需应用令牌。",
  walmart: "Walmart 前台搜索/商品页可免 API 密钥抽样；Marketplace API 仍需卖家凭证。",
  etsy: "Etsy 前台搜索/商品页可免 API 密钥抽样；Open API 仍需应用凭证。",
  aliexpress: "AliExpress 前台搜索/商品页可免 API 密钥抽样；Open Platform 仍需应用权限。",
  shopee: "Shopee 各国家站商品页可免 API 密钥抽样；Open Platform 仍需合作伙伴与卖家授权。",
  lazada: "Lazada 各国家站商品页可免 API 密钥抽样；Open Platform 仍需应用授权。",
  mercado_libre: "Mercado Libre 各国家站商品页可免 API 密钥抽样；官方产品搜索 API 仍需访问令牌。",
  rakuten: "Rakuten 前台商品页可免 API 密钥抽样；Web Service API 仍需应用 ID。",
};

function runtimeValue(key: string) {
  const workerValue = (env as unknown as Record<string, unknown>)[key];
  return String(workerValue ?? process.env[key] ?? "").trim();
}

type ManagedCredentialField = {
  id: string;
  label: string;
  type: "text" | "password" | "url";
  placeholder: string;
  required: boolean;
};

type ManagedCredentialDefinition = {
  name: string;
  registerUrl: string;
  docsUrl: string;
  instructions: string;
  fields: ManagedCredentialField[];
  envVars: Record<string, string>;
  testable: boolean;
  publicAccess?: boolean;
};

const MANAGED_CREDENTIALS: Record<string, ManagedCredentialDefinition> = {
  un_comtrade: {
    name: "UN Comtrade",
    registerUrl: "https://comtradedeveloper.un.org/product#product=free",
    docsUrl: "https://uncomtrade.org/docs/api-subscription-keys/",
    instructions: "订阅 Free API 后复制 Primary key。系统会加密保存，采集时自动使用。",
    fields: [{ id: "apiKey", label: "Primary key", type: "password", placeholder: "粘贴 Primary key", required: true }],
    envVars: { apiKey: "UN_COMTRADE_API_KEY" },
    testable: true,
  },
  eurostat_comext: {
    name: "Eurostat Comext",
    registerUrl: "https://ec.europa.eu/eurostat/web/international-trade-in-goods/data/database",
    docsUrl: "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction",
    instructions: "Eurostat 公共 API 无需密钥，系统可直接采集。需要登录下载的文件仍由你导出后上传。",
    fields: [],
    envVars: {},
    testable: false,
    publicAccess: true,
  },
  uk_hmrc: {
    name: "UK HMRC Trade Info",
    registerUrl: "https://www.uktradeinfo.com/",
    docsUrl: "https://www.uktradeinfo.com/api-documentation/",
    instructions: "HMRC UK Trade Info 是公开 OData REST API，无需密钥；系统按 HS/CN 编码和月份自动汇总英国进口额与净重。",
    fields: [],
    envVars: {},
    testable: false,
    publicAccess: true,
  },
  us_census: {
    name: "U.S. Census International Trade",
    registerUrl: "https://api.census.gov/data/key_signup.html",
    docsUrl: "https://www.census.gov/data/developers/data-sets/international-trade.html",
    instructions: "少量查询可免密钥；批量调用建议申请免费的 Census API Key。",
    fields: [{ id: "apiKey", label: "Census API Key", type: "password", placeholder: "粘贴 Census API Key", required: true }],
    envVars: { apiKey: "CENSUS_API_KEY" },
    testable: false,
  },
  wto_data: {
    name: "WTO Data / WTO API",
    registerUrl: "https://apiportal.wto.org/",
    docsUrl: "https://apiportal.wto.org/",
    instructions: "公开查询不需要密钥；如 WTO 为你的账号签发订阅密钥，可在这里保存。",
    fields: [{ id: "apiKey", label: "WTO Subscription Key", type: "password", placeholder: "没有密钥可暂不配置", required: true }],
    envVars: { apiKey: "WTO_API_KEY" },
    testable: false,
  },
  world_bank_wits: {
    name: "World Bank WITS",
    registerUrl: "https://wits.worldbank.org/",
    docsUrl: "https://wits.worldbank.org/witsapiintro.aspx",
    instructions: "WITS REST API 是公开接口，无需 API Key 或网站登录密码；系统可直接采集 TRAINS 关税与 Trade Stats 指标。",
    fields: [],
    envVars: {},
    testable: false,
    publicAccess: true,
  },
  national_statistics: {
    name: "各国海关与统计局",
    registerUrl: "https://unstats.un.org/unsd/methodology/m49/",
    docsUrl: "https://unstats.un.org/unsd/methodology/m49/",
    instructions: "不同国家没有统一密钥。仅在目标国家提供 API 时，保存官方接口地址和密钥。",
    fields: [
      { id: "endpoint", label: "官方 API 地址", type: "url", placeholder: "https://...", required: true },
      { id: "apiKey", label: "API Key / Access Token", type: "password", placeholder: "粘贴官方凭证", required: true },
    ],
    envVars: { endpoint: "NATIONAL_STATS_API_URL", apiKey: "NATIONAL_STATS_API_KEY" },
    testable: false,
  },
  odoo_sales: {
    name: "Odoo 销售与 CRM",
    registerUrl: "https://www.odoo.com/documentation/",
    docsUrl: "https://www.odoo.com/documentation/19.0/developer/reference/external_api.html",
    instructions: "建议创建只读或最小权限集成账号。连接信息会作为一个整体加密保存。",
    fields: [
      { id: "baseUrl", label: "Odoo 地址", type: "url", placeholder: "https://your-company.odoo.com", required: true },
      { id: "database", label: "数据库名称", type: "text", placeholder: "Odoo database", required: true },
      { id: "username", label: "集成账号", type: "text", placeholder: "integration@example.com", required: true },
      { id: "apiKey", label: "API Key", type: "password", placeholder: "粘贴 Odoo API Key", required: true },
    ],
    envVars: { baseUrl: "ODOO_URL", database: "ODOO_DATABASE", username: "ODOO_USERNAME", apiKey: "ODOO_API_KEY" },
    testable: false,
  },
  tiktok_business: {
    name: "TikTok Business API",
    registerUrl: "https://business-api.tiktok.com/portal",
    docsUrl: "https://business-api.tiktok.com/portal/docs",
    instructions: "创建 TikTok for Business 开发者应用并完成审核后，保存应用凭证、长期访问令牌和广告主 ID。",
    fields: [
      { id: "appId", label: "App ID", type: "text", placeholder: "TikTok App ID", required: true },
      { id: "appSecret", label: "App Secret", type: "password", placeholder: "粘贴 App Secret", required: true },
      { id: "accessToken", label: "Access Token", type: "password", placeholder: "粘贴长期 Access Token", required: true },
      { id: "advertiserId", label: "Advertiser ID", type: "text", placeholder: "广告主 ID", required: true },
    ],
    envVars: {},
    testable: false,
  },
  meta_graph: {
    name: "Meta Ads / Instagram Graph API",
    registerUrl: "https://developers.facebook.com/apps/",
    docsUrl: "https://developers.facebook.com/docs/marketing-apis/",
    instructions: "Meta Ads 与 Instagram 共用一套 Graph API 连接。应用需获得相应权限，并使用长期访问令牌。",
    fields: [
      { id: "appId", label: "Meta App ID", type: "text", placeholder: "Meta App ID", required: true },
      { id: "appSecret", label: "App Secret", type: "password", placeholder: "粘贴 App Secret", required: true },
      { id: "accessToken", label: "Long-lived Access Token", type: "password", placeholder: "粘贴长期访问令牌", required: true },
      { id: "businessId", label: "Business Manager ID", type: "text", placeholder: "可选", required: false },
      { id: "adAccountId", label: "Ad Account ID", type: "text", placeholder: "例如 act_123456", required: false },
      { id: "instagramAccountId", label: "Instagram Business Account ID", type: "text", placeholder: "可选", required: false },
    ],
    envVars: {},
    testable: false,
  },
  google_ads_keyword_planner: {
    name: "Google Ads Keyword Planner",
    registerUrl: "https://ads.google.com/home/tools/keyword-planner/",
    docsUrl: "https://developers.google.com/google-ads/api/docs/keyword-planning/overview",
    instructions: "Google Trends 公共趋势不需要 Key；关键词月均搜索量、竞争度与 CPC 通过 Google Ads Keyword Planner API 获取。需要 OAuth 凭证、获批 Basic 访问权限的 Google Cloud 项目和 Google Ads 客户 ID。",
    fields: [
      { id: "developerToken", label: "Developer Token（旧版，可选）", type: "password", placeholder: "Google 已弃用，新配置可留空", required: false },
      { id: "clientId", label: "OAuth Client ID", type: "password", placeholder: "Google Cloud OAuth Client ID", required: true },
      { id: "clientSecret", label: "OAuth Client Secret", type: "password", placeholder: "粘贴 OAuth Client Secret", required: true },
      { id: "refreshToken", label: "OAuth Refresh Token", type: "password", placeholder: "粘贴 Refresh Token", required: true },
      { id: "customerId", label: "Google Ads Customer ID", type: "text", placeholder: "10 位数字，不含连字符", required: true },
      { id: "loginCustomerId", label: "Manager Account ID", type: "text", placeholder: "通过经理账号访问时填写，不含连字符", required: false },
    ],
    envVars: {},
    testable: true,
  },
  alibaba_open: {
    name: "Alibaba.com Open Platform",
    registerUrl: "https://open.alibaba.com/",
    docsUrl: "https://open.alibaba.com/",
    instructions: "创建或绑定 Alibaba.com 开放平台应用并完成授权后，保存 App Key、App Secret 和访问令牌。",
    fields: [
      { id: "appKey", label: "App Key", type: "text", placeholder: "Alibaba App Key", required: true },
      { id: "appSecret", label: "App Secret", type: "password", placeholder: "粘贴 App Secret", required: true },
      { id: "accessToken", label: "Access Token", type: "password", placeholder: "粘贴 Access Token", required: true },
    ],
    envVars: {},
    testable: false,
  },
  amazon_sp_api: {
    name: "Amazon Selling Partner API",
    registerUrl: "https://developer-docs.amazon.com/sp-api/docs/registering-your-application",
    docsUrl: "https://developer-docs.amazon.com/sp-api/",
    instructions: "注册并授权 Selling Partner API 应用后，保存 Login with Amazon 凭证、刷新令牌和站点 Marketplace ID。",
    fields: [
      { id: "clientId", label: "LWA Client ID", type: "password", placeholder: "amzn1.application-oa2-client...", required: true },
      { id: "clientSecret", label: "LWA Client Secret", type: "password", placeholder: "粘贴 LWA Client Secret", required: true },
      { id: "refreshToken", label: "Refresh Token", type: "password", placeholder: "粘贴 SP-API Refresh Token", required: true },
      { id: "marketplaceId", label: "Marketplace ID", type: "text", placeholder: "例如 ATVPDKIKX0DER", required: true },
    ],
    envVars: {},
    testable: false,
  },
  temu_open: {
    name: "Temu Seller / Partner API",
    registerUrl: "https://seller.temu.com/",
    docsUrl: "https://seller.temu.com/",
    instructions: "Temu 接口通常只向已入驻卖家或获批合作伙伴开放。获批后保存平台签发的应用凭证；未获批时使用后台导出文件。",
    fields: [
      { id: "appKey", label: "App Key / Client ID", type: "text", placeholder: "Temu 签发的应用标识", required: true },
      { id: "appSecret", label: "App Secret", type: "password", placeholder: "粘贴 App Secret", required: true },
      { id: "accessToken", label: "Access Token", type: "password", placeholder: "如平台签发则填写", required: false },
    ],
    envVars: {},
    testable: false,
  },
  shein_open: {
    name: "SHEIN Marketplace API",
    registerUrl: "https://open.sheincorp.com/",
    docsUrl: "https://open.sheincorp.com/",
    instructions: "SHEIN Marketplace 接口需卖家或合作伙伴资格。获批后保存应用凭证；没有权限时使用官方后台导出。",
    fields: [
      { id: "appId", label: "App ID", type: "text", placeholder: "SHEIN App ID", required: true },
      { id: "appSecret", label: "App Secret", type: "password", placeholder: "粘贴 App Secret", required: true },
      { id: "accessToken", label: "Access Token", type: "password", placeholder: "如平台签发则填写", required: false },
    ],
    envVars: {},
    testable: false,
  },
  ebay_developer: {
    name: "eBay Developers API",
    registerUrl: "https://developer.ebay.com/signin",
    docsUrl: "https://developer.ebay.com/api-docs/static/authorization_guide_landing.html",
    instructions: "创建 eBay 开发者应用并完成 OAuth 授权后，保存 Client ID、Client Secret 与 Refresh Token。",
    fields: [
      { id: "clientId", label: "Client ID (App ID)", type: "text", placeholder: "eBay Client ID", required: true },
      { id: "clientSecret", label: "Client Secret (Cert ID)", type: "password", placeholder: "粘贴 Client Secret", required: true },
      { id: "refreshToken", label: "OAuth Refresh Token", type: "password", placeholder: "粘贴 Refresh Token", required: true },
      { id: "marketplaceId", label: "Marketplace ID", type: "text", placeholder: "例如 EBAY_US", required: false },
    ],
    envVars: {},
    testable: false,
  },
  walmart_marketplace: {
    name: "Walmart Marketplace API",
    registerUrl: "https://developer.walmart.com/",
    docsUrl: "https://developer.walmart.com/doc/us/mp/us-mp-auth/",
    instructions: "Walmart Marketplace 卖家或服务商在 Developer Portal 生成 Client ID 与 Client Secret 后保存。",
    fields: [
      { id: "clientId", label: "Client ID", type: "text", placeholder: "Walmart Client ID", required: true },
      { id: "clientSecret", label: "Client Secret", type: "password", placeholder: "粘贴 Client Secret", required: true },
    ],
    envVars: {},
    testable: false,
  },
  etsy_open_api: {
    name: "Etsy Open API",
    registerUrl: "https://www.etsy.com/developers/register",
    docsUrl: "https://developers.etsy.com/documentation/",
    instructions: "注册 Etsy 应用并完成 OAuth 2.0 授权后，保存 Keystring、Shared Secret 与 Refresh Token。",
    fields: [
      { id: "apiKey", label: "Keystring", type: "text", placeholder: "Etsy Keystring", required: true },
      { id: "sharedSecret", label: "Shared Secret", type: "password", placeholder: "粘贴 Shared Secret", required: true },
      { id: "refreshToken", label: "OAuth Refresh Token", type: "password", placeholder: "粘贴 Refresh Token", required: true },
    ],
    envVars: {},
    testable: false,
  },
  aliexpress_open: {
    name: "AliExpress Open Platform",
    registerUrl: "https://open.aliexpress.com/",
    docsUrl: "https://open.aliexpress.com/doc.htm",
    instructions: "创建 AliExpress 开放平台应用并完成店铺授权后，保存 App Key、App Secret 和访问令牌。",
    fields: [
      { id: "appKey", label: "App Key", type: "text", placeholder: "AliExpress App Key", required: true },
      { id: "appSecret", label: "App Secret", type: "password", placeholder: "粘贴 App Secret", required: true },
      { id: "accessToken", label: "Access Token", type: "password", placeholder: "粘贴 Access Token", required: true },
    ],
    envVars: {},
    testable: false,
  },
  shopee_open: {
    name: "Shopee Open Platform",
    registerUrl: "https://open.shopee.com/",
    docsUrl: "https://open.shopee.com/documents",
    instructions: "注册 Shopee Open Platform 合作伙伴应用并授权店铺后，保存 Partner ID、Partner Key、Shop ID 和访问令牌。",
    fields: [
      { id: "partnerId", label: "Partner ID", type: "text", placeholder: "Shopee Partner ID", required: true },
      { id: "partnerKey", label: "Partner Key", type: "password", placeholder: "粘贴 Partner Key", required: true },
      { id: "shopId", label: "Shop ID", type: "text", placeholder: "店铺 ID", required: true },
      { id: "accessToken", label: "Access Token", type: "password", placeholder: "粘贴 Access Token", required: true },
    ],
    envVars: {},
    testable: false,
  },
  lazada_open: {
    name: "Lazada Open Platform",
    registerUrl: "https://open.lazada.com/",
    docsUrl: "https://open.lazada.com/doc/doc.htm",
    instructions: "注册 Lazada Open Platform 应用并完成卖家授权后，保存 App Key、App Secret、访问令牌和站点。",
    fields: [
      { id: "appKey", label: "App Key", type: "text", placeholder: "Lazada App Key", required: true },
      { id: "appSecret", label: "App Secret", type: "password", placeholder: "粘贴 App Secret", required: true },
      { id: "accessToken", label: "Access Token", type: "password", placeholder: "粘贴 Access Token", required: true },
      { id: "countryCode", label: "站点国家代码", type: "text", placeholder: "例如 SG / MY / TH", required: true },
    ],
    envVars: {},
    testable: false,
  },
  mercado_libre: {
    name: "Mercado Libre Developers",
    registerUrl: "https://developers.mercadolibre.com/",
    docsUrl: "https://developers.mercadolibre.com/en_us/authentication-and-authorization",
    instructions: "创建 Mercado Libre 应用并完成 OAuth 授权后，保存 Client ID、Client Secret 与 Refresh Token。",
    fields: [
      { id: "clientId", label: "Client ID", type: "text", placeholder: "Mercado Libre Client ID", required: true },
      { id: "clientSecret", label: "Client Secret", type: "password", placeholder: "粘贴 Client Secret", required: true },
      { id: "refreshToken", label: "Refresh Token", type: "password", placeholder: "粘贴 Refresh Token", required: true },
      { id: "siteId", label: "Site ID", type: "text", placeholder: "例如 MLB / MLM / MLA", required: true },
    ],
    envVars: {},
    testable: false,
  },
  rakuten_web_service: {
    name: "Rakuten Web Service",
    registerUrl: "https://webservice.rakuten.co.jp/app/create",
    docsUrl: "https://webservice.rakuten.co.jp/documentation",
    instructions: "创建 Rakuten Web Service 应用后保存 Application ID；需要联盟归因时再填写 Affiliate ID。",
    fields: [
      { id: "applicationId", label: "Application ID", type: "password", placeholder: "Rakuten Application ID", required: true },
      { id: "affiliateId", label: "Affiliate ID", type: "password", placeholder: "可选", required: false },
    ],
    envVars: {},
    testable: false,
  },
};

type ManagedCredentialId = keyof typeof MANAGED_CREDENTIALS;

function managedCredentialId(value: unknown): ManagedCredentialId {
  const id = String(value ?? "").trim();
  if (!(id in MANAGED_CREDENTIALS)) throw new Error("暂不支持该 API Key");
  return id as ManagedCredentialId;
}

function credentialSettingKey(id: ManagedCredentialId) {
  return `credential:${id}`;
}

function credentialMetaKey(id: ManagedCredentialId) {
  return `credential_meta:${id}`;
}

function credentialsMasterKey() {
  const value = runtimeValue("LIGHTLINK_CREDENTIALS_MASTER_KEY");
  if (!value) throw new Error("本机密钥保险箱尚未初始化，请重新启动 LightLink");
  return value;
}

function environmentCredentialValues(id: ManagedCredentialId) {
  const definition = MANAGED_CREDENTIALS[id];
  return Object.fromEntries(
    Object.entries(definition.envVars)
      .map(([fieldId, envVar]) => [fieldId, runtimeValue(envVar)])
      .filter(([, value]) => Boolean(value)),
  );
}

function environmentCredentialConfigured(id: ManagedCredentialId) {
  const definition = MANAGED_CREDENTIALS[id];
  const values = environmentCredentialValues(id);
  return definition.fields.length > 0
    && definition.fields.filter((field) => field.required).every((field) => Boolean(values[field.id]));
}

async function readManagedCredential(id: ManagedCredentialId): Promise<Record<string, string>> {
  const db = getRawDb();
  const row = await db
    .prepare("SELECT value FROM user_settings WHERE key = ?")
    .bind(credentialSettingKey(id))
    .first<{ value: string }>();
  if (row?.value) {
    const plaintext = await decryptCredential(parseEncryptedCredential(row.value), credentialsMasterKey());
    try {
      const parsed = JSON.parse(plaintext) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return Object.fromEntries(Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [key, String(value ?? "")]));
      }
    } catch {
      if (id === "un_comtrade") return { apiKey: plaintext };
    }
    throw new Error("无法识别已保存的连接配置，请删除后重新保存");
  }
  return environmentCredentialValues(id);
}

async function managedCredentialStatuses() {
  await ensureIntelligenceSchema();
  const db = getRawDb();
  const keys = Object.keys(MANAGED_CREDENTIALS) as ManagedCredentialId[];
  return Promise.all(keys.map(async (id) => {
    const item = MANAGED_CREDENTIALS[id];
    const [secretRow, metaRow, healthRow] = await Promise.all([
      db.prepare("SELECT updated_at FROM user_settings WHERE key = ?")
        .bind(credentialSettingKey(id)).first<{ updated_at: string }>(),
      db.prepare("SELECT value FROM user_settings WHERE key = ?")
        .bind(credentialMetaKey(id)).first<{ value: string }>(),
      db.prepare(`SELECT status, coverage_countries, quota_summary, update_frequency, last_attempt_at,
          last_success_at, last_failure_at, last_error_category, last_error, consecutive_failures,
          result_count, duration_ms, retry_count, updated_at
        FROM intelligence_source_health WHERE source_id = ? ORDER BY updated_at DESC LIMIT 1`)
        .bind(id).first<JsonRecord>(),
    ]);
    const meta = jsonObject(metaRow?.value);
    const environmentConfigured = environmentCredentialConfigured(id);
    return {
      id,
      name: item.name,
      configured: item.publicAccess || Boolean(secretRow) || environmentConfigured,
      source: item.publicAccess ? "public" : secretRow ? "managed" : environmentConfigured ? "environment" : null,
      storageReady: Boolean(runtimeValue("LIGHTLINK_CREDENTIALS_MASTER_KEY")),
      updatedAt: item.publicAccess ? null : secretRow?.updated_at ?? null,
      lastTestAt: typeof meta.lastTestAt === "string" ? meta.lastTestAt : null,
      lastTestStatus: typeof meta.lastTestStatus === "string" ? meta.lastTestStatus : null,
      lastTestMessage: typeof meta.lastTestMessage === "string" ? meta.lastTestMessage : "",
      registerUrl: item.registerUrl,
      docsUrl: item.docsUrl,
      instructions: item.instructions,
      fields: item.fields,
      testable: item.testable || item.fields.length > 0,
      publicAccess: Boolean(item.publicAccess),
      healthStatus: healthRow ? String(healthRow.status ?? "never_run") : "never_run",
      coverageCountries: healthRow ? stringList(healthRow.coverage_countries, 60) : [],
      quotaSummary: healthRow ? String(healthRow.quota_summary ?? "") : "",
      updateFrequency: healthRow ? String(healthRow.update_frequency ?? "") : "",
      lastAttemptAt: healthRow?.last_attempt_at ? String(healthRow.last_attempt_at) : null,
      lastSuccessAt: healthRow?.last_success_at ? String(healthRow.last_success_at) : null,
      lastFailureAt: healthRow?.last_failure_at ? String(healthRow.last_failure_at) : null,
      lastErrorCategory: healthRow ? String(healthRow.last_error_category ?? "") : "",
      lastError: healthRow ? String(healthRow.last_error ?? "") : "",
      consecutiveFailures: Number(healthRow?.consecutive_failures ?? 0),
      resultCount: Number(healthRow?.result_count ?? 0),
      durationMs: Number(healthRow?.duration_ms ?? 0),
      retryCount: Number(healthRow?.retry_count ?? 0),
    };
  }));
}

async function saveManagedCredential(payload: JsonRecord) {
  const id = managedCredentialId(payload.provider);
  const definition = MANAGED_CREDENTIALS[id];
  if (!definition.fields.length) throw new Error("该来源使用公开接口，无需保存密钥");
  const submitted = asObject(payload.values);
  if (typeof payload.secret === "string" && id === "un_comtrade") submitted.apiKey = payload.secret;
  const values: Record<string, string> = {};
  for (const field of definition.fields) {
    const value = String(submitted[field.id] ?? "").trim();
    if (field.required && !value) throw new Error(`请填写${field.label}`);
    if (value.length > 4096) throw new Error(`${field.label}内容过长`);
    if (field.type === "url" && value) {
      try {
        const url = new URL(value);
        if (!['http:', 'https:'].includes(url.protocol)) throw new Error();
      } catch {
        throw new Error(`${field.label}必须是有效的 HTTP(S) 地址`);
      }
    }
    if (value) values[field.id] = value;
  }
  const encrypted = await encryptCredential(JSON.stringify(values), credentialsMasterKey());
  const timestamp = nowIso();
  await getRawDb().prepare(
    `INSERT INTO user_settings (key, value, updated_at) VALUES (?, ?, ?)
     ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
  ).bind(credentialSettingKey(id), JSON.stringify(encrypted), timestamp).run();
  return { saved: true, provider: id, updatedAt: timestamp };
}

async function deleteManagedCredential(payload: JsonRecord) {
  const id = managedCredentialId(payload.provider);
  const db = getRawDb();
  await db.batch([
    db.prepare("DELETE FROM user_settings WHERE key = ?").bind(credentialSettingKey(id)),
    db.prepare("DELETE FROM user_settings WHERE key = ?").bind(credentialMetaKey(id)),
  ]);
  return { deleted: true, provider: id, environmentFallback: environmentCredentialConfigured(id) };
}

async function testUnComtradeCredential(secret: string) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const url = new URL("https://comtradeapi.un.org/data/v1/getLiveUpdate");
    url.searchParams.set("subscription-key", secret);
    const response = await fetch(url, {
      headers: { accept: "application/json" },
      signal: controller.signal,
    });
    if (response.ok) return { status: "ok", message: "连接成功，UN Comtrade 已接受该密钥。" };
    if (response.status === 401 || response.status === 403) {
      return { status: "error", message: "密钥未通过 UN Comtrade 验证，请重新复制 Primary key。" };
    }
    if (response.status === 429) {
      return { status: "rate_limited", message: "密钥已被识别，但当前配额或调用频率受限。" };
    }
    return { status: "error", message: `UN Comtrade 暂时无法验证（HTTP ${response.status}）。` };
  } catch (error) {
    return {
      status: "error",
      message: error instanceof Error && error.name === "AbortError"
        ? "连接 UN Comtrade 超时，请稍后重试。"
        : "无法连接 UN Comtrade，请检查本机网络后重试。",
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function testGoogleAdsKeywordPlannerCredential(values: Record<string, string>) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);
  try {
    const bridgeUrl = runtimeValue("LIGHTLINK_GOOGLE_API_BRIDGE_URL");
    const tokenUrl = bridgeUrl
      ? new URL("/oauth/token", bridgeUrl).toString()
      : "https://oauth2.googleapis.com/token";
    const tokenResponse = await fetch(tokenUrl, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: values.clientId ?? "",
        client_secret: values.clientSecret ?? "",
        refresh_token: values.refreshToken ?? "",
      }),
      signal: controller.signal,
    });
    const tokenPayload = asObject(await tokenResponse.json().catch(() => ({})));
    if (!tokenResponse.ok || typeof tokenPayload.access_token !== "string") {
      const oauthCode = String(tokenPayload.error ?? "");
      const oauthDescription = String(tokenPayload.error_description ?? "");
      const detail = [oauthCode, oauthDescription].filter(Boolean).join("：");
      if (tokenResponse.status === 502 || tokenResponse.status === 504) {
        return { status: "error", message: "本机 Google API 代理暂时无法连接上游，请确认 127.0.0.1:10808 代理正在运行后重试。" };
      }
      return {
        status: "error",
        message: detail
          ? `OAuth 验证失败（${detail.slice(0, 240)}）。请检查 Client ID、Client Secret 与 Refresh Token。`
          : `OAuth 验证失败（HTTP ${tokenResponse.status}）。请检查 OAuth 凭证。`,
      };
    }

    const customerId = String(values.customerId ?? "").replace(/\D/g, "");
    const loginCustomerId = String(values.loginCustomerId ?? "").replace(/\D/g, "");
    if (customerId.length !== 10) {
      return { status: "error", message: "OAuth 已通过，但 Google Ads Customer ID 必须是10位数字。" };
    }

    const headers: Record<string, string> = {
      authorization: `Bearer ${tokenPayload.access_token}`,
      "content-type": "application/json",
      accept: "application/json",
    };
    if (values.developerToken) headers["developer-token"] = values.developerToken;
    if (loginCustomerId) headers["login-customer-id"] = loginCustomerId;
    const plannerUrl = bridgeUrl
      ? (() => {
          const url = new URL("/ads/keyword-ideas", bridgeUrl);
          url.searchParams.set("customerId", customerId);
          return url.toString();
        })()
      : `https://googleads.googleapis.com/v25/customers/${customerId}:generateKeywordIdeas`;
    const plannerResponse = await fetch(
      plannerUrl,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          language: "languageConstants/1000",
          geoTargetConstants: ["geoTargetConstants/2840"],
          includeAdultKeywords: false,
          keywordPlanNetwork: "GOOGLE_SEARCH",
          keywordSeed: { keywords: ["wholesale products"] },
        }),
        signal: controller.signal,
      },
    );
    const plannerPayload = asObject(await plannerResponse.json().catch(() => ({})));
    if (plannerResponse.ok) {
      const results = Array.isArray(plannerPayload.results) ? plannerPayload.results : [];
      return {
        status: "ok",
        message: `连接成功：OAuth、客户账号与 Keyword Planner 权限均已通过，并返回 ${results.length} 条测试结果。`,
      };
    }
    if (plannerResponse.status === 429) {
      return { status: "rate_limited", message: "OAuth 已通过，但 Google Ads Keyword Planner 当前触发配额或频率限制。" };
    }
    const apiError = asObject(plannerPayload.error);
    const apiStatus = String(apiError.status ?? "");
    const apiMessage = String(apiError.message ?? "").slice(0, 260);
    if (plannerResponse.status === 401) {
      return { status: "error", message: "OAuth 已通过，但 Google Ads 拒绝认证。请重新授权 OAuth 并确认所用 Cloud 项目与 OAuth 客户端一致。" };
    }
    if (plannerResponse.status === 403) {
      const diagnostic = [apiStatus, apiMessage].filter(Boolean).join("：");
      return {
        status: "error",
        message: diagnostic
          ? `OAuth 已通过，但 Keyword Planner 权限不足（${diagnostic}）。请检查当前 Google Cloud 项目的 Ads API 访问级别与客户账号关系。`
          : "OAuth 已通过，但 Keyword Planner 权限不足。请检查当前 Google Cloud 项目的 Ads API 访问级别与客户账号关系。",
      };
    }
    return {
      status: "error",
      message: `OAuth 已通过，但 Keyword Planner 测试失败（HTTP ${plannerResponse.status}${apiStatus ? ` · ${apiStatus}` : ""}${apiMessage ? `：${apiMessage}` : ""}）。`,
    };
  } catch (error) {
    return {
      status: "error",
      message: error instanceof Error && error.name === "AbortError"
        ? "连接 Google Ads 超时，请稍后重试。"
        : "无法连接 Google Ads，请检查本机网络后重试。",
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function testManagedCredential(payload: JsonRecord) {
  const id = managedCredentialId(payload.provider);
  const definition = MANAGED_CREDENTIALS[id];
  if (!definition.testable && !definition.fields.length) throw new Error("该来源使用公开接口，无需配置凭证");
  const values = await readManagedCredential(id);
  if (!Object.keys(values).length) throw new Error("请先保存连接信息");
  const result = id === "un_comtrade"
    ? await testUnComtradeCredential(values.apiKey ?? "")
    : id === "google_ads_keyword_planner"
      ? await testGoogleAdsKeywordPlannerCredential(values)
      : {
          status: "unverified",
          message: `${definition.name} 的加密配置字段完整；该平台暂未提供安全的通用只读验证请求，凭证权限将在首次实际采集时确认。`,
        };
  const timestamp = nowIso();
  await getRawDb().prepare(
    `INSERT INTO user_settings (key, value, updated_at) VALUES (?, ?, ?)
     ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
  ).bind(credentialMetaKey(id), JSON.stringify({
    lastTestAt: timestamp,
    lastTestStatus: result.status,
    lastTestMessage: result.message,
  }), timestamp).run();
  return { provider: id, ...result, testedAt: timestamp };
}

function integrationStatuses() {
  return INTEGRATION_CATALOG.map((catalogItem) => {
    const { required, ...item } = catalogItem;
    const configuredGroups = "configuredGroups" in catalogItem ? catalogItem.configuredGroups : [required];
    return {
      ...item,
      publicMode: PUBLIC_ACCESS_NOTES[catalogItem.id] ?? null,
      configured: configuredGroups.some((group) => group.every((key) => Boolean(runtimeValue(key)))),
    };
  });
}

function extractResponseText(value: unknown) {
  const response = asObject(value);
  if (typeof response.output_text === "string") return response.output_text;
  const output = Array.isArray(response.output) ? response.output : [];
  for (const item of output) {
    const content = Array.isArray(asObject(item).content) ? asObject(item).content as unknown[] : [];
    for (const part of content) {
      const text = asObject(part).text;
      if (typeof text === "string" && text.trim()) return text;
    }
  }
  return "";
}

function languageForRequest(market: string, value: unknown) {
  const language = String(value ?? defaultLanguageForMarket(market)).trim().toLowerCase();
  if (!SUPPORTED_LANGUAGES.has(language)) throw new Error("暂不支持该语言");
  return language;
}

function normalizePlatform(value: unknown) {
  const platform = String(value ?? "").trim().toLocaleLowerCase("en-US");
  const aliases: Record<string, string> = {
    tiktok: "TikTok",
    "tik tok": "TikTok",
    facebook: "Meta Ads",
    meta: "Meta Ads",
    "meta ads": "Meta Ads",
    instagram: "Instagram",
    ig: "Instagram",
    ins: "Instagram",
    alibaba: "Alibaba.com",
    "alibaba.com": "Alibaba.com",
    "阿里国际站": "Alibaba.com",
    google: "Google Trends",
    "google trends": "Google Trends",
    trends: "Google Trends",
    "谷歌趋势": "Google Trends",
    amazon: "Amazon",
    "amazon.com": "Amazon",
    temu: "Temu",
    shein: "SHEIN",
    "希音": "SHEIN",
    ebay: "eBay",
    walmart: "Walmart",
    etsy: "Etsy",
    aliexpress: "AliExpress",
    "ali express": "AliExpress",
    shopee: "Shopee",
    lazada: "Lazada",
    "mercado libre": "Mercado Libre",
    mercadolibre: "Mercado Libre",
    rakuten: "Rakuten",
    "乐天": "Rakuten",
  };
  return aliases[platform] ?? "";
}

function safeImageUrl(value: unknown) {
  const candidate = String(value ?? "").trim();
  if (!candidate || candidate.length > 1000) return null;
  try {
    const url = new URL(candidate);
    if (!["http:", "https:"].includes(url.protocol)) return null;
    return candidate;
  } catch {
    return null;
  }
}

type ProductImageEvidence = {
  url: string;
  platform: string;
  source_ref: string;
  verified_source: boolean;
};

function imageUrlCandidates(value: unknown) {
  const values = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.split(/[|\n]+/)
      : value == null
        ? []
        : [value];
  const seen = new Set<string>();
  return values
    .map(safeImageUrl)
    .filter((url): url is string => {
      if (!url || seen.has(url)) return false;
      seen.add(url);
      return true;
    })
    .slice(0, 6);
}

function imagesForObservation(row: JsonRecord): ProductImageEvidence[] {
  const raw = jsonObject(row.raw_json);
  const candidates = [
    ...imageUrlCandidates(raw.imageUrls),
    ...imageUrlCandidates(raw.imageUrl),
    ...imageUrlCandidates(raw.thumbnailUrl),
    ...imageUrlCandidates(raw.productImageUrl),
  ];
  const sourceRef = String(row.source_ref ?? "");
  if (/\.(?:avif|gif|jpe?g|png|webp)(?:[?#].*)?$/i.test(sourceRef)) candidates.push(...imageUrlCandidates(sourceRef));
  const explicitSourceRef = safeImageUrl(raw.imageSourceRef);
  const fallbackSourceRef = safeImageUrl(sourceRef) ?? "";
  const seen = new Set<string>();
  return candidates.filter((url) => !seen.has(url) && seen.add(url)).slice(0, 6).map((url) => ({
    url,
    platform: String(row.platform ?? ""),
    source_ref: explicitSourceRef ?? fallbackSourceRef,
    verified_source: Boolean(explicitSourceRef),
  }));
}

function imagesByCluster(rows: JsonRecord[]) {
  const candidates = new Map<string, ProductImageEvidence[]>();
  const clustersByUrl = new Map<string, Set<string>>();
  for (const row of rows) {
    const clusterId = String(row.cluster_id ?? "");
    if (!clusterId) continue;
    const list = candidates.get(clusterId) ?? [];
    const existing = new Set(list.map((image) => image.url));
    for (const image of imagesForObservation(row)) {
      if (existing.has(image.url)) continue;
      list.push(image);
      existing.add(image.url);
      if (!clustersByUrl.has(image.url)) clustersByUrl.set(image.url, new Set());
      clustersByUrl.get(image.url)!.add(clusterId);
    }
    candidates.set(clusterId, list);
  }
  return new Map([...candidates].map(([clusterId, images]) => [
    clusterId,
    images.filter((image) => clustersByUrl.get(image.url)?.size === 1).slice(0, 6),
  ]));
}

function keywordZhByCluster(rows: JsonRecord[]) {
  const translations = new Map<string, string>();
  for (const row of rows) {
    const clusterId = String(row.cluster_id ?? "");
    const raw = jsonObject(row.raw_json);
    const keywordZh = String(raw.keywordZh ?? raw.chineseName ?? "").trim().slice(0, 120);
    if (clusterId && keywordZh && !translations.has(clusterId)) translations.set(clusterId, keywordZh);
  }
  return translations;
}

function purchasePricesByCluster(rows: JsonRecord[]) {
  const prices = new Map<string, { min: number; max: number; currency: string; unit: string }>();
  for (const row of rows) {
    const clusterId = String(row.cluster_id ?? "");
    const raw = jsonObject(row.raw_json);
    if (raw.purchasePriceMin == null || raw.purchasePriceMax == null || raw.purchasePriceMin === "" || raw.purchasePriceMax === "") continue;
    const min = Number(raw.purchasePriceMin);
    const max = Number(raw.purchasePriceMax);
    const currency = String(raw.purchasePriceCurrency ?? "").trim().toUpperCase();
    const unit = String(raw.purchasePriceUnit ?? "").trim();
    if (clusterId && !prices.has(clusterId) && Number.isFinite(min) && Number.isFinite(max) && min >= 0 && max >= min && /^[A-Z]{3}$/.test(currency)) {
      prices.set(clusterId, { min, max, currency, unit });
    }
  }
  return prices;
}

function geoScopesByCluster(rows: JsonRecord[]) {
  const scopes = new Map<string, Set<string>>();
  for (const row of rows) {
    const clusterId = String(row.cluster_id ?? "");
    const geoScope = String(row.geo_scope ?? "").trim().toUpperCase();
    if (!clusterId || !geoScope) continue;
    if (!scopes.has(clusterId)) scopes.set(clusterId, new Set());
    scopes.get(clusterId)!.add(geoScope);
  }
  return new Map([...scopes].map(([clusterId, values]) => [clusterId, [...values]]));
}

function validateObservation(value: unknown): IncomingObservation {
  const row = asObject(value);
  const keyword = normalizeKeyword(String(row.keyword ?? ""));
  const platform = normalizePlatform(row.platform);
  const metric = String(row.metric ?? "").trim().toLocaleLowerCase("en-US");
  const status = String(row.status ?? "ok").trim().toLocaleLowerCase("en-US");
  const sourceKind = String(row.sourceKind ?? "manual_import").trim().toLocaleLowerCase("en-US");
  const validMetrics = ["attention", "commercial", "competition"];
  const validStatuses = ["ok", "confirmed_zero", "unsupported", "auth_failed", "rate_limited", "collection_error", "geo_unavailable"];
  const validSourceKinds = ["official_api", "official_export", "browser_sample", "open_source", "manual_import", "assistant", "demo"];

  if (!keyword) throw new Error("每行都需要 keyword");
  if (!platform) throw new Error(`“${keyword}”的 platform 不受支持；请使用数据源页列出的平台名称`);
  if (!validMetrics.includes(metric)) throw new Error(`“${keyword}”的 metric 必须是 attention、commercial 或 competition`);
  if (!validStatuses.includes(status)) throw new Error(`“${keyword}”的数据状态无效`);
  if (!validSourceKinds.includes(sourceKind)) throw new Error(`“${keyword}”的来源类型无效`);

  const numeric = (candidate: unknown) => {
    if (candidate === null || candidate === undefined || candidate === "") return null;
    if (typeof candidate === "boolean" || typeof candidate === "object") throw new Error(`“${keyword}”包含无效数值`);
    if (typeof candidate === "string" && !candidate.trim()) return null;
    const parsed = Number(candidate);
    if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`“${keyword}”包含无效数值`);
    return parsed;
  };

  const currentValue = numeric(row.currentValue);
  if (status === "ok" && currentValue === null) throw new Error(`“${keyword}”状态为 ok 时必须提供 currentValue`);
  if (status === "confirmed_zero" && currentValue !== 0) throw new Error(`“${keyword}”状态为 confirmed_zero 时 currentValue 必须为 0`);
  if (!["ok", "confirmed_zero"].includes(status) && currentValue !== null) {
    throw new Error(`“${keyword}”采集失败或不可用时 currentValue 必须留空`);
  }

  const coverageDays = Number(row.coverageDays ?? 30);
  if (!Number.isFinite(coverageDays) || coverageDays < 1 || coverageDays > 365) throw new Error(`“${keyword}”的 coverageDays 无效`);
  const collectedAt = String(row.collectedAt ?? nowIso()).trim();
  if (!collectedAt || !Number.isFinite(new Date(collectedAt).getTime())) throw new Error(`“${keyword}”的 collectedAt 无效`);
  if (new Date(collectedAt).getTime() > Date.now() + 300_000) throw new Error(`“${keyword}”的 collectedAt 不能晚于当前时间`);
  const missingReason = row.missingReason == null ? null : String(row.missingReason).trim() || null;
  if (!["ok", "confirmed_zero"].includes(status) && !missingReason) throw new Error(`“${keyword}”采集失败或不可用时需要 missingReason`);
  const aliases = Array.isArray(row.aliases)
    ? row.aliases.map(String)
    : typeof row.aliases === "string"
      ? row.aliases.split(/[|;；]+/)
      : [];
  const raw = asObject(row.raw);
  const legacyImageCandidate = row.imageUrl ?? raw.imageUrl ?? raw.thumbnailUrl ?? raw.productImageUrl;
  const legacyImageUrl = legacyImageCandidate == null || legacyImageCandidate === "" ? null : safeImageUrl(legacyImageCandidate);
  if (legacyImageCandidate != null && legacyImageCandidate !== "" && !legacyImageUrl) throw new Error(`“${keyword}”的 imageUrl 必须是 http 或 https 图片链接`);
  const suppliedImageUrls = row.imageUrls ?? raw.imageUrls;
  const imageUrls = imageUrlCandidates(suppliedImageUrls);
  const suppliedImageCount = Array.isArray(suppliedImageUrls)
    ? suppliedImageUrls.length
    : typeof suppliedImageUrls === "string" && suppliedImageUrls.trim()
      ? suppliedImageUrls.split(/[|\n]+/).length
      : 0;
  if (suppliedImageCount > 6) throw new Error(`“${keyword}”最多可提供 6 张产品图片`);
  if (suppliedImageCount && imageUrls.length !== suppliedImageCount) throw new Error(`“${keyword}”的 imageUrls 必须全部是 http 或 https 图片链接`);
  const imageSourceCandidate = row.imageSourceRef ?? raw.imageSourceRef;
  const imageSourceRef = imageSourceCandidate == null || imageSourceCandidate === "" ? null : safeImageUrl(imageSourceCandidate);
  if (imageSourceCandidate != null && imageSourceCandidate !== "" && !imageSourceRef) throw new Error(`“${keyword}”的 imageSourceRef 必须是 http 或 https 商品来源链接`);
  if (imageUrls.length && !imageSourceRef) throw new Error(`“${keyword}”提供多张图片时必须填写 imageSourceRef，说明图片来自哪个商品页或 API`);
  const keywordZh = String(row.keywordZh ?? raw.keywordZh ?? raw.chineseName ?? "").trim();
  if (keywordZh.length > 120) throw new Error(`“${keyword}”的 keywordZh 不能超过 120 个字符`);
  const purchasePriceMin = numeric(row.purchasePriceMin ?? raw.purchasePriceMin);
  const purchasePriceMax = numeric(row.purchasePriceMax ?? raw.purchasePriceMax);
  const purchasePriceCurrency = String(row.purchasePriceCurrency ?? raw.purchasePriceCurrency ?? "").trim().toUpperCase();
  const purchasePriceUnit = String(row.purchasePriceUnit ?? raw.purchasePriceUnit ?? "").trim();
  const hasPurchasePrice = purchasePriceMin !== null || purchasePriceMax !== null || Boolean(purchasePriceCurrency || purchasePriceUnit);
  if (hasPurchasePrice && (purchasePriceMin === null || purchasePriceMax === null || !/^[A-Z]{3}$/.test(purchasePriceCurrency))) {
    throw new Error(`“${keyword}”的采购价需要同时提供最低价、最高价和三位币种代码`);
  }
  if (purchasePriceMin !== null && purchasePriceMax !== null && purchasePriceMax < purchasePriceMin) {
    throw new Error(`“${keyword}”的采购最高价不能低于最低价`);
  }
  if (purchasePriceUnit.length > 40) throw new Error(`“${keyword}”的采购价单位不能超过 40 个字符`);

  const geoScope = String(row.geoScope ?? "GLOBAL").trim().toUpperCase() || "GLOBAL";
  if (!SUPPORTED_MARKETS.has(geoScope)) throw new Error(`“${keyword}”的数据国家 ${geoScope} 不受支持`);

  const sampleN = numeric(row.sampleN);
  const uniqueActorN = numeric(row.uniqueActorN);
  if ((sampleN !== null && !Number.isInteger(sampleN)) || (uniqueActorN !== null && !Number.isInteger(uniqueActorN))) {
    throw new Error(`“${keyword}”的 sampleN 和 uniqueActorN 必须是整数`);
  }

  return {
    keyword,
    groupName: String(row.groupName ?? keyword).trim(),
    aliases: aliases.map(normalizeKeyword).filter(Boolean),
    category: String(row.category ?? "未分类"),
    platform,
    metric: metric as IncomingObservation["metric"],
    currentValue,
    previousValue: numeric(row.previousValue),
    sampleN,
    uniqueActorN,
    coverageDays: Math.round(coverageDays),
    sourceKind: sourceKind as IncomingObservation["sourceKind"],
    sourceRef: String(row.sourceRef ?? ""),
    geoScope,
    status: status as IncomingObservation["status"],
    missingReason,
    collectedAt,
    raw: {
      ...raw,
      ...(legacyImageUrl ? { imageUrl: legacyImageUrl } : {}),
      ...(imageUrls.length ? { imageUrls, imageSourceRef } : {}),
      ...(keywordZh ? { keywordZh } : {}),
      ...(hasPurchasePrice ? { purchasePriceMin, purchasePriceMax, purchasePriceCurrency, purchasePriceUnit } : {}),
    },
  };
}

async function researchDashboard() {
  await ensureResearchSchema();
  const db = getRawDb();
  const [rows, buyerLibrary] = await Promise.all([
    db.prepare(
      `SELECT p.*,
              (SELECT COUNT(*) FROM research_runs r WHERE r.project_id = p.id) AS run_count,
              (SELECT COUNT(*) FROM research_evidence e WHERE e.project_id = p.id) AS evidence_count,
              (SELECT r.id FROM research_runs r WHERE r.project_id = p.id ORDER BY r.created_at DESC LIMIT 1) AS latest_run_id,
              (SELECT r.status FROM research_runs r WHERE r.project_id = p.id ORDER BY r.created_at DESC LIMIT 1) AS latest_run_status,
              (SELECT COUNT(*) FROM research_candidates c WHERE c.project_id = p.id) AS candidate_count
         FROM research_projects p
        ORDER BY CASE WHEN p.status = 'archived' THEN 1 ELSE 0 END, p.updated_at DESC`,
    ).all<JsonRecord>(),
    readGlobalBuyerLibrary(),
  ]);
  return {
    projects: rows.results.map(parseResearchProject),
    templates: RESEARCH_TEMPLATES,
    sections: RESEARCH_SECTIONS,
    buyerLibrary,
  };
}

async function taskCenter() {
  await ensureResearchSchema();
  const db = getRawDb();
  const [scanRows, researchRows, personaRows, tradeRows, validationRows] = await Promise.all([
    db.prepare(`SELECT r.id, r.mode, r.query, r.status, r.created_at, r.completed_at,
                       r.source_summary,
                       (SELECT COUNT(*) FROM observations o WHERE o.run_id = r.id) AS result_count
                  FROM scan_runs r
                 ORDER BY r.created_at DESC LIMIT 200`).all<JsonRecord>(),
    db.prepare(`SELECT r.id, r.project_id, r.status, r.request_payload, r.result_payload,
                       r.source_summary, r.created_at, r.completed_at,
                       p.product_name, p.product_category
                  FROM research_runs r
                  JOIN research_projects p ON p.id = r.project_id
                 ORDER BY r.created_at DESC LIMIT 200`).all<JsonRecord>(),
    db.prepare(`SELECT run_id AS id,
                       MIN(mode) AS mode,
                       MIN(target_code) AS target_code,
                       CASE WHEN SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) > 0 THEN 'review' ELSE 'completed' END AS status,
                       MIN(created_at) AS created_at,
                       MAX(reviewed_at) AS completed_at,
                       COUNT(*) AS result_count,
                       SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count
                  FROM buyer_persona_ai_proposals
                 GROUP BY run_id
                 ORDER BY MIN(created_at) DESC LIMIT 200`).all<JsonRecord>(),
    db.prepare(`SELECT r.id, r.opportunity_id, r.status, r.collection_level, r.trigger_reason,
                       r.error, r.created_at, r.completed_at, c.title, f.name AS product_family_name
                  FROM trade_data_refresh_requests r
                  JOIN opportunity_cases c ON c.id = r.opportunity_id
                  LEFT JOIN product_family_master f ON f.code = r.product_family_code
                 ORDER BY r.created_at DESC LIMIT 200`).all<JsonRecord>(),
    db.prepare(`SELECT r.id, r.opportunity_id, r.status, r.trigger_reason, r.summary,
                       r.suggested_next_action, r.error, r.created_at, r.completed_at,
                       c.title, f.name AS product_family_name
                  FROM opportunity_validation_requests r
                  JOIN opportunity_cases c ON c.id = r.opportunity_id
                  LEFT JOIN product_family_master f ON f.code = c.product_family_code
                 ORDER BY r.created_at DESC LIMIT 200`).all<JsonRecord>(),
  ]);

  const items = [
    ...scanRows.results.map((row) => ({
      id: String(row.id), module: "discovery", task_type: "radar", task_label: row.mode === "discover" ? "热点发现" : "关键词扫描",
      title: String(row.query || "未命名扫描"), subtitle: "产品机会工作台", status: String(row.status || "waiting_for_data"),
      progress: null, result_count: Number(row.result_count || 0), target_id: String(row.id),
      created_at: String(row.created_at || ""), completed_at: row.completed_at ? String(row.completed_at) : null,
      error: String(asObject(row.source_summary).error || ""),
    })),
    ...researchRows.results.map((row) => {
      const requestPayload = asObject(row.request_payload);
      const resultPayload = asObject(row.result_payload);
      const sourceSummary = asObject(row.source_summary);
      return {
        id: String(row.id), module: "research", task_type: "research", task_label: requestPayload.runMode === "review" ? "项目复查" : "产品与市场调研",
        title: String(row.product_name || "未命名调研"), subtitle: String(row.product_category || "长期调研项目"), status: String(row.status || "waiting_for_codex"),
        progress: null, result_count: Array.isArray(resultPayload.candidates) ? resultPayload.candidates.length : Number(sourceSummary.candidateCount || 0),
        target_id: String(row.project_id), created_at: String(row.created_at || ""), completed_at: row.completed_at ? String(row.completed_at) : null,
        error: String(sourceSummary.error || ""),
      };
    }),
    ...personaRows.results.map((row) => ({
      id: String(row.id), module: "personas", task_type: "taxonomy_assist", task_label: row.mode === "enrich" ? "画像复核" : "画像补充",
      title: row.target_code ? `买家画像 · ${String(row.target_code)}` : "全球买家画像分类", subtitle: `${Number(row.result_count || 0)} 条 AI 建议`,
      status: String(row.status || "review"), progress: null, result_count: Number(row.result_count || 0), target_id: String(row.target_code || ""),
      created_at: String(row.created_at || ""), completed_at: row.completed_at ? String(row.completed_at) : null, error: "",
    })),
    ...tradeRows.results.map((row) => ({
      id: String(row.id), module: "opportunities", task_type: "trade_data", task_label: "贸易数据采集",
      title: String(row.title || row.product_family_name || "商机贸易数据"), subtitle: `${String(row.product_family_name || "产品家族")} · ${String(row.collection_level || "baseline")}`,
      status: String(row.status || "pending"), progress: null, result_count: 0, target_id: String(row.opportunity_id),
      created_at: String(row.created_at || ""), completed_at: row.completed_at ? String(row.completed_at) : null, error: String(row.error || ""),
    })),
    ...validationRows.results.map((row) => ({
      id: String(row.id), module: "opportunities", task_type: "opportunity_validation", task_label: "商机公开证据验证",
      title: String(row.title || row.product_family_name || "商机验证"), subtitle: String(row.summary || row.suggested_next_action || "公开证据与真实买家线索"),
      status: String(row.status || "pending"), progress: null, result_count: row.summary ? 1 : 0, target_id: String(row.opportunity_id),
      created_at: String(row.created_at || ""), completed_at: row.completed_at ? String(row.completed_at) : null, error: String(row.error || ""),
    })),
  ].sort((left, right) => right.created_at.localeCompare(left.created_at));

  return {
    items,
    stats: {
      total: items.length,
      pending: items.filter((item) => ["pending", "waiting_for_codex", "waiting_for_data", "queued", "researching"].includes(item.status)).length,
      review: items.filter((item) => ["review", "partial"].includes(item.status)).length,
      failed: items.filter((item) => item.status === "failed").length,
    },
  };
}

async function researchProjectDetail(projectIdValue: unknown) {
  await ensureResearchSchema();
  const projectId = String(projectIdValue ?? "").trim();
  if (!projectId) throw new Error("缺少调研项目编号");
  const db = getRawDb();
  const project = await db.prepare(
    `SELECT p.*,
            (SELECT COUNT(*) FROM research_runs r WHERE r.project_id = p.id) AS run_count,
            (SELECT COUNT(*) FROM research_evidence e WHERE e.project_id = p.id) AS evidence_count,
            (SELECT COUNT(*) FROM research_candidates c WHERE c.project_id = p.id) AS candidate_count
       FROM research_projects p
      WHERE p.id = ?`,
  ).bind(projectId).first<JsonRecord>();
  if (!project) throw new Error("没有找到该调研项目");
  const [runs, evidence, candidates, activities, marketActivities, buyerProfiles, buyerFamilyLinks] = await Promise.all([
    db.prepare("SELECT * FROM research_runs WHERE project_id = ? ORDER BY created_at DESC LIMIT 50").bind(projectId).all<JsonRecord>(),
    db.prepare("SELECT * FROM research_evidence WHERE project_id = ? ORDER BY captured_at DESC LIMIT 500").bind(projectId).all<JsonRecord>(),
    db.prepare("SELECT * FROM research_candidates WHERE project_id = ? ORDER BY CASE stage WHEN 'validated' THEN 0 WHEN 'shortlist' THEN 1 WHEN 'validation' THEN 2 WHEN 'sample' THEN 3 WHEN 'research' THEN 4 WHEN 'idea' THEN 5 ELSE 6 END, score DESC, updated_at DESC LIMIT 2500").bind(projectId).all<JsonRecord>(),
    db.prepare("SELECT * FROM research_candidate_activities WHERE project_id = ? ORDER BY created_at DESC LIMIT 5000").bind(projectId).all<JsonRecord>(),
    db.prepare("SELECT * FROM research_market_activities WHERE project_id = ? ORDER BY created_at DESC LIMIT 1000").bind(projectId).all<JsonRecord>(),
    db.prepare("SELECT * FROM research_buyer_profiles WHERE project_id = ? ORDER BY CASE profile_status WHEN 'validated' THEN 0 WHEN 'qualified' THEN 1 WHEN 'hypothesis' THEN 2 ELSE 3 END, updated_at DESC LIMIT 1000").bind(projectId).all<JsonRecord>(),
    db.prepare("SELECT * FROM research_buyer_family_links WHERE project_id = ? ORDER BY relationship_score DESC, updated_at DESC LIMIT 5000").bind(projectId).all<JsonRecord>(),
  ]);
  return {
    project: parseResearchProject(project),
    runs: runs.results.map((row) => ({
      ...row,
      request_payload: jsonObject(row.request_payload),
      result_payload: jsonObject(row.result_payload),
      source_summary: jsonObject(row.source_summary),
    })),
    evidence: evidence.results.map((row) => ({ ...row, metrics: jsonObject(row.metrics) })),
    candidates: candidates.results.map(parseResearchCandidate),
    activities: activities.results,
    marketActivities: marketActivities.results,
    buyerProfiles: buyerProfiles.results.map(parseResearchBuyerProfile),
    buyerFamilyLinks: buyerFamilyLinks.results.map(parseResearchBuyerFamilyLink),
    templates: RESEARCH_TEMPLATES,
    sections: RESEARCH_SECTIONS,
  };
}

async function createResearchProject(payload: JsonRecord) {
  await ensureResearchSchema();
  const productName = String(payload.productName ?? "").trim();
  if (productName.length < 2 || productName.length > 120) throw new Error("产品名称需为 2–120 个字符");
  const templateId = String(payload.templateId ?? "general_validation");
  if (!RESEARCH_TEMPLATES.some((item) => item.id === templateId)) throw new Error("调研模板无效");
  const targetMarkets = stringList(payload.targetMarkets)
    .map((item) => item.toUpperCase())
    .filter((item) => item === "GLOBAL" || SUPPORTED_MARKETS.has(item));
  const languages = stringList(payload.languages)
    .map((item) => item.toLowerCase())
    .filter((item) => SUPPORTED_LANGUAGES.has(item));
  const channels = stringList(payload.channels).filter((item) => RESEARCH_CHANNELS.has(item));
  const normalizedMarkets = targetMarkets.length ? targetMarkets : ["GLOBAL"];
  const normalizedLanguages = languages.length ? languages : ["en"];
  const normalizedChannels = channels.length
    ? channels
    : ["google_trends", "alibaba", "official_regulation", "buyer_websites"];
  const targetCandidateCount = payload.targetCandidateCount === undefined ? 2000 : Number(payload.targetCandidateCount);
  if (!Number.isInteger(targetCandidateCount) || targetCandidateCount < 1 || targetCandidateCount > 2000) {
    throw new Error("候选产品目标数量必须是 1–2000 的整数");
  }
  const id = crypto.randomUUID();
  const timestamp = nowIso();
  const db = getRawDb();
  await db.prepare(
    `INSERT INTO research_projects
      (id, product_name, product_category, product_description, target_markets, languages,
       channels, template_id, target_candidate_count, objectives, constraints, status, current_stage, progress,
       summary, recommendation, scorecard, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planning', 'product_definition', 10, '', 'pending', '{}', ?, ?)`,
  ).bind(
    id,
    productName,
    String(payload.productCategory ?? "").trim().slice(0, 120),
    String(payload.productDescription ?? "").trim().slice(0, 2000),
    JSON.stringify(normalizedMarkets),
    JSON.stringify(normalizedLanguages),
    JSON.stringify(normalizedChannels),
    templateId,
    targetCandidateCount,
    String(payload.objectives ?? "验证需求、竞争、采购可行性与市场进入路径").trim().slice(0, 6000),
    String(payload.constraints ?? "").trim().slice(0, 2000),
    timestamp,
    timestamp,
  ).run();
  return researchProjectDetail(id);
}

async function createResearchRun(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  if (!projectId) throw new Error("缺少调研项目编号");
  const db = getRawDb();
  const project = await db.prepare("SELECT * FROM research_projects WHERE id = ?").bind(projectId).first<JsonRecord>();
  if (!project) throw new Error("没有找到该调研项目");
  if (String(project.status) === "archived") throw new Error("已归档项目不能发起调研，请先恢复项目");
  const active = await db.prepare(
    "SELECT id FROM research_runs WHERE project_id = ? AND status IN ('waiting_for_codex', 'researching') ORDER BY created_at DESC LIMIT 1",
  ).bind(projectId).first<{ id: string }>();
  if (active) throw new Error("该项目已有一项调研正在执行");
  const candidateTotal = await db.prepare(
    "SELECT COUNT(*) AS total FROM research_candidates WHERE project_id = ?",
  ).bind(projectId).first<{ total: number }>();
  const requestedTarget = payload.targetCandidateCount === undefined
    ? Number(project.target_candidate_count) || 2000
    : Number(payload.targetCandidateCount);
  if (!Number.isInteger(requestedTarget) || requestedTarget < 1 || requestedTarget > 2000) {
    throw new Error("候选产品目标数量必须是 1–2000 的整数");
  }
  const targetCandidateCount = Math.max(Number(candidateTotal?.total ?? 0), requestedTarget);
  const candidateCount = Number(candidateTotal?.total ?? 0);
  const runMode = payload.runMode === "expand_candidates" ? "expand_candidates" : "review";
  const requestedCandidateCount = runMode === "expand_candidates"
    ? Number(payload.requestedCandidateCount ?? Math.min(100, Math.max(1, targetCandidateCount - candidateCount)))
    : 0;
  if (runMode === "expand_candidates" && candidateCount >= targetCandidateCount) {
    throw new Error("候选产品池已达到项目目标，请先提高目标数量");
  }
  if (runMode === "expand_candidates" && (!Number.isInteger(requestedCandidateCount) || requestedCandidateCount < 1 || requestedCandidateCount > 300)) {
    throw new Error("本轮新增数量必须是 1–300 的整数");
  }
  const buyerLibrary = await readGlobalBuyerLibrary();
  const matchedBuyerKnowledge = buildProjectBuyerKnowledge({
    profiles: buyerLibrary.profiles.map((item) => ({
      id: String(item.id),
      company_name: String(item.company_name),
      country: String(item.country),
      buyer_type: String(item.buyer_type),
      customer_groups: stringList(item.customer_groups, 50),
      sales_channels: stringList(item.sales_channels, 30),
      purchasing_scenarios: stringList(item.purchasing_scenarios, 50),
      seasonality: String(item.seasonality ?? ""),
      replenishment_cycle: String(item.replenishment_cycle ?? ""),
      order_requirements: String(item.order_requirements ?? ""),
      source_url: String(item.source_url ?? ""),
      profile_status: String(item.profile_status ?? "hypothesis"),
    })),
    links: buyerLibrary.links.map((item) => ({
      buyer_profile_id: String(item.buyer_profile_id),
      track_category: String(item.track_category),
      product_family: String(item.product_family),
      relationship_score: Number(item.relationship_score ?? 0),
      family_role: String(item.family_role ?? "test"),
      sales_scenarios: stringList(item.sales_scenarios, 50),
      rationale: String(item.rationale ?? ""),
      evidence_status: String(item.evidence_status ?? "hypothesis"),
    })),
    targetMarkets: stringList(project.target_markets),
    productCategory: String(project.product_category),
    productDescription: String(project.product_description),
    objectives: String(project.objectives),
    limit: stringList(project.target_markets).includes("GLOBAL") ? 18 : 12,
  });
  const targetMarkets = stringList(project.target_markets).map((item) => item.toUpperCase());
  const targetRegionCodes = new Set<string>(["GLOBAL"]);
  for (const region of buyerLibrary.taxonomy.regions) {
    if (targetMarkets.includes("GLOBAL") || region.countries.some((country) => targetMarkets.includes(country))) targetRegionCodes.add(region.code);
  }
  const researchTerms = [...new Set([String(project.product_category), String(project.product_description), String(project.objectives)]
    .flatMap((value) => value.toLocaleLowerCase().split(/[\s,，、/;；|]+/)).map((value) => value.trim()).filter((value) => value.length >= 2))].slice(0, 30);
  const trackScore = new Map<string, number>();
  for (const track of buyerLibrary.taxonomy.productTracks) {
    const haystack = `${track.name} ${track.description} ${track.buyer_value} ${track.compliance_focus.join(" ")}`.toLocaleLowerCase();
    trackScore.set(track.code, researchTerms.filter((term) => haystack.includes(term)).length * 20);
  }
  for (const profile of buyerLibrary.profiles) {
    if (matchedBuyerKnowledge.profiles.some((item) => item.id === profile.id) && profile.persona_code) {
      for (const link of buyerLibrary.taxonomy.personaMatrix.filter((item) => item.persona_code === profile.persona_code && targetRegionCodes.has(item.region_code))) {
        trackScore.set(link.track_code, (trackScore.get(link.track_code) ?? 0) + link.relevance_score / 10);
      }
    }
  }
  const selectedTrackCodes = new Set([...buyerLibrary.taxonomy.productTracks]
    .sort((a, b) => (trackScore.get(b.code) ?? 0) - (trackScore.get(a.code) ?? 0) || a.name.localeCompare(b.name, "zh-CN"))
    .slice(0, 10).map((item) => item.code));
  const personaCodesFromProfiles = new Set(buyerLibrary.profiles
    .filter((profile) => matchedBuyerKnowledge.profiles.some((item) => item.id === profile.id))
    .map((profile) => profile.persona_code).filter(Boolean));
  const selectedMatrix = buyerLibrary.taxonomy.personaMatrix
    .filter((item) => targetRegionCodes.has(item.region_code) && selectedTrackCodes.has(item.track_code))
    .sort((a, b) => Number(b.relevance_score) - Number(a.relevance_score)).slice(0, 36);
  for (const item of selectedMatrix.slice(0, 16)) personaCodesFromProfiles.add(item.persona_code);
  const globalBuyerKnowledge = {
    ...matchedBuyerKnowledge,
    taxonomy: {
      regions: buyerLibrary.taxonomy.regions.filter((item) => targetRegionCodes.has(item.code)).map((item) => ({
        code: item.code, name: item.name, countries: item.countries, characteristics: item.characteristics,
      })),
      personaCategories: buyerLibrary.taxonomy.personaCategories.filter((item) => personaCodesFromProfiles.has(item.code)).slice(0, 12).map((item) => ({
        code: item.code, name: item.name, groupName: item.group_name, valueChainRole: item.value_chain_role,
        purchaseScenarios: item.purchase_scenarios, buyingTriggers: item.buying_triggers, orderCharacteristics: item.order_characteristics,
      })),
      productTracks: buyerLibrary.taxonomy.productTracks.filter((item) => selectedTrackCodes.has(item.code)).map((item) => ({
        code: item.code, name: item.name, buyerValue: item.buyer_value, complianceFocus: item.compliance_focus,
      })),
      productFamilies: buyerLibrary.taxonomy.productFamilies.filter((item) => selectedTrackCodes.has(item.track_code)).slice(0, 40).map((item) => ({
        code: item.code, trackCode: item.track_code, name: item.name, useScenarios: item.use_scenarios, complianceTags: item.compliance_tags,
      })),
      personaMatrix: selectedMatrix.map((item) => ({
        personaCode: item.persona_code, regionCode: item.region_code, trackCode: item.track_code,
        productFamilyCode: item.product_family_code, relevanceScore: item.relevance_score,
        familyRole: item.family_role, evidenceStatus: item.evidence_status,
      })),
    },
  };
  const runId = crypto.randomUUID();
  const timestamp = nowIso();
  const requestPayload = {
    productName: String(project.product_name),
    productCategory: String(project.product_category),
    productDescription: String(project.product_description),
    targetMarkets: stringList(project.target_markets),
    languages: stringList(project.languages),
    channels: stringList(project.channels),
    templateId: String(project.template_id),
    objectives: String(project.objectives),
    constraints: String(project.constraints),
    sections: RESEARCH_SECTIONS,
    candidateCount,
    targetCandidateCount,
    runMode,
    requestedCandidateCount,
    requestNote: String(payload.requestNote ?? "").trim().slice(0, 2000),
    globalBuyerKnowledge,
  };
  await db.batch([
    db.prepare(
      `INSERT INTO research_runs (id, project_id, status, request_payload, result_payload, source_summary, created_at)
       VALUES (?, ?, 'waiting_for_codex', ?, '{}', '{}', ?)`,
    ).bind(runId, projectId, JSON.stringify(requestPayload), timestamp),
    db.prepare(
      "UPDATE research_projects SET status = 'queued', current_stage = 'product_definition', progress = 15, target_candidate_count = ?, updated_at = ? WHERE id = ?",
    ).bind(targetCandidateCount, timestamp, projectId),
  ]);
  return { projectId, runId, status: "waiting_for_codex", dispatchTask: requestPayload };
}

async function importResearchResult(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const runId = String(payload.researchRunId ?? payload.runId ?? "").trim();
  if (!projectId || !runId) throw new Error("缺少调研项目或运行编号");
  const db = getRawDb();
  const run = await db.prepare("SELECT * FROM research_runs WHERE id = ? AND project_id = ?").bind(runId, projectId).first<JsonRecord>();
  if (!run) throw new Error("没有找到待写回的调研任务");
  const previousRun = await db.prepare(
    `SELECT result_payload
       FROM research_runs
      WHERE project_id = ? AND id != ? AND status IN ('complete', 'partial')
      ORDER BY COALESCE(completed_at, created_at) DESC
      LIMIT 1`,
  ).bind(projectId, runId).first<JsonRecord>();
  const previousReport = jsonObject(previousRun?.result_payload);
  const report = asObject(payload.report ?? payload.result ?? payload);
  const summary = String(report.summary ?? "").trim();
  if (summary.length < 10) throw new Error("调研摘要过短，无法形成可复用报告");
  const status = report.status === "partial" ? "partial" : "complete";
  const recommendation = ["go", "test", "hold", "reject"].includes(String(report.recommendation))
    ? String(report.recommendation)
    : "test";
  const rawScorecard = asObject(report.scorecard);
  const scorecard = {
    complianceSafety: boundedNumber(rawScorecard.complianceSafety, 0, 25),
    marketBuyer: boundedNumber(rawScorecard.marketBuyer, 0, 20),
    unitEconomics: boundedNumber(rawScorecard.unitEconomics, 0, 20),
    supplyStability: boundedNumber(rawScorecard.supplyStability, 0, 20),
    salesExpression: boundedNumber(rawScorecard.salesExpression, 0, 15),
  };
  const scoreTotal = Object.values(scorecard).reduce((sum, value) => sum + value, 0);
  const trackCategories = (Array.isArray(report.trackCategories) ? report.trackCategories : [])
    .slice(0, 100)
    .map((value, index) => {
      const item = asObject(value);
      const priority = ["high", "medium", "low"].includes(String(item.priority)) ? String(item.priority) : "medium";
      const evidenceStatus = ["hypothesis", "partial", "validated"].includes(String(item.evidenceStatus))
        ? String(item.evidenceStatus)
        : "hypothesis";
      return {
        id: reportText(item.id || `track-${index + 1}`, 80),
        name: reportText(item.name, 120),
        description: reportText(item.description, 1200),
        subcategories: stringList(item.subcategories, 100).map((entry) => entry.slice(0, 120)),
        targetMarkets: stringList(item.targetMarkets, 100).map((entry) => entry.toUpperCase().slice(0, 40)),
        buyerTypes: stringList(item.buyerTypes, 50).map((entry) => entry.slice(0, 160)),
        priority,
        opportunityScore: boundedOptionalNumber(item.opportunityScore, 0, 100),
        evidenceStatus,
      };
    })
    .filter((item) => item.name);
  const productPool = (Array.isArray(report.productPool) ? report.productPool : [])
    .slice(0, 1000)
    .map((value, index) => {
      const item = asObject(value);
      const riskLevel = ["low", "medium", "high", "unknown"].includes(String(item.riskLevel))
        ? String(item.riskLevel)
        : "unknown";
      const stage = ["idea", "research", "sample", "validation", "shortlist", "validated", "rejected"].includes(String(item.stage))
        ? String(item.stage)
        : "idea";
      const evidenceStatus = ["hypothesis", "partial", "validated"].includes(String(item.evidenceStatus))
        ? String(item.evidenceStatus)
        : "hypothesis";
      return {
        id: reportText(item.id || `candidate-${index + 1}`, 80),
        name: reportText(item.name, 160),
        trackCategory: reportText(item.trackCategory, 120),
        subcategory: reportText(item.subcategory, 120),
        productFamily: reportText(item.productFamily || item.subcategory, 120),
        commercialVariant: reportText(item.commercialVariant, 160),
        imageUrls: imageUrlCandidates(item.imageUrls ?? item.imageUrl),
        imageSourceRef: safeImageUrl(item.imageSourceRef) ?? "",
        targetMarkets: stringList(item.targetMarkets, 100).map((entry) => entry.toUpperCase().slice(0, 40)),
        buyerTypes: stringList(item.buyerTypes, 50).map((entry) => entry.slice(0, 160)),
        priceBand: reportText(item.priceBand, 160),
        moq: reportText(item.moq, 120),
        compliance: stringList(item.compliance, 50).map((entry) => entry.slice(0, 160)),
        riskLevel,
        stage,
        score: boundedOptionalNumber(item.score, 0, 100),
        rationale: reportText(item.rationale, 1200),
        evidenceStatus,
      };
    })
    .filter((item) => item.name);
  const usedProductImageUrls = new Set<string>();
  for (const item of productPool) {
    item.imageUrls = item.imageUrls.filter((url) => {
      if (usedProductImageUrls.has(url)) return false;
      usedProductImageUrls.add(url);
      return true;
    });
  }
  const marketHypotheses = (Array.isArray(report.marketHypotheses) ? report.marketHypotheses : [])
    .slice(0, 100)
    .map((value) => {
      const item = asObject(value);
      const validationStatus = ["hypothesis", "partial", "validated"].includes(String(item.validationStatus))
        ? String(item.validationStatus)
        : "hypothesis";
      return {
        marketCode: reportText(item.marketCode, 40).toUpperCase(),
        marketName: reportText(item.marketName, 120),
        demandHypothesis: reportText(item.demandHypothesis, 1600),
        buyerTypes: stringList(item.buyerTypes, 50).map((entry) => entry.slice(0, 160)),
        entryMode: reportText(item.entryMode, 1000),
        complianceFocus: stringList(item.complianceFocus, 50).map((entry) => entry.slice(0, 160)),
        recommendedTracks: stringList(item.recommendedTracks, 100).map((entry) => entry.slice(0, 120)),
        validationStatus,
      };
    })
    .filter((item) => item.marketCode || item.marketName);
  const buyerProfiles = (Array.isArray(report.buyerProfiles) ? report.buyerProfiles : [])
    .slice(0, 300)
    .map((value) => {
      const item = asObject(value);
      const website = safeImageUrl(item.website) ?? "";
      const sourceUrl = safeImageUrl(item.sourceUrl) ?? website;
      const requestedStatus = String(item.profileStatus ?? "hypothesis");
      return {
        companyName: reportText(item.companyName, 160),
        website,
        country: reportText(item.country, 80).toUpperCase(),
        buyerType: reportText(item.buyerType, 160),
        customerGroups: stringList(item.customerGroups, 50),
        salesChannels: stringList(item.salesChannels, 30),
        purchasingScenarios: stringList(item.purchasingScenarios, 50),
        seasonality: reportText(item.seasonality, 1000),
        replenishmentCycle: reportText(item.replenishmentCycle, 500),
        orderRequirements: reportText(item.orderRequirements, 2000),
        sourceUrl,
        profileStatus: requestedStatus === "qualified" || requestedStatus === "validated" ? "qualified" : "hypothesis",
      };
    })
    .filter((item) => item.companyName && item.country && item.buyerType && item.sourceUrl);
  const existingFamilyRows = await db.prepare(
    "SELECT DISTINCT track_category, COALESCE(NULLIF(product_family, ''), subcategory) AS product_family FROM research_candidates WHERE project_id = ?",
  ).bind(projectId).all<JsonRecord>();
  const familyTracks = new Map<string, Set<string>>();
  for (const row of [
    ...existingFamilyRows.results.map((item) => ({
      trackCategory: reportText(item.track_category, 120),
      productFamily: reportText(item.product_family, 120),
    })),
    ...productPool.map((item) => ({ trackCategory: item.trackCategory, productFamily: item.productFamily })),
  ]) {
    if (!row.trackCategory || !row.productFamily) continue;
    const familyKey = row.productFamily.toLocaleLowerCase();
    const tracks = familyTracks.get(familyKey) ?? new Set<string>();
    tracks.add(row.trackCategory);
    familyTracks.set(familyKey, tracks);
  }
  const reportedBuyerFamilyMatrix = (Array.isArray(report.buyerFamilyMatrix) ? report.buyerFamilyMatrix : [])
    .slice(0, 1000)
    .map((value) => {
      const item = asObject(value);
      return {
        companyName: reportText(item.companyName, 160),
        country: reportText(item.country, 80).toUpperCase(),
        trackCategory: reportText(item.trackCategory, 120),
        productFamily: reportText(item.productFamily, 120),
        relationshipScore: Math.round(boundedNumber(item.relationshipScore, 0, 100)),
        familyRole: ["core", "cross_sell", "seasonal", "test"].includes(String(item.familyRole)) ? String(item.familyRole) : "test",
        salesScenarios: stringList(item.salesScenarios, 50),
        rationale: reportText(item.rationale, 1200),
        evidenceStatus: ["partial", "validated"].includes(String(item.evidenceStatus)) ? "partial" : "hypothesis",
      };
    })
    .filter((item) => item.companyName && item.country && item.productFamily);
  const buyerFamilyMatrix = reportedBuyerFamilyMatrix.flatMap((item) => {
    const tracks = familyTracks.get(item.productFamily.toLocaleLowerCase());
    if (!tracks?.size) return [];
    if (tracks.has(item.trackCategory)) return [item];
    if (tracks.size !== 1) return [];
    return [{ ...item, trackCategory: [...tracks][0] }];
  });
  const skippedBuyerFamilyLinkCount = reportedBuyerFamilyMatrix.length - buyerFamilyMatrix.length;
  const evidenceRows = (Array.isArray(report.evidence) ? report.evidence : []).slice(0, 500).map((item) => asObject(item));
  const statements: D1PreparedStatement[] = [db.prepare("DELETE FROM research_evidence WHERE run_id = ?").bind(runId)];
  const capturedAt = nowIso();
  let availableCount = 0;
  for (const item of evidenceRows) {
    const sectionKey = RESEARCH_SECTIONS.includes(String(item.sectionKey) as (typeof RESEARCH_SECTIONS)[number])
      ? String(item.sectionKey)
      : "market_demand";
    let sourceUrl = String(item.sourceUrl ?? "").trim();
    if (sourceUrl) {
      try {
        const parsed = new URL(sourceUrl);
        if (!["http:", "https:"].includes(parsed.protocol)) sourceUrl = "";
      } catch {
        sourceUrl = "";
      }
    }
    const evidenceStatus = ["available", "missing", "blocked", "failed", "confirmed_zero"].includes(String(item.status))
      ? String(item.status)
      : sourceUrl ? "available" : "missing";
    if (evidenceStatus === "available" && sourceUrl) availableCount += 1;
    statements.push(db.prepare(
      `INSERT INTO research_evidence
        (id, project_id, run_id, section_key, source_type, source_title, source_url, market,
         status, excerpt, metrics, captured_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      crypto.randomUUID(), projectId, runId, sectionKey,
      String(item.sourceType ?? "public_web").slice(0, 80),
      String(item.sourceTitle ?? "").slice(0, 300), sourceUrl,
      String(item.market ?? "").toUpperCase().slice(0, 12), evidenceStatus,
      String(item.excerpt ?? "").slice(0, 1200), JSON.stringify(asObject(item.metrics)),
      String(item.capturedAt ?? capturedAt).slice(0, 40),
    ));
  }
  const timestamp = nowIso();
  for (const item of productPool) {
    const fingerprint = [item.trackCategory, item.subcategory, item.name, [...item.targetMarkets].sort().join(",")]
      .join("|")
      .toLocaleLowerCase();
    statements.push(db.prepare(
      `INSERT INTO research_candidates
        (id, project_id, fingerprint, name, track_category, subcategory, product_family, commercial_variant,
         image_urls, image_source_ref, target_markets, buyer_types, price_band, moq, compliance, risk_level, stage, score,
         rationale, evidence_status, source_run_id, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(project_id, fingerprint) DO UPDATE SET
         name = excluded.name,
         track_category = excluded.track_category,
         subcategory = excluded.subcategory,
         product_family = CASE WHEN research_candidates.product_family != '' THEN research_candidates.product_family ELSE excluded.product_family END,
         commercial_variant = excluded.commercial_variant,
         image_urls = CASE WHEN excluded.image_urls != '[]' THEN excluded.image_urls ELSE research_candidates.image_urls END,
         image_source_ref = CASE WHEN excluded.image_source_ref != '' THEN excluded.image_source_ref ELSE research_candidates.image_source_ref END,
         target_markets = excluded.target_markets,
         buyer_types = excluded.buyer_types,
         price_band = excluded.price_band,
         moq = excluded.moq,
         compliance = excluded.compliance,
         risk_level = excluded.risk_level,
         stage = CASE WHEN research_candidates.stage IN ('shortlist', 'validation', 'sample', 'validated', 'rejected') THEN research_candidates.stage ELSE excluded.stage END,
         score = excluded.score,
         rationale = excluded.rationale,
         evidence_status = excluded.evidence_status,
         source_run_id = excluded.source_run_id,
         updated_at = excluded.updated_at`,
    ).bind(
      crypto.randomUUID(), projectId, fingerprint, item.name, item.trackCategory, item.subcategory, item.productFamily,
      item.commercialVariant, JSON.stringify(item.imageUrls), item.imageSourceRef,
      JSON.stringify(item.targetMarkets), JSON.stringify(item.buyerTypes),
      item.priceBand, item.moq, JSON.stringify(item.compliance), item.riskLevel, item.stage,
      item.score, item.rationale, item.evidenceStatus, runId, timestamp, timestamp,
    ));
  }
  for (const buyer of buyerProfiles) {
    statements.push(db.prepare(`INSERT INTO research_buyer_profiles
      (id, project_id, company_name, website, country, buyer_type, customer_groups, sales_channels,
       purchasing_scenarios, seasonality, replenishment_cycle, order_requirements, source_url,
       profile_status, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ai', ?, ?)
      ON CONFLICT(project_id, company_name, country) DO UPDATE SET
        website = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.website ELSE excluded.website END,
        buyer_type = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.buyer_type ELSE excluded.buyer_type END,
        customer_groups = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.customer_groups ELSE excluded.customer_groups END,
        sales_channels = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.sales_channels ELSE excluded.sales_channels END,
        purchasing_scenarios = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.purchasing_scenarios ELSE excluded.purchasing_scenarios END,
        seasonality = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.seasonality ELSE excluded.seasonality END,
        replenishment_cycle = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.replenishment_cycle ELSE excluded.replenishment_cycle END,
        order_requirements = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.order_requirements ELSE excluded.order_requirements END,
        source_url = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.source_url ELSE excluded.source_url END,
        profile_status = CASE WHEN research_buyer_profiles.created_by = 'user' THEN research_buyer_profiles.profile_status ELSE excluded.profile_status END,
        updated_at = excluded.updated_at`)
      .bind(crypto.randomUUID(), projectId, buyer.companyName, buyer.website, buyer.country, buyer.buyerType,
        JSON.stringify(buyer.customerGroups), JSON.stringify(buyer.salesChannels), JSON.stringify(buyer.purchasingScenarios),
        buyer.seasonality, buyer.replenishmentCycle, buyer.orderRequirements, buyer.sourceUrl, buyer.profileStatus, timestamp, timestamp));
  }
  for (const link of buyerFamilyMatrix) {
    statements.push(db.prepare(`INSERT INTO research_buyer_family_links
      (id, project_id, buyer_profile_id, track_category, product_family, relationship_score,
       family_role, sales_scenarios, rationale, evidence_status, created_by, created_at, updated_at)
      SELECT ?, ?, id, ?, ?, ?, ?, ?, ?, ?, 'ai', ?, ?
        FROM research_buyer_profiles
       WHERE project_id = ? AND company_name = ? AND country = ?
      ON CONFLICT(buyer_profile_id, track_category, product_family) DO UPDATE SET
        relationship_score = CASE WHEN research_buyer_family_links.created_by = 'user' THEN research_buyer_family_links.relationship_score ELSE excluded.relationship_score END,
        family_role = CASE WHEN research_buyer_family_links.created_by = 'user' THEN research_buyer_family_links.family_role ELSE excluded.family_role END,
        sales_scenarios = CASE WHEN research_buyer_family_links.created_by = 'user' THEN research_buyer_family_links.sales_scenarios ELSE excluded.sales_scenarios END,
        rationale = CASE WHEN research_buyer_family_links.created_by = 'user' THEN research_buyer_family_links.rationale ELSE excluded.rationale END,
        evidence_status = CASE WHEN research_buyer_family_links.created_by = 'user' THEN research_buyer_family_links.evidence_status ELSE excluded.evidence_status END,
        updated_at = excluded.updated_at`)
      .bind(crypto.randomUUID(), projectId, link.trackCategory, link.productFamily, link.relationshipScore,
        link.familyRole, JSON.stringify(link.salesScenarios), link.rationale, link.evidenceStatus, timestamp, timestamp,
        projectId, link.companyName, link.country));
  }
  const normalizedReport = mergeResearchReports(previousReport, {
    ...report,
    status,
    recommendation,
    scorecard: { ...scorecard, total: scoreTotal },
    sections: asObject(report.sections),
    risks: stringList(report.risks, 50),
    actionPlan: stringList(report.actionPlan, 50),
    trackCategories,
    productPool,
    marketHypotheses,
    buyerProfiles,
    buyerFamilyMatrix,
    playbook: asObject(report.playbook),
  });
  const sourceSummary = {
    evidenceCount: evidenceRows.length,
    availableCount,
    buyerProfileCount: buyerProfiles.length,
    buyerFamilyLinkCount: buyerFamilyMatrix.length,
    skippedBuyerFamilyLinkCount,
    markets: [...new Set(evidenceRows.map((item) => String(item.market ?? "").toUpperCase()).filter(Boolean))],
    generator: "Codex / ChatGPT",
  };
  statements.push(
    db.prepare(
      "UPDATE research_runs SET status = ?, result_payload = ?, source_summary = ?, completed_at = ? WHERE id = ?",
    ).bind(status, JSON.stringify(normalizedReport), JSON.stringify(sourceSummary), timestamp, runId),
    db.prepare(
      `UPDATE research_projects
          SET status = ?, current_stage = 'recommendation_actions', progress = ?, summary = ?,
              recommendation = ?, scorecard = ?, updated_at = ?, last_researched_at = ?
        WHERE id = ?`,
    ).bind(
      status === "complete" ? "completed" : "needs_review",
      status === "complete" ? 100 : 80,
      summary.slice(0, 4000), recommendation, JSON.stringify({ ...scorecard, total: scoreTotal }),
      timestamp, timestamp, projectId,
    ),
  );
  for (let index = 0; index < statements.length; index += 100) {
    await db.batch(statements.slice(index, index + 100));
  }
  const globalBuyerSync = await syncProjectBuyerKnowledge(projectId);
  return { projectId, runId, status, evidenceCount: evidenceRows.length, availableCount, candidateCount: productPool.length, buyerProfileCount: buyerProfiles.length, buyerFamilyLinkCount: buyerFamilyMatrix.length, skippedBuyerFamilyLinkCount, globalBuyerSync, scoreTotal };
}

async function updateResearchCandidate(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const candidateId = String(payload.candidateId ?? "").trim();
  const stage = String(payload.stage ?? "").trim();
  if (!projectId || !candidateId) throw new Error("缺少项目或候选产品编号");
  if (!["idea", "research", "sample", "validation", "shortlist", "validated", "rejected"].includes(stage)) throw new Error("候选产品阶段无效");
  const note = reportText(payload.note, 2000);
  const nextAction = reportText(payload.nextAction, 500);
  const followUpAt = String(payload.followUpAt ?? "").trim();
  if (followUpAt && !/^\d{4}-\d{2}-\d{2}$/.test(followUpAt)) throw new Error("跟进日期格式无效");
  const evidenceInput = String(payload.evidenceUrl ?? "").trim();
  const evidenceUrl = evidenceInput ? safeImageUrl(evidenceInput) : "";
  if (evidenceInput && !evidenceUrl) throw new Error("证据链接必须是有效的 http 或 https 地址");
  const db = getRawDb();
  const candidate = await db.prepare(
    "SELECT id, stage FROM research_candidates WHERE id = ? AND project_id = ?",
  ).bind(candidateId, projectId).first<JsonRecord>();
  if (!candidate) throw new Error("没有找到该候选产品");
  const fromStage = String(candidate.stage ?? "idea");
  if (stage === fromStage && !note && !evidenceUrl && !nextAction && !followUpAt) throw new Error("请至少填写一项进展记录");
  const timestamp = nowIso();
  const activity = {
    id: crypto.randomUUID(), project_id: projectId, candidate_id: candidateId,
    from_stage: fromStage, to_stage: stage, note, evidence_url: evidenceUrl,
    next_action: nextAction, follow_up_at: followUpAt, recommended_stage: "",
    created_by: "user", created_at: timestamp,
  };
  await db.batch([
    db.prepare("UPDATE research_candidates SET stage = ?, updated_at = ? WHERE id = ? AND project_id = ?")
      .bind(stage, timestamp, candidateId, projectId),
    db.prepare(`INSERT INTO research_candidate_activities
      (id, project_id, candidate_id, from_stage, to_stage, note, evidence_url, next_action, follow_up_at, recommended_stage, created_by, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(activity.id, projectId, candidateId, fromStage, stage, note, evidenceUrl, nextAction, followUpAt, "", "user", timestamp),
    db.prepare("UPDATE research_projects SET updated_at = ? WHERE id = ?").bind(timestamp, projectId),
  ]);
  return { projectId, candidateId, stage, activity };
}

async function updateResearchCandidateAssessment(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const candidateId = String(payload.candidateId ?? "").trim();
  if (!projectId || !candidateId) throw new Error("缺少项目或候选产品编号");
  const db = getRawDb();
  const row = await db.prepare("SELECT * FROM research_candidates WHERE id = ? AND project_id = ?")
    .bind(candidateId, projectId).first<JsonRecord>();
  if (!row) throw new Error("没有找到该候选产品");
  const assessment = normalizeCandidateSelectionAssessment({
    ...asObject(payload.assessment),
    assessedAt: nowIso(),
    assessedBy: "user",
  });
  const productFamily = reportText(payload.productFamily || row.product_family || row.subcategory, 120);
  const timestamp = nowIso();
  await db.batch([
    db.prepare("UPDATE research_candidates SET product_family = ?, selection_assessment = ?, updated_at = ? WHERE id = ? AND project_id = ?")
      .bind(productFamily, JSON.stringify(assessment), timestamp, candidateId, projectId),
    db.prepare("UPDATE research_projects SET updated_at = ? WHERE id = ?").bind(timestamp, projectId),
  ]);
  const candidate = parseResearchCandidate({ ...row, product_family: productFamily, selection_assessment: JSON.stringify(assessment), updated_at: timestamp });
  return { projectId, candidateId, candidate };
}

async function upsertResearchBuyerProfile(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const buyerId = String(payload.buyerId ?? "").trim();
  const companyName = reportText(payload.companyName, 160);
  const country = reportText(payload.country, 80).toUpperCase();
  const buyerType = reportText(payload.buyerType, 160);
  const websiteInput = String(payload.website ?? "").trim();
  const sourceInput = String(payload.sourceUrl ?? websiteInput).trim();
  const website = websiteInput ? safeImageUrl(websiteInput) : "";
  const sourceUrl = sourceInput ? safeImageUrl(sourceInput) : "";
  const personaCode = reportText(payload.personaCode, 80).toUpperCase()
    || suggestPersonaCode(buyerType, ...stringList(payload.customerGroups), ...stringList(payload.salesChannels), ...stringList(payload.purchasingScenarios));
  const regionCode = reportText(payload.regionCode, 20).toUpperCase() || regionCodeForCountry(country);
  const profileStatus = ["hypothesis", "qualified", "validated", "rejected"].includes(String(payload.profileStatus))
    ? String(payload.profileStatus)
    : "hypothesis";
  if (!projectId || companyName.length < 2 || !country || !buyerType) throw new Error("请填写真实买家公司、国家和买家类型");
  if (!sourceUrl) throw new Error("真实买家画像必须提供可访问的公开来源链接");
  if (websiteInput && !website) throw new Error("公司网站必须是有效的 http 或 https 地址");
  const db = getRawDb();
  const [personaExists, regionExists] = await Promise.all([
    db.prepare("SELECT code FROM buyer_persona_categories WHERE code = ? AND active = 1").bind(personaCode).first<JsonRecord>(),
    db.prepare("SELECT code FROM trade_regions WHERE code = ? AND active = 1").bind(regionCode).first<JsonRecord>(),
  ]);
  if (!personaExists) throw new Error("请选择有效的买家画像分类");
  if (!regionExists) throw new Error("请选择有效的地区分类");
  const project = await db.prepare("SELECT id FROM research_projects WHERE id = ?").bind(projectId).first<JsonRecord>();
  if (!project) throw new Error("没有找到该调研项目");
  const duplicate = buyerId ? null : await db.prepare(
    "SELECT id FROM research_buyer_profiles WHERE project_id = ? AND company_name = ? AND country = ?",
  ).bind(projectId, companyName, country).first<JsonRecord>();
  const timestamp = nowIso();
  const id = buyerId || String(duplicate?.id ?? crypto.randomUUID());
  if (buyerId) {
    const existing = await db.prepare("SELECT id FROM research_buyer_profiles WHERE id = ? AND project_id = ?").bind(buyerId, projectId).first<JsonRecord>();
    if (!existing) throw new Error("没有找到该买家画像");
  }
  await db.prepare(`INSERT INTO research_buyer_profiles
    (id, project_id, company_name, website, country, buyer_type, customer_groups, sales_channels,
     purchasing_scenarios, seasonality, replenishment_cycle, order_requirements, source_url,
     profile_status, odoo_lead_id, created_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'user', ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      company_name = excluded.company_name, website = excluded.website, country = excluded.country,
      buyer_type = excluded.buyer_type, customer_groups = excluded.customer_groups,
      sales_channels = excluded.sales_channels, purchasing_scenarios = excluded.purchasing_scenarios,
      seasonality = excluded.seasonality, replenishment_cycle = excluded.replenishment_cycle,
      order_requirements = excluded.order_requirements, source_url = excluded.source_url,
      profile_status = excluded.profile_status, odoo_lead_id = excluded.odoo_lead_id,
      created_by = 'user', updated_at = excluded.updated_at`)
    .bind(
      id, projectId, companyName, website, country, buyerType,
      JSON.stringify(stringList(payload.customerGroups, 50)), JSON.stringify(stringList(payload.salesChannels, 30)),
      JSON.stringify(stringList(payload.purchasingScenarios, 50)), reportText(payload.seasonality, 1000),
      reportText(payload.replenishmentCycle, 500), reportText(payload.orderRequirements, 2000), sourceUrl,
      profileStatus, payload.odooLeadId ? Math.max(1, Math.round(Number(payload.odooLeadId))) : null, timestamp, timestamp,
    ).run();
  await db.prepare("UPDATE research_projects SET updated_at = ? WHERE id = ?").bind(timestamp, projectId).run();
  await syncProjectBuyerKnowledge(projectId);
  const row = await db.prepare("SELECT * FROM research_buyer_profiles WHERE id = ?").bind(id).first<JsonRecord>();
  return { projectId, buyer: parseResearchBuyerProfile(row ?? {}) };
}

async function updateResearchBuyerFamilyMatrix(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const buyerId = String(payload.buyerId ?? "").trim();
  if (!projectId || !buyerId) throw new Error("缺少项目或买家画像编号");
  const db = getRawDb();
  const buyer = await db.prepare("SELECT id FROM research_buyer_profiles WHERE id = ? AND project_id = ?").bind(buyerId, projectId).first<JsonRecord>();
  if (!buyer) throw new Error("没有找到该买家画像");
  const familyRows = await db.prepare("SELECT DISTINCT track_category, COALESCE(NULLIF(product_family, ''), subcategory) AS product_family FROM research_candidates WHERE project_id = ?")
    .bind(projectId).all<JsonRecord>();
  const validFamilies = new Set(familyRows.results.map((row) => `${String(row.track_category).trim()}|${String(row.product_family).trim()}`.toLocaleLowerCase()));
  const links = (Array.isArray(payload.links) ? payload.links : []).slice(0, 500).map((value) => {
    const item = asObject(value);
    const trackCategory = reportText(item.trackCategory, 120);
    const productFamily = reportText(item.productFamily, 120);
    const key = `${trackCategory}|${productFamily}`.toLocaleLowerCase();
    if (!validFamilies.has(key)) throw new Error(`产品家族不存在：${productFamily || "未命名"}`);
    return {
      trackCategory,
      productFamily,
      relationshipScore: Math.round(boundedNumber(item.relationshipScore, 0, 100)),
      familyRole: ["core", "cross_sell", "seasonal", "test"].includes(String(item.familyRole)) ? String(item.familyRole) : "test",
      salesScenarios: stringList(item.salesScenarios, 50),
      rationale: reportText(item.rationale, 1200),
      evidenceStatus: ["hypothesis", "partial", "validated"].includes(String(item.evidenceStatus)) ? String(item.evidenceStatus) : "hypothesis",
    };
  });
  const timestamp = nowIso();
  const statements: D1PreparedStatement[] = [db.prepare("DELETE FROM research_buyer_family_links WHERE buyer_profile_id = ? AND project_id = ?").bind(buyerId, projectId)];
  for (const link of links) {
    statements.push(db.prepare(`INSERT INTO research_buyer_family_links
      (id, project_id, buyer_profile_id, track_category, product_family, relationship_score,
       family_role, sales_scenarios, rationale, evidence_status, created_by, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'user', ?, ?)`)
      .bind(crypto.randomUUID(), projectId, buyerId, link.trackCategory, link.productFamily, link.relationshipScore,
        link.familyRole, JSON.stringify(link.salesScenarios), link.rationale, link.evidenceStatus, timestamp, timestamp));
  }
  statements.push(db.prepare("UPDATE research_projects SET updated_at = ? WHERE id = ?").bind(timestamp, projectId));
  await db.batch(statements);
  await syncProjectBuyerKnowledge(projectId);
  const rows = await db.prepare("SELECT * FROM research_buyer_family_links WHERE buyer_profile_id = ? ORDER BY relationship_score DESC").bind(buyerId).all<JsonRecord>();
  return { projectId, buyerId, links: rows.results.map(parseResearchBuyerFamilyLink) };
}

async function upsertGlobalBuyerProfile(payload: JsonRecord) {
  await ensureResearchSchema();
  const buyerId = String(payload.buyerId ?? "").trim();
  const companyName = reportText(payload.companyName, 160);
  const country = reportText(payload.country, 80).toUpperCase();
  const buyerType = reportText(payload.buyerType, 160);
  const websiteInput = String(payload.website ?? "").trim();
  const sourceInput = String(payload.sourceUrl ?? websiteInput).trim();
  const website = websiteInput ? safeImageUrl(websiteInput) : "";
  const sourceUrl = sourceInput ? safeImageUrl(sourceInput) : "";
  const personaCode = reportText(payload.personaCode, 80).toUpperCase()
    || suggestPersonaCode(buyerType, ...stringList(payload.customerGroups), ...stringList(payload.salesChannels), ...stringList(payload.purchasingScenarios));
  const regionCode = reportText(payload.regionCode, 20).toUpperCase() || regionCodeForCountry(country);
  const profileStatus = ["hypothesis", "qualified", "validated", "rejected"].includes(String(payload.profileStatus))
    ? String(payload.profileStatus)
    : "hypothesis";
  if (companyName.length < 2 || !country || !buyerType) throw new Error("请填写真实买家公司、国家和买家类型");
  if (!sourceUrl) throw new Error("全球买家画像必须提供可访问的公开来源链接");
  if (websiteInput && !website) throw new Error("公司网站必须是有效的 http 或 https 地址");
  const db = getRawDb();
  const [personaExists, regionExists] = await Promise.all([
    db.prepare("SELECT code FROM buyer_persona_categories WHERE code = ? AND active = 1").bind(personaCode).first<JsonRecord>(),
    db.prepare("SELECT code FROM trade_regions WHERE code = ? AND active = 1").bind(regionCode).first<JsonRecord>(),
  ]);
  if (!personaExists) throw new Error("请选择有效的买家画像分类");
  if (!regionExists) throw new Error("请选择有效的地区分类");
  const duplicate = buyerId ? null : await db.prepare(
    "SELECT id FROM global_buyer_profiles WHERE company_name = ? AND country = ?",
  ).bind(companyName, country).first<JsonRecord>();
  const id = buyerId || String(duplicate?.id ?? crypto.randomUUID());
  if (buyerId) {
    const existing = await db.prepare("SELECT id FROM global_buyer_profiles WHERE id = ?").bind(buyerId).first<JsonRecord>();
    if (!existing) throw new Error("没有找到该全球买家画像");
  }
  const timestamp = nowIso();
  await db.prepare(`INSERT INTO global_buyer_profiles
    (id, company_name, website, country, buyer_type, persona_code, region_code, customer_groups, sales_channels,
     purchasing_scenarios, seasonality, replenishment_cycle, order_requirements, source_url,
     profile_status, created_by, created_at, updated_at, last_verified_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'user', ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      company_name = excluded.company_name, website = excluded.website, country = excluded.country,
      buyer_type = excluded.buyer_type, persona_code = excluded.persona_code, region_code = excluded.region_code,
      customer_groups = excluded.customer_groups,
      sales_channels = excluded.sales_channels, purchasing_scenarios = excluded.purchasing_scenarios,
      seasonality = excluded.seasonality, replenishment_cycle = excluded.replenishment_cycle,
      order_requirements = excluded.order_requirements, source_url = excluded.source_url,
      profile_status = excluded.profile_status, created_by = 'user', updated_at = excluded.updated_at,
      last_verified_at = excluded.last_verified_at`)
    .bind(
      id, companyName, website, country, buyerType, personaCode, regionCode,
      JSON.stringify(stringList(payload.customerGroups, 50)), JSON.stringify(stringList(payload.salesChannels, 30)),
      JSON.stringify(stringList(payload.purchasingScenarios, 50)), reportText(payload.seasonality, 1000),
      reportText(payload.replenishmentCycle, 500), reportText(payload.orderRequirements, 2000), sourceUrl,
      profileStatus, timestamp, timestamp, profileStatus === "validated" ? timestamp : null,
    ).run();
  const row = await db.prepare(`SELECT g.*,
    (SELECT COUNT(*) FROM global_buyer_project_refs r WHERE r.buyer_profile_id = g.id) AS source_project_count
    FROM global_buyer_profiles g WHERE g.id = ?`).bind(id).first<JsonRecord>();
  return { buyer: { ...parseResearchBuyerProfile(row ?? {}), source_project_count: Number(row?.source_project_count ?? 0) } };
}

async function updateGlobalBuyerFamilyMatrix(payload: JsonRecord) {
  await ensureResearchSchema();
  const buyerId = String(payload.buyerId ?? "").trim();
  if (!buyerId) throw new Error("缺少全球买家画像编号");
  const db = getRawDb();
  const buyer = await db.prepare("SELECT id FROM global_buyer_profiles WHERE id = ?").bind(buyerId).first<JsonRecord>();
  if (!buyer) throw new Error("没有找到该全球买家画像");
  const familyRows = await db.prepare(`SELECT t.name AS track_category, f.name AS product_family
    FROM product_family_master f JOIN product_tracks t ON t.code = f.track_code
    WHERE f.active = 1 AND t.active = 1
    UNION
    SELECT DISTINCT track_category, COALESCE(NULLIF(product_family, ''), subcategory) AS product_family
    FROM research_candidates`).all<JsonRecord>();
  const validFamilies = new Set(familyRows.results.map((row) => `${String(row.track_category).trim()}|${String(row.product_family).trim()}`.toLocaleLowerCase()));
  const links = (Array.isArray(payload.links) ? payload.links : []).slice(0, 500).map((value) => {
    const item = asObject(value);
    const trackCategory = reportText(item.trackCategory, 120);
    const productFamily = reportText(item.productFamily, 120);
    if (!validFamilies.has(`${trackCategory}|${productFamily}`.toLocaleLowerCase())) throw new Error(`产品家族不存在：${productFamily || "未命名"}`);
    return {
      trackCategory,
      productFamily,
      relationshipScore: Math.round(boundedNumber(item.relationshipScore, 0, 100)),
      familyRole: ["core", "cross_sell", "seasonal", "test"].includes(String(item.familyRole)) ? String(item.familyRole) : "test",
      salesScenarios: stringList(item.salesScenarios, 50),
      rationale: reportText(item.rationale, 1200),
      evidenceStatus: ["hypothesis", "partial", "validated"].includes(String(item.evidenceStatus)) ? String(item.evidenceStatus) : "hypothesis",
    };
  });
  const timestamp = nowIso();
  const statements: D1PreparedStatement[] = [db.prepare("DELETE FROM global_buyer_family_links WHERE buyer_profile_id = ?").bind(buyerId)];
  for (const link of links) statements.push(db.prepare(`INSERT INTO global_buyer_family_links
    (id, buyer_profile_id, track_category, product_family, relationship_score, family_role,
     sales_scenarios, rationale, evidence_status, created_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'user', ?, ?)`)
    .bind(crypto.randomUUID(), buyerId, link.trackCategory, link.productFamily, link.relationshipScore,
      link.familyRole, JSON.stringify(link.salesScenarios), link.rationale, link.evidenceStatus, timestamp, timestamp));
  await db.batch(statements);
  const rows = await db.prepare("SELECT * FROM global_buyer_family_links WHERE buyer_profile_id = ? ORDER BY relationship_score DESC")
    .bind(buyerId).all<JsonRecord>();
  return { buyerId, links: rows.results.map(parseResearchBuyerFamilyLink) };
}

function taxonomyCode(value: unknown, label: string) {
  const code = String(value ?? "").trim().toUpperCase();
  if (!/^[A-Z0-9_]{2,48}$/.test(code)) throw new Error(`${label}代码仅允许 2–48 位大写字母、数字和下划线`);
  return code;
}

function taxonomySourceRefs(value: unknown) {
  return stringList(value, 30).map((item) => safeImageUrl(item)).filter((item): item is string => Boolean(item));
}

async function logPersonaChange(input: {
  code: string;
  action: string;
  origin: string;
  runId?: string;
  before?: JsonRecord | null;
  after?: JsonRecord | null;
}) {
  const db = getRawDb();
  await db.prepare(`INSERT INTO commercial_taxonomy_change_log
    (id, entity_type, entity_code, action, origin, run_id, before_json, after_json, created_at)
    VALUES (?, 'buyer_persona', ?, ?, ?, ?, ?, ?, ?)`)
    .bind(crypto.randomUUID(), input.code, input.action, input.origin, input.runId ?? "",
      JSON.stringify(input.before ?? {}), JSON.stringify(input.after ?? {}), nowIso()).run();
}

async function upsertBuyerPersonaCategory(payload: JsonRecord, origin = "user", runId = "") {
  await ensureResearchSchema();
  const code = taxonomyCode(payload.code, "画像分类");
  const name = reportText(payload.name, 120);
  const groupName = reportText(payload.groupName, 120);
  const description = reportText(payload.description, 1200);
  const valueChainRole = reportText(payload.valueChainRole, 300);
  if (name.length < 2 || !groupName || !description || !valueChainRole) throw new Error("请完整填写分类组、名称、价值链角色和描述");
  const timestamp = nowIso();
  const db = getRawDb();
  const existing = await db.prepare("SELECT * FROM buyer_persona_categories WHERE code = ?").bind(code).first<JsonRecord>();
  const active = payload.active === false ? 0 : 1;
  const sourceRefs = taxonomySourceRefs(payload.sourceRefs);
  const nextVersion = existing ? Math.max(1, Number(existing.version ?? 1)) + 1 : 1;
  await db.prepare(`INSERT INTO buyer_persona_categories
    (code, group_name, name, description, value_chain_role, customer_groups, sales_channels,
     purchase_scenarios, buying_triggers, order_characteristics, compliance_focus, source_refs, version,
     last_reviewed_at, active, created_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(code) DO UPDATE SET group_name = excluded.group_name, name = excluded.name,
      description = excluded.description, value_chain_role = excluded.value_chain_role,
      customer_groups = excluded.customer_groups, sales_channels = excluded.sales_channels,
      purchase_scenarios = excluded.purchase_scenarios, buying_triggers = excluded.buying_triggers,
      order_characteristics = excluded.order_characteristics, compliance_focus = excluded.compliance_focus,
      source_refs = excluded.source_refs, version = excluded.version, last_reviewed_at = excluded.last_reviewed_at,
      active = excluded.active, updated_at = excluded.updated_at`)
    .bind(code, groupName, name, description, valueChainRole,
      JSON.stringify(stringList(payload.customerGroups, 50)), JSON.stringify(stringList(payload.salesChannels, 50)),
      JSON.stringify(stringList(payload.purchaseScenarios, 50)), JSON.stringify(stringList(payload.buyingTriggers, 50)),
      JSON.stringify(stringList(payload.orderCharacteristics, 50)), JSON.stringify(stringList(payload.complianceFocus, 50)),
      JSON.stringify(sourceRefs), nextVersion, timestamp, active, origin, timestamp, timestamp).run();
  const updated = await db.prepare("SELECT * FROM buyer_persona_categories WHERE code = ?").bind(code).first<JsonRecord>();
  await logPersonaChange({
    code,
    action: existing ? Number(existing.active ?? 1) === 0 && active === 1 ? "restore" : "update" : "create",
    origin,
    runId,
    before: existing,
    after: updated,
  });
  return readGlobalBuyerLibrary();
}

async function setBuyerPersonaCategoryActive(payload: JsonRecord) {
  await ensureResearchSchema();
  const code = taxonomyCode(payload.code, "画像分类");
  const active = payload.active === true;
  const db = getRawDb();
  const existing = await db.prepare("SELECT * FROM buyer_persona_categories WHERE code = ?").bind(code).first<JsonRecord>();
  if (!existing) throw new Error("没有找到该画像分类");
  const timestamp = nowIso();
  await db.prepare("UPDATE buyer_persona_categories SET active = ?, version = version + 1, updated_at = ? WHERE code = ?")
    .bind(active ? 1 : 0, timestamp, code).run();
  const updated = await db.prepare("SELECT * FROM buyer_persona_categories WHERE code = ?").bind(code).first<JsonRecord>();
  await logPersonaChange({ code, action: active ? "restore" : "delete", origin: "user", before: existing, after: updated });
  return readGlobalBuyerLibrary();
}

async function importBuyerPersonaProposals(payload: JsonRecord) {
  await ensureResearchSchema();
  const runId = String(payload.runId ?? "").trim();
  if (!/^[0-9a-f-]{36}$/i.test(runId)) throw new Error("AI画像任务编号无效");
  const report = asObject(payload.report);
  const mode = report.mode === "enrich" ? "enrich" : "discover";
  const targetCode = report.targetCode ? taxonomyCode(report.targetCode, "目标画像") : "";
  const proposals = Array.isArray(report.personas) ? report.personas.slice(0, 10).map(asObject) : [];
  if (!proposals.length) throw new Error("AI结果没有画像建议");
  const db = getRawDb();
  const timestamp = nowIso();
  const statements: D1PreparedStatement[] = [];
  for (const item of proposals) {
    const code = taxonomyCode(item.code, "画像分类");
    const name = reportText(item.name, 120);
    const groupName = reportText(item.groupName, 120);
    const description = reportText(item.description, 1200);
    const valueChainRole = reportText(item.valueChainRole, 300);
    const sourceRefs = taxonomySourceRefs(item.sourceRefs);
    if (name.length < 2 || !groupName || !description || !valueChainRole) throw new Error(`画像建议 ${code} 的必填字段不完整`);
    if (!sourceRefs.length) throw new Error(`画像建议 ${code} 缺少可核验来源`);
    const normalized = {
      code, groupName, name, description, valueChainRole,
      customerGroups: stringList(item.customerGroups, 50), salesChannels: stringList(item.salesChannels, 50),
      purchaseScenarios: stringList(item.purchaseScenarios, 50), buyingTriggers: stringList(item.buyingTriggers, 50),
      orderCharacteristics: stringList(item.orderCharacteristics, 50), complianceFocus: stringList(item.complianceFocus, 50),
      sourceRefs,
    };
    statements.push(db.prepare(`INSERT INTO buyer_persona_ai_proposals
      (id, run_id, mode, target_code, persona_code, payload, source_refs, rationale, status, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)`)
      .bind(crypto.randomUUID(), runId, mode, targetCode, code, JSON.stringify(normalized), JSON.stringify(sourceRefs),
        reportText(item.rationale, 1200), timestamp));
  }
  await db.batch(statements);
  return { imported: statements.length, buyerLibrary: await readGlobalBuyerLibrary() };
}

async function reviewBuyerPersonaProposal(payload: JsonRecord) {
  await ensureResearchSchema();
  const proposalId = String(payload.proposalId ?? "").trim();
  const decision = payload.decision === "apply" ? "apply" : payload.decision === "reject" ? "reject" : "";
  if (!proposalId || !decision) throw new Error("请选择有效的AI建议和审核结果");
  const db = getRawDb();
  const proposal = await db.prepare("SELECT * FROM buyer_persona_ai_proposals WHERE id = ? AND status = 'pending'")
    .bind(proposalId).first<JsonRecord>();
  if (!proposal) throw new Error("AI建议不存在或已经审核");
  if (decision === "apply") {
    const proposalPayload = jsonObject(proposal.payload);
    await upsertBuyerPersonaCategory({ ...proposalPayload, active: true }, "ai_assistant", String(proposal.run_id ?? ""));
  }
  await db.prepare("UPDATE buyer_persona_ai_proposals SET status = ?, reviewed_at = ? WHERE id = ?")
    .bind(decision === "apply" ? "applied" : "rejected", nowIso(), proposalId).run();
  return readGlobalBuyerLibrary();
}

async function upsertProductTrack(payload: JsonRecord) {
  await ensureResearchSchema();
  const code = taxonomyCode(payload.code, "产品赛道");
  const name = reportText(payload.name, 120);
  const description = reportText(payload.description, 1200);
  const buyerValue = reportText(payload.buyerValue, 600);
  if (name.length < 2 || !description || !buyerValue) throw new Error("请完整填写赛道名称、描述和买家价值");
  const timestamp = nowIso();
  const db = getRawDb();
  await db.prepare(`INSERT INTO product_tracks
    (code, name, description, buyer_value, compliance_focus, active, created_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, 'user', ?, ?)
    ON CONFLICT(code) DO UPDATE SET name = excluded.name, description = excluded.description,
      buyer_value = excluded.buyer_value, compliance_focus = excluded.compliance_focus,
      active = excluded.active, created_by = 'user', updated_at = excluded.updated_at`)
    .bind(code, name, description, buyerValue, JSON.stringify(stringList(payload.complianceFocus, 50)),
      payload.active === false ? 0 : 1, timestamp, timestamp).run();
  return readGlobalBuyerLibrary();
}

async function upsertProductFamilyMaster(payload: JsonRecord) {
  await ensureResearchSchema();
  const code = taxonomyCode(payload.code, "产品家族");
  const trackCode = taxonomyCode(payload.trackCode, "所属赛道");
  const name = reportText(payload.name, 120);
  const description = reportText(payload.description, 1200);
  if (name.length < 2 || !description) throw new Error("请完整填写产品家族名称和描述");
  const db = getRawDb();
  const track = await db.prepare("SELECT code FROM product_tracks WHERE code = ? AND active = 1").bind(trackCode).first<JsonRecord>();
  if (!track) throw new Error("请选择有效的产品赛道");
  const timestamp = nowIso();
  await db.prepare(`INSERT INTO product_family_master
    (code, track_code, name, description, use_scenarios, compliance_tags, keywords, active, created_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'user', ?, ?)
    ON CONFLICT(code) DO UPDATE SET track_code = excluded.track_code, name = excluded.name,
      description = excluded.description, use_scenarios = excluded.use_scenarios,
      compliance_tags = excluded.compliance_tags, keywords = excluded.keywords,
      active = excluded.active, created_by = 'user', updated_at = excluded.updated_at`)
    .bind(code, trackCode, name, description, JSON.stringify(stringList(payload.useScenarios, 50)),
      JSON.stringify(stringList(payload.complianceTags, 50)), JSON.stringify(stringList(payload.keywords, 50)),
      payload.active === false ? 0 : 1, timestamp, timestamp).run();
  return readGlobalBuyerLibrary();
}

async function upsertPersonaProductMatrix(payload: JsonRecord) {
  await ensureResearchSchema();
  const personaCode = taxonomyCode(payload.personaCode, "画像分类");
  const regionCode = taxonomyCode(payload.regionCode || "GLOBAL", "地区");
  const trackCode = taxonomyCode(payload.trackCode, "产品赛道");
  const productFamilyCode = payload.productFamilyCode ? taxonomyCode(payload.productFamilyCode, "产品家族") : "";
  const db = getRawDb();
  const [persona, region, track, family] = await Promise.all([
    db.prepare("SELECT code FROM buyer_persona_categories WHERE code = ? AND active = 1").bind(personaCode).first<JsonRecord>(),
    db.prepare("SELECT code FROM trade_regions WHERE code = ? AND active = 1").bind(regionCode).first<JsonRecord>(),
    db.prepare("SELECT code FROM product_tracks WHERE code = ? AND active = 1").bind(trackCode).first<JsonRecord>(),
    productFamilyCode ? db.prepare("SELECT code, track_code FROM product_family_master WHERE code = ? AND active = 1").bind(productFamilyCode).first<JsonRecord>() : Promise.resolve(null),
  ]);
  if (!persona || !region || !track) throw new Error("画像分类、地区或产品赛道无效");
  if (productFamilyCode && (!family || String(family.track_code) !== trackCode)) throw new Error("产品家族不属于所选赛道");
  const familyRole = ["core", "cross_sell", "seasonal", "test"].includes(String(payload.familyRole)) ? String(payload.familyRole) : "test";
  const evidenceStatus = ["hypothesis", "partial", "validated"].includes(String(payload.evidenceStatus)) ? String(payload.evidenceStatus) : "hypothesis";
  const timestamp = nowIso();
  const id = `${personaCode}:${regionCode}:${trackCode}:${productFamilyCode || "*"}`;
  await db.prepare(`INSERT INTO persona_product_matrix
    (id, persona_code, region_code, track_code, product_family_code, relevance_score, family_role,
     sales_scenarios, seasonality, rationale, evidence_status, created_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'user', ?, ?)
    ON CONFLICT(persona_code, region_code, track_code, product_family_code) DO UPDATE SET
      relevance_score = excluded.relevance_score, family_role = excluded.family_role,
      sales_scenarios = excluded.sales_scenarios, seasonality = excluded.seasonality,
      rationale = excluded.rationale, evidence_status = excluded.evidence_status,
      created_by = 'user', updated_at = excluded.updated_at`)
    .bind(id, personaCode, regionCode, trackCode, productFamilyCode,
      Math.round(boundedNumber(payload.relevanceScore, 0, 100)), familyRole,
      JSON.stringify(stringList(payload.salesScenarios, 50)), reportText(payload.seasonality, 500),
      reportText(payload.rationale, 1200), evidenceStatus, timestamp, timestamp).run();
  return readGlobalBuyerLibrary();
}

async function updateResearchMarket(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const marketCode = String(payload.marketCode ?? "").trim().toUpperCase();
  const status = String(payload.status ?? "").trim();
  if (!projectId || !marketCode) throw new Error("缺少项目或市场编号");
  if (!["hypothesis", "partial", "validated", "rejected"].includes(status)) throw new Error("市场验证状态无效");
  const note = reportText(payload.note, 2000);
  const nextAction = reportText(payload.nextAction, 500);
  const followUpAt = String(payload.followUpAt ?? "").trim();
  if (followUpAt && !/^\d{4}-\d{2}-\d{2}$/.test(followUpAt)) throw new Error("跟进日期格式无效");
  const evidenceInput = String(payload.evidenceUrl ?? "").trim();
  const evidenceUrl = evidenceInput ? safeImageUrl(evidenceInput) : "";
  if (evidenceInput && !evidenceUrl) throw new Error("证据链接必须是有效的 http 或 https 地址");
  if (status === "validated" && (!note || !evidenceUrl)) throw new Error("标记为已验证时，请填写结论并提供可核验的证据链接");
  if (status === "rejected" && !note) throw new Error("标记为已否定时，请填写否定原因");
  const db = getRawDb();
  const project = await db.prepare("SELECT id FROM research_projects WHERE id = ?").bind(projectId).first<JsonRecord>();
  if (!project) throw new Error("没有找到该调研项目");
  const previous = await db.prepare(
    "SELECT to_status FROM research_market_activities WHERE project_id = ? AND market_code = ? ORDER BY created_at DESC LIMIT 1",
  ).bind(projectId, marketCode).first<JsonRecord>();
  const fromStatus = String(previous?.to_status ?? payload.fromStatus ?? "hypothesis");
  if (status === fromStatus && !note && !evidenceUrl && !nextAction && !followUpAt) throw new Error("请至少填写一项验证记录");
  const timestamp = nowIso();
  const activity = {
    id: crypto.randomUUID(), project_id: projectId, market_code: marketCode,
    from_status: fromStatus, to_status: status, note, evidence_url: evidenceUrl,
    next_action: nextAction, follow_up_at: followUpAt, created_by: "user", created_at: timestamp,
  };
  await db.batch([
    db.prepare(`INSERT INTO research_market_activities
      (id, project_id, market_code, from_status, to_status, note, evidence_url, next_action, follow_up_at, created_by, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).bind(
      activity.id, projectId, marketCode, fromStatus, status, note, evidenceUrl, nextAction, followUpAt, "user", timestamp,
    ),
    db.prepare("UPDATE research_projects SET updated_at = ? WHERE id = ?").bind(timestamp, projectId),
  ]);
  return { projectId, marketCode, status, activity };
}

async function createCandidateAssist(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const candidateId = String(payload.candidateId ?? "").trim();
  const requestNote = reportText(payload.requestNote, 1000);
  if (!projectId || !candidateId) throw new Error("缺少项目或候选产品编号");
  const db = getRawDb();
  const project = await db.prepare("SELECT * FROM research_projects WHERE id = ?").bind(projectId).first<JsonRecord>();
  const candidate = await db.prepare("SELECT * FROM research_candidates WHERE id = ? AND project_id = ?").bind(candidateId, projectId).first<JsonRecord>();
  if (!project || !candidate) throw new Error("没有找到该调研项目或候选产品");
  const assistRunId = crypto.randomUUID();
  return {
    projectId,
    candidateId,
    assistRunId,
    dispatchTask: {
      runId: assistRunId,
      projectId,
      candidateId,
      projectName: String(project.product_name ?? ""),
      projectCategory: String(project.product_category ?? ""),
      candidateName: String(candidate.name ?? ""),
      trackCategory: String(candidate.track_category ?? ""),
      subcategory: String(candidate.subcategory ?? ""),
      productFamily: String(candidate.product_family || candidate.subcategory || ""),
      commercialVariant: String(candidate.commercial_variant ?? ""),
      targetMarkets: stringList(candidate.target_markets, 30),
      buyerTypes: stringList(candidate.buyer_types, 30),
      priceBand: String(candidate.price_band ?? ""),
      moq: String(candidate.moq ?? ""),
      compliance: stringList(candidate.compliance, 30),
      riskLevel: String(candidate.risk_level ?? "unknown"),
      currentStage: String(candidate.stage ?? "idea"),
      languages: stringList(project.languages, 30),
      channels: stringList(project.channels, 30),
      requestNote,
    },
  };
}

async function importCandidateAssist(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const candidateId = String(payload.candidateId ?? "").trim();
  const report = asObject(payload.report);
  if (!projectId || !candidateId) throw new Error("缺少项目或候选产品编号");
  const db = getRawDb();
  const candidate = await db.prepare("SELECT id, stage FROM research_candidates WHERE id = ? AND project_id = ?")
    .bind(candidateId, projectId).first<JsonRecord>();
  if (!candidate) throw new Error("没有找到该候选产品");
  const currentStage = String(candidate.stage ?? "idea");
  const validStages = ["idea", "research", "sample", "validation", "shortlist", "validated", "rejected"];
  const recommendedStage = validStages.includes(String(report.recommendedStage)) ? String(report.recommendedStage) : currentStage;
  const note = reportText(report.note, 2000);
  const nextAction = reportText(report.nextAction, 500);
  const evidenceInput = String(report.evidenceUrl ?? "").trim();
  const evidenceUrl = evidenceInput ? safeImageUrl(evidenceInput) : "";
  const imageSourceRef = safeImageUrl(report.imageSourceRef) ?? "";
  const usedImageRows = await db.prepare("SELECT image_urls FROM research_candidates WHERE project_id = ? AND id <> ?")
    .bind(projectId, candidateId).all<JsonRecord>();
  const usedImageUrls = new Set(usedImageRows.results.flatMap((item) => stringList(item.image_urls, 6)));
  const imageUrls = imageSourceRef
    ? imageUrlCandidates(report.imageUrls).filter((url) => !usedImageUrls.has(url)).slice(0, 3)
    : [];
  if (!note && !nextAction) throw new Error("AI辅助结果缺少调研记录和下一步建议");
  if (evidenceInput && !evidenceUrl) throw new Error("AI辅助结果中的证据链接无效");
  const timestamp = nowIso();
  const activity = {
    id: crypto.randomUUID(), project_id: projectId, candidate_id: candidateId,
    from_stage: currentStage, to_stage: currentStage, note, evidence_url: evidenceUrl,
    next_action: nextAction, follow_up_at: "", recommended_stage: recommendedStage,
    created_by: "ai", created_at: timestamp,
  };
  const statements = [
    db.prepare(`INSERT INTO research_candidate_activities
      (id, project_id, candidate_id, from_stage, to_stage, note, evidence_url, next_action, follow_up_at, recommended_stage, created_by, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(activity.id, projectId, candidateId, currentStage, currentStage, note, evidenceUrl, nextAction, "", recommendedStage, "ai", timestamp),
    db.prepare("UPDATE research_candidates SET updated_at = ? WHERE id = ? AND project_id = ?").bind(timestamp, candidateId, projectId),
    db.prepare("UPDATE research_projects SET updated_at = ? WHERE id = ?").bind(timestamp, projectId),
  ];
  if (imageUrls.length) {
    statements.push(db.prepare("UPDATE research_candidates SET image_urls = ?, image_source_ref = ?, updated_at = ? WHERE id = ? AND project_id = ?")
      .bind(JSON.stringify(imageUrls), imageSourceRef, timestamp, candidateId, projectId));
  }
  await db.batch(statements);
  return { projectId, candidateId, activity, imageCount: imageUrls.length };
}

async function createCandidateImageAssist(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const candidateIds = stringList(payload.candidateIds, 25);
  if (!projectId || !candidateIds.length) throw new Error("请选择本轮需要补图的候选产品");
  const db = getRawDb();
  const project = await db.prepare("SELECT product_name FROM research_projects WHERE id = ?").bind(projectId).first<JsonRecord>();
  if (!project) throw new Error("没有找到该调研项目");
  const rows = await db.prepare("SELECT * FROM research_candidates WHERE project_id = ?").bind(projectId).all<JsonRecord>();
  const requested = new Set(candidateIds);
  const candidates = rows.results.filter((item) => requested.has(String(item.id))).slice(0, 25);
  if (!candidates.length) throw new Error("没有找到需要补图的候选产品");
  const runId = crypto.randomUUID();
  return {
    projectId,
    runId,
    dispatchTask: {
      runId,
      projectId,
      projectName: String(project.product_name ?? "产品与市场调研"),
      candidates: candidates.map((item) => ({
        candidateId: String(item.id),
        name: String(item.name ?? ""),
        commercialVariant: String(item.commercial_variant ?? ""),
        targetMarkets: stringList(item.target_markets, 10),
      })),
    },
  };
}

async function importCandidateImages(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const report = asObject(payload.report);
  const inputRows = Array.isArray(report.images) ? report.images.slice(0, 25).map(asObject) : [];
  if (!projectId || !inputRows.length) throw new Error("图片辅助结果为空");
  const db = getRawDb();
  const rows = await db.prepare("SELECT id, stage, image_urls FROM research_candidates WHERE project_id = ?").bind(projectId).all<JsonRecord>();
  const candidateMap = new Map(rows.results.map((item) => [String(item.id), item]));
  const targetIds = new Set(inputRows.map((item) => String(item.candidateId ?? "")));
  const seenUrls = new Set(rows.results.filter((item) => !targetIds.has(String(item.id))).flatMap((item) => stringList(item.image_urls, 6)));
  const timestamp = nowIso();
  const statements = [];
  let updated = 0;
  let imageCount = 0;
  for (const item of inputRows) {
    const candidateId = String(item.candidateId ?? "").trim();
    const candidate = candidateMap.get(candidateId);
    const imageSourceRef = safeImageUrl(item.imageSourceRef) ?? "";
    if (!candidate || !imageSourceRef) continue;
    const imageUrls = imageUrlCandidates(item.imageUrls).filter((url) => {
      if (seenUrls.has(url)) return false;
      seenUrls.add(url);
      return true;
    }).slice(0, 3);
    if (!imageUrls.length) continue;
    const stage = String(candidate.stage ?? "idea");
    statements.push(
      db.prepare("UPDATE research_candidates SET image_urls = ?, image_source_ref = ?, updated_at = ? WHERE id = ? AND project_id = ?")
        .bind(JSON.stringify(imageUrls), imageSourceRef, timestamp, candidateId, projectId),
      db.prepare(`INSERT INTO research_candidate_activities
        (id, project_id, candidate_id, from_stage, to_stage, note, evidence_url, next_action, follow_up_at, recommended_stage, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).bind(
        crypto.randomUUID(), projectId, candidateId, stage, stage,
        `AI已补充 ${imageUrls.length} 张可追溯产品图片。`, imageSourceRef,
        "核对图片与计划采购规格是否一致", "", stage, "ai", timestamp,
      ),
    );
    updated += 1;
    imageCount += imageUrls.length;
  }
  if (!updated) throw new Error("没有取得可核验且不重复的产品图片");
  statements.push(db.prepare("UPDATE research_projects SET updated_at = ? WHERE id = ?").bind(timestamp, projectId));
  for (let index = 0; index < statements.length; index += 100) await db.batch(statements.slice(index, index + 100));
  return { projectId, updated, imageCount };
}

async function failResearchRun(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const runId = String(payload.researchRunId ?? payload.runId ?? "").trim();
  if (!projectId || !runId) throw new Error("缺少调研项目或运行编号");
  const db = getRawDb();
  const timestamp = nowIso();
  const result = await db.prepare(
    `UPDATE research_runs
        SET status = 'failed', source_summary = ?, completed_at = ?
      WHERE id = ? AND project_id = ? AND status IN ('waiting_for_codex', 'researching')`,
  ).bind(
    JSON.stringify({ error: String(payload.error ?? "Codex 调研未完成").trim().slice(0, 1000) }),
    timestamp,
    runId,
    projectId,
  ).run();
  const latestSuccessfulRun = await db.prepare(
    `SELECT status
       FROM research_runs
      WHERE project_id = ? AND status IN ('complete', 'partial')
      ORDER BY COALESCE(completed_at, created_at) DESC
      LIMIT 1`,
  ).bind(projectId).first<{ status: string }>();
  await db.prepare(
    `UPDATE research_projects
        SET status = ?, current_stage = ?, progress = ?, updated_at = ?
      WHERE id = ? AND status != 'archived'`,
  ).bind(
    latestSuccessfulRun?.status === "complete" ? "completed" : latestSuccessfulRun ? "needs_review" : "planning",
    latestSuccessfulRun ? "recommendation_actions" : "product_definition",
    latestSuccessfulRun?.status === "complete" ? 100 : latestSuccessfulRun ? 80 : 10,
    timestamp,
    projectId,
  ).run();
  return { projectId, runId, status: result.meta.changes ? "failed" : "unchanged" };
}

async function setResearchProjectArchived(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  const archived = Boolean(payload.archived);
  if (!projectId) throw new Error("缺少调研项目编号");
  const result = await getRawDb().prepare(
    "UPDATE research_projects SET status = ?, updated_at = ? WHERE id = ?",
  ).bind(archived ? "archived" : "planning", nowIso(), projectId).run();
  if (!result.meta.changes) throw new Error("没有找到该调研项目");
  return { projectId, archived };
}

async function deleteResearchProject(payload: JsonRecord) {
  await ensureResearchSchema();
  const projectId = String(payload.projectId ?? "").trim();
  if (!projectId) throw new Error("缺少调研项目编号");
  const db = getRawDb();
  const project = await db.prepare("SELECT id FROM research_projects WHERE id = ?").bind(projectId).first<{ id: string }>();
  if (!project) throw new Error("没有找到该调研项目");
  const activeRun = await db.prepare(
    "SELECT id FROM research_runs WHERE project_id = ? AND status IN ('waiting_for_codex', 'researching') LIMIT 1",
  ).bind(projectId).first<{ id: string }>();
  if (activeRun) throw new Error("调研正在执行，完成或停止后才能删除项目");
  await db.batch([
    db.prepare("DELETE FROM research_candidates WHERE project_id = ?").bind(projectId),
    db.prepare("DELETE FROM research_evidence WHERE project_id = ?").bind(projectId),
    db.prepare("DELETE FROM research_runs WHERE project_id = ?").bind(projectId),
    db.prepare("DELETE FROM research_projects WHERE id = ?").bind(projectId),
  ]);
  return { projectId, deleted: true };
}

async function exportResearchProject(projectIdValue: unknown) {
  const detail = await researchProjectDetail(projectIdValue);
  const project = detail.project as JsonRecord;
  const latestRun = latestResearchReportRun(detail.runs as JsonRecord[]);
  const report = latestRun ? asObject(latestRun.result_payload) : {};
  const sections = asObject(report.sections);
  const tracks = jsonArray(report.trackCategories).map(asObject);
  const markets = jsonArray(report.marketHypotheses).map(asObject);
  const playbook = asObject(report.playbook);
  const candidates = detail.candidates as JsonRecord[];
  const lines = [
    `# ${String(project.product_name)}｜产品与市场调研`,
    "",
    `- 目标市场：${stringList(project.target_markets).join("、") || "全球"}`,
    `- 研究语言：${stringList(project.languages).join("、") || "英语"}`,
    `- 当前状态：${String(project.status)}`,
    `- 建议：${String(project.recommendation)}`,
    `- 更新时间：${String(project.updated_at)}`,
    "",
    "## 摘要",
    "",
    String(project.summary || "尚未完成首轮调研。"),
    "",
    `## 赛道大类（${tracks.length}）`,
    "",
  ];
  for (const track of tracks) {
    lines.push(`### ${String(track.name || "未命名赛道")}`, "", String(track.description || "暂无说明"), "");
    const subcategories = stringList(track.subcategories, 100);
    if (subcategories.length) lines.push(`- 细分领域：${subcategories.join("、")}`);
    const targetMarkets = stringList(track.targetMarkets, 100);
    if (targetMarkets.length) lines.push(`- 对应市场：${targetMarkets.join("、")}`);
    lines.push("");
  }
  lines.push(`## 候选产品池（${candidates.length} / ${Number(project.target_candidate_count) || 2000} 目标）`, "");
  for (const candidate of candidates) {
    lines.push(
      `- ${String(candidate.name)}｜${String(candidate.track_category || "未分类")} / ${String(candidate.subcategory || "未细分")}｜${stringList(candidate.target_markets, 100).join("、") || "市场待判断"}｜${String(candidate.stage || "idea")}｜评分 ${candidate.score ?? "—"}`,
    );
  }
  lines.push("", `## 对应市场（${markets.length}）`, "");
  for (const market of markets) {
    lines.push(
      `### ${String(market.marketName || market.marketCode || "未命名市场")}`,
      "",
      String(market.demandHypothesis || "暂无需求假设"),
      "",
      `- 典型买家：${stringList(market.buyerTypes, 50).join("、") || "待判断"}`,
      `- 进入方式：${String(market.entryMode || "待判断")}`,
      `- 合规重点：${stringList(market.complianceFocus, 50).join("、") || "待判断"}`,
      "",
    );
  }
  const playbookSections = [
    ["roadmap180Days", "180 天路线"],
    ["teamSop", "两人 SOP"],
    ["budgetAndQuoting", "预算与报价"],
    ["complianceSupplyChain", "合规供应链"],
    ["customerAcquisition", "获客与成交"],
    ["executionChecklist", "执行清单"],
  ];
  for (const [key, label] of playbookSections) {
    const section = asObject(playbook[key]);
    lines.push(`## ${label}`, "", String(section.summary ?? "暂无内容"), "");
    for (const item of stringList(section.items, 200)) lines.push(`- ${item}`);
    lines.push("");
  }
  for (const sectionKey of RESEARCH_SECTIONS) {
    const section = asObject(sections[sectionKey]);
    lines.push(`## ${sectionKey}`, "", String(section.summary ?? "暂无结论"), "");
    for (const finding of stringList(section.findings, 50)) lines.push(`- ${finding}`);
    lines.push("");
  }
  lines.push("## 来源证据", "");
  for (const item of detail.evidence as JsonRecord[]) {
    lines.push(`- [${String(item.source_title || item.source_type)}](${String(item.source_url || "#")}) · ${String(item.market || "未注明市场")} · ${String(item.status)}`);
  }
  return new Response(lines.join("\n"), {
    headers: {
      "content-type": "text/markdown; charset=utf-8",
      "content-disposition": `attachment; filename="lightlink-research-${String(projectIdValue).slice(0, 8)}.md"`,
    },
  });
}

async function exportResearchCandidateHandoff(projectIdValue: unknown, candidateIdValue: unknown) {
  await ensureResearchSchema();
  const projectId = String(projectIdValue ?? "").trim();
  const candidateId = String(candidateIdValue ?? "").trim();
  if (!projectId || !candidateId) throw new Error("缺少项目或候选产品编号");
  const db = getRawDb();
  const [projectRow, candidateRow, activityRows] = await Promise.all([
    db.prepare("SELECT * FROM research_projects WHERE id = ?").bind(projectId).first<JsonRecord>(),
    db.prepare("SELECT * FROM research_candidates WHERE id = ? AND project_id = ?").bind(candidateId, projectId).first<JsonRecord>(),
    db.prepare("SELECT * FROM research_candidate_activities WHERE candidate_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT 100")
      .bind(candidateId, projectId).all<JsonRecord>(),
  ]);
  if (!projectRow || !candidateRow) throw new Error("没有找到该调研项目或候选产品");
  const project = parseResearchProject(projectRow) as ReturnType<typeof parseResearchProject> & JsonRecord;
  const candidate = parseResearchCandidate(candidateRow) as ReturnType<typeof parseResearchCandidate> & JsonRecord;
  const readiness = candidateHandoffReadiness(candidate, candidate.selection_assessment);
  if (!readiness.ready) {
    return Response.json({ error: "候选产品尚未达到 Odoo 移交门槛", blockers: readiness.blockers }, { status: 409 });
  }
  const handoff = {
    schemaVersion: "lightlink.radar.odoo.product_handoff.v1",
    generatedAt: nowIso(),
    source: { system: "LightLink Radar", projectId, candidateId, projectName: String(project.product_name) },
    target: { system: "Odoo", projectId: null, note: "导入前由用户选择 Odoo 运营项目；Odoo 仍是正式产品数据唯一事实源。" },
    family: {
      trackCategory: String(candidate.track_category || ""),
      subcategory: String(candidate.subcategory || ""),
      productFamily: String(candidate.product_family || candidate.subcategory || ""),
    },
    productTemplate: {
      name: String(candidate.name),
      commercialVariant: String(candidate.commercial_variant || ""),
      targetMarkets: candidate.target_markets,
      buyerTypes: candidate.buyer_types,
      priceBand: String(candidate.price_band || ""),
      moq: String(candidate.moq || ""),
      compliance: candidate.compliance,
      riskLevel: String(candidate.risk_level || "unknown"),
      rationale: String(candidate.rationale || ""),
      images: candidate.image_urls,
      imageSourceRef: String(candidate.image_source_ref || ""),
    },
    selection: { ...candidate.selection_assessment, totalScore: readiness.score },
    evidence: {
      status: String(candidate.evidence_status || "hypothesis"),
      activities: activityRows.results.map((activity) => ({
        stage: String(activity.to_stage || ""),
        note: String(activity.note || ""),
        evidenceUrl: String(activity.evidence_url || ""),
        nextAction: String(activity.next_action || ""),
        createdAt: String(activity.created_at || ""),
      })),
    },
    handoff: {
      status: "ready_for_odoo_review",
      disclaimer: "可移交不等于可上架；Odoo 侧仍需完成产品建档、变体、供应商、成本、合规与审批复核。",
    },
  };
  return new Response(JSON.stringify(handoff, null, 2), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "content-disposition": `attachment; filename="lightlink-odoo-handoff-${candidateId.slice(0, 8)}.json"`,
    },
  });
}

async function dashboard() {
  const db = getRawDb();
  const latest = await db.prepare("SELECT * FROM scan_runs ORDER BY created_at DESC LIMIT 1").first<JsonRecord>();
  const settingsRows = await db.prepare("SELECT key, value FROM user_settings").all<JsonRecord>();
  const settings = Object.fromEntries(settingsRows.results.map((row) => [String(row.key), String(row.value)]));

  if (!latest) {
    return {
      empty: true,
      settings,
      integrations: integrationStatuses(),
      results: [],
      sources: VALID_PLATFORMS.map((platform) => ({
        platform,
        coverage: 0,
        collected_at: "",
        statuses: ["missing"],
        cluster_count: 0,
        observation_count: 0,
        source_kinds: [],
        source_refs: [],
      })),
      history: [],
      watchlist: [],
      trend: [],
    };
  }

  const runId = String(latest.id);
  const [resultRows, observationRows, historyRows, watchRows, trendRows] = await Promise.all([
    db
      .prepare(
        `SELECT c.id AS cluster_id, c.canonical_keyword, c.group_name, c.aliases, c.category,
                c.market, c.language, c.intent_label, c.status AS cluster_status,
                s.attention_level, s.momentum, s.commercial_validation, s.buyer_intent,
                s.competition, s.heat, s.opportunity, s.confidence,
                s.conservative_opportunity, s.lifecycle, s.rationale,
                s.anomaly_flags, s.score_version, s.calculated_at
           FROM score_snapshots s
           JOIN keyword_clusters c ON c.id = s.cluster_id
          WHERE s.run_id = ?
          ORDER BY COALESCE(s.conservative_opportunity, -1) DESC, s.confidence DESC`,
      )
      .bind(runId)
      .all<JsonRecord>(),
    db
      .prepare(
        `SELECT id, cluster_id, platform, metric, current_value, previous_value, sample_n,
                unique_actor_n, coverage_days, source_kind, source_ref, geo_scope,
                status, missing_reason, collected_at
           FROM observations WHERE run_id = ? ORDER BY platform, metric`,
      )
      .bind(runId)
      .all<JsonRecord>(),
    db
      .prepare(
        `SELECT r.id, r.mode, r.query, r.market, r.language, r.window_days, r.status, r.is_demo,
                r.source_summary, r.created_at, r.completed_at, COUNT(s.id) AS cluster_count,
                AVG(s.heat) AS heat, AVG(s.opportunity) AS opportunity,
                AVG(s.confidence) AS confidence,
                (SELECT COUNT(*) FROM observations o WHERE o.run_id = r.id) AS observation_count,
                (SELECT COUNT(*) FROM observations o WHERE o.run_id = r.id AND o.status IN ('ok', 'confirmed_zero')) AS valid_observation_count,
                (SELECT COUNT(DISTINCT o.platform) FROM observations o WHERE o.run_id = r.id) AS platform_count
           FROM scan_runs r LEFT JOIN score_snapshots s ON s.run_id = r.id
          GROUP BY r.id ORDER BY r.created_at DESC LIMIT 500`,
      )
      .all<JsonRecord>(),
    db
      .prepare(
        `SELECT w.id, w.cluster_id, w.market, w.cadence_days, w.enabled,
                w.last_run_at, w.next_run_at, c.canonical_keyword, c.group_name, c.aliases
           FROM watchlist w JOIN keyword_clusters c ON c.id = w.cluster_id
          ORDER BY w.created_at DESC`,
      )
      .all<JsonRecord>(),
    db
      .prepare(
        `SELECT r.id, r.created_at, AVG(s.heat) AS heat, AVG(s.opportunity) AS opportunity
           FROM scan_runs r JOIN score_snapshots s ON s.run_id = r.id
          WHERE r.status IN ('complete', 'partial')
            AND r.query = ? AND r.market = ? AND r.language = ? AND r.window_days = ?
            AND r.is_demo = ?
          GROUP BY r.id ORDER BY r.created_at DESC LIMIT 12`,
      )
      .bind(String(latest.query), String(latest.market), String(latest.language), Number(latest.window_days), Number(latest.is_demo))
      .all<JsonRecord>(),
  ]);

  const results = resultRows.results.map((row) => ({
    ...row,
    aliases: jsonArray(row.aliases),
    anomaly_flags: jsonArray(row.anomaly_flags),
  }));
  const sourceSummary = jsonObject(latest.source_summary);
  const plannedKeywords = Array.isArray(sourceSummary.plannedKeywords) ? sourceSummary.plannedKeywords : [];
  const observedClusterCount = new Set(observationRows.results.map((row) => String(row.cluster_id))).size;
  const expectedClusterCount = Math.max(results.length, plannedKeywords.length, observedClusterCount);
  const sources = VALID_PLATFORMS.map((platform) => {
    const platformRows = observationRows.results.filter((row) => String(row.platform) === platform);
    const coveredClusters = new Set(
      platformRows
        .filter((row) => ["ok", "confirmed_zero"].includes(String(row.status)))
        .map((row) => String(row.cluster_id)),
    );
    const collectedAt = platformRows
      .map((row) => String(row.collected_at))
      .sort()
      .at(-1) ?? String(latest.created_at);
    return {
      platform,
      coverage: expectedClusterCount ? Math.round((coveredClusters.size / expectedClusterCount) * 100) : 0,
      collected_at: collectedAt,
      statuses: platformRows.length ? [...new Set(platformRows.map((row) => String(row.status)))] : ["missing"],
      cluster_count: new Set(platformRows.map((row) => String(row.cluster_id))).size,
      observation_count: platformRows.length,
      source_kinds: [...new Set(platformRows.map((row) => String(row.source_kind)))],
      source_refs: [...new Set(platformRows.map((row) => String(row.source_ref)).filter(Boolean))].slice(0, 8),
    };
  });
  const watches = watchRows.results.map((row) => ({ ...row, aliases: jsonArray(row.aliases) }));
  const history = historyRows.results.map((row) => ({ ...row, source_summary: jsonObject(row.source_summary) }));

  return {
    empty: false,
    run: { ...latest, source_summary: sourceSummary },
    settings,
    integrations: integrationStatuses(),
    results,
    observations: observationRows.results,
    sources,
    history,
    watchlist: watches,
    trend: [...trendRows.results].reverse(),
  };
}

async function seedDemo() {
  const db = getRawDb();
  const existing = await db.prepare("SELECT id FROM scan_runs WHERE is_demo = 1 ORDER BY created_at DESC LIMIT 1").first<{ id: string }>();
  if (existing) return { runId: existing.id, reused: true };

  const runId = crypto.randomUUID();
  const timestamp = nowIso();
  const clusterIds = new Map<string, string>();
  const statements: D1PreparedStatement[] = [
    db
      .prepare(
        `INSERT INTO scan_runs
          (id, mode, query, market, language, window_days, status, is_demo, source_summary, created_at, completed_at)
         VALUES (?, 'seed', ?, 'US', 'en', 30, 'complete', 1, ?, ?, ?)`,
      )
      .bind(
        runId,
        "solar street light",
        JSON.stringify({ demo: true, note: "仅用于功能演示，不代表真实平台数据" }),
        timestamp,
        timestamp,
      ),
  ];

  for (const row of DEMO_OBSERVATIONS) {
    const canonical = normalizeKeyword(row.keyword);
    if (clusterIds.has(canonical)) continue;
    const clusterId = crypto.randomUUID();
    clusterIds.set(canonical, clusterId);
    statements.push(
      db
        .prepare(
          `INSERT INTO keyword_clusters
            (id, canonical_keyword, group_name, aliases, category, market, language, intent_label, status, updated_at)
           VALUES (?, ?, ?, ?, ?, 'US', 'en', '待判断', 'candidate', ?)
           ON CONFLICT(canonical_keyword, market, language) DO UPDATE SET
             group_name = excluded.group_name,
             aliases = excluded.aliases,
             category = excluded.category,
             updated_at = excluded.updated_at`,
        )
        .bind(clusterId, canonical, row.groupName ?? canonical, JSON.stringify(row.aliases ?? []), row.category ?? "未分类", timestamp),
    );
  }

  await db.batch(statements);

  const persistedClusters = await db
    .prepare("SELECT id, canonical_keyword FROM keyword_clusters WHERE market = 'US' AND language = 'en'")
    .all<{ id: string; canonical_keyword: string }>();
  for (const row of persistedClusters.results) clusterIds.set(row.canonical_keyword, row.id);

  const dataStatements: D1PreparedStatement[] = [];
  for (const row of DEMO_OBSERVATIONS) {
    const clusterId = clusterIds.get(normalizeKeyword(row.keyword));
    if (!clusterId) continue;
    dataStatements.push(
      db
        .prepare(
          `INSERT INTO observations
            (id, run_id, cluster_id, platform, metric, current_value, previous_value, sample_n,
             unique_actor_n, coverage_days, source_kind, source_ref, geo_scope, status,
             missing_reason, raw_json, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          crypto.randomUUID(),
          runId,
          clusterId,
          row.platform,
          row.metric,
          row.currentValue,
          row.previousValue,
          row.sampleN,
          row.uniqueActorN,
          row.coverageDays,
          row.sourceKind,
          row.sourceRef ?? "",
          row.geoScope,
          row.status,
          row.missingReason ?? null,
          JSON.stringify(row.raw ?? {}),
          row.collectedAt,
        ),
    );
  }

  for (const score of computeScores(DEMO_OBSERVATIONS)) {
    const clusterId = clusterIds.get(score.canonicalKeyword);
    if (!clusterId) continue;
    dataStatements.push(
      db
        .prepare(
          `INSERT INTO score_snapshots
            (id, run_id, cluster_id, attention_level, momentum, commercial_validation,
             buyer_intent, competition, heat, opportunity, confidence, conservative_opportunity,
             lifecycle, rationale, anomaly_flags, score_version, calculated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          crypto.randomUUID(), runId, clusterId, score.attentionLevel, score.momentum,
          score.commercialValidation, score.buyerIntent, score.competition, score.heat,
          score.opportunity, score.confidence, score.conservativeOpportunity, score.lifecycle,
          score.rationale, JSON.stringify(score.anomalyFlags), SCORE_VERSION, timestamp,
        ),
    );
  }

  await db.batch(dataStatements);
  return { runId, reused: false };
}

async function createScan(payload: JsonRecord) {
  const db = getRawDb();
  const mode = payload.mode === "discover" ? "discover" : "seed";
  const query = String(payload.query ?? "").trim();
  const market = String(payload.market ?? "US").toUpperCase();
  if (!SUPPORTED_MARKETS.has(market)) throw new Error("暂不支持该市场");
  const language = languageForRequest(market, payload.language);
  const windowDays = [7, 30, 90].includes(Number(payload.windowDays)) ? Number(payload.windowDays) : 30;
  if (!query) throw new Error(mode === "discover" ? "请输入产品类目" : "请输入至少一个关键词");

  const seeds = splitKeywords(query);
  if (!seeds.length) throw new Error("没有可用的关键词");
  const runId = crypto.randomUUID();
  const timestamp = nowIso();
  const statements: D1PreparedStatement[] = [
    db
      .prepare(
        `INSERT INTO scan_runs
          (id, mode, query, market, language, window_days, status, is_demo, source_summary, created_at)
         VALUES (?, ?, ?, ?, ?, ?, 'waiting_for_data', 0, ?, ?)`,
      )
      .bind(
        runId,
        mode,
        query,
        market,
        language,
        windowDays,
        JSON.stringify({ plannedKeywords: seeds, platforms: VALID_PLATFORMS, collectionMode: "manual_or_assistant" }),
        timestamp,
      ),
  ];

  for (const seed of seeds) {
    const aliases = expandSeedKeyword(seed, language).filter((candidate) => candidate !== seed);
    statements.push(
      db
        .prepare(
          `INSERT INTO keyword_clusters
            (id, canonical_keyword, group_name, aliases, category, market, language, intent_label, status, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, '待判断', 'candidate', ?)
           ON CONFLICT(canonical_keyword, market, language) DO UPDATE SET
             aliases = excluded.aliases,
             updated_at = excluded.updated_at`,
        )
        .bind(crypto.randomUUID(), seed, seed, JSON.stringify(aliases), String(payload.category ?? "未分类"), market, language, timestamp),
    );
  }

  await db.batch(statements);
  return {
    runId,
    status: "waiting_for_data",
    collectionTask: {
      query,
      market,
      language,
      windowDays,
      platforms: VALID_PLATFORMS,
      note: "请采集真实证据后调用 import_observations；缺失和失败不可填为 0。",
    },
  };
}

async function importObservations(
  payload: JsonRecord,
  options: { mode?: "seed" | "discover" | "import"; sourceSummary?: JsonRecord } = {},
) {
  const db = getRawDb();
  const rawRows = Array.isArray(payload.rows) ? payload.rows : [];
  if (!rawRows.length) throw new Error("没有可导入的数据行");
  if (rawRows.length > 5000) throw new Error("单次最多导入 5000 行");
  const incomingRows = rawRows.map(validateObservation);
  const market = String(payload.market ?? incomingRows[0].geoScope ?? "US").toUpperCase();
  if (!SUPPORTED_MARKETS.has(market)) throw new Error("暂不支持该市场");
  const language = languageForRequest(market, payload.language);
  const windowDays = [7, 30, 90].includes(Number(payload.windowDays)) ? Number(payload.windowDays) : 30;
  let runId = String(payload.runId ?? "");
  const existingRun = Boolean(runId);
  const timestamp = nowIso();

  const statements: D1PreparedStatement[] = [];
  if (!runId) {
    runId = crypto.randomUUID();
    statements.push(
      db
        .prepare(
          `INSERT INTO scan_runs
            (id, mode, query, market, language, window_days, status, is_demo, source_summary, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'collecting', 0, ?, ?)`,
        )
        .bind(
          runId,
          options.mode ?? "import",
          String(payload.query ?? "导入数据"),
          market,
          language,
          windowDays,
          JSON.stringify(options.sourceSummary ?? {}),
          timestamp,
        ),
    );
  } else {
    const run = await db
      .prepare("SELECT id, market, language, window_days FROM scan_runs WHERE id = ?")
      .bind(runId)
      .first<{ id: string; market: string; language: string; window_days: number }>();
    if (!run) throw new Error("目标扫描任务不存在");
    if (run.market !== market || run.language !== language || Number(run.window_days) !== windowDays) {
      throw new Error("导入数据的市场、语言或时间窗口与扫描任务不一致");
    }
  }

  for (const row of incomingRows) {
    if (row.coverageDays !== windowDays) throw new Error(`“${row.keyword}”的覆盖天数与扫描任务的 ${windowDays} 天窗口不一致`);
    const geoScope = row.geoScope.toUpperCase();
    if (market !== "GLOBAL" && geoScope !== "GLOBAL" && geoScope !== market) {
      throw new Error(`“${row.keyword}”的地区 ${row.geoScope} 与扫描市场 ${market} 不一致`);
    }
  }

  const existing = await db
    .prepare("SELECT id, canonical_keyword, aliases, status FROM keyword_clusters WHERE market = ? AND language = ?")
    .bind(market, language)
    .all<{ id: string; canonical_keyword: string; aliases: string; status: string }>();
  const clusterMap = new Map<string, string>();
  const canonicalById = new Map<string, string>();

  for (const cluster of existing.results.filter((cluster) => cluster.status !== "excluded")) {
    clusterMap.set(normalizeKeyword(cluster.canonical_keyword), cluster.id);
    canonicalById.set(cluster.id, normalizeKeyword(cluster.canonical_keyword));
  }
  for (const cluster of existing.results.filter((cluster) => cluster.status !== "excluded")) {
    for (const alias of jsonArray(cluster.aliases).map(String).map(normalizeKeyword)) {
      if (alias && !clusterMap.has(alias)) clusterMap.set(alias, cluster.id);
    }
  }
  for (const cluster of existing.results) {
    const canonical = normalizeKeyword(cluster.canonical_keyword);
    if (!clusterMap.has(canonical)) clusterMap.set(canonical, cluster.id);
    if (!canonicalById.has(cluster.id)) canonicalById.set(cluster.id, canonical);
  }

  for (const row of incomingRows) {
    const importedKeyword = normalizeKeyword(row.keyword);
    if (clusterMap.has(importedKeyword)) continue;
    const clusterId = crypto.randomUUID();
    clusterMap.set(importedKeyword, clusterId);
    canonicalById.set(clusterId, importedKeyword);
    statements.push(
      db
        .prepare(
          `INSERT INTO keyword_clusters
            (id, canonical_keyword, group_name, aliases, category, market, language, intent_label, status, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, '待判断', 'candidate', ?)`,
        )
        .bind(clusterId, importedKeyword, row.groupName ?? importedKeyword, JSON.stringify(row.aliases ?? []), row.category ?? "未分类", market, language, timestamp),
    );
  }

  const previousRows = existingRun
    ? await db
        .prepare(
          `SELECT c.canonical_keyword, c.group_name, c.aliases, c.category,
                  o.platform, o.metric, o.current_value, o.previous_value, o.sample_n,
                  o.unique_actor_n, o.coverage_days, o.source_kind, o.source_ref,
                  o.geo_scope, o.status, o.missing_reason, o.raw_json, o.collected_at
             FROM observations o JOIN keyword_clusters c ON c.id = o.cluster_id
            WHERE o.run_id = ?`,
        )
        .bind(runId)
        .all<JsonRecord>()
    : { results: [] as JsonRecord[] };
  const rowsByKey = new Map<string, IncomingObservation>();
  const rowKey = (row: IncomingObservation) => {
    const clusterId = clusterMap.get(normalizeKeyword(row.keyword));
    if (!clusterId) throw new Error(`无法为“${row.keyword}”确定词簇`);
    return `${clusterId}\u0000${row.platform}\u0000${row.metric}`;
  };

  for (const stored of previousRows.results) {
    const row: IncomingObservation = {
      keyword: String(stored.canonical_keyword),
      groupName: String(stored.group_name),
      aliases: jsonArray(stored.aliases).map(String),
      category: String(stored.category),
      platform: String(stored.platform),
      metric: String(stored.metric) as IncomingObservation["metric"],
      currentValue: stored.current_value == null ? null : Number(stored.current_value),
      previousValue: stored.previous_value == null ? null : Number(stored.previous_value),
      sampleN: stored.sample_n == null ? null : Number(stored.sample_n),
      uniqueActorN: stored.unique_actor_n == null ? null : Number(stored.unique_actor_n),
      coverageDays: Number(stored.coverage_days),
      sourceKind: String(stored.source_kind) as IncomingObservation["sourceKind"],
      sourceRef: String(stored.source_ref ?? ""),
      geoScope: String(stored.geo_scope),
      status: String(stored.status) as IncomingObservation["status"],
      missingReason: stored.missing_reason == null ? null : String(stored.missing_reason),
      collectedAt: String(stored.collected_at),
      raw: jsonObject(stored.raw_json),
    };
    rowsByKey.set(rowKey(row), row);
  }

  const incomingKeys = new Set<string>();
  for (const row of incomingRows) {
    const key = rowKey(row);
    if (incomingKeys.has(key)) {
      throw new Error(`“${row.keyword}”在 ${row.platform} 的 ${row.metric} 指标重复，请每个词簇、平台和指标只保留一行`);
    }
    incomingKeys.add(key);
    rowsByKey.set(key, row);
  }
  const rows = [...rowsByKey.values()];

  statements.push(
    db.prepare("DELETE FROM observations WHERE run_id = ?").bind(runId),
    db.prepare("DELETE FROM score_snapshots WHERE run_id = ?").bind(runId),
  );
  for (const row of rows) {
    const clusterId = clusterMap.get(normalizeKeyword(row.keyword));
    if (!clusterId) continue;
    statements.push(
      db
        .prepare(
          `INSERT INTO observations
            (id, run_id, cluster_id, platform, metric, current_value, previous_value, sample_n,
             unique_actor_n, coverage_days, source_kind, source_ref, geo_scope, status,
             missing_reason, raw_json, collected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          crypto.randomUUID(), runId, clusterId, row.platform, row.metric, row.currentValue,
          row.previousValue, row.sampleN, row.uniqueActorN, row.coverageDays, row.sourceKind,
          row.sourceRef ?? "", row.geoScope, row.status, row.missingReason ?? null,
          JSON.stringify({ importedKeyword: row.keyword, ...(row.raw ?? {}) }), row.collectedAt,
        ),
    );
  }

  const scoringRows = rows.map((row) => {
    const importedKeyword = normalizeKeyword(row.keyword);
    const clusterId = clusterMap.get(importedKeyword)!;
    return {
      ...row,
      keyword: canonicalById.get(clusterId) ?? importedKeyword,
      aliases: [...new Set([...(row.aliases ?? []), importedKeyword])],
    };
  });
  const scores = computeScores(scoringRows);
  for (const score of scores) {
    const clusterId = clusterMap.get(score.canonicalKeyword);
    const resolvedClusterId = clusterId ?? [...canonicalById.entries()].find(([, canonical]) => canonical === score.canonicalKeyword)?.[0];
    if (!resolvedClusterId) continue;
    statements.push(
      db
        .prepare(
          `INSERT INTO score_snapshots
            (id, run_id, cluster_id, attention_level, momentum, commercial_validation,
             buyer_intent, competition, heat, opportunity, confidence, conservative_opportunity,
             lifecycle, rationale, anomaly_flags, score_version, calculated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          crypto.randomUUID(), runId, resolvedClusterId, score.attentionLevel, score.momentum,
          score.commercialValidation, score.buyerIntent, score.competition, score.heat,
          score.opportunity, score.confidence, score.conservativeOpportunity, score.lifecycle,
          score.rationale, JSON.stringify(score.anomalyFlags), SCORE_VERSION, timestamp,
        ),
    );
  }
  const observedPlatforms = new Set(rows.map((row) => row.platform));
  const partial =
    rows.some((row) => !["ok", "confirmed_zero"].includes(row.status)) ||
    CORE_PLATFORMS.some((platform) => !observedPlatforms.has(platform)) ||
    scores.some((score) => score.opportunity === null);
  statements.push(
    db
      .prepare("UPDATE scan_runs SET status = ?, completed_at = ?, source_summary = ? WHERE id = ?")
      .bind(
        partial ? "partial" : "complete",
        timestamp,
        JSON.stringify({
          ...(options.sourceSummary ?? {}),
          importedRows: incomingRows.length,
          totalRows: rows.length,
          platforms: [...new Set(rows.map((row) => row.platform))],
        }),
        runId,
      ),
  );
  await db.batch(statements);
  return { runId, importedRows: incomingRows.length, totalRows: rows.length, scores: scores.length, status: partial ? "partial" : "complete" };
}

async function generateWithAssistant(payload: JsonRecord) {
  const query = String(payload.query ?? "").trim();
  const market = String(payload.market ?? "US").toUpperCase();
  if (!query || query.length > 500) throw new Error("请输入 1–500 个字符的产品词或类目");
  if (!SUPPORTED_MARKETS.has(market)) throw new Error("暂不支持该市场");
  const language = languageForRequest(market, payload.language);
  const windowDays = [7, 30, 90].includes(Number(payload.windowDays)) ? Number(payload.windowDays) : 30;
  const scanMode = payload.scanMode === "discover" ? "discover" : "seed";
  const resultLimit = [10, 15, 20].includes(Number(payload.resultLimit)) ? Number(payload.resultLimit) : 20;
  const requestNote = String(payload.requestNote ?? "").trim().slice(0, 1000);
  const apiKey = String(payload.apiKey ?? runtimeValue("OPENAI_API_KEY")).trim();
  if (!apiKey) throw new Error("请先在 API 配置中填写本次 OpenAI API Key，或在 .dev.vars 配置 OPENAI_API_KEY");
  const configuredModel = String(payload.model ?? (runtimeValue("OPENAI_MODEL") || "gpt-5.4-mini")).trim();
  const model = /^[a-zA-Z0-9._-]{1,80}$/.test(configuredModel) ? configuredModel : "gpt-5.4-mini";
  const generatedAt = nowIso();

  const rowSchema = {
    type: "object",
    additionalProperties: false,
    properties: {
      keyword: { type: "string", minLength: 2, maxLength: 120 },
      groupName: { type: "string", minLength: 2, maxLength: 120 },
      aliases: { type: "array", maxItems: 8, items: { type: "string", maxLength: 120 } },
      category: { type: "string", minLength: 1, maxLength: 120 },
      keywordZh: { type: ["string", "null"], maxLength: 120 },
      imageUrls: { type: "array", maxItems: 6, items: { type: "string", maxLength: 1000 } },
      imageSourceRef: { type: ["string", "null"], maxLength: 1000 },
      purchasePriceMin: { type: ["number", "null"], minimum: 0 },
      purchasePriceMax: { type: ["number", "null"], minimum: 0 },
      purchasePriceCurrency: { type: ["string", "null"], maxLength: 3 },
      purchasePriceUnit: { type: ["string", "null"], maxLength: 40 },
      platform: { type: "string", enum: VALID_PLATFORMS },
      metric: { type: "string", enum: ["attention", "commercial", "competition"] },
      currentValue: { type: ["number", "null"], minimum: 0 },
      previousValue: { type: ["number", "null"], minimum: 0 },
      sampleN: { type: ["integer", "null"], minimum: 0 },
      uniqueActorN: { type: ["integer", "null"], minimum: 0 },
      coverageDays: { type: "integer", enum: [windowDays] },
      sourceKind: { type: "string", enum: ["assistant"] },
      sourceRef: { type: "string", maxLength: 500 },
      geoScope: { type: "string", enum: market === "GLOBAL" ? MARKET_CODES : [market, "GLOBAL"] },
      status: { type: "string", enum: ["ok", "confirmed_zero", "unsupported", "auth_failed", "rate_limited", "collection_error", "geo_unavailable"] },
      missingReason: { type: ["string", "null"], maxLength: 500 },
      collectedAt: { type: "string", enum: [generatedAt] },
    },
    required: [
      "keyword", "groupName", "aliases", "category", "keywordZh", "imageUrls", "imageSourceRef", "purchasePriceMin", "purchasePriceMax",
      "purchasePriceCurrency", "purchasePriceUnit", "platform", "metric", "currentValue",
      "previousValue", "sampleN", "uniqueActorN", "coverageDays", "sourceKind", "sourceRef",
      "geoScope", "status", "missingReason", "collectedAt",
    ],
  };

  const prompt = [
    `为两人外贸团队的情报站整理“${query}”。`,
    `目标市场：${market}；关键词语言：${language}；观察窗口：最近 ${windowDays} 天；生成时间：${generatedAt}。`,
    requestNote ? `用户补充要求：${requestNote}` : "",
    `扩展并归并 ${resultLimit} 个有采购意义、彼此不同的关键词簇，再检索公开、可核验的证据。不要固定缩减为 6–7 个；证据不足的词簇保留空值和准确状态。每个关键词簇为核心来源 ${CORE_PLATFORMS.join("、")} 各返回一行，并从补充电商来源 ${COMMERCE_PLATFORMS.join("、")} 中选择 2–5 个与目标市场最相关且可核验的平台。`,
    "TikTok、Instagram 和 Google Trends 使用 attention；Meta Ads 与补充电商平台使用 commercial；Alibaba.com 使用 competition。每个关键词、平台、指标组合只能出现一次。Google Trends 优先使用官方 Trends 页面或官方 CSV；电商平台优先使用官方 API、授权导出或可直接访问的商品页，并保留直接来源链接。没有证据的平台不要伪造数值。",
    "绝不估算、推断或编造平台数值。只有来源明确给出同一关键词、同一地区和同一时间窗口的非负数值时，status 才可为 ok；确认官方结果为零时才用 confirmed_zero。",
    "任何不满足精确口径的数据都把 currentValue 和 previousValue 设为 null，选择准确的失败/不可用状态，并用 missingReason 说明。空值不等于 0。",
    "每个词簇把准确的简体中文产品名称写入 keywordZh；不要改写原始关键词。sourceRef 填当前平台的直接证据 URL；没有可核验 URL 时留空。每个词簇可从同一条已核验商品/API 证据提供 1–6 张不同的产品图片直链到 imageUrls，并把图片所在的原商品页或 API URL 写入 imageSourceRef。图片搜索结果、图库、品牌 Logo、与 sourceRef 无关的图片不得入库；同一图片 URL 不得复用于不同词簇。无法核验时 imageUrls 填 []、imageSourceRef 填 null。采购价只从可核验的供应商或商品来源提取，写入 purchasePriceMin、purchasePriceMax、purchasePriceCurrency（三位币种代码）和 purchasePriceUnit；无法核验时四项都填 null。sourceKind 固定为 assistant，以表明这是 AI 整理结果。summary 用中文简述覆盖情况和下一步免费补数方式。",
    market === "GLOBAL"
      ? "本次为全球任务。每条证据的 geoScope 必须尽量填写证据实际对应的国家代码；只有来源确实是全球汇总或无法细分国家时才使用 GLOBAL。"
      : `本次为单一国家任务，geoScope 使用 ${market}；只有来源确实是全球汇总时才使用 GLOBAL。`,
  ].filter(Boolean).join("\n");

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      authorization: `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      store: false,
      reasoning: { effort: "low" },
      tools: [{ type: "web_search" }],
      input: prompt,
      max_output_tokens: 24000,
      text: {
        format: {
          type: "json_schema",
          name: "lightlink_radar_result",
          strict: true,
          schema: {
            type: "object",
            additionalProperties: false,
            properties: {
              summary: { type: "string", minLength: 1, maxLength: 1000 },
              rows: { type: "array", minItems: 4, maxItems: resultLimit * 10, items: rowSchema },
            },
            required: ["summary", "rows"],
          },
        },
      },
    }),
  });

  const apiResult = asObject(await response.json());
  if (!response.ok) {
    const apiError = asObject(apiResult.error);
    throw new Error(`OpenAI 调用失败：${String(apiError.message ?? `HTTP ${response.status}`)}`);
  }
  const outputText = extractResponseText(apiResult);
  if (!outputText) throw new Error("OpenAI 没有返回可导入的数据");
  let generated: JsonRecord;
  try {
    generated = asObject(JSON.parse(outputText));
  } catch {
    throw new Error("OpenAI 返回的数据结构无法解析，请重试");
  }
  const rows = Array.isArray(generated.rows) ? generated.rows : [];
  if (!rows.length) throw new Error("OpenAI 没有生成关键词观测");
  const summary = String(generated.summary ?? "AI 已整理关键词和公开证据").trim();
  const result = await importObservations(
    { query, market, language, windowDays, rows },
    {
      mode: scanMode,
      sourceSummary: {
        generator: "OpenAI Responses API",
        model,
        responseId: String(apiResult.id ?? ""),
        generatedAt,
        assistantSummary: summary,
        collectionMode: "assistant_web_research",
        resultLimit,
        scanMode,
      },
    },
  );
  return { ...result, summary, model };
}

async function setClusterStatus(payload: JsonRecord) {
  const db = getRawDb();
  const clusterId = String(payload.clusterId ?? "");
  const status = String(payload.status ?? "");
  if (!clusterId || !["candidate", "watching", "excluded"].includes(status)) throw new Error("状态参数无效");
  const cadenceDays = Number(payload.cadenceDays ?? 7);
  if (!Number.isFinite(cadenceDays) || !Number.isInteger(cadenceDays) || cadenceDays < 1 || cadenceDays > 365) throw new Error("复查周期必须是 1–365 天的整数");
  const cluster = await db.prepare("SELECT id, market FROM keyword_clusters WHERE id = ?").bind(clusterId).first<{ id: string; market: string }>();
  if (!cluster) throw new Error("关键词簇不存在");
  const statements: D1PreparedStatement[] = [
    db.prepare("UPDATE keyword_clusters SET status = ?, updated_at = ? WHERE id = ?").bind(status, nowIso(), clusterId),
  ];
  if (status === "watching") {
    const next = new Date(Date.now() + cadenceDays * 86_400_000).toISOString();
    statements.push(
      db
        .prepare(
          `INSERT INTO watchlist (id, cluster_id, market, cadence_days, enabled, next_run_at)
           VALUES (?, ?, ?, ?, 1, ?)
           ON CONFLICT(cluster_id, market) DO UPDATE SET
             cadence_days = excluded.cadence_days,
             enabled = 1,
             next_run_at = excluded.next_run_at`,
        )
        .bind(crypto.randomUUID(), clusterId, cluster.market, cadenceDays, next),
    );
  } else {
    statements.push(db.prepare("DELETE FROM watchlist WHERE cluster_id = ?").bind(clusterId));
  }
  await db.batch(statements);
  return { clusterId, status };
}

async function mergeClusters(payload: JsonRecord) {
  const db = getRawDb();
  const targetId = String(payload.targetId ?? "");
  const sourceId = String(payload.sourceId ?? "");
  if (!targetId || !sourceId || targetId === sourceId) throw new Error("请选择两个不同的关键词簇");
  const rows = await db
    .prepare("SELECT id, canonical_keyword, aliases, market, language FROM keyword_clusters WHERE id IN (?, ?)")
    .bind(targetId, sourceId)
    .all<{ id: string; canonical_keyword: string; aliases: string; market: string; language: string }>();
  if (rows.results.length !== 2) throw new Error("关键词簇不存在");
  const target = rows.results.find((row) => row.id === targetId)!;
  const source = rows.results.find((row) => row.id === sourceId)!;
  if (target.market !== source.market || target.language !== source.language) throw new Error("只能合并同一市场和语言的词簇");
  const aliases = [...new Set([...jsonArray(target.aliases), source.canonical_keyword, ...jsonArray(source.aliases)].map(String).map(normalizeKeyword))];
  await db.batch([
    db.prepare("UPDATE keyword_clusters SET aliases = ?, cluster_version = printf('%.1f', CAST(cluster_version AS REAL) + 0.1), updated_at = ? WHERE id = ?").bind(JSON.stringify(aliases), nowIso(), targetId),
    db.prepare("UPDATE keyword_clusters SET status = 'excluded', cluster_version = printf('%.1f', CAST(cluster_version AS REAL) + 0.1), updated_at = ? WHERE id = ?").bind(nowIso(), sourceId),
    db.prepare("DELETE FROM watchlist WHERE cluster_id = ?").bind(sourceId),
  ]);
  return { targetId, sourceId, aliases };
}

async function splitCluster(payload: JsonRecord) {
  const db = getRawDb();
  const clusterId = String(payload.clusterId ?? "");
  const alias = normalizeKeyword(String(payload.alias ?? ""));
  if (!clusterId || !alias) throw new Error("请选择要拆分的变体");
  const cluster = await db
    .prepare("SELECT * FROM keyword_clusters WHERE id = ?")
    .bind(clusterId)
    .first<JsonRecord>();
  if (!cluster) throw new Error("关键词簇不存在");
  const aliases: string[] = jsonArray(cluster.aliases).map(String);
  if (!aliases.includes(alias)) throw new Error("该变体不在当前关键词簇中");
  const existing = await db
    .prepare("SELECT id FROM keyword_clusters WHERE canonical_keyword = ? AND market = ? AND language = ?")
    .bind(alias, cluster.market, cluster.language)
    .first<{ id: string }>();
  const splitId = existing?.id ?? crypto.randomUUID();
  const statements: D1PreparedStatement[] = [
    db.prepare("UPDATE keyword_clusters SET aliases = ?, cluster_version = printf('%.1f', CAST(cluster_version AS REAL) + 0.1), updated_at = ? WHERE id = ?")
      .bind(JSON.stringify(aliases.filter((item: string) => item !== alias)), nowIso(), clusterId),
  ];
  if (!existing) {
    statements.push(
      db
        .prepare(
          `INSERT INTO keyword_clusters
            (id, canonical_keyword, group_name, aliases, category, market, language, intent_label, status, updated_at)
           VALUES (?, ?, ?, '[]', ?, ?, ?, '待判断', 'candidate', ?)`,
        )
        .bind(splitId, alias, alias, cluster.category, cluster.market, cluster.language, nowIso()),
    );
  }
  await db.batch(statements);
  return { clusterId, alias, splitId, reused: Boolean(existing) };
}

async function saveSettings(payload: JsonRecord) {
  const db = getRawDb();
  const allowed = ["defaultMarket", "defaultLanguage", "defaultWindowDays", "defaultPlatforms"];
  const entries = Object.entries(asObject(payload.settings)).filter(([key]) => allowed.includes(key));
  if (!entries.length) throw new Error("没有可保存的设置");
  const timestamp = nowIso();
  await db.batch(
    entries.map(([key, value]) =>
      db
        .prepare(
          `INSERT INTO user_settings (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
        )
        .bind(key, typeof value === "string" ? value : JSON.stringify(value), timestamp),
    ),
  );
  return { saved: Object.fromEntries(entries) };
}

async function deleteRun(payload: JsonRecord) {
  const db = getRawDb();
  const runId = String(payload.runId ?? "").trim();
  if (!runId) throw new Error("缺少要删除的任务编号");

  const run = await db
    .prepare("SELECT id, status, source_summary, market, language FROM scan_runs WHERE id = ?")
    .bind(runId)
    .first<{ id: string; status: string; source_summary: string; market: string; language: string }>();
  if (!run) throw new Error("任务不存在或已删除");
  if (run.status === "collecting") throw new Error("执行中的任务不能删除");

  const clusterRows = await db
    .prepare(
      `SELECT cluster_id FROM observations WHERE run_id = ?
       UNION
       SELECT cluster_id FROM score_snapshots WHERE run_id = ?`,
    )
    .bind(runId, runId)
    .all<{ cluster_id: string }>();
  const plannedKeywords = new Set(
    jsonArray(jsonObject(run.source_summary).plannedKeywords).map((item: unknown) => normalizeKeyword(String(item))),
  );
  if (plannedKeywords.size) {
    const plannedClusterRows = await db
      .prepare("SELECT id, canonical_keyword FROM keyword_clusters WHERE market = ? AND language = ?")
      .bind(run.market, run.language)
      .all<{ id: string; canonical_keyword: string }>();
    for (const row of plannedClusterRows.results) {
      if (plannedKeywords.has(normalizeKeyword(row.canonical_keyword))) clusterRows.results.push({ cluster_id: row.id });
    }
  }
  const clusterIds = [...new Set(clusterRows.results.map((row) => row.cluster_id))];

  const statements: D1PreparedStatement[] = [
    db.prepare("DELETE FROM observations WHERE run_id = ?").bind(runId),
    db.prepare("DELETE FROM score_snapshots WHERE run_id = ?").bind(runId),
    db.prepare("DELETE FROM scan_runs WHERE id = ?").bind(runId),
  ];
  for (const clusterId of clusterIds) {
    statements.push(
      db
        .prepare(
          `DELETE FROM keyword_clusters
            WHERE id = ?
              AND NOT EXISTS (SELECT 1 FROM observations WHERE cluster_id = ?)
              AND NOT EXISTS (SELECT 1 FROM score_snapshots WHERE cluster_id = ?)
              AND NOT EXISTS (SELECT 1 FROM watchlist WHERE cluster_id = ?)`,
        )
        .bind(clusterId, clusterId, clusterId, clusterId),
    );
  }
  await db.batch(statements);
  return { runId, deleted: true };
}

async function runDetail(requestedRunId: string | null) {
  const runId = String(requestedRunId ?? "").trim();
  if (!runId) throw new Error("缺少任务编号");
  const db = getRawDb();
  const run = await db.prepare("SELECT * FROM scan_runs WHERE id = ?").bind(runId).first<JsonRecord>();
  if (!run) throw new Error("没有找到该任务");

  const [resultQuery, observationQuery] = await Promise.all([
    db
      .prepare(
        `SELECT c.id AS cluster_id, c.canonical_keyword, c.group_name, c.aliases, c.category,
                c.market, c.language, c.status AS cluster_status,
                s.attention_level, s.momentum, s.commercial_validation, s.buyer_intent,
                s.competition, s.heat, s.opportunity, s.confidence,
                s.conservative_opportunity, s.lifecycle, s.rationale,
                s.anomaly_flags, s.score_version,
                (SELECT COUNT(*) FROM observations o WHERE o.run_id = ? AND o.cluster_id = c.id) AS observation_count,
                (SELECT COUNT(*) FROM observations o WHERE o.run_id = ? AND o.cluster_id = c.id AND o.status IN ('ok', 'confirmed_zero')) AS valid_observation_count,
                (SELECT GROUP_CONCAT(DISTINCT o.platform) FROM observations o WHERE o.run_id = ? AND o.cluster_id = c.id) AS platforms
           FROM score_snapshots s
           JOIN keyword_clusters c ON c.id = s.cluster_id
          WHERE s.run_id = ?
          ORDER BY COALESCE(s.conservative_opportunity, -1) DESC, s.confidence DESC`,
      )
      .bind(runId, runId, runId, runId)
      .all<JsonRecord>(),
    db
      .prepare(
        `SELECT id, cluster_id, platform, metric, current_value, previous_value, sample_n,
                unique_actor_n, coverage_days, source_kind, source_ref, geo_scope,
                status, missing_reason, raw_json, collected_at
           FROM observations WHERE run_id = ? ORDER BY cluster_id, platform, metric`,
      )
      .bind(runId)
      .all<JsonRecord>(),
  ]);
  const images = imagesByCluster(observationQuery.results);
  const keywordZh = keywordZhByCluster(observationQuery.results);
  const purchasePrices = purchasePricesByCluster(observationQuery.results);
  const geoScopes = geoScopesByCluster(observationQuery.results);
  const results = resultQuery.results.map((row) => ({
    ...row,
    aliases: jsonArray(row.aliases),
    anomaly_flags: jsonArray(row.anomaly_flags),
    platforms: String(row.platforms ?? "").split(",").filter(Boolean),
    image_url: images.get(String(row.cluster_id))?.[0]?.url ?? null,
    image_urls: (images.get(String(row.cluster_id)) ?? []).map((image) => image.url),
    images: images.get(String(row.cluster_id)) ?? [],
    keyword_zh: keywordZh.get(String(row.cluster_id)) ?? (String(row.language) === "zh" ? String(row.canonical_keyword) : null),
    purchase_price_min: purchasePrices.get(String(row.cluster_id))?.min ?? null,
    purchase_price_max: purchasePrices.get(String(row.cluster_id))?.max ?? null,
    purchase_price_currency: purchasePrices.get(String(row.cluster_id))?.currency ?? null,
    purchase_price_unit: purchasePrices.get(String(row.cluster_id))?.unit ?? null,
    geo_scopes: geoScopes.get(String(row.cluster_id)) ?? [],
  }));
  const observations = observationQuery.results.map((row) => {
    const observation = { ...row };
    delete observation.raw_json;
    return observation;
  });
  return {
    run: { ...run, source_summary: jsonObject(run.source_summary) },
    results,
    observations,
  };
}

async function exportData(format: string, requestedRunId?: string | null) {
  const db = getRawDb();
  const run = requestedRunId
    ? await db.prepare("SELECT * FROM scan_runs WHERE id = ?").bind(requestedRunId).first<JsonRecord>()
    : await db.prepare("SELECT * FROM scan_runs ORDER BY created_at DESC LIMIT 1").first<JsonRecord>();
  if (!run) return new Response("没有找到可导出的任务", { status: 404 });
  const resultQuery = await db
    .prepare(
      `SELECT c.id AS cluster_id, c.canonical_keyword, c.group_name, c.aliases, c.category,
              c.market, c.language, c.status AS cluster_status,
              s.attention_level, s.momentum, s.commercial_validation, s.buyer_intent,
              s.competition, s.heat, s.opportunity, s.confidence,
              s.conservative_opportunity, s.lifecycle, s.rationale,
              s.anomaly_flags, s.score_version,
              (SELECT COUNT(*) FROM observations o WHERE o.run_id = ? AND o.cluster_id = c.id) AS observation_count,
              (SELECT COUNT(*) FROM observations o WHERE o.run_id = ? AND o.cluster_id = c.id AND o.status IN ('ok', 'confirmed_zero')) AS valid_observation_count,
              (SELECT GROUP_CONCAT(DISTINCT o.platform) FROM observations o WHERE o.run_id = ? AND o.cluster_id = c.id) AS platforms
         FROM score_snapshots s
         JOIN keyword_clusters c ON c.id = s.cluster_id
        WHERE s.run_id = ?
        ORDER BY COALESCE(s.conservative_opportunity, -1) DESC, s.confidence DESC`,
    )
    .bind(String(run.id), String(run.id), String(run.id), String(run.id))
    .all<JsonRecord>();
  const imageRows = await db
    .prepare("SELECT cluster_id, platform, source_ref, geo_scope, raw_json FROM observations WHERE run_id = ?")
    .bind(String(run.id))
    .all<JsonRecord>();
  const images = imagesByCluster(imageRows.results);
  const keywordZh = keywordZhByCluster(imageRows.results);
  const purchasePrices = purchasePricesByCluster(imageRows.results);
  const geoScopes = geoScopesByCluster(imageRows.results);
  const resultRows = resultQuery.results.map<JsonRecord>((row) => ({
    ...row,
    aliases: jsonArray(row.aliases),
    anomaly_flags: jsonArray(row.anomaly_flags),
    image_url: images.get(String(row.cluster_id))?.[0]?.url ?? null,
    image_urls: (images.get(String(row.cluster_id)) ?? []).map((image) => image.url),
    images: images.get(String(row.cluster_id)) ?? [],
    keyword_zh: keywordZh.get(String(row.cluster_id)) ?? (String(row.language) === "zh" ? String(row.canonical_keyword) : null),
    purchase_price_min: purchasePrices.get(String(row.cluster_id))?.min ?? null,
    purchase_price_max: purchasePrices.get(String(row.cluster_id))?.max ?? null,
    purchase_price_currency: purchasePrices.get(String(row.cluster_id))?.currency ?? null,
    purchase_price_unit: purchasePrices.get(String(row.cluster_id))?.unit ?? null,
    geo_scopes: geoScopes.get(String(row.cluster_id)) ?? [],
  }));
  const sourceSummary = jsonObject(run.source_summary);
  const plannedKeywords = Array.isArray(sourceSummary.plannedKeywords) ? sourceSummary.plannedKeywords.map(String) : [];
  const scoredKeywords = new Set(resultRows.map((row) => normalizeKeyword(String(row.canonical_keyword ?? ""))));
  const plannedRows = plannedKeywords
    .filter((keyword) => !scoredKeywords.has(normalizeKeyword(keyword)))
    .map<JsonRecord>((keyword) => ({
      canonical_keyword: keyword,
      group_name: keyword,
      aliases: [],
      category: "未分类",
      image_url: null,
      image_urls: [],
      images: [],
      keyword_zh: String(run.language) === "zh" ? keyword : null,
      purchase_price_min: null,
      purchase_price_max: null,
      purchase_price_currency: null,
      purchase_price_unit: null,
      geo_scopes: [],
      market: String(run.market ?? ""),
      language: String(run.language ?? ""),
      cluster_status: "candidate",
      rationale: "等待导入真实平台证据",
      anomaly_flags: ["missing_evidence"],
      score_version: SCORE_VERSION,
      observation_count: 0,
      valid_observation_count: 0,
      platforms: "",
    }));
  const rows = [...resultRows, ...plannedRows];
  const headers = [
    "任务编号",
    "任务主题",
    "关键词",
    "中文品名",
    "词簇",
    "同义词与语言变体",
    "产品类目",
    "产品主图",
    "全部产品图片",
    "图片来源",
    "市场",
    "数据国家",
    "语言",
    "采购价最低",
    "采购价最高",
    "采购价币种",
    "采购价单位",
    "周期（天）",
    "任务状态",
    "来源平台",
    "有效证据数",
    "证据总数",
    "热度",
    "增长动量",
    "商业验证",
    "采购意图",
    "竞争度",
    "机会分",
    "保守机会分",
    "置信度",
    "阶段",
    "状态",
    "判断说明",
    "异常标记",
    "评分版本",
  ];
  const values = rows.map((row) => [
    run.id,
    run.query,
    row.canonical_keyword,
    row.keyword_zh,
    row.group_name,
    jsonArray(row.aliases).join(" | "),
    row.category,
    row.image_url,
    jsonArray(row.image_urls).join(" | "),
    jsonArray(row.images).map((image: unknown) => {
      const item = asObject(image);
      return [item.platform, item.source_ref].filter(Boolean).join(": ");
    }).filter(Boolean).join(" | "),
    row.market,
    jsonArray(row.geo_scopes).map((scope: unknown) => `${marketNameForCode(String(scope))}（${String(scope)}）`).join(" | "),
    row.language,
    row.purchase_price_min,
    row.purchase_price_max,
    row.purchase_price_currency,
    row.purchase_price_unit,
    run.window_days,
    run.status,
    row.platforms,
    row.valid_observation_count,
    row.observation_count,
    row.heat,
    row.momentum,
    row.commercial_validation,
    row.buyer_intent,
    row.competition,
    row.opportunity,
    row.conservative_opportunity,
    row.confidence,
    row.lifecycle,
    row.cluster_status,
    row.rationale,
    jsonArray(row.anomaly_flags).join(" | "),
    row.score_version,
  ]);
  const filenameBase = `lightlink-radar-${String(run.market ?? "global").toLowerCase()}-${String(run.id).slice(0, 8)}`;

  if (format === "md") {
    const body = [
      `| ${headers.join(" | ")} |`,
      `| ${headers.map(() => "---").join(" | ")} |`,
      ...values.map((row) => `| ${row.map((value) => String(value ?? "—").replaceAll("|", "\\|")).join(" | ")} |`),
    ].join("\n");
    return new Response(body, {
      headers: {
        "content-type": "text/markdown; charset=utf-8",
        "content-disposition": `attachment; filename="${filenameBase}.md"`,
      },
    });
  }

  const csv = `\uFEFF${[headers, ...values].map((row) => row.map(safeCsvCell).join(",")).join("\r\n")}`;
  return new Response(csv, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="${filenameBase}.csv"`,
    },
  });
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    if (url.searchParams.get("view") === "credential_statuses") {
      return Response.json({ credentials: await managedCredentialStatuses() });
    }
    if (url.searchParams.get("view") === "research") {
      return Response.json(await researchDashboard());
    }
    if (url.searchParams.get("view") === "task_center") {
      return Response.json(await taskCenter());
    }
    if (url.searchParams.get("view") === "buyer_library") {
      await ensureResearchSchema();
      return Response.json(await readGlobalBuyerLibrary());
    }
    if (url.searchParams.get("view") === "intelligence_station") {
      return Response.json(await readIntelligenceStation(url));
    }
    if (url.searchParams.get("view") === "opportunity_center") {
      return Response.json(await readOpportunityCenter());
    }
    if (url.searchParams.get("view") === "opportunity_programs") {
      return Response.json(await readOpportunityProgramPage(url));
    }
    if (url.searchParams.get("view") === "opportunity_program_detail") {
      return Response.json(await readOpportunityProgramDetail(url.searchParams.get("programId")));
    }
    if (url.searchParams.get("view") === "trade_data_cache") {
      return Response.json(await readTradeDataCache(url.searchParams.get("opportunityId")));
    }
    if (url.searchParams.get("view") === "opportunity_validation_context") {
      return Response.json(await readOpportunityValidationContext(url.searchParams.get("opportunityId")));
    }
    if (url.searchParams.get("view") === "research_project") {
      return Response.json(await researchProjectDetail(url.searchParams.get("projectId")));
    }
    if (url.searchParams.get("view") === "research_export") {
      return exportResearchProject(url.searchParams.get("projectId"));
    }
    if (url.searchParams.get("view") === "research_odoo_handoff") {
      return exportResearchCandidateHandoff(url.searchParams.get("projectId"), url.searchParams.get("candidateId"));
    }
    if (url.searchParams.get("view") === "run_detail") {
      return Response.json(await runDetail(url.searchParams.get("runId")));
    }
    if (url.searchParams.get("view") === "export") {
      return exportData(url.searchParams.get("format") ?? "csv", url.searchParams.get("runId"));
    }
    return Response.json(await dashboard());
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "读取雷达数据失败" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const payload = asObject(await request.json());
    const action = String(payload.action ?? "");
    const result =
      action === "save_api_credential"
        ? await saveManagedCredential(payload)
        : action === "delete_api_credential"
          ? await deleteManagedCredential(payload)
          : action === "test_api_credential"
            ? await testManagedCredential(payload)
      : action === "seed_demo"
        ? await seedDemo()
        : action === "create_scan"
          ? await createScan(payload)
          : action === "import_observations"
            ? await importObservations(
                payload,
                payload.origin === "assistant"
                  ? {
                      mode: payload.scanMode === "discover" ? "discover" : "seed",
                      sourceSummary: {
                        generator: "Codex / WebMCP",
                        collectionMode: "assistant_collected_import",
                        scanMode: payload.scanMode === "discover" ? "discover" : "seed",
                        resultLimit: Number(payload.resultLimit) || undefined,
                      },
                    }
                  : {},
              )
            : action === "assistant_generate"
              ? await generateWithAssistant(payload)
              : action === "set_cluster_status"
                ? await setClusterStatus(payload)
                : action === "merge_clusters"
                  ? await mergeClusters(payload)
                  : action === "split_cluster"
                    ? await splitCluster(payload)
                    : action === "save_settings"
                      ? await saveSettings(payload)
                      : action === "delete_run"
                        ? await deleteRun(payload)
                        : action === "create_research_project"
                          ? await createResearchProject(payload)
                          : action === "create_research_run"
                            ? await createResearchRun(payload)
                            : action === "import_research_result"
                              ? await importResearchResult(payload)
                              : action === "fail_research_run"
                              ? await failResearchRun(payload)
                               : action === "update_research_candidate"
                                 ? await updateResearchCandidate(payload)
                               : action === "update_research_candidate_assessment"
                                 ? await updateResearchCandidateAssessment(payload)
                               : action === "upsert_research_buyer_profile"
                                 ? await upsertResearchBuyerProfile(payload)
                                : action === "update_research_buyer_family_matrix"
                                  ? await updateResearchBuyerFamilyMatrix(payload)
                                : action === "upsert_global_buyer_profile"
                                  ? await upsertGlobalBuyerProfile(payload)
                                : action === "update_global_buyer_family_matrix"
                                  ? await updateGlobalBuyerFamilyMatrix(payload)
                                : action === "upsert_buyer_persona_category"
                                  ? await upsertBuyerPersonaCategory(payload)
                                : action === "set_buyer_persona_category_active"
                                  ? await setBuyerPersonaCategoryActive(payload)
                                : action === "import_buyer_persona_proposals"
                                  ? await importBuyerPersonaProposals(payload)
                                : action === "review_buyer_persona_proposal"
                                  ? await reviewBuyerPersonaProposal(payload)
                                : action === "upsert_product_track"
                                  ? await upsertProductTrack(payload)
                                : action === "upsert_product_family_master"
                                  ? await upsertProductFamilyMaster(payload)
                                : action === "upsert_persona_product_matrix"
                                  ? await upsertPersonaProductMatrix(payload)
                                : action === "create_opportunity_program"
                                  ? await createOpportunityProgram(payload)
                                : action === "add_opportunity_program_matrices"
                                  ? await addOpportunityProgramMatrices(payload)
                                : action === "void_opportunity_program"
                                  ? await voidOpportunityProgram(payload)
                                : action === "update_opportunity_program_settings"
                                  ? await updateOpportunityProgramSettings(payload)
                                : action === "update_opportunity_round_family"
                                  ? await updateOpportunityRoundFamily(payload)
                                : action === "add_opportunity_customer_feedback"
                                  ? await addOpportunityCustomerFeedback(payload)
                                : action === "decide_opportunity_round"
                                  ? await decideOpportunityRound(payload)
                                : action === "add_opportunity_evidence"
                                  ? await addOpportunityEvidence(payload)
                                : action === "add_opportunity_assessment"
                                  ? await addOpportunityAssessment(payload)
                                : action === "create_market_signal_monitor"
                                  ? await createMarketSignalMonitor(payload)
                                : action === "update_market_signal_monitor_sources"
                                  ? await updateMarketSignalMonitorSources(payload)
                                : action === "set_market_signal_monitor_status"
                                  ? await setMarketSignalMonitorStatus(payload)
                                : action === "execute_market_signal_monitor"
                                  ? await executeMarketSignalMonitor(payload)
                                : action === "simulate_market_signal_monitor"
                                  ? await simulateMarketSignalMonitor(payload)
                                : action === "run_due_market_signal_monitors"
                                  ? await runDueMarketSignalMonitors(payload)
                                : action === "import_market_signals"
                                  ? await importMarketSignals(payload)
                                : action === "upsert_intelligence_event"
                                  ? await upsertIntelligenceEvent(payload)
                                : action === "set_intelligence_event_status"
                                  ? await setIntelligenceEventStatus(payload)
                                : action === "review_intelligence_candidate"
                                  ? await reviewIntelligenceCandidate(payload)
                                : action === "create_trade_data_request"
                                  ? await createTradeDataRequest(payload)
                                : action === "import_trade_data"
                                  ? await importTradeData(payload)
                                : action === "fail_trade_data_request"
                                  ? await failTradeDataRequest(payload)
                                : action === "create_opportunity_validation_request"
                                  ? await createOpportunityValidationRequest(payload)
                                : action === "import_opportunity_validation"
                                  ? await importOpportunityValidation(payload)
                                : action === "fail_opportunity_validation_request"
                                  ? await failOpportunityValidationRequest(payload)
                                : action === "update_research_market"
                                ? await updateResearchMarket(payload)
                              : action === "create_candidate_assist"
                                ? await createCandidateAssist(payload)
                              : action === "import_candidate_assist"
                                ? await importCandidateAssist(payload)
                              : action === "create_candidate_image_assist"
                                ? await createCandidateImageAssist(payload)
                              : action === "import_candidate_images"
                                ? await importCandidateImages(payload)
                              : action === "set_research_project_archived"
                                ? await setResearchProjectArchived(payload)
                              : action === "delete_research_project"
                                ? await deleteResearchProject(payload)
                      : null;
    if (!result) return Response.json({ error: "未知操作" }, { status: 400 });
    return Response.json(result);
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "操作失败" }, { status: 400 });
  }
}
