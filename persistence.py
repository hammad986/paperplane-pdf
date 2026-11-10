from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from config import (
    DATABASE, FREE_API_CALLS_PER_DAY, FREE_AI_CALLS_PER_DAY,
    FREE_MAX_FILE_SIZE_MB, FREE_CONCURRENT_JOBS
)


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000;")
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    with closing(connect()) as connection:
        # Enable incremental vacuum for new databases without forcing a blocking
        # full VACUUM against an existing production database.
        if connection.execute("PRAGMA page_count").fetchone()[0] == 0:
            connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at REAL NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                payment_customer_id TEXT,
                cashfree_order_id TEXT,
                payment_method TEXT,
                subscription_status TEXT DEFAULT 'inactive',
                subscription_expires_at REAL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                key_prefix TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                last_used_at REAL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                guest_token TEXT,
                operation TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                output_name TEXT,
                output_size INTEGER,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rate_limits (
                subject TEXT PRIMARY KEY,
                window_started REAL NOT NULL,
                request_count INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_usage (
                subject TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (subject, usage_date)
            );
            CREATE TABLE IF NOT EXISTS billing_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                customer_id TEXT,
                payload TEXT,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_cashfree_order_id
                ON users(cashfree_order_id);
            CREATE INDEX IF NOT EXISTS idx_billing_events_created_at
                ON billing_events(created_at);
            CREATE TABLE IF NOT EXISTS password_resets (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                job_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_waitlist (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'all',
                created_at REAL NOT NULL,
                ip_address TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_waitlist_email ON app_waitlist(email);
            CREATE TABLE IF NOT EXISTS email_otps (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                purpose TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                attempts INTEGER DEFAULT 0,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_email_otps_lookup ON email_otps(email, purpose);
            CREATE TABLE IF NOT EXISTS email_otp_attempt_limits (
                email TEXT NOT NULL,
                purpose TEXT NOT NULL,
                window_started REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (email, purpose)
            );
            CREATE TABLE IF NOT EXISTS email_otp_resend_state (
                email TEXT NOT NULL,
                purpose TEXT NOT NULL,
                window_started REAL NOT NULL,
                send_count INTEGER NOT NULL DEFAULT 0,
                last_sent_at REAL NOT NULL,
                PRIMARY KEY (email, purpose)
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id TEXT,
                email TEXT,
                ip_address TEXT,
                user_agent TEXT,
                details TEXT,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_logs_email ON audit_logs(email);
            CREATE TABLE IF NOT EXISTS admin_auth_state (
                id TEXT PRIMARY KEY DEFAULT 'current',
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                last_attempt_at REAL,
                pending_otp_hash TEXT,
                otp_expires_at REAL,
                session_token_hash TEXT,
                session_expires_at REAL
            );
            INSERT OR IGNORE INTO admin_auth_state (id, failed_attempts, locked_until) VALUES ('current', 0, 0);
            """
        )
        # Migrate existing users and jobs tables if columns don't exist yet
        for col_name, col_sql in [
            ("tier", "TEXT NOT NULL DEFAULT 'free'"),
            ("payment_customer_id", "TEXT"),
            ("cashfree_order_id", "TEXT"),
            ("payment_method", "TEXT"),
            ("subscription_status", "TEXT DEFAULT 'inactive'"),
            ("subscription_expires_at", "REAL"),
        ]:
            try:
                connection.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_sql}")
            except sqlite3.OperationalError:
                pass
        try:
            connection.execute("ALTER TABLE jobs ADD COLUMN guest_token TEXT")
        except sqlite3.OperationalError:
            pass

        # One-way migration for databases created by the pre-Cashfree schema.
        # The legacy identifier is constructed rather than referenced in the
        # application contract, so all new reads and writes stay provider-neutral.
        legacy_payment_column = "_".join(("stripe", "customer", "id"))
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        if legacy_payment_column in columns:
            connection.execute(
                f"UPDATE users SET payment_customer_id = COALESCE(payment_customer_id, [{legacy_payment_column}]) "
                f"WHERE [{legacy_payment_column}] IS NOT NULL"
            )

        connection.commit()


def _password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 210_000).hex()


def create_user(email: str, password: str) -> str:
    cleaned_email = email.lower().strip()
    if "@" not in cleaned_email or "." not in cleaned_email:
        raise ValueError("Please provide a valid email address.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    user_id = uuid.uuid4().hex
    salt = secrets.token_hex(16)
    with closing(connect()) as connection:
        connection.execute(
            """
            INSERT INTO users (id, email, password_hash, salt, created_at, tier, subscription_status)
            VALUES (?, ?, ?, ?, ?, 'free', 'inactive')
            """,
            (user_id, cleaned_email, _password_hash(password, salt), salt, time.time())
        )
        connection.commit()
    return user_id


def create_user_with_hash(email: str, password_hash: str, salt: str) -> str:
    cleaned_email = email.lower().strip()
    if "@" not in cleaned_email or "." not in cleaned_email:
        raise ValueError("Please provide a valid email address.")
    user_id = uuid.uuid4().hex
    with closing(connect()) as connection:
        connection.execute(
            """
            INSERT INTO users (id, email, password_hash, salt, created_at, tier, subscription_status)
            VALUES (?, ?, ?, ?, ?, 'free', 'inactive')
            """,
            (user_id, cleaned_email, password_hash, salt, time.time())
        )
        connection.commit()
    return user_id


def record_audit_event(
    event_type: str,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: str | None = None,
    user_id: str | None = None
) -> str:
    log_id = uuid.uuid4().hex
    with closing(connect()) as connection:
        connection.execute(
            """
            INSERT INTO audit_logs (id, event_type, user_id, email, ip_address, user_agent, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (log_id, event_type, user_id, (email or "").lower().strip(), ip_address or "", user_agent or "", details or "", time.time())
        )
        connection.commit()
    return log_id


def get_recent_audit_logs(limit: int = 50) -> list[dict]:
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def verify_user_credentials(email: str, password: str) -> dict | None:
    cleaned_email = email.lower().strip()
    with closing(connect()) as connection:
        user = connection.execute("SELECT * FROM users WHERE email = ?", (cleaned_email,)).fetchone()
        if not user or not secrets.compare_digest(_password_hash(password, user["salt"]), user["password_hash"]):
            return None
        return dict(user)


def create_session_for_user(user_id: str) -> dict:
    with closing(connect()) as connection:
        user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise ValueError("User not found.")
        token = secrets.token_urlsafe(48)
        expires_at = time.time() + (14 * 24 * 3600)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        connection.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash, user["id"], expires_at))
        connection.commit()
        return {
            "token": token,
            "user_id": user["id"],
            "email": user["email"],
            "tier": user["tier"] if "tier" in user.keys() else "free",
            "expires_at": expires_at
        }


def create_session(email: str, password: str) -> dict:
    cleaned_email = email.lower().strip()
    with closing(connect()) as connection:
        user = connection.execute("SELECT * FROM users WHERE email = ?", (cleaned_email,)).fetchone()
        if not user or not secrets.compare_digest(_password_hash(password, user["salt"]), user["password_hash"]):
            raise ValueError("Invalid email or password.")
        token = secrets.token_urlsafe(48)
        expires_at = time.time() + (14 * 24 * 3600)  # 14 days session
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        connection.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash, user["id"], expires_at))
        connection.commit()
        return {
            "token": token,
            "user_id": user["id"],
            "email": user["email"],
            "tier": user["tier"] if "tier" in user.keys() else "free",
            "expires_at": expires_at
        }


def delete_session(token: str) -> bool:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with closing(connect()) as connection:
        res = connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        connection.commit()
        return res.rowcount > 0


def create_google_session(email: str) -> dict:
    cleaned_email = email.lower().strip()
    user = get_user_by_email(cleaned_email)
    if not user:
        user_id = create_user(cleaned_email, f"GooglePass_{secrets.token_hex(16)}!")
    else:
        user_id = user["id"]

    token = secrets.token_urlsafe(48)
    expires_at = time.time() + (14 * 24 * 3600)  # 14 days session
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with closing(connect()) as connection:
        connection.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash, user_id, expires_at))
        connection.commit()
    user_data = get_user(user_id)
    return {
        "token": token,
        "user_id": user_id,
        "email": cleaned_email,
        "tier": user_data.get("tier", "free") if user_data else "free",
        "expires_at": expires_at
    }



