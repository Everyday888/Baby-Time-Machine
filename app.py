import os
import random
import smtplib
import string
import uuid
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from io import BytesIO
from urllib.parse import quote as _url_quote
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

try:
    import requests as _http_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

import database as core_db
import services_admin as admin_service
import services_auth as auth_service
import services_family as family_service


load_dotenv()

ALLOWED_ROLES = {"admin", "father", "mother", "grandpa", "grandma", "grandpa_maternal", "grandma_maternal", "guardian"}
ALLOWED_VACCINE_STATUSES = {"pending", "booked", "done"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

WECHAT_APPID = os.getenv("WECHAT_APPID", "").strip()
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "").strip()


def is_wechat_browser() -> bool:
    return "MicroMessenger" in request.headers.get("User-Agent", "")


def get_client_ip() -> str:
    """Return the real client IP, trusting X-Real-IP set by a trusted reverse proxy."""
    real_ip = request.headers.get("X-Real-IP", "").strip()
    return real_ip if real_ip else (request.remote_addr or "unknown")


def is_ajax() -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def ajax_redirect(success: bool, message: str):
    """Return JSON for AJAX requests, redirect otherwise."""
    if is_ajax():
        return jsonify({"ok": success, "message": message})
    if success:
        flash(message, "success")
    else:
        flash(message, "error")
    return redirect(url_for("dashboard"))


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=15)
    app.config["UPLOAD_IMAGE_DIR"] = os.path.join(app.root_path, "images")
    app.config["PUBLIC_BASE_URL"] = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

    @app.before_request
    def wechat_silent_oauth():
        """Silently obtain WeChat OpenID for users inside WeChat browser."""
        if not (WECHAT_APPID and WECHAT_SECRET and HAS_REQUESTS):
            return
        if not is_wechat_browser():
            return
        if session.get("wechat_openid"):
            return
        if session.get("wechat_oauth_attempted"):
            return
        skip_endpoints = {
            "wechat_oauth_start", "wechat_oauth_callback",
            "static", "node_modules", "manifest", "uploaded_image",
        }
        if not request.endpoint or request.endpoint in skip_endpoints:
            return
        session["wechat_oauth_attempted"] = True
        session["wechat_pre_path"] = request.path
        return redirect(url_for("wechat_oauth_start"))

    @app.before_request
    def load_user():
        user_id = session.get("user_id")
        if not user_id:
            g.user = None
            return

        now = datetime.utcnow()
        last_seen_raw = session.get("last_seen_at")
        if last_seen_raw:
            try:
                last_seen = datetime.fromisoformat(last_seen_raw)
            except ValueError:
                last_seen = None
            if last_seen and now - last_seen > timedelta(minutes=15):
                session.clear()
                flash("登录已过期，请重新登录。", "error")
                return redirect(url_for("login", next=get_current_relative_url()))

        endpoint = request.endpoint or ""
        if endpoint not in {"static", "manifest", "node_modules", "uploaded_image"}:
            session["last_seen_at"] = now.isoformat()
            session.modified = True

        user = auth_service.get_active_user_by_id(user_id)
        g.user = user
        if user is None:
            session.clear()

    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "today": date.today(),
            "role_labels": {
                "admin": "管理员",
                "father": "爸爸",
                "mother": "妈妈",
                "grandpa": "爷爷",
                "grandma": "奶奶",
                "grandpa_maternal": "外公",
                "grandma_maternal": "外婆",
                "guardian": "看护人",
            },
            "event_type_labels": {
                "feeding": "喂养",
                "sleep": "睡眠",
                "diaper": "排便/尿布",
                "health": "健康",
                "milestone": "里程碑",
            },
            "vaccine_status_labels": {
                "pending": "待接种",
                "soon": "即将到期",
                "booked": "已预约",
                "overdue": "已逾期",
                "done": "已完成",
            },
        }

    @app.template_filter("age_text")
    def age_text(birthday: date) -> str:
        days = (date.today() - birthday).days
        months = days // 30
        if months < 1:
            return f"{days} 天"
        years = months // 12
        if years < 1:
            return f"{months} 个月"
        return f"{years} 岁 {months % 12} 个月"

    @app.route("/")
    def index():
        if g.user:
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.route("/manifest.json")
    def manifest():
        """提供 PWA manifest 文件"""
        manifest_path = os.path.join(app.root_path, "manifest.json")
        return send_from_directory(os.path.dirname(manifest_path), "manifest.json")

    @app.route("/node_modules/<path:filename>")
    def node_modules(filename: str):
        node_modules_dir = os.path.join(app.root_path, "node_modules")
        return send_from_directory(node_modules_dir, filename)

    @app.route("/images/<path:filename>")
    def uploaded_image(filename: str):
        return send_from_directory(app.config["UPLOAD_IMAGE_DIR"], filename)

    @app.route("/terms")
    def terms():
        return render_template("terms.html")

    @app.route("/privacy")
    def privacy():
        return render_template("privacy.html")

    @app.route("/join")
    def join_by_invite_code():
        code = request.args.get("code", "").strip().upper()
        if not code:
            flash("邀请码无效，请联系家庭成员重新分享。", "error")
            return redirect(url_for("register"))
        return redirect(url_for("register", family_mode="join", invite_code=code))

    # ------------------------------------------------------------------
    # WeChat Official Account OAuth routes
    # ------------------------------------------------------------------

    @app.route("/wechat/oauth")
    def wechat_oauth_start():
        """Redirect user to WeChat silent-authorization page (snsapi_base)."""
        if not (WECHAT_APPID and WECHAT_SECRET and HAS_REQUESTS):
            return redirect(url_for("index"))
        callback_uri = url_for("wechat_oauth_callback", _external=True)
        oauth_url = (
            "https://open.weixin.qq.com/connect/oauth2/authorize"
            f"?appid={WECHAT_APPID}"
            f"&redirect_uri={_url_quote(callback_uri, safe='')}"
            "&response_type=code"
            "&scope=snsapi_base"
            "&state=wbtm"
            "#wechat_redirect"
        )
        return redirect(oauth_url)

    @app.route("/wechat/callback")
    def wechat_oauth_callback():
        """Exchange code for OpenID, optionally auto-login if already bound."""
        code = request.args.get("code", "")
        return_path = session.pop("wechat_pre_path", None) or "/"
        if not get_safe_next_url(return_path):
            return_path = "/"

        if code and WECHAT_APPID and WECHAT_SECRET and HAS_REQUESTS:
            try:
                resp = _http_requests.get(
                    "https://api.weixin.qq.com/sns/oauth2/access_token",
                    params={
                        "appid": WECHAT_APPID,
                        "secret": WECHAT_SECRET,
                        "code": code,
                        "grant_type": "authorization_code",
                    },
                    timeout=8,
                )
                data = resp.json()
                openid = data.get("openid", "").strip()
                if openid:
                    session["wechat_openid"] = openid
                    # Auto-login if this OpenID is already bound to a user
                    if not session.get("user_id"):
                        wechat_user = auth_service.get_user_by_wechat_openid(openid)
                        if wechat_user and wechat_user["is_active"]:
                            session["user_id"] = wechat_user["id"]
                            session.permanent = True
                            session["last_seen_at"] = datetime.utcnow().isoformat()
            except Exception:
                pass  # Non-critical; user falls back to normal login

        return redirect(return_path)


    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            email = request.form.get("email", "").strip().lower() or None
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            role = "guardian"  # role is set on the profile page after registration
            family_mode = request.form.get("family_mode", "create")
            family_name = request.form.get("family_name", "").strip()
            invite_code_input = request.form.get("invite_code", "").strip().upper()
            accepted_terms = request.form.get("accepted_terms")
            accepted_privacy = request.form.get("accepted_privacy")

            def _render_register_error(message):
                flash(message, "error")
                return render_template("auth/register.html", form=request.form)

            if not full_name or not phone or not password:
                return _render_register_error("请完整填写注册信息。")

            # ── Phone validation (server-side) ──────────────────────────
            phone_ok, phone_err = auth_service.validate_phone(phone)
            if not phone_ok:
                return _render_register_error(phone_err)

            # ── Password strength check ──────────────────────────────────
            pwd_ok, pwd_err = auth_service.validate_password_strength(password)
            if not pwd_ok:
                return _render_register_error(pwd_err)

            if accepted_terms != "on":
                return _render_register_error("请阅读并同意《用户服务协议》。")
            if accepted_privacy != "on":
                return _render_register_error("请阅读并同意《隐私政策》。")

            if password != confirm_password:
                return _render_register_error("两次输入的密码不一致。")

            if role not in ALLOWED_ROLES:
                role = "guardian"  # safe fallback

            # ── IP rate limiting: max 2 registrations per IP per hour ────
            client_ip = get_client_ip()
            recent_count = auth_service.count_recent_registrations_by_ip(
                client_ip, datetime.now() - timedelta(hours=1)
            )
            if recent_count >= 2:
                return _render_register_error(
                    "该网络注册过于频繁，请 1 小时后再试，或联系管理员。"
                )

            # ── Duplicate phone / email check ────────────────────────────
            existing_user = auth_service.user_phone_exists(phone)
            if existing_user:
                return _render_register_error("该手机号已注册，请直接登录或使用找回密码。")

            if email:
                existing_email_user = auth_service.user_email_exists(email)
                if existing_email_user:
                    return _render_register_error("该邮箱已被占用，请更换或留空。")

            # ── WeChat OpenID binding check (in WeChat H5) ───────────────
            wechat_openid = session.get("wechat_openid", "") or None
            if wechat_openid:
                already_bound = auth_service.get_user_by_wechat_openid(wechat_openid)
                if already_bound:
                    return _render_register_error(
                        "该微信账号已绑定其他账号，请直接登录；或更换微信账号注册。"
                    )

            now = datetime.now()
            try:
                user_id = auth_service.create_user_with_family(
                    full_name=full_name,
                    phone=phone,
                    email=email,
                    password_hash=auth_service.hash_password(password),
                    role=role,
                    family_mode=family_mode,
                    family_name=family_name,
                    invite_code_input=invite_code_input,
                    created_at=now,
                    update_by=full_name,
                    wechat_openid=wechat_openid,
                )
            except ValueError as err:
                flash(str(err), "error")
                return render_template("auth/register.html", form=request.form)

            auth_service.log_ip_registration(client_ip, now)
            session["user_id"] = user_id
            session.permanent = True
            flash("注册成功，欢迎来到童忆时光册。", "success")
            return redirect(url_for("dashboard"))

        prefill_form = {
            "family_mode": request.args.get("family_mode", "create").strip().lower(),
            "invite_code": request.args.get("invite_code", "").strip().upper(),
        }
        if prefill_form["family_mode"] not in {"create", "join"}:
            prefill_form["family_mode"] = "create"
        return render_template("auth/register.html", form=prefill_form)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        next_url = get_safe_next_url(request.values.get("next"))
        if request.method == "POST":
            account = request.form.get("account", "").strip().lower()
            password = request.form.get("password", "")
            remember_me = request.form.get("remember_me") == "on"

            user = auth_service.get_login_user_by_phone_or_email(account)

            if not user or not user["is_active"] or not auth_service.check_password(password, user["password_hash"]):
                flash("手机号或密码错误。", "error")
                return render_template("auth/login.html", form=request.form)

            auth_service.update_user_last_login(user["id"], user["full_name"])
            session["user_id"] = user["id"]
            session.permanent = remember_me
            session["last_seen_at"] = datetime.utcnow().isoformat()

            # ── Bind WeChat OpenID if present in session ─────────────────
            wechat_openid = session.get("wechat_openid", "")
            if wechat_openid:
                already_bound = auth_service.get_user_by_wechat_openid(wechat_openid)
                if already_bound and already_bound["id"] != user["id"]:
                    flash("该微信账号已绑定其他账号，本次登录不自动绑定。", "warning")
                elif not already_bound:
                    auth_service.bind_wechat_openid(user["id"], wechat_openid)

            return redirect(next_url or url_for("dashboard"))

        return render_template("auth/login.html", form=request.form, next_url=next_url)

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        pending_phone = session.get("fp_pending_phone")

        if request.method == "POST":
            form_action = request.form.get("form_action", "request_code")

            if form_action == "request_code":
                phone = request.form.get("phone", "").strip()

                phone_ok, phone_err = auth_service.validate_phone(phone)
                if not phone_ok:
                    flash(phone_err, "error")
                    return redirect(url_for("forgot_password"))

                user = auth_service.get_active_user_by_phone(phone)
                if not user:
                    flash("未找到该手机号对应的账号，请确认后重试。", "error")
                    return redirect(url_for("forgot_password"))

                if not user.get("email"):
                    flash(
                        "该账号未绑定邮箱，无法自助找回密码。请联系家庭管理员或系统管理员手工重置。",
                        "warning"
                    )
                    return redirect(url_for("forgot_password"))

                code = generate_numeric_code()
                auth_service.replace_password_reset_code(
                    user_id=user["id"],
                    code=code,
                    expires_at=datetime.now() + timedelta(minutes=10),
                    created_at=datetime.now(),
                )
                try:
                    delivery_message = send_password_reset_code(app, user, code)
                    flash(delivery_message, "success")
                except Exception:
                    flash("邮件发送失败，请检查服务器邮件配置或联系管理员。", "error")
                    return redirect(url_for("forgot_password"))

                session["fp_pending_phone"] = phone
                return redirect(url_for("forgot_password"))

            # form_action == "reset_password"
            phone = pending_phone or request.form.get("phone", "").strip()
            code = request.form.get("code", "").strip()
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            pwd_ok, pwd_err = auth_service.validate_password_strength(new_password)
            if not pwd_ok:
                flash(pwd_err, "error")
                return redirect(url_for("forgot_password"))

            if new_password != confirm_password:
                flash("两次输入的新密码不一致。", "error")
                return redirect(url_for("forgot_password"))

            user = auth_service.get_active_user_by_phone(phone) if phone else None
            if not user:
                flash("账号信息异常，请重新操作。", "error")
                session.pop("fp_pending_phone", None)
                return redirect(url_for("forgot_password"))

            reset_code = auth_service.get_latest_unused_reset_code(user["id"], code)
            if not reset_code or reset_code["expires_at"] < datetime.now():
                flash("验证码无效或已过期，请重新获取。", "error")
                return redirect(url_for("forgot_password"))

            auth_service.reset_user_password(
                user_id=user["id"],
                password_hash=auth_service.hash_password(new_password),
                reset_code_id=reset_code["id"],
                used_at=datetime.now(),
                update_by=user["full_name"]
            )
            session.pop("fp_pending_phone", None)
            flash("密码重置成功，请使用新密码登录。", "success")
            return redirect(url_for("login"))

        return render_template("auth/forgot_password.html", pending_phone=pending_phone)

    @app.route("/logout")
    @login_required
    def logout():
        session.clear()
        flash("已退出登录。", "success")
        return redirect(url_for("login"))

    @app.route("/dashboard", methods=["GET", "POST"])
    @login_required
    def dashboard():
        if request.method == "POST":
            action = request.form.get("form_action")
            if action == "add_baby":
                return handle_add_baby(g.user)
            if action == "add_event":
                return handle_add_event(g.user)
            if action == "add_photo":
                return handle_add_photo(g.user)
            if action == "add_measurement":
                return handle_add_measurement(g.user)
            if action == "add_vaccine":
                return handle_add_vaccine(g.user)

        family = family_service.get_family_by_id(g.user["family_id"])
        family_users = family_service.get_family_users(family["id"])
        family["users"] = family_users

        babies = family_service.get_family_babies(family["id"])

        event_rows = family_service.get_family_event_rows(family["id"], limit=120)
        events = [
            {
                **row,
                "baby": {"name": row["baby_name"], "family": {"name": family["name"]}},
                "author": {"full_name": row["author_name"]},
            }
            for row in event_rows
        ]

        photo_rows = family_service.get_family_photo_rows(family["id"], limit=12)
        photos = [{**row, "baby": {"name": row["baby_name"]}} for row in photo_rows]

        vaccine_rows = family_service.get_family_vaccine_rows(family["id"])
        vaccines = []
        for row in vaccine_rows:
            row["baby"] = {"name": row["baby_name"]}
            row["display_status"] = compute_vaccine_display_status(row["status"], row["due_date"])
            vaccines.append(row)

        measurement_rows = family_service.get_family_measurement_rows(family["id"])

        grouped_measurements = {}
        for row in measurement_rows:
            grouped_measurements.setdefault(row["baby_id"], []).append(row)

        latest_measurements = {}
        growth_charts = {}
        for baby in babies:
            measurements = grouped_measurements.get(baby["id"], [])
            latest_measurements[baby["id"]] = measurements[-1] if measurements else None
            growth_charts[baby["id"]] = {
                "weight": build_chart_data(measurements, "weight_kg", "kg"),
                "height": build_chart_data(measurements, "height_cm", "cm"),
            }

        start_of_day = datetime.combine(date.today(), datetime.min.time())
        count_rows = family_service.get_today_event_counts(family["id"], start_of_day)
        quick_stats = {"feeding": 0, "sleep": 0, "diaper": 0, "health": 0, "milestone": 0}
        for row in count_rows:
            quick_stats[row["event_type"]] = row["count"]

        return render_template(
            "dashboard.html",
            family=family,
            babies=babies,
            events=events,
            photos=photos,
            vaccines=vaccines,
            latest_measurements=latest_measurements,
            growth_charts=growth_charts,
            quick_stats=quick_stats,
        )

    @app.route("/invite")
    @login_required
    def invite_page():
        """邀请家庭成员页面 - 显示邀请码和二维码"""
        user = g.get("user")
        family_id = user["family_id"]

        # 获取邀请码（如果没有则生成）
        invite_code_record = family_service.get_invite_code_for_family(family_id)
        if not invite_code_record:
            invite_code = generate_numeric_code()
            family_service.create_invite_code(family_id, invite_code)
        else:
            invite_code = invite_code_record["invite_code"]

        # 获取家庭成员
        family_members = family_service.get_family_members(family_id)

        join_path = url_for("join_by_invite_code", code=invite_code)
        public_base_url = app.config.get("PUBLIC_BASE_URL")
        if public_base_url:
            join_url = f"{public_base_url}{join_path}"
        else:
            join_url = url_for("join_by_invite_code", code=invite_code, _external=True)

        join_url_is_local = "localhost" in join_url or "127.0.0.1" in join_url

        return render_template(
            "invite.html",
            invite_code=invite_code,
            join_url=join_url,
            join_url_is_local=join_url_is_local,
            family_members=family_members,
        )

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        if request.method == "GET":
            return render_template("profile.html")

        form_action = request.form.get("form_action", "")

        if form_action == "update_profile":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip()
            role = request.form.get("role", "").strip()
            ok, msg = auth_service.update_user_profile(g.user["id"], full_name, email or None, role or None)
            flash(msg, "success" if ok else "error")
            return redirect(url_for("profile"))

        if form_action == "change_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            user_with_hash = auth_service.get_login_user_by_phone_or_email(g.user["phone"])
            if not user_with_hash or not auth_service.check_password(current_password, user_with_hash["password_hash"]):
                flash("当前密码不正确。", "error")
                return redirect(url_for("profile"))

            pwd_ok, pwd_err = auth_service.validate_password_strength(new_password)
            if not pwd_ok:
                flash(pwd_err, "error")
                return redirect(url_for("profile"))

            if new_password != confirm_password:
                flash("两次输入的新密码不一致。", "error")
                return redirect(url_for("profile"))

            auth_service.update_user_password(g.user["id"], auth_service.hash_password(new_password))
            flash("密码已更新，请用新密码重新登录。", "success")
            session.clear()
            return redirect(url_for("login"))

        flash("未知操作。", "error")
        return redirect(url_for("profile"))

    @app.route("/admin")
    @login_required
    @admin_required
    def admin_panel():
        family_id = request.args.get("family_id", type=int)
        event_type = request.args.get("event_type", "").strip()
        date_from_raw = request.args.get("date_from", "").strip()
        date_to_raw = request.args.get("date_to", "").strip()
        keyword = request.args.get("keyword", "").strip()

        family_stats_rows = admin_service.get_admin_family_stats_rows()
        family_stats = [
            {
                "family": {
                    "id": row["id"],
                    "name": row["name"],
                    "invite_code": row["invite_code"],
                    "created_at": row["created_at"],
                },
                "user_count": row["user_count"],
                "baby_count": row["baby_count"],
                "event_count": row["event_count"],
                "photo_count": row["photo_count"],
                "vaccine_count": row["vaccine_count"],
            }
            for row in family_stats_rows
        ]

        family_options = admin_service.get_family_options()
        recent_users = admin_service.get_recent_users(limit=12)

        date_from = parse_date_from_form(date_from_raw)
        start_time = datetime.combine(date_from, datetime.min.time()) if date_from else None

        date_to = parse_date_from_form(date_to_raw)
        end_time = datetime.combine(date_to, datetime.max.time()) if date_to else None

        filtered_event_rows = admin_service.search_admin_events(
            family_id=family_id,
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            limit=100,
        )
        recent_events = [
            {
                **row,
                "baby": {"name": row["baby_name"], "family": {"name": row["family_name"]}},
                "author": {"full_name": row["author_name"]},
            }
            for row in filtered_event_rows
        ]

        totals_row = admin_service.get_admin_totals()

        return render_template(
            "admin.html",
            family_stats=family_stats,
            family_options=family_options,
            recent_users=recent_users,
            recent_events=recent_events,
            filters={
                "family_id": family_id,
                "event_type": event_type,
                "date_from": date_from_raw,
                "date_to": date_to_raw,
                "keyword": keyword,
            },
            totals=totals_row,
        )

    @app.route("/admin/family/<int:family_id>")
    @login_required
    @admin_required
    def admin_family_detail(family_id: int):
        family = family_service.get_family_by_id(family_id)
        if not family:
            flash("未找到该家庭。", "error")
            return redirect(url_for("admin_panel"))

        family_users = family_service.get_family_users(family_id)
        babies = family_service.get_family_babies(family_id)

        vaccine_rows = family_service.get_family_vaccine_rows(family_id)
        vaccines = []
        for row in vaccine_rows:
            row["baby"] = {"name": row["baby_name"]}
            row["display_status"] = compute_vaccine_display_status(row["status"], row["due_date"])
            vaccines.append(row)

        photo_rows = family_service.get_family_photo_rows(family_id, limit=12)
        photos = [{**row, "baby": {"name": row["baby_name"]}} for row in photo_rows]

        event_rows = family_service.get_family_event_rows(family_id, limit=30)
        recent_events = [{**row, "baby": {"name": row["baby_name"]}, "author": {"full_name": row["author_name"]}} for row in event_rows]

        return render_template(
            "admin_family.html",
            family=family,
            family_users=family_users,
            babies=babies,
            vaccines=vaccines,
            photos=photos,
            recent_events=recent_events,
        )

    @app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_user(user_id: int):
        user = admin_service.get_user_basic_by_id(user_id)
        if not user:
            flash("未找到要删除的用户。", "error")
            return redirect(url_for("admin_panel"))
        if g.user["id"] == user["id"]:
            flash("不能删除当前登录的管理员。", "error")
            return redirect(url_for("admin_panel"))

        admin_service.deactivate_user(user_id)
        flash(f"已停用用户：{user['full_name']}。", "success")
        return redirect(url_for("admin_family_detail", family_id=user["family_id"]))

    # 生成分享二维码的路由
    @app.route("/qrcode/<code_type>/<code_value>")
    def generate_qrcode(code_type: str, code_value: str):
        """生成二维码（邀请码、分享链接等）"""
        if not HAS_QRCODE:
            return "QR code library not installed", 501

        if code_type not in ["invite", "share"]:
            return "Invalid code type", 400

        # 生成二维码数据
        if code_type == "invite":
            # 邀请码格式
            qr_data = f"https://baby-time-machine.com/join?code={code_value}"
        elif code_type == "share":
            # 分享链接
            qr_data = f"https://baby-time-machine.com/shared/{code_value}"

        # 创建二维码
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        # 生成图像
        img = qr.make_image(fill_color="black", back_color="white")

        # 保存到字节流
        img_io = BytesIO()
        img.save(img_io, "PNG")
        img_io.seek(0)

        return send_from_directory(
            BytesIO(img_io.getvalue()),
            "",
            mimetype="image/png",
            as_attachment=False,
        )

    @app.route("/api/qrcode", methods=["POST"])
    @login_required
    def api_generate_qrcode():
        """API 路由 - 生成二维码并返回 base64"""
        if not HAS_QRCODE:
            return {"error": "QR code library not installed"}, 501

        import base64

        data = request.get_json() or {}
        code_type = data.get("type", "invite")
        code_value = data.get("value", "")

        if not code_value:
            return {"error": "Missing code value"}, 400

        # 生成二维码
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(code_value)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # 转换为 base64
        img_io = BytesIO()
        img.save(img_io, "PNG")
        img_base64 = base64.b64encode(img_io.getvalue()).decode()

        return {
            "success": True,
            "qrcode": f"data:image/png;base64,{img_base64}",
            "type": code_type,
            "value": code_value,
        }


    @app.cli.command("init-db")
    def init_db_command():
        core_db.init_database_schema()
        print("Database tables created.")

    return app


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not g.get("user"):
            flash("请先登录。", "error")
            return redirect(url_for("login", next=get_current_relative_url()))
        return view_func(*args, **kwargs)

    return wrapped


