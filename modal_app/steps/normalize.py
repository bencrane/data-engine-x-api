# modal_app/steps/normalize.py — Example: company name normalization

from typing import Any

from modal_app.config import app, base_image, secrets


@app.function(image=base_image, secrets=secrets)
def normalize_company_names(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize company names in the input data.

    - Strips whitespace
    - Removes common suffixes (Inc, LLC, Ltd, etc.)
    - Standardizes capitalization
    """
    suffixes = [
        ", Inc.",
        ", Inc",
        " Inc.",
        " Inc",
        ", LLC",
        " LLC",
        ", Ltd.",
        ", Ltd",
        " Ltd.",
        " Ltd",
        ", Corp.",
        ", Corp",
        " Corp.",
        " Corp",
    ]

    normalized = []
    for record in data:
        record = record.copy()
        if "company_name" in record and record["company_name"]:
            name = record["company_name"].strip()
            for suffix in suffixes:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    break
            record["company_name"] = name.strip()
            record["company_name_normalized"] = True
        normalized.append(record)

    return normalized
