Root cause is in routing, not env var parsing.
app/config.py is correct for this key:
field is super_admin_api_key
expected env var is SUPER_ADMIN_API_KEY
no env_prefix is set in SettingsConfigDict, so there is no APP_/other prefix requirement.
app/auth/super_admin.py does a direct raw compare:
if token != settings.super_admin_api_key: return None
no hashing, no normalization, no prefixing.
Dockerfile is correctly using doppler run -- ..., so runtime injection path is valid.
Railway deploy logs show requests hitting POST /api/v1/execute and returning 401, but no Doppler runtime error.
Critical diagnosis
Your assumption about /api/v1/execute auth flow is incorrect in current code.
/api/v1/execute uses:
auth: AuthContext = Depends(get_current_auth)
not _resolve_flexible_auth.
So super-admin API key is never considered for /api/v1/execute. It only accepts:
internal API key
tenant session JWT
tenant API token (hashed lookup)
That exactly explains the behavior: super-admin key fails, then it falls through to tenant auth failure, returning {"error":"Invalid authentication token"}.
Why super-admin key works elsewhere
In the same file, /api/v1/batch/submit and /api/v1/batch/status do use _resolve_flexible_auth, so super-admin auth is supported there.
Railway/Doppler state check
From Railway tooling, the linked service/environment is data-engine-x-api / production. Railway variables show only DOPPLER_TOKEN + Railway metadata (expected, since app secrets come from Doppler at startup). So nothing indicates a config-prefix mismatch in app code.
What to do next
If intended behavior is “super-admin key should work on /api/v1/execute”, this is a code change request, not a deploy config issue.
If intended behavior is tenant-only execute, then current behavior is correct and callers should use tenant JWT/API token for /api/v1/execute.
If you want, I can patch /api/v1/execute to support super-admin safely (with explicit org_id/company_id handling so operation history remains valid and tenant scoping is unambiguous).