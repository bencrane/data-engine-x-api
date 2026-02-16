# modal_app/steps/deduplicate.py — Example: dedup records

from typing import Any

from modal_app.config import app, base_image, secrets


@app.function(image=base_image, secrets=secrets)
def deduplicate_records(
    data: list[dict[str, Any]],
    key_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Remove duplicate records from the input data.

    Args:
        data: List of records to deduplicate
        key_fields: Fields to use for deduplication. Defaults to ["email"].

    Returns:
        Deduplicated list of records
    """
    if key_fields is None:
        key_fields = ["email"]

    seen = set()
    deduplicated = []

    for record in data:
        # Build key from specified fields
        key_parts = []
        for field in key_fields:
            value = record.get(field, "")
            if isinstance(value, str):
                value = value.lower().strip()
            key_parts.append(str(value))
        key = tuple(key_parts)

        if key not in seen:
            seen.add(key)
            record = record.copy()
            record["is_duplicate"] = False
            deduplicated.append(record)

    return deduplicated
