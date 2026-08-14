CREATE TABLE IF NOT EXISTS hotspot_collection_runs (
    run_id VARCHAR(191) PRIMARY KEY,
    platform VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    freshness VARCHAR(16) NOT NULL,
    window_start VARCHAR(40) NOT NULL,
    window_end VARCHAR(40) NOT NULL,
    started_at VARCHAR(40) NOT NULL,
    finished_at VARCHAR(40) NOT NULL,
    winning_provider_id VARCHAR(191),
    stale_reason VARCHAR(255),
    error_kind VARCHAR(64), error_code VARCHAR(191), error_message TEXT,
    error_retryable TINYINT, error_upstream_status INTEGER,
    created_at VARCHAR(40) NOT NULL,
    INDEX idx_hotspot_runs_platform_window(platform, window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_raw_payloads (
    payload_id VARCHAR(191) PRIMARY KEY,
    run_id VARCHAR(191) NOT NULL,
    provider_id VARCHAR(191) NOT NULL,
    platform VARCHAR(32) NOT NULL,
    attempt_number INTEGER NOT NULL,
    content_type VARCHAR(191), sha256 CHAR(64) NOT NULL,
    body LONGBLOB NOT NULL,
    fetched_at VARCHAR(40) NOT NULL, created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_payload_attempt(run_id, provider_id, attempt_number),
    CONSTRAINT fk_hotspot_payload_run FOREIGN KEY(run_id) REFERENCES hotspot_collection_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_provider_attempts (
    attempt_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(191) NOT NULL, provider_id VARCHAR(191) NOT NULL,
    attempt_number INTEGER NOT NULL,
    started_at VARCHAR(40) NOT NULL, finished_at VARCHAR(40) NOT NULL,
    status VARCHAR(32) NOT NULL, freshness VARCHAR(16) NOT NULL,
    item_count INTEGER NOT NULL, observed_at VARCHAR(40) NOT NULL,
    fetched_at VARCHAR(40) NOT NULL, source_updated_at VARCHAR(40),
    error_kind VARCHAR(64), error_code VARCHAR(191), error_message TEXT,
    error_retryable TINYINT, error_upstream_status INTEGER,
    raw_payload_id VARCHAR(191), metadata_json LONGTEXT NOT NULL,
    UNIQUE KEY uq_hotspot_attempt(run_id, provider_id, attempt_number),
    CONSTRAINT fk_hotspot_attempt_run FOREIGN KEY(run_id) REFERENCES hotspot_collection_runs(run_id),
    CONSTRAINT fk_hotspot_attempt_payload FOREIGN KEY(raw_payload_id) REFERENCES hotspot_raw_payloads(payload_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_raw_items (
    raw_item_id VARCHAR(191) PRIMARY KEY,
    run_id VARCHAR(191) NOT NULL, platform VARCHAR(32) NOT NULL,
    provider_id VARCHAR(191) NOT NULL, provider_attempt_number INTEGER,
    source_item_position INTEGER NOT NULL, is_selected TINYINT NOT NULL,
    freshness VARCHAR(16) NOT NULL, external_id VARCHAR(512),
    title TEXT NOT NULL, url TEXT NOT NULL, rank_value INTEGER,
    hot_score VARCHAR(191), published_at VARCHAR(40),
    observed_at VARCHAR(40) NOT NULL, fetched_at VARCHAR(40) NOT NULL,
    raw_data_json LONGTEXT NOT NULL, raw_payload_sha256 CHAR(64),
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_raw_position(run_id, provider_id, provider_attempt_number, source_item_position),
    INDEX idx_hotspot_raw_items_run(run_id, is_selected, source_item_position),
    CONSTRAINT fk_hotspot_raw_run FOREIGN KEY(run_id) REFERENCES hotspot_collection_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_snapshots (
    snapshot_id VARCHAR(191) PRIMARY KEY, platform VARCHAR(32) NOT NULL,
    window_start VARCHAR(40) NOT NULL, window_end VARCHAR(40) NOT NULL,
    collection_run_id VARCHAR(191) NOT NULL UNIQUE,
    winning_provider_id VARCHAR(191) NOT NULL, freshness VARCHAR(16) NOT NULL,
    observed_at VARCHAR(40) NOT NULL, created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_snapshot_window(platform, window_start),
    INDEX idx_hotspot_snapshots_latest(platform, window_start),
    CONSTRAINT fk_hotspot_snapshot_run FOREIGN KEY(collection_run_id) REFERENCES hotspot_collection_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_snapshot_members (
    snapshot_id VARCHAR(191) NOT NULL, raw_item_id VARCHAR(191) NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY(snapshot_id, raw_item_id),
    UNIQUE KEY uq_hotspot_snapshot_position(snapshot_id, position),
    CONSTRAINT fk_hotspot_member_snapshot FOREIGN KEY(snapshot_id) REFERENCES hotspot_snapshots(snapshot_id),
    CONSTRAINT fk_hotspot_member_raw FOREIGN KEY(raw_item_id) REFERENCES hotspot_raw_items(raw_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_collection_locks (
    lock_key VARCHAR(191) PRIMARY KEY, owner_id VARCHAR(191) NOT NULL,
    acquired_at VARCHAR(40) NOT NULL, expires_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
