from database import execute_sql, fetch_all, fetch_one


def get_admin_family_stats_rows():
    return fetch_all(
        """
        SELECT
            f.id, f.name, f.invite_code, f.created_time AS created_at,
            (SELECT COUNT(*) FROM users u WHERE u.family_id = f.id AND u.is_active = 1) AS user_count,
            (SELECT COUNT(*) FROM babies b WHERE b.family_id = f.id) AS baby_count,
            (SELECT COUNT(*) FROM baby_events e WHERE e.family_id = f.id) AS event_count,
            (SELECT COUNT(*) FROM baby_photos p WHERE p.family_id = f.id) AS photo_count,
            (SELECT COUNT(*) FROM vaccine_reminders v WHERE v.family_id = f.id) AS vaccine_count
        FROM families f
        ORDER BY f.created_time DESC
        """
    )


def get_family_options():
    return fetch_all("SELECT id, name FROM families ORDER BY name ASC")


def get_recent_users(limit=12):
    return fetch_all(
        """
        SELECT id, full_name, role, email, is_active, created_time AS created_at
        FROM users
        ORDER BY created_time DESC
        LIMIT %s
        """,
        (limit,),
    )


def search_admin_events(family_id=None, event_type="", start_time=None, end_time=None, keyword="", limit=100):
    event_sql = [
        """
        SELECT
            e.id, e.family_id, e.baby_id, e.user_id, e.event_type, e.amount, e.unit, e.start_time, e.end_time, e.note,
            e.created_time AS created_at,
            f.name AS family_name,
            b.name AS baby_name,
            u.full_name AS author_name
        FROM baby_events e
        JOIN families f ON f.id = e.family_id
        JOIN babies b ON b.id = e.baby_id
        JOIN users u ON u.id = e.user_id
        WHERE 1 = 1
        """
    ]
    params = []

    if family_id:
        event_sql.append("AND e.family_id = %s")
        params.append(family_id)
    if event_type:
        event_sql.append("AND e.event_type = %s")
        params.append(event_type)
    if start_time:
        event_sql.append("AND e.start_time >= %s")
        params.append(start_time)
    if end_time:
        event_sql.append("AND e.start_time <= %s")
        params.append(end_time)
    if keyword:
        like_value = f"%{keyword}%"
        event_sql.append("AND (b.name LIKE %s OR u.full_name LIKE %s OR e.note LIKE %s)")
        params.extend([like_value, like_value, like_value])

    event_sql.append("ORDER BY e.start_time DESC LIMIT %s")
    params.append(limit)
    return fetch_all("\n".join(event_sql), params)


def get_admin_totals():
    return fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM users WHERE is_active = 1) AS users,
            (SELECT COUNT(*) FROM families) AS families,
            (SELECT COUNT(*) FROM babies) AS babies,
            (SELECT COUNT(*) FROM baby_events) AS events
        """
    )


def get_user_basic_by_id(user_id):
    return fetch_one("SELECT id, full_name, family_id FROM users WHERE id = %s", (user_id,))


def deactivate_user(user_id):
    return execute_sql("UPDATE users SET is_active = 0, updated_time = NOW() WHERE id = %s", (user_id,))