def get_safe_next_url(next_value: str | None) -> str | None:
    if not next_value:
        return None
    target = next_value.strip()
    if not target:
        return None

    parsed = urlsplit(target)
    # Only allow local relative paths to avoid open redirects.
    if parsed.scheme or parsed.netloc:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target


def get_current_relative_url() -> str:
    full_path = request.full_path or request.path or "/"
    if full_path.endswith("?"):
        full_path = full_path[:-1]
    return full_path or "/"


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        user = g.get("user")
        if not user or user["role"] != "admin":
            flash("你没有管理员权限。", "error")
            return redirect(url_for("dashboard"))
        return view_func(*args, **kwargs)

    return wrapped


def generate_numeric_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def parse_date_from_form(value: str):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_datetime_from_form(value: str) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.utcnow()


def parse_optional_float(value: str):
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def save_uploaded_image(image_file) -> str | None:
    original_name = secure_filename(image_file.filename or "")
    extension = os.path.splitext(original_name)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None

    image_dir = app.config["UPLOAD_IMAGE_DIR"]
    os.makedirs(image_dir, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}{extension}"
    image_file.save(os.path.join(image_dir, stored_name))
    return url_for("uploaded_image", filename=stored_name)


def handle_add_baby(user: dict):
    name = request.form.get("baby_name", "").strip()
    birthday_raw = request.form.get("baby_birthday", "").strip()
    gender = request.form.get("baby_gender", "unknown")
    note = request.form.get("baby_note", "").strip()

    birthday = parse_date_from_form(birthday_raw)

    success, message = family_service.add_baby_validated(user["family_id"], name, birthday, gender, note)
    return ajax_redirect(success, message)


