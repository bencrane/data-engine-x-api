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


_PERSON_CONTACT_FIELDS = {
    "email",
    "email_status",
    "mobile_phone",
    "mobile_status",
    "verification",
    "contact_info",
    "work_email",
    "personal_email",
}


def _ensure_person_contact_field_for_title_filter(desired_fields: list[str], options: dict[str, Any]) -> list[str]:
    if "job_title" not in options:
        return desired_fields
    if any(field in _PERSON_CONTACT_FIELDS for field in desired_fields):
        return desired_fields
    if "email" in desired_fields:
        return desired_fields
    return [*desired_fields, "email"]


def _extract_available_fields(operations: list[dict[str, Any]], entity_type: str) -> dict[str, list[str]]:
    """Extract and categorize available fields from operations registry."""
    all_fields: set[str] = set()
    for op in operations:
        if op.get("entity_type") != entity_type:
            continue
        produces = op.get("produces")
        if isinstance(produces, list):
            all_fields.update(f for f in produces if isinstance(f, str))

    # Categorize fields
    categories: dict[str, list[str]] = {
        "identity": [],
        "contact": [],
        "company_info": [],
        "location": [],
        "employment": [],
        "financials": [],
        "research": [],
        "ecommerce": [],
        "ads": [],
        "metadata": [],
    }

    for field in sorted(all_fields):
        if field in ("email", "email_status", "mobile_phone", "mobile_status", "verification", "contact_info"):
            categories["contact"].append(field)
        elif field in ("full_name", "first_name", "last_name", "linkedin_url", "headline", "bio", "company_name", "company_domain", "company_website", "company_linkedin_url", "company_linkedin_id", "company_type", "brand_name", "merchant_name"):
            categories["identity"].append(field)
        elif field in ("hq_locality", "hq_country_code", "location", "location_name", "country", "country_code", "city", "top_location_name", "top_location_address", "top_location_city", "top_location_state"):
            categories["location"].append(field)
        elif field in ("current_title", "current_company_name", "current_company_domain", "current_company_linkedin_url", "current_job_title", "past_company_name", "past_company_domain", "past_job_title", "job_title", "seniority", "department", "work_history", "education", "skills", "certifications", "honors", "recommendations", "total_tenure_years"):
            categories["employment"].append(field)
        elif field in ("employee_count", "employee_range", "industry_primary", "industry_derived", "founded_year", "description", "description_raw", "specialties", "follower_count", "connections_count", "logo_url", "technologies", "categories", "technology_count", "features"):
            categories["company_info"].append(field)
        elif field in ("annual_revenue_range", "annual_card_revenue", "card_revenue_period", "card_revenue_period_start", "card_revenue_period_end", "estimated_monthly_sales_cents", "monthly_app_spend_cents", "has_raised_vc", "vc_count", "vc_names", "vcs", "founded_date"):
            categories["financials"].append(field)
        elif field in ("competitors", "competitor_count", "similar_companies", "similar_count", "similarity_score", "customers", "customer_count", "customer_name", "customer_domain", "customer_linkedin_url", "alumni", "alumni_count", "champions", "champion_count", "case_study_url", "testimonial", "g2_url", "pricing_page_url", "confidence"):
            categories["research"].append(field)
        elif field in ("ecommerce_platform", "ecommerce_plan", "product_count", "global_rank", "platform_rank", "installed_apps", "store_created_at", "shipping_carriers", "sales_carriers", "domain_state", "location_count", "top_location_rank_position", "top_location_rank_cohort_size"):
            categories["ecommerce"].append(field)
        elif field in ("ads", "ads_count", "total_ads", "number_of_ads", "continuation_token", "is_last_page", "is_result_complete", "page_id", "search_type", "endpoint_used", "media_type", "active_status"):
            categories["ads"].append(field)
        elif field in ("free_trial", "pricing_visibility", "sales_motion", "pricing_model", "billing_default", "number_of_tiers", "add_ons_offered", "enterprise_tier_exists", "security_compliance_gating", "annual_commitment_required", "plan_naming_style", "custom_pricing_mentioned", "money_back_guarantee", "minimum_seats", "fields_resolved"):
            categories["research"].append(field)
        else:
            categories["metadata"].append(field)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def _build_nl_assembler_prompt(*, prompt: str, entity_type: str, operations: list[dict[str, Any]]) -> str:
    categorized_fields = _extract_available_fields(operations, entity_type)

    field_list_str = ""
    for category, fields in categorized_fields.items():
        field_list_str += f"\n  {category.upper()}: {', '.join(fields)}"

    all_valid_fields = []
    for fields in categorized_fields.values():
        all_valid_fields.extend(fields)

    return f"""You convert user intent into a blueprint assembly payload for {entity_type} enrichment.

TASK: Parse the user's request and return a JSON object with:
- desired_fields: array of field names the user wants (ONLY use fields from the valid list below)
- options: object with optional settings

AVAILABLE FIELDS FOR {entity_type.upper()}:{field_list_str}

VALID FIELD NAMES (use exactly these strings):
{json.dumps(sorted(all_valid_fields))}

OPTIONS (include only if relevant to the request):
- include_work_history (bool): Set true if user wants employment history
- max_results (int): Limit for search results
- job_title (string): Filter by job title
- include_pricing_intelligence (bool): Set true if user wants pricing page analysis

MANDATORY SEMANTIC FIELD MAPPING RULES (YOU MUST APPLY THESE):
- If user mentions "emails", "work email", "email addresses", or "contact info for people" -> include "email" in desired_fields.
- If user mentions "phone", "mobile", or "phone number" -> include "mobile_phone" in desired_fields.
- If user mentions "find people", "decision makers", "search for people", "VPs", "Directors", or similar role-based people search language -> include "email" in desired_fields.
- If user mentions "enrich people", "person profile", or "work history" -> include "current_title", "seniority", and "work_history" in desired_fields.
- If user mentions "pricing" or "pricing page" -> include "pricing_page_url" in desired_fields.
- If user mentions "competitors" -> include "competitors" in desired_fields.
- If user mentions "customers" -> include "customers" in desired_fields.
- If user mentions "alumni" or "former employees" -> include "alumni" in desired_fields.
- If user mentions "technolog" (any form, e.g. "technology", "technologies") or "tech stack" -> include "technologies" in desired_fields.
- If user mentions "VC", "funding", or "investors" -> include "has_raised_vc" in desired_fields.
- If user mentions "similar companies" or "lookalikes" -> include "similar_companies" in desired_fields.
- If user mentions "ads" or "advertising" -> include "ads" in desired_fields.
- If user mentions "ecommerce", "Shopify", or "store" -> include "ecommerce_platform" in desired_fields.

ADDITIONAL MANDATORY RULE:
- If options includes "job_title" and desired_fields has no person contact field, add "email" to desired_fields.

EXAMPLES:

Input: "I need company profiles with LinkedIn and employee count"
Output: {{"desired_fields": ["company_name", "company_domain", "company_linkedin_url", "employee_count", "employee_range"], "options": {{}}}}

Input: "Find people at this company with their emails and phone numbers"
Output: {{"desired_fields": ["full_name", "linkedin_url", "email", "mobile_phone", "current_title"], "options": {{}}}}

Input: "Get competitor analysis and similar companies"
Output: {{"desired_fields": ["competitors", "competitor_count", "similar_companies", "similar_count"], "options": {{}}}}

USER REQUEST: {prompt}

Return JSON only. Do not include any explanation or markdown."""


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
    desired_fields = _ensure_person_contact_field_for_title_filter(desired_fields, options)
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
