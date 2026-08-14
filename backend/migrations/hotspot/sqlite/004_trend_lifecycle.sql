CREATE TABLE IF NOT EXISTS hotspot_trend_runs (
    trend_run_id TEXT PRIMARY KEY,
    source_clustering_run_id TEXT NOT NULL,
    evaluation_id TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    event_count INTEGER NOT NULL,
    complete_count INTEGER NOT NULL,
    partial_count INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_clustering_run_id, evaluation_id, algorithm_version, config_hash),
    FOREIGN KEY(source_clustering_run_id) REFERENCES hotspot_clustering_runs(clustering_run_id),
    FOREIGN KEY(evaluation_id) REFERENCES hotspot_collection_runs(run_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_trend_runs_evaluated
ON hotspot_trend_runs(evaluated_at, algorithm_version, config_hash);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_trend_states (
    trend_state_id TEXT PRIMARY KEY,
    trend_run_id TEXT NOT NULL,
    trend_series_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    predecessor_event_id TEXT,
    lineage_match_kind TEXT NOT NULL,
    lineage_overlap_count INTEGER NOT NULL,
    canonical_title TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    previous_state TEXT,
    trend_score TEXT NOT NULL,
    data_quality TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL,
    fresh_observation_count INTEGER NOT NULL,
    stale_observation_count INTEGER NOT NULL,
    fresh_platform_count INTEGER NOT NULL,
    failed_platform_count INTEGER NOT NULL,
    stale_platform_count INTEGER NOT NULL,
    missing_platform_count INTEGER NOT NULL,
    data_completeness TEXT NOT NULL,
    current_strength TEXT NOT NULL,
    previous_strength TEXT NOT NULL,
    earlier_strength TEXT NOT NULL,
    velocity TEXT NOT NULL,
    acceleration TEXT NOT NULL,
    coverage_score TEXT NOT NULL,
    persistence_score TEXT NOT NULL,
    active_duration_hours TEXT NOT NULL,
    latest_fresh_age_hours TEXT,
    recurrence_gap_hours TEXT,
    first_fresh_seen_at TEXT,
    last_fresh_seen_at TEXT,
    features_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(trend_run_id, source_event_id),
    FOREIGN KEY(trend_run_id) REFERENCES hotspot_trend_runs(trend_run_id),
    FOREIGN KEY(source_event_id) REFERENCES hotspot_events(event_id),
    FOREIGN KEY(predecessor_event_id) REFERENCES hotspot_events(event_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_trend_states_current
ON hotspot_trend_states(trend_series_id, evaluated_at, lifecycle_state);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_trend_states_run
ON hotspot_trend_states(trend_run_id, lifecycle_state, trend_score);
