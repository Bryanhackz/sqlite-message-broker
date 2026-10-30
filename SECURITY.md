# Security Policy

**Contact:** br4yangil006@gmail.com
**GitHub:** github.com/Bryanhackz
**LinkedIn:** linkedin.com/in/brayan-gil-68b70338b

## Scope

`sqlite-message-broker` is a persistent message broker built exclusively on
SQLite and the Python 3.11+ standard library. It targets on-prem air-gapped
environments with zero external dependencies.

**In scope:**
- HTTP endpoints for producer, consumer, and admin roles.
- Worker CLI (`python -m src.worker`).
- API-key issuance, revocation, and verification (`scrypt` +
  `hmac.compare_digest`).
- Rate limiting and audit log.
- Database schema and transaction handling.

**Out of scope:**
- Third-party WSGI servers (gunicorn, uvicorn, waitress).
- Multi-node deployment, clustering, or replication.
- Operator infrastructure (OS, network, disk, TLS terminator, reverse proxy).
- Client applications written by third parties.

## SLA

- Initial acknowledgment: **≤ 48 hours**.
- Mitigation plan: **≤ 7 days**.
- CRITICAL severity patch: **highest priority**.

## Responsible disclosure

Do **not** open a public issue for a security finding. Email
`br4yangil006@gmail.com` with:

1. Clear description of the finding.
2. Reproducible steps (commands, payload, configuration).
3. Estimated impact (confidentiality / integrity / availability).
4. Affected version or commit.
5. Optional name/handle for public credit after the fix ships.

Confirmation within ≤ 48 hours. If the finding is valid, a public
disclosure date is coordinated after the patch ships.

## Supported versions

Only the latest release on `main` receives security patches. Older branches
are unsupported.

## Project security practices

- Zero external dependencies (Python 3.11+ standard library only).
- API keys hashed with `scrypt` (N=2**14, r=8, p=1, 16-byte per-key salt).
- Constant-time secret comparison via `hmac.compare_digest`.
- Security headers on every response — success and error alike: CSP (no
  `unsafe-inline`), COOP, CORP, Permissions-Policy, `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; HSTS
  gated on `env=prod` AND `https`.
- Fixed-window rate limiting persisted in SQLite per IP.
- Parameterized SQL only; no string interpolation.
- Atomic claim/ack under `BEGIN IMMEDIATE`.
- Audit log for security-relevant events.

## Credits

Built and maintained by Bryan Gil (@Bryanhackz).