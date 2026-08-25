CREATE TABLE IF NOT EXISTS hotspot_report_runs (
    report_run_id TEXT PRIMARY KEY,
    report_run_id_base TEXT NOT NULL,
    report_type TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    report_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    data_quality TEXT NOT NULL,
    stale_platforms_json TEXT NOT NULL,
    missing_platforms_json TEXT NOT NULL,
    content TEXT NOT NULL,
    template TEXT NOT NULL,
    source_trend_run_id TEXT NOT NULL,
    source_classification_run_id TEXT,
    attempt INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(report_run_id_base, report_type, period_start, report_version,
           config_hash, input_hash, attempt),
    FOREIGN KEY(source_trend_run_id)
        REFERENCES hotspot_trend_runs(trend_run_id),
    FOREIGN KEY(source_classification_run_id)
        REFERENCES hotspot_classification_runs(classification_run_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_report_runs_type_period
ON hotspot_report_runs(report_type, period_start DESC, finished_at DESC);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_report_runs_base
ON hotspot_report_runs(report_run_id_base, attempt);
