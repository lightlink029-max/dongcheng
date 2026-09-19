CREATE TABLE IF NOT EXISTS `research_projects` (
	`id` text PRIMARY KEY NOT NULL,
	`product_name` text NOT NULL,
	`product_category` text DEFAULT '' NOT NULL,
	`product_description` text DEFAULT '' NOT NULL,
	`target_markets` text DEFAULT '[]' NOT NULL,
	`languages` text DEFAULT '[]' NOT NULL,
	`channels` text DEFAULT '[]' NOT NULL,
	`template_id` text DEFAULT 'general_validation' NOT NULL,
	`objectives` text DEFAULT '' NOT NULL,
	`constraints` text DEFAULT '' NOT NULL,
	`status` text DEFAULT 'planning' NOT NULL,
	`current_stage` text DEFAULT 'product_definition' NOT NULL,
	`progress` integer DEFAULT 10 NOT NULL,
	`summary` text DEFAULT '' NOT NULL,
	`recommendation` text DEFAULT 'pending' NOT NULL,
	`scorecard` text DEFAULT '{}' NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`last_researched_at` text
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_research_projects_updated_at` ON `research_projects` (`updated_at`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_research_projects_status` ON `research_projects` (`status`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `research_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`status` text DEFAULT 'waiting_for_codex' NOT NULL,
	`request_payload` text DEFAULT '{}' NOT NULL,
	`result_payload` text DEFAULT '{}' NOT NULL,
	`source_summary` text DEFAULT '{}' NOT NULL,
	`codex_thread_id` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`completed_at` text,
	FOREIGN KEY (`project_id`) REFERENCES `research_projects`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_research_runs_project_created` ON `research_runs` (`project_id`,`created_at`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `research_evidence` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`run_id` text NOT NULL,
	`section_key` text NOT NULL,
	`source_type` text DEFAULT 'public_web' NOT NULL,
	`source_title` text DEFAULT '' NOT NULL,
	`source_url` text DEFAULT '' NOT NULL,
	`market` text DEFAULT '' NOT NULL,
	`status` text DEFAULT 'available' NOT NULL,
	`excerpt` text DEFAULT '' NOT NULL,
	`metrics` text DEFAULT '{}' NOT NULL,
	`captured_at` text NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `research_projects`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`run_id`) REFERENCES `research_runs`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_research_evidence_project_run` ON `research_evidence` (`project_id`,`run_id`);