def handle_add_event(user: dict):
    baby_id_raw = request.form.get("baby_id", "")
    event_type = request.form.get("event_type", "feeding")
    amount_raw = request.form.get("amount", "").strip()
    unit = request.form.get("unit", "").strip()
    start_time_raw = request.form.get("start_time", "")
    end_time_raw = request.form.get("end_time", "")
    note = request.form.get("note", "").strip()

    try:
        baby_id = int(baby_id_raw)
    except (TypeError, ValueError):
        return ajax_redirect(False, "请选择有效的宝宝。")

    amount = parse_optional_float(amount_raw) if amount_raw else None
    start_time = parse_datetime_from_form(start_time_raw)
    end_time = parse_datetime_from_form(end_time_raw) if end_time_raw else None

    success, message = family_service.add_event_validated(
        family_id=user["family_id"],
        baby_id=baby_id,
        user_id=user["id"],
        event_type=event_type,
        amount=amount,
        unit=unit or None,
        start_time=start_time,
        end_time=end_time,
        note=note,
    )
    return ajax_redirect(success, message)


def handle_add_photo(user: dict):
    baby_id_raw = request.form.get("baby_id", "")
    caption = request.form.get("caption", "").strip()
    taken_on = parse_date_from_form(request.form.get("taken_on", "").strip())
    image_file = request.files.get("image_file")

    try:
        baby_id = int(baby_id_raw)
    except (TypeError, ValueError):
        return ajax_redirect(False, "请选择有效的宝宝。")

    if not image_file or not image_file.filename:
        return ajax_redirect(False, "请选择要上传的照片文件。")

    image_url = save_uploaded_image(image_file)
    if not image_url:
        return ajax_redirect(False, "仅支持上传 jpg、jpeg、png、gif、webp 格式的图片。")

    success, message = family_service.add_photo_validated(
        family_id=user["family_id"],
        baby_id=baby_id,
        user_id=user["id"],
        image_url=image_url,
        caption=caption,
        taken_on=taken_on,
    )
    return ajax_redirect(success, message)


