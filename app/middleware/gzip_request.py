import gzip
from starlette.types import ASGIApp, Receive, Scope, Send, Message

MAX_DECOMPRESSED_SIZE = 500 * 1024 * 1024  # 500 MB


class GzipRequestMiddleware:
    """ASGI middleware that transparently decompresses gzip-encoded request bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_encoding = headers.get(b"content-encoding", b"").decode("latin-1").strip().lower()

        if content_encoding != "gzip":
            await self.app(scope, receive, send)
            return

        # Collect the full request body
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        # Decompress
        try:
            decompressed = gzip.decompress(body)
        except Exception:
            await self._send_error(send, 400, "Invalid gzip body")
            return

        if len(decompressed) > MAX_DECOMPRESSED_SIZE:
            await self._send_error(send, 413, "Decompressed body exceeds size limit")
            return

        # Remove Content-Encoding from headers passed downstream
        new_headers = [
            (k, v) for k, v in scope["headers"]
            if k.lower() != b"content-encoding"
        ]
        # Update Content-Length to match decompressed size
        new_headers = [
            (k, v) for k, v in new_headers
            if k.lower() != b"content-length"
        ]
        new_headers.append((b"content-length", str(len(decompressed)).encode("latin-1")))

        scope = {**scope, "headers": new_headers}

        # Provide decompressed body as a single message
        body_sent = False

        async def receive_decompressed() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": decompressed, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, receive_decompressed, send)

    @staticmethod
    async def _send_error(send: Send, status: int, detail: str) -> None:
        import json
        body = json.dumps({"error": detail}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
