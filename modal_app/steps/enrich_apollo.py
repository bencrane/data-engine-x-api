# modal_app/steps/enrich_apollo.py — Example: Apollo enrichment

import os
from typing import Any

import httpx
import modal

from modal_app.config import app, base_image, secrets


apollo_image = base_image.pip_install("httpx>=0.27.0")


@app.function(
    image=apollo_image,
    secrets=secrets + [modal.Secret.from_name("apollo-secrets")],
)
def enrich_with_apollo(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Enrich records with data from Apollo.io API.

    Looks up each record by email and adds company/person data.
    """
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        raise ValueError("APOLLO_API_KEY not configured")

    enriched = []

    with httpx.Client() as client:
        for record in data:
            record = record.copy()
            email = record.get("email")

            if not email:
                record["apollo_enriched"] = False
                record["apollo_error"] = "No email provided"
                enriched.append(record)
                continue

            try:
                response = client.post(
                    "https://api.apollo.io/v1/people/match",
                    headers={"X-Api-Key": api_key},
                    json={"email": email},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    apollo_data = response.json()
                    person = apollo_data.get("person", {})

                    record["apollo_enriched"] = True
                    record["apollo_title"] = person.get("title")
                    record["apollo_company"] = person.get("organization", {}).get("name")
                    record["apollo_linkedin"] = person.get("linkedin_url")
                    record["apollo_phone"] = person.get("phone_numbers", [{}])[0].get("number")
                else:
                    record["apollo_enriched"] = False
                    record["apollo_error"] = f"API error: {response.status_code}"

            except Exception as e:
                record["apollo_enriched"] = False
                record["apollo_error"] = str(e)

            enriched.append(record)

    return enriched
