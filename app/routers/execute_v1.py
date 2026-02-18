from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.email_operations import (
    execute_person_contact_resolve_email,
    execute_person_contact_resolve_mobile_phone,
    execute_person_contact_verify_email,
)
from app.services.company_operations import (
    execute_company_enrich_fmcsa,
    execute_company_enrich_card_revenue,
    execute_company_enrich_ecommerce,
    execute_company_enrich_profile,
    execute_company_enrich_technographics,
)
from app.services.person_enrich_operations import execute_person_enrich_profile
from app.services.search_operations import (
    execute_company_search,
    execute_company_search_fmcsa,
    execute_company_search_ecommerce,
    execute_person_search,
)
from app.services.adyntel_operations import (
    execute_company_ads_search_google,
    execute_company_ads_search_linkedin,
    execute_company_ads_search_meta,
)
from app.services.operation_history import persist_operation_execution
from app.services.submission_flow import create_batch_submission_and_trigger_pipeline_runs
from app.services.research_operations import (
    execute_company_research_check_vc_funding,
    execute_company_research_discover_competitors,
    execute_company_research_find_similar_companies,
    execute_company_research_lookup_alumni,
    execute_company_research_lookup_champion_testimonials,
    execute_company_research_lookup_champions,
    execute_company_research_lookup_customers,
    execute_company_research_resolve_g2_url,
    execute_company_research_resolve_pricing_page_url,
)
from app.services.sec_filing_operations import (
    execute_company_analyze_sec_10k,
    execute_company_analyze_sec_10q,
    execute_company_analyze_sec_8k_executive,
    execute_company_research_fetch_sec_filings,
)
from app.services.pricing_intelligence_operations import (
    execute_company_derive_pricing_intelligence,
)
from app.services.change_detection_operations import (
    execute_company_derive_detect_changes,
    execute_person_derive_detect_changes,
)
from app.services.theirstack_operations import (
    execute_company_enrich_hiring_signals,
    execute_company_enrich_tech_stack,
    execute_company_search_by_job_postings,
    execute_company_search_by_tech_stack,
)
from app.services.shovels_operations import (
    execute_address_residents,
    execute_contractor_employees,
    execute_contractor_enrich,
    execute_contractor_search,
    execute_permit_search,
)
from app.services.courtlistener_operations import (
    execute_company_research_check_court_filings,
    execute_company_research_get_docket_detail,
    execute_company_signal_bankruptcy_filings,
)

router = APIRouter()

_security = HTTPBearer(auto_error=False)

SUPPORTED_OPERATION_IDS = {
    "person.contact.resolve_email",
    "person.contact.resolve_mobile_phone",
    "person.contact.verify_email",
    "person.search",
    "person.enrich.profile",
    "person.derive.detect_changes",
    "company.enrich.profile",
    "company.enrich.fmcsa",
    "company.enrich.card_revenue",
    "company.enrich.ecommerce",
    "company.enrich.technographics",
    "company.search",
    "company.search.fmcsa",
    "company.search.ecommerce",
    "company.ads.search.linkedin",
    "company.ads.search.meta",
    "company.ads.search.google",
    "company.research.resolve_g2_url",
    "company.research.resolve_pricing_page_url",
    "company.research.discover_competitors",
    "company.research.find_similar_companies",
    "company.research.lookup_customers",
    "company.research.lookup_alumni",
    "company.research.lookup_champions",
    "company.research.lookup_champion_testimonials",
    "company.research.check_vc_funding",
    "company.research.check_court_filings",
    "company.signal.bankruptcy_filings",
    "company.research.get_docket_detail",
    "company.research.fetch_sec_filings",
    "company.analyze.sec_10k",
    "company.analyze.sec_10q",
    "company.analyze.sec_8k_executive",
    "company.derive.pricing_intelligence",
    "company.derive.detect_changes",
    "company.search.by_tech_stack",
    "company.search.by_job_postings",
    "company.enrich.tech_stack",
    "company.enrich.hiring_signals",
    "permit.search",
    "contractor.enrich",
    "contractor.search",
    "contractor.search.employees",
    "address.search.residents",
}


