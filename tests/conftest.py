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