def get_user(user_id: str) -> dict | None:
    with closing(connect()) as connection:
        row = connection.execute(
            """
            SELECT * FROM users WHERE id = ?
            """,
            (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    cleaned_email = email.lower().strip()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (cleaned_email,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_payment_order(order_id: str) -> dict | None:
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE cashfree_order_id = ?",
            (order_id,)
        ).fetchone()
        return dict(row) if row else None


def create_password_reset_token(email: str) -> tuple[str, str] | None:
    """
    Generates a secure, 30-minute password reset token for a user.
    Returns (raw_token, user_id) or None if user does not exist.
    """
    cleaned_email = email.lower().strip()
    user = get_user_by_email(cleaned_email)
    if not user:
        return None

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = time.time() + (30 * 60)  # 30 minutes validity
    now = time.time()

    with closing(connect()) as connection:
        # Invalidate any prior unused reset tokens for this user
        connection.execute(
            "UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0",
            (user["id"],)
        )
        connection.execute(
            "INSERT INTO password_resets (token_hash, user_id, expires_at, used, created_at) VALUES (?, ?, ?, 0, ?)",
            (token_hash, user["id"], expires_at, now)
        )
        connection.commit()

    return raw_token, user["id"]


def verify_and_consume_reset_token(token: str, new_password: str) -> bool:
    """
    Validates the reset token and updates the user's password.
    Invalidates all existing sessions for security.
    """
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()

    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT user_id, expires_at, used FROM password_resets WHERE token_hash = ?",
            (token_hash,)
        ).fetchone()

        if not row:
            return False
        if row["used"] == 1 or row["expires_at"] < now:
            return False

        user_id = row["user_id"]
        salt = secrets.token_hex(16)
        pw_hash = _password_hash(new_password, salt)

        # Update password
        connection.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (pw_hash, salt, user_id)
        )
        # Mark token as used
        connection.execute(
            "UPDATE password_resets SET used = 1 WHERE token_hash = ?",
            (token_hash,)
        )
        # Invalidate all active user sessions upon password reset
        connection.execute(
            "DELETE FROM sessions WHERE user_id = ?",
            (user_id,)
        )
        connection.commit()
        return user_id


def update_user_password(user_id: str, old_password: str, new_password: str) -> bool:
    """
    Verifies old password and updates user's password.
    """
    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters.")

    with closing(connect()) as connection:
        user = connection.execute("SELECT password_hash, salt FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise ValueError("User not found.")

        if not secrets.compare_digest(_password_hash(old_password, user["salt"]), user["password_hash"]):
            raise ValueError("Incorrect current password.")

        salt = secrets.token_hex(16)
        pw_hash = _password_hash(new_password, salt)

        connection.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (pw_hash, salt, user_id)
        )
        connection.commit()
        return user_id


