# BUILDLOG: AI usage log

| Date | Where AI helped | What was wrong / what I changed |
|---|---|---|
| 2026-09-27 | Claude drafted the FastAPI layers, models, widget bundle, tests and docs. | Reviewed each module before committing. |
| 2026-09-27 | Spam check order. | The first version validated fields **before** the honeypot check, so a bot with a filled honeypot and bad data got a detailed 422, which teaches the bot something. Moved the spam checks first so bots always get the same bland 202. |
| 2026-09-27 | Geo fallback with real providers. | A precedence bug in the "skip private IPs" condition (`a and b or (a and c)`) was rewritten as two clear statements. Real providers can't locate 127.0.0.1, which is why the probes use deterministic mock providers (as the brief asks). |
| 2026-09-27 | Loader for several widgets on one page. | The first loader always injected the bundle, and a second widget on the same page never mounted. The bundle now exposes `__leadWidgetScan`, and later loaders call it instead of loading the bundle again. |
| _add yours_ | _e.g. your CORS debugging afternoon_ | |

Lines I can explain: the preflight response in `main.py`; why `ETag`/304 plus a short `max-age` for config but `immutable` for the bundle; `ratelimit.SlidingWindow.check` (only allowed hits are counted); why `submit()` commits **before** `notify.enqueue`.
