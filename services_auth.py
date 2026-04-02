import re
import bcrypt as _bcrypt
import random
import string
from datetime import date, datetime, timedelta

from database import execute_sql, fetch_one, get_connection, run_transaction


# ---------------------------------------------------------------------------
# Phone & password validation
# ---------------------------------------------------------------------------

_PHONE_RE = re.compile(r'^1[3-9]\d{9}$')

_WEAK_PASSWORDS = frozenset({
    '000000', '111111', '222222', '333333', '444444', '555555',
    '666666', '777777', '888888', '999999', '123456', '654321',
    '123123', '321321', '112233', '998877', '1234567', '12345678',
    '123456789', '1234567890', 'password', 'qwerty', 'abc123', 'admin123',
})


def validate_phone(phone: str) -> tuple[bool, str]:
    """Return (True, '') if valid mainland China number, else (False, error_msg)."""
    p = (phone or '').strip()
    if not _PHONE_RE.match(p):
        return False, "请填写11位中国大陆手机号（13~19开头）。"
    # Block obviously fake numbers: last 8 digits all identical (e.g. 13333333333)
    if len(set(p[3:])) == 1:
        return False, "该手机号格式异常，请填写真实手机号。"
    return True, ""


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Return (True, '') if password meets strength requirements."""
    if len(password) < 6:
        return False, "密码至少需要 6 位。"
    if password in _WEAK_PASSWORDS:
        return False, "密码过于简单，请换一个更安全的密码（避免 123456、888888 等）。"
    if len(set(password)) == 1:
        return False, "密码不能全为相同字符。"
    return True, ""


# ---------------------------------------------------------------------------
# Password hashing (bcrypt) with werkzeug fallback for legacy hashes
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash password with bcrypt (rounds=12)."""
    return _bcrypt.hashpw(password.encode('utf-8'), _bcrypt.gensalt(rounds=12)).decode('utf-8')


def check_password(password: str, password_hash: str) -> bool:
    """Verify a password. Supports bcrypt hashes and legacy werkzeug hashes."""
    try:
        if password_hash.startswith(('$2b$', '$2a$', '$2y$')):
            return _bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        # Fallback for existing werkzeug pbkdf2/scrypt hashes
        from werkzeug.security import check_password_hash as _wz_check
        return _wz_check(password_hash, password)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# IP registration rate limiting
# ---------------------------------------------------------------------------

def count_recent_registrations_by_ip(ip: str, since: datetime) -> int:
    result = fetch_one(
        "SELECT COUNT(*) AS cnt FROM ip_reg_log WHERE ip = %s AND registered_at >= %s",
        (ip, since)
    )
    return (result or {}).get('cnt', 0)


def log_ip_registration(ip: str, registered_at: datetime) -> None:
    execute_sql(
        "INSERT INTO ip_reg_log (ip, registered_at) VALUES (%s, %s)",
        (ip, registered_at)
    )


def get_active_user_by_id(user_id):
    return fetch_one(
        """
        SELECT id, full_name, phone, email, role, family_id, is_active,
               wechat_openid, created_time AS created_at, updated_time AS updated_at
        FROM users
        WHERE id = %s AND is_active = 1
        """,
        (user_id,)
    )


def get_active_user_by_phone(phone: str):
    """Look up an active user by phone number only."""
    return fetch_one(
        """
        SELECT id, full_name, phone, email, role, family_id, is_active,
               wechat_openid, created_time AS created_at
        FROM users
        WHERE phone = %s AND is_active = 1
        """,
        (phone,)
    )


def get_user_by_wechat_openid(openid: str):
    """Return user matching the given WeChat OpenID (any active status)."""
    return fetch_one(
        "SELECT id, full_name, is_active FROM users WHERE wechat_openid = %s",
        (openid,)
    )


def bind_wechat_openid(user_id: int, openid: str) -> None:
    """Bind a WeChat OpenID to an existing user account."""
    execute_sql(
        "UPDATE users SET wechat_openid = %s, updated_time = NOW() WHERE id = %s",
        (openid, user_id)
    )


def user_phone_exists(phone):
    return fetch_one("SELECT id FROM users WHERE phone = %s", (phone,))


def user_email_exists(email):
    return fetch_one("SELECT id FROM users WHERE email = %s", (email,))


def get_login_user_by_phone_or_email(account):
    return fetch_one(
        """
        SELECT id, full_name, password_hash, is_active
        FROM users
        WHERE phone = %s OR email = %s
        """,
        (account, account)
    )