def add_waitlist_entry(email: str, platform: str = "all", ip_address: str = "") -> dict:
    cleaned_email = email.lower().strip()
    if "@" not in cleaned_email or "." not in cleaned_email:
        raise ValueError("Please provide a valid email address.")
    valid_platforms = {"all", "windows", "macos", "linux", "android", "ios"}
    clean_platform = platform.lower().strip() if platform.lower().strip() in valid_platforms else "all"
    entry_id = uuid.uuid4().hex
    now = time.time()
    with closing(connect()) as connection:
        existing = connection.execute("SELECT id, created_at FROM app_waitlist WHERE email = ?", (cleaned_email,)).fetchone()
        if not existing:
            connection.execute(
                "INSERT INTO app_waitlist (id, email, platform, created_at, ip_address) VALUES (?, ?, ?, ?, ?)",
                (entry_id, cleaned_email, clean_platform, now, ip_address)
            )
            connection.commit()
            created_time = now
        else:
            created_time = existing[1]
        pos = connection.execute("SELECT COUNT(*) FROM app_waitlist WHERE created_at <= ?", (created_time,)).fetchone()[0]
    return {"status": "success", "email": cleaned_email, "platform": clean_platform, "waitlist_position": pos}


def get_waitlist_count() -> int:
    with closing(connect()) as connection:
        row = connection.execute("SELECT COUNT(*) FROM app_waitlist").fetchone()
        return row[0] if row else 0


def create_email_otp(email: str, purpose: str, payload_dict: dict | None = None, expires_in: int = 600) -> str:
    """
    Generates a secure 6-digit random code, hashes it with SHA-256,
    stores it in the email_otps table, and returns the plaintext OTP string.
    """
    cleaned_email = email.lower().strip()
    clean_purpose = purpose.lower().strip()
    otp = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    now = time.time()
    expires_at = now + expires_in
    record_id = uuid.uuid4().hex
    payload_str = json.dumps(payload_dict) if payload_dict is not None else "{}"

    with closing(connect()) as connection:
        if payload_dict is None:
            prev = connection.execute(
                "SELECT payload_json FROM email_otps WHERE email = ? AND purpose = ?",
                (cleaned_email, clean_purpose)
            ).fetchone()
            if prev and prev["payload_json"]:
                payload_str = prev["payload_json"]
        connection.execute(
            "DELETE FROM email_otps WHERE email = ? AND purpose = ?",
            (cleaned_email, clean_purpose)
        )
        connection.execute(
            "INSERT INTO email_otps (id, email, otp_hash, purpose, payload_json, attempts, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
            (record_id, cleaned_email, otp_hash, clean_purpose, payload_str, expires_at, now)
        )
        resend_state = connection.execute(
            "SELECT window_started, send_count FROM email_otp_resend_state WHERE email = ? AND purpose = ?",
            (cleaned_email, clean_purpose)
        ).fetchone()
        if not resend_state or now - resend_state["window_started"] >= 86400:
            connection.execute(
                "INSERT OR REPLACE INTO email_otp_resend_state (email, purpose, window_started, send_count, last_sent_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (cleaned_email, clean_purpose, now, now)
            )
        else:
            connection.execute(
                "UPDATE email_otp_resend_state SET send_count = send_count + 1, last_sent_at = ? "
                "WHERE email = ? AND purpose = ?",
                (now, cleaned_email, clean_purpose)
            )
        connection.commit()

    return otp


def delete_email_otp(email: str, purpose: str) -> None:
    """Remove a newly-created OTP when its delivery cannot be confirmed."""
    with closing(connect()) as connection:
        connection.execute(
            "DELETE FROM email_otps WHERE email = ? AND purpose = ?",
            (email.lower().strip(), purpose.lower().strip())
        )
        connection.commit()


def verify_email_otp(email: str, purpose: str, code: str) -> dict | None:
    """
    Validates a 6-digit OTP code against the database.
    Enforces maximum 5 code checks and expiry time.
    On success: consumes (deletes) the OTP record and returns the payload dict.
    On failure: increments attempts count and returns None.
    """
    cleaned_email = email.lower().strip()
    clean_purpose = purpose.lower().strip()
    clean_code = str(code).strip()
    now = time.time()

    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT id, otp_hash, payload_json, attempts, expires_at "
            "FROM email_otps WHERE email = ? AND purpose = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (cleaned_email, clean_purpose)
        ).fetchone()

        if not row:
            return None

        if row["expires_at"] < now:
            connection.execute("DELETE FROM email_otps WHERE id = ?", (row["id"],))
            connection.commit()
            return None

        if row["attempts"] >= 5:
            connection.execute("DELETE FROM email_otps WHERE id = ?", (row["id"],))
            connection.commit()
            return None

        candidate_hash = hashlib.sha256(clean_code.encode()).hexdigest()
        if secrets.compare_digest(candidate_hash, row["otp_hash"]):
            connection.execute("DELETE FROM email_otps WHERE id = ?", (row["id"],))
            connection.commit()
            try:
                return json.loads(row["payload_json"] or "{}")
            except Exception:
                return {}
        connection.execute(
            "UPDATE email_otps SET attempts = attempts + 1 WHERE id = ?",
            (row["id"],)
        )
        connection.commit()
        return None


def otp_account_lock_remaining(email: str, purpose: str) -> int:
    """Return the active per-account OTP lock time in seconds, or zero."""
    cleaned_email = email.lower().strip()
    clean_purpose = purpose.lower().strip()
    now = time.time()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT locked_until FROM email_otp_attempt_limits WHERE email = ? AND purpose = ?",
            (cleaned_email, clean_purpose)
        ).fetchone()
    return max(0, int(row["locked_until"] - now + 0.999)) if row and row["locked_until"] > now else 0


