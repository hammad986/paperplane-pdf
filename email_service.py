from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

logger = logging.getLogger("paperplane.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip()
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


def _dispatch_email(to_email: str, subject: str, html_body: str, text_body: str, *, allow_simulated: bool = True) -> bool:
    """Unified email dispatcher: supports standard SMTP with TLS, Resend REST API, and development preview logging."""
    if SMTP_ENABLED and SMTP_HOST:
        smtp_ok = _send_smtp(to_email, subject, html_body, text_body)
        if smtp_ok:
            return True
        logger.warning("SMTP dispatch failed, checking Resend API fallback...")

    if RESEND_API_KEY:
        resend_ok = _send_resend_api(to_email, subject, html_body, text_body)
        if resend_ok:
            return True
        logger.warning("Resend API failed, checking SMTP fallback...")

    if allow_simulated:
        logger.info(
            "Email dispatch simulated for %s (Subject: %s)\n[DISPATCH PREVIEW]:\n%s",
            to_email, subject, text_body
        )
        return True
    logger.error("Transactional email was not delivered because no configured provider accepted the message.")
    return False


def send_otp_email(to_email: str, otp_code: str, purpose: str = "login") -> bool:
    """Sends a 6-digit one-time password (OTP) verification email for signup or login."""
    is_signup = purpose.lower().strip() == "signup"
    action_name = "Confirm Your Account" if is_signup else "Sign-In Verification"
    safe_to_email = escape(str(to_email), quote=True)
    subject = f"Paperplane PDF {action_name} verification"

    headline = "Confirm Your Paperplane PDF Account" if is_signup else "Two-Factor Sign-In Verification"
    explanation = (
        f"Thank you for creating an account with <strong style='color: #ffffff;'>{safe_to_email}</strong>. "
        f"Please enter the 6-digit one-time code below to verify your email and activate your account:"
        if is_signup
        else f"A sign-in request was initiated for your Paperplane PDF account (<strong style='color: #ffffff;'>{safe_to_email}</strong>). "
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
    return _dispatch_email(to_email, subject, html_body, text_body, allow_simulated=False)


def send_login_notification(to_email: str, client_ip: str = "Unknown", user_agent: str = "") -> bool:
    """Sends a security notification when a user logs in."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = "Security Alert: Your Paperplane PDF account was logged in"
    safe_to_email = escape(str(to_email), quote=True)
    safe_client_ip = escape(str(client_ip), quote=True)
    safe_user_agent = escape(str(user_agent[:60]), quote=True)
    
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

    ua_row = f'<div><strong style="color: #a3b8b6;">Device:</strong> <span style="color: #f0f5f4;">{safe_user_agent}</span></div>' if user_agent else ""

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
      Your Paperplane PDF account (<strong style="color: #ffffff;">{safe_to_email}</strong>) was successfully logged in.
    </p>
    <div style="background-color: #1a2528; border: 1px solid #33484c; border-radius: 8px; padding: 14px; margin-bottom: 24px; font-size: 13px;">
      <div style="margin-bottom: 6px;"><strong style="color: #a3b8b6;">Timestamp:</strong> <span style="color: #f0f5f4;">{now_utc}</span></div>
      <div style="margin-bottom: 6px;"><strong style="color: #a3b8b6;">Client IP:</strong> <span style="color: #f0f5f4;">{safe_client_ip}</span></div>
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
    return _dispatch_email(to_email, subject, html_body, text_body, allow_simulated=False)


def send_admin_login_otp(to_email: str, otp_code: str, client_ip: str = "Unknown") -> bool:
    """Dispatches a high-priority 6-digit OTP for owner admin authentication."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_client_ip = escape(str(client_ip), quote=True)
    subject = "Paperplane PDF admin sign-in verification"

    text_body = (
        f"Admin Sign-In Verification\n\n"
        f"A login request was initiated for the Paperplane PDF Admin Console.\n\n"
        f"Your 6-digit verification code is: {otp_code}\n\n"
        f"Time: {now_utc}\n"
        f"IP: {client_ip}\n"
        f"Validity: 10 minutes\n\n"
        f"If you did not initiate this login, your credentials may be compromised. Lock down the server immediately.\n\n"
        f"— Paperplane PDF Security System"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b1113; color: #f0f5f4; margin: 0; padding: 32px 16px;">
  <div style="max-width: 540px; margin: 0 auto; background-color: #141f22; border: 1px solid #26373b; border-radius: 12px; padding: 28px; box-shadow: 0 8px 30px rgba(0,0,0,0.5);">
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
      <div style="background-color: #ff4b26; width: 34px; height: 34px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; color: #ffffff; text-align: center; line-height: 34px;">P</div>
      <span style="font-size: 18px; font-weight: 700; color: #f0f5f4; margin-left: 8px;">Paperplane Admin Security</span>
    </div>
    <h2 style="font-size: 20px; color: #f0f5f4; margin-top: 0; margin-bottom: 12px;">Admin Authentication OTP</h2>
    <p style="color: #8ca3a2; font-size: 14px; line-height: 1.5; margin-bottom: 20px;">
      A sign-in request was initiated for the Paperplane Owner Console from IP: <strong style="color: #ffffff;">{safe_client_ip}</strong>.
      Enter the one-time code below to unlock the dashboard:
    </p>
    <div style="font-size: 38px; font-weight: 900; letter-spacing: 12px; color: #ff4b26; background: #0f181a; border: 2px dashed #ff4b26; padding: 18px 24px; text-align: center; border-radius: 10px; margin: 24px 0; font-family: monospace;">
      {otp_code}
    </div>
    <div style="background-color: #0f181a; border: 1px solid #233438; border-radius: 8px; padding: 14px; margin-bottom: 24px; font-size: 13px;">
      <div style="margin-bottom: 6px;"><strong style="color: #8ca3a2;">Time:</strong> <span style="color: #f0f5f4;">{now_utc}</span></div>
      <div style="margin-bottom: 6px;"><strong style="color: #8ca3a2;">Validity:</strong> <span style="color: #34d399;">10 minutes</span></div>
      <div><strong style="color: #8ca3a2;">Notice:</strong> <span style="color: #f87171;">Never share this code with anyone.</span></div>
    </div>
    <div style="border-top: 1px solid #26373b; padding-top: 16px; font-size: 12px; color: #64748b; text-align: center;">
      Paperplane PDF &middot; Zero-Trust Ephemeral Infrastructure
    </div>
  </div>
</body>
</html>"""
    return _dispatch_email(to_email, subject, html_body, text_body, allow_simulated=False)


def send_admin_lockout_alert(to_email: str, client_ip: str = "Unknown", failure_reason: str = "") -> bool:
    """Dispatches a critical security lockout notification after 3 failed admin login attempts."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = "🚨 CRITICAL: Admin Console Locked (3 Failed Attempts) — Paperplane PDF"
    safe_client_ip = escape(str(client_ip), quote=True)
    safe_failure_reason = escape(str(failure_reason or "3 consecutive failed attempts on admin secret key/code"), quote=True)

    text_body = (
        f"CRITICAL SECURITY ALERT: ADMIN CONSOLE LOCKED\n\n"
        f"3 consecutive failed admin login attempts were detected on Paperplane PDF.\n\n"
        f"Action Taken: The Admin Console has been LOCKED FOR 24 HOURS.\n"
        f"No admin logins will be permitted until the 24-hour lockout expires.\n\n"
        f"Timestamp: {now_utc}\n"
        f"Source IP Address: {client_ip}\n"
        f"Reason: {failure_reason or '3 consecutive failed attempts on admin secret key/code'}\n\n"
        f"If this was NOT you, an unauthorized party may be attempting to access your administrative dashboard.\n"
        f"Server logs have been recorded with source IP and headers.\n\n"
        f"— Paperplane PDF Security Sentinel"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b1113; color: #f0f5f4; margin: 0; padding: 32px 16px;">
  <div style="max-width: 560px; margin: 0 auto; background-color: #1a0f0f; border: 2px solid #ef4444; border-radius: 12px; padding: 28px; box-shadow: 0 8px 32px rgba(239,68,68,0.25);">
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
      <div style="background-color: #ef4444; width: 34px; height: 34px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; color: #ffffff; text-align: center; line-height: 34px; font-size: 18px;">⚠️</div>
      <span style="font-size: 18px; font-weight: 800; color: #f87171; margin-left: 8px;">SECURITY LOCKOUT ENFORCED</span>
    </div>
    <h2 style="font-size: 20px; color: #ffffff; margin-top: 0; margin-bottom: 12px;">Admin Console Locked (3 Failed Attempts)</h2>
    <p style="color: #fca5a5; font-size: 14px; line-height: 1.5; margin-bottom: 20px;">
      3 consecutive incorrect login attempts were recorded for the Paperplane Owner Console.
      To prevent brute-force attacks, the console has been <strong>automatically locked for 24 hours</strong>.
    </p>
    <div style="background-color: #271414; border: 1px solid #7f1d1d; border-radius: 8px; padding: 16px; margin-bottom: 24px; font-size: 13px;">
      <div style="margin-bottom: 8px;"><strong style="color: #fca5a5;">Lock Duration:</strong> <span style="color: #ef4444; font-weight: 700;">24 Hours (No logins accepted)</span></div>
      <div style="margin-bottom: 8px;"><strong style="color: #fca5a5;">Detection Time:</strong> <span style="color: #ffffff;">{now_utc}</span></div>
      <div style="margin-bottom: 8px;"><strong style="color: #fca5a5;">Source IP:</strong> <span style="font-family: monospace; color: #ffffff;">{safe_client_ip}</span></div>
      <div><strong style="color: #fca5a5;">Cause:</strong> <span style="color: #ffffff;">{safe_failure_reason}</span></div>
    </div>
    <p style="color: #991b1b; font-size: 13px; line-height: 1.5; margin-bottom: 20px;">
      If you did not initiate these attempts, your server is actively resisting an unauthorized intrusion. The audit trail has captured all incoming network telemetry.
    </p>
    <div style="border-top: 1px solid #7f1d1d; padding-top: 16px; font-size: 12px; color: #7f1d1d; text-align: center;">
      Paperplane PDF &middot; Automated Intrusion Defense Sentinel
    </div>
  </div>
</body>
</html>"""
    return _dispatch_email(to_email, subject, html_body, text_body, allow_simulated=False)


def send_waitlist_alert(signup_email: str, platform: str = "all", waitlist_position: int = 0, ip_address: str = "") -> bool:
    """Notify the admin when a new user joins the waitlist."""
    admin_email = os.getenv("ADMIN_ALERT_EMAIL", "").strip()
    if not admin_email:
        logger.warning("Waitlist notification skipped because ADMIN_ALERT_EMAIL is not configured.")
        return False
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_subject_email = re.sub(r"[\r\n\x00-\x1f\x7f]", "", str(signup_email))[:254]
    subject = f"🎉 New Waitlist Signup — {safe_subject_email}"
    safe_signup_email = escape(str(signup_email), quote=True)
    safe_platform = escape(str(platform), quote=True)
    safe_ip_address = escape(str(ip_address or "unknown"), quote=True)

    text_body = (
        f"New Paperplane PDF waitlist signup!\n\n"
        f"Email:    {signup_email}\n"
        f"Platform: {platform}\n"
        f"Position: #{waitlist_position}\n"
        f"Time:     {now_utc}\n"
        f"IP:       {ip_address or 'unknown'}\n\n"
        f"View dashboard: {PAPERPLANE_PUBLIC_URL}/admin\n\n"
        f"— Paperplane PDF Notifications"
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
    <h2 style="font-size: 20px; color: #ff4b26; margin-top: 0; margin-bottom: 12px;">🎉 New Waitlist Signup!</h2>
    <div style="background-color: #1a2528; border: 1px solid #33484c; border-radius: 8px; padding: 14px; margin-bottom: 24px; font-size: 14px;">
      <div style="margin-bottom: 8px;"><strong style="color: #a3b8b6;">Email:</strong> <span style="color: #f0f5f4;">{safe_signup_email}</span></div>
      <div style="margin-bottom: 8px;"><strong style="color: #a3b8b6;">Platform:</strong> <span style="color: #f0f5f4;">{safe_platform}</span></div>
      <div style="margin-bottom: 8px;"><strong style="color: #a3b8b6;">Position:</strong> <span style="color: #ff4b26; font-weight: 700;">#{waitlist_position}</span></div>
      <div style="margin-bottom: 8px;"><strong style="color: #a3b8b6;">Signed up at:</strong> <span style="color: #f0f5f4;">{now_utc}</span></div>
      <div><strong style="color: #a3b8b6;">IP Address:</strong> <span style="color: #f0f5f4;">{safe_ip_address}</span></div>
    </div>
    <div style="border-top: 1px solid #28393d; padding-top: 18px; font-size: 12px; color: #708684; text-align: center;">
      Paperplane PDF &middot; Admin Notification System
    </div>
  </div>
</body>
</html>"""
    return _dispatch_email(admin_email, subject, html_body, text_body)


def send_password_reset_email(to_email: str, reset_token: str, base_url: str | None = None) -> bool:
    """Sends a cryptographically secure 1-hour password reset link."""
    domain = (base_url or PAPERPLANE_PUBLIC_URL).rstrip("/")
    reset_url = f"{domain}/?reset_token={reset_token}"
    safe_to_email = escape(str(to_email), quote=True)
    safe_reset_url = escape(reset_url, quote=True)
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
      We received a request to reset the password for <strong style="color: #ffffff;">{safe_to_email}</strong>. Click the button below to choose a new password. This link expires in 60 minutes.
    </p>
    <div style="text-align: center; margin-bottom: 28px;">
      <a href="{safe_reset_url}" style="background-color: #ff4b26; color: #ffffff; padding: 12px 28px; font-size: 14px; font-weight: 600; text-decoration: none; border-radius: 8px; display: inline-block;">
        Reset Password &rarr;
      </a>
    </div>
    <p style="color: #708684; font-size: 12px; line-height: 1.4; margin-bottom: 20px;">
      Or copy and paste this URL into your browser:<br>
      <a href="{safe_reset_url}" style="color: #ff4b26; word-break: break-all;">{safe_reset_url}</a>
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
    return _dispatch_email(to_email, subject, html_body, text_body, allow_simulated=False)


def send_password_changed_notification(to_email: str, client_ip: str = "Unknown") -> bool:
    """Sends a security confirmation when the password has been modified."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = "Security Alert: Your Paperplane PDF Password Was Changed"
    safe_to_email = escape(str(to_email), quote=True)
    safe_client_ip = escape(str(client_ip), quote=True)

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
      The password for your Paperplane PDF account (<strong style="color: #ffffff;">{safe_to_email}</strong>) was recently updated.
    </p>
    <div style="background-color: #1a2528; border: 1px solid #33484c; border-radius: 8px; padding: 14px; margin-bottom: 24px; font-size: 13px;">
      <div style="margin-bottom: 6px;"><strong style="color: #a3b8b6;">Changed At:</strong> <span style="color: #f0f5f4;">{now_utc}</span></div>
      <div><strong style="color: #a3b8b6;">Request IP:</strong> <span style="color: #f0f5f4;">{safe_client_ip}</span></div>
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
    return _dispatch_email(to_email, subject, html_body, text_body, allow_simulated=False)
