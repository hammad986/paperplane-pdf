import os
import secrets
import tempfile
from pathlib import Path

import pytest

# Ensure testing flag is active for test suite assertions
os.environ["TESTING"] = "True"
os.environ["PAPERPLANE_ENV"] = "development"
os.environ["PAPERPLANE_SKIP_DOTENV"] = "1"
os.environ["PAPERPLANE_ENABLE_DOCS"] = "false"
os.environ["CASHFREE_ENV"] = "TEST"
# Keep the local suite fully offline and independent of any owner credentials
# inherited from the desktop session or present in a developer .env file.
for _credential_env in (
    "CASHFREE_APP_ID", "CASHFREE_SECRET_KEY", "RESEND_API_KEY", "SMTP_PASSWORD",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "BLUESMINDS_API_KEY",
    "PAPERPLANE_AI_API_KEY", "PAPERPLANE_AI_SETTINGS_KEY", "PAPERPLANE_ADMIN_KEY",
    "PAPERPLANE_ADMIN_SECRET_KEY", "PAPERPLANE_ADMIN_CODE", "PAPERPLANE_ADMIN_SECRET_CODE",
    "ADMIN_SECRET_KEY", "ADMIN_SECRET_CODE", "PAPERPLANE_SESSION_SECRET", "SESSION_SECRET_KEY",
):
    os.environ.pop(_credential_env, None)
# Startup requires explicit credentials. These values are generated locally per run.
os.environ["PAPERPLANE_ADMIN_KEY"] = secrets.token_urlsafe(48)
os.environ["PAPERPLANE_ADMIN_CODE"] = secrets.token_urlsafe(32)
# Keep persistent app state from one pytest invocation out of another. Billable
# local requests update the same daily usage store as the app, so reusing the
# developer's runtime_data database can make later suite runs fail at quota 100.
os.environ["PAPERPLANE_DATA_DIR"] = str(
    Path(tempfile.gettempdir()) / f"paperplane-pytest-{os.getpid()}"
)


@pytest.fixture(autouse=True)
def clear_ai_request_limit_bucket():
    """Keep per-test AI throttling isolated while preserving in-test limit checks."""
    import persistence

    persistence.init_db()
    with persistence.connect() as connection:
        connection.execute("DELETE FROM rate_limits WHERE subject LIKE 'ai-account:%' OR subject LIKE 'job-account:%'")
        connection.execute("DELETE FROM user_usage WHERE subject LIKE 'ip:%'")
        connection.commit()
