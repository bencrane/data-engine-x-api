"""Enigma MCP client — session management, tool calling, credit guard.

Manages a singleton MCP session against https://mcp.enigma.com/http-key
using JSON-RPC 2.0. Provides call_tool() and list_tools() as the public API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENIGMA_MCP_URL = "https://mcp.enigma.com/http-key"
MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_CLIENT_NAME = "data-engine-x"
MCP_CLIENT_VERSION = "1.0.0"
SESSION_TTL_SECONDS = 30 * 60  # 30 minutes

# Screening tools blocked from proxy calls (different auth model, compliance workflow)
BLOCKED_TOOLS = {
    "screen_customer",
    "screen_business",
    "screen_entity_search",
    "find_decision",
    "find_decisions",
    "update_decision",
}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class McpError(Exception):
    """Base MCP error."""


class McpSessionError(McpError):
    """Session initialization or refresh failure."""


class McpRateLimitError(McpError):
    """429 rate limit hit."""


class McpInsufficientCreditsError(McpError):
    """402 insufficient credits."""


class McpCallError(McpError):
    """Generic tool call failure."""


class McpToolBlockedError(McpError):
    """Tool is in BLOCKED_TOOLS set."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_session_expired_error(resp: httpx.Response) -> bool:
    """Heuristic check for session-expired indicators in the response."""
    if resp.status_code == 404:
        return True
    try:
        body = resp.json()
        error = body.get("error", {})
        msg = str(error.get("message", "")).lower()
        code = error.get("code")
        if "session" in msg and ("expired" in msg or "invalid" in msg or "not found" in msg):
            return True
        # JSON-RPC error code -32000 range is often used for session errors
        if isinstance(code, int) and -32099 <= code <= -32000:
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Session singleton
# ---------------------------------------------------------------------------


class _McpSession:
    """Manages a single MCP session with lazy init and auto-refresh."""

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.initialized_at: float = 0.0
        self._lock = asyncio.Lock()
        self._request_counter: int = 0
        self._tools_cache: list[dict] | None = None
        self._tools_cached_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        if not self.session_id:
            return True
        return (time.time() - self.initialized_at) > SESSION_TTL_SECONDS

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    async def _ensure_session(self, api_key: str) -> str:
        """Return a valid session_id, initializing if needed."""
        if not self.is_expired:
            return self.session_id  # type: ignore

        async with self._lock:
            # Double-check after acquiring lock
            if not self.is_expired:
                return self.session_id  # type: ignore
            return await self._initialize(api_key)

    async def _initialize(self, api_key: str) -> str:
        """Send initialize request and store the session ID."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": MCP_CLIENT_NAME,
                    "version": MCP_CLIENT_VERSION,
                },
            },
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                ENIGMA_MCP_URL,
                json=payload,
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
            )
        if resp.status_code != 200:
            raise McpSessionError(
                f"MCP initialize failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )

        session_id = resp.headers.get("mcp-session-id")
        if not session_id:
            # Try extracting from response body as fallback
            body = resp.json()
            session_id = body.get("sessionId") or body.get("session_id")
        if not session_id:
            raise McpSessionError(
                "MCP initialize succeeded but no mcp-session-id in response headers or body"
            )

        self.session_id = session_id
        self.initialized_at = time.time()
        self._tools_cache = None  # Invalidate tools cache on new session
        logger.info("MCP session initialized: %s", session_id[:12])
        return session_id

    async def _send(
        self, *, api_key: str, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a JSON-RPC request using the current session."""
        session_id = await self._ensure_session(api_key)
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "mcp-session-id": session_id,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(ENIGMA_MCP_URL, json=payload, headers=headers)

        # Handle session expiry — re-init and retry once
        if resp.status_code in (401, 403) or _is_session_expired_error(resp):
            logger.warning("MCP session expired, re-initializing...")
            self.session_id = None  # Force re-init
            session_id = await self._ensure_session(api_key)
            headers["mcp-session-id"] = session_id
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(ENIGMA_MCP_URL, json=payload, headers=headers)

        if resp.status_code == 429:
            raise McpRateLimitError("MCP rate limited (429)")
        if resp.status_code == 402:
            raise McpInsufficientCreditsError("MCP insufficient credits (402)")
        if resp.status_code != 200:
            raise McpCallError(
                f"MCP {method} failed: HTTP {resp.status_code} — {resp.text[:500]}"
            )

        body = resp.json()
        if "error" in body:
            error = body["error"]
            raise McpCallError(
                f"MCP JSON-RPC error: [{error.get('code')}] {error.get('message', '')}"
            )

        return body.get("result", {})


_session = _McpSession()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_tool(
    *,
    api_key: str,
    tool_name: str,
    arguments: dict[str, Any],
    max_results: int | None = None,
) -> dict[str, Any]:
    """Call an MCP tool and return parsed results.

    Returns:
        {
            "tool": str,
            "raw_content": list[dict],   # Original MCP content blocks
            "parsed_result": Any | None,  # JSON-parsed result if text was valid JSON
            "raw_text": str | None,       # Raw text if not JSON-parseable
            "is_structured": bool,        # True if parsed_result is not None
        }
    """
    if tool_name in BLOCKED_TOOLS:
        raise McpToolBlockedError(
            f"Tool '{tool_name}' is not available via proxy. "
            "Screening tools are not yet supported. Contact engineering."
        )

    # Credit guard: inject or override limit
    effective_args = {**arguments}
    if max_results is not None:
        effective_args["limit"] = max_results
    elif "limit" not in effective_args:
        effective_args["limit"] = 10  # Safety default per D3
    else:
        if effective_args["limit"] > 50:
            logger.warning(
                "MCP tool %s called with limit=%d — high credit cost",
                tool_name,
                effective_args["limit"],
            )

    logger.info(
        "MCP tool call: %s (args keys: %s, limit: %s)",
        tool_name,
        list(effective_args.keys()),
        effective_args.get("limit"),
    )

    result = await _session._send(
        api_key=api_key,
        method="tools/call",
        params={"name": tool_name, "arguments": effective_args},
    )

    # Parse content blocks
    content_blocks = result.get("content", [])
    all_text = "\n".join(
        block.get("text", "")
        for block in content_blocks
        if block.get("type") == "text"
    )

    # Try structured JSON parse (D5)
    parsed = None
    try:
        parsed = json.loads(all_text)
        if not isinstance(parsed, (dict, list)):
            parsed = None  # Only accept dicts/lists as structured
    except (json.JSONDecodeError, TypeError):
        pass

    return {
        "tool": tool_name,
        "raw_content": content_blocks,
        "parsed_result": parsed,
        "raw_text": all_text if parsed is None else None,
        "is_structured": parsed is not None,
    }


async def list_tools(
    *, api_key: str, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Return the list of available MCP tools with schemas.

    Cached for the lifetime of the session.
    """
    cache_age = time.time() - _session._tools_cached_at
    if (
        _session._tools_cache is not None
        and not force_refresh
        and cache_age < SESSION_TTL_SECONDS
    ):
        return _session._tools_cache

    result = await _session._send(
        api_key=api_key,
        method="tools/list",
        params={},
    )
    tools = result.get("tools", [])
    _session._tools_cache = tools
    _session._tools_cached_at = time.time()
    logger.info("MCP tools list refreshed: %d tools", len(tools))
    return tools
