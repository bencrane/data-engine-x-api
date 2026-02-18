from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from app.registry.loader import get_all_operations, get_operations_that_produce

_COST_RANK = {"free": 0, "low": 1, "medium": 2, "high": 3}
_CATEGORY_RANK = {"enrich": 0, "contact": 1, "derive": 2, "research": 3, "search": 4, "ads": 5}

_DEFAULT_INITIAL_FIELDS: dict[str, set[str]] = {
    "company": {"company_domain", "company_name", "company_website", "company_linkedin_url", "source_company_id"},
    "person": {
        "first_name",
        "last_name",
        "full_name",
        "linkedin_url",
        "email",
        "company_domain",
        "company_name",
        "company_linkedin_url",
        "profile_url",
        "work_email",
        "personal_email",
        "person_id",
    },
}

_COMPANY_TO_PERSON_SIGNAL_FIELDS = {"email", "mobile_phone"}
_ECOMMERCE_SPECIFIC_FIELDS = {
    "ecommerce_platform",
    "ecommerce_plan",
    "estimated_monthly_sales_cents",
    "installed_apps",
    "product_count",
    "platform_rank",
    "global_rank",
    "monthly_app_spend_cents",
    "store_created_at",
    "shipping_carriers",
    "sales_carriers",
    "domain_state",
    "merchant_name",
    "contact_info",
}


def _operation_sort_key(operation: dict[str, Any]) -> tuple[int, int, str]:
    return (
        _COST_RANK.get(str(operation.get("cost_tier")), 99),
        _CATEGORY_RANK.get(str(operation.get("category")), 99),
        str(operation.get("operation_id")),
    )


def _operation_cost_rank(operation: dict[str, Any]) -> int:
    return _COST_RANK.get(str(operation.get("cost_tier")), 99)


def _operation_produces_set(operation: dict[str, Any]) -> set[str]:
    produces = operation.get("produces")
    if not isinstance(produces, list):
        return set()
    return {field for field in produces if isinstance(field, str)}


def _operation_desired_coverage(operation: dict[str, Any], desired_fields: set[str]) -> int:
    if not desired_fields:
        return 0
    return len(_operation_produces_set(operation) & desired_fields)


def _operations_by_id() -> dict[str, dict[str, Any]]:
    return {str(op["operation_id"]): op for op in get_all_operations() if isinstance(op.get("operation_id"), str)}


def _parse_options(options: dict[str, Any] | None) -> dict[str, Any]:
    opts = options or {}
    parsed: dict[str, Any] = {}
    parsed["include_work_history"] = bool(opts.get("include_work_history"))
    parsed["include_pricing_intelligence"] = bool(opts.get("include_pricing_intelligence"))
    if isinstance(opts.get("max_results"), int):
        parsed["max_results"] = max(opts["max_results"], 1)
    if isinstance(opts.get("job_title"), str) and opts["job_title"].strip():
        parsed["job_title"] = opts["job_title"].strip()
    return parsed


def _expr_parts(expr: str) -> list[list[str]]:
    and_parts = [part.strip() for part in expr.split("+") if part.strip()]
    parsed: list[list[str]] = []
    for and_part in and_parts:
        parsed.append([alt.strip() for alt in and_part.split("|") if alt.strip()])
    return parsed


def _expr_satisfied(expr: str, available_fields: set[str]) -> bool:
    for alternatives in _expr_parts(expr):
        if not any(alt in available_fields for alt in alternatives):
            return False
    return True


def _first_missing_from_expr(expr: str, available_fields: set[str]) -> str | None:
    for alternatives in _expr_parts(expr):
        if any(alt in available_fields for alt in alternatives):
            continue
        return alternatives[0] if alternatives else None
    return None