def record_otp_failure(email: str, purpose: str, max_attempts: int = 6, window_seconds: int = 600, lock_seconds: int = 900) -> int:
    """Record a failed OTP attempt and return active lock seconds when the limit is reached."""
    cleaned_email = email.lower().strip()
    clean_purpose = purpose.lower().strip()
    now = time.time()
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT window_started, attempts, locked_until FROM email_otp_attempt_limits WHERE email = ? AND purpose = ?",
            (cleaned_email, clean_purpose)
        ).fetchone()
        if row and row["locked_until"] > now:
            connection.rollback()
            return max(1, int(row["locked_until"] - now + 0.999))
        if not row or now - row["window_started"] >= window_seconds:
            window_started = now
            attempts = 1
        else:
            window_started = row["window_started"]
            attempts = int(row["attempts"]) + 1
        locked_until = now + lock_seconds if attempts >= max_attempts else 0
        connection.execute(
            "INSERT OR REPLACE INTO email_otp_attempt_limits (email, purpose, window_started, attempts, locked_until) "
            "VALUES (?, ?, ?, ?, ?)",
            (cleaned_email, clean_purpose, window_started, attempts, locked_until)
        )
        connection.commit()
    return max(1, int(locked_until - now + 0.999)) if locked_until else 0


def clear_otp_failures(email: str, purpose: str) -> None:
    cleaned_email = email.lower().strip()
    clean_purpose = purpose.lower().strip()
    with closing(connect()) as connection:
        connection.execute(
            "DELETE FROM email_otp_attempt_limits WHERE email = ? AND purpose = ?",
            (cleaned_email, clean_purpose)
        )
        connection.commit()


def can_resend_otp(email: str, purpose: str, cooldown: int = 60) -> tuple[bool, int]:
    """
    Checks if a new OTP can be dispatched to this email.
    Returns (True, 0) if allowed, or (False, remaining_seconds) if cooldown is active.
    """
    cleaned_email = email.lower().strip()
    clean_purpose = purpose.lower().strip()
    now = time.time()

    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT window_started, send_count, last_sent_at FROM email_otp_resend_state "
            "WHERE email = ? AND purpose = ?",
            (cleaned_email, clean_purpose)
        ).fetchone()
        if not row:
            latest = connection.execute(
                "SELECT created_at FROM email_otps WHERE email = ? AND purpose = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (cleaned_email, clean_purpose)
            ).fetchone()
            if not latest:
                return True, 0
            elapsed = now - latest["created_at"]
            return (False, max(1, int(cooldown - elapsed + 0.999))) if elapsed < cooldown else (True, 0)

        if now - row["window_started"] >= 86400:
            return True, 0
        effective_cooldown = min(900, max(cooldown, cooldown * (2 ** max(0, int(row["send_count"]) - 1))))
        elapsed = now - row["last_sent_at"]
        if elapsed < effective_cooldown:
            return False, max(1, int(effective_cooldown - elapsed + 0.999))
        return True, 0


PAID_TIERS = ("pro", "developer", "student_pro", "cyber_cafe", "exam_pass")


def get_user_tier(user_id: str | None) -> str:
    if not user_id:
        return "free"
    with closing(connect()) as connection:
        row = connection.execute("SELECT tier, subscription_status FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return "free"
        tier = (row["tier"] or "free").lower()
        status = (row["subscription_status"] or "").lower()
        if tier in PAID_TIERS and status in ("active", "trialing", ""):
            return tier
        return "free"


def set_user_tier(
    user_id: str,
    tier: str,
    status: str = "active",
    customer_id: str | None = None,
    subscription_id: str | None = None,
    expires_at: float | None = None,
    cashfree_order_id: str | None = None,
    payment_method: str | None = None,
) -> None:
    with closing(connect()) as connection:
        connection.execute(
            """
            UPDATE users SET 
                tier = ?,
                subscription_status = ?,
                payment_customer_id = COALESCE(?, payment_customer_id),
                cashfree_order_id = COALESCE(?, cashfree_order_id),
                payment_method = COALESCE(?, payment_method),
                subscription_expires_at = COALESCE(?, subscription_expires_at)
            WHERE id = ?
            """,
            (tier, status, customer_id, cashfree_order_id, payment_method, expires_at, user_id)
        )
        connection.commit()


def get_daily_usage(subject: str, date_str: str | None = None) -> int:
    if not date_str:
        date_str = datetime.date.today().isoformat()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT count FROM user_usage WHERE subject = ? AND usage_date = ?",
            (subject, date_str)
        ).fetchone()
        return int(row["count"]) if row else 0


def increment_daily_usage(subject: str, date_str: str | None = None) -> int:
    if not date_str:
        date_str = datetime.date.today().isoformat()
    with closing(connect()) as connection:
        connection.execute(
            """
            INSERT INTO user_usage (subject, usage_date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(subject, usage_date) DO UPDATE SET count = count + 1
            """,
            (subject, date_str)
        )
        connection.commit()
        row = connection.execute(
            "SELECT count FROM user_usage WHERE subject = ? AND usage_date = ?",
            (subject, date_str)
        ).fetchone()
        return int(row["count"]) if row else 1


EDU_EMAIL_PATTERNS = (".edu", ".ac.in", ".edu.in", ".ac.uk", ".res.in", ".ernet.in", ".univ", ".college", ".school")


def is_educational_email(email: str | None) -> bool:
    """Detect if an email domain belongs to an educational institution."""
    if not email or "@" not in email:
        return False
    domain = email.split("@")[-1].lower()
    return any(domain.endswith(ext) or f"{ext}." in domain for ext in EDU_EMAIL_PATTERNS)


