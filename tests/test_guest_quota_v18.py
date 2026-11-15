from fastapi.testclient import TestClient

import server


def test_guest_daily_quota_is_scoped_to_signed_browser_cookie(monkeypatch):
    monkeypatch.setattr(server.executor, "submit", lambda *_args, **_kwargs: None)
    first = TestClient(server.app)
    second = TestClient(server.app)

    first_landing = first.get("/")
    second_landing = second.get("/")
    first_cookie = first.cookies.get(server.GUEST_QUOTA_COOKIE)
    second_cookie = second.cookies.get(server.GUEST_QUOTA_COOKIE)

    assert first_landing.status_code == second_landing.status_code == 200
    assert first_cookie and second_cookie and first_cookie != second_cookie
    assert "httponly" in first_landing.headers["set-cookie"].lower()
    assert server._guest_quota_id_from_cookie(first_cookie)
    assert server._guest_quota_id_from_cookie(second_cookie)
    assert server._guest_quota_id_from_cookie(first_cookie[:-1] + ("0" if first_cookie[-1] != "0" else "1")) is None

    for client in (first, first, second):
        response = client.post(
            "/api/jobs",
            data={"operation": "html_to_pdf", "options": '{"url":"https://example.com"}'},
        )
        assert response.status_code == 202

    assert first.get("/api/billing/status").json()["usage_today"] == 2
    assert second.get("/api/billing/status").json()["usage_today"] == 1