def handle_add_measurement(user: dict):
    baby_id_raw = request.form.get("baby_id", "")
    recorded_on = parse_date_from_form(request.form.get("recorded_on", "").strip())
    weight_raw = request.form.get("weight_kg", "").strip()
    height_raw = request.form.get("height_cm", "").strip()
    head_raw = request.form.get("head_circumference_cm", "").strip()
    note = request.form.get("note", "").strip()

    try:
        baby_id = int(baby_id_raw)
    except (TypeError, ValueError):
        return ajax_redirect(False, "请选择有效的宝宝。")

    weight_kg = parse_optional_float(weight_raw) if weight_raw else None
    height_cm = parse_optional_float(height_raw) if height_raw else None
    head_circumference_cm = parse_optional_float(head_raw) if head_raw else None

    if weight_raw and weight_kg is None:
        return ajax_redirect(False, "体重格式不正确。")
    if height_raw and height_cm is None:
        return ajax_redirect(False, "身高格式不正确。")
    if head_raw and head_circumference_cm is None:
        return ajax_redirect(False, "头围格式不正确。")

    success, message = family_service.add_measurement_validated(
        family_id=user["family_id"],
        baby_id=baby_id,
        user_id=user["id"],
        recorded_on=recorded_on,
        weight_kg=weight_kg,
        height_cm=height_cm,
        head_circumference_cm=head_circumference_cm,
        note=note,
    )
    return ajax_redirect(success, message)


