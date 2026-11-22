from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name("live_verification.py")
SPEC = importlib.util.spec_from_file_location("paperplane_local_smoke", SCRIPT)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_local_smoke_checks_only_read_only_health_and_catalog(monkeypatch, capsys):
    requested = []
    responses = {
        "/api/health": {"status": "ok", "workers": 4},
        "/api/integrations": {"queue": True},
        "/api/operations": {"merge_pdf": {}, "split_pdf": {}},
    }

    def fake_get_json(path):
        requested.append(path)
        return responses[path]

    monkeypatch.setattr(smoke, "BASE_URL", "http://127.0.0.1:8501")
    monkeypatch.setattr(smoke, "_get_json", fake_get_json)
    smoke.test_live_server()

    assert requested == ["/api/health", "/api/integrations", "/api/operations"]
    assert "LOCAL READ-ONLY SMOKE CHECKS PASSED" in capsys.readouterr().out


@pytest.mark.parametrize("url", ["https://paperplane.qd.je", "http://example.com", "http://192.168.1.4:8501"])
def test_local_smoke_refuses_non_loopback_targets(monkeypatch, url):
    monkeypatch.setattr(smoke, "BASE_URL", url)
    with pytest.raises(ValueError, match="loopback"):
        smoke.test_live_server()