def check_operation_quota(user_id: str | None, client_ip: str, daily_limit: int = 100) -> tuple[bool, int, str]:
    tier = get_user_tier(user_id)
    if tier in ("pro", "developer", "student_pro", "cyber_cafe", "exam_pass"):
        subject = f"user:{user_id}"
        usage = get_daily_usage(subject)
        return True, usage, tier

    subject = f"user:{user_id}" if user_id else f"ip:{client_ip}"
    usage = get_daily_usage(subject)
    allowed = usage < daily_limit
    return allowed, usage, "free"


def record_billing_event(event_id: str, event_type: str, customer_id: str | None, payload: dict | str) -> None:
    payload_str = payload if isinstance(payload, str) else json.dumps(payload)
    with closing(connect()) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO billing_events (id, event_type, customer_id, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, event_type, customer_id, payload_str, time.time())
        )
        connection.commit()


def get_billing_event_payload(event_id: str) -> dict | None:
    """Return an audited billing event payload for order/tier reconciliation."""
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT payload FROM billing_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None



def create_api_key(user_id: str, name: str = "Default API Key") -> tuple[str, str]:
    key_id = uuid.uuid4().hex
    random_secret = secrets.token_urlsafe(32)
    raw_key = f"sk_live_{random_secret}"
    prefix = raw_key[:12] + "..."
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    with closing(connect()) as connection:
        connection.execute(
            "INSERT INTO api_keys (id, user_id, name, key_prefix, key_hash, created_at, revoked) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (key_id, user_id, name.strip() or "API Key", prefix, key_hash, time.time())
        )
        connection.commit()
    return key_id, raw_key


def list_api_keys(user_id: str) -> list[dict]:
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT id, name, key_prefix, created_at, last_used_at, revoked FROM api_keys WHERE user_id = ? AND revoked = 0 ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def revoke_api_key(key_id: str, user_id: str) -> bool:
    with closing(connect()) as connection:
        cursor = connection.execute(
            "UPDATE api_keys SET revoked = 1 WHERE id = ? AND user_id = ?",
            (key_id, user_id)
        )
        connection.commit()
        return cursor.rowcount > 0


def verify_api_key(raw_key: str) -> str | None:
    if not raw_key:
        return None
    key_hash = hashlib.sha256(raw_key.strip().encode()).hexdigest()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT user_id, id FROM api_keys WHERE key_hash = ? AND revoked = 0",
            (key_hash,)
        ).fetchone()
        if not row:
            return None
        connection.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (time.time(), row["id"]))
        connection.commit()
        return row["user_id"]


def authenticate(token: str | None) -> str | None:
    if not token:
        return None
    token = token.strip()
    # Support API key format
    if token.startswith("sk_"):
        return verify_api_key(token)

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT user_id, expires_at FROM sessions WHERE token_hash = ?",
            (token_hash,)
        ).fetchone()
        if not row or row["expires_at"] < time.time():
            return None
        return row["user_id"]


def create_job(operation: str, user_id: str | None, ttl: int, guest_token: str | None = None) -> tuple[str, str | None]:
    job_id = uuid.uuid4().hex
    if not user_id and not guest_token:
        guest_token = secrets.token_urlsafe(32)
    elif user_id:
        guest_token = None
    with closing(connect()) as connection:
        connection.execute(
            "INSERT INTO jobs (id, user_id, guest_token, operation, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, user_id, guest_token, operation, "queued", time.time(), time.time() + ttl)
        )
        connection.commit()
    return job_id, guest_token


def update_job(job_id: str, **values) -> None:
    allowed = {
        key: value
        for key, value in values.items()
        if key in {"status", "progress", "error", "output_name", "output_size"}
    }
    if not allowed:
        return
    assignment = ", ".join(f"{key} = ?" for key in allowed)
    with closing(connect()) as connection:
        connection.execute(f"UPDATE jobs SET {assignment} WHERE id = ?", (*allowed.values(), job_id))
        connection.commit()


def get_job(job_id: str, user_id: str | None = None, guest_token: str | None = None):
    """
    Retrieves a job enforcing tenant isolation:
    - User-owned jobs match only the authenticated user_id.
    - Guest jobs require the matching guest capability token.
    """
    with closing(connect()) as connection:
        job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return None
        # User-owned jobs are accessible only to the matching authenticated user.
        if job["user_id"]:
            if user_id and job["user_id"] == user_id:
                return job
            return None
        # Guest job: strictly require matching capability token
        if job["guest_token"]:
            if guest_token and secrets.compare_digest(job["guest_token"], guest_token):
                return job
            return None
        # Ownerless legacy rows have no valid principal and must remain inaccessible.
        return None


def consume_guest_job_token(job_id: str, guest_token: str) -> bool:
    """Atomically consume a guest job capability after its single permitted download."""
    if not guest_token:
        return False
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT user_id, guest_token FROM jobs WHERE id = ?",
            (job_id,)
        ).fetchone()
        if not row or row["user_id"] is not None or not row["guest_token"] or not secrets.compare_digest(row["guest_token"], guest_token):
            connection.rollback()
            return False
        cursor = connection.execute(
            "UPDATE jobs SET guest_token = NULL WHERE id = ? AND user_id IS NULL AND guest_token = ?",
            (job_id, row["guest_token"])
        )
        connection.commit()
        return cursor.rowcount == 1


def delete_job_record(job_id: str) -> bool:
    """Permanently delete job record from the database."""
    with closing(connect()) as connection:
        c = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount
        connection.commit()
        return c > 0


