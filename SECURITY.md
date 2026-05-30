# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in TradeRunner, **please do NOT open a public GitHub issue**. Instead, email the maintainer directly so the issue can be patched before disclosure.

**Contact:** human.artem@icloud.com

Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- (Optional) Suggested fix

We aim to respond within 72 hours and ship a patch within 7 days for critical issues.

## What TradeRunner Protects

TradeRunner is a **personal crypto trading journal** that can be self-hosted or deployed as a multi-user SaaS. We protect:

- **User passwords**: hashed with Werkzeug PBKDF2-SHA256 (never stored in plaintext)
- **Exchange API keys**: encrypted at rest using **Fernet (AES-128-CBC + HMAC-SHA256)**. The encryption key is **derived from the user's password via Argon2id** (OWASP 2024 params: time=2, memory=19MB, parallelism=1) and only exists in the active session — never persisted to disk.
- **Tenant isolation**: every database row has a `user_id` foreign key. All queries filter by the authenticated user. `_current_user_id()` raises RuntimeError if no user is set, so a "forgotten filter" is structurally impossible.
- **CSRF**: Origin/Referer same-origin check on all mutating endpoints + ProxyFix for Railway.
- **Rate limiting**:
  - `/login`: 5 attempts / 15 min / IP
  - `/register`: 3 / hour / IP
  - `/api/sync`: 1 / 30 sec / user
  - Verification resend: 1 / 60 sec / user
- **Email verification** for new registrations (since v4.1, 2026-05-30).
- **Password reset** via email with single-use, signed tokens (1-hour TTL, `itsdangerous`).
- **HTTP security headers** (since v4.1): HSTS, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy (disabling camera/microphone/geolocation), basic Content-Security-Policy.
- **Secure cookies**: HttpOnly + SameSite=Lax always; Secure when `IS_PROD` (detected via `RAILWAY_ENVIRONMENT` / `RENDER` / `PRODUCTION` / `DYNO`).
- **Global error handler**: tracebacks never leak to users even on unhandled exceptions; JSON 500 for `/api/*`, HTML 500 for the rest.

## Zero-Knowledge Architecture

Even the server administrator **cannot decrypt** a user's API keys without their password. If a user forgets their password:
- Their trade history and goals remain accessible (not encrypted)
- Their exchange API keys are **unrecoverable** — they must re-enter them after password reset
- Password reset endpoint automatically clears the encrypted-but-now-undecryptable API keys to avoid stale ciphertext

This is a deliberate trade-off to protect users from a malicious admin or a database breach.

The **admin panel** (`/admin/*`, accessible only to `is_admin=True`) shows user metadata, activity stats, and audit logs — but **does not** and **cannot** decrypt other users' exchange API keys.

## Fixed Vulnerabilities (sec-fix 2026-05-30)

Three critical vulnerabilities were fixed and released in v4.1:

1. **`/api/credentials` GET returned plaintext exchange API keys.** Any XSS or stolen session cookie could exfiltrate Bitunix keys. Fixed: GET now returns only a mask (`••••cd34`) and a boolean `api_connected` flag.

2. **`/logout` didn't actually log out.** It cleared the encryption key but did not call `logout_user()` — Flask-Login session remained valid. It also accepted GET, exposing it to CSRF via `<img src=/logout>`. Fixed: POST-only, calls `logout_user()` + flash + redirect.

3. **`/share/<token>` could leak another user's data.** Share tokens were kept in an in-memory dict without an owner. An unauthenticated visitor got a 500; an authenticated visitor got *their own* data on someone else's share URL. Fixed: tokens are now stored in the `ShareLink` DB model with `user_id`, and queries use the explicit owner ID.

Additional hardening in the same release: rate-limit on `/register`, security headers, explicit PROD flag, global error handler, `security_pin` moved from a global setting to per-user.

## Recommended Production Hardening

When deploying TradeRunner:

1. **Use HTTPS only** (Railway/Render do this automatically)
2. **Use read-only / Sending-access API keys** on exchanges (TradeRunner never needs withdraw permissions)
3. **Set a strong `FLASK_SECRET_KEY`** as an environment variable (at least 32 random bytes)
4. **Set `RESEND_API_KEY`** for verification/reset emails (without it, links are logged to console — fine for self-host, not for public SaaS)
5. **Enable PostgreSQL with backups** (Railway includes automated daily backups) or use a Persistent Volume for SQLite
6. **Add Cloudflare** in front for DDoS protection and rate limiting
7. **Rotate keys periodically** — TradeRunner shows a reminder after 90 days (planned for v4.2)
8. **Restrict registration** if you don't want public signups — set `is_blocked=True` on new users via admin panel until manually approved (manual workflow for now)

## Out of Scope

These are **not** considered vulnerabilities:
- Information disclosure when running with `FLASK_DEBUG=1` (debug mode is for development only — never use in production)
- Self-XSS in user-supplied trade notes (notes are escaped on render)
- Slow login responses (mitigated by Argon2id's intentionally slow KDF; consider Cloudflare Bot Management for further protection)
- The `PACEMAKER_DB` environment variable name (legacy from the v3 era; harmless backward-compat alias)
