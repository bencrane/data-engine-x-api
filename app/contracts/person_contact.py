from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class EmailVerificationResult(BaseModel):
    provider: str
    status: str
    inconclusive: bool
    raw_response: dict[str, Any]


class ResolveEmailOutput(BaseModel):
    email: str | None
    source_provider: str | None
    verification: EmailVerificationResult | None


class VerifyEmailOutput(BaseModel):
    email: str
    verification: EmailVerificationResult | None


class ResolveMobilePhoneOutput(BaseModel):
    mobile_phone: str | None
    source_provider: str | None
