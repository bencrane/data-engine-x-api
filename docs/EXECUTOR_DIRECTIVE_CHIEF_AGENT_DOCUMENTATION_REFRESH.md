# Directive: Chief Agent Documentation Refresh

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** A brand-new Chief Agent should be able to read the key Markdown docs in this repo and come away with an accurate understanding of: (1) its role and constraints, (2) which documents are authoritative for production truth, (3) which docs are design doctrine versus current-state fact, (4) the current architecture/migration reality, and (5) which older docs are historical or lower-authority and should not be trusted as live truth. Right now, that picture is too easy to misread because several docs overlap, some older docs remain visible, and some core onboarding docs still center an older project snapshot more than the current live situation and recent workstreams.

This directive is documentation-only work. You are refreshing the Chief Agent onboarding and reference surface, not changing the product, schema, or runtime behavior.

## Non-Negotiable Truth Boundary

These are the current production-truth documents and must remain the authoritative factual baseline:

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `CLAUDE.md`

Your job is to update the surrounding docs so they point to these clearly and do not contradict them.

Do **not** rewrite those two dated reports to make onboarding cleaner. Improve the onboarding docs around them.

## Existing code to read

- `CLAUDE.md`
- `docs/CHIEF_AGENT_DIRECTIVE.md`
- `docs/WRITING_EXECUTOR_DIRECTIVES.md`
- `docs/STRATEGIC_DIRECTIVE.md`
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`
- `docs/SYSTEM_OVERVIEW.md`
- `docs/ARCHITECTURE.md`
- `docs/AGENT_HANDOFF.md`
- `docs/COMPREHENSION.md`
- `docs/EXECUTOR_DIRECTIVE_DEDICATED_JOB_POSTING_DISCOVERY_WORKFLOW.md`
- `docs/EXECUTOR_DIRECTIVE_VERIFY_ENTITY_QUERY_ENDPOINTS_AFTER_SCHEMA_SPLIT.md`
- `docs/EXECUTOR_DIRECTIVE_INVESTIGATE_PRODUCTION_502_RAILWAY.md`
- `docs/EXECUTOR_DIRECTIVE_FMCSA_DAILY_DIFF_INGESTION_TOP5_FEEDS.md`
- `docs/EXECUTOR_DIRECTIVE_FMCSA_NEXT_BATCH_SNAPSHOTS_AND_HISTORY_FEEDS.md`
- `docs/EXECUTOR_DIRECTIVE_FMCSA_SMS_FEEDS_INGESTION.md`
- `docs/EXECUTOR_DIRECTIVE_FMCSA_REMAINING_CSV_EXPORT_FEEDS.md`
- `docs/FMCSA_TOP5_DAILY_DIFF_MAPPINGS.md`
- `docs/FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_MAPPINGS.md`
- `docs/FMCSA_SMS_FEEDS_PREFLIGHT_AND_MAPPINGS.md`
- `docs/FMCSA_REMAINING_CSV_EXPORT_FEEDS_PREFLIGHT_AND_MAPPINGS.md`

Read the recent directive titles/scope closely enough to understand the current workstreams. A new Chief Agent should not come away thinking the repo is only about the original dedicated-workflow migration if recent directive families now materially include FMCSA ingestion, production reliability investigation, schema verification, and newer workflow families.

---

### Deliverable 1: Documentation Authority Map

Create `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`.

This file should be the concise map a new Chief Agent can use to understand the documentation landscape before reading deeply.

It must:

- define the reading order for a new Chief Agent
- classify documents into clear buckets such as:
  - production-truth reports
  - normative design/doctrine
  - Chief Agent onboarding and workflow
  - technical reference
  - historical/archive
- state explicitly that executor directives are task scopes and calibration artifacts, not proof that the described state is already deployed, live, or verified in production
- call out which docs are intentionally historical and why
- identify which docs the executor intends to update directly in later deliverables

Keep it concise and high-signal. This is a navigation/authority doc, not another broad architecture summary.

Commit standalone.

### Deliverable 2: Refresh Core Chief Agent Docs

Update the core onboarding/authority docs so a new Chief Agent gets an accurate mental model on first read:

- `CLAUDE.md`
- `docs/CHIEF_AGENT_DIRECTIVE.md`
- `docs/WRITING_EXECUTOR_DIRECTIVES.md`
- `docs/STRATEGIC_DIRECTIVE.md` if needed to remove or clearly date-scope stale “current target” language

The goals of these edits are:

- make the Chief Agent role and execution boundary unambiguous
- reduce overlap and contradiction between the core docs
- make truth precedence unmistakable
- clearly distinguish:
  - live production fact
  - target design doctrine
  - in-flight architecture direction
  - historical directive inventory
- make it explicit that existing directive files do not prove deployment or production completion
- update the current-work picture so it reflects newer directive families, not just the early dedicated-workflow migration snapshot

Specific issues that must be addressed:

- `docs/CHIEF_AGENT_DIRECTIVE.md` currently mixes live truth, migration direction, and directive history too loosely
- `docs/CHIEF_AGENT_DIRECTIVE.md` should be updated so a new Chief Agent understands that production still centers on the audited live reality, even if many newer directives describe target architecture or produced-but-not-necessarily-live work
- `CLAUDE.md` should reinforce that directive files are not evidence of deployment or verification
- `docs/WRITING_EXECUTOR_DIRECTIVES.md` should explicitly state that existing directive files are scope documents and examples of format/style, not ground-truth status documents
- `docs/STRATEGIC_DIRECTIVE.md` should not read as if an old “next implementation target” is still the live project priority unless you clearly date-scope or reframe it

Commit standalone.

### Deliverable 3: Update, Demote, or Archive Misleading Secondary Docs

Evaluate and clean up the lower-authority or older docs that could mislead a new Chief Agent:

- `docs/SYSTEM_OVERVIEW.md`
- `docs/ARCHITECTURE.md`
- `docs/AGENT_HANDOFF.md`
- `docs/COMPREHENSION.md`

You must choose and apply a consistent strategy for each:

- update directly if the doc is still worth keeping as an active reference
- or demote/archive it if it is mostly historical and likely to mislead

Allowed approaches:

- keep the file in place but strengthen the warning/status banner substantially
- move clearly historical docs into a consistent archive/historical location if that is cleaner
- leave behind short stubs or redirects if moving files would otherwise create confusion

Requirements:

- use one consistent archival/demotion approach rather than ad hoc treatment
- if you archive/move docs, update the core docs and authority map so the new location and status are clear
- if you keep a doc active, tighten its disclaimers and scope so it cannot easily be mistaken for production truth
- do not silently delete useful historical context

Commit standalone.

### Deliverable 4: Final Consistency Pass

Do a final documentation consistency pass across the key Markdown files touched by this directive.

Verify that:

- no updated core doc contradicts `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- no updated core doc contradicts `docs/DATA_ENGINE_X_ARCHITECTURE.md`
- the Chief Agent reading order is consistent across the refreshed docs
- the distinction between authoritative truth, doctrine, and history is easy to understand
- references to recent workstreams are no longer stale or misleading
- links/paths still work after any archive/demotion moves

If there are small final wording or link fixes needed, make them here.

Commit standalone.

---

**What is NOT in scope:** No code changes. No non-Markdown functional changes. No schema changes. No runtime/config/deploy work. Do not rewrite `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` or `docs/DATA_ENGINE_X_ARCHITECTURE.md` as part of this cleanup. Do not weaken `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` just because production does not yet fully match the doctrine. Do not invent new production claims that are not supported by the audited reports.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the path to `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`, (b) the exact list of core docs updated and the main clarity changes made in each, (c) which secondary docs were updated in place versus demoted/archived, (d) any file moves or archive-location decisions, (e) how you clarified the difference between production truth, doctrine, and historical docs, (f) how you updated the current-work picture for a new Chief Agent, and (g) anything to flag — especially any doc that was too intertwined to cleanly archive without follow-up work.
