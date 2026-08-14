CREATE TABLE IF NOT EXISTS hotspot_clustering_runs (
    clustering_run_id TEXT PRIMARY KEY,
    algorithm_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    normalization_rule_version TEXT NOT NULL,
    normalization_config_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    status TEXT NOT NULL,
    input_group_count INTEGER NOT NULL,
    candidate_pair_count INTEGER NOT NULL,
    truncated_candidate_count INTEGER NOT NULL,
    semantic_call_count INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(algorithm_version, config_hash, normalization_config_hash, input_hash)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_clustering_window
ON hotspot_clustering_runs(window_end, algorithm_version, config_hash);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_cluster_candidates (
    candidate_id TEXT PRIMARY KEY,
    clustering_run_id TEXT NOT NULL,
    left_group_id TEXT NOT NULL,
    right_group_id TEXT NOT NULL,
    recall_reasons_json TEXT NOT NULL,
    components_json TEXT NOT NULL,
    deterministic_score TEXT NOT NULL,
    decision TEXT NOT NULL,
    semantic_status TEXT NOT NULL,
    semantic_same_event INTEGER,
    semantic_confidence TEXT,
    semantic_reason TEXT,
    semantic_model_id TEXT,
    semantic_error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(clustering_run_id, left_group_id, right_group_id),
    FOREIGN KEY(clustering_run_id) REFERENCES hotspot_clustering_runs(clustering_run_id),
    FOREIGN KEY(left_group_id) REFERENCES hotspot_dedup_groups(group_id),
    FOREIGN KEY(right_group_id) REFERENCES hotspot_dedup_groups(group_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_candidates_run_decision
ON hotspot_cluster_candidates(clustering_run_id, decision, semantic_status);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_events (
    event_id TEXT PRIMARY KEY,
    clustering_run_id TEXT NOT NULL,
    canonical_title TEXT NOT NULL,
    representative_group_id TEXT NOT NULL,
    representative_normalized_item_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    platforms_json TEXT NOT NULL,
    platform_count INTEGER NOT NULL,
    member_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(clustering_run_id) REFERENCES hotspot_clustering_runs(clustering_run_id),
    FOREIGN KEY(representative_group_id) REFERENCES hotspot_dedup_groups(group_id),
    FOREIGN KEY(representative_normalized_item_id) REFERENCES hotspot_normalized_items(normalized_item_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_events_run
ON hotspot_events(clustering_run_id, last_seen_at, platform_count);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_event_members (
    event_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    normalized_item_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    is_representative INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(event_id, group_id),
    FOREIGN KEY(event_id) REFERENCES hotspot_events(event_id),
    FOREIGN KEY(group_id) REFERENCES hotspot_dedup_groups(group_id),
    FOREIGN KEY(normalized_item_id) REFERENCES hotspot_normalized_items(normalized_item_id),
    FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_event_members_group
ON hotspot_event_members(group_id, event_id);