def _best_operation_for_field(
    field: str,
    preferred_entity_type: str | None = None,
    desired_fields: set[str] | None = None,
) -> dict[str, Any] | None:
    desired_set = desired_fields or set()
    candidates = get_operations_that_produce(field)
    if preferred_entity_type:
        preferred = [op for op in candidates if op.get("entity_type") == preferred_entity_type]
        if preferred:
            candidates = preferred
    if field not in _ECOMMERCE_SPECIFIC_FIELDS:
        non_ecommerce_candidates = [op for op in candidates if op.get("operation_id") != "company.enrich.ecommerce"]
        if non_ecommerce_candidates:
            candidates = non_ecommerce_candidates
    if not candidates:
        return None
    candidates.sort(
        key=lambda operation: (
            _operation_cost_rank(operation),
            -_operation_desired_coverage(operation, desired_set),
            _CATEGORY_RANK.get(str(operation.get("category")), 99),
            str(operation.get("operation_id")),
        )
    )
    return candidates[0]


def _required_inputs(operation: dict[str, Any]) -> tuple[list[str], list[str]]:
    required = operation.get("required_inputs")
    if not isinstance(required, dict):
        return [], []
    all_of = [item for item in required.get("all_of", []) if isinstance(item, str)]
    any_of = [item for item in required.get("any_of", []) if isinstance(item, str)]
    return all_of, any_of


def _produced_fields_for_operations(operation_ids: set[str], operation_map: dict[str, dict[str, Any]]) -> set[str]:
    produced: set[str] = set()
    for operation_id in operation_ids:
        operation = operation_map.get(operation_id)
        if not operation:
            continue
        values = operation.get("produces")
        if isinstance(values, list):
            produced.update(field for field in values if isinstance(field, str))
    return produced


def _required_inputs_satisfied_for_selection(
    *,
    operation_ids: set[str],
    operation_map: dict[str, dict[str, Any]],
    initial_fields: set[str],
) -> bool:
    for operation_id in operation_ids:
        operation = operation_map.get(operation_id)
        if not operation:
            continue
        available_fields = initial_fields | _produced_fields_for_operations(operation_ids - {operation_id}, operation_map)
        all_of, any_of = _required_inputs(operation)
        if any(not _expr_satisfied(expr, available_fields) for expr in all_of):
            return False
        if any_of and not any(_expr_satisfied(expr, available_fields) for expr in any_of):
            return False
    return True


def _all_desired_fields_covered(
    *,
    operation_ids: set[str],
    operation_map: dict[str, dict[str, Any]],
    desired_fields: set[str],
    entity_type: str,
) -> bool:
    for field in desired_fields:
        producers: list[dict[str, Any]] = []
        for operation_id in operation_ids:
            operation = operation_map.get(operation_id)
            if not operation:
                continue
            if field in _operation_produces_set(operation):
                producers.append(operation)
        if not producers:
            return False
        if entity_type == "company" and field not in _ECOMMERCE_SPECIFIC_FIELDS:
            if all(op.get("operation_id") == "company.enrich.ecommerce" for op in producers):
                available_non_ecommerce = [
                    op
                    for op in get_operations_that_produce(field)
                    if op.get("operation_id") != "company.enrich.ecommerce"
                    and op.get("entity_type") == "company"
                ]
                if available_non_ecommerce:
                    return False
    return True


def _redundancy_candidate_sort_key(
    operation_id: str,
    operation_map: dict[str, dict[str, Any]],
    desired_fields: set[str],
    entity_type: str,
) -> tuple[int, int, int, int, str]:
    operation = operation_map.get(operation_id, {})
    ecommerce_for_standard_company_fields = (
        entity_type == "company"
        and operation_id == "company.enrich.ecommerce"
        and desired_fields.isdisjoint(_ECOMMERCE_SPECIFIC_FIELDS)
    )
    produced = _operation_produces_set(operation)
    desired_contribution = len(produced & desired_fields)
    return (
        0 if ecommerce_for_standard_company_fields else 1,
        -_operation_cost_rank(operation),
        desired_contribution,
        len(produced),
        operation_id,
    )


