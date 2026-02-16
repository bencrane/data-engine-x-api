#!/usr/bin/env python3
"""
Seed a single super admin record.

Required environment variables:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
- SUPER_ADMIN_EMAIL
- SUPER_ADMIN_PASSWORD
"""

import os
import sys

import bcrypt
from supabase import create_client


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    supabase_url = _required_env("SUPABASE_URL")
    supabase_service_role_key = _required_env("SUPABASE_SERVICE_ROLE_KEY")
    email = _required_env("SUPER_ADMIN_EMAIL").strip().lower()
    password = _required_env("SUPER_ADMIN_PASSWORD")

    client = create_client(supabase_url, supabase_service_role_key)

    existing = (
        client.table("super_admins")
        .select("id")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    if existing.data:
        print(f"super_admin already exists for {email}")
        return 0

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    client.table("super_admins").insert(
        {
            "email": email,
            "password_hash": password_hash,
            "is_active": True,
        }
    ).execute()

    print(f"seeded super_admin: {email}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"seed_super_admin failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
