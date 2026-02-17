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