def _deduplicate_redundant_operations(
    *,
    operation_ids: set[str],
    operation_map: dict[str, dict[str, Any]],
    desired_fields: set[str],
    initial_fields: set[str],
    pinned_operation_ids: set[str],
    entity_type: str,
) -> set[str]:
    deduped_ids = set(operation_ids)
    changed = True
    while changed:
        changed = False
        for operation_id in sorted(
            deduped_ids,
            key=lambda op_id: _redundancy_candidate_sort_key(
                op_id,
                operation_map,
                desired_fields,
                entity_type,
            ),
        ):
            if operation_id in pinned_operation_ids:
                continue
            remaining_ids = deduped_ids - {operation_id}
            if not remaining_ids:
                continue
            if not _all_desired_fields_covered(
                operation_ids=remaining_ids,
                operation_map=operation_map,
                desired_fields=desired_fields,
                entity_type=entity_type,
            ):
                continue
            if not _required_inputs_satisfied_for_selection(
                operation_ids=remaining_ids,
                operation_map=operation_map,
                initial_fields=initial_fields,
            ):
                continue
            deduped_ids = remaining_ids
            changed = True
            break
    return deduped_ids


def _wire_requirement_dependencies(
    *,
    operation_id: str,
    operation: dict[str, Any],
    operation_ids: set[str],
    operation_map: dict[str, dict[str, Any]],
    initial_fields: set[str],
    unresolvable_fields: set[str],
    preferred_entity_type: str,
    desired_fields: set[str],
) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    available_fields = initial_fields | _produced_fields_for_operations(operation_ids - {operation_id}, operation_map)
    all_of, any_of = _required_inputs(operation)

    for expr in all_of:
        if _expr_satisfied(expr, available_fields):
            continue
        candidate_field = _first_missing_from_expr(expr, available_fields)
        if not candidate_field:
            continue
        producer = _best_operation_for_field(candidate_field, preferred_entity_type, desired_fields)
        if not producer:
            unresolvable_fields.add(candidate_field)
            continue
        producer_id = str(producer["operation_id"])
        operation_ids.add(producer_id)
        edges.add((producer_id, operation_id))

    if any_of:
        any_satisfied = any(_expr_satisfied(expr, available_fields) for expr in any_of)
        if not any_satisfied:
            chosen_field: str | None = None
            for expr in any_of:
                chosen_field = _first_missing_from_expr(expr, available_fields)
                if chosen_field:
                    break
            if chosen_field:
                producer = _best_operation_for_field(chosen_field, preferred_entity_type, desired_fields)
                if not producer:
                    unresolvable_fields.add(chosen_field)
                else:
                    producer_id = str(producer["operation_id"])
                    operation_ids.add(producer_id)
                    edges.add((producer_id, operation_id))

    # Add explicit dependencies for already-selected producers that satisfy requirements.
    available_fields = initial_fields | _produced_fields_for_operations(operation_ids - {operation_id}, operation_map)
    for req_expr in all_of:
        for selected_id in operation_ids:
            if selected_id == operation_id:
                continue
            selected = operation_map.get(selected_id)
            if not selected:
                continue
            produces = selected.get("produces")
            if not isinstance(produces, list):
                continue
            missing_candidate = _first_missing_from_expr(req_expr, initial_fields)
            if missing_candidate and missing_candidate in produces:
                edges.add((selected_id, operation_id))

    return edges


def _toposort(operation_ids: set[str], edges: set[tuple[str, str]]) -> list[str]:
    indegree: dict[str, int] = {operation_id: 0 for operation_id in operation_ids}
    adjacency: dict[str, set[str]] = defaultdict(set)

    for source, target in edges:
        if source not in indegree or target not in indegree:
            continue
        if target in adjacency[source]:
            continue
        adjacency[source].add(target)
        indegree[target] += 1

    queue = deque(sorted([op_id for op_id, degree in indegree.items() if degree == 0]))
    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for nxt in sorted(adjacency.get(node, set())):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(ordered) == len(indegree):
        return ordered

    # Cycle fallback: append remaining nodes deterministically.
    remaining = sorted(set(indegree) - set(ordered))
    return ordered + remaining


def _build_step_config(operation_id: str, options: dict[str, Any]) -> dict[str, Any] | None:
    config: dict[str, Any] = {}
    if operation_id == "person.search":
        if "max_results" in options:
            config["max_results"] = options["max_results"]
        if "job_title" in options:
            config["job_title"] = options["job_title"]
    if operation_id == "person.enrich.profile" and options.get("include_work_history"):
        config["include_work_history"] = True
    if operation_id == "company.derive.pricing_intelligence" and options.get("include_pricing_intelligence"):
        config["condition"] = {"field": "pricing_page_url", "op": "exists"}
    return config or None


