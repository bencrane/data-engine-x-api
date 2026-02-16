-- 003_api_tokens_user_id.sql — token ownership for API token management

ALTER TABLE api_tokens
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens(user_id);