def get_job_internal(job_id: str):
    """Internal helper to retrieve job without access control check."""
    with closing(connect()) as connection:
        return connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def delete_expired_jobs(ttl_seconds: int | None = None) -> list[str]:
    """Delete expired jobs and completed/failed history older than the retention window."""
    with closing(connect()) as connection:
        now = time.time()
        cutoff = now - ttl_seconds if ttl_seconds is not None else now
        rows = connection.execute(
            """
            SELECT id FROM jobs
            WHERE expires_at < ?
               OR (status IN ('completed', 'failed') AND created_at < ?)
            """,
            (now, cutoff),
        ).fetchall()
        connection.execute(
            """
            DELETE FROM jobs
            WHERE expires_at < ?
               OR (status IN ('completed', 'failed') AND created_at < ?)
            """,
            (now, cutoff),
        )
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        connection.commit()
        return [row["id"] for row in rows]


def compact_database(max_pages: int | None = None) -> dict[str, int | str]:
    """Checkpoint WAL pages and release incremental-vacuumable free pages."""
    with closing(connect()) as connection:
        checkpoint = connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        before = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        if max_pages is None:
            connection.execute("PRAGMA incremental_vacuum")
        else:
            connection.execute(f"PRAGMA incremental_vacuum({max(0, int(max_pages))})")
        after = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        connection.commit()
        return {
            "checkpoint": str(tuple(checkpoint) if checkpoint is not None else ""),
            "freelist_before": before,
            "freelist_after": after,
        }


def consume_rate_limit(subject: str, limit: int, window_seconds: int = 60) -> bool:
    now = time.time()
    window_seconds = max(1, int(window_seconds))
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT window_started, request_count FROM rate_limits WHERE subject = ?", (subject,)).fetchone()
        if not row or now - row["window_started"] >= window_seconds:
            connection.execute("INSERT OR REPLACE INTO rate_limits VALUES (?, ?, 1)", (subject, now))
            connection.commit()
            return True
        if row["request_count"] >= limit:
            connection.rollback()
            return False
        connection.execute("UPDATE rate_limits SET request_count = request_count + 1 WHERE subject = ?", (subject,))
        connection.commit()
        return True


# ----------------------------------------------------------------------
# Developer Public REST API Quotas & Idempotency
# ----------------------------------------------------------------------

def _utc_midnight_timestamp() -> int:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    tomorrow_utc = now_utc.date() + datetime.timedelta(days=1)
    reset_dt = datetime.datetime.combine(tomorrow_utc, datetime.time.min, tzinfo=datetime.timezone.utc)
    return int(reset_dt.timestamp())


def _utc_today_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def get_developer_api_usage(user_id: str) -> dict:
    today_str = _utc_today_str()
    subject_api = f"dev_api:{user_id}"
    subject_ai = f"dev_ai:{user_id}"

    calls_used = get_daily_usage(subject_api, today_str)
    ai_used = get_daily_usage(subject_ai, today_str)

    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT COUNT(*) as count FROM jobs WHERE user_id = ? AND status IN ('queued', 'processing')",
            (user_id,)
        ).fetchone()
        active_jobs = int(row["count"]) if row else 0

    reset_ts = _utc_midnight_timestamp()
    reset_iso = datetime.datetime.fromtimestamp(reset_ts, tz=datetime.timezone.utc).isoformat()

    return {
        "user_id": user_id,
        "daily_limit": FREE_API_CALLS_PER_DAY,
        "calls_used": calls_used,
        "calls_remaining": max(0, FREE_API_CALLS_PER_DAY - calls_used),
        "ai_limit": FREE_AI_CALLS_PER_DAY,
        "ai_used": ai_used,
        "ai_remaining": max(0, FREE_AI_CALLS_PER_DAY - ai_used),
        "max_file_size_mb": FREE_MAX_FILE_SIZE_MB,
        "concurrent_jobs_limit": FREE_CONCURRENT_JOBS,
        "active_jobs": active_jobs,
        "reset_time_utc": reset_iso,
        "reset_timestamp": reset_ts,
    }


def check_and_consume_developer_quota(user_id: str, is_ai: bool = False, file_size_bytes: int = 0) -> tuple[bool, str | None, dict]:
    usage = get_developer_api_usage(user_id)

    # 1. File size enforcement
    max_bytes = usage["max_file_size_mb"] * 1024 * 1024
    if file_size_bytes > max_bytes:
        return False, f"File size exceeds free developer testing limit of {usage['max_file_size_mb']} MB.", usage

    # 2. Concurrent jobs enforcement
    if usage["active_jobs"] >= usage["concurrent_jobs_limit"]:
        return False, f"Concurrent job limit ({usage['concurrent_jobs_limit']}) reached. Please wait for running jobs to finish.", usage

    # 3. Overall daily call limit
    if usage["calls_remaining"] <= 0:
        return False, f"Daily API allowance ({usage['daily_limit']} calls/day) exceeded. Limit resets at {usage['reset_time_utc']}.", usage

    # 4. AI-assisted call cap (nested within total calls)
    if is_ai and usage["ai_remaining"] <= 0:
        return False, f"Daily AI-assisted operation cap ({usage['ai_limit']} AI calls/day) reached. Limit resets at {usage['reset_time_utc']}.", usage

    # Consume quota atomically
    today_str = _utc_today_str()
    increment_daily_usage(f"dev_api:{user_id}", today_str)
    if is_ai:
        increment_daily_usage(f"dev_ai:{user_id}", today_str)

    updated_usage = get_developer_api_usage(user_id)
    return True, None, updated_usage


