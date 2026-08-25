CREATE TABLE IF NOT EXISTS hotspot_normalization_runs (
    normalization_run_id VARCHAR(191) PRIMARY KEY,
    snapshot_id VARCHAR(191) NOT NULL,
    rule_version VARCHAR(191) NOT NULL,
    config_hash CHAR(64) NOT NULL,
    config_json LONGTEXT NOT NULL,
    algorithm_version VARCHAR(191) NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_count INTEGER NOT NULL,
    success_count INTEGER NOT NULL,
    partial_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    started_at VARCHAR(40) NOT NULL,
    finished_at VARCHAR(40) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_normalization_config(snapshot_id, rule_version, config_hash),
    INDEX idx_hotspot_normalization_pending(snapshot_id, rule_version, config_hash),
    CONSTRAINT fk_hotspot_normalization_snapshot FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_normalized_items (
    normalized_item_id VARCHAR(191) PRIMARY KEY,
    normalization_run_id VARCHAR(191) NOT NULL,
    snapshot_id VARCHAR(191) NOT NULL,
    raw_item_id VARCHAR(191) NOT NULL,
    source_position INTEGER NOT NULL,
    platform VARCHAR(32) NOT NULL,
    provider_id VARCHAR(191) NOT NULL,
    rank_value INTEGER,
    external_id_normalized VARCHAR(512),
    normalized_title TEXT,
    title_fingerprint VARCHAR(1024),
    canonical_url TEXT,
    hot_score_value VARCHAR(64),
    hot_score_unit VARCHAR(32),
    published_at VARCHAR(40),
    published_at_precision VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    warnings_json LONGTEXT NOT NULL,
    error_code VARCHAR(191),
    rule_version VARCHAR(191) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_normalized_raw(normalization_run_id, raw_item_id),
    INDEX idx_hotspot_normalized_snapshot(snapshot_id, status, source_position),
    CONSTRAINT fk_hotspot_normalized_run FOREIGN KEY(normalization_run_id) REFERENCES hotspot_normalization_runs(normalization_run_id),
    CONSTRAINT fk_hotspot_normalized_snapshot FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id),
    CONSTRAINT fk_hotspot_normalized_raw FOREIGN KEY(raw_item_id) REFERENCES hotspot_raw_items(raw_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_dedup_groups (
    group_id VARCHAR(191) PRIMARY KEY,
    normalization_run_id VARCHAR(191) NOT NULL,
    snapshot_id VARCHAR(191) NOT NULL,
    algorithm_version VARCHAR(191) NOT NULL,
    representative_normalized_item_id VARCHAR(191) NOT NULL,
    member_count INTEGER NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    INDEX idx_hotspot_dedup_snapshot(snapshot_id, normalization_run_id),
    CONSTRAINT fk_hotspot_dedup_run FOREIGN KEY(normalization_run_id) REFERENCES hotspot_normalization_runs(normalization_run_id),
    CONSTRAINT fk_hotspot_dedup_snapshot FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id),
    CONSTRAINT fk_hotspot_dedup_representative FOREIGN KEY(representative_normalized_item_id) REFERENCES hotspot_normalized_items(normalized_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_dedup_members (
    group_id VARCHAR(191) NOT NULL,
    normalized_item_id VARCHAR(191) NOT NULL,
    is_representative TINYINT NOT NULL,
    match_kind VARCHAR(32) NOT NULL,
    evidence_json LONGTEXT NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    PRIMARY KEY(group_id, normalized_item_id),
    CONSTRAINT fk_hotspot_dedup_member_group FOREIGN KEY(group_id) REFERENCES hotspot_dedup_groups(group_id),
    CONSTRAINT fk_hotspot_dedup_member_item FOREIGN KEY(normalized_item_id) REFERENCES hotspot_normalized_items(normalized_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
