-- One-time reset for the pre-launch LightLink prototype.
-- Preserves system taxonomy, product/persona matrix seeds, user settings and encrypted credentials.
PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

DELETE FROM market_signal_project_refs;
DELETE FROM intelligence_opportunity_candidates;
DELETE FROM market_signal_versions;
DELETE FROM market_signal_monitor_refs;
DELETE FROM market_signals;
DELETE FROM market_signal_runs;
DELETE FROM intelligence_events;
DELETE FROM market_signal_monitors;

DELETE FROM opportunity_validation_requests;
DELETE FROM trade_data_refresh_requests;
DELETE FROM trade_data_observations;
DELETE FROM opportunity_customer_feedback;
DELETE FROM opportunity_round_families;
DELETE FROM opportunity_rounds;
DELETE FROM opportunity_assessments;
DELETE FROM opportunity_evidence;
DELETE FROM opportunity_change_log;
DELETE FROM opportunity_cases;
DELETE FROM opportunity_dossiers;
DELETE FROM opportunity_programs;

DELETE FROM global_buyer_project_refs;
DELETE FROM global_buyer_family_links;
DELETE FROM global_buyer_profiles;
DELETE FROM research_buyer_family_links;
DELETE FROM research_buyer_profiles;
DELETE FROM research_candidate_activities;
DELETE FROM research_market_activities;
DELETE FROM research_candidates;
DELETE FROM research_evidence;
DELETE FROM research_runs;
DELETE FROM research_projects;
DELETE FROM buyer_persona_ai_proposals;
DELETE FROM commercial_taxonomy_change_log;

DELETE FROM watchlist;
DELETE FROM score_snapshots;
DELETE FROM observations;
DELETE FROM keyword_clusters;
DELETE FROM scan_runs;

COMMIT;
PRAGMA foreign_keys = ON;
