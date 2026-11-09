import os
import tempfile
from pathlib import Path

import pytest

# Ensure testing flag is active for test suite assertions
os.environ["TESTING"] = "True"
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
        connection.execute("DELETE FROM rate_limits WHERE subject LIKE 'ai-account:%'")
        connection.commit()
