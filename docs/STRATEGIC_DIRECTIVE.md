# Strategic Directive: Pragmatic Build Rules for data-engine-x-api

This document is the execution directive for future AI contributors.
Build decisions must follow this file unless explicitly overridden by the project owner.

## Mission

Build `data-engine-x-api` as a **multi-tenant enrichment infrastructure product** with strict technical boundaries and practical delivery speed.

The system must support real business outcomes, not theoretical architecture.

## Non-Negotiables

- **No guessing. Ever.**
  - If a provider contract, field mapping, or policy is unclear, stop and request explicit input.
- **Entity model is fixed to:** `company`, `person`, and `job`.
- **All external provider logic must be wrapped behind canonical operations/actions.**
- **Provider order must be config-driven, not hardcoded.**
- **Raw provider payloads + canonical outputs + attempt lineage must be persisted.**
- **Do not introduce unnecessary abstractions** (e.g., workspaces/playbooks) unless explicitly requested.

## Canonical Structure

- `operation_id`: what the system is doing (stable contract)
- `action`: concrete provider implementation (replaceable)
- `input`: canonical operation input (optional fields allowed)
- `output`: canonical operation output
- `provider_attempts`: ordered audit log of execution attempts

## API Surface Rule

Use `POST /api/v1/execute` as the core API surface.

Request shape:

- `operation_id`
- `entity_type`
- `input`
- optional `options`

Response shape:

- operation run metadata
- canonical output
- provider attempts with status/skip/failure details

## Input-Adaptive Execution Rule

Operations must tolerate varied inputs without brittle failure.

- Each action has explicit eligibility rules.
- Missing optional inputs => action skip with reason.
- Missing operation-minimum inputs => operation failure with `missing_inputs`.

## Current Locked V1 Decisions

### Email

- `person.contact.resolve_email`
  - order: `icypeas -> leadmagic -> parallel(findability fallback)`
  - if email found: verify afterward
- `person.contact.verify_email`
  - order: `millionverifier -> reoon`

Default runtime parameters:

- Icypeas polling interval: `2000ms`
- Icypeas max wait: `45000ms`
- Reoon mode: `power`
- MillionVerifier timeout: `10s`
- Parallel processor: `core`

### Company Profile (next implementation target)

- `company.enrich.profile`
  - planned order: `prospeo -> blitzapi -> companyenrich.com -> leadmagic`
  - blitz bridge behavior:
    - if no LinkedIn URL and domain exists, use `domain-to-linkedin` before `blitz company enrichment`

## Persistence Rule

Every execution must write durable history:

- `operation_runs`
- `operation_attempts`

Persist at minimum:

- org/company/user/auth context
- operation status
- canonical input/output
- provider/action attempts
- provider status + HTTP status + skip reason

## Modularity Rule

- Keep provider clients modular and replaceable.
- Keep provider ordering in a central config/registry.
- Swapping provider order should not require major code rewrites.

## Tooling Boundary Rule

- Trigger.dev is orchestration/runtime.
- Providers (including Parallel) are data/action sources, not orchestrators.
- Modal is optional execution backend only when needed for runtime isolation or heavy compute.

## Security Rule

- Never hardcode API keys in code or docs.
- Use environment variables only.
- If secrets are exposed in chat/logs, rotate immediately.

## Delivery Style Rule

Prefer pragmatic vertical slices:

1. lock contract
2. implement one operation end-to-end
3. persist and validate lineage
4. test with live inputs
5. iterate

Avoid broad rewrites without contract lock and real test evidence.

