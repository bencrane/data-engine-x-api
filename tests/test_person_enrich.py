from __future__ import annotations

import pytest

from app.services import person_enrich_operations


def _assert_structured_result(result: dict) -> None:
    assert isinstance(result, dict)
    assert isinstance(result.get("run_id"), str)
    assert result.get("operation_id") == "person.enrich.profile"
    assert result.get("status") in {"found", "not_found", "failed"}
    assert isinstance(result.get("provider_attempts"), list)


@pytest.mark.asyncio
async def test_execute_person_enrich_profile_noisy_input_returns_structured_response():
    result = await person_enrich_operations.execute_person_enrich_profile(
        input_data={
            "linkedin_url": {"bad": "value"},
            "first_name": ["bad"],
            "last_name": {"bad": "value"},
            "full_name": {"bad": "value"},
            "company_domain": {"bad": "value"},
            "company_name": ["bad"],
            "company_linkedin_url": {"bad": "value"},
            "email": {"bad": "value"},
            "person_id": {"bad": "value"},
            "include_work_history": {"bad": "value"},
            "company_profile": {"noise": True},
            "results": [{"noise": "value"}],
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_person_enrich_waterfall_stops_at_first_success(monkeypatch: pytest.MonkeyPatch):
    async def _stub_prospeo(**kwargs):
        return {
            "attempt": {"provider": "prospeo", "action": "person_enrich_profile", "status": "found"},
            "mapped": {
                "full_name": "Alex Smith",
                "first_name": "Alex",
                "last_name": "Smith",
                "linkedin_url": "https://linkedin.com/in/alexsmith",
                "source_provider": "prospeo",
            },
        }

    called = {"ample": False, "leadmagic": False}

    async def _stub_ample(**kwargs):
        called["ample"] = True
        return {
            "attempt": {"provider": "ampleleads", "action": "person_enrich_profile", "status": "found"},
            "mapped": {},
        }

    async def _stub_leadmagic(**kwargs):
        called["leadmagic"] = True
        return {
            "attempt": {"provider": "leadmagic", "action": "person_enrich_profile", "status": "found"},
            "mapped": {},
        }

    monkeypatch.setattr(person_enrich_operations, "_prospeo_enrich_person", _stub_prospeo)
    monkeypatch.setattr(person_enrich_operations.ampleleads, "enrich_person", _stub_ample)
    monkeypatch.setattr(person_enrich_operations, "_leadmagic_profile_search", _stub_leadmagic)

    result = await person_enrich_operations.execute_person_enrich_profile(
        input_data={
            "linkedin_url": "https://linkedin.com/in/alexsmith",
            "include_work_history": True,
        }
    )

    assert result["status"] == "found"
    assert result["output"]["source_provider"] == "prospeo"
    assert called["ample"] is False
    assert called["leadmagic"] is False


@pytest.mark.asyncio
async def test_person_enrich_waterfall_falls_through_to_next_provider(monkeypatch: pytest.MonkeyPatch):
    async def _stub_prospeo(**kwargs):
        return {
            "attempt": {"provider": "prospeo", "action": "person_enrich_profile", "status": "not_found"},
            "mapped": None,
        }

    called = {"ample": 0}

    async def _stub_ample(**kwargs):
        called["ample"] += 1
        return {
            "attempt": {"provider": "ampleleads", "action": "person_enrich_profile", "status": "found"},
            "mapped": {
                "full_name": "Taylor Doe",
                "first_name": "Taylor",
                "last_name": "Doe",
                "linkedin_url": "https://linkedin.com/in/taylordoe",
                "headline": "Head of Sales",
                "work_history": [{"title": "Head of Sales", "current": True}],
            },
        }

    async def _stub_leadmagic(**kwargs):
        raise AssertionError("LeadMagic should not be called after AmpleLeads success")

    monkeypatch.setattr(person_enrich_operations, "_prospeo_enrich_person", _stub_prospeo)
    monkeypatch.setattr(person_enrich_operations.ampleleads, "enrich_person", _stub_ample)
    monkeypatch.setattr(person_enrich_operations, "_leadmagic_profile_search", _stub_leadmagic)

    result = await person_enrich_operations.execute_person_enrich_profile(
        input_data={
            "linkedin_url": "https://linkedin.com/in/taylordoe",
            "include_work_history": True,
        }
    )

    assert result["status"] == "found"
    assert result["output"]["source_provider"] == "ampleleads"
    assert called["ample"] == 1


@pytest.mark.asyncio
async def test_person_enrich_include_work_history_controls_ampleleads(monkeypatch: pytest.MonkeyPatch):
    async def _stub_prospeo(**kwargs):
        return {
            "attempt": {"provider": "prospeo", "action": "person_enrich_profile", "status": "not_found"},
            "mapped": None,
        }

    async def _stub_leadmagic(**kwargs):
        return {
            "attempt": {"provider": "leadmagic", "action": "person_enrich_profile", "status": "not_found"},
            "mapped": None,
        }

    called = {"ample": 0}

    async def _stub_ample(**kwargs):
        called["ample"] += 1
        return {
            "attempt": {"provider": "ampleleads", "action": "person_enrich_profile", "status": "not_found"},
            "mapped": None,
        }

    monkeypatch.setattr(person_enrich_operations, "_prospeo_enrich_person", _stub_prospeo)
    monkeypatch.setattr(person_enrich_operations, "_leadmagic_profile_search", _stub_leadmagic)
    monkeypatch.setattr(person_enrich_operations.ampleleads, "enrich_person", _stub_ample)

    result_with_history = await person_enrich_operations.execute_person_enrich_profile(
        input_data={
            "linkedin_url": "https://linkedin.com/in/with-history",
            "include_work_history": True,
        }
    )
    result_without_history = await person_enrich_operations.execute_person_enrich_profile(
        input_data={
            "linkedin_url": "https://linkedin.com/in/without-history",
            "include_work_history": False,
        }
    )

    assert result_with_history["status"] == "not_found"
    assert result_without_history["status"] == "not_found"
    assert called["ample"] == 1
    assert len(result_with_history["provider_attempts"]) == 3
    assert len(result_without_history["provider_attempts"]) == 2


@pytest.mark.asyncio
async def test_person_enrich_all_providers_fail_returns_not_found(monkeypatch: pytest.MonkeyPatch):
    async def _stub_prospeo(**kwargs):
        return {
            "attempt": {"provider": "prospeo", "action": "person_enrich_profile", "status": "failed"},
            "mapped": None,
        }

    async def _stub_ample(**kwargs):
        return {
            "attempt": {"provider": "ampleleads", "action": "person_enrich_profile", "status": "failed"},
            "mapped": None,
        }

    async def _stub_leadmagic(**kwargs):
        return {
            "attempt": {"provider": "leadmagic", "action": "person_enrich_profile", "status": "failed"},
            "mapped": None,
        }

    monkeypatch.setattr(person_enrich_operations, "_prospeo_enrich_person", _stub_prospeo)
    monkeypatch.setattr(person_enrich_operations.ampleleads, "enrich_person", _stub_ample)
    monkeypatch.setattr(person_enrich_operations, "_leadmagic_profile_search", _stub_leadmagic)

    result = await person_enrich_operations.execute_person_enrich_profile(
        input_data={
            "linkedin_url": "https://linkedin.com/in/not-found",
            "include_work_history": True,
        }
    )

    assert result["status"] == "not_found"
    assert len(result["provider_attempts"]) == 3
    assert [attempt["provider"] for attempt in result["provider_attempts"]] == ["prospeo", "ampleleads", "leadmagic"]
