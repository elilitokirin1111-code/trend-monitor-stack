CREATE TABLE IF NOT EXISTS hotspot_collection_runs (
    run_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    status TEXT NOT NULL,
    freshness TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    winning_provider_id TEXT,
    stale_reason TEXT,
    error_kind TEXT,
    error_code TEXT,
    error_message TEXT,
    error_retryable INTEGER,
    error_upstream_status INTEGER,
    created_at TEXT NOT NULL
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_runs_platform_window
ON hotspot_collection_runs(platform, window_start);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_raw_payloads (
    payload_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    content_type TEXT,
    sha256 TEXT NOT NULL,
    body BLOB NOT NULL,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, provider_id, attempt_number),
    FOREIGN KEY(run_id) REFERENCES hotspot_collection_runs(run_id)
);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_provider_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    freshness TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    source_updated_at TEXT,
    error_kind TEXT,
    error_code TEXT,
    error_message TEXT,
    error_retryable INTEGER,
    error_upstream_status INTEGER,
    raw_payload_id TEXT,
    metadata_json TEXT NOT NULL,
    UNIQUE(run_id, provider_id, attempt_number),
    FOREIGN KEY(run_id) REFERENCES hotspot_collection_runs(run_id),
    FOREIGN KEY(raw_payload_id) REFERENCES hotspot_raw_payloads(payload_id)
);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_raw_items (
    raw_item_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    provider_attempt_number INTEGER,
    source_item_position INTEGER NOT NULL,
    is_selected INTEGER NOT NULL,
    freshness TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    rank_value INTEGER,
    hot_score TEXT,
    published_at TEXT,
    observed_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_data_json TEXT NOT NULL,
    raw_payload_sha256 TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, provider_id, provider_attempt_number, source_item_position),
    FOREIGN KEY(run_id) REFERENCES hotspot_collection_runs(run_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_raw_items_run
ON hotspot_raw_items(run_id, is_selected, source_item_position);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    collection_run_id TEXT NOT NULL UNIQUE,
    winning_provider_id TEXT NOT NULL,
    freshness TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(platform, window_start),
    FOREIGN KEY(collection_run_id) REFERENCES hotspot_collection_runs(run_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_snapshots_latest
ON hotspot_snapshots(platform, window_start DESC);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_snapshot_members (
    snapshot_id TEXT NOT NULL,
    raw_item_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY(snapshot_id, raw_item_id),
    UNIQUE(snapshot_id, position),
    FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id),
    FOREIGN KEY(raw_item_id) REFERENCES hotspot_raw_items(raw_item_id)
);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_collection_locks (
    lock_key TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
