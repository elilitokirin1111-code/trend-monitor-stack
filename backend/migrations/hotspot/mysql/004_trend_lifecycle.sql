CREATE TABLE IF NOT EXISTS hotspot_trend_runs (
    trend_run_id VARCHAR(96) PRIMARY KEY,
    source_clustering_run_id VARCHAR(96) NOT NULL,
    evaluation_id VARCHAR(191) NOT NULL,
    algorithm_version VARCHAR(64) NOT NULL,
    config_hash CHAR(64) NOT NULL,
    config_json LONGTEXT NOT NULL,
    input_hash CHAR(64) NOT NULL,
    evaluated_at VARCHAR(40) NOT NULL,
    status VARCHAR(24) NOT NULL,
    event_count INTEGER NOT NULL,
    complete_count INTEGER NOT NULL,
    partial_count INTEGER NOT NULL,
    started_at VARCHAR(40) NOT NULL,
    finished_at VARCHAR(40) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_trend_run (
        source_clustering_run_id, evaluation_id, algorithm_version, config_hash
    ),
    CONSTRAINT fk_hotspot_trend_clustering FOREIGN KEY(source_clustering_run_id)
        REFERENCES hotspot_clustering_runs(clustering_run_id),
    CONSTRAINT fk_hotspot_trend_evaluation FOREIGN KEY(evaluation_id)
        REFERENCES hotspot_collection_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_trend_runs_evaluated
ON hotspot_trend_runs(evaluated_at, algorithm_version, config_hash);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_trend_states (
    trend_state_id VARCHAR(96) PRIMARY KEY,
    trend_run_id VARCHAR(96) NOT NULL,
    trend_series_id VARCHAR(96) NOT NULL,
    source_event_id VARCHAR(96) NOT NULL,
    predecessor_event_id VARCHAR(96),
    lineage_match_kind VARCHAR(32) NOT NULL,
    lineage_overlap_count INTEGER NOT NULL,
    canonical_title TEXT NOT NULL,
    lifecycle_state VARCHAR(24) NOT NULL,
    previous_state VARCHAR(24),
    trend_score VARCHAR(32) NOT NULL,
    data_quality VARCHAR(24) NOT NULL,
    evaluated_at VARCHAR(40) NOT NULL,
    observation_count INTEGER NOT NULL,
    fresh_observation_count INTEGER NOT NULL,
    stale_observation_count INTEGER NOT NULL,
    fresh_platform_count INTEGER NOT NULL,
    failed_platform_count INTEGER NOT NULL,
    stale_platform_count INTEGER NOT NULL,
    missing_platform_count INTEGER NOT NULL,
    data_completeness VARCHAR(32) NOT NULL,
    current_strength VARCHAR(32) NOT NULL,
    previous_strength VARCHAR(32) NOT NULL,
    earlier_strength VARCHAR(32) NOT NULL,
    velocity VARCHAR(32) NOT NULL,
    acceleration VARCHAR(32) NOT NULL,
    coverage_score VARCHAR(32) NOT NULL,
    persistence_score VARCHAR(32) NOT NULL,
    active_duration_hours VARCHAR(32) NOT NULL,
    latest_fresh_age_hours VARCHAR(32),
    recurrence_gap_hours VARCHAR(32),
    first_fresh_seen_at VARCHAR(40),
    last_fresh_seen_at VARCHAR(40),
    features_json LONGTEXT NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_trend_state(trend_run_id, source_event_id),
    CONSTRAINT fk_hotspot_state_run FOREIGN KEY(trend_run_id)
        REFERENCES hotspot_trend_runs(trend_run_id),
    CONSTRAINT fk_hotspot_state_event FOREIGN KEY(source_event_id)
        REFERENCES hotspot_events(event_id),
    CONSTRAINT fk_hotspot_state_predecessor FOREIGN KEY(predecessor_event_id)
        REFERENCES hotspot_events(event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_trend_states_current
ON hotspot_trend_states(trend_series_id, evaluated_at, lifecycle_state);
-- statement-breakpoint
CREATE INDEX idx_hotspot_trend_states_run
ON hotspot_trend_states(trend_run_id, lifecycle_state, trend_score);