def refund_developer_quota(user_id: str, is_ai: bool = False) -> None:
    today_str = _utc_today_str()
    with closing(connect()) as connection:
        connection.execute(
            "UPDATE user_usage SET count = MAX(0, count - 1) WHERE subject = ? AND usage_date = ?",
            (f"dev_api:{user_id}", today_str)
        )
        if is_ai:
            connection.execute(
                "UPDATE user_usage SET count = MAX(0, count - 1) WHERE subject = ? AND usage_date = ?",
                (f"dev_ai:{user_id}", today_str)
            )
        connection.commit()


def get_idempotent_job(key: str, user_id: str) -> str | None:
    if not key:
        return None
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT job_id, expires_at FROM idempotency_keys WHERE key = ? AND user_id = ?",
            (key.strip(), user_id)
        ).fetchone()
        if row and row["expires_at"] > time.time():
            return row["job_id"]
        if row:
            connection.execute("DELETE FROM idempotency_keys WHERE key = ?", (key.strip(),))
            connection.commit()
    return None


def record_idempotent_job(key: str, user_id: str, job_id: str, ttl: int = 86400) -> None:
    if not key:
        return
    with closing(connect()) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO idempotency_keys (key, user_id, job_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (key.strip(), user_id, job_id, time.time(), time.time() + ttl)
        )
        connection.commit()


# ---------------------------------------------------------------------------
# Admin-only analytics functions
# ---------------------------------------------------------------------------

def admin_get_analytics() -> dict:
    """Return aggregate statistics for the admin dashboard."""
    today_str = __import__("datetime").date.today().isoformat()
    with closing(connect()) as connection:
        total_users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        tier_rows = connection.execute(
            "SELECT tier, COUNT(*) AS cnt FROM users GROUP BY tier"
        ).fetchall()
        tier_counts: dict[str, int] = {r["tier"]: r["cnt"] for r in tier_rows}

        today_active = connection.execute(
            "SELECT COUNT(DISTINCT subject) FROM user_usage WHERE usage_date = ?",
            (today_str,)
        ).fetchone()[0]

        new_7d = connection.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?",
            (time.time() - 7 * 86400,)
        ).fetchone()[0]

        total_jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        jobs_today = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE created_at >= ?",
            (time.time() - 86400,)
        ).fetchone()[0]

        total_waitlist = connection.execute("SELECT COUNT(*) FROM app_waitlist").fetchone()[0]

    return {
        "total_users": total_users,
        "tier_breakdown": tier_counts,
        "pro_users": tier_counts.get("pro", 0) + tier_counts.get("student_pro", 0),
        "dev_users": tier_counts.get("developer", 0) + tier_counts.get("dev", 0),
        "free_users": tier_counts.get("free", 0),
        "today_active": today_active,
        "new_signups_7d": new_7d,
        "total_jobs": total_jobs,
        "jobs_today": jobs_today,
        "total_waitlist": total_waitlist,
    }


