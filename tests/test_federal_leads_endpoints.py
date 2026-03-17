"""Tests for Federal Leads new endpoints — SBA query, CSV export, company detail, verticals."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.sba_query import query_sba_loans, get_sba_loans_stats
from app.services.federal_leads_export import stream_federal_contract_leads_csv
from app.services.federal_leads_company_detail import get_company_detail, _extract_search_name
from app.services.federal_leads_verticals import get_vertical_summary

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────

SAMPLE_SBA_ROW = {
    "id": "00000000-0000-0000-0000-000000000001",
    "borrname": "ACME WIDGETS LLC",
    "borrstate": "VA",
    "borrcity": "ARLINGTON",
    "naicscode": "332710",
    "grossapproval": "250000.00",
    "approvaldate": "01/15/2025",
    "businessage": "Existing or more than 2 years old",
    "businesstype": "CORPORATION",
    "bankname": "FIRST NATIONAL BANK",
    "loanstatus": "EXEMPT",
    "jobssupported": "12",
    "total_matched": 1,
}


def _mock_cursor_factory(rows: list[dict]):
    cursor = MagicMock()
    cursor.fetchall.return_value = [dict(r) for r in rows]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


def _mock_pool(rows: list[dict]):
    cursor = _mock_cursor_factory(rows)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    pool = MagicMock()
    pool.connection.return_value = conn
    return pool, cursor


def _make_super_admin():
    from uuid import uuid4
    from app.auth.models import SuperAdminContext
    return SuperAdminContext(super_admin_id=uuid4(), email="test@test.com")


def _override_auth():
    from app.routers.entities_v1 import _resolve_flexible_auth
    sa = _make_super_admin()
    app.dependency_overrides[_resolve_flexible_auth] = lambda: sa
    return lambda: app.dependency_overrides.pop(_resolve_flexible_auth, None)


SUPER_ADMIN_HEADERS = {"Authorization": "Bearer test-super-admin-key"}


# ── 1. SBA Query Service Tests ──────────────────────────────────────────────


class TestSbaQueryDefault:
    @patch("app.services.sba_query._get_pool")
    def test_default_no_filters(self, mock_get_pool):
        pool, cursor = _mock_pool([SAMPLE_SBA_ROW])
        mock_get_pool.return_value = pool

        result = query_sba_loans(filters={}, limit=25, offset=0)

        assert result["limit"] == 25
        assert result["offset"] == 0
        assert result["total_matched"] == 1
        assert len(result["items"]) == 1
        assert "total_matched" not in result["items"][0]

    @patch("app.services.sba_query._get_pool")
    def test_empty_result(self, mock_get_pool):
        pool, _ = _mock_pool([])
        mock_get_pool.return_value = pool

        result = query_sba_loans(filters={})
        assert result["items"] == []
        assert result["total_matched"] == 0


class TestSbaQueryFilters:
    @patch("app.services.sba_query._get_pool")
    def test_naics_prefix_generates_like(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"naics_prefix": "33"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "naicscode LIKE %s" in sql
        assert "33%" in params

    @patch("app.services.sba_query._get_pool")
    def test_state_exact_match(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"state": "VA"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "borrstate = %s" in sql
        assert "VA" in params

    @patch("app.services.sba_query._get_pool")
    def test_min_loan_amount_casts_numeric(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"min_loan_amount": "100000"})

        sql = cursor.execute.call_args[0][0]
        assert "CAST(grossapproval AS NUMERIC) >= %s" in sql

    @patch("app.services.sba_query._get_pool")
    def test_max_loan_amount_casts_numeric(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"max_loan_amount": "500000"})

        sql = cursor.execute.call_args[0][0]
        assert "CAST(grossapproval AS NUMERIC) <= %s" in sql

    @patch("app.services.sba_query._get_pool")
    def test_approval_date_from_uses_to_date(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"approval_date_from": "2025-01-01"})

        sql = cursor.execute.call_args[0][0]
        assert "TO_DATE(approvaldate, 'MM/DD/YYYY') >= %s::DATE" in sql

    @patch("app.services.sba_query._get_pool")
    def test_approval_date_to_uses_to_date(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"approval_date_to": "2025-12-31"})

        sql = cursor.execute.call_args[0][0]
        assert "TO_DATE(approvaldate, 'MM/DD/YYYY') <= %s::DATE" in sql

    @patch("app.services.sba_query._get_pool")
    def test_business_age_exact_match(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"business_age": "Existing or more than 2 years old"})

        sql = cursor.execute.call_args[0][0]
        assert "businessage = %s" in sql

    @patch("app.services.sba_query._get_pool")
    def test_business_type_exact_match(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"business_type": "CORPORATION"})

        sql = cursor.execute.call_args[0][0]
        assert "businesstype = %s" in sql

    @patch("app.services.sba_query._get_pool")
    def test_lender_name_ilike(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"lender_name": "FIRST NATIONAL"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "bankname ILIKE %s" in sql
        assert "%FIRST NATIONAL%" in params

    @patch("app.services.sba_query._get_pool")
    def test_borrower_name_ilike(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"borrower_name": "ACME"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "borrname ILIKE %s" in sql
        assert "%ACME%" in params

    @patch("app.services.sba_query._get_pool")
    def test_min_jobs_casts_integer(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"min_jobs": "5"})

        sql = cursor.execute.call_args[0][0]
        assert "CAST(jobssupported AS INTEGER) >= %s" in sql

    @patch("app.services.sba_query._get_pool")
    def test_multiple_filters_combine_with_and(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={"state": "VA", "naics_prefix": "33", "business_type": "CORPORATION"})

        sql = cursor.execute.call_args[0][0]
        assert " AND " in sql
        assert "borrstate = %s" in sql
        assert "naicscode LIKE %s" in sql
        assert "businesstype = %s" in sql

    @patch("app.services.sba_query._get_pool")
    def test_pagination(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_sba_loans(filters={}, limit=10, offset=50)

        params = cursor.execute.call_args[0][1]
        assert 10 in params
        assert 50 in params


# ── 2. CSV Export Tests ──────────────────────────────────────────────────────


class TestCsvExport:
    @patch("app.services.federal_leads_export._get_pool")
    def test_export_returns_iterator(self, mock_get_pool):
        # Mock count query
        count_cursor = MagicMock()
        count_cursor.fetchone.return_value = (2,)
        count_cursor.__enter__ = MagicMock(return_value=count_cursor)
        count_cursor.__exit__ = MagicMock(return_value=False)

        # Mock data cursor (server-side)
        data_cursor = MagicMock()
        data_cursor.description = [("col_a",), ("col_b",), ("col_c",)]
        data_cursor.fetchmany.side_effect = [
            [("val1", "val2", "val3"), ("val4", "val5", "val6")],
            [],
        ]
        data_cursor.__enter__ = MagicMock(return_value=data_cursor)
        data_cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        call_count = [0]

        def cursor_side_effect(**kwargs):
            call_count[0] += 1
            if "name" in kwargs:
                return data_cursor
            return count_cursor

        conn.cursor = MagicMock(side_effect=cursor_side_effect)
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        lines = list(stream_federal_contract_leads_csv(filters={}))

        assert len(lines) == 3  # header + 2 data rows
        assert "col_a" in lines[0]
        assert "val1" in lines[1]

    @patch("app.services.federal_leads_export._get_pool")
    def test_first_line_is_header(self, mock_get_pool):
        count_cursor = MagicMock()
        count_cursor.fetchone.return_value = (1,)
        count_cursor.__enter__ = MagicMock(return_value=count_cursor)
        count_cursor.__exit__ = MagicMock(return_value=False)

        data_cursor = MagicMock()
        data_cursor.description = [("recipient_uei",), ("naics_code",)]
        data_cursor.fetchmany.side_effect = [[("ABC123", "541512")], []]
        data_cursor.__enter__ = MagicMock(return_value=data_cursor)
        data_cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor = MagicMock(side_effect=lambda **kwargs: data_cursor if "name" in kwargs else count_cursor)
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        lines = list(stream_federal_contract_leads_csv(filters={}))
        assert lines[0].strip() == "recipient_uei,naics_code"

    @patch("app.services.federal_leads_export._get_pool")
    def test_filters_applied(self, mock_get_pool):
        count_cursor = MagicMock()
        count_cursor.fetchone.return_value = (0,)
        count_cursor.__enter__ = MagicMock(return_value=count_cursor)
        count_cursor.__exit__ = MagicMock(return_value=False)

        data_cursor = MagicMock()
        data_cursor.description = [("col",)]
        data_cursor.fetchmany.return_value = []
        data_cursor.__enter__ = MagicMock(return_value=data_cursor)
        data_cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor = MagicMock(side_effect=lambda **kwargs: data_cursor if "name" in kwargs else count_cursor)
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        list(stream_federal_contract_leads_csv(filters={"state": "VA"}))

        # Count query should have the filter
        count_sql = count_cursor.execute.call_args[0][0]
        assert "recipient_state_code = %s" in count_sql

    @patch("app.services.federal_leads_export._get_pool")
    def test_max_rows_raises_value_error(self, mock_get_pool):
        count_cursor = MagicMock()
        count_cursor.fetchone.return_value = (200_000,)
        count_cursor.__enter__ = MagicMock(return_value=count_cursor)
        count_cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor = MagicMock(return_value=count_cursor)
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        gen = stream_federal_contract_leads_csv(filters={}, max_rows=100_000)
        with pytest.raises(ValueError, match="200000 rows"):
            next(gen)


# ── 3. Company Detail Tests ──────────────────────────────────────────────────


class TestExtractSearchName:
    def test_strips_inc(self):
        assert _extract_search_name("THE MATTHEWS GROUP INC") == "MATTHEWS"

    def test_strips_llc(self):
        assert _extract_search_name("ACME WIDGETS LLC") == "WIDGETS"

    def test_strips_corporation(self):
        assert _extract_search_name("GLOBAL SOLUTIONS CORPORATION") == "GLOBAL"

    def test_strips_multiple_suffixes(self):
        result = _extract_search_name("THE BIG COMPANY GROUP INC")
        assert result == "BIG"

    def test_returns_none_for_empty(self):
        assert _extract_search_name("INC LLC") is None


class TestCompanyDetail:
    @patch("app.services.federal_leads_company_detail._get_pool")
    def test_returns_all_three_sections(self, mock_get_pool):
        sam_row = {"unique_entity_id": "ABC123456789", "legal_business_name": "ACME INC", "physical_address_province_or_state": "VA"}
        usa_row = {
            "contract_transaction_unique_key": "TXN1",
            "contract_award_unique_key": "AWD1",
            "award_type": "A",
            "action_date": "2025-06-15",
            "federal_action_obligation": "100000.00",
            "total_dollars_obligated": "100000.00",
            "potential_total_value_of_award": "200000.00",
            "awarding_agency_name": "DOD",
            "naics_code": "541512",
            "naics_description": "IT Services",
            "usaspending_permalink": "https://example.com",
            "recipient_name": "ACME INC",
            "recipient_state_code": "VA",
        }
        sba_row = {"borrname": "ACME WIDGETS", "borrstate": "VA", "grossapproval": "50000"}

        call_idx = [0]

        def cursor_side_effect(*args, **kwargs):
            cursor = MagicMock()
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                cursor.fetchone.return_value = sam_row
                cursor.fetchall.return_value = [sam_row]
            elif idx == 1:
                cursor.fetchall.return_value = [usa_row]
            else:
                cursor.fetchall.return_value = [sba_row]
            return cursor

        conn = MagicMock()
        conn.cursor = MagicMock(side_effect=cursor_side_effect)
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        result = get_company_detail(uei="ABC123456789")

        assert result is not None
        assert result["uei"] == "ABC123456789"
        assert result["sam_registration"] is not None
        assert len(result["awards"]["items"]) == 1
        assert result["sba_loans"]["match_method"] == "fuzzy_name_state"

    @patch("app.services.federal_leads_company_detail._get_pool")
    def test_returns_none_when_not_found(self, mock_get_pool):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        result = get_company_detail(uei="NONEXISTENT00")
        assert result is None

    @patch("app.services.federal_leads_company_detail._get_pool")
    def test_works_with_only_usaspending(self, mock_get_pool):
        usa_row = {
            "contract_transaction_unique_key": "TXN1",
            "contract_award_unique_key": "AWD1",
            "award_type": "A",
            "action_date": "2025-06-15",
            "federal_action_obligation": "100000.00",
            "total_dollars_obligated": "100000.00",
            "potential_total_value_of_award": "200000.00",
            "awarding_agency_name": "DOD",
            "naics_code": "541512",
            "naics_description": "IT Services",
            "usaspending_permalink": "https://example.com",
            "recipient_name": "ACME BUILDERS INC",
            "recipient_state_code": "TX",
        }
        sba_row = {"borrname": "ACME BUILDERS", "borrstate": "TX", "grossapproval": "25000"}

        call_idx = [0]

        def cursor_side_effect(*args, **kwargs):
            cursor = MagicMock()
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 0:
                cursor.fetchone.return_value = None  # No SAM match
            elif idx == 1:
                cursor.fetchall.return_value = [usa_row]
            else:
                cursor.fetchall.return_value = [sba_row]
            return cursor

        conn = MagicMock()
        conn.cursor = MagicMock(side_effect=cursor_side_effect)
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        result = get_company_detail(uei="XYZ999999999")

        assert result is not None
        assert result["sam_registration"] is None
        assert len(result["awards"]["items"]) == 1
        assert result["sba_loans"]["search_state"] == "TX"


# ── 4. Vertical Summary Tests ───────────────────────────────────────────────


class TestVerticalSummary:
    @patch("app.services.federal_leads_verticals._get_pool")
    def test_returns_all_verticals(self, mock_get_pool):
        rows = [
            {"vertical": "Manufacturing", "total_rows": 500, "unique_companies": 100, "first_time_awardees": 30, "repeat_awardees": 70, "total_obligated": 5000000},
            {"vertical": "Construction", "total_rows": 400, "unique_companies": 80, "first_time_awardees": 20, "repeat_awardees": 60, "total_obligated": 4000000},
            {"vertical": "IT & Professional Services", "total_rows": 300, "unique_companies": 60, "first_time_awardees": 15, "repeat_awardees": 45, "total_obligated": 3000000},
            {"vertical": "Healthcare & Social Assistance", "total_rows": 200, "unique_companies": 40, "first_time_awardees": 10, "repeat_awardees": 30, "total_obligated": 2000000},
            {"vertical": "Transportation & Warehousing", "total_rows": 150, "unique_companies": 30, "first_time_awardees": 8, "repeat_awardees": 22, "total_obligated": 1500000},
            {"vertical": "Admin & Staffing Services", "total_rows": 100, "unique_companies": 20, "first_time_awardees": 5, "repeat_awardees": 15, "total_obligated": 1000000},
            {"vertical": "All Other", "total_rows": 50, "unique_companies": 10, "first_time_awardees": 3, "repeat_awardees": 7, "total_obligated": 500000},
        ]

        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        result = get_vertical_summary()

        assert len(result) == 7
        verticals = {r["vertical"] for r in result}
        assert "Manufacturing" in verticals
        assert "All Other" in verticals

    @patch("app.services.federal_leads_verticals._get_pool")
    def test_counts_are_non_negative(self, mock_get_pool):
        rows = [
            {"vertical": "Manufacturing", "total_rows": 10, "unique_companies": 5, "first_time_awardees": 2, "repeat_awardees": 3, "total_obligated": 100000},
        ]

        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        result = get_vertical_summary()
        for r in result:
            assert r["total_rows"] >= 0
            assert r["unique_companies"] >= 0
            assert r["first_time_awardees"] >= 0
            assert r["repeat_awardees"] >= 0

    @patch("app.services.federal_leads_verticals._get_pool")
    def test_repeat_equals_unique_minus_first_time(self, mock_get_pool):
        rows = [
            {"vertical": "Construction", "total_rows": 20, "unique_companies": 10, "first_time_awardees": 4, "repeat_awardees": 6, "total_obligated": 200000},
        ]

        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        result = get_vertical_summary()
        for r in result:
            assert r["repeat_awardees"] == r["unique_companies"] - r["first_time_awardees"]


# ── 5. Endpoint Tests ───────────────────────────────────────────────────────


class TestSbaEndpoints:
    @patch("app.services.sba_query._get_pool")
    def test_sba_query_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            pool, cursor = _mock_pool([SAMPLE_SBA_ROW])
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/sba-loans/query",
                json={"state": "VA", "limit": 5},
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert "items" in body["data"]
        finally:
            cleanup()

    def test_sba_query_requires_auth(self):
        response = client.post("/api/v1/sba-loans/query", json={})
        assert response.status_code == 401

    @patch("app.services.sba_query._get_pool")
    def test_sba_stats_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            cursor = MagicMock()
            cursor.fetchone.return_value = (5000, 3000, 1250000000.50, 150, 50)
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            conn = MagicMock()
            conn.cursor.return_value = cursor
            conn.__enter__ = MagicMock(return_value=conn)
            conn.__exit__ = MagicMock(return_value=False)
            pool = MagicMock()
            pool.connection.return_value = conn
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/sba-loans/stats",
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert body["data"]["total_rows"] == 5000
            assert body["data"]["unique_borrowers"] == 3000
        finally:
            cleanup()

    def test_sba_stats_requires_auth(self):
        response = client.post("/api/v1/sba-loans/stats")
        assert response.status_code == 401


class TestExportEndpoint:
    @patch("app.services.federal_leads_export._get_pool")
    def test_export_returns_csv_content_type(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            count_cursor = MagicMock()
            count_cursor.fetchone.return_value = (1,)
            count_cursor.__enter__ = MagicMock(return_value=count_cursor)
            count_cursor.__exit__ = MagicMock(return_value=False)

            data_cursor = MagicMock()
            data_cursor.description = [("col_a",), ("col_b",)]
            data_cursor.fetchmany.side_effect = [[("v1", "v2")], []]
            data_cursor.__enter__ = MagicMock(return_value=data_cursor)
            data_cursor.__exit__ = MagicMock(return_value=False)

            conn = MagicMock()
            conn.cursor = MagicMock(side_effect=lambda **kwargs: data_cursor if "name" in kwargs else count_cursor)
            conn.__enter__ = MagicMock(return_value=conn)
            conn.__exit__ = MagicMock(return_value=False)

            pool = MagicMock()
            pool.connection.return_value = conn
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/federal-contract-leads/export",
                json={},
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            assert "text/csv" in response.headers["content-type"]
            assert "attachment" in response.headers["content-disposition"]
        finally:
            cleanup()

    def test_export_requires_auth(self):
        response = client.post("/api/v1/federal-contract-leads/export", json={})
        assert response.status_code == 401


class TestCompanyDetailEndpoint:
    @patch("app.services.federal_leads_company_detail._get_pool")
    def test_get_uei_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            sam_row = {"unique_entity_id": "ABC123456789", "legal_business_name": "ACME INC", "physical_address_province_or_state": "VA"}
            usa_row = {
                "contract_transaction_unique_key": "TXN1",
                "contract_award_unique_key": "AWD1",
                "award_type": "A",
                "action_date": "2025-06-15",
                "federal_action_obligation": "100000.00",
                "total_dollars_obligated": "100000.00",
                "potential_total_value_of_award": "200000.00",
                "awarding_agency_name": "DOD",
                "naics_code": "541512",
                "naics_description": "IT",
                "usaspending_permalink": "https://example.com",
                "recipient_name": "ACME INC",
                "recipient_state_code": "VA",
            }

            call_idx = [0]

            def cursor_side_effect(*args, **kwargs):
                cursor = MagicMock()
                cursor.__enter__ = MagicMock(return_value=cursor)
                cursor.__exit__ = MagicMock(return_value=False)
                idx = call_idx[0]
                call_idx[0] += 1
                if idx == 0:
                    cursor.fetchone.return_value = sam_row
                elif idx == 1:
                    cursor.fetchall.return_value = [usa_row]
                else:
                    cursor.fetchall.return_value = []
                return cursor

            conn = MagicMock()
            conn.cursor = MagicMock(side_effect=cursor_side_effect)
            conn.__enter__ = MagicMock(return_value=conn)
            conn.__exit__ = MagicMock(return_value=False)

            pool = MagicMock()
            pool.connection.return_value = conn
            mock_get_pool.return_value = pool

            response = client.get(
                "/api/v1/federal-contract-leads/ABC123456789",
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert body["data"]["uei"] == "ABC123456789"
        finally:
            cleanup()

    @patch("app.services.federal_leads_company_detail._get_pool")
    def test_get_uei_returns_404_when_not_found(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            cursor = MagicMock()
            cursor.fetchone.return_value = None
            cursor.fetchall.return_value = []
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)

            conn = MagicMock()
            conn.cursor.return_value = cursor
            conn.__enter__ = MagicMock(return_value=conn)
            conn.__exit__ = MagicMock(return_value=False)

            pool = MagicMock()
            pool.connection.return_value = conn
            mock_get_pool.return_value = pool

            response = client.get(
                "/api/v1/federal-contract-leads/NONEXISTENT00",
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 404
        finally:
            cleanup()

    def test_get_uei_requires_auth(self):
        response = client.get("/api/v1/federal-contract-leads/ABC123456789")
        assert response.status_code == 401


class TestVerticalsEndpoint:
    @patch("app.services.federal_leads_verticals._get_pool")
    def test_verticals_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            rows = [
                {"vertical": "Manufacturing", "total_rows": 100, "unique_companies": 50, "first_time_awardees": 10, "repeat_awardees": 40, "total_obligated": 1000000},
            ]
            cursor = MagicMock()
            cursor.fetchall.return_value = rows
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)

            conn = MagicMock()
            conn.cursor.return_value = cursor
            conn.__enter__ = MagicMock(return_value=conn)
            conn.__exit__ = MagicMock(return_value=False)

            pool = MagicMock()
            pool.connection.return_value = conn
            mock_get_pool.return_value = pool

            response = client.get(
                "/api/v1/federal-contract-leads/verticals",
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert "verticals" in body["data"]
        finally:
            cleanup()

    def test_verticals_requires_auth(self):
        response = client.get("/api/v1/federal-contract-leads/verticals")
        assert response.status_code == 401

    @patch("app.services.federal_leads_verticals._get_pool")
    def test_verticals_does_not_collide_with_uei(self, mock_get_pool):
        """Verify /verticals is not captured by /{uei} path parameter."""
        cleanup = _override_auth()
        try:
            rows = [
                {"vertical": "All Other", "total_rows": 1, "unique_companies": 1, "first_time_awardees": 0, "repeat_awardees": 1, "total_obligated": 100},
            ]
            cursor = MagicMock()
            cursor.fetchall.return_value = rows
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)

            conn = MagicMock()
            conn.cursor.return_value = cursor
            conn.__enter__ = MagicMock(return_value=conn)
            conn.__exit__ = MagicMock(return_value=False)

            pool = MagicMock()
            pool.connection.return_value = conn
            mock_get_pool.return_value = pool

            response = client.get(
                "/api/v1/federal-contract-leads/verticals",
                headers=SUPER_ADMIN_HEADERS,
            )

            # Should return 200 from verticals endpoint, not try to look up "verticals" as a UEI
            assert response.status_code == 200
            body = response.json()
            assert "verticals" in body["data"]
        finally:
            cleanup()
