from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from app.config import get_settings
from app.contracts.fmcsa_socrata import FMCSASocrataQueryOutput
from app.providers import socrata


@dataclass(frozen=True)
class FmcsaSocrataDatasetConfig:
    dataset_name: str
    dataset_id: str
    operation_id: str
    dot_field_name: str | None
    dot_field_is_numeric: bool
    mc_lookup_strategy: Literal["company_census_slots", "single_docket_field"]
    mc_field_name: str | None = None


COMPANY_CENSUS_CONFIG = FmcsaSocrataDatasetConfig(
    dataset_name="Company Census File",
    dataset_id="az4n-8mr2",
    operation_id="company.enrich.fmcsa.company_census",
    dot_field_name="DOT_NUMBER",
    dot_field_is_numeric=True,
    mc_lookup_strategy="company_census_slots",
)

CARRIER_ALL_HISTORY_CONFIG = FmcsaSocrataDatasetConfig(
    dataset_name="Carrier - All With History",
    dataset_id="6eyk-hxee",
    operation_id="company.enrich.fmcsa.carrier_all_history",
    dot_field_name="DOT_NUMBER",
    dot_field_is_numeric=False,
    mc_lookup_strategy="single_docket_field",
    mc_field_name="DOCKET_NUMBER",
)

REVOCATION_ALL_HISTORY_CONFIG = FmcsaSocrataDatasetConfig(
    dataset_name="Revocation - All With History",
    dataset_id="sa6p-acbp",
    operation_id="company.enrich.fmcsa.revocation_all_history",
    dot_field_name="DOT_NUMBER",
    dot_field_is_numeric=False,
    mc_lookup_strategy="single_docket_field",
    mc_field_name="DOCKET_NUMBER",
)

INSUR_ALL_HISTORY_CONFIG = FmcsaSocrataDatasetConfig(
    dataset_name="Insur - All With History",
    dataset_id="ypjt-5ydn",
    operation_id="company.enrich.fmcsa.insur_all_history",
    dot_field_name=None,
    dot_field_is_numeric=False,
    mc_lookup_strategy="single_docket_field",
    mc_field_name="prefix_docket_number",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_present_identifier(input_data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if input_data.get(key) is not None:
            return input_data.get(key)

    for nested_key in ("company_profile", "output"):
        nested = _as_dict(input_data.get(nested_key))
        for key in keys:
            if nested.get(key) is not None:
                return nested.get(key)

    for collection_key in ("results", "matched_rows"):
        for item in _as_list(input_data.get(collection_key)):
            item_dict = _as_dict(item)
            for key in keys:
                if item_dict.get(key) is not None:
                    return item_dict.get(key)

    return None


def _extract_dot_number(input_data: dict[str, Any]) -> str | None:
    return socrata.normalize_dot_number(
        _first_present_identifier(input_data, ("dot_number", "dotNumber"))
    )


def _extract_mc_number(input_data: dict[str, Any]) -> str | None:
    return socrata.normalize_mc_number(
        _first_present_identifier(input_data, ("mc_number", "mcNumber", "docket_number", "docketNumber"))
    )


def _build_company_census_mc_query(mc_number: str) -> str:
    mc_numeric_literal = socrata.soql_numeric_literal(mc_number)
    where_clauses = []
    for index in (1, 2, 3):
        prefix_field = socrata.quote_identifier(f"DOCKET{index}PREFIX")
        docket_field = socrata.quote_identifier(f"DOCKET{index}")
        where_clauses.append(
            f"{prefix_field} = {socrata.soql_string_literal('MC')} AND {docket_field} = {mc_numeric_literal}"
        )
    return socrata.build_or_query(where_clauses)


def _build_query_for_identifier(
    config: FmcsaSocrataDatasetConfig,
    *,
    dot_number: str | None,
    mc_number: str | None,
) -> tuple[str, Literal["dot_number", "mc_number"], str] | None:
    if dot_number and config.dot_field_name:
        query = socrata.build_exact_match_query(
            field_name=config.dot_field_name,
            value=dot_number,
            numeric=config.dot_field_is_numeric,
        )
        return query, "dot_number", dot_number

    if mc_number:
        if config.mc_lookup_strategy == "company_census_slots":
            return _build_company_census_mc_query(mc_number), "mc_number", mc_number

        if config.mc_lookup_strategy == "single_docket_field" and config.mc_field_name:
            query = socrata.build_exact_match_query(
                field_name=config.mc_field_name,
                value=socrata.build_mc_docket_value(mc_number),
            )
            return query, "mc_number", mc_number

    return None


def _missing_inputs_for_dataset(
    config: FmcsaSocrataDatasetConfig,
    *,
    dot_number: str | None,
    mc_number: str | None,
) -> list[str]:
    if config.dot_field_name is None:
        return ["mc_number"]

    if dot_number is None and mc_number is None:
        return ["dot_number|mc_number"]

    if dot_number is not None and mc_number is None:
        return ["mc_number"] if config.dot_field_name is None else ["dot_number|mc_number"]

    return ["dot_number|mc_number"]


async def _execute_dataset_query(
    *,
    config: FmcsaSocrataDatasetConfig,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []

    dot_number = _extract_dot_number(input_data)
    mc_number = _extract_mc_number(input_data)
    query_payload = _build_query_for_identifier(
        config,
        dot_number=dot_number,
        mc_number=mc_number,
    )

    if query_payload is None:
        return {
            "run_id": run_id,
            "operation_id": config.operation_id,
            "status": "failed",
            "missing_inputs": _missing_inputs_for_dataset(
                config,
                dot_number=dot_number,
                mc_number=mc_number,
            ),
            "provider_attempts": provider_attempts,
        }

    query, identifier_type_used, identifier_value_used = query_payload
    settings = get_settings()
    adapter_result = await socrata.query_dataset(
        dataset_id=config.dataset_id,
        query=query,
        api_key_id=settings.socrata_api_key_id,
        api_key_secret=settings.socrata_api_key_secret,
    )
    provider_attempts.append(adapter_result["attempt"])

    mapped = _as_dict(adapter_result.get("mapped"))
    matched_rows = [row for row in _as_list(mapped.get("rows")) if isinstance(row, dict)]
    output = FMCSASocrataQueryOutput.model_validate(
        {
            "dataset_name": config.dataset_name,
            "dataset_id": config.dataset_id,
            "identifier_type_used": identifier_type_used,
            "identifier_value_used": identifier_value_used,
            "result_count": len(matched_rows),
            "matched_rows": matched_rows,
            "source_provider": "socrata",
        }
    ).model_dump()

    return {
        "run_id": run_id,
        "operation_id": config.operation_id,
        "status": adapter_result["attempt"].get("status", "failed"),
        "output": output,
        "provider_attempts": provider_attempts,
    }


async def execute_company_enrich_fmcsa_company_census(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_dataset_query(config=COMPANY_CENSUS_CONFIG, input_data=input_data)


async def execute_company_enrich_fmcsa_carrier_all_history(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_dataset_query(config=CARRIER_ALL_HISTORY_CONFIG, input_data=input_data)


async def execute_company_enrich_fmcsa_revocation_all_history(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_dataset_query(config=REVOCATION_ALL_HISTORY_CONFIG, input_data=input_data)


async def execute_company_enrich_fmcsa_insur_all_history(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_dataset_query(config=INSUR_ALL_HISTORY_CONFIG, input_data=input_data)
