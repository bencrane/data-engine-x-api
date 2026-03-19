# Auth Model

**Last updated:** 2026-03-18T12:00:00Z

Authentication and multi-tenancy reference for `data-engine-x-api`.

## Multi-Tenancy Model

Hierarchy:

`Org -> Company -> User`

Execution lineage:

`Company -> Submission -> Pipeline Run -> Step Result`

Roles:

- `org_admin`
- `company_admin`
- `member`

Scoping rules:

- Tenant-owned queries are scoped by `org_id`.
- Company-scoped auth paths enforce `company_id` ownership.
- Step registry is global; blueprints are org-scoped.

## Auth Model

All protected endpoints use `Authorization: Bearer <token>`, with four supported auth paths:

1. **Tenant JWT session**
   - Decoded by `decode_tenant_session_jwt(...)`.
   - Produces tenant `AuthContext`.
2. **Tenant API token**
   - SHA-256 hash lookup against `api_tokens`.
   - Produces tenant `AuthContext`.
3. **Super-admin API key**
   - Compared to `SUPER_ADMIN_API_KEY`.
   - Grants `SuperAdminContext` on super-admin endpoints, flexible super-admin routes, `/api/v1/execute` (requires `org_id` + `company_id` in request body), and all entity query endpoints including `/api/v1/entities/companies` and `/api/v1/entities/persons` (requires `org_id` in request body).
4. **Internal service auth (Trigger.dev -> FastAPI)**
   - `Authorization: Bearer <INTERNAL_API_KEY>`
   - `x-internal-org-id: <org_uuid>` (required)
   - `x-internal-company-id: <company_uuid>` (optional)
