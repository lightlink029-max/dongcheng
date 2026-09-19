CREATE TABLE IF NOT EXISTS `research_candidates` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`fingerprint` text NOT NULL,
	`name` text NOT NULL,
	`track_category` text DEFAULT '' NOT NULL,
	`subcategory` text DEFAULT '' NOT NULL,
	`commercial_variant` text DEFAULT '' NOT NULL,
	`target_markets` text DEFAULT '[]' NOT NULL,
	`buyer_types` text DEFAULT '[]' NOT NULL,
	`price_band` text DEFAULT '' NOT NULL,
	`moq` text DEFAULT '' NOT NULL,
	`compliance` text DEFAULT '[]' NOT NULL,
	`risk_level` text DEFAULT 'unknown' NOT NULL,
	`stage` text DEFAULT 'idea' NOT NULL,
	`score` real,
	`rationale` text DEFAULT '' NOT NULL,
	`evidence_status` text DEFAULT 'hypothesis' NOT NULL,
	`source_run_id` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `research_projects`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`source_run_id`) REFERENCES `research_runs`(`id`) ON UPDATE no action ON DELETE set null,
	UNIQUE (`project_id`,`fingerprint`)
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_research_candidates_project_stage` ON `research_candidates` (`project_id`,`stage`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_research_candidates_project_track` ON `research_candidates` (`project_id`,`track_category`);
