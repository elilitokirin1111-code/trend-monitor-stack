CREATE TABLE IF NOT EXISTS hotspot_clustering_runs (
    clustering_run_id VARCHAR(96) PRIMARY KEY,
    algorithm_version VARCHAR(64) NOT NULL,
    config_hash CHAR(64) NOT NULL,
    config_json LONGTEXT NOT NULL,
    normalization_rule_version VARCHAR(64) NOT NULL,
    normalization_config_hash CHAR(64) NOT NULL,
    input_hash CHAR(64) NOT NULL,
    window_start VARCHAR(40) NOT NULL,
    window_end VARCHAR(40) NOT NULL,
    status VARCHAR(24) NOT NULL,
    input_group_count INTEGER NOT NULL,
    candidate_pair_count INTEGER NOT NULL,
    truncated_candidate_count INTEGER NOT NULL,
    semantic_call_count INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    started_at VARCHAR(40) NOT NULL,
    finished_at VARCHAR(40) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_clustering_input (
        algorithm_version, config_hash, normalization_config_hash, input_hash
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_clustering_window
ON hotspot_clustering_runs(window_end, algorithm_version, config_hash);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_cluster_candidates (
    candidate_id VARCHAR(96) PRIMARY KEY,
    clustering_run_id VARCHAR(96) NOT NULL,
    left_group_id VARCHAR(191) NOT NULL,
    right_group_id VARCHAR(191) NOT NULL,
    recall_reasons_json TEXT NOT NULL,
    components_json TEXT NOT NULL,
    deterministic_score VARCHAR(32) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    semantic_status VARCHAR(32) NOT NULL,
    semantic_same_event TINYINT,
    semantic_confidence VARCHAR(32),
    semantic_reason TEXT,
    semantic_model_id VARCHAR(191),
    semantic_error TEXT,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_cluster_candidate (
        clustering_run_id, left_group_id, right_group_id
    ),
    CONSTRAINT fk_hotspot_candidate_run FOREIGN KEY(clustering_run_id)
        REFERENCES hotspot_clustering_runs(clustering_run_id),
    CONSTRAINT fk_hotspot_candidate_left FOREIGN KEY(left_group_id)
        REFERENCES hotspot_dedup_groups(group_id),
    CONSTRAINT fk_hotspot_candidate_right FOREIGN KEY(right_group_id)
        REFERENCES hotspot_dedup_groups(group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_candidates_run_decision
ON hotspot_cluster_candidates(clustering_run_id, decision, semantic_status);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_events (
    event_id VARCHAR(96) PRIMARY KEY,
    clustering_run_id VARCHAR(96) NOT NULL,
    canonical_title TEXT NOT NULL,
    representative_group_id VARCHAR(191) NOT NULL,
    representative_normalized_item_id VARCHAR(191) NOT NULL,
    first_seen_at VARCHAR(40) NOT NULL,
    last_seen_at VARCHAR(40) NOT NULL,
    platforms_json TEXT NOT NULL,
    platform_count INTEGER NOT NULL,
    member_count INTEGER NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    CONSTRAINT fk_hotspot_event_run FOREIGN KEY(clustering_run_id)
        REFERENCES hotspot_clustering_runs(clustering_run_id),
    CONSTRAINT fk_hotspot_event_group FOREIGN KEY(representative_group_id)
        REFERENCES hotspot_dedup_groups(group_id),
    CONSTRAINT fk_hotspot_event_normalized FOREIGN KEY(representative_normalized_item_id)
        REFERENCES hotspot_normalized_items(normalized_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_events_run
ON hotspot_events(clustering_run_id, last_seen_at, platform_count);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_event_members (
    event_id VARCHAR(96) NOT NULL,
    group_id VARCHAR(191) NOT NULL,
    normalized_item_id VARCHAR(191) NOT NULL,
    snapshot_id VARCHAR(191) NOT NULL,
    platform VARCHAR(32) NOT NULL,
    is_representative TINYINT NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    PRIMARY KEY(event_id, group_id),
    CONSTRAINT fk_hotspot_member_event FOREIGN KEY(event_id)
        REFERENCES hotspot_events(event_id),
    CONSTRAINT fk_hotspot_member_group FOREIGN KEY(group_id)
        REFERENCES hotspot_dedup_groups(group_id),
    CONSTRAINT fk_hotspot_member_normalized FOREIGN KEY(normalized_item_id)
        REFERENCES hotspot_normalized_items(normalized_item_id),
    CONSTRAINT fk_hotspot_member_snapshot FOREIGN KEY(snapshot_id)
        REFERENCES hotspot_snapshots(snapshot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_event_members_group
ON hotspot_event_members(group_id, event_id);
