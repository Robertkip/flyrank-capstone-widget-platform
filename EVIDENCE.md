# EVIDENCE

Every block is real output from a local run: `uvicorn` on :8000, the demo site on :5500 (`python -m http.server`), and SQLite seeded with `scripts.seed`. Geo uses the deterministic mock providers. `TRUST_X_FORWARDED_FOR=1` lets curl simulate different visitors.

Test suite, `python -m pytest -v` (18 tests):
```
tests/test_delivery.py::test_config_is_small_cached_and_etagged PASSED
tests/test_delivery.py::test_bundle_is_versioned_and_immutable PASSED
tests/test_delivery.py::test_loader_points_to_current_bundle PASSED
tests/test_owner_api.py::test_requests_without_valid_auth_are_rejected PASSED
tests/test_owner_api.py::test_crud_and_embed_snippet PASSED
tests/test_owner_api.py::test_widget_validation PASSED
tests/test_owner_api.py::test_tenant_isolation PASSED
tests/test_resilience.py::test_probe4_provider_a_down_b_answers PASSED
tests/test_resilience.py::test_probe4_all_providers_down_still_stored PASSED
tests/test_resilience.py::test_probe5_failing_email_does_not_block_submission PASSED
tests/test_resilience.py::test_successful_email_is_sent PASSED
tests/test_resilience.py::test_dashboard_stats PASSED
tests/test_submissions.py::test_preflight_and_cors PASSED
tests/test_submissions.py::test_probe1_valid_submission_stored_and_visible PASSED
tests/test_submissions.py::test_probe2_malformed_and_oversized_are_clean_4xx PASSED
tests/test_submissions.py::test_disallowed_origin_is_refused PASSED
tests/test_submissions.py::test_probe3_burst_gets_429_and_service_keeps_serving PASSED
tests/test_submissions.py::test_probe6_honeypot_and_time_trap_block_bots PASSED
============================== 18 passed in 1.91s ==============================
```

## Widget management

**☑ Authenticated CRUD; requests without valid auth are rejected.**
```
no token -> 401
bad token -> 401
```
The full CRUD sequence is `test_crud_and_embed_snippet`: POST 201, GET, PATCH (`config_version` 1→2), DELETE 204, then GET 404.

**☑ Multi-tenant isolation.** "Other Company" tries to touch the bakery's widget and submissions:
```
GET other tenant's widget -> 404
PATCH other tenant's widget -> 404
DELETE other tenant's widget -> 404
{"detail":"widget not found"} -> 404
```
The response is 404 rather than 403, so it doesn't even reveal that the widget exists.

**☑ Embed snippet generated per widget.**
```
201 created wgt_OnK1lmfW9wFT
embed_snippet: <script src="http://localhost:8000/widget.js?id=wgt_OnK1lmfW9wFT" async></script>
```

## Widget delivery

**☑ Public config: small payload, correct cache headers.**
```
HTTP/1.1 200 OK
access-control-allow-origin: *
cache-control: public, max-age=60, stale-while-revalidate=300
etag: "53ed6ae89f66d8c2"
content-length: 486
If-None-Match -> 304
```
It is 486 bytes and contains no private fields (`notify_email` and `allowed_origins` are stripped). The ETag gives a 304 revalidation.

**☑ Versioned bundle.** The loader has a short cache; the bundle URL contains a content hash and is cached for a year as `immutable`. An old hash gets a 301 to the current one:
```
HTTP/1.1 200 OK
cache-control: public, max-age=300
bundle: /assets/widget-a327e1b19682.js
HTTP/1.1 200 OK
cache-control: public, max-age=31536000, immutable
HTTP/1.1 301 Moved Permanently
location: /assets/widget-a327e1b19682.js
```

**☑ The widget renders on a page from a different origin.** Chromium opened `http://localhost:5500/`, filled in the form and submitted it (the API is on :8000):

![second-origin demo](docs/second-origin-demo.png)

```
200 GET http://localhost:8000/widget.js?id=wgt_demoSignup01          cache=public, max-age=300
200 GET http://localhost:8000/assets/widget-a327e1b19682.js           cache=public, max-age=31536000, immutable
200 GET http://localhost:8000/widgets/wgt_demoSignup01/config         cache=public, max-age=60, stale-while-revalidate=300
API log: "OPTIONS /submissions HTTP/1.1" 204   ← browser preflight
         "POST /submissions HTTP/1.1" 201
widget status text: Thank you! We received your details.   (no console errors)
```

