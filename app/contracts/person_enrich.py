from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PersonEnrichProfileOutput(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linkedin_url: str | None = None
    headline: str | None = None
    current_title: str | None = None
    seniority: str | None = None
    department: str | None = None
    bio: str | None = None
    location: str | None = None
    country: str | None = None
    current_company_name: str | None = None
    current_company_domain: str | None = None
    current_company_linkedin_url: str | None = None
    work_history: list[dict[str, Any]] | None = None
    education: list[dict[str, Any]] | None = None
    skills: list[str] | None = None
    certifications: list[dict[str, Any]] | None = None
    honors: list[dict[str, Any]] | None = None
    recommendations: list[dict[str, Any]] | None = None
    people_also_viewed: list[dict[str, Any]] | None = None
    email: str | None = None
    email_status: str | None = None
    mobile_phone: str | None = None
    mobile_status: str | None = None
    total_tenure_years: str | None = None
    connections_count: int | None = None
    follower_count: int | None = None
    source_provider: str
