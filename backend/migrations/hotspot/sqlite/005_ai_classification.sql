CREATE TABLE IF NOT EXISTS hotspot_classification_runs (
    classification_run_id TEXT PRIMARY KEY,
    source_trend_run_id TEXT NOT NULL,
    classifier_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    event_count INTEGER NOT NULL,
    success_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(
        source_trend_run_id, classifier_version, prompt_version,
        model, config_hash, input_hash
    ),
    FOREIGN KEY(source_trend_run_id)
        REFERENCES hotspot_trend_runs(trend_run_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_classification_runs_source
ON hotspot_classification_runs(source_trend_run_id, finished_at, status);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_ai_classifications (
    classification_id TEXT PRIMARY KEY,
    classification_run_id TEXT NOT NULL,
    trend_state_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    topic_category TEXT,
    tags_json TEXT,
    hospitality_relevance TEXT,
    hospitality_score TEXT,
    confidence TEXT,
    rationale TEXT,
    summary TEXT,
    evidence_ids_json TEXT,
    decision_json TEXT,
    response_json TEXT,
    response_hash TEXT,
    latency_ms INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cost TEXT,
    error_kind TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(classification_run_id, trend_state_id),
    FOREIGN KEY(classification_run_id)
        REFERENCES hotspot_classification_runs(classification_run_id),
    FOREIGN KEY(trend_state_id)
        REFERENCES hotspot_trend_states(trend_state_id),
    FOREIGN KEY(source_event_id)
        REFERENCES hotspot_events(event_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_ai_classifications_relevance
ON hotspot_ai_classifications(
    hospitality_relevance, topic_category, status
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_ai_classifications_trend
ON hotspot_ai_classifications(trend_state_id, created_at);
