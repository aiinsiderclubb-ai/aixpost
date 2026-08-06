# Credentials security (current runtime)

Applies to **`run_test_v2.py`** (canonical app), not legacy `web_app.py`.

## Storage

| Secret | Mechanism |
|--------|-----------|
| Dashboard password | bcrypt |
| Facebook password (user + accounts) | Fernet (`FERNET_KEY` or `encryption.key`) |
| JWT | HttpOnly cookies (`access_token`, `refresh_token`) |
| Telegram bot token | plaintext in DB/env (treat as secret) |

## API behavior

- `GET /api/credentials` and `POST /api/credentials/load` return **username only** (`has_saved_credentials`), never the Facebook password.
- Account create/update stores `encrypted_password` in `platform_runtime.db`.
- Decrypt happens only inside workers/runners for automation.

## CSRF / cookies

- Mutating requests require Flask-WTF CSRF (`X-CSRFToken`) when CSRF is enabled.
- Do not store JWT in `localStorage` or query strings.

## Ops

- Rotate `FERNET_KEY` carefully (re-encrypt existing rows).
- Never commit `.env`, `encryption.key`, or profile/cookie directories (see `.gitignore`).
