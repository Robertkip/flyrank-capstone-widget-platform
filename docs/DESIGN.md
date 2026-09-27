# Design doc: Embeddable Widget & Lead-Capture Platform

**Problem.** A customer wants a signup or contact form on their site with one line of code. The backend receives traffic from browsers it doesn't control, so every request is untrusted, bursty and cross-origin.

## Data model
| Table | Purpose | Indexes / integrity |
|---|---|---|
| `tenants` | owners; API token stored as a SHA-256 hash | unique `token_hash` |
| `widgets` | `public_id`, tenant, type, title, fields (JSON spec), display, allowed_origins, config_version | unique `public_id`, index `tenant_id` |
| `submissions` | widget, **tenant (denormalised)**, cleaned data, origin, `ip_hash`, geo fields, provider | `(tenant_id, created_at)`, `(widget_id, created_at)` |
| `spam_events` | blocked bot attempts (counter only, no payload) | `widget_id` |
| `notifications` | side-effect status: queued/sent/failed, attempts, error | `status` |

## Embed flow
1. `<script src="/widget.js?id=wgt_…">` loads the **loader** (5-minute cache).
2. The loader tags its own `<script>` and loads the **versioned bundle** `/assets/widget-<sha>.js` (1 year, `immutable`).
3. The bundle fetches `GET /widgets/<id>/config` (60 s + ETag) and renders into a **Shadow DOM**.
4. The visitor submits `POST /submissions`; the browser sends a preflight `OPTIONS` first.

## API contracts (three paths)
- **Owner (Bearer):** `POST/GET/PATCH/DELETE /api/widgets`, `/api/widgets/{id}/embed`, `/api/submissions`, `/api/stats`.
- **Delivery (public, cached):** `/widget.js`, `/assets/widget-{hash}.js`, `/widgets/{id}/config`.
- **Visitor (public, CORS):** `OPTIONS` and `POST /submissions`.

## Submission pipeline
1. Size check (413), then content type (415), JSON (400) and shape (400).
2. Widget exists (404) and the origin is allowed (403).
3. Rate limit per IP and per widget (429 + `Retry-After`).
4. Spam checks: honeypot, time trap, link heuristic → silent 202.
5. Field validation against the widget's own spec (422).
6. Geo lookup with provider A → B → none.
7. **Commit.**
8. Queue the notification in the background (3 retries, alert on failure).

## Non-goal
No drag-and-drop form builder, no hosted CDN, no real email delivery (it's logged, or caught by Mailpit).