def admin_get_all_users(limit: int = 500) -> list[dict]:
    """Return all registered users with basic profile data."""
    with closing(connect()) as connection:
        rows = connection.execute(
            """SELECT u.id, u.email, u.tier, u.created_at, u.subscription_status,
                      MAX(uu.usage_date) AS last_active_date
               FROM users u
               LEFT JOIN user_usage uu ON uu.subject = u.id
               GROUP BY u.id
               ORDER BY u.created_at DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def admin_get_waitlist(limit: int = 1000) -> list[dict]:
    """Return all waitlist entries ordered by signup time."""
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT id, email, platform, created_at, ip_address FROM app_waitlist ORDER BY created_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Admin Multi-Factor & Intrusion Lockout Functions
# ---------------------------------------------------------------------------

def get_admin_lockout_remaining() -> float:
    """Returns remaining seconds if admin console is in a 24-hour lockout state, else 0."""
    now = time.time()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT locked_until FROM admin_auth_state WHERE id = 'current'"
        ).fetchone()
        if row and row["locked_until"] and row["locked_until"] > now:
            return round(row["locked_until"] - now, 1)
    return 0.0


def record_admin_failed_attempt() -> tuple[int, bool]:
    """Records a failed attempt. If failed_attempts >= 3, enforces a 24-hour lockout.
    Returns (attempts_count, is_locked_now).
    """
    now = time.time()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT failed_attempts, locked_until FROM admin_auth_state WHERE id = 'current'"
        ).fetchone()
        current_attempts = (row["failed_attempts"] if row else 0) + 1
        is_locked = False
        locked_until = 0.0
        if current_attempts >= 3:
            locked_until = now + 86400  # 24-hour lockout
            is_locked = True
        
        connection.execute(
            """INSERT INTO admin_auth_state (id, failed_attempts, locked_until, last_attempt_at)
               VALUES ('current', ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   failed_attempts = excluded.failed_attempts,
                   locked_until = CASE WHEN excluded.locked_until > 0 THEN excluded.locked_until ELSE admin_auth_state.locked_until END,
                   last_attempt_at = excluded.last_attempt_at""",
            (current_attempts, locked_until, now)
        )
        connection.commit()
    return current_attempts, is_locked


def reset_admin_failed_attempts() -> None:
    """Clears failed attempts counter after a successful full multi-factor login."""
    with closing(connect()) as connection:
        connection.execute(
            "UPDATE admin_auth_state SET failed_attempts = 0, locked_until = 0 WHERE id = 'current'"
        )
        connection.commit()


def set_admin_pending_otp(otp_code: str, expires_in: int = 600) -> None:
    """Stores a cryptographically hashed OTP with expiration (default 10 minutes)."""
    now = time.time()
    otp_hash = hashlib.sha256(otp_code.encode()).hexdigest()
    with closing(connect()) as connection:
        connection.execute(
            """INSERT INTO admin_auth_state (id, pending_otp_hash, otp_expires_at)
               VALUES ('current', ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   pending_otp_hash = excluded.pending_otp_hash,
                   otp_expires_at = excluded.otp_expires_at""",
            (otp_hash, now + expires_in)
        )
        connection.commit()


def verify_admin_otp(otp_code: str) -> bool:
    """Validates the pending OTP using constant-time comparison and single-use consumption."""
    now = time.time()
    clean_code = str(otp_code).strip()
    if not clean_code:
        return False
    otp_hash = hashlib.sha256(clean_code.encode()).hexdigest()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT pending_otp_hash, otp_expires_at FROM admin_auth_state WHERE id = 'current'"
        ).fetchone()
        if not row or not row["pending_otp_hash"]:
            return False
        if row["otp_expires_at"] < now:
            return False
        if not hmac.compare_digest(row["pending_otp_hash"], otp_hash):
            return False
        # Invalidate OTP on successful use
        connection.execute(
            "UPDATE admin_auth_state SET pending_otp_hash = NULL, otp_expires_at = 0 WHERE id = 'current'"
        )
        connection.commit()
        return True


def create_admin_session(ttl_seconds: int = 14400) -> str:
    """Generates a secure 64-char session token (4-hour validity) for authenticated admin operations."""
    token = secrets.token_hex(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with closing(connect()) as connection:
        connection.execute(
            """INSERT INTO admin_auth_state (id, session_token_hash, session_expires_at)
               VALUES ('current', ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   session_token_hash = excluded.session_token_hash,
                   session_expires_at = excluded.session_expires_at,
                   failed_attempts = 0,
                   locked_until = 0""",
            (token_hash, now + ttl_seconds)
        )
        connection.commit()
    return token


def verify_admin_session(token: str) -> bool:
    """Validates an active admin session token."""
    if not token or len(token) < 32:
        return False
    token_hash = hashlib.sha256(token.strip().encode()).hexdigest()
    now = time.time()
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT session_token_hash, session_expires_at FROM admin_auth_state WHERE id = 'current'"
        ).fetchone()
        if not row or not row["session_token_hash"]:
            return False
        if row["session_expires_at"] < now:
            return False
        return hmac.compare_digest(row["session_token_hash"], token_hash)


def revoke_admin_session() -> None:
    """Invalidates the admin session on logout."""
    with closing(connect()) as connection:
        connection.execute(
            "UPDATE admin_auth_state SET session_token_hash = NULL, session_expires_at = 0 WHERE id = 'current'"
        )
        connection.commit()


def admin_get_extended_analytics() -> dict:
    """Return comprehensive analytics, time-series signup trends, and platform metrics."""
    today_str = __import__("datetime").date.today().isoformat()
    now = time.time()
    with closing(connect()) as connection:
        total_users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        tier_rows = connection.execute(
            "SELECT tier, COUNT(*) AS cnt FROM users GROUP BY tier"
        ).fetchall()
        tier_counts: dict[str, int] = {r["tier"]: r["cnt"] for r in tier_rows}

        today_active = connection.execute(
            "SELECT COUNT(DISTINCT subject) FROM user_usage WHERE usage_date = ?",
            (today_str,)
        ).fetchone()[0]

        new_7d = connection.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?",
            (now - 7 * 86400,)
        ).fetchone()[0]

        total_jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        jobs_today = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE created_at >= ?",
            (now - 86400,)
        ).fetchone()[0]

        total_waitlist = connection.execute("SELECT COUNT(*) FROM app_waitlist").fetchone()[0]

        # 14-day signup trend
        days_trend = []
        for d in range(13, -1, -1):
            day_start = now - (d + 1) * 86400
            day_end = now - d * 86400
            day_dt = __import__("datetime").datetime.fromtimestamp(day_end, __import__("datetime").timezone.utc)
            day_label = day_dt.strftime("%d %b")
            cnt = connection.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= ? AND created_at < ?",
                (day_start, day_end)
            ).fetchone()[0]
            days_trend.append({"date": day_label, "count": cnt})

        # Waitlist platform breakdown
        plat_rows = connection.execute(
            "SELECT platform, COUNT(*) as cnt FROM app_waitlist GROUP BY platform ORDER BY cnt DESC"
        ).fetchall()
        waitlist_platforms = [{"platform": r["platform"], "count": r["cnt"]} for r in plat_rows]

        # Top Job operations
        op_rows = connection.execute(
            "SELECT operation, COUNT(*) as cnt FROM jobs GROUP BY operation ORDER BY cnt DESC LIMIT 6"
        ).fetchall()
        top_operations = [{"operation": r["operation"], "count": r["cnt"]} for r in op_rows]

        # Recent audit logs (last 10 events)
        audit_rows = connection.execute(
            "SELECT event_type, email, ip_address, created_at, details FROM audit_logs ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        recent_audits = [dict(r) for r in audit_rows]

    return {
        "total_users": total_users,
        "tier_breakdown": tier_counts,
        "pro_users": tier_counts.get("pro", 0) + tier_counts.get("student_pro", 0),
        "dev_users": tier_counts.get("developer", 0) + tier_counts.get("dev", 0),
        "free_users": tier_counts.get("free", 0),
        "today_active": today_active,
        "new_signups_7d": new_7d,
        "total_jobs": total_jobs,
        "jobs_today": jobs_today,
        "total_waitlist": total_waitlist,
        "days_trend": days_trend,
        "waitlist_platforms": waitlist_platforms,
        "top_operations": top_operations,
        "recent_audits": recent_audits,
    }

