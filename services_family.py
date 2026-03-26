from datetime import date, datetime

from database import execute_sql, fetch_all, fetch_one


def get_family_by_id(family_id):
    return fetch_one("SELECT id, name, invite_code, created_time AS created_at FROM families WHERE id = %s", (family_id,))


def get_family_users(family_id):
    return fetch_all(
        "SELECT id, full_name, email, role, is_active, created_time AS created_at FROM users WHERE family_id = %s ORDER BY created_time ASC",
        (family_id,),
    )


def get_family_babies(family_id):
    return fetch_all(
        "SELECT id, family_id, name, birthday, gender, note, created_time AS created_at FROM babies WHERE family_id = %s ORDER BY birthday ASC",
        (family_id,),
    )


def get_family_event_rows(family_id, limit=120):
    return fetch_all(
        """
        SELECT
            e.id, e.family_id, e.baby_id, e.user_id, e.event_type, e.amount, e.unit, e.start_time, e.end_time, e.note,
            e.created_time AS created_at,
            b.name AS baby_name,
            u.full_name AS author_name
        FROM baby_events e
        JOIN babies b ON b.id = e.baby_id
        JOIN users u ON u.id = e.user_id
        WHERE e.family_id = %s
        ORDER BY e.start_time DESC
        LIMIT %s
        """,
        (family_id, limit),
    )


def get_family_photo_rows(family_id, limit=12):
    return fetch_all(
        """
        SELECT
            p.id, p.family_id, p.baby_id, p.user_id, p.image_url, p.caption, p.taken_on,
            p.created_time AS created_at,
            b.name AS baby_name
        FROM baby_photos p
        JOIN babies b ON b.id = p.baby_id
        WHERE p.family_id = %s
        ORDER BY p.taken_on DESC, p.created_time DESC
        LIMIT %s
        """,
        (family_id, limit),
    )


def get_family_vaccine_rows(family_id):
    return fetch_all(
        """
        SELECT
            v.id, v.family_id, v.baby_id, v.title, v.due_date, v.status, v.note,
            v.created_time AS created_at,
            b.name AS baby_name
        FROM vaccine_reminders v
        JOIN babies b ON b.id = v.baby_id
        WHERE v.family_id = %s
        ORDER BY v.due_date ASC
        """,
        (family_id,),
    )


def get_family_measurement_rows(family_id):
    return fetch_all(
        """
         SELECT id, family_id, baby_id, user_id, recorded_on, weight_kg, height_cm, head_circumference_cm, note,
             created_time AS created_at
        FROM baby_measurements
        WHERE family_id = %s
         ORDER BY baby_id ASC, recorded_on ASC, created_time ASC
        """,
        (family_id,),
    )


def get_today_event_counts(family_id, start_of_day):
    return fetch_all(
        """
        SELECT event_type, COUNT(*) AS count
        FROM baby_events
        WHERE family_id = %s AND start_time >= %s
        GROUP BY event_type
        """,
        (family_id, start_of_day),
    )


def get_baby_in_family(baby_id, family_id):
    return fetch_one("SELECT id, family_id, name FROM babies WHERE id = %s AND family_id = %s", (baby_id, family_id))


