from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import SuperAdminContext, get_current_super_admin
from app.config import get_settings
from app.providers import anthropic_provider, gemini, openai_provider
from app.registry.loader import get_all_operations
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.blueprint_assembler import assemble_blueprint

router = APIRouter()


class RegistryOperationsRequest(BaseModel):
    entity_type: str | None = None
    produces_field: str | None = None


@router.post("/registry/operations", response_model=DataEnvelope)
async def list_registry_operations(payload: RegistryOperationsRequest) -> DataEnvelope:
    operations = get_all_operations()

    if payload.entity_type:
        operations = [op for op in operations if op.get("entity_type") == payload.entity_type]

    if payload.produces_field:
        operations = [
            op
            for op in operations
            if isinstance(op.get("produces"), list) and payload.produces_field in op["produces"]
        ]

    return DataEnvelope(data={"operations": operations, "count": len(operations)})


class BlueprintAssembleRequest(BaseModel):
    mode: Literal["fields", "natural_language"]
    entity_type: Literal["company", "person"] = "company"
    desired_fields: list[str] | None = None
    options: dict[str, Any] | None = None
    prompt: str | None = None


def _normalize_extracted_fields(raw_fields: Any) -> list[str]:
    if not isinstance(raw_fields, list):
        return []
    normalized: list[str] = []
    for value in raw_fields:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _normalize_extracted_options(raw_options: Any) -> dict[str, Any]:
    if not isinstance(raw_options, dict):
        return {}
    options: dict[str, Any] = {}

    if isinstance(raw_options.get("include_work_history"), bool):
        options["include_work_history"] = raw_options["include_work_history"]
    if isinstance(raw_options.get("include_pricing_intelligence"), bool):
        options["include_pricing_intelligence"] = raw_options["include_pricing_intelligence"]
    if isinstance(raw_options.get("job_title"), str) and raw_options["job_title"].strip():
        options["job_title"] = raw_options["job_title"].strip()
    if isinstance(raw_options.get("max_results"), int):
        options["max_results"] = max(raw_options["max_results"], 1)

    return options


def _build_nl_assembler_prompt(*, prompt: str, entity_type: str, operations: list[dict[str, Any]]) -> str:
    return (
        "You convert user intent into a blueprint assembly payload.\n"
        "Return JSON only with keys: desired_fields (string[]), options (object).\n"
        "Options keys allowed: include_work_history (bool), max_results (int), job_title (string), include_pricing_intelligence (bool).\n"
        "Use only fields and operations that exist in this registry context.\n"
        f"entity_type: {entity_type}\n"
        f"registry: {json.dumps(operations)}\n"
        f"user_prompt: {prompt}"
    )


async def _extract_fields_and_options_from_prompt(*, prompt: str, entity_type: str) -> tuple[list[str], dict[str, Any]]:
    settings = get_settings()
    operations = get_all_operations()
    llm_prompt = _build_nl_assembler_prompt(prompt=prompt, entity_type=entity_type, operations=operations)

    # Try Anthropic first
    anthropic_result = await anthropic_provider.resolve_structured(
        api_key=settings.anthropic_api_key,
        model="claude-sonnet-4-20250514",
        prompt=llm_prompt,
    )
    mapped = anthropic_result.get("mapped") if isinstance(anthropic_result, dict) else None

    # Fallback to OpenAI
    if not isinstance(mapped, dict):
        openai_result = await openai_provider.resolve_structured(
            api_key=settings.openai_api_key,
            model=settings.llm_fallback_model,
            prompt=llm_prompt,
        )
        mapped = openai_result.get("mapped") if isinstance(openai_result, dict) else None

    # Fallback to Gemini
    if not isinstance(mapped, dict):
        gemini_result = await gemini.resolve_structured(
            api_key=settings.gemini_api_key,
            model=settings.llm_primary_model,
            prompt=llm_prompt,
        )
        mapped = gemini_result.get("mapped") if isinstance(gemini_result, dict) else None

    if not isinstance(mapped, dict):
        return [], {}

    desired_fields = _normalize_extracted_fields(mapped.get("desired_fields"))
    options = _normalize_extracted_options(mapped.get("options"))
    return desired_fields, options


@router.post(
    "/blueprints/assemble",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 401: {"model": ErrorEnvelope}},
)
async def assemble_blueprint_endpoint(
    payload: BlueprintAssembleRequest,
    _super_admin: SuperAdminContext = Depends(get_current_super_admin),
):
    if payload.mode == "fields":
        if not payload.desired_fields:
            return error_response("desired_fields is required when mode=fields", 400)
        assembled = assemble_blueprint(
            desired_fields=payload.desired_fields,
            entity_type=payload.entity_type,
            options=payload.options,
        )
        return DataEnvelope(data=assembled)

    if payload.mode == "natural_language":
        if not payload.prompt or not payload.prompt.strip():
            return error_response("prompt is required when mode=natural_language", 400)
        desired_fields, extracted_options = await _extract_fields_and_options_from_prompt(
            prompt=payload.prompt.strip(),
            entity_type=payload.entity_type,
        )
        merged_options = dict(extracted_options)
        if isinstance(payload.options, dict):
            merged_options.update(payload.options)
        assembled = assemble_blueprint(
            desired_fields=desired_fields,
            entity_type=payload.entity_type,
            options=merged_options,
        )
        assembled["llm_extracted"] = {"desired_fields": desired_fields, "options": extracted_options}
        return DataEnvelope(data=assembled)

    return error_response(f"Unsupported mode: {payload.mode}", 400)
