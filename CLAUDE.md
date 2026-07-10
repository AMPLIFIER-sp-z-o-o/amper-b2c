# amper-b2c — B2C storefront (project `amplifier`)

Django 6.0 / Python 3.12 / uv storefront (SaaS Pegasus lineage: HTMX + Alpine, Vite 7 +
Tailwind v4, Celery/Redis, logical Team tenancy — NOT schema tenancy). Coding conventions
live in `AGENTS.md`. DB `amplifier` on docker pg port **7432**.

## Golden rules

1. **The dev server on :8000 is always already running — never start it.** It embeds the
   LAS chat widget served by las-backend :8001 (also always running).
2. **Git: push straight to `main`.** Never create a feature branch or PR in this repo.
3. English is the i18n source language here too; natural Polish, no calques.

## Commands

- Tests (pytest, `--reuse-db` baked in): `make test`, `make test-parallel` (xdist).
  Windows gotcha: `uv run pytest -n auto` fails ("Failed to canonicalize script path") —
  the make target correctly uses `uv run python -m pytest -n auto`.
- `uv run manage.py relay_outbox` flushes pending LAS event outbox.

## LAS integration traps

- `LiveAssistedSalesSettings.store_api_key` must equal las-backend
  `TrackedSite.write_key`. **Recreating the LAS store outside its seed rotates the key**
  → ingest 403s silently (widget still loads from cached `site_public_key`; browser
  events still 200). Empty live-activity panel = stale key: paste new write_key + run
  the settings connection test. `manage.py seed` wires this automatically (env-matched
  default key for localhost/QA + auto connection test); las-backend `make seed` keeps
  its write_key stable, so the pair survives re-seeding on both sides.
- Widget iframe (:8001 inside :8000 page) is cross-origin — drive it via chrome-devtools
  CDP, not page-context JS. DEBUG bypasses the Origin==store-domain check for localhost.
- Chat: pre-chat form (email required) skipped when `window.LAS_CUSTOMER` set; anonymous
  visitors get multi-conversation history; all chat UX lives in the las-backend widget —
  never build chat UI in this repo.
- Business events (orders/carts) are emitted SERVER-side; `session_start` + telemetry
  client-side. Event taxonomy is GA4 names (view_item, add_to_cart, purchase…).
