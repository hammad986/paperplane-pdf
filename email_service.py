from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

logger = logging.getLogger("paperplane.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USER", "noreply@paperplane-pdf.com"))
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Paperplane PDF Security")
SMTP_ENABLED = os.getenv("SMTP_ENABLED", "false").lower() in ("true", "1", "yes")
PAPERPLANE_PUBLIC_URL = os.getenv("PAPERPLANE_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def _send_resend_api(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Dispatches email via official Resend HTTPS REST API."""
    try:
        from_email = SMTP_FROM_EMAIL or "onboarding@resend.dev"
        sender_header = f"{SMTP_FROM_NAME} <{from_email}>" if SMTP_FROM_NAME else from_email
        payload = {
            "from": sender_header,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body
        }
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "Paperplane-Email/2.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                logger.info("Email delivered via Resend API to %s: %s", to_email, subject)
                return True
            logger.warning("Resend API returned status %s for %s", resp.status, to_email)
            return False
    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode("utf-8", errors="ignore")
        logger.warning("Resend API HTTP error for %s (%s): %s", to_email, http_err.code, err_body)
        return False
    except Exception as exc:
        logger.warning("Failed to dispatch email to %s via Resend API: %s", to_email, exc)
        return False


def _send_smtp(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Dispatches an email synchronously via SMTP with TLS. Returns True on success."""
    if not SMTP_ENABLED or not SMTP_HOST:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM_EMAIL))
        msg["To"] = to_email

        part1 = MIMEText(text_body, "plain", "utf-8")
        part2 = MIMEText(html_body, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)

        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()

        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)

        server.sendmail(SMTP_FROM_EMAIL, [to_email], msg.as_string())
        server.quit()
        logger.info("Email delivered successfully to %s: %s", to_email, subject)
        return True
    except Exception as exc:
        logger.warning("Failed to send transactional email to %s via SMTP (%s): %s", to_email, SMTP_HOST, exc)
        return False


def _dispatch_email(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Unified email dispatcher: supports Resend REST API, standard SMTP, and development preview logging."""
    if RESEND_API_KEY:
        resend_ok = _send_resend_api(to_email, subject, html_body, text_body)
        if resend_ok:
            return True
        logger.warning("Resend API failed, checking SMTP fallback...")

    if SMTP_ENABLED and SMTP_HOST:
        smtp_ok = _send_smtp(to_email, subject, html_body, text_body)
        if smtp_ok:
            return True

    logger.info(
        "Email dispatch simulated for %s (Subject: %s)\n[DISPATCH PREVIEW]:\n%s",
        to_email, subject, text_body
    )
    return True


def send_otp_email(to_email: str, otp_code: str, purpose: str = "login") -> bool:
    """Sends a 6-digit one-time password (OTP) verification email for signup or login."""
    is_signup = purpose.lower().strip() == "signup"
    action_name = "Confirm Your Account" if is_signup else "Sign-In Verification"
    subject = f"Your Paperplane PDF One-Time Code: {otp_code} ({action_name})"

    headline = "Confirm Your Paperplane PDF Account" if is_signup else "Two-Factor Sign-In Verification"
    explanation = (
        f"Thank you for creating an account with <strong style='color: #ffffff;'>{to_email}</strong>. "
        f"Please enter the 6-digit one-time code below to verify your email and activate your account:"
        if is_signup
        else f"A sign-in request was initiated for your Paperplane PDF account (<strong style='color: #ffffff;'>{to_email}</strong>). "
        f"Enter the 6-digit one-time verification code below to complete your login:"
    )

    text_body = (
        f"Hello,\n\n"
        f"{headline}\n\n"
        f"Your 6-digit one-time code is: {otp_code}\n\n"
        f"This code will expire in 10 minutes.\n"
        f"If you did not initiate this request, you can safely disregard this message. Never share this code with anyone.\n\n"
        f"The Paperplane PDF Security Team\n{PAPERPLANE_PUBLIC_URL}"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0d1416; color: #f0f5f4; margin: 0; padding: 32px 16px;">
  <div style="max-width: 540px; margin: 0 auto; background-color: #141e21; border: 1px solid #28393d; border-radius: 12px; padding: 28px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
      <div style="background-color: #ff4b26; width: 32px; height: 32px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; color: #ffffff; text-align: center; line-height: 32px;">P</div>
      <span style="font-size: 18px; font-weight: 700; color: #f0f5f4; margin-left: 8px;">Paperplane PDF</span>
    </div>
    <h2 style="font-size: 20px; color: #f0f5f4; margin-top: 0; margin-bottom: 12px;">{headline}</h2>
    <p style="color: #a3b8b6; font-size: 14px; line-height: 1.5; margin-bottom: 20px;">
      {explanation}
    </p>
    <div style="font-size: 36px; font-weight: 800; letter-spacing: 10px; color: #ff4b26; background: #1a2528; border: 1.5px dashed #ff4b26; padding: 18px 24px; text-align: center; border-radius: 10px; margin: 24px 0; font-family: monospace;">
      {otp_code}
    </div>
    <div style="background-color: #1a2528; border: 1px solid #33484c; border-radius: 8px; padding: 14px; margin-bottom: 24px; font-size: 13px;">
      <div style="margin-bottom: 6px;"><strong style="color: #a3b8b6;">Validity:</strong> <span style="color: #f0f5f4;">10 minutes</span></div>
      <div><strong style="color: #a3b8b6;">Security Notice:</strong> <span style="color: #a3b8b6;">Do not share this code with anyone. Paperplane staff will never ask for your code.</span></div>
    </div>
    <p style="color: #708684; font-size: 12px; line-height: 1.4; margin-bottom: 20px;">
      If you did not initiate this request, you can safely ignore this email.
    </p>
    <div style="border-top: 1px solid #28393d; padding-top: 18px; font-size: 12px; color: #708684; text-align: center;">
      Ephemeral Local Document Processing &middot; Privacy-First Security
    </div>
  </div>
</body>
</html>"""
    return _dispatch_email(to_email, subject, html_body, text_body)


def send_login_notification(to_email: str, client_ip: str = "Unknown", user_agent: str = "") -> bool:
    """Sends a security notification when a user logs in."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = "Security Alert: Your Paperplane PDF account was logged in"
    
    agent_info = f"\nBrowser / Device: {user_agent}" if user_agent else ""
    text_body = (
        f"Hello,\n\n"
        f"Your Paperplane PDF account ({to_email}) was successfully logged in.\n"
        f"Time: {now_utc}\n"
        f"IP Address: {client_ip}{agent_info}\n\n"
        f"If this was you, you can safely ignore this alert.\n"
        f"If you did not sign in, please secure your account immediately by resetting your password.\n\n"
        f"The Paperplane PDF Security Team\n{PAPERPLANE_PUBLIC_URL}"
    )

    ua_row = f'<div><strong style="color: #a3b8b6;">Device:</strong> <span style="color: #f0f5f4;">{user_agent[:60]}</span></div>' if user_agent else ""

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0d1416; color: #f0f5f4; margin: 0; padding: 32px 16px;">
  <div style="max-width: 540px; margin: 0 auto; background-color: #141e21; border: 1px solid #28393d; border-radius: 12px; padding: 28px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
      <div style="background-color: #ff4b26; width: 32px; height: 32px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; color: #ffffff; text-align: center; line-height: 32px;">P</div>
      <span style="font-size: 18px; font-weight: 700; color: #f0f5f4; margin-left: 8px;">Paperplane PDF</span>
    </div>
    <h2 style="font-size: 20px; color: #f0f5f4; margin-top: 0; margin-bottom: 12px;">Your Account Was Logged In</h2>
    <p style="color: #a3b8b6; font-size: 14px; line-height: 1.5; margin-bottom: 20px;">
      Your Paperplane PDF account (<strong style="color: #ffffff;">{to_email}</strong>) was successfully logged in.
    </p>
    <div style="background-color: #1a2528; border: 1px solid #33484c; border-radius: 8px; padding: 14px; margin-bottom: 24px; font-size: 13px;">
      <div style="margin-bottom: 6px;"><strong style="color: #a3b8b6;">Timestamp:</strong> <span style="color: #f0f5f4;">{now_utc}</span></div>
      <div style="margin-bottom: 6px;"><strong style="color: #a3b8b6;">Client IP:</strong> <span style="color: #f0f5f4;">{client_ip}</span></div>
      {ua_row}
    </div>
    <p style="color: #a3b8b6; font-size: 13px; line-height: 1.5; margin-bottom: 24px;">
      If this was you, no action is needed. If you did not sign in or suspect unauthorized access, reset your password right away.
    </p>
    <div style="border-top: 1px solid #28393d; padding-top: 18px; font-size: 12px; color: #708684; text-align: center;">
      Ephemeral Local Document Processing &middot; Privacy-First Security
    </div>
  </div>
</body>
</html>"""
    return _dispatch_email(to_email, subject, html_body, text_body)


def send_password_reset_email(to_email: str, reset_token: str, base_url: str | None = None) -> bool:
    """Sends a cryptographically secure 1-hour password reset link."""
    domain = (base_url or PAPERPLANE_PUBLIC_URL).rstrip("/")
    reset_url = f"{domain}/?reset_token={reset_token}"
    subject = "Reset Your Paperplane PDF Password"

    text_body = (
        f"Hello,\n\n"
        f"We received a request to reset your Paperplane PDF password.\n"
        f"To reset your password, click the link below (valid for 1 hour):\n\n"
        f"{reset_url}\n\n"
        f"If you did not request a password reset, please ignore this email.\n\n"
        f"The Paperplane PDF Team"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0d1416; color: #f0f5f4; margin: 0; padding: 32px 16px;">
  <div style="max-width: 540px; margin: 0 auto; background-color: #141e21; border: 1px solid #28393d; border-radius: 12px; padding: 28px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
      <div style="background-color: #ff4b26; width: 32px; height: 32px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; color: #ffffff; text-align: center; line-height: 32px;">P</div>
      <span style="font-size: 18px; font-weight: 700; color: #f0f5f4; margin-left: 8px;">Paperplane PDF</span>
    </div>
    <h2 style="font-size: 20px; color: #f0f5f4; margin-top: 0; margin-bottom: 12px;">Reset Your Password</h2>
    <p style="color: #a3b8b6; font-size: 14px; line-height: 1.5; margin-bottom: 24px;">
      We received a request to reset the password for <strong style="color: #ffffff;">{to_email}</strong>. Click the button below to choose a new password. This link expires in 60 minutes.
    </p>
    <div style="text-align: center; margin-bottom: 28px;">
      <a href="{reset_url}" style="background-color: #ff4b26; color: #ffffff; padding: 12px 28px; font-size: 14px; font-weight: 600; text-decoration: none; border-radius: 8px; display: inline-block;">
        Reset Password &rarr;
      </a>
    </div>
    <p style="color: #708684; font-size: 12px; line-height: 1.4; margin-bottom: 20px;">
      Or copy and paste this URL into your browser:<br>
      <a href="{reset_url}" style="color: #ff4b26; word-break: break-all;">{reset_url}</a>
    </p>
    <p style="color: #a3b8b6; font-size: 12px; line-height: 1.4;">
      If you did not request this password reset, no action is needed and your account remains secure.
    </p>
    <div style="border-top: 1px solid #28393d; padding-top: 18px; font-size: 12px; color: #708684; text-align: center; margin-top: 24px;">
      Paperplane PDF &middot; Zero-Knowledge Document Privacy
    </div>
  </div>
</body>
</html>"""
    return _dispatch_email(to_email, subject, html_body, text_body)


def send_password_changed_notification(to_email: str, client_ip: str = "Unknown") -> bool:
    """Sends a security confirmation when the password has been modified."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = "Security Alert: Your Paperplane PDF Password Was Changed"

    text_body = (
        f"Hello,\n\n"
        f"The password for your Paperplane PDF account ({to_email}) was successfully changed.\n"
        f"Time: {now_utc}\n"
        f"IP Address: {client_ip}\n\n"
        f"If you initiated this change, no further action is required.\n"
        f"If you did NOT change your password, please contact support and reset your password immediately.\n\n"
        f"The Paperplane PDF Security Team\n{PAPERPLANE_PUBLIC_URL}"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0d1416; color: #f0f5f4; margin: 0; padding: 32px 16px;">
  <div style="max-width: 540px; margin: 0 auto; background-color: #141e21; border: 1px solid #28393d; border-radius: 12px; padding: 28px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
      <div style="background-color: #ff4b26; width: 32px; height: 32px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; color: #ffffff; text-align: center; line-height: 32px;">P</div>
      <span style="font-size: 18px; font-weight: 700; color: #f0f5f4; margin-left: 8px;">Paperplane PDF</span>
    </div>
    <h2 style="font-size: 20px; color: #f0f5f4; margin-top: 0; margin-bottom: 12px;">Password Changed Successfully</h2>
    <p style="color: #a3b8b6; font-size: 14px; line-height: 1.5; margin-bottom: 20px;">
      The password for your Paperplane PDF account (<strong style="color: #ffffff;">{to_email}</strong>) was recently updated.
    </p>
    <div style="background-color: #1a2528; border: 1px solid #33484c; border-radius: 8px; padding: 14px; margin-bottom: 24px; font-size: 13px;">
      <div style="margin-bottom: 6px;"><strong style="color: #a3b8b6;">Changed At:</strong> <span style="color: #f0f5f4;">{now_utc}</span></div>
      <div><strong style="color: #a3b8b6;">Request IP:</strong> <span style="color: #f0f5f4;">{client_ip}</span></div>
    </div>
    <p style="color: #a3b8b6; font-size: 13px; line-height: 1.5;">
      If you performed this action, you can safely disregard this message. If you did not authorize this change, please recover your account immediately.
    </p>
    <div style="border-top: 1px solid #28393d; padding-top: 18px; font-size: 12px; color: #708684; text-align: center; margin-top: 24px;">
      Paperplane PDF &middot; Ephemeral Document Infrastructure
    </div>
  </div>
</body>
</html>"""
    return _dispatch_email(to_email, subject, html_body, text_body)