def handle_add_vaccine(user: dict):
    baby_id_raw = request.form.get("baby_id", "")
    title = request.form.get("title", "").strip()
    due_date = parse_date_from_form(request.form.get("due_date", "").strip())
    status = request.form.get("status", "pending")
    note = request.form.get("note", "").strip()

    if status not in ALLOWED_VACCINE_STATUSES:
        return ajax_redirect(False, "疫苗状态无效。")

    try:
        baby_id = int(baby_id_raw)
    except (TypeError, ValueError):
        return ajax_redirect(False, "请选择有效的宝宝。")

    success, message = family_service.add_vaccine_validated(
        family_id=user["family_id"],
        baby_id=baby_id,
        title=title,
        due_date=due_date,
        status=status,
        note=note,
    )
    return ajax_redirect(success, message)


def compute_vaccine_display_status(status: str, due_date: date) -> str:
    if status == "done":
        return "done"
    if due_date < date.today():
        return "overdue"
    if due_date <= date.today() + timedelta(days=7):
        return "soon"
    if status == "booked":
        return "booked"
    return "pending"


def build_chart_data(measurements, field_name: str, unit: str):
    data_points = []
    for measurement in measurements:
        value = measurement.get(field_name)
        if value is not None:
            data_points.append((measurement["recorded_on"], value))

    if not data_points:
        return None

    min_value = min(value for _, value in data_points)
    max_value = max(value for _, value in data_points)
    span = max(max_value - min_value, 1)
    width = 280
    x_step = width / max(len(data_points) - 1, 1)

    points = []
    labels = []
    for index, (recorded_on, value) in enumerate(data_points):
        x = 12 + (index * x_step)
        y = 116 - ((value - min_value) / span) * 88
        points.append(f"{round(x, 2)},{round(y, 2)}")
        labels.append({"date": recorded_on.strftime("%m-%d"), "value": value})

    return {
        "points": " ".join(points),
        "labels": labels,
        "min": round(min_value, 1),
        "max": round(max_value, 1),
        "unit": unit,
    }


def send_password_reset_code(app: Flask, user: dict, code: str) -> str:
    smtp_host = app.config.get("SMTP_HOST")
    if not smtp_host or not user.get("email"):
        return f"邮箱地址或邮件服务未配置"

    message = EmailMessage()
    message["Subject"] = "童忆时光册密码重置验证码"
    message["From"] = app.config.get("SMTP_FROM") or app.config.get("SMTP_USERNAME")
    message["To"] = user["email"]
    message.set_content(
        f"你好，{user['full_name']}：\n\n你的密码重置验证码是 {code}，10 分钟内有效。\n如果不是你本人操作，请忽略这封邮件。"
    )

    with smtplib.SMTP(smtp_host, app.config.get("SMTP_PORT", 587), timeout=15) as smtp:
        smtp.starttls()
        username = app.config.get("SMTP_USERNAME")
        password = app.config.get("SMTP_PASSWORD")
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
    return "验证码已发送到邮箱，请查收。"


app = create_app()


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
