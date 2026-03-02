Implemented and committed both deliverables as requested.
Commit 1: e115891 — add retry-on-429 rate limiting to all BlitzAPI provider adapter functions
Commit 2: 7cc1efd — add tests for BlitzAPI rate limiting retry logic
(a) Functions updated with retry logic
domain_to_linkedin
company_search
person_search (both HTTP call paths: waterfall + employee finder)
search_employees
search_icp_waterfall
phone_enrich
Also added shared helper in app/providers/blitzapi.py:
_blitzapi_request_with_retry(...)
(b) Max retries and backoff formula
Max retries: 3 (so up to 4 total attempts)
Base delay: 2.0 seconds
Backoff: 2.0 * (2 ** attempt) for retry attempts, i.e. 2s, 4s, 8s
(c) How 429 with retry-after is handled
On 429, helper checks response.headers["retry-after"]
If present and numeric, uses that exact delay (seconds)
Otherwise falls back to exponential backoff
(d) How exhausted retries are surfaced in result
Helper returns the final 429 response after retries are exhausted
Existing per-function error handling then returns status: "failed" with http_status: 429 and raw_response preserved
(e) Test count and names
Added 4 tests in tests/test_blitzapi_rate_limiting.py:
test_retry_on_429_succeeds_on_second_attempt
test_retry_on_429_respects_retry_after_header
test_retry_exhausted_returns_failed
test_non_429_errors_not_retried
(f) Anything to flag
Could not execute tests in this shell because pytest is not installed in the current runtime (python3 -m pytest reports No module named pytest).
No linter issues reported for edited files.