def create_baby(family_id, name, birthday, gender, note, created_at):
    return execute_sql(
        """
        INSERT INTO babies (family_id, name, birthday, gender, note, updated_time, created_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (family_id, name, birthday, gender, note, created_at, created_at),
    )


def create_baby_event(family_id, baby_id, user_id, event_type, amount, unit, start_time, end_time, note, created_at):
    return execute_sql(
        """
        INSERT INTO baby_events (
            family_id, baby_id, user_id, event_type, amount, unit, start_time, end_time, note, updated_time, created_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (family_id, baby_id, user_id, event_type, amount, unit, start_time, end_time, note, created_at, created_at),
    )


def create_baby_photo(family_id, baby_id, user_id, image_url, caption, taken_on, created_at):
    return execute_sql(
        """
        INSERT INTO baby_photos (family_id, baby_id, user_id, image_url, caption, taken_on, updated_time, created_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (family_id, baby_id, user_id, image_url, caption, taken_on, created_at, created_at),
    )


def create_baby_measurement(
    family_id,
    baby_id,
    user_id,
    recorded_on,
    weight_kg,
    height_cm,
    head_circumference_cm,
    note,
    created_at,
):
    return execute_sql(
        """
        INSERT INTO baby_measurements (
            family_id, baby_id, user_id, recorded_on, weight_kg, height_cm, head_circumference_cm, note, updated_time, created_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (family_id, baby_id, user_id, recorded_on, weight_kg, height_cm, head_circumference_cm, note, created_at, created_at),
    )


def create_vaccine_reminder(family_id, baby_id, title, due_date, status, note, created_at):
    return execute_sql(
        """
        INSERT INTO vaccine_reminders (family_id, baby_id, title, due_date, status, note, updated_time, created_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (family_id, baby_id, title, due_date, status, note, created_at, created_at),
    )


def add_baby_validated(family_id: int, name: str, birthday, gender: str = "unknown", note: str = ""):
    """验证并创建宝宝 - 返回 (success, message)"""
    if not name:
        return False, "请填写宝宝姓名。"
    if not birthday:
        return False, "请填写宝宝生日。"
    if birthday > date.today():
        return False, "宝宝生日不能是未来日期。"
    
    create_baby(family_id, name, birthday, gender, note, datetime.now())
    return True, f"已添加宝宝：{name}。"


def add_event_validated(family_id: int, baby_id: int, user_id: int, event_type: str, 
                       amount: float = None, unit: str = None, start_time: datetime = None, 
                       end_time: datetime = None, note: str = ""):
    """验证并创建成长记录 - 返回 (success, message)"""
    if not get_baby_in_family(baby_id, family_id):
        return False, "请选择有效的宝宝。"
    
    if amount and isinstance(amount, str):
        try:
            amount = float(amount)
        except ValueError:
            return False, "数量请填写数字。"
    
    if end_time and start_time and end_time < start_time:
        return False, "结束时间不能早于开始时间。"
    
    create_baby_event(
        family_id=family_id, baby_id=baby_id, user_id=user_id, event_type=event_type,
        amount=amount, unit=unit or None, start_time=start_time, end_time=end_time, 
        note=note, created_at=datetime.now()
    )
    return True, "成长记录已保存。"


def add_photo_validated(family_id: int, baby_id: int, user_id: int, image_url: str, 
                       caption: str = "", taken_on: date = None):
    """验证并创建照片 - 返回 (success, message)"""
    if not get_baby_in_family(baby_id, family_id):
        return False, "请选择有效的宝宝。"
    if not image_url:
        return False, "请填写照片地址。"
    
    create_baby_photo(family_id, baby_id, user_id, image_url, caption, taken_on, datetime.now())
    return True, "照片已加入宝宝照片墙。"


def add_measurement_validated(family_id: int, baby_id: int, user_id: int, recorded_on: date,
                             weight_kg: float = None, height_cm: float = None, 
                             head_circumference_cm: float = None, note: str = ""):
    """验证并创建测量记录 - 返回 (success, message)"""
    if not get_baby_in_family(baby_id, family_id):
        return False, "请选择有效的宝宝。"
    if not recorded_on:
        return False, "请填写测量日期。"
    
    create_baby_measurement(
        family_id=family_id, baby_id=baby_id, user_id=user_id, recorded_on=recorded_on,
        weight_kg=weight_kg, height_cm=height_cm, head_circumference_cm=head_circumference_cm,
        note=note, created_at=datetime.now()
    )
    return True, "成长曲线数据已保存。"


def add_vaccine_validated(family_id: int, baby_id: int, title: str, due_date: date, 
                         status: str = "pending", note: str = ""):
    """验证并创建疫苗提醒 - 返回 (success, message)"""
    if not get_baby_in_family(baby_id, family_id):
        return False, "请选择有效的宝宝。"
    if not title:
        return False, "请填写疫苗名称。"
    if not due_date:
        return False, "请填写接种日期。"
    
    create_vaccine_reminder(family_id, baby_id, title, due_date, status, note, datetime.now())
    return True, "疫苗提醒已添加。"


def get_invite_code_for_family(family_id: int):
    """获取家庭的邀请码"""
    return fetch_one(
        "SELECT id, invite_code, created_time FROM families WHERE id = %s AND invite_code IS NOT NULL",
        (family_id,)
    )


def create_invite_code(family_id: int, code: str):
    """为家庭生成邀请码"""
    execute_sql(
        "UPDATE families SET invite_code = %s WHERE id = %s",
        (code, family_id)
    )


def get_family_members(family_id: int):
    """获取家庭的所有成员（只显示活跃用户）"""
    return fetch_all(
        """
        SELECT id, full_name, phone, email, role, is_active, created_time 
        FROM users 
        WHERE family_id = %s AND is_active = 1 
        ORDER BY created_time ASC
        """,
        (family_id,)
    )

