CREATE TABLE IF NOT EXISTS hotspot_report_deliveries (
    delivery_id TEXT PRIMARY KEY,
    report_run_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    content_version TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    latency_ms INTEGER,
    error_kind TEXT,
    error_message TEXT,
    response_json TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    UNIQUE(report_run_id, channel, content_version, chunk_index),
    FOREIGN KEY(report_run_id)
        REFERENCES hotspot_report_runs(report_run_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_report_deliveries_report
ON hotspot_report_deliveries(report_run_id, chunk_index, status);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_report_deliveries_status
ON hotspot_report_deliveries(status, finished_at);
