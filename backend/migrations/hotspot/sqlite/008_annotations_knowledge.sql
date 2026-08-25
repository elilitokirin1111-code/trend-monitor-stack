CREATE TABLE IF NOT EXISTS hotspot_event_annotations (
    annotation_id TEXT PRIMARY KEY,
    trend_series_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    review_status TEXT NOT NULL,
    topic_category TEXT,
    tags_json TEXT NOT NULL,
    hospitality_relevance TEXT,
    decision_lane TEXT,
    notes TEXT,
    summary_override TEXT,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(trend_series_id, revision),
    FOREIGN KEY(source_event_id) REFERENCES hotspot_events(event_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_event_annotations_latest
ON hotspot_event_annotations(trend_series_id, revision, created_at);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_knowledge_syncs (
    sync_id TEXT PRIMARY KEY,
    annotation_id TEXT NOT NULL,
    trend_series_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    knowledge_base_id TEXT NOT NULL,
    knowledge_id TEXT,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    operation TEXT NOT NULL,
    parse_status TEXT,
    error_kind TEXT,
    error_message TEXT,
    response_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    FOREIGN KEY(annotation_id) REFERENCES hotspot_event_annotations(annotation_id),
    FOREIGN KEY(source_event_id) REFERENCES hotspot_events(event_id)
);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_knowledge_syncs_series
ON hotspot_knowledge_syncs(trend_series_id, provider, knowledge_base_id, finished_at);
-- statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_hotspot_knowledge_syncs_content
ON hotspot_knowledge_syncs(annotation_id, content_hash, status);
