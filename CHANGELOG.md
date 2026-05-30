# CHANGELOG

All notable changes to TradeRunner. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org).

## [v4.1] — 2026-05-30 — sec-fix + Admin Panel

### 🛑 Fixed (critical security)

- **`/api/credentials` GET no longer returns plaintext API keys** — only `api_key_mask` ("••••cd34") and `api_connected` boolean. Protects against XSS/session-theft leaking Bitunix credentials. Added `DELETE /api/credentials` and `{clear: true}` POST flag for clearing keys.
- **`/logout` now properly logs out** — POST-only (CSRF-safe), calls `logout_user()`, returns redirect with flash. Was previously a no-op that left Flask-Login session valid and accepted GET.
- **`/share/<token>` no longer leaks data** — tokens are stored in the `ShareLink` DB model with `user_id`. Queries use the explicit owner. Previous in-memory dict without owner caused 500 for unauthenticated visitors and *wrong user's data* for authenticated ones. Added `POST /api/share/revoke` for revocation.
- **`security_pin` is now per-user** — was in the global `settings` table without `user_id` (one PIN shared by all users — multi-tenant violation). Now in `user_settings`.

### ✨ Added

- **Email verification** — new registrations must confirm email before login. Tokens via `itsdangerous` (24h TTL).
- **Password reset** flow: `/auth/forgot-password` → email → `/auth/reset-password/<token>` (1h TTL). Resets `kdf_salt` and clears encrypted API keys (zero-knowledge preserved — old ciphertext can't be decrypted with new password).
- **Resend integration** (`email_service.py`) — Free tier 100 emails/day. Without `RESEND_API_KEY`, falls back to DEV mode (logs link to console).
- **Admin Panel** (`/admin/*`, blueprint `admin_views.py`):
  - `/admin/` — dashboard with metrics (total/new/active users, connected exchanges, trades, goals, share links) + 2 Chart.js graphs (signups, DAU per day)
  - `/admin/users` — paginated list with search + sort
  - `/admin/users/<id>` — user card + actions (block/unblock, make admin / demote, verify email, resend verification)
  - `/admin/audit` — global audit log with filters by user / action
  - `/admin/share-links` — active share-link monitoring
  - Star icon in dashboard header only for `is_admin=True`
- **Security headers** (always-on `@app.after_request`):
  - HSTS (`max-age=15552000; includeSubDomains`) in PROD only
  - X-Frame-Options DENY (clickjacking protection)
  - X-Content-Type-Options nosniff
  - Referrer-Policy strict-origin-when-cross-origin
  - Permissions-Policy (camera/microphone/geolocation/FLoC disabled)
  - Content-Security-Policy (basic — allowed CDN cdn.jsdelivr.net, cdnjs.cloudflare.com)
- **Rate-limit on `/register`**: 3 per hour per IP.
- **Resend-verification rate-limit**: 1 per 60 sec per user.
- **Global error handler** `@app.errorhandler(Exception)` — no traceback ever leaks; JSON 500 for `/api/*`, HTML 500 otherwise.
- **Explicit PROD flag** `IS_PROD` from `RAILWAY_ENVIRONMENT` / `RENDER` / `PRODUCTION` / `DYNO` (replaces the hack `bool(FLASK_SECRET_KEY)`).
- **Auto-migration** for new columns (`email_verified`, `email_verification_sent_at`, `is_blocked`) — idempotent ALTER TABLE on startup (SQLite + PostgreSQL).
- New user columns: `email_verified`, `email_verification_sent_at`, `is_blocked`.
- New model `ShareLink` (was defined but unused before).

### 📚 Docs

- README.md fully rewritten — features, env vars, security, structure, roadmap.
- SECURITY.md expanded with fixed vulnerabilities section + new defenses.
- This CHANGELOG.md added.

### 📦 Dependencies

- `itsdangerous>=2.1` (explicit; was transitive via Flask) — for one-time tokens.
- Stdlib `urllib.request` used for Resend HTTP API (no extra HTTP client dependency).

---

## [v4.0] — 2026-05-28 — Multi-tenant SaaS

### Added

- Multi-tenant data isolation: every table has `user_id` FK with CASCADE delete.
- Zero-knowledge encryption of exchange API keys: Argon2id KDF + Fernet AES-128-CBC + HMAC-SHA256.
- User registration / login / logout via Flask-Login.
- SQLAlchemy ORM models alongside legacy sqlite functions.
- Migration script `migrate_to_v4.py` for v3.2 → v4.0.
- Railway deployment ready: Procfile, `.env.example`, auto Postgres URL.
- CSRF Origin/Referer check + per-session token.
- Rate-limit on `/api/sync` (1 per 30 sec).
- Audit log of settings/goals/trades changes.
- Logging with rotation (`logs/app.log`).
- Strong password requirements (8+ chars, letter+digit).
- Renamed product Pacemaker → TradeRunner.
- AGPL-3.0 license.

### Infrastructure

- GitHub repo created: `Cardsoff/traderunner`.
- Railway project deployed at `https://web-production-dbdcd.up.railway.app`.
- Telegram bet-community group created: [TradeRunner | Бета-комьюнити](https://t.me/+vMGOG45hjKo3Nmdy).

---

## [v3.x] — 2026-05-24 to 2026-05-27 — single-user incarnation

Earlier versions of TradeRunner (then called "Pacemaker" and before that "Crypto Trading Financial Planner") were single-user local Flask apps. See git history for details: bug fixes, dashboard UX overhaul, trader analytics (Sharpe/Sortino/R-multiple/heatmap), PDF reports, mobile adaptation, security hardening v1.
