"""
TradeRunner — Auth blueprint.

Включает: регистрацию, логин, logout, email verification, password reset.
"""
import os
from datetime import datetime, timedelta
from flask import (
    Blueprint, request, render_template, redirect, url_for,
    flash, session, current_app, abort,
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from email_validator import validate_email, EmailNotValidError

from models import db, User
from crypto_keys import (
    generate_salt, derive_encryption_key,
    session_set_key, session_clear_key,
)
import email_service
import token_service

auth_bp = Blueprint("auth", __name__)

# Rate-limit регистрации: 3 регистрации с одного IP за час
_REGISTER_ATTEMPTS = {}   # ip → [(timestamp, ...), ...]
_REGISTER_WINDOW   = 3600 # 1 час
_REGISTER_LIMIT    = 3
# Rate-limit повторной отправки verification: 1 раз в 60 сек
_RESEND_COOLDOWN_SEC = 60


def _is_strong_password(password: str):
    if len(password) < 8:
        return False, "Пароль должен быть минимум 8 символов"
    if not any(c.isdigit() for c in password):
        return False, "Пароль должен содержать хотя бы одну цифру"
    if not any(c.isalpha() for c in password):
        return False, "Пароль должен содержать хотя бы одну букву"
    return True, ""


def _check_register_rate(ip):
    """True если можно регистрироваться, False если лимит превышен."""
    import time as _t
    now = _t.time()
    attempts = [t for t in _REGISTER_ATTEMPTS.get(ip, []) if now - t < _REGISTER_WINDOW]
    _REGISTER_ATTEMPTS[ip] = attempts
    return len(attempts) < _REGISTER_LIMIT


def _record_register_attempt(ip):
    import time as _t
    _REGISTER_ATTEMPTS.setdefault(ip, []).append(_t.time())


def _send_verification(user):
    """Отправить (или повторно отправить) verification email."""
    secret = current_app.config["SECRET_KEY"]
    token = token_service.generate_email_verify_token(secret, user.id)
    verify_url = url_for("auth.verify_email", token=token, _external=True)
    subject, html, text = email_service.render_verify_email(user.display_name or user.email, verify_url)
    result = email_service.send_email(user.email, subject, html, text)
    user.email_verification_sent_at = datetime.utcnow()
    db.session.commit()
    return result


# === Регистрация ===

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        ip = request.remote_addr or "unknown"

        if not _check_register_rate(ip):
            flash("Слишком много регистраций с этого IP. Попробуй через час.", "error")
            return render_template("auth_register.html")

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        name = (request.form.get("name") or "").strip()

        try:
            v = validate_email(email, check_deliverability=False)
            email = v.normalized
        except EmailNotValidError as e:
            flash(f"Невалидный email: {e}", "error")
            return render_template("auth_register.html", email=email, name=name)

        ok, msg = _is_strong_password(password)
        if not ok:
            flash(msg, "error")
            return render_template("auth_register.html", email=email, name=name)

        if password != password2:
            flash("Пароли не совпадают", "error")
            return render_template("auth_register.html", email=email, name=name)

        if User.query.filter_by(email=email).first():
            flash("Этот email уже зарегистрирован", "error")
            return render_template("auth_register.html", email=email, name=name)

        _record_register_attempt(ip)

        salt = generate_salt()
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            kdf_salt=salt,
            display_name=name or email.split("@")[0],
            created_at=datetime.utcnow(),
            last_login_at=None,
            email_verified=False,
        )
        db.session.add(user)
        db.session.flush()
        new_user_id = user.id
        db.session.commit()
        db.session.refresh(user)

        # Дефолтные данные для нового юзера
        try:
            import database as legacy_db
            from datetime import datetime as _dt
            with legacy_db.get_conn() as _conn:
                _conn.execute(
                    "INSERT INTO goals (name, amount, monthly_return_pct, monthly_deposit, created_at, is_active, user_id) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?)",
                    ("Первая цель", 10000, 10, 0, _dt.utcnow().strftime("%Y-%m-%d"), new_user_id)
                )
                for s in ['breakout', 'trend', 'scalp', 'swing', 'news']:
                    _conn.execute(
                        "INSERT OR IGNORE INTO setups (user_id, name) VALUES (?, ?)",
                        (new_user_id, s)
                    )
            print(f"[register] Defaults created for user {new_user_id}", flush=True)
        except Exception as _e:
            import traceback, sys
            print(f"[register] Ошибка дефолтов user {new_user_id}: {_e}", file=sys.stderr)
            traceback.print_exc()

        # Отправляем verification email
        result = _send_verification(user)
        if email_service.is_configured():
            flash(f"Письмо с подтверждением отправлено на {email}. Проверь почту (и спам).", "success")
        else:
            secret = current_app.config["SECRET_KEY"]
            token = token_service.generate_email_verify_token(secret, user.id)
            verify_url = url_for("auth.verify_email", token=token, _external=True)
            flash(
                f"⚠ DEV-mode: email-сервис не настроен. Перейди по ссылке вручную: {verify_url}",
                "info"
            )

        return redirect(url_for("auth.email_sent", email=email))

    return render_template("auth_register.html")


