"""
database.py — Couche d'accès SQLite pour PC Monitor.

Tables :
    users
    devices
    device_tokens
    metrics
    alerts
    commands
    settings
    pending_agent_commands
    emergency_attempts
    audio_commands
"""

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

import config

_local = threading.local()
_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# CONNEXION SQLITE
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """Retourne une connexion SQLite propre au thread courant."""

    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(
            config.DB_PATH,
            check_same_thread=False,
            timeout=30
        )

        conn.row_factory = sqlite3.Row

        conn.execute(
            "PRAGMA foreign_keys = ON"
        )

        conn.execute(
            "PRAGMA journal_mode = WAL"
        )

        _local.conn = conn

    return _local.conn


@contextmanager
def cursor():

    conn = get_connection()
    cur = conn.cursor()

    try:
        yield cur
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()


# ---------------------------------------------------------------------------
# INITIALISATION
# ---------------------------------------------------------------------------

def init_db():
    """Crée les tables si elles n'existent pas déjà."""

    with cursor() as cur:

        # ---------------------------------------------------------------
        # USERS
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)

        # ---------------------------------------------------------------
        # DEVICES
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                hostname TEXT,
                os_name TEXT,
                os_version TEXT,
                architecture TEXT,
                mac_address TEXT,
                last_ip TEXT,
                first_seen REAL,
                last_seen REAL,
                status TEXT DEFAULT 'offline',
                wol_enabled INTEGER DEFAULT 1,
                autostart_enabled INTEGER DEFAULT 0,
                revoked INTEGER DEFAULT 0
            )
        """)

        # ---------------------------------------------------------------
        # DEVICE TOKENS
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS device_tokens (
                device_id TEXT PRIMARY KEY,
                token TEXT UNIQUE NOT NULL,
                created_at REAL NOT NULL,
                revoked INTEGER DEFAULT 0,
                FOREIGN KEY (device_id)
                    REFERENCES devices(id)
                    ON DELETE CASCADE
            )
        """)

        # ---------------------------------------------------------------
        # METRICS
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                cpu_percent REAL,
                ram_percent REAL,
                disk_percent REAL,
                battery_percent REAL,
                payload TEXT,
                FOREIGN KEY (device_id)
                    REFERENCES devices(id)
                    ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_device_ts
            ON metrics(device_id, timestamp)
        """)

        # ---------------------------------------------------------------
        # ALERTS
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                device_name TEXT,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                value REAL,
                timestamp REAL NOT NULL,
                acknowledged INTEGER DEFAULT 0,
                FOREIGN KEY (device_id)
                    REFERENCES devices(id)
                    ON DELETE CASCADE
            )
        """)

        # ---------------------------------------------------------------
        # COMMANDS
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                device_name TEXT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                result_message TEXT,
                username TEXT,
                timestamp REAL NOT NULL,
                FOREIGN KEY (device_id)
                    REFERENCES devices(id)
                    ON DELETE CASCADE
            )
        """)

        # ---------------------------------------------------------------
        # SETTINGS
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # ---------------------------------------------------------------
        # COMMANDES AGENT
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_agent_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                command_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                created_at REAL NOT NULL,
                delivered INTEGER DEFAULT 0,
                FOREIGN KEY (device_id)
                    REFERENCES devices(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (command_id)
                    REFERENCES commands(id)
                    ON DELETE CASCADE
            )
        """)

        # ---------------------------------------------------------------
        # ANTI-BRUTEFORCE URGENCE
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS emergency_attempts (
                username TEXT PRIMARY KEY,
                failed_count INTEGER DEFAULT 0,
                locked_until REAL DEFAULT 0
            )
        """)

        # ---------------------------------------------------------------
        # AUDIO COMMANDS
        # ---------------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS audio_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                created_at REAL NOT NULL,
                played INTEGER DEFAULT 0,
                FOREIGN KEY (device_id)
                    REFERENCES devices(id)
                    ON DELETE CASCADE
            )
        """)

    _seed_default_settings()


# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------

def _seed_default_settings():

    defaults = {
        "server_name": config.SERVER_NAME,
        "collect_interval": str(
            config.AGENT_INTERVAL_SECONDS
        ),
        "port": str(
            config.SERVER_PORT
        ),
        "cpu_threshold": str(
            config.DEFAULT_CPU_THRESHOLD
        ),
        "ram_threshold": str(
            config.DEFAULT_RAM_THRESHOLD
        ),
        "disk_threshold": str(
            config.DEFAULT_DISK_THRESHOLD
        ),
        "battery_threshold": str(
            config.DEFAULT_BATTERY_THRESHOLD
        ),
    }

    with cursor() as cur:

        for key, value in defaults.items():

            cur.execute(
                """
                INSERT OR IGNORE INTO settings
                (key, value)
                VALUES (?, ?)
                """,
                (key, value)
            )


