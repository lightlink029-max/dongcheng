CREATE TABLE `keyword_clusters` (
	`id` text PRIMARY KEY NOT NULL,
	`canonical_keyword` text NOT NULL,
	`group_name` text NOT NULL,
	`aliases` text DEFAULT '[]' NOT NULL,
	`category` text DEFAULT '未分类' NOT NULL,
	`market` text NOT NULL,
	`language` text NOT NULL,
	`intent_label` text DEFAULT '待判断' NOT NULL,
	`status` text DEFAULT 'candidate' NOT NULL,
	`cluster_version` text DEFAULT '1.0' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uidx_clusters_keyword_market_language` ON `keyword_clusters` (`canonical_keyword`,`market`,`language`);--> statement-breakpoint
CREATE INDEX `idx_clusters_status` ON `keyword_clusters` (`status`);--> statement-breakpoint
CREATE TABLE `observations` (
	`id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`cluster_id` text NOT NULL,
	`platform` text NOT NULL,
	`metric` text NOT NULL,
	`current_value` real,
	`previous_value` real,
	`sample_n` integer,
	`unique_actor_n` integer,
	`coverage_days` integer NOT NULL,
	`source_kind` text NOT NULL,
	`source_ref` text DEFAULT '' NOT NULL,
	`geo_scope` text NOT NULL,
	`status` text NOT NULL,
	`missing_reason` text,
	`raw_json` text DEFAULT '{}' NOT NULL,
	`collected_at` text NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `scan_runs`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`cluster_id`) REFERENCES `keyword_clusters`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_observations_run_cluster` ON `observations` (`run_id`,`cluster_id`);--> statement-breakpoint
CREATE INDEX `idx_observations_cluster_collected` ON `observations` (`cluster_id`,`collected_at`);--> statement-breakpoint
CREATE TABLE `scan_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`mode` text NOT NULL,
	`query` text NOT NULL,
	`market` text NOT NULL,
	`language` text NOT NULL,
	`window_days` integer NOT NULL,
	`status` text NOT NULL,
	`is_demo` integer DEFAULT false NOT NULL,
	`source_summary` text DEFAULT '{}' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`completed_at` text
);
--> statement-breakpoint
CREATE INDEX `idx_scan_runs_created_at` ON `scan_runs` (`created_at`);--> statement-breakpoint
CREATE TABLE `score_snapshots` (
	`id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`cluster_id` text NOT NULL,
	`attention_level` real,
	`momentum` real,
	`commercial_validation` real,
	`buyer_intent` real NOT NULL,
	`competition` real,
	`heat` real,
	`opportunity` real,
	`confidence` real NOT NULL,
	`conservative_opportunity` real,
	`lifecycle` text NOT NULL,
	`rationale` text NOT NULL,
	`anomaly_flags` text DEFAULT '[]' NOT NULL,
	`score_version` text DEFAULT '1.0' NOT NULL,
	`calculated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `scan_runs`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`cluster_id`) REFERENCES `keyword_clusters`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uidx_scores_run_cluster` ON `score_snapshots` (`run_id`,`cluster_id`);--> statement-breakpoint
CREATE INDEX `idx_scores_opportunity` ON `score_snapshots` (`opportunity`);--> statement-breakpoint
CREATE TABLE `user_settings` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE TABLE `watchlist` (
	`id` text PRIMARY KEY NOT NULL,
	`cluster_id` text NOT NULL,
	`market` text NOT NULL,
	`cadence_days` integer DEFAULT 7 NOT NULL,
	`enabled` integer DEFAULT true NOT NULL,
	`last_run_at` text,
	`next_run_at` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`cluster_id`) REFERENCES `keyword_clusters`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uidx_watchlist_cluster_market` ON `watchlist` (`cluster_id`,`market`);