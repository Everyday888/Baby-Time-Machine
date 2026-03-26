import random
import string
from datetime import date, datetime, timedelta

from database import execute_sql, fetch_one, get_connection, run_transaction


def get_active_user_by_id(user_id):
    return fetch_one(
        """
        SELECT id, full_name, phone, email, role, family_id, is_active,
               created_time AS created_at, updated_time AS updated_at
        FROM users
        WHERE id = %s AND is_active = 1
        """,
        (user_id,)
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


def create_user_with_family(full_name, phone, email, password_hash, role, family_mode, family_name, invite_code_input, created_at, update_by):
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
                    updated_time, created_time, created_by, updated_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
                """,
                (full_name, phone, email, password_hash, role, family_id, created_at, created_at, update_by, update_by)
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


def update_user_profile(user_id, full_name, email):
    """Update a user's display name and optional email.
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
