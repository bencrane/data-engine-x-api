from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

PENDING_ICYPEAS_STATUSES = {"NONE", "SCHEDULED", "IN_PROGRESS"}


async def resolve_email(
    *,
    api_key: str | None,
    first_name: str | None,
    last_name: str | None,
    domain_or_company: str | None,
    poll_interval_ms: int,
    max_wait_ms: int,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "icypeas",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }
    if not (first_name or last_name):
        return {
            "attempt": {
                "provider": "icypeas",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_name_input",
            },
            "mapped": None,
        }
    if not domain_or_company:
        return {
            "attempt": {
                "provider": "icypeas",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        submit_res = await client.post(
            "https://app.icypeas.com/api/email-search",
            headers=headers,
            json={
                "firstname": first_name or "",
                "lastname": last_name or "",
                "domainOrCompany": domain_or_company,
            },
        )
        submit_body = parse_json_or_raw(submit_res.text, submit_res.json)
        if submit_res.status_code >= 400:
            return {
                "attempt": {
                    "provider": "icypeas",
                    "action": "resolve_email",
                    "status": "failed",
                    "http_status": submit_res.status_code,
                    "duration_ms": now_ms() - start_ms,
                    "raw_response": submit_body,
                },
                "mapped": None,
            }

        search_id = submit_body.get("item", {}).get("_id")
        if not search_id:
            return {
                "attempt": {
                    "provider": "icypeas",
                    "action": "resolve_email",
                    "status": "failed",
                    "duration_ms": now_ms() - start_ms,
                    "raw_response": submit_body,
                    "error": "missing_search_id",
                },
                "mapped": None,
            }

        deadline = now_ms() + max_wait_ms
        last_body: dict[str, Any] = {}
        final_status: str | None = None
        while now_ms() < deadline:
            read_res = await client.post(
                "https://app.icypeas.com/api/bulk-single-searchs/read",
                headers=headers,
                json={"id": search_id},
            )
            last_body = parse_json_or_raw(read_res.text, read_res.json)
            if read_res.status_code >= 400:
                return {
                    "attempt": {
                        "provider": "icypeas",
                        "action": "resolve_email",
                        "status": "failed",
                        "http_status": read_res.status_code,
                        "duration_ms": now_ms() - start_ms,
                        "raw_response": last_body,
                    },
                    "mapped": None,
                }

            item = (last_body.get("items") or [{}])[0]
            final_status = str(item.get("status") or "")
            if final_status not in PENDING_ICYPEAS_STATUSES:
                emails = item.get("results", {}).get("emails") or []
                resolved_email = None
                if emails and isinstance(emails, list):
                    first_email = emails[0] or {}
                    resolved_email = first_email.get("email")
                return {
                    "attempt": {
                        "provider": "icypeas",
                        "action": "resolve_email",
                        "status": "found" if resolved_email else "not_found",
                        "duration_ms": now_ms() - start_ms,
                        "provider_status": final_status,
                        "search_id": search_id,
                        "raw_response": last_body,
                    },
                    "mapped": {"email": resolved_email},
                }
            await asyncio.sleep(poll_interval_ms / 1000)

    return {
        "attempt": {
            "provider": "icypeas",
            "action": "resolve_email",
            "status": "failed",
            "duration_ms": now_ms() - start_ms,
            "error": "poll_timeout",
            "search_id": search_id,
            "provider_status": final_status,
            "raw_response": last_body,
        },
        "mapped": None,
    }
