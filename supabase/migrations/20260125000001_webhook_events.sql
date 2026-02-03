-- ============================================================================
-- Webhook Events Persistence Layer
-- ============================================================================
-- Provides raw event storage for auditing, analytics, and resilience.
-- Enables replay of failed events and dead letter queue management.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS webhooks;

-- ============================================================================
-- Raw Event Storage (All events persisted before processing)
-- ============================================================================
CREATE TABLE webhooks.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Provider identification
    provider TEXT NOT NULL,           -- 'typeform', 'stripe', 'zoom'
    external_id TEXT,                 -- ID from the provider (for idempotency)
    event_type TEXT NOT NULL,         -- 'form_submission', 'payment.succeeded'

    -- Payload storage
    raw_payload JSONB NOT NULL,       -- Original payload (complete)
    normalized_payload JSONB,         -- OASIS-normalized format

    -- Processing state
    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('received', 'processing', 'processed', 'failed')),
    error_message TEXT,               -- Last error if failed

    -- Traceability
    user_identifier TEXT,             -- Extracted user ID/email
    organization_id UUID,             -- Extracted org context

    -- Timestamps
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,

    -- Deduplication
    CONSTRAINT unique_provider_external_id UNIQUE (provider, external_id)
);

-- Index for status queries (retry logic, dashboards)
CREATE INDEX idx_events_status ON webhooks.events(status);
CREATE INDEX idx_events_provider ON webhooks.events(provider);
CREATE INDEX idx_events_received_at ON webhooks.events(received_at DESC);
CREATE INDEX idx_events_organization ON webhooks.events(organization_id) WHERE organization_id IS NOT NULL;

-- ============================================================================
-- Dead Letter Queue (Failed events for retry)
-- ============================================================================
CREATE TABLE webhooks.dead_letter_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Reference to original event
    event_id UUID NOT NULL REFERENCES webhooks.events(id) ON DELETE CASCADE,

    -- Failure tracking
    error_message TEXT NOT NULL,
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,

    -- Retry scheduling
    next_retry_at TIMESTAMPTZ,
    last_retry_at TIMESTAMPTZ,

    -- Resolution
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'retrying', 'resolved', 'abandoned')),
    resolved_at TIMESTAMPTZ,
    resolution_note TEXT,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for retry scheduler
CREATE INDEX idx_dlq_next_retry ON webhooks.dead_letter_queue(next_retry_at)
    WHERE status IN ('pending', 'retrying');
CREATE INDEX idx_dlq_event_id ON webhooks.dead_letter_queue(event_id);
CREATE INDEX idx_dlq_status ON webhooks.dead_letter_queue(status);

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Calculate next retry time with exponential backoff
CREATE OR REPLACE FUNCTION webhooks.calculate_next_retry(retry_count INT)
RETURNS TIMESTAMPTZ AS $$
BEGIN
    -- Exponential backoff: 2^retry_count seconds (1s, 2s, 4s, 8s, ...)
    RETURN NOW() + (POWER(2, retry_count) || ' seconds')::INTERVAL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Auto-update updated_at on DLQ changes
CREATE OR REPLACE FUNCTION webhooks.update_dlq_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER dlq_updated_at
    BEFORE UPDATE ON webhooks.dead_letter_queue
    FOR EACH ROW
    EXECUTE FUNCTION webhooks.update_dlq_timestamp();

-- ============================================================================
-- RLS Policies (Service-level access only)
-- ============================================================================
ALTER TABLE webhooks.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhooks.dead_letter_queue ENABLE ROW LEVEL SECURITY;

-- Service role has full access (webhook_service uses service_role key)
CREATE POLICY "Service role full access on events"
    ON webhooks.events
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "Service role full access on dlq"
    ON webhooks.dead_letter_queue
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON SCHEMA webhooks IS 'Webhook event storage and dead letter queue';
COMMENT ON TABLE webhooks.events IS 'Raw storage for all incoming webhook events';
COMMENT ON TABLE webhooks.dead_letter_queue IS 'Failed events queued for retry';
COMMENT ON COLUMN webhooks.events.external_id IS 'Provider-assigned event ID for idempotency';
COMMENT ON COLUMN webhooks.events.normalized_payload IS 'OASIS-standardized event format';
COMMENT ON COLUMN webhooks.dead_letter_queue.next_retry_at IS 'Scheduled time for next retry attempt';

-- ============================================================================
-- Extend journey schema for external event tracking
-- ============================================================================

-- Add external_event_id to step_completions for idempotency
ALTER TABLE journeys.step_completions
ADD COLUMN IF NOT EXISTS external_event_id TEXT;

-- Add external_config to steps for mapping form_id -> step
ALTER TABLE journeys.steps
ADD COLUMN IF NOT EXISTS external_config JSONB DEFAULT '{}'::jsonb;

-- Index for fast idempotency lookup
CREATE INDEX IF NOT EXISTS idx_completions_external_event
ON journeys.step_completions(external_event_id)
WHERE external_event_id IS NOT NULL;

-- Index for external config lookup (e.g., find step by form_id)
CREATE INDEX IF NOT EXISTS idx_steps_external_config
ON journeys.steps USING GIN (external_config);

COMMENT ON COLUMN journeys.step_completions.external_event_id IS 'External webhook event ID for idempotency';
COMMENT ON COLUMN journeys.steps.external_config IS 'External provider config (e.g., {"form_id": "xxx"})';