def get_setting(key: str, default=None):

    with cursor() as cur:

        cur.execute(
            """
            SELECT value
            FROM settings
            WHERE key = ?
            """,
            (key,)
        )

        row = cur.fetchone()

        return row["value"] if row else default


def set_setting(key: str, value):

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (key, str(value))
        )


def get_all_settings() -> dict:

    with cursor() as cur:

        cur.execute(
            "SELECT key, value FROM settings"
        )

        return {
            row["key"]: row["value"]
            for row in cur.fetchall()
        }


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------

def create_user(username: str, password_hash: str):

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO users
            (username, password_hash, created_at)
            VALUES (?, ?, ?)
            """,
            (
                username,
                password_hash,
                time.time()
            )
        )


def get_user_by_username(username: str):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        )

        return cur.fetchone()


def any_user_exists() -> bool:

    with cursor() as cur:

        cur.execute(
            """
            SELECT COUNT(*) AS c
            FROM users
            """
        )

        return cur.fetchone()["c"] > 0


# ---------------------------------------------------------------------------
# DEVICES
# ---------------------------------------------------------------------------

def upsert_device(
    device_id,
    name,
    hostname,
    os_name,
    os_version,
    architecture,
    mac_address,
    last_ip
):

    now = time.time()

    with cursor() as cur:

        cur.execute(
            """
            SELECT id
            FROM devices
            WHERE id = ?
            """,
            (device_id,)
        )

        exists = cur.fetchone()

        if exists:

            cur.execute(
                """
                UPDATE devices
                SET
                    hostname = ?,
                    os_name = ?,
                    os_version = ?,
                    architecture = ?,
                    mac_address = ?,
                    last_ip = ?,
                    last_seen = ?,
                    status = 'online'
                WHERE id = ?
                """,
                (
                    hostname,
                    os_name,
                    os_version,
                    architecture,
                    mac_address,
                    last_ip,
                    now,
                    device_id
                )
            )

        else:

            cur.execute(
                """
                INSERT INTO devices (
                    id,
                    name,
                    hostname,
                    os_name,
                    os_version,
                    architecture,
                    mac_address,
                    last_ip,
                    first_seen,
                    last_seen,
                    status
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, 'online'
                )
                """,
                (
                    device_id,
                    name,
                    hostname,
                    os_name,
                    os_version,
                    architecture,
                    mac_address,
                    last_ip,
                    now,
                    now
                )
            )


def touch_device_seen(device_id):

    with cursor() as cur:

        cur.execute(
            """
            UPDATE devices
            SET last_seen = ?,
                status = 'online'
            WHERE id = ?
            """,
            (
                time.time(),
                device_id
            )
        )


def get_device(device_id):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM devices
            WHERE id = ?
            """,
            (device_id,)
        )

        return cur.fetchone()


def get_all_devices():

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM devices
            ORDER BY name COLLATE NOCASE
            """
        )

        return cur.fetchall()


def rename_device(device_id, new_name):

    with cursor() as cur:

        cur.execute(
            """
            UPDATE devices
            SET name = ?
            WHERE id = ?
            """,
            (
                new_name,
                device_id
            )
        )


def set_device_status(device_id, status):

    with cursor() as cur:

        cur.execute(
            """
            UPDATE devices
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                device_id
            )
        )


def set_device_wol(device_id, enabled: bool):

    with cursor() as cur:

        cur.execute(
            """
            UPDATE devices
            SET wol_enabled = ?
            WHERE id = ?
            """,
            (
                1 if enabled else 0,
                device_id
            )
        )


def set_device_autostart(device_id, enabled: bool):

    with cursor() as cur:

        cur.execute(
            """
            UPDATE devices
            SET autostart_enabled = ?
            WHERE id = ?
            """,
            (
                1 if enabled else 0,
                device_id
            )
        )


def delete_device(device_id):

    with cursor() as cur:

        cur.execute(
            """
            DELETE FROM devices
            WHERE id = ?
            """,
            (device_id,)
        )


