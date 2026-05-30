# TradeRunner v4.1 — Multi-tenant SaaS (обновлено 2026-05-30)

**«Беги к своей цели. Считай каждый трейд»** — открытый журнал и аналитика крипто-сделок с биржи Bitunix.

🌐 **Бета:** https://web-production-dbdcd.up.railway.app
💬 **Чат комьюнити (баги/идеи):** https://t.me/+vMGOG45hjKo3Nmdy

Может работать локально (Flask + SQLite) или быть задеплоен на Railway/Render как мульти-пользовательский SaaS.

## ✨ Что нового в v4.1 (2026-05-30) — sec-fix + Admin Panel

- 🛑 **Закрыты 3 критичные дыры:**
  - `/logout` теперь только POST + `logout_user()` (раньше не разлогинивал, был уязвим к CSRF через `<img>`)
  - `/api/credentials` GET больше не возвращает plaintext API-ключи биржи — только маску `••••cd34` (защита от утечки через XSS)
  - `/share/<token>` использует модель `ShareLink` с `user_id` (раньше токены лежали в in-memory dict без owner — посетитель получал свои данные вместо данных шарящего)
- ✉ **Email verification** — новые юзеры подтверждают email перед первым входом
- 🔑 **Password reset** через email с одноразовыми токенами (TTL 1 час, через `itsdangerous`)
- 📨 Отправка писем через [Resend](https://resend.com) (free tier: 100 писем/день)
- 🛡 **Security headers**: HSTS, CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy, Permissions-Policy
- 🚪 Rate-limit на регистрацию: 3/час/IP
- 🚨 Глобальный errorhandler — traceback никогда не утекает юзеру даже при необработанном исключении
- 🔐 `security_pin` теперь per-user (раньше был один на всё приложение — нарушение multi-tenant)
- 🎚 Явный PROD-флаг через `RAILWAY_ENVIRONMENT` для secure cookies (раньше был хак на наличие `FLASK_SECRET_KEY`)
- 🛠 **Admin Panel** для владельца (`is_admin=True`):
  - `/admin/` — dashboard с метриками (всего юзеров, новые регистрации сегодня/неделя/месяц, DAU, подключенных бирж, активных целей, сделок) + 2 графика Chart.js
  - `/admin/users` — таблица всех юзеров с поиском, сортировкой, пагинацией
  - `/admin/users/<id>` — карточка юзера + действия (block/unblock, make admin, resend verification)
  - `/admin/audit` — общий audit log всех юзеров с фильтрами
  - `/admin/share-links` — мониторинг активных share-ссылок
  - Защита через декоратор `@admin_required` (403 для не-админа)
  - **Не расшифровывает чужие API-ключи биржи** — zero-knowledge сохраняется

## 📦 Что в v4.0 (2026-05-28)

- 👥 **Multi-tenant**: каждый пользователь видит только свои данные (физическая изоляция на уровне БД)
- 🔐 **Zero-knowledge шифрование API-ключей биржи** через Argon2id + Fernet
- 🚪 Регистрация / логин / logout (Flask-Login)
- 🗄 **SQLAlchemy ORM** — готовность к PostgreSQL для прода
- 🌐 Готовность к деплою на Railway (Procfile + .env + auto Postgres URL)
- 📊 30+ метрик: Sharpe, Sortino, Calmar, R-multiple, equity curve, heatmap по часам/дням
- 🎯 Цели + прогноз даты достижения
- ⚡ Открытые позиции live + unrealized PnL
- 🔗 Share read-only ссылка с маской сумм для ментора
- 📓 PDF-отчёт за месяц

---

## 🚀 Быстрый старт (локально)

### 1. Установи Python 3.10+

- **Windows:** [python.org](https://www.python.org/downloads/) → при установке поставь галочку **«Add Python to PATH»**
- **macOS:** `brew install python`
- **Linux:** `sudo apt install python3 python3-venv`

### 2. Запусти

- **Windows:** двойной клик по **`ЗАПУСТИ_МЕНЯ_TradeRunner.bat`**
- **macOS/Linux:** `./run.sh`

Браузер откроется на `http://localhost:5000/login`.

### 3. Зарегистрируйся

- `Зарегистрироваться` → email + пароль (8+ символов, обязательно буква+цифра)
- Перейди по ссылке из verification письма (на локалке без `RESEND_API_KEY` ссылка покажется через flash на странице)
- Залогинься

### 4. Подключи биржу

- Нажми pill **«Bitunix · не настроен»** в шапке → введи API Key + Secret → Сохранить
- На бирже Bitunix создавай ключ с правом **только "Sending access" / Read** (без Withdraw)
- Жми **Sync** — подтянутся сделки

---

## 🌐 Деплой на Railway (production)

### 1. Создай проект на Railway.app
- Connect GitHub repo
- Добавь Persistent Volume на `/data` (для SQLite на проде)
- Опционально: PostgreSQL service (Railway создаст `DATABASE_URL`)

### 2. Переменные окружения

**Обязательные:**
- `FLASK_SECRET_KEY` — strong random string (минимум 32 символа)
- `PACEMAKER_DB` = `/data/planner.db` — путь к SQLite БД (если без Postgres)

**Опциональные:**
- `DATABASE_URL` — Railway проставит из Postgres (если используешь)
- `PORT` — Railway проставит автоматически
- `RESEND_API_KEY` — для отправки verification и reset password писем (без этого письма ушли только в логи; получи на [resend.com](https://resend.com))
- `MAIL_FROM` — отправитель писем (по умолчанию `TradeRunner <onboarding@resend.dev>`)
- `RAILWAY_ENVIRONMENT` — Railway проставляет автоматически (нужно для HSTS/Secure cookies)

### 3. Деплой запустит `Procfile`:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60
```

### 4. Подключи домен (опционально)

- Railway даёт `*.up.railway.app` бесплатно
- Свой домен: `traderunner.app` (Namecheap, Porkbun) → CNAME

**Цена:** ~$5/мес Postgres + $5 hobby tier для веба, или бесплатно с лимитами.

---

## 🔐 Безопасность

### Zero-knowledge шифрование API-ключей
- Пароль юзера → Argon2id (с уникальной солью, OWASP 2024 params: time=2, mem=19MB) → encryption_key (32 байта)
- API-ключи биржи шифруются Fernet (AES-128-CBC + HMAC-SHA256) перед сохранением в БД
- На сервере в открытом виде ключи НЕ хранятся
- Даже админ не может расшифровать чужие ключи — этого нельзя сделать без пароля юзера
- При смене пароля старый `kdf_salt` пересоздаётся, зашифрованные ключи становятся недоступны (и автоматически очищаются)

### Изоляция данных (multi-tenant)
- Все таблицы имеют колонку `user_id` с FK CASCADE
- `_current_user_id()` бросает RuntimeError если user_id не задан — невозможно "забыть"
- Каждый запрос обязательно фильтруется по `user_id`

### Защита от атак
- **CSRF**: Origin/Referer + same-origin check + ProxyFix для Railway
- **Rate-limit**:
  - `/login`: 5 попыток / 15 мин / IP
  - `/register`: 3 / час / IP
  - `/api/sync`: 1 / 30 сек
  - Resend verification: 1 / 60 сек / юзер
- **Strong password**: 8+ символов, обязательно буква+цифра
- **Secure cookies**: HttpOnly + SameSite=Lax + Secure (в PROD)
- **Security headers**: HSTS, CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy, Permissions-Policy
- **Audit log** изменений в settings/goals/trades, action всех админ-действий
- **Логи** с rotation в `logs/app.log`, API-ключи маскируются в логах
- **Email verification** обязательна перед первым логином (для новых юзеров после 2026-05-30)
- **Глобальный errorhandler** — traceback не утекает даже при необработанном Exception

См. [SECURITY.md](SECURITY.md) для деталей и контакта для report'ов.

---

## 📁 Структура

```
TradeRunner/
├── app.py                       # Flask + endpoints (~2700 строк)
├── auth.py                      # Blueprint регистрации/логина/verify/reset
├── admin_views.py               # Admin Panel blueprint
├── email_service.py             # Resend API клиент + шаблоны писем
├── token_service.py             # itsdangerous токены для verify/reset
├── models.py                    # SQLAlchemy ORM модели
├── database.py                  # Legacy sqlite функции (per-user)
├── crypto_keys.py               # Zero-knowledge шифрование
├── bitunix_client.py            # API клиент Bitunix
├── migrate_to_v4.py             # Миграция v3.2 → v4.0 (для старых юзеров)
├── templates/
│   ├── index.html               # Главный дашборд
│   ├── auth_layout.html         # Базовый шаблон auth
│   ├── auth_login.html
│   ├── auth_register.html
│   ├── auth_email_sent.html     # «Проверь почту»
│   ├── auth_forgot.html         # Forgot password form
│   ├── auth_reset.html          # Reset password form
│   ├── admin_layout.html        # Базовый шаблон админки
│   ├── admin_dashboard.html
│   ├── admin_users.html
│   ├── admin_user_detail.html
│   ├── admin_audit.html
│   └── admin_share_links.html
├── static/
│   ├── app.js
│   └── style.css
├── tests/                       # pytest
├── requirements.txt
├── Procfile                     # Для Railway/Render
├── runtime.txt                  # python-3.12.4
├── .env.example                 # Шаблон env переменных
├── .gitignore
├── setup.bat/sh                 # Локальная установка venv
├── run.bat/sh                   # Локальный запуск
└── ЗАПУСТИ_МЕНЯ_TradeRunner.bat # Полный цикл (Windows)
```

---

## 🛣 Roadmap

**v4.2 (планируется):**
- 2FA (TOTP) через `pyotp` + QR
- Telegram-уведомления о логине с нового IP
- Webhook URL alerts при достижении цели
- Auto-backup БД на S3/B2
- Sentry для error tracking

**v4.3+:**
- Multi-exchange: Binance, Bybit, OKX, Bitget
- Telegram-бот для алертов
- Tiered subscriptions (free + paid)
- GDPR delete-my-data endpoint

См. [CHANGELOG.md](CHANGELOG.md) для полной истории изменений.

---

## 🆘 Что-то не работает?

1. **Не приходит verification письмо** — проверь спам. Если `RESEND_API_KEY` не задан в Railway env vars — письмо ушло в логи (Deployments → View logs). Резен → API Keys → проверь активен.
2. **Не могу войти после смены пароля** — введи API-ключи биржи заново (zero-knowledge: старые расшифровываются только старым паролем).
3. **«Войди чтобы продолжить»** — кука сессии истекла. Жми Login.
4. **Запустил локально, но `RESEND_API_KEY` не задан** — verification ссылка покажется через flash прямо на странице.

---

**Автор:** Артём ([@cardsoff](https://github.com/Cardsoff))
**Версия:** v4.1 · 2026-05-30
**Лицензия:** [AGPL-3.0](LICENSE)
**Брендинг:** TradeRunner · «Беги к своей цели. Считай каждый трейд»