async def _resolve_flexible_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> AuthContext | SuperAdminContext:
    """Accept super-admin API key or tenant auth (JWT / API token)."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    try:
        return await get_current_super_admin(credentials)
    except HTTPException:
        pass
    return await get_current_auth(request=request, credentials=credentials)


class ExecuteV1Request(BaseModel):
    operation_id: str
    entity_type: Literal["person", "company"]
    input: dict[str, Any]
    options: dict[str, Any] | None = None


class BatchEntityInput(BaseModel):
    entity_type: Literal["person", "company"]
    input: dict[str, Any]


class BatchSubmitRequest(BaseModel):
    blueprint_id: str
    entities: list[BatchEntityInput]
    org_id: str | None = None
    company_id: str | None = None
    source: str | None = "api_v1_batch"
    metadata: dict[str, Any] | None = None


class BatchStatusRequest(BaseModel):
    submission_id: str
    org_id: str | None = None


@router.post(
    "/execute",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def execute_v1(
    payload: ExecuteV1Request,
    auth: AuthContext = Depends(get_current_auth),
):
    if payload.operation_id not in SUPPORTED_OPERATION_IDS:
        return error_response(f"Unsupported operation_id: {payload.operation_id}", 400)
    if payload.operation_id.startswith("person.") and payload.entity_type != "person":
        return error_response("entity_type must be person for person operations", 400)
    if payload.operation_id.startswith("company.") and payload.entity_type != "company":
        return error_response("entity_type must be company for company operations", 400)
    if payload.operation_id in {
        "permit.search",
        "contractor.enrich",
        "contractor.search",
        "contractor.search.employees",
        "address.search.residents",
    } and payload.entity_type != "company":
        return error_response("entity_type must be company for shovels operations", 400)
    if auth.role in {"company_admin", "member"} and not auth.company_id:
        return error_response("Company-scoped user missing company_id", 403)

    if payload.operation_id == "person.contact.resolve_email":
        result = await execute_person_contact_resolve_email(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "person.contact.resolve_mobile_phone":
        result = await execute_person_contact_resolve_mobile_phone(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "person.contact.verify_email":
        result = await execute_person_contact_verify_email(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "person.search":
        result = await execute_person_search(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "person.enrich.profile":
        result = await execute_person_enrich_profile(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "person.derive.detect_changes":
        result = await execute_person_derive_detect_changes(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.enrich.profile":
        result = await execute_company_enrich_profile(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.enrich.fmcsa":
        result = await execute_company_enrich_fmcsa(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.enrich.card_revenue":
        result = await execute_company_enrich_card_revenue(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.enrich.ecommerce":
        result = await execute_company_enrich_ecommerce(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.enrich.technographics":
        result = await execute_company_enrich_technographics(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.search":
        result = await execute_company_search(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.search.fmcsa":
        result = await execute_company_search_fmcsa(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.search.ecommerce":
        result = await execute_company_search_ecommerce(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.ads.search.linkedin":
        result = await execute_company_ads_search_linkedin(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.ads.search.meta":
        result = await execute_company_ads_search_meta(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.ads.search.google":
        result = await execute_company_ads_search_google(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.resolve_g2_url":
        result = await execute_company_research_resolve_g2_url(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.resolve_pricing_page_url":
        result = await execute_company_research_resolve_pricing_page_url(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.discover_competitors":
        result = await execute_company_research_discover_competitors(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.find_similar_companies":
        result = await execute_company_research_find_similar_companies(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.lookup_customers":
        result = await execute_company_research_lookup_customers(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.lookup_alumni":
        result = await execute_company_research_lookup_alumni(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.lookup_champions":
        result = await execute_company_research_lookup_champions(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.lookup_champion_testimonials":
        result = await execute_company_research_lookup_champion_testimonials(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.check_vc_funding":
        result = await execute_company_research_check_vc_funding(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.check_court_filings":
        result = await execute_company_research_check_court_filings(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.signal.bankruptcy_filings":
        result = await execute_company_signal_bankruptcy_filings(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.get_docket_detail":
        result = await execute_company_research_get_docket_detail(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.research.fetch_sec_filings":
        result = await execute_company_research_fetch_sec_filings(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.analyze.sec_10k":
        result = await execute_company_analyze_sec_10k(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.analyze.sec_10q":
        result = await execute_company_analyze_sec_10q(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.analyze.sec_8k_executive":
        result = await execute_company_analyze_sec_8k_executive(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.derive.pricing_intelligence":
        result = await execute_company_derive_pricing_intelligence(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.derive.detect_changes":
        result = await execute_company_derive_detect_changes(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.search.by_tech_stack":
        result = await execute_company_search_by_tech_stack(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.search.by_job_postings":
        result = await execute_company_search_by_job_postings(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.enrich.tech_stack":
        result = await execute_company_enrich_tech_stack(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "company.enrich.hiring_signals":
        result = await execute_company_enrich_hiring_signals(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "permit.search":
        result = await execute_permit_search(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "contractor.enrich":
        result = await execute_contractor_enrich(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "contractor.search":
        result = await execute_contractor_search(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "contractor.search.employees":
        result = await execute_contractor_employees(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    if payload.operation_id == "address.search.residents":
        result = await execute_address_residents(input_data=payload.input)
        persist_operation_execution(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_payload=payload.input,
            result=result,
        )
        return DataEnvelope(data=result)

    return error_response(f"Unsupported operation_id: {payload.operation_id}", 400)


@router.post(
    "/batch/submit",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def batch_submit(
    payload: BatchSubmitRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    if not payload.entities:
        return error_response("entities must contain at least one entity", 400)

    is_super_admin = isinstance(auth, SuperAdminContext)

    if is_super_admin:
        if not payload.org_id:
            return error_response("org_id is required for super-admin batch submit", 400)
        if not payload.company_id:
            return error_response("company_id is required for super-admin batch submit", 400)
        org_id = payload.org_id
        company_id = payload.company_id
    else:
        org_id = auth.org_id
        if auth.role in {"company_admin", "member"}:
            if not auth.company_id:
                return error_response("Company-scoped user missing company_id", 403)
            company_id = auth.company_id
            if payload.company_id and payload.company_id != auth.company_id:
                return error_response("Forbidden company access", 403)
        else:
            company_id = payload.company_id
            if not company_id:
                return error_response("company_id is required for org-scoped users", 400)

    invalid_entities = []
    for idx, entity in enumerate(payload.entities):
        if entity.entity_type not in {"company", "person"}:
            invalid_entities.append(f"{idx}:invalid_entity_type")
        if not isinstance(entity.input, dict):
            invalid_entities.append(f"{idx}:input_must_be_object")
    if invalid_entities:
        return error_response(
            f"Invalid entities: {', '.join(invalid_entities)}",
            400,
        )

    try:
        result = await create_batch_submission_and_trigger_pipeline_runs(
            org_id=org_id,
            company_id=company_id,
            blueprint_id=payload.blueprint_id,
            entities=[entity.model_dump() for entity in payload.entities],
            source=payload.source,
            metadata=payload.metadata,
            submitted_by_user_id=auth.user_id if hasattr(auth, "user_id") else None,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)

    return DataEnvelope(data=result)


def _map_pipeline_status(status: str | None) -> str:
    if status == "succeeded":
        return "completed"
    if status == "running":
        return "running"
    if status in {"failed", "canceled"}:
        return "failed"
    return "pending"


def _extract_final_context_for_run(
    *,
    client,
    org_id: str,
    pipeline_run_id: str,
    mapped_status: str,
) -> dict[str, Any] | None:
    if mapped_status != "completed":
        return None
    step_results = (
        client.table("step_results")
        .select("step_position, status, output_payload")
        .eq("pipeline_run_id", pipeline_run_id)
        .eq("org_id", org_id)
        .order("step_position", desc=True)
        .execute()
    )
    for step in step_results.data:
        if step.get("status") == "succeeded":
            payload_data = step.get("output_payload") or {}
            if isinstance(payload_data, dict):
                final_context = payload_data.get("cumulative_context")
                if isinstance(final_context, dict):
                    return final_context
    return None


def _build_pipeline_run_tree(run_rows: list[dict[str, Any]], run_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a submission run tree with arbitrary parent/child depth."""
    roots: list[dict[str, Any]] = []
    for run in run_rows:
        run_payload = run_map[run["id"]]
        parent_id = run_payload.get("parent_pipeline_run_id")
        if not parent_id:
            roots.append(run_payload)
            continue
        parent_payload = run_map.get(parent_id)
        if parent_payload is None:
            # Keep orphaned runs visible rather than dropping them from status output.
            roots.append(run_payload)
            continue
        parent_payload.setdefault("children", []).append(run_payload)
    return roots


