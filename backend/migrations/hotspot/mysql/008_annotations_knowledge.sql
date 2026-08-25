CREATE TABLE IF NOT EXISTS hotspot_event_annotations (
    annotation_id VARCHAR(96) PRIMARY KEY,
    trend_series_id VARCHAR(96) NOT NULL,
    source_event_id VARCHAR(96) NOT NULL,
    revision INTEGER NOT NULL,
    review_status VARCHAR(24) NOT NULL,
    topic_category VARCHAR(80),
    tags_json TEXT NOT NULL,
    hospitality_relevance VARCHAR(32),
    decision_lane VARCHAR(32),
    notes TEXT,
    summary_override TEXT,
    updated_by VARCHAR(191) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_hotspot_event_annotation_revision(trend_series_id, revision),
    CONSTRAINT fk_hotspot_annotation_event
        FOREIGN KEY(source_event_id) REFERENCES hotspot_events(event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_event_annotations_latest
ON hotspot_event_annotations(trend_series_id, revision, created_at);
-- statement-breakpoint
CREATE TABLE IF NOT EXISTS hotspot_knowledge_syncs (
    sync_id VARCHAR(96) PRIMARY KEY,
    annotation_id VARCHAR(96) NOT NULL,
    trend_series_id VARCHAR(96) NOT NULL,
    source_event_id VARCHAR(96) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    knowledge_base_id VARCHAR(191) NOT NULL,
    knowledge_id VARCHAR(191),
    content_hash CHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    operation VARCHAR(24) NOT NULL,
    parse_status VARCHAR(24),
    error_kind VARCHAR(64),
    error_message VARCHAR(1000),
    response_json LONGTEXT,
    started_at VARCHAR(40) NOT NULL,
    finished_at VARCHAR(40) NOT NULL,
    CONSTRAINT fk_hotspot_sync_annotation
        FOREIGN KEY(annotation_id) REFERENCES hotspot_event_annotations(annotation_id),
    CONSTRAINT fk_hotspot_sync_event
        FOREIGN KEY(source_event_id) REFERENCES hotspot_events(event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- statement-breakpoint
CREATE INDEX idx_hotspot_knowledge_syncs_series
ON hotspot_knowledge_syncs(trend_series_id, provider, knowledge_base_id, finished_at);
-- statement-breakpoint
CREATE INDEX idx_hotspot_knowledge_syncs_content
ON hotspot_knowledge_syncs(annotation_id, content_hash, status);
