"""
TradeRunner — одноразовые токены для email verification и password reset.

Используется itsdangerous TimedSerializer (HMAC + timestamp).
Ключ — Flask SECRET_KEY (тот же что для session). При его смене все токены инвалидируются.
"""
import logging
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

log = logging.getLogger("token_service")

# Salt'ы разделяют namespace токенов — токен email-verify не сработает для password-reset.
SALT_EMAIL_VERIFY    = "email-verify-v1"
SALT_PASSWORD_RESET  = "password-reset-v1"

# TTL по умолчанию
TTL_EMAIL_VERIFY     = 24 * 3600      # 24 часа
TTL_PASSWORD_RESET   =  1 * 3600      # 1 час


def _serializer(secret_key: str, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=salt)


def generate_email_verify_token(secret_key: str, user_id: int) -> str:
    """Создаёт токен email-verification для указанного user_id."""
    return _serializer(secret_key, SALT_EMAIL_VERIFY).dumps({"uid": int(user_id)})


def verify_email_verify_token(secret_key: str, token: str) -> int | None:
    """
    Расшифровывает email-verification токен. Возвращает user_id или None если невалиден/просрочен.
    """
    try:
        data = _serializer(secret_key, SALT_EMAIL_VERIFY).loads(token, max_age=TTL_EMAIL_VERIFY)
        return int(data["uid"])
    except SignatureExpired:
        log.info("email-verify token expired")
        return None
    except BadSignature:
        log.info("email-verify token invalid signature")
        return None
    except Exception as e:
        log.warning("email-verify token failed: %s", e)
        return None


def generate_password_reset_token(secret_key: str, user_id: int) -> str:
    return _serializer(secret_key, SALT_PASSWORD_RESET).dumps({"uid": int(user_id)})


def verify_password_reset_token(secret_key: str, token: str) -> int | None:
    try:
        data = _serializer(secret_key, SALT_PASSWORD_RESET).loads(token, max_age=TTL_PASSWORD_RESET)
        return int(data["uid"])
    except SignatureExpired:
        log.info("password-reset token expired")
        return None
    except BadSignature:
        log.info("password-reset token invalid signature")
        return None
    except Exception as e:
        log.warning("password-reset token failed: %s", e)
        return None
