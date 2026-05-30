"""
TradeRunner — Admin Panel.

Доступ только для is_admin=True.
Все эндпоинты только-чтение или безопасные действия (block, make-admin, resend-verify).
НИКОГДА не расшифровывает чужие API-ключи — zero-knowledge сохраняется.
"""
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Blueprint, request, render_template, redirect, url_for,
    flash, abort, jsonify, current_app,
)
from flask_login import current_user, login_required
from sqlalchemy import func, text as sql_text

from models import db, User, Trade, Deposit, Goal, AuditLog, ShareLink

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    """Декоратор: требует is_admin=True у current_user."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return f(*args, **kwargs)
    return decorated


# === Главная админки ===

@admin_bp.route("/")
@admin_required
def dashboard():
    """Сводная панель: метрики + 2 графика."""
    now = datetime.utcnow()
    day_ago    = now - timedelta(days=1)
    week_ago   = now - timedelta(days=7)
    month_ago  = now - timedelta(days=30)

    total_users    = db.session.query(func.count(User.id)).scalar() or 0
    new_today      = db.session.query(func.count(User.id)).filter(User.created_at >= day_ago).scalar() or 0
    new_week       = db.session.query(func.count(User.id)).filter(User.created_at >= week_ago).scalar() or 0
    new_month      = db.session.query(func.count(User.id)).filter(User.created_at >= month_ago).scalar() or 0
    verified_users = db.session.query(func.count(User.id)).filter(User.email_verified == True).scalar() or 0
    blocked_users  = db.session.query(func.count(User.id)).filter(User.is_blocked == True).scalar() or 0
    active_week    = db.session.query(func.count(User.id)).filter(User.last_login_at >= week_ago).scalar() or 0

    total_trades   = db.session.query(func.count(Trade.id)).scalar() or 0
    total_deposits = db.session.query(func.count(Deposit.id)).scalar() or 0
    active_goals   = db.session.query(func.count(Goal.id)).filter(Goal.is_active == 1).scalar() or 0

    # Юзеры с подключенной биржей (есть зашифрованный api_key в user_settings)
    try:
        with db.engine.connect() as conn:
            row = conn.execute(sql_text(
                "SELECT COUNT(DISTINCT user_id) FROM user_settings "
                "WHERE key='bitunix_api_key' AND value != ''"
            )).fetchone()
            connected_users = int(row[0]) if row else 0
    except Exception:
        connected_users = 0

    # Активные share-ссылки (не отозванные, не истёкшие)
    active_share_links = db.session.query(func.count(ShareLink.id)).filter(
        ShareLink.revoked == False,
        ShareLink.expires_at > now,
    ).scalar() or 0

    # График: новые регистрации по дням за последние 30 дней
    signup_daily = []
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        n = db.session.query(func.count(User.id)).filter(
            User.created_at >= day_start, User.created_at < day_end
        ).scalar() or 0
        signup_daily.append({"date": day.isoformat(), "n": n})

    # График: DAU (daily active users — кто заходил/обновлял в этот день)
    dau_daily = []
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        n = db.session.query(func.count(User.id)).filter(
            User.last_login_at >= day_start, User.last_login_at < day_end
        ).scalar() or 0
        dau_daily.append({"date": day.isoformat(), "n": n})

    metrics = {
        "total_users": total_users,
        "verified_users": verified_users,
        "blocked_users": blocked_users,
        "new_today": new_today,
        "new_week": new_week,
        "new_month": new_month,
        "active_week": active_week,
        "connected_users": connected_users,
        "total_trades": total_trades,
        "total_deposits": total_deposits,
        "active_goals": active_goals,
        "active_share_links": active_share_links,
    }
    return render_template(
        "admin_dashboard.html",
        metrics=metrics,
        signup_daily=signup_daily,
        dau_daily=dau_daily,
    )


# === Список юзеров ===

@admin_bp.route("/users")
@admin_required
def users_list():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    search = (request.args.get("q") or "").strip().lower()
    sort = request.args.get("sort", "new")  # new / old / active / inactive

    q = User.query
    if search:
        q = q.filter(User.email.ilike(f"%{search}%"))

    if sort == "new":
        q = q.order_by(User.created_at.desc())
    elif sort == "old":
        q = q.order_by(User.created_at.asc())
    elif sort == "active":
        q = q.order_by(User.last_login_at.desc().nullslast())
    elif sort == "inactive":
        q = q.order_by(User.last_login_at.asc().nullsfirst())

    total = q.count()
    users = q.offset((page - 1) * per_page).limit(per_page).all()

    # Подсчёт количества сделок per user (одним запросом)
    trade_counts = dict(
        db.session.query(Trade.user_id, func.count(Trade.id)).group_by(Trade.user_id).all()
    )

    rows = []
    for u in users:
        rows.append({
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name or "",
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "—",
            "last_login_at": u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "—",
            "email_verified": u.email_verified,
            "is_admin": u.is_admin,
            "is_blocked": getattr(u, "is_blocked", False),
            "n_trades": trade_counts.get(u.id, 0),
        })

    pages = (total + per_page - 1) // per_page
    return render_template(
        "admin_users.html",
        users=rows,
        total=total,
        page=page,
        pages=pages,
        search=search,
        sort=sort,
    )


# === Карточка одного юзера ===

@admin_bp.route("/users/<int:uid>")
@admin_required
def user_detail(uid):
    u = db.session.get(User, uid)
    if not u:
        abort(404)
    n_trades   = db.session.query(func.count(Trade.id)).filter(Trade.user_id == uid).scalar() or 0
    n_deposits = db.session.query(func.count(Deposit.id)).filter(Deposit.user_id == uid).scalar() or 0
    n_goals    = db.session.query(func.count(Goal.id)).filter(Goal.user_id == uid).scalar() or 0
    n_audit    = db.session.query(func.count(AuditLog.id)).filter(AuditLog.user_id == uid).scalar() or 0
    n_share    = db.session.query(func.count(ShareLink.id)).filter(ShareLink.user_id == uid).scalar() or 0
    # Подключен ли биржевой API
    try:
        with db.engine.connect() as conn:
            row = conn.execute(sql_text(
                "SELECT value FROM user_settings WHERE user_id=:uid AND key='bitunix_api_key'"
            ), {"uid": uid}).fetchone()
            api_connected = bool(row and row[0])
    except Exception:
        api_connected = False

    last_audits = AuditLog.query.filter_by(user_id=uid).order_by(AuditLog.ts.desc()).limit(20).all()

    user_data = {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name or "",
        "created_at": u.created_at.strftime("%Y-%m-%d %H:%M UTC") if u.created_at else "—",
        "last_login_at": u.last_login_at.strftime("%Y-%m-%d %H:%M UTC") if u.last_login_at else "—",
        "email_verified": u.email_verified,
        "is_admin": u.is_admin,
        "is_blocked": getattr(u, "is_blocked", False),
        "n_trades": n_trades,
        "n_deposits": n_deposits,
        "n_goals": n_goals,
        "n_audit": n_audit,
        "n_share": n_share,
        "api_connected": api_connected,
    }
    return render_template("admin_user_detail.html", user=user_data, audits=last_audits)


# === Действия с юзером ===

@admin_bp.route("/users/<int:uid>/action", methods=["POST"])
@admin_required
def user_action(uid):
    u = db.session.get(User, uid)
    if not u:
        abort(404)

    action = (request.form.get("action") or "").strip()

    # Защита: нельзя заблокировать или разжаловать самого себя
    if uid == current_user.id and action in ("block", "demote"):
        flash("Нельзя выполнить это действие над собой.", "error")
        return redirect(url_for("admin.user_detail", uid=uid))

    if action == "block":
        u.is_blocked = True
        flash(f"Юзер {u.email} заблокирован.", "success")
    elif action == "unblock":
        u.is_blocked = False
        flash(f"Юзер {u.email} разблокирован.", "success")
    elif action == "make_admin":
        u.is_admin = True
        flash(f"Юзер {u.email} получил права админа.", "success")
    elif action == "demote":
        u.is_admin = False
        flash(f"Юзер {u.email} разжалован.", "success")
    elif action == "verify_email":
        u.email_verified = True
        flash(f"Email {u.email} помечен как verified.", "success")
    elif action == "resend_verification":
        try:
            import auth as auth_module
            auth_module._send_verification(u)
            flash(f"Verification email повторно отправлен на {u.email}.", "success")
        except Exception as e:
            flash(f"Ошибка отправки: {e}", "error")
    else:
        flash(f"Неизвестное действие: {action}", "error")

    db.session.commit()
    # Аудит
    try:
        log = AuditLog(
            user_id=current_user.id,  # кто совершил действие (админ)
            ts=datetime.utcnow().isoformat(),
            action=f"admin:{action}",
            entity="user",
            entity_id=str(uid),
            payload=f"target_email={u.email}",
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass

    return redirect(url_for("admin.user_detail", uid=uid))


# === Audit log ===

@admin_bp.route("/audit")
@admin_required
def audit_log():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 100
    user_filter = (request.args.get("user_id") or "").strip()
    action_filter = (request.args.get("action") or "").strip()

    q = AuditLog.query
    if user_filter:
        try:
            q = q.filter(AuditLog.user_id == int(user_filter))
        except ValueError:
            pass
    if action_filter:
        q = q.filter(AuditLog.action.ilike(f"%{action_filter}%"))

    q = q.order_by(AuditLog.ts.desc())
    total = q.count()
    audits = q.offset((page - 1) * per_page).limit(per_page).all()

    # Map user_id → email для отображения
    user_ids = list({a.user_id for a in audits})
    users = {u.id: u.email for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    pages = (total + per_page - 1) // per_page
    return render_template(
        "admin_audit.html",
        audits=audits,
        users=users,
        total=total,
        page=page,
        pages=pages,
        user_filter=user_filter,
        action_filter=action_filter,
    )


# === Share links ===

@admin_bp.route("/share-links")
@admin_required
def share_links_list():
    now = datetime.utcnow()
    q = ShareLink.query.order_by(ShareLink.created_at.desc()).limit(200)
    links = q.all()
    # Map user_id → email
    user_ids = list({l.user_id for l in links})
    users = {u.id: u.email for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    rows = []
    for l in links:
        status = "active"
        if l.revoked:
            status = "revoked"
        elif l.expires_at < now:
            status = "expired"
        rows.append({
            "id": l.id,
            "user_id": l.user_id,
            "user_email": users.get(l.user_id, "—"),
            "token": l.token[:10] + "...",
            "created_at": l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else "—",
            "expires_at": l.expires_at.strftime("%Y-%m-%d %H:%M") if l.expires_at else "—",
            "status": status,
        })
    return render_template("admin_share_links.html", links=rows, total=len(rows))
