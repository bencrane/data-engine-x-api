-- 004_steps_executor_config.sql — generic executor step configuration

ALTER TABLE steps
ADD COLUMN IF NOT EXISTS url TEXT NOT NULL DEFAULT 'https://example.invalid/step-endpoint',
ADD COLUMN IF NOT EXISTS method TEXT NOT NULL DEFAULT 'POST',
ADD COLUMN IF NOT EXISTS auth_type TEXT,
ADD COLUMN IF NOT EXISTS auth_config JSONB NOT NULL DEFAULT '{}'::jsonb,
ADD COLUMN IF NOT EXISTS payload_template JSONB,
ADD COLUMN IF NOT EXISTS response_mapping JSONB,
ADD COLUMN IF NOT EXISTS timeout_ms INT DEFAULT 30000,
ADD COLUMN IF NOT EXISTS retry_config JSONB NOT NULL DEFAULT '{"max_attempts": 3, "backoff_factor": 2}'::jsonb;
