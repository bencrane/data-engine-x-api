BEGIN;

CREATE TABLE IF NOT EXISTS entities.fmcsa_carrier_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_type TEXT NOT NULL,
    feed_date DATE NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dot_number TEXT NOT NULL,
    docket_number TEXT,
    entity_key TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    legal_name TEXT,
    physical_state TEXT,
    power_unit_count INTEGER,
    driver_total INTEGER,
    before_values JSONB,
    after_values JSONB,
    signal_details JSONB,
    source_table TEXT NOT NULL,
    source_feed_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(signal_type, feed_date, entity_key)
);

CREATE INDEX IF NOT EXISTS idx_fmcsa_carrier_signals_type_feed_date
    ON entities.fmcsa_carrier_signals(signal_type, feed_date DESC);

CREATE INDEX IF NOT EXISTS idx_fmcsa_carrier_signals_dot_number
    ON entities.fmcsa_carrier_signals(dot_number);

CREATE INDEX IF NOT EXISTS idx_fmcsa_carrier_signals_feed_date
    ON entities.fmcsa_carrier_signals(feed_date DESC);

CREATE INDEX IF NOT EXISTS idx_fmcsa_carrier_signals_severity
    ON entities.fmcsa_carrier_signals(severity);

CREATE INDEX IF NOT EXISTS idx_fmcsa_carrier_signals_state_feed_date
    ON entities.fmcsa_carrier_signals(physical_state, feed_date DESC);

ALTER TABLE entities.fmcsa_carrier_signals ENABLE ROW LEVEL SECURITY;

COMMIT;
