from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.email_operations import (
    execute_person_contact_resolve_email,
    execute_person_contact_resolve_mobile_phone,
    execute_person_contact_verify_email,
)
from app.services.company_operations import execute_company_enrich_profile
from app.services.search_operations import execute_company_search, execute_person_search
from app.services.adyntel_operations import (
    execute_company_ads_search_google,
    execute_company_ads_search_linkedin,
    execute_company_ads_search_meta,
)
from app.services.operation_history import persist_operation_execution
from app.services.submission_flow import create_batch_submission_and_trigger_pipeline_runs
from app.services.research_operations import (
    execute_company_research_resolve_g2_url,
    execute_company_research_resolve_pricing_page_url,
)

router = APIRouter()

SUPPORTED_OPERATION_IDS = {
    "person.contact.resolve_email",
    "person.contact.resolve_mobile_phone",
    "person.contact.verify_email",
    "person.search",
    "company.enrich.profile",
    "company.search",
    "company.ads.search.linkedin",
    "company.ads.search.meta",
    "company.ads.search.google",
    "company.research.resolve_g2_url",
    "company.research.resolve_pricing_page_url",
}


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
    company_id: str | None = None
    source: str | None = "api_v1_batch"
    metadata: dict[str, Any] | None = None


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

    return error_response(f"Unsupported operation_id: {payload.operation_id}", 400)


@router.post(
    "/batch/submit",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def batch_submit(
    payload: BatchSubmitRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    if not payload.entities:
        return error_response("entities must contain at least one entity", 400)

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
            org_id=auth.org_id,
            company_id=company_id,
            blueprint_id=payload.blueprint_id,
            entities=[entity.model_dump() for entity in payload.entities],
            source=payload.source,
            metadata=payload.metadata,
            submitted_by_user_id=auth.user_id,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)

    return DataEnvelope(data=result)

