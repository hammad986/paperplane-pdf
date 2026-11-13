from __future__ import annotations


def register_verified(client, email: str, password: str):
    """Register through the same OTP verification path used by the web client."""
    registration = client.post(
        "/api/auth/register",
        data={"email": email, "password": password, "confirm_password": password},
    )
    assert registration.status_code == 200, registration.text
    payload = registration.json()
    assert payload.get("status") == "otp_required", payload
    otp = payload.get("dev_otp")
    assert otp and len(otp) == 6, "Tests require TESTING=True so the development OTP is returned."
    verified = client.post(
        "/api/auth/verify-signup-otp",
        json={"email": email, "otp": otp},
    )
    assert verified.status_code == 200, verified.text
    return verified
