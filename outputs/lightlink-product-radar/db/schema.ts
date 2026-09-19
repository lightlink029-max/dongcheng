import { sql } from "drizzle-orm";
import { index, integer, real, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const scanRuns = sqliteTable(
  "scan_runs",
  {
    id: text("id").primaryKey(),
    mode: text("mode", { enum: ["seed", "discover", "import", "assistant"] }).notNull(),
    query: text("query").notNull(),
    market: text("market").notNull(),
    language: text("language").notNull(),
    windowDays: integer("window_days").notNull(),
    status: text("status", {
      enum: ["waiting_for_data", "collecting", "partial", "complete", "failed"],
    }).notNull(),
    isDemo: integer("is_demo", { mode: "boolean" }).notNull().default(false),
    sourceSummary: text("source_summary").notNull().default("{}"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    completedAt: text("completed_at"),
  },
  (table) => [index("idx_scan_runs_created_at").on(table.createdAt)],
);

export const keywordClusters = sqliteTable(
  "keyword_clusters",
  {
    id: text("id").primaryKey(),
    canonicalKeyword: text("canonical_keyword").notNull(),
    groupName: text("group_name").notNull(),
    aliases: text("aliases").notNull().default("[]"),
    category: text("category").notNull().default("未分类"),
    market: text("market").notNull(),
    language: text("language").notNull(),
    intentLabel: text("intent_label").notNull().default("待判断"),
    status: text("status", { enum: ["candidate", "watching", "excluded"] })
      .notNull()
      .default("candidate"),
    clusterVersion: text("cluster_version").notNull().default("1.0"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("uidx_clusters_keyword_market_language").on(
      table.canonicalKeyword,
      table.market,
      table.language,
    ),
    index("idx_clusters_status").on(table.status),
  ],
);

export const observations = sqliteTable(
  "observations",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => scanRuns.id, { onDelete: "cascade" }),
    clusterId: text("cluster_id")
      .notNull()
      .references(() => keywordClusters.id, { onDelete: "cascade" }),
    platform: text("platform").notNull(),
    metric: text("metric", { enum: ["attention", "commercial", "competition"] }).notNull(),
    currentValue: real("current_value"),
    previousValue: real("previous_value"),
    sampleN: integer("sample_n"),
    uniqueActorN: integer("unique_actor_n"),
    coverageDays: integer("coverage_days").notNull(),
    sourceKind: text("source_kind", {
      enum: ["official_api", "official_export", "browser_sample", "open_source", "manual_import", "assistant", "demo"],
    }).notNull(),
    sourceRef: text("source_ref").notNull().default(""),
    geoScope: text("geo_scope").notNull(),
    status: text("status", {
      enum: ["ok", "confirmed_zero", "unsupported", "auth_failed", "rate_limited", "collection_error", "geo_unavailable"],
    }).notNull(),
    missingReason: text("missing_reason"),
    rawJson: text("raw_json").notNull().default("{}"),
    collectedAt: text("collected_at").notNull(),
  },
  (table) => [
    index("idx_observations_run_cluster").on(table.runId, table.clusterId),
    index("idx_observations_cluster_collected").on(table.clusterId, table.collectedAt),
  ],
);

export const scoreSnapshots = sqliteTable(
  "score_snapshots",
  {
    id: text("id").primaryKey(),
    runId: text("run_id")
      .notNull()
      .references(() => scanRuns.id, { onDelete: "cascade" }),
    clusterId: text("cluster_id")
      .notNull()
      .references(() => keywordClusters.id, { onDelete: "cascade" }),
    attentionLevel: real("attention_level"),
    momentum: real("momentum"),
    commercialValidation: real("commercial_validation"),
    buyerIntent: real("buyer_intent").notNull(),
    competition: real("competition"),
    heat: real("heat"),
    opportunity: real("opportunity"),
    confidence: real("confidence").notNull(),
    conservativeOpportunity: real("conservative_opportunity"),
    lifecycle: text("lifecycle").notNull(),
    rationale: text("rationale").notNull(),
    anomalyFlags: text("anomaly_flags").notNull().default("[]"),
    scoreVersion: text("score_version").notNull().default("1.0"),
    calculatedAt: text("calculated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("uidx_scores_run_cluster").on(table.runId, table.clusterId),
    index("idx_scores_opportunity").on(table.opportunity),
  ],
);

export const watchlist = sqliteTable(
  "watchlist",
  {
    id: text("id").primaryKey(),
    clusterId: text("cluster_id")
      .notNull()
      .references(() => keywordClusters.id, { onDelete: "cascade" }),
    market: text("market").notNull(),
    cadenceDays: integer("cadence_days").notNull().default(7),
    enabled: integer("enabled", { mode: "boolean" }).notNull().default(true),
    lastRunAt: text("last_run_at"),
    nextRunAt: text("next_run_at"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [uniqueIndex("uidx_watchlist_cluster_market").on(table.clusterId, table.market)],
);

export const userSettings = sqliteTable("user_settings", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});
