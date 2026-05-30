"""
TradeRunner — Email service через Resend API.

В DEV режиме (без RESEND_API_KEY) — логгирует письма в консоль вместо отправки.
В PROD режиме — отправляет через Resend HTTP API (resend.com).

Бесплатный план Resend: 100 писем/день, 3000/месяц.
"""
import os
import json
import logging
import requests  # надёжнее urllib (urllib попадает в Cloudflare bot-block)

log = logging.getLogger("email_service")

DEFAULT_FROM = "TradeRunner <onboarding@resend.dev>"
RESEND_API_URL = "https://api.resend.com/emails"


def is_configured() -> bool:
    """True если RESEND_API_KEY задан."""
    return bool(os.environ.get("RESEND_API_KEY", "").strip())


def send_email(to: str, subject: str, html_body: str, text_body: str = None, from_addr: str = None) -> dict:
    """
    Отправляет email через Resend HTTP API.

    Возвращает {"ok": True, "id": "..."} при успехе,
    {"ok": False, "error": "..."} при ошибке,
    {"ok": True, "dev_mode": True} если API_KEY не задан (письмо ушло в лог).
    """
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender  = (from_addr or os.environ.get("MAIL_FROM") or DEFAULT_FROM).strip()

    if not api_key:
        log.warning("=" * 60)
        log.warning("EMAIL (DEV-mode, RESEND_API_KEY не задан, письмо НЕ отправлено):")
        log.warning(f"  To:      {to}")
        log.warning(f"  From:    {sender}")
        log.warning(f"  Subject: {subject}")
        log.warning(f"  Body (text): {text_body or '(only html)'}")
        log.warning(f"  Body (html): {html_body[:300]}{'...' if len(html_body) > 300 else ''}")
        log.warning("=" * 60)
        return {"ok": True, "dev_mode": True, "to": to}

    payload = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # User-Agent чтобы Cloudflare не воспринимал нас как бота
        "User-Agent": "TradeRunner/4.1 (+https://github.com/Cardsoff/traderunner)",
        "Accept": "application/json",
    }
    try:
        resp = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            try:
                data = resp.json()
            except Exception:
                data = {}
            log.info("Resend OK: to=%s id=%s subject=%r", to, data.get("id", "?"), subject)
            return {"ok": True, "id": data.get("id"), "to": to}
        else:
            body = resp.text[:300] if resp.text else ""
            log.error("Resend HTTP %s: %s", resp.status_code, body)
            return {"ok": False, "error": f"HTTP {resp.status_code}: {body}", "to": to}
    except Exception as e:
        log.exception("Resend send failed: %s", e)
        return {"ok": False, "error": str(e), "to": to}


# === Шаблоны писем ===

def _wrap(content: str) -> str:
    return f"""<!DOCTYPE html>
<html><body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;
                    background: #f6f8fa; padding: 32px 16px; color: #0a0e14; line-height: 1.55;">
  <div style="max-width: 560px; margin: 0 auto; background: #fff; border-radius: 12px;
              padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,.06);">
    <div style="font-size: 22px; font-weight: 700; color: #10c98a; margin-bottom: 8px;">TradeRunner</div>
    <div style="font-size: 13px; color: #6e7681; margin-bottom: 24px;">Беги к своей цели. Считай каждый трейд.</div>
    {content}
    <hr style="border: none; border-top: 1px solid #e1e4e8; margin: 32px 0 16px;">
    <div style="font-size: 12px; color: #6e7681;">
      Если ты не запрашивал это письмо — просто проигнорируй его. Никто не получит доступ к твоему аккаунту, пока ты не подтвердишь email.
    </div>
  </div>
</body></html>"""


def render_verify_email(name: str, verify_url: str):
    subject = "Подтверди свой email в TradeRunner"
    html = _wrap(f"""
    <h2 style="margin-top: 0;">Привет, {name}!</h2>
    <p>Спасибо за регистрацию в TradeRunner. Подтверди свой email — нажми на кнопку ниже:</p>
    <p style="text-align: center; margin: 28px 0;">
      <a href="{verify_url}" style="display: inline-block; background: #10c98a; color: #fff;
                                    text-decoration: none; padding: 12px 32px; border-radius: 8px;
                                    font-weight: 600;">Подтвердить email</a>
    </p>
    <p style="font-size: 13px; color: #6e7681;">
      Или скопируй ссылку в браузер:<br>
      <code style="word-break: break-all;">{verify_url}</code>
    </p>
    <p style="font-size: 13px; color: #6e7681;">Ссылка действует 24 часа.</p>
    """)
    text = f"Привет, {name}!\n\nПодтверди email в TradeRunner, перейдя по ссылке:\n{verify_url}\n\nСсылка действует 24 часа."
    return subject, html, text


def render_reset_password_email(name: str, reset_url: str):
    subject = "Восстановление пароля TradeRunner"
    html = _wrap(f"""
    <h2 style="margin-top: 0;">Привет, {name}!</h2>
    <p>Кто-то (надеемся, ты) запросил восстановление пароля для аккаунта TradeRunner.</p>
    <p style="text-align: center; margin: 28px 0;">
      <a href="{reset_url}" style="display: inline-block; background: #7c5cff; color: #fff;
                                   text-decoration: none; padding: 12px 32px; border-radius: 8px;
                                   font-weight: 600;">Восстановить пароль</a>
    </p>
    <p style="font-size: 13px; color: #6e7681;">
      Или скопируй ссылку:<br><code style="word-break: break-all;">{reset_url}</code>
    </p>
    <p style="font-size: 13px; color: #ff5a6c;">
      <b>ВАЖНО:</b> после смены пароля твои сохранённые API-ключи биржи станут недоступны
      (они зашифрованы старым паролем — это zero-knowledge защита).
      Тебе нужно будет ввести их заново через интерфейс. Сделки и история останутся.
    </p>
    <p style="font-size: 13px; color: #6e7681;">Ссылка действует 1 час. Если ты не запрашивал — игнорируй письмо.</p>
    """)
    text = f"Привет, {name}!\n\nВосстановление пароля TradeRunner:\n{reset_url}\n\nСсылка действует 1 час."
    return subject, html, text