def assemble_blueprint(
    *,
    desired_fields: list[str],
    entity_type: str,
    options: dict | None,
) -> dict:
    parsed_options = _parse_options(options)
    operation_map = _operations_by_id()
    selected_operation_ids: set[str] = set()
    edges: set[tuple[str, str]] = set()
    unresolvable_fields: set[str] = set()

    normalized_desired_fields = [field.strip() for field in desired_fields if isinstance(field, str) and field.strip()]
    normalized_desired_field_set = set(normalized_desired_fields)
    initial_fields = set(_DEFAULT_INITIAL_FIELDS.get(entity_type, set()))

    cross_entity_person_needed = entity_type == "company" and any(
        field in _COMPANY_TO_PERSON_SIGNAL_FIELDS for field in normalized_desired_fields
    )

    for field in normalized_desired_fields:
        preferred_entity = "person" if field in _COMPANY_TO_PERSON_SIGNAL_FIELDS else entity_type
        producer = _best_operation_for_field(field, preferred_entity, normalized_desired_field_set)
        if not producer:
            unresolvable_fields.add(field)
            continue
        selected_operation_ids.add(str(producer["operation_id"]))

    if cross_entity_person_needed:
        selected_operation_ids.add("person.search")

    if parsed_options.get("include_pricing_intelligence"):
        selected_operation_ids.add("company.derive.pricing_intelligence")
    pinned_operation_ids = {"company.derive.pricing_intelligence"} if parsed_options.get("include_pricing_intelligence") else set()

    changed = True
    while changed:
        changed = False
        snapshot = set(selected_operation_ids)
        for operation_id in snapshot:
            operation = operation_map.get(operation_id)
            if not operation:
                continue
            new_edges = _wire_requirement_dependencies(
                operation_id=operation_id,
                operation=operation,
                operation_ids=selected_operation_ids,
                operation_map=operation_map,
                initial_fields=initial_fields,
                unresolvable_fields=unresolvable_fields,
                preferred_entity_type=entity_type if operation_id.startswith("company.") else "person",
                desired_fields=normalized_desired_field_set,
            )
            previous_edge_count = len(edges)
            edges.update(new_edges)
            if len(edges) != previous_edge_count:
                changed = True
        if selected_operation_ids != snapshot:
            changed = True

    selected_operation_ids = _deduplicate_redundant_operations(
        operation_ids=selected_operation_ids,
        operation_map=operation_map,
        desired_fields=normalized_desired_field_set,
        initial_fields=initial_fields,
        pinned_operation_ids=pinned_operation_ids,
        entity_type=entity_type,
    )
    edges = {(source, target) for source, target in edges if source in selected_operation_ids and target in selected_operation_ids}

    if cross_entity_person_needed and "person.search" in selected_operation_ids:
        for operation_id in list(selected_operation_ids):
            if operation_id.startswith("person.") and operation_id != "person.search":
                edges.add(("person.search", operation_id))

    if parsed_options.get("include_pricing_intelligence"):
        if "company.research.resolve_pricing_page_url" in selected_operation_ids:
            edges.add(("company.research.resolve_pricing_page_url", "company.derive.pricing_intelligence"))

    ordered_operation_ids = _toposort(selected_operation_ids, edges)

    steps: list[dict[str, Any]] = []
    for index, operation_id in enumerate(ordered_operation_ids, start=1):
        operation = operation_map.get(operation_id)
        if not operation:
            continue
        step: dict[str, Any] = {
            "position": index,
            "operation_id": operation_id,
        }
        if bool(operation.get("supports_fan_out")):
            step["fan_out"] = True
        step_config = _build_step_config(operation_id, parsed_options)
        if step_config:
            step["step_config"] = step_config
        steps.append(step)

    return {
        "name": "auto-generated",
        "entity_type": entity_type,
        "desired_fields": normalized_desired_fields,
        "steps": steps,
        "unresolvable_fields": sorted(unresolvable_fields),
    }