def mark_stale_devices_offline(threshold_seconds):

    now = time.time()
    cutoff = now - threshold_seconds

    with cursor() as cur:

        cur.execute(
            """
            SELECT id
            FROM devices
            WHERE status = 'online'
            AND last_seen < ?
            """,
            (cutoff,)
        )

        newly_offline = [
            row["id"]
            for row in cur.fetchall()
        ]

        if newly_offline:

            cur.executemany(
                """
                UPDATE devices
                SET status = 'offline'
                WHERE id = ?
                """,
                [
                    (device_id,)
                    for device_id in newly_offline
                ]
            )

    return newly_offline


# ---------------------------------------------------------------------------
# TOKENS
# ---------------------------------------------------------------------------

def create_device_token(device_id) -> str:

    token = (
        uuid.uuid4().hex +
        uuid.uuid4().hex
    )

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO device_tokens
            (device_id, token, created_at, revoked)
            VALUES (?, ?, ?, 0)

            ON CONFLICT(device_id)
            DO UPDATE SET
                token = excluded.token,
                revoked = 0
            """,
            (
                device_id,
                token,
                time.time()
            )
        )

    return token


def get_token_for_device(device_id):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM device_tokens
            WHERE device_id = ?
            """,
            (device_id,)
        )

        return cur.fetchone()


def validate_device_token(
    device_id,
    token
) -> bool:

    with cursor() as cur:

        cur.execute(
            """
            SELECT
                dt.revoked AS token_revoked,
                d.revoked AS device_revoked
            FROM device_tokens dt

            JOIN devices d
                ON d.id = dt.device_id

            WHERE
                dt.device_id = ?
                AND dt.token = ?
            """,
            (
                device_id,
                token
            )
        )

        row = cur.fetchone()

        if not row:
            return False

        return (
            row["token_revoked"] == 0
            and row["device_revoked"] == 0
        )


def revoke_device_token(device_id):

    with cursor() as cur:

        cur.execute(
            """
            UPDATE device_tokens
            SET revoked = 1
            WHERE device_id = ?
            """,
            (device_id,)
        )

        cur.execute(
            """
            UPDATE devices
            SET revoked = 1
            WHERE id = ?
            """,
            (device_id,)
        )


# ---------------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------------

def insert_metric(
    device_id,
    cpu,
    ram,
    disk,
    battery,
    payload: dict
):

    now = time.time()

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO metrics (
                device_id,
                timestamp,
                cpu_percent,
                ram_percent,
                disk_percent,
                battery_percent,
                payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                now,
                cpu,
                ram,
                disk,
                battery,
                json.dumps(payload)
            )
        )

        cur.execute(
            """
            SELECT COUNT(*) AS c
            FROM metrics
            WHERE device_id = ?
            """,
            (device_id,)
        )

        count = cur.fetchone()["c"]

        if count > config.MAX_METRICS_PER_DEVICE:

            excess = (
                count -
                config.MAX_METRICS_PER_DEVICE
            )

            cur.execute(
                """
                DELETE FROM metrics
                WHERE id IN (
                    SELECT id
                    FROM metrics
                    WHERE device_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
                """,
                (
                    device_id,
                    excess
                )
            )


def get_latest_metric(device_id):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM metrics
            WHERE device_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (device_id,)
        )

        return cur.fetchone()


def get_metric_history(
    device_id,
    limit=60
):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM metrics
            WHERE device_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (
                device_id,
                limit
            )
        )

        rows = cur.fetchall()

        return list(reversed(rows))


# ---------------------------------------------------------------------------
# ALERTS
# ---------------------------------------------------------------------------

def insert_alert(
    device_id,
    device_name,
    alert_type,
    message,
    value=None
):

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO alerts (
                device_id,
                device_name,
                type,
                message,
                value,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                device_name,
                alert_type,
                message,
                value,
                time.time()
            )
        )

        cur.execute(
            """
            SELECT COUNT(*) AS c
            FROM alerts
            """
        )

        count = cur.fetchone()["c"]

        if count > config.MAX_ALERT_HISTORY:

            excess = (
                count -
                config.MAX_ALERT_HISTORY
            )

            cur.execute(
                """
                DELETE FROM alerts
                WHERE id IN (
                    SELECT id
                    FROM alerts
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
                """,
                (excess,)
            )


def get_recent_alert(
    device_id,
    alert_type,
    within_seconds=60
):

    cutoff = (
        time.time() -
        within_seconds
    )

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM alerts
            WHERE
                device_id = ?
                AND type = ?
                AND timestamp > ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (
                device_id,
                alert_type,
                cutoff
            )
        )

        return cur.fetchone()


