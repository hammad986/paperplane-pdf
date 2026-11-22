from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from app import configured_port


def test_host_platform_port_takes_precedence_over_docker_default():
    assert configured_port({"PORT": "24680", "PAPERPLANE_PORT": "8501"}) == 24680


def test_local_port_override_is_used_without_platform_port():
    assert configured_port({"PAPERPLANE_PORT": "18501"}) == 18501


def test_default_port_is_used_when_no_port_is_configured():
    assert configured_port({}) == 8501


def test_railway_healthcheck_host_is_allowed_only_in_railway_runtime():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="paperplane-railway-config-") as data_dir:
        base_env = os.environ.copy()
        base_env.update({
            "PAPERPLANE_SKIP_DOTENV": "1",
            "PAPERPLANE_DATA_DIR": data_dir,
            "PAPERPLANE_TRUSTED_HOSTS": "paperplane.qd.je",
        })
        script = "import config; print('healthcheck.railway.app' in config.TRUSTED_HOSTS)"
        local_env = base_env.copy()
        local_env.pop("RAILWAY_SERVICE_ID", None)
        local = subprocess.run([sys.executable, "-c", script], cwd=root, env=local_env, capture_output=True, text=True, check=True)
        railway_env = base_env | {"RAILWAY_SERVICE_ID": "synthetic-service"}
        railway = subprocess.run([sys.executable, "-c", script], cwd=root, env=railway_env, capture_output=True, text=True, check=True)

    assert local.stdout.strip() == "False"
    assert railway.stdout.strip() == "True"
