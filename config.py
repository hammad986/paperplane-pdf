from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PAPERPLANE_PUBLIC_URL = os.getenv("PAPERPLANE_PUBLIC_URL", "").strip().rstrip("/")

DATA_DIR = Path(os.getenv("PAPERPLANE_DATA_DIR", ROOT / "runtime_data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(exist_ok=True)
DATABASE = DATA_DIR / "paperplane.sqlite3"

# File size limits (Default: 500 MB per file, batch limit up to 100 files)
MAX_FILE_SIZE = int(os.getenv("PAPERPLANE_MAX_FILE_SIZE", 500 * 1024 * 1024))
import secrets

# Ephemeral storage lifecycle: 2 hours (7,200 seconds) by default.
# Deployments can raise this through PAPERPLANE_JOB_TTL_SECONDS when longer
# download windows are required.
JOB_TTL_SECONDS = int(os.getenv("PAPERPLANE_JOB_TTL_SECONDS", 2 * 60 * 60))
CLEANUP_INTERVAL_SECONDS = max(
    60,
    int(os.getenv("PAPERPLANE_CLEANUP_INTERVAL_SECONDS", 15 * 60)),
)
EMERGENCY_DISK_FREE_PERCENT = 15
EMERGENCY_DISK_FREE_BYTES = 2 * 1024 * 1024 * 1024
EMERGENCY_JOB_AGE_SECONDS = 30 * 60
REQUIRE_AUTH = os.getenv("PAPERPLANE_REQUIRE_AUTH", "false").lower() in {"true", "1", "yes"}
RATE_LIMIT_PER_MINUTE = int(os.getenv("PAPERPLANE_RATE_LIMIT_PER_MINUTE", "120"))

# Runtime Environment & Production Safety Controls
ENVIRONMENT = os.getenv("PAPERPLANE_ENV", "development").lower()
ALLOW_BILLING_SIMULATION = os.getenv(
    "PAPERPLANE_ALLOW_BILLING_SIMULATION",
    "true" if ENVIRONMENT != "production" else "false"
).lower() in ("true", "1", "yes")

# Google OAuth2 Credential Verification
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


# Cookie Security Settings
SECURE_COOKIES = os.getenv("PAPERPLANE_SECURE_COOKIES", "true" if ENVIRONMENT == "production" else "false").lower() in ("true", "1", "yes")
COOKIE_SAMESITE = os.getenv("PAPERPLANE_COOKIE_SAMESITE", "lax").lower()

# Transactional Email & Security Notifications (Resend API & SMTP)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@paperplanepdf.com")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USER", "noreply@paperplane-pdf.com"))
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Paperplane PDF Security")
SMTP_ENABLED = os.getenv("SMTP_ENABLED", "false").lower() in ("true", "1", "yes")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

# Production-safe CORS & Host whitelisting (wildcard '*' strictly excluded)
raw_origins = os.getenv(
    "PAPERPLANE_ALLOWED_ORIGINS",
    "http://127.0.0.1:8501,http://localhost:8501,http://127.0.0.1:8000,http://localhost:8000"
)
ALLOWED_ORIGINS = [
    item.strip()
    for item in raw_origins.split(",")
    if item.strip() and item.strip() != "*"
]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["http://127.0.0.1:8501", "http://localhost:8501"]

raw_hosts = os.getenv(
    "PAPERPLANE_TRUSTED_HOSTS",
    "127.0.0.1,localhost,0.0.0.0,testserver"
)
TRUSTED_HOSTS = [
    item.strip()
    for item in raw_hosts.split(",")
    if item.strip() and item.strip() != "*"
]
if not TRUSTED_HOSTS:
    TRUSTED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

# Cryptographic Session & JWT Secrets with safe random fallback
_configured_session_secret = (
    os.getenv("PAPERPLANE_SESSION_SECRET", "").strip()
    or os.getenv("SESSION_SECRET_KEY", "").strip()
    or os.getenv("JWT_SECRET", "").strip()
)
_configured_jwt_secret = os.getenv("JWT_SECRET", "").strip() or _configured_session_secret
SESSION_SECRET_KEY = _configured_session_secret or f"paperplane-sec-{secrets.token_hex(32)}"
JWT_SECRET = _configured_jwt_secret or SESSION_SECRET_KEY

CLAMAV_HOST = os.getenv("PAPERPLANE_CLAMAV_HOST", "")
CLAMAV_PORT = int(os.getenv("PAPERPLANE_CLAMAV_PORT", "3310"))

# AI Providers (Google Gemini gemini-1.5-flash, OpenAI, or local offline fallback)
AI_PROVIDER = os.getenv("PAPERPLANE_AI_PROVIDER", "gemini")
GEMINI_MODEL = os.getenv("PAPERPLANE_GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Cashfree Payment Gateway (PG v2023-08-01)
#
# CASHFREE_ENV controls the API host only. Keep these credentials server-side;
# the browser receives a short-lived payment_session_id, never the secret key.
CASHFREE_APP_ID = os.getenv("CASHFREE_APP_ID", "").strip()
CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY", "").strip()
CASHFREE_ENV = os.getenv("CASHFREE_ENV", "TEST").upper()
if CASHFREE_ENV not in {"TEST", "PROD"}:
    CASHFREE_ENV = "TEST"
CASHFREE_API_VERSION = "2023-08-01"
CASHFREE_BASE_URL = (
    "https://sandbox.cashfree.com/pg"
    if CASHFREE_ENV == "TEST"
    else "https://api.cashfree.com/pg"
)
CASHFREE_DEFAULT_CUSTOMER_PHONE = os.getenv("CASHFREE_DEFAULT_CUSTOMER_PHONE", "9999999999")

# Freemium Tier Quotas & Multi-Tier Pricing Architecture.
# Cashfree checkout defaults to INR. USD amounts remain available for merchants
# whose Cashfree account is enabled for USD settlement.
FREE_TIER_DAILY_LIMIT = int(os.getenv("PAPERPLANE_FREE_TIER_DAILY_LIMIT", "100"))
PRO_TIER_PRICE_USD = float(os.getenv("PAPERPLANE_PRO_PRICE_USD", "3.00"))
PRO_TIER_PRICE_INR = int(os.getenv("PAPERPLANE_PRO_PRICE_INR", "250"))
DEV_TIER_PRICE_USD = float(os.getenv("PAPERPLANE_DEV_PRICE_USD", "9.00"))
DEV_TIER_PRICE_INR = int(os.getenv("PAPERPLANE_DEV_PRICE_INR", "750"))

S3_BUCKET = os.getenv("PAPERPLANE_S3_BUCKET", "")

# AgentRouter AI Provider Configuration
AGENTROUTER_API_KEY = os.getenv("AGENTROUTER_API_KEY", "")
AGENTROUTER_BASE_URL = os.getenv("AGENTROUTER_BASE_URL", "https://agentrouter.org").rstrip("/")
AGENTROUTER_MODEL = os.getenv("AGENTROUTER_MODEL", "gpt-6.1-sol")
AGENTROUTER_TIMEOUT_SECONDS = min(8, max(1, int(os.getenv("AGENTROUTER_TIMEOUT_SECONDS", "8"))))
AGENTROUTER_MAX_RETRIES = max(0, min(1, int(os.getenv("AGENTROUTER_MAX_RETRIES", "0"))))
AGENTROUTER_MAX_OUTPUT_TOKENS = int(os.getenv("AGENTROUTER_MAX_OUTPUT_TOKENS", "4096"))
AI_KILL_SWITCH = os.getenv("PAPERPLANE_AI_KILL_SWITCH", "false").lower() in ("true", "1", "yes")

# Public Developer REST API Quotas (Free Tier Defaults)
FREE_API_CALLS_PER_DAY = int(os.getenv("PAPERPLANE_FREE_API_CALLS_PER_DAY", "10"))
FREE_AI_CALLS_PER_DAY = int(os.getenv("PAPERPLANE_FREE_AI_CALLS_PER_DAY", "3"))
FREE_MAX_FILE_SIZE_MB = int(os.getenv("PAPERPLANE_FREE_MAX_FILE_SIZE_MB", "10"))
FREE_CONCURRENT_JOBS = int(os.getenv("PAPERPLANE_FREE_CONCURRENT_JOBS", "2"))
