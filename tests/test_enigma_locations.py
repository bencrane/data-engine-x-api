from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.company_enrich import EnigmaLocationsOutput
from app.providers import enigma
from app.services import company_operations
from app.services.company_operations import execute_company_enrich_locations


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self):
        return self._payload


def _set_enigma_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        company_operations,
        "get_settings",
        lambda: SimpleNamespace(enigma_api_key="test-enigma-key"),
    )


@pytest.mark.asyncio
async def test_get_brand_locations_missing_api_key():
    result = await enigma.get_brand_locations(api_key=None, brand_id="brand_123")
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_provider_api_key"
    assert result["mapped"] is None


@pytest.mark.asyncio
async def test_get_brand_locations_missing_brand_id():
    result = await enigma.get_brand_locations(api_key="test-enigma-key", brand_id=None)
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_required_inputs"
    assert result["mapped"] is None


@pytest.mark.asyncio
async def test_get_brand_locations_success(monkeypatch: pytest.MonkeyPatch):
    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        assert url == "https://api.enigma.com/graphql"
        assert headers["x-api-key"] == "test-enigma-key"
        assert "GetBrandLocations" in json["query"]
        assert json["variables"]["searchInput"] == {"entityType": "BRAND", "id": "brand_mcd"}
        assert json["variables"]["locationLimit"] == 25
        return _FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "search": [
                        {
                            "id": "brand_mcd",
                            "namesConnection": {"edges": [{"node": {"name": "McDonald's"}}]},
                            "totalLocationCount": 120,
                            "operatingLocationsConnection": {
                                "totalCount": 3,
                                "edges": [
                                    {
                                        "node": {
                                            "id": "loc_austin",
                                            "names": {"edges": [{"node": {"name": "McDonald's - Austin"}}]},
                                            "addresses": {
                                                "edges": [
                                                    {
                                                        "node": {
                                                            "fullAddress": "1901 E 6TH ST AUSTIN TX 78702",
                                                            "streetAddress1": "1901 E 6TH ST",
                                                            "city": "AUSTIN",
                                                            "state": "TX",
                                                            "postalCode": "78702",
                                                        }
                                                    }
                                                ]
                                            },
                                            "operatingStatuses": {"edges": [{"node": {"operatingStatus": "Open"}}]},
                                        }
                                    },
                                    {
                                        "node": {
                                            "id": "loc_nyc",
                                            "names": {"edges": [{"node": {"name": "McDonald's - New York"}}]},
                                            "addresses": {
                                                "edges": [
                                                    {
                                                        "node": {
                                                            "fullAddress": "123 BROADWAY NEW YORK NY 10001",
                                                            "streetAddress1": "123 BROADWAY",
                                                            "city": "NEW YORK",
                                                            "state": "NY",
                                                            "postalCode": "10001",
                                                        }
                                                    }
                                                ]
                                            },
                                            "operatingStatuses": {"edges": [{"node": {"operatingStatus": "Open"}}]},
                                        }
                                    },
                                    {
                                        "node": {
                                            "id": "loc_sf",
                                            "names": {"edges": [{"node": {"name": "McDonald's - San Francisco"}}]},
                                            "addresses": {
                                                "edges": [
                                                    {
                                                        "node": {
                                                            "fullAddress": "456 MARKET ST SAN FRANCISCO CA 94105",
                                                            "streetAddress1": "456 MARKET ST",
                                                            "city": "SAN FRANCISCO",
                                                            "state": "CA",
                                                            "postalCode": "94105",
                                                        }
                                                    }
                                                ]
                                            },
                                            "operatingStatuses": {"edges": [{"node": {"operatingStatus": "Closed"}}]},
                                        }
                                    },
                                ],
                                "pageInfo": {"hasNextPage": False, "endCursor": "cursor_3"},
                            },
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await enigma.get_brand_locations(api_key="test-enigma-key", brand_id="brand_mcd")
    mapped = result["mapped"]
    assert result["attempt"]["status"] == "found"
    assert mapped is not None
    assert mapped["location_count"] == 3
    assert mapped["open_count"] == 2
    assert mapped["closed_count"] == 1
    assert len(mapped["locations"]) == 3
    assert mapped["locations"][0]["enigma_location_id"] == "loc_austin"
    assert mapped["locations"][0]["full_address"] == "1901 E 6TH ST AUSTIN TX 78702"
    assert mapped["locations"][0]["operating_status"] == "Open"


@pytest.mark.asyncio
async def test_get_brand_locations_empty(monkeypatch: pytest.MonkeyPatch):
    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers)
        assert "GetBrandLocations" in json["query"]
        return _FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "search": [
                        {
                            "id": "brand_mcd",
                            "namesConnection": {"edges": [{"node": {"name": "McDonald's"}}]},
                            "totalLocationCount": 0,
                            "operatingLocationsConnection": {
                                "totalCount": 0,
                                "edges": [],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            },
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)
    result = await enigma.get_brand_locations(api_key="test-enigma-key", brand_id="brand_mcd")
    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["location_count"] == 0
    assert result["mapped"]["locations"] == []


@pytest.mark.asyncio
async def test_get_brand_locations_with_status_filter(monkeypatch: pytest.MonkeyPatch):
    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers)
        assert json["variables"]["locationConditions"] == {
            "filter": {"EQ": ["operatingStatuses.operatingStatus", "Open"]}
        }
        return _FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "search": [
                        {
                            "id": "brand_mcd",
                            "namesConnection": {"edges": [{"node": {"name": "McDonald's"}}]},
                            "totalLocationCount": 1,
                            "operatingLocationsConnection": {
                                "totalCount": 1,
                                "edges": [],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            },
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)
    result = await enigma.get_brand_locations(
        api_key="test-enigma-key",
        brand_id="brand_mcd",
        operating_status_filter="Open",
    )
    assert result["attempt"]["status"] == "found"


@pytest.mark.asyncio
async def test_execute_company_enrich_locations_missing_inputs():
    result = await execute_company_enrich_locations(input_data={})
    assert result["operation_id"] == "company.enrich.locations"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["enigma_brand_id|company_name|company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_enrich_locations_with_brand_id(monkeypatch: pytest.MonkeyPatch):
    _set_enigma_key(monkeypatch)
    called = {"match": 0, "locations": 0}

    async def _mock_match_business(**kwargs):  # noqa: ANN003
        called["match"] += 1
        _ = kwargs
        return {"attempt": {"provider": "enigma", "action": "match_business", "status": "found"}, "mapped": {}}

    async def _mock_get_brand_locations(**kwargs):  # noqa: ANN003
        called["locations"] += 1
        assert kwargs["brand_id"] == "brand_mcd"
        return {
            "attempt": {"provider": "enigma", "action": "get_brand_locations", "status": "found"},
            "mapped": {
                "enigma_brand_id": "brand_mcd",
                "brand_name": "McDonald's",
                "total_location_count": 3,
                "locations": [
                    {"enigma_location_id": "loc_austin", "full_address": "1901 E 6TH ST AUSTIN TX 78702", "operating_status": "Open"},
                    {"enigma_location_id": "loc_nyc", "full_address": "123 BROADWAY NEW YORK NY 10001", "operating_status": "Open"},
                    {
                        "enigma_location_id": "loc_sf",
                        "full_address": "456 MARKET ST SAN FRANCISCO CA 94105",
                        "operating_status": "Closed",
                    },
                ],
                "location_count": 3,
                "open_count": 2,
                "closed_count": 1,
                "has_next_page": False,
                "end_cursor": "cursor_3",
            },
        }

    monkeypatch.setattr(enigma, "match_business", _mock_match_business)
    monkeypatch.setattr(enigma, "get_brand_locations", _mock_get_brand_locations)

    result = await execute_company_enrich_locations(input_data={"enigma_brand_id": "brand_mcd"})
    validated = EnigmaLocationsOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert called["match"] == 0
    assert called["locations"] == 1
    assert len(result["provider_attempts"]) == 1
    assert result["provider_attempts"][0]["action"] == "get_brand_locations"
    assert validated.enigma_brand_id == "brand_mcd"
    assert validated.location_count == 3
    assert validated.open_count == 2
    assert validated.closed_count == 1


@pytest.mark.asyncio
async def test_execute_company_enrich_locations_with_domain_fallback(monkeypatch: pytest.MonkeyPatch):
    _set_enigma_key(monkeypatch)
    calls: list[str] = []

    async def _mock_match_business(**kwargs):  # noqa: ANN003
        calls.append("match")
        assert kwargs["company_domain"] == "mcdonalds.com"
        return {
            "attempt": {"provider": "enigma", "action": "match_business", "status": "found"},
            "mapped": {
                "enigma_brand_id": "brand_mcd",
                "brand_name": "McDonald's",
                "location_count": 120,
            },
        }

    async def _mock_get_brand_locations(**kwargs):  # noqa: ANN003
        calls.append("locations")
        assert kwargs["brand_id"] == "brand_mcd"
        return {
            "attempt": {"provider": "enigma", "action": "get_brand_locations", "status": "found"},
            "mapped": {
                "enigma_brand_id": "brand_mcd",
                "brand_name": "McDonald's",
                "total_location_count": 120,
                "locations": [
                    {
                        "enigma_location_id": "loc_austin",
                        "location_name": "McDonald's - Austin",
                        "full_address": "1901 E 6TH ST AUSTIN TX 78702",
                        "street": "1901 E 6TH ST",
                        "city": "AUSTIN",
                        "state": "TX",
                        "postal_code": "78702",
                        "operating_status": "Open",
                    }
                ],
                "location_count": 1,
                "open_count": 1,
                "closed_count": 0,
                "has_next_page": False,
                "end_cursor": "cursor_1",
            },
        }

    monkeypatch.setattr(enigma, "match_business", _mock_match_business)
    monkeypatch.setattr(enigma, "get_brand_locations", _mock_get_brand_locations)

    result = await execute_company_enrich_locations(input_data={"company_domain": "mcdonalds.com"})
    validated = EnigmaLocationsOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert calls == ["match", "locations"]
    assert len(result["provider_attempts"]) == 2
    assert result["provider_attempts"][0]["action"] == "match_business"
    assert result["provider_attempts"][1]["action"] == "get_brand_locations"
    assert validated.brand_name == "McDonald's"
    assert validated.location_count == 1