## Public submission API

**☑ Cross-origin submissions work: CORS + preflight.**
```
HTTP/1.1 204 No Content
access-control-allow-origin: http://localhost:5500
access-control-allow-methods: POST, OPTIONS
access-control-allow-headers: Content-Type
access-control-max-age: 600
```

**☑ Input validated; malformed and oversized payloads → 4xx JSON.** (probe 2)
```
{"error":"malformed_json","message":"request body is not valid JSON"} -> 400
{"error":"payload_too_large","message":"body exceeds 10240 bytes"} -> 413
{"error":"validation_failed","errors":[{"field":"isAdmin","error":"unknown field"},{"field":"name","error":"required"},{"field":"email","error":"not a valid email address"}]} -> 422
```
415 (wrong content type) and 404 (unknown widget) are covered in `test_probe2_malformed_and_oversized_are_clean_4xx`. A disallowed origin gets 403 (`test_disallowed_origin_is_refused`).

**☑ Valid submissions stored, linked to the right widget and tenant.** (probe 1)
```
HTTP/1.1 201 Created
access-control-allow-origin: http://localhost:5500
{"ok":true,"submission_id":5,"enriched":true}

[{"id":5,"widget_id":1,"data":{"name":"Amina","email":"amina@example.com"},"origin":"http://localhost:5500","geo":{"country":"Kenya","country_code":"KE","city":"Nairobi","provider":"mock_a"},"created_at":"2026-09-27T08:34:43.098434"}]
```

## Abuse protection

**☑ Rate limiting → 429 under a burst; legitimate traffic still served.** (probe 3; limit 5 per IP per 10 s)
```
201 201 201 201 201 429 429 429 
retry-after: 10
{"error":"rate_limited","scope":"ip","message":"too many submissions from this ip; retry in 10s"}

{"ok":true,"submission_id":11,"enriched":true} -> 201 (different visitor right after)
```

**☑ Spam prevention blocks a bot submission.** (probe 6) Two layers: a filled honeypot, and a time trap for forms submitted under 1.5 s after render:
```
{"ok":true} -> 202
{"ok":true} -> 202
```
Both get a bland `202 {"ok": true}`, so a bot learns nothing, and neither is stored. The dashboard counts them (`"spam_blocked": 2` in the stats below).

## Enrichment & safe side effects

**☑ Provider A down → provider B answers.** **☑ All providers down → still stored.** (probe 4)
```
{"down":["mock_a"],"chain":["mock_a","mock_b"]}
{"ok":true,"submission_id":12,"enriched":true}
stored geo: {'country': 'Kenya', 'country_code': 'KE', 'city': 'Kisii', 'provider': 'mock_b'}
{"down":["mock_a","mock_b"],"chain":["mock_a","mock_b"]}
{"ok":true,"submission_id":13,"enriched":false} -> 201
stored geo: {'country': None, 'country_code': None, 'city': None, 'provider': None}
```

**☑ A failing email doesn't prevent storing.** (probe 5) The email is sent by a background worker with 3 retries and an alert:
```
{"email_forced_failure":true}
{"ok":true,"submission_id":14,"enriched":true} -> 201
2026-09-27 11:34:43,931 ERROR notify ALERT notification 11 for submission 14 failed after 3 attempts: email provider unavailable (forced failure)
```

## Dashboard
```
{"period_days":30,"total_submissions":14,"per_day":[{"date":"2026-09-27","count":14}],"per_widget":[{"widget_id":"wgt_demoSignup01","title":"Get our weekly specials","submissions":14,"spam_blocked":2},{"widget_id":"wgt_OnK1lmfW9wFT","title":"Contact us","submissions":0,"spam_blocked":0}],"by_country":[{"country":"Kenya","count":12},{"country":"Unknown","count":2}],"enriched_pct":85.7,"notifications":{"failed":1,"sent":10}}
```

## Documentation
**☑** `README.md` (architecture diagram, setup, API docs, limitations), `capstone.yaml`, `EVIDENCE.md`, `BUILDLOG.md`, `.env.example`, `docs/DESIGN.md`, `LICENSE`.