@auth_bp.route("/auth/email-sent")
def email_sent():
    email = request.args.get("email", "")
    return render_template("auth_email_sent.html", email=email)


@auth_bp.route("/auth/verify-email/<token>")
def verify_email(token):
    secret = current_app.config["SECRET_KEY"]
    uid = token_service.verify_email_verify_token(secret, token)
    if uid is None:
        flash("Ссылка подтверждения невалидна или просрочена. Запроси новую.", "error")
        return redirect(url_for("auth.login"))

    user = db.session.get(User, uid)
    if not user:
        flash("Пользователь не найден.", "error")
        return redirect(url_for("auth.login"))

    if not user.email_verified:
        user.email_verified = True
        db.session.commit()
        flash("Email подтверждён! Войди с паролем.", "success")
    else:
        flash("Email уже был подтверждён ранее. Просто войди.", "info")

    return redirect(url_for("auth.login"))


@auth_bp.route("/auth/resend-verification", methods=["POST"])
def resend_verification():
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        flash("Введи email.", "error")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Если такой email зарегистрирован — письмо отправлено.", "info")
        return redirect(url_for("auth.email_sent", email=email))

    if user.email_verified:
        flash("Email уже подтверждён. Войди обычным образом.", "info")
        return redirect(url_for("auth.login"))

    if user.email_verification_sent_at:
        elapsed = (datetime.utcnow() - user.email_verification_sent_at).total_seconds()
        if elapsed < _RESEND_COOLDOWN_SEC:
            wait = int(_RESEND_COOLDOWN_SEC - elapsed)
            flash(f"Подожди ещё {wait} сек перед повторной отправкой.", "error")
            return redirect(url_for("auth.email_sent", email=email))

    _send_verification(user)
    flash(f"Письмо отправлено повторно на {email}.", "success")
    return redirect(url_for("auth.email_sent", email=email))


# === Логин ===

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Неверный email или пароль", "error")
            return render_template("auth_login.html", email=email)

        if getattr(user, "is_blocked", False):
            flash("Этот аккаунт заблокирован. Свяжись с поддержкой.", "error")
            return render_template("auth_login.html", email=email)

        if not getattr(user, "email_verified", True):
            flash(
                f"Email {email} не подтверждён. Проверь почту или отправь заново через страницу регистрации.",
                "error"
            )
            return render_template("auth_login.html", email=email)

        ek = derive_encryption_key(password, user.kdf_salt)
        session_set_key(session, ek)

        user.last_login_at = datetime.utcnow()
        db.session.commit()

        login_user(user, remember=remember)
        flash(f"С возвращением, {user.display_name}!", "success")

        next_url = request.args.get("next") or url_for("index")
        return redirect(next_url)

    return render_template("auth_login.html")


# === Logout ===

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Разлогинивает пользователя. Только POST — защита от CSRF."""
    session_clear_key(session)
    logout_user()
    flash("Вы вышли из аккаунта.", "info")
    return redirect(url_for("auth.login"))


# === Password reset (forgot password flow) ===

@auth_bp.route("/auth/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email).first()

        if user and user.email_verified:
            secret = current_app.config["SECRET_KEY"]
            token = token_service.generate_password_reset_token(secret, user.id)
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            subject, html, text = email_service.render_reset_password_email(
                user.display_name or user.email, reset_url
            )
            email_service.send_email(user.email, subject, html, text)
            if not email_service.is_configured():
                flash(f"⚠ DEV-mode: перейди по ссылке вручную: {reset_url}", "info")

        flash(
            "Если этот email зарегистрирован — мы отправили ссылку для восстановления. Проверь почту (и спам).",
            "info"
        )
        return redirect(url_for("auth.login"))

    return render_template("auth_forgot.html")


@auth_bp.route("/auth/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    secret = current_app.config["SECRET_KEY"]
    uid = token_service.verify_password_reset_token(secret, token)
    if uid is None:
        flash("Ссылка восстановления невалидна или просрочена. Запроси новую.", "error")
        return redirect(url_for("auth.forgot_password"))

    user = db.session.get(User, uid)
    if not user:
        flash("Пользователь не найден.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""

        ok, msg = _is_strong_password(password)
        if not ok:
            flash(msg, "error")
            return render_template("auth_reset.html", token=token)

        if password != password2:
            flash("Пароли не совпадают", "error")
            return render_template("auth_reset.html", token=token)

        user.password_hash = generate_password_hash(password)
        user.kdf_salt = generate_salt()
        try:
            import database as legacy_db
            with legacy_db.get_conn() as _conn:
                _conn.execute(
                    "UPDATE user_settings SET value='' "
                    "WHERE user_id=? AND key IN ('bitunix_api_key', 'bitunix_api_secret')",
                    (user.id,)
                )
        except Exception as _e:
            print(f"[reset_password] Ошибка очистки API-ключей user {user.id}: {_e}", flush=True)

        db.session.commit()
        flash(
            "Пароль изменён. ⚠ Сохранённые API-ключи биржи очищены (zero-knowledge защита). "
            "После входа введи их заново через настройки.",
            "success"
        )
        return redirect(url_for("auth.login"))

    return render_template("auth_reset.html", token=token)
