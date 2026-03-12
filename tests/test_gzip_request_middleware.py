import gzip
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware.gzip_request import GzipRequestMiddleware, MAX_DECOMPRESSED_SIZE


def _create_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(GzipRequestMiddleware)

    @test_app.post("/test-echo")
    async def echo(request: Request):
        body = await request.json()
        return JSONResponse(content={"received": body})

    return test_app


client = TestClient(_create_test_app())


def test_gzip_request_decompressed_correctly():
    payload = {"rows": [{"id": 1, "name": "test"}, {"id": 2, "name": "other"}]}
    compressed = gzip.compress(json.dumps(payload).encode("utf-8"))

    response = client.post(
        "/test-echo",
        content=compressed,
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )

    assert response.status_code == 200
    assert response.json()["received"] == payload


def test_uncompressed_request_passes_through():
    payload = {"hello": "world"}

    response = client.post("/test-echo", json=payload)

    assert response.status_code == 200
    assert response.json()["received"] == payload


def test_oversized_decompressed_body_returns_413():
    # Create a body that will exceed the limit when decompressed.
    # Gzip compresses repeated bytes very well, so a small compressed
    # payload can decompress to a huge size.
    # We create a payload just over the limit.
    over_limit = MAX_DECOMPRESSED_SIZE + 1
    raw_body = b"x" * over_limit
    compressed = gzip.compress(raw_body)

    response = client.post(
        "/test-echo",
        content=compressed,
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )

    assert response.status_code == 413
    assert "size limit" in response.json()["error"].lower()


def test_invalid_gzip_body_returns_400():
    response = client.post(
        "/test-echo",
        content=b"this is not gzip",
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )

    assert response.status_code == 400
    assert "invalid" in response.json()["error"].lower()
