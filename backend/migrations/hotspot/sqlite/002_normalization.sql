CREATE TABLE IF NOT EXISTS hotspot_normalization_runs (
    normalization_run_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    status TEXT NOT NULL,
    total_count INTEGER NOT NULL,
    success_count INTEGER NOT NULL,
    partial_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(snapshot_id, rule_version, config_hash),
    FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_normalization_pending
ON hotspot_normalization_runs(snapshot_id, rule_version, config_hash);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_normalized_items (
    normalized_item_id TEXT PRIMARY KEY,
    normalization_run_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    raw_item_id TEXT NOT NULL,
    source_position INTEGER NOT NULL,
    platform TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    rank_value INTEGER,
    external_id_normalized TEXT,
    normalized_title TEXT,
    title_fingerprint TEXT,
    canonical_url TEXT,
    hot_score_value TEXT,
    hot_score_unit TEXT,
    published_at TEXT,
    published_at_precision TEXT NOT NULL,
    status TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    error_code TEXT,
    rule_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(normalization_run_id, raw_item_id),
    FOREIGN KEY(normalization_run_id) REFERENCES hotspot_normalization_runs(normalization_run_id),
    FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id),
    FOREIGN KEY(raw_item_id) REFERENCES hotspot_raw_items(raw_item_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_normalized_snapshot
ON hotspot_normalized_items(snapshot_id, status, source_position);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_normalized_fingerprints
ON hotspot_normalized_items(platform, title_fingerprint, canonical_url);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_dedup_groups (
    group_id TEXT PRIMARY KEY,
    normalization_run_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    representative_normalized_item_id TEXT NOT NULL,
    member_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(normalization_run_id) REFERENCES hotspot_normalization_runs(normalization_run_id),
    FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id),
    FOREIGN KEY(representative_normalized_item_id) REFERENCES hotspot_normalized_items(normalized_item_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_dedup_snapshot
ON hotspot_dedup_groups(snapshot_id, normalization_run_id);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_dedup_members (
    group_id TEXT NOT NULL,
    normalized_item_id TEXT NOT NULL,
    is_representative INTEGER NOT NULL,
    match_kind TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(group_id, normalized_item_id),
    FOREIGN KEY(group_id) REFERENCES hotspot_dedup_groups(group_id),
    FOREIGN KEY(normalized_item_id) REFERENCES hotspot_normalized_items(normalized_item_id)
);