@router.post(
    "/batch/status",
    response_model=DataEnvelope,
    responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def batch_status(
    payload: BatchStatusRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    is_super_admin = isinstance(auth, SuperAdminContext)

    client = get_supabase_client()
    query = client.table("submissions").select("*").eq("id", payload.submission_id)
    if is_super_admin:
        if payload.org_id:
            query = query.eq("org_id", payload.org_id)
    else:
        query = query.eq("org_id", auth.org_id)

    submission_result = query.limit(1).execute()
    if not submission_result.data:
        return error_response("Submission not found", 404)

    submission = submission_result.data[0]
    org_id = submission["org_id"]

    if not is_super_admin and auth.role in {"company_admin", "member"} and submission.get("company_id") != auth.company_id:
        return error_response("Forbidden submission access", 403)

    runs_result = (
        client.table("pipeline_runs")
        .select("*")
        .eq("submission_id", payload.submission_id)
        .eq("org_id", org_id)
        .order("created_at")
        .execute()
    )
    run_rows = runs_result.data
    run_map: dict[str, dict[str, Any]] = {}
    summary = {"total": len(run_rows), "completed": 0, "failed": 0, "pending": 0, "running": 0}

    for run in run_rows:
        mapped_status = _map_pipeline_status(run.get("status"))
        summary[mapped_status] = summary.get(mapped_status, 0) + 1
        entity_meta = (run.get("blueprint_snapshot") or {}).get("entity") or {}
        run_payload = {
            "entity_index": entity_meta.get("index"),
            "entity_type": entity_meta.get("entity_type"),
            "pipeline_run_id": run["id"],
            "parent_pipeline_run_id": run.get("parent_pipeline_run_id"),
            "trigger_run_id": run.get("trigger_run_id"),
            "status": mapped_status,
            "final_context": _extract_final_context_for_run(
                client=client,
                org_id=org_id,
                pipeline_run_id=run["id"],
                mapped_status=mapped_status,
            ),
            "error_message": run.get("error_message"),
            "children": [],
        }
        run_map[run["id"]] = run_payload
    per_entity = _build_pipeline_run_tree(run_rows, run_map)

    return DataEnvelope(
        data={
            "submission": {
                "id": submission["id"],
                "org_id": submission["org_id"],
                "company_id": submission.get("company_id"),
                "blueprint_id": submission["blueprint_id"],
                "status": submission["status"],
                "source": submission.get("source"),
                "metadata": submission.get("metadata"),
                "created_at": submission.get("created_at"),
                "updated_at": submission.get("updated_at"),
            },
            "summary": summary,
            "runs": per_entity,
        }
    )
