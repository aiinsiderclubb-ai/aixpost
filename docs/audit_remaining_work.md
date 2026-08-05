# Remaining AIPostX hardening work

The active runtime now has production secret validation, cookie/header JWT authentication,
per-user task/template isolation, and durable local/RQ task failure handling.

Future architectural work intentionally remains out of scope for this remediation:

- Migrate the monolithic `run_test_v2.py` application to an application-factory layout.
- Replace SQLite runtime coordination with a production database for multi-host deployment.
- Containerize the web, worker, Redis, and browser automation services with production TLS and
  secret injection.
- Add integration tests that exercise authenticated Socket.IO, RQ failure recovery, and
  Facebook verification flows against controlled test doubles.
