CREATE TABLE IF NOT EXISTS hotspot_report_runs (
    report_run_id VARCHAR(191) PRIMARY KEY,
    report_run_id_base CHAR(64) NOT NULL,
    report_type VARCHAR(16) NOT NULL,
    period_start VARCHAR(40) NOT NULL,
    period_end VARCHAR(40) NOT NULL,
    report_version VARCHAR(64) NOT NULL,
    config_hash CHAR(64) NOT NULL,
    config_json TEXT NOT NULL,
    input_hash CHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    data_quality VARCHAR(32) NOT NULL,
    stale_platforms_json TEXT NOT NULL,
    missing_platforms_json TEXT NOT NULL,
    content MEDIUMTEXT NOT NULL,
    template VARCHAR(64) NOT NULL,
    source_trend_run_id VARCHAR(191) NOT NULL,
    source_classification_run_id VARCHAR(191),
    attempt INTEGER NOT NULL,
    started_at VARCHAR(40) NOT NULL,
    finished_at VARCHAR(40) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_report_runs (
        report_run_id_base, report_type, period_start, report_version,
        config_hash, input_hash, attempt
    ),
    CONSTRAINT fk_hotspot_report_trend
        FOREIGN KEY(source_trend_run_id)
        REFERENCES hotspot_trend_runs(trend_run_id),
    CONSTRAINT fk_hotspot_report_classification
        FOREIGN KEY(source_classification_run_id)
        REFERENCES hotspot_classification_runs(classification_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_report_runs_type_period
ON hotspot_report_runs(report_type, period_start DESC, finished_at DESC);
-- statement-breakpoint
CREATE INDEX idx_hotspot_report_runs_base
ON hotspot_report_runs(report_run_id_base, attempt);
