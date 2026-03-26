import os

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor


load_dotenv()


def _db_name() -> str:
    return os.getenv("MYSQL_DB") or os.getenv("MYSQL_DATABASE") or "baby_time_machine"


def _db_charset() -> str:
    return os.getenv("MYSQL_CHARSET", "utf8mb4")


def get_connection(with_database=True):
    params = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "charset": _db_charset(),
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    if with_database:
        params["database"] = _db_name()
    return pymysql.connect(**params)


def fetch_one(sql, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchone()
    finally:
        connection.close()


def fetch_all(sql, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchall()
    finally:
        connection.close()


def execute_sql(sql, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            connection.commit()
            return cursor.lastrowid, cursor.rowcount
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def run_transaction(transaction_func):
    connection = get_connection()
    try:
        result = transaction_func(connection)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database_schema():
    db_name = _db_name()
    charset = _db_charset()

    connection = get_connection(with_database=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"CHARACTER SET {charset} COLLATE {charset}_unicode_ci"
            )
        connection.commit()
    finally:
        connection.close()

    schema_statements = [
        """
        CREATE TABLE IF NOT EXISTS families (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            invite_code VARCHAR(12) NOT NULL UNIQUE,
            updated_by VARCHAR(50) DEFAULT NULL,
            updated_time DATETIME NOT NULL,
            created_by VARCHAR(50) DEFAULT NULL,
            created_time DATETIME NOT NULL,
            INDEX idx_families_invite_code (invite_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(80) NOT NULL,
            phone VARCHAR(30) NOT NULL UNIQUE,
            email VARCHAR(120) DEFAULT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL,
            family_id INT NOT NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            updated_by VARCHAR(50) DEFAULT NULL,
            updated_time DATETIME NOT NULL,
            created_by VARCHAR(50) DEFAULT NULL,
            created_time DATETIME NOT NULL,
            INDEX idx_users_phone (phone),
            INDEX idx_users_email (email),
            INDEX idx_users_family_id (family_id),
            CONSTRAINT fk_users_family FOREIGN KEY (family_id) REFERENCES families(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS babies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            family_id INT NOT NULL,
            name VARCHAR(80) NOT NULL,
            birthday DATE NOT NULL,
            gender VARCHAR(20) NOT NULL DEFAULT 'unknown',
            note VARCHAR(255) NOT NULL DEFAULT '',
            updated_by VARCHAR(50) DEFAULT NULL,
            updated_time DATETIME NOT NULL,
            created_by VARCHAR(50) DEFAULT NULL,
            created_time DATETIME NOT NULL,
            INDEX idx_babies_family_id (family_id),
            CONSTRAINT fk_babies_family FOREIGN KEY (family_id) REFERENCES families(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS baby_events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            family_id INT NOT NULL,
            baby_id INT NOT NULL,
            user_id INT NOT NULL,
            event_type VARCHAR(20) NOT NULL,
            amount FLOAT NULL,
            unit VARCHAR(20) NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NULL,
            note VARCHAR(255) NOT NULL DEFAULT '',
            updated_by VARCHAR(50) DEFAULT NULL,
            updated_time DATETIME NOT NULL,
            created_by VARCHAR(50) DEFAULT NULL,
            created_time DATETIME NOT NULL,
            INDEX idx_events_family_id (family_id),
            INDEX idx_events_baby_id (baby_id),
            INDEX idx_events_event_type (event_type),
            CONSTRAINT fk_events_family FOREIGN KEY (family_id) REFERENCES families(id),
            CONSTRAINT fk_events_baby FOREIGN KEY (baby_id) REFERENCES babies(id),
            CONSTRAINT fk_events_user FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS baby_photos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            family_id INT NOT NULL,
            baby_id INT NOT NULL,
            user_id INT NOT NULL,
            image_url VARCHAR(500) NOT NULL,
            caption VARCHAR(255) NOT NULL DEFAULT '',
            taken_on DATE NULL,
            updated_by VARCHAR(50) DEFAULT NULL,
            updated_time DATETIME NOT NULL,
            created_by VARCHAR(50) DEFAULT NULL,
            created_time DATETIME NOT NULL,
            INDEX idx_photos_family_id (family_id),
            INDEX idx_photos_baby_id (baby_id),
            CONSTRAINT fk_photos_family FOREIGN KEY (family_id) REFERENCES families(id),
            CONSTRAINT fk_photos_baby FOREIGN KEY (baby_id) REFERENCES babies(id),
            CONSTRAINT fk_photos_user FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS baby_measurements (
            id INT AUTO_INCREMENT PRIMARY KEY,
            family_id INT NOT NULL,
            baby_id INT NOT NULL,
            user_id INT NOT NULL,
            recorded_on DATE NOT NULL,
            weight_kg FLOAT NULL,
            height_cm FLOAT NULL,
            head_circumference_cm FLOAT NULL,
            note VARCHAR(255) NOT NULL DEFAULT '',
            updated_by VARCHAR(50) DEFAULT NULL,
            updated_time DATETIME NOT NULL,
            created_by VARCHAR(50) DEFAULT NULL,
            created_time DATETIME NOT NULL,
            INDEX idx_measurements_family_id (family_id),
            INDEX idx_measurements_baby_id (baby_id),
            CONSTRAINT fk_measurements_family FOREIGN KEY (family_id) REFERENCES families(id),
            CONSTRAINT fk_measurements_baby FOREIGN KEY (baby_id) REFERENCES babies(id),
            CONSTRAINT fk_measurements_user FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS vaccine_reminders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            family_id INT NOT NULL,
            baby_id INT NOT NULL,
            title VARCHAR(120) NOT NULL,
            due_date DATE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            note VARCHAR(255) NOT NULL DEFAULT '',
            updated_by VARCHAR(50) DEFAULT NULL,
            updated_time DATETIME NOT NULL,
            created_by VARCHAR(50) DEFAULT NULL,
            created_time DATETIME NOT NULL,
            INDEX idx_vaccine_family_id (family_id),
            INDEX idx_vaccine_baby_id (baby_id),
            CONSTRAINT fk_vaccine_family FOREIGN KEY (family_id) REFERENCES families(id),
            CONSTRAINT fk_vaccine_baby FOREIGN KEY (baby_id) REFERENCES babies(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS password_reset_codes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            code VARCHAR(6) NOT NULL,
            expires_at DATETIME NOT NULL,
            used_time DATETIME NULL,
            updated_by VARCHAR(50) DEFAULT NULL,
            updated_time DATETIME NOT NULL,
            created_by VARCHAR(50) DEFAULT NULL,
            created_time DATETIME NOT NULL,
            INDEX idx_reset_user_id (user_id),
            INDEX idx_reset_code (code),
            CONSTRAINT fk_reset_user FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    ]

    migration_statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30) NULL AFTER full_name",
        "ALTER TABLE users MODIFY COLUMN email VARCHAR(120) NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_by VARCHAR(50) DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_by VARCHAR(50) DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD UNIQUE INDEX idx_users_phone (phone)",
        "ALTER TABLE users ADD UNIQUE INDEX idx_users_email (email)",
        "ALTER TABLE users MODIFY COLUMN phone VARCHAR(30) NOT NULL",
        "ALTER TABLE password_reset_codes ADD COLUMN IF NOT EXISTS used_time DATETIME NULL",
        "ALTER TABLE password_reset_codes ADD COLUMN IF NOT EXISTS updated_by VARCHAR(50) DEFAULT NULL",
        "ALTER TABLE password_reset_codes ADD COLUMN IF NOT EXISTS updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE password_reset_codes ADD COLUMN IF NOT EXISTS created_by VARCHAR(50) DEFAULT NULL",
        "ALTER TABLE password_reset_codes ADD COLUMN IF NOT EXISTS created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    ]

    connection = get_connection(with_database=True)
    try:
        with connection.cursor() as cursor:
            for statement in schema_statements:
                cursor.execute(statement)
            for statement in migration_statements:
                try:
                    cursor.execute(statement)
                except Exception:
                    # Keep migrations idempotent across different MySQL versions/index states.
                    pass
        connection.commit()
    finally:
        connection.close()