def get_active_user_by_phone_or_email(account):
    return fetch_one(
        """
        SELECT id, full_name, phone, email, created_time AS created_at, updated_time AS updated_at 
        FROM users 
        WHERE (phone = %s OR email = %s) AND is_active = 1
        """,
        (account, account)
    )


def update_user_last_login(user_id, user_full_name):
    return execute_sql(
        "UPDATE users SET updated_time = %s, updated_by = %s WHERE id = %s",
        (datetime.now(), user_full_name, user_id)
    )


def generate_invite_code(connection=None) -> str:
    external_connection = connection is not None
    conn = connection or get_connection()
    try:
        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM families WHERE invite_code = %s", (code,))
                exists = cursor.fetchone()
            if not exists:
                return code
    finally:
        if not external_connection:
            conn.close()


def create_user_with_family(full_name, phone, email, password_hash, role, family_mode, family_name, invite_code_input, created_at, update_by, wechat_openid=None):
    def _register_transaction(connection):
        with connection.cursor() as cursor:
            if family_mode == "join":
                cursor.execute(
                    "SELECT id, name FROM families WHERE invite_code = %s",
                    (invite_code_input,)
                )
                family = cursor.fetchone()
                if not family:
                    raise ValueError("家庭邀请码无效，请检查后重试。")
                family_id = family["id"]
            else:
                if not family_name:
                    raise ValueError("创建家庭时请填写家庭名称。")
                cursor.execute(
                    """
                    INSERT INTO families (name, invite_code, updated_time, created_time, created_by, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (family_name, generate_invite_code(connection), created_at, created_at, update_by, update_by)
                )
                family_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO users (
                    full_name, phone, email, password_hash, role, family_id, is_active,
                    wechat_openid, updated_time, created_time, created_by, updated_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s)
                """,
                (full_name, phone, email, password_hash, role, family_id, wechat_openid, created_at, created_at, update_by, update_by)
            )
            return cursor.lastrowid

    return run_transaction(_register_transaction)


def replace_password_reset_code(user_id, code, expires_at, created_at):
    def _reset_code_transaction(connection):
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM password_reset_codes WHERE user_id = %s AND used_time IS NULL",
                (user_id,)
            )
            cursor.execute(
                """
                INSERT INTO password_reset_codes (user_id, code, expires_at, updated_time, created_time)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, code, expires_at, created_at, created_at)
            )

    return run_transaction(_reset_code_transaction)


def get_latest_unused_reset_code(user_id, code):
    return fetch_one(
        """
        SELECT id, expires_at
        FROM password_reset_codes
        WHERE user_id = %s AND code = %s AND used_time IS NULL
        ORDER BY created_time DESC
        LIMIT 1
        """,
        (user_id, code)
    )


def reset_user_password(user_id, password_hash, reset_code_id, used_at, update_by):
    def _password_reset_transaction(connection):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET password_hash = %s, updated_time = %s, updated_by = %s WHERE id = %s",
                (password_hash, used_at, update_by, user_id)
            )
            cursor.execute(
                "UPDATE password_reset_codes SET used_time = %s, updated_time = %s, updated_by = %s WHERE id = %s",
                (used_at, used_at, update_by, reset_code_id)
            )

    return run_transaction(_password_reset_transaction)


_ALLOWED_PROFILE_ROLES = frozenset({
    'father', 'mother', 'grandpa', 'grandma',
    'grandpa_maternal', 'grandma_maternal', 'guardian',
})


def update_user_profile(user_id, full_name, email, role=None):
    """Update a user's display name, optional email, and optional role.
    Returns (True, success_msg) or (False, error_msg).
    """
    if not full_name or not full_name.strip():
        return False, "姓名不能为空。"
    full_name = full_name.strip()

    email = email.strip() if email else None

    if email:
        conflict = fetch_one(
            "SELECT id FROM users WHERE email = %s AND id != %s",
            (email, user_id)
        )
        if conflict:
            return False, "该邮箱已被其他账号使用。"

    if role and role in _ALLOWED_PROFILE_ROLES:
        execute_sql(
            "UPDATE users SET full_name = %s, email = %s, role = %s, updated_time = NOW() WHERE id = %s",
            (full_name, email, role, user_id)
        )
    else:
        execute_sql(
            "UPDATE users SET full_name = %s, email = %s, updated_time = NOW() WHERE id = %s",
            (full_name, email, user_id)
        )
    return True, "个人信息已更新。"


def update_user_password(user_id, new_password_hash):
    """Replace a user's password hash."""
    execute_sql(
        "UPDATE users SET password_hash = %s, updated_time = NOW() WHERE id = %s",
        (new_password_hash, user_id)
    )
