-- 002_users_password_hash.sql — add password hash for tenant login

ALTER TABLE users
ADD COLUMN IF NOT EXISTS password_hash TEXT;
