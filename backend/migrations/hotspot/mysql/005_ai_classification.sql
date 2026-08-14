CREATE TABLE IF NOT EXISTS hotspot_classification_runs (
    classification_run_id VARCHAR(96) PRIMARY KEY,
    source_trend_run_id VARCHAR(96) NOT NULL,
    classifier_version VARCHAR(64) NOT NULL,
    prompt_version VARCHAR(64) NOT NULL,
    model VARCHAR(191) NOT NULL,
    config_hash CHAR(64) NOT NULL,
    config_json LONGTEXT NOT NULL,
    input_hash CHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    event_count INTEGER NOT NULL,
    success_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    started_at VARCHAR(40) NOT NULL,
    finished_at VARCHAR(40) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_classification_run (
        source_trend_run_id, classifier_version, prompt_version,
        model, config_hash, input_hash
    ),
    CONSTRAINT fk_hotspot_classification_trend_run
        FOREIGN KEY(source_trend_run_id)
        REFERENCES hotspot_trend_runs(trend_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_classification_runs_source
ON hotspot_classification_runs(source_trend_run_id, finished_at, status);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_ai_classifications (
    classification_id VARCHAR(96) PRIMARY KEY,
    classification_run_id VARCHAR(96) NOT NULL,
    trend_state_id VARCHAR(96) NOT NULL,
    source_event_id VARCHAR(96) NOT NULL,
    status VARCHAR(24) NOT NULL,
    model VARCHAR(191) NOT NULL,
    prompt_version VARCHAR(64) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    topic_category VARCHAR(40),
    tags_json LONGTEXT,
    hospitality_relevance VARCHAR(24),
    hospitality_score VARCHAR(32),
    confidence VARCHAR(32),
    rationale TEXT,
    summary TEXT,
    evidence_ids_json LONGTEXT,
    decision_json LONGTEXT,
    response_json LONGTEXT,
    response_hash CHAR(64),
    latency_ms INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cost VARCHAR(32),
    error_kind VARCHAR(32),
    error_message TEXT,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_ai_classification(
        classification_run_id, trend_state_id
    ),
    CONSTRAINT fk_hotspot_ai_classification_run
        FOREIGN KEY(classification_run_id)
        REFERENCES hotspot_classification_runs(classification_run_id),
    CONSTRAINT fk_hotspot_ai_classification_trend_state
        FOREIGN KEY(trend_state_id)
        REFERENCES hotspot_trend_states(trend_state_id),
    CONSTRAINT fk_hotspot_ai_classification_event
        FOREIGN KEY(source_event_id)
        REFERENCES hotspot_events(event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_ai_classifications_relevance
ON hotspot_ai_classifications(
    hospitality_relevance, topic_category, status
);
-- statement-breakpoint
CREATE INDEX idx_hotspot_ai_classifications_trend
ON hotspot_ai_classifications(trend_state_id, created_at);
