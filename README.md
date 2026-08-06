# AIPostX

Facebook group posting automation with a multi-user Flask dashboard, durable task control, and optional Redis/RQ workers.

## What this is

- **Runtime:** Selenium + Chrome automate Facebook group fetch/post.
- **Dashboard:** JWT (HttpOnly cookies) + Socket.IO UI in `run_test_v2.py`.
- **App DB:** SQLite locally; Postgres when `DATABASE_URL` is set (Docker Compose).
- **Runtime coordination:** SQLite `platform_runtime.db` (single-host; not multi-replica yet).
- **Queues:** in-process threads by default; Redis RQ when `USE_RQ_WORKERS=true`.
- **Plans:** FREE / PLUS / PREMIUM limits enforced in-app; **plan changes are admin-only** (no Stripe).

This is **not** a Celery/Stripe/React SaaS. Older docs that claim otherwise are outdated (`saas_structure.md`, historical `README_SAAS.md`).

## Risk notice

Automated mass posting to Facebook groups violates Facebook Terms of Service. Accounts can be checkpointed or banned. Use at your own risk and prefer manual, policy-compliant workflows where possible.

## Quick start (local)

```bash
cp .env.example .env
# set FERNET_KEY, FLASK_SECRET_KEY, JWT_SECRET_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./start_platform.sh web
# optional: USE_RQ_WORKERS=true ./start_platform.sh all
```

Open http://localhost:8080

## Docker Compose

Requires env: `FERNET_KEY`, `FLASK_SECRET_KEY`, `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`.

```bash
docker compose up --build
```

Services: `web`, `worker` (Chrome + Xvfb), `analytics-worker`, `redis`, `postgres`.

Runtime task DB remains a mounted SQLite volume (`runtime_data`) — suitable for single-host deployments.

## Security notes

- CSRF enabled (Flask-WTF); templates send `X-CSRFToken`.
- JWT access/refresh cookies are HttpOnly; do not put tokens in URLs.
- Facebook passwords encrypted at rest with Fernet (`FERNET_KEY`).
- Debug routes (`/groups_no_jwt`, etc.) only when `FLASK_DEBUG=true`.

## Tests

```bash
pytest -q tests/
```

## Layout

| Path | Role |
|------|------|
| `run_test_v2.py` | Live web/API entry |
| `app/factory.py` | Factory re-export |
| `app/services/` | Task dispatch, posting runner, control |
| `platform_runtime.py` | Task/account SQLite store |
| `bot/` | Selenium poster/fetcher |
| `archive/orphans/` | Quarantined legacy duplicates |