def get_alerts(limit=100):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM alerts
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,)
        )

        return cur.fetchall()


# ---------------------------------------------------------------------------
# COMMANDS
# ---------------------------------------------------------------------------

def insert_command(
    device_id,
    device_name,
    action,
    status,
    username,
    result_message=""
):

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO commands (
                device_id,
                device_name,
                action,
                status,
                result_message,
                username,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                device_name,
                action,
                status,
                result_message,
                username,
                time.time()
            )
        )

        command_id = cur.lastrowid

        cur.execute(
            """
            SELECT COUNT(*) AS c
            FROM commands
            """
        )

        count = cur.fetchone()["c"]

        if count > config.MAX_COMMAND_HISTORY:

            excess = (
                count -
                config.MAX_COMMAND_HISTORY
            )

            cur.execute(
                """
                DELETE FROM commands
                WHERE id IN (
                    SELECT id
                    FROM commands
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
                """,
                (excess,)
            )

        return command_id


def update_command_status(
    command_id,
    status,
    result_message=""
):

    with cursor() as cur:

        cur.execute(
            """
            UPDATE commands
            SET
                status = ?,
                result_message = ?
            WHERE id = ?
            """,
            (
                status,
                result_message,
                command_id
            )
        )


def get_command_history(limit=100):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM commands
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,)
        )

        return cur.fetchall()


def queue_agent_command(
    device_id,
    command_id,
    action
):

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO pending_agent_commands (
                device_id,
                command_id,
                action,
                created_at,
                delivered
            )
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                device_id,
                command_id,
                action,
                time.time()
            )
        )


def pop_pending_commands_for_device(
    device_id
):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM pending_agent_commands
            WHERE
                device_id = ?
                AND delivered = 0
            ORDER BY created_at ASC
            """,
            (device_id,)
        )

        rows = cur.fetchall()

        if rows:

            ids = [
                row["id"]
                for row in rows
            ]

            cur.executemany(
                """
                UPDATE pending_agent_commands
                SET delivered = 1
                WHERE id = ?
                """,
                [
                    (command_id,)
                    for command_id in ids
                ]
            )

        return rows


# ---------------------------------------------------------------------------
# MODE URGENCE — ANTI-BRUTEFORCE
# ---------------------------------------------------------------------------

def get_emergency_lock(username):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM emergency_attempts
            WHERE username = ?
            """,
            (username,)
        )

        return cur.fetchone()


def register_emergency_failure(username):

    now = time.time()

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM emergency_attempts
            WHERE username = ?
            """,
            (username,)
        )

        row = cur.fetchone()

        if row:

            failed = (
                row["failed_count"] +
                1
            )

            locked_until = (
                row["locked_until"]
            )

            if (
                failed >=
                config.EMERGENCY_MAX_ATTEMPTS
            ):

                locked_until = (
                    now +
                    config.EMERGENCY_LOCKOUT_SECONDS
                )

                failed = 0

            cur.execute(
                """
                UPDATE emergency_attempts
                SET
                    failed_count = ?,
                    locked_until = ?
                WHERE username = ?
                """,
                (
                    failed,
                    locked_until,
                    username
                )
            )

        else:

            cur.execute(
                """
                INSERT INTO emergency_attempts (
                    username,
                    failed_count,
                    locked_until
                )
                VALUES (?, 1, 0)
                """,
                (username,)
            )


def reset_emergency_failures(username):

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO emergency_attempts (
                username,
                failed_count,
                locked_until
            )
            VALUES (?, 0, 0)

            ON CONFLICT(username)
            DO UPDATE SET
                failed_count = 0,
                locked_until = 0
            """,
            (username,)
        )


# ---------------------------------------------------------------------------
# AUDIO COMMANDS
# ---------------------------------------------------------------------------

def create_audio_command(
    device_id,
    filename,
    filepath
):

    with cursor() as cur:

        cur.execute(
            """
            INSERT INTO audio_commands (
                device_id,
                filename,
                filepath,
                created_at,
                played
            )
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                device_id,
                filename,
                filepath,
                time.time()
            )
        )

        return cur.lastrowid


def get_pending_audio_commands(
    device_id
):

    with cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM audio_commands
            WHERE
                device_id = ?
                AND played = 0
            ORDER BY created_at ASC
            """,
            (device_id,)
        )

        rows = cur.fetchall()

        if rows:

            cur.executemany(
                """
                UPDATE audio_commands
                SET played = 1
                WHERE id = ?
                """,
                [
                    (row["id"],)
                    for row in rows
                ]
            )

        return rows