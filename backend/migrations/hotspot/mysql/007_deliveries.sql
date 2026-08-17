CREATE TABLE IF NOT EXISTS hotspot_report_deliveries (
    delivery_id VARCHAR(191) PRIMARY KEY,
    report_run_id VARCHAR(191) NOT NULL,
    channel VARCHAR(32) NOT NULL,
    content_version CHAR(64) NOT NULL,
    chunk_index INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL,
    attempt INTEGER NOT NULL,
    latency_ms INTEGER,
    error_kind VARCHAR(32),
    error_message VARCHAR(1000),
    response_json TEXT,
    created_at VARCHAR(40) NOT NULL,
    finished_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_report_deliveries (
        report_run_id, channel, content_version, chunk_index
    ),
    CONSTRAINT fk_hotspot_delivery_report
        FOREIGN KEY(report_run_id)
        REFERENCES hotspot_report_runs(report_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_report_deliveries_report
ON hotspot_report_deliveries(report_run_id, chunk_index, status);
-- statement-breakpoint
CREATE INDEX idx_hotspot_report_deliveries_status
ON hotspot_report_deliveries(status, finished_at);
