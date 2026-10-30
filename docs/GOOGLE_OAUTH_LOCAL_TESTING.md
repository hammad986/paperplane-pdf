# Google OAuth 2.0 Local Testing & Configuration Guide

This guide describes how to configure and test **Sign in with Google** locally for Paperplane PDF using Google Identity Services (GIS).

---

## 1. Overview of Authentication Architecture

Paperplane PDF uses the official **Google Identity Services (GIS)** popup & JavaScript callback flow.

1. The browser loads Google's official GIS library (`https://accounts.google.com/gsi/client`).
2. When the user clicks "Continue with Google", a secure Google OAuth popup opens.
3. Upon user authorization, Google returns a cryptographically signed OpenID Connect ID token (`credential`).
4. The frontend submits the ID token to `POST /api/auth/google`.
5. The backend validates the token cryptographically:
   - Verifies the signature against Google's public JSON Web Key Sets (JWKS).
   - Validates audience (`aud == GOOGLE_CLIENT_ID`).
   - Validates issuer (`iss` is `accounts.google.com` or `https://accounts.google.com`).
   - Ensures `email_verified == true`.
6. Upon successful verification, an internal user account and session token are created in SQLite, and an `HttpOnly` cookie is set.

> [!NOTE]
> Because Paperplane uses the client-side credential callback flow, an **Authorized redirect URI is NOT required**. Only **Authorized JavaScript origins** need to be registered in Google Cloud Console.

---

## 2. Google Cloud Console Step-by-Step Setup

### Step 1: Create or Select a Google Cloud Project
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown at the top and select **New Project**.
3. Name the project `Paperplane PDF` and click **Create**.

### Step 2: Configure the OAuth Consent Screen
1. Navigate to **APIs & Services** > **OAuth consent screen**.
2. Select **External** user type and click **Create**.
3. Enter App Information:
   - **App name**: `Paperplane PDF`
   - **User support email**: Select your email address.
   - **Developer contact information**: Enter your email address.
4. Click **Save and Continue**.
5. **Scopes**: Click **Add or Remove Scopes**, select `openid`, `.../auth/userinfo.email`, and `.../auth/userinfo.profile`. Click **Update**, then **Save and Continue**.
6. **Test Users**: If the app status is in "Testing" mode, click **Add Users** and add the Google email account(s) you will use for testing. Click **Save and Continue**.

### Step 3: Create OAuth Client ID
1. Navigate to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Set **Application type**: **Web application**.
4. Set **Name**: `Paperplane Local Development`.
5. Under **Authorized JavaScript origins**, click **Add URI** and enter:
   - `http://localhost:8501`
   - `http://127.0.0.1:8501`
   - `http://localhost`
6. Leave **Authorized redirect URIs** empty.
7. Click **Create**.
8. A modal will display your **Client ID** and **Client Secret**.

---

## 3. Configuring Local Environment Variables

Add the credentials to your local `.env` file (do not commit `.env` to git):

```ini
# Google OAuth2 Credentials for Local Testing
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
# Note: Google Identity Services (GIS) client-side ID token verification requires only GOOGLE_CLIENT_ID.
# Do not store or commit production client secrets. If a client secret was previously exposed, revoke it immediately in Google Cloud Console.
```

Restart the Paperplane server:

```bash
python app.py
```

---

## 4. Manual End-to-End Testing Procedure

1. Open `http://127.0.0.1:8501` or `http://localhost:8501` in your browser.
2. Click **Sign In** (or the Profile card in the sidebar).
3. The authentication modal displays the **Continue with Google** button.
4. Click **Continue with Google**:
   - A Google account selection popup opens.
   - Choose your testing Google account.
5. Upon confirmation:
   - The popup closes.
   - A notification toast confirms: *"Signed in with Google successfully."*
   - The user profile in the sidebar changes from `Guest Explorer` to your Google account email.
6. Verify Session State:
   - Inspect network request to `GET /api/auth/me`. The response returns `authenticated: true` and your email.
   - Cookie `paperplane_token` is stored as an `HttpOnly` cookie.
7. Verify Logout:
   - Click the profile card or settings modal and click **Sign Out**.
   - Network call `POST /api/auth/logout` invalidates the SQLite session.
   - Profile resets to `Guest Explorer`.

---

## 5. Troubleshooting Common Issues

| Error | Cause | Resolution |
| :--- | :--- | :--- |
| **`origin_mismatch` / `gsi_logger`** | The URL in your address bar is not in the Authorized JavaScript origins list. | Ensure the exact URL (including port `8501`) is added to **Authorized JavaScript origins** in Google Cloud Console. |
| **`access_denied` / 403 Forbidden** | OAuth consent screen is in "Testing" mode and your account is not a designated test user. | Go to **OAuth consent screen** > **Test users** and add your Google email address. |
| **Popup blocked by browser** | Browser popup blocker prevented the Google sign-in window from opening. | Click the popup icon in your address bar and allow popups for `127.0.0.1` and `localhost`. |
| **503 Service Unavailable** | `GOOGLE_CLIENT_ID` is empty or not loaded from `.env`. | Verify that `GOOGLE_CLIENT_ID` is defined in `.env` and restart `python app.py`. |
| **401 Invalid token / audience mismatch** | Token was generated for a different client ID. | Verify the `GOOGLE_CLIENT_ID` in `.env` matches the client ID registered in Google Cloud Console. |

---

## 6. Distinctions Between Local Testing and Production Setup

| URL Property | Local Development | Production Environment |
| :--- | :--- | :--- |
| **Application Homepage** | `http://127.0.0.1:8501/` or `http://localhost:8501/` | `https://pdf.yourdomain.com/` |
| **Authorized JavaScript Origins** | `http://localhost:8501`, `http://127.0.0.1:8501` | `https://pdf.yourdomain.com` |
| **Authorized Redirect URIs** | None (GIS popup flow) | None (GIS popup flow) |
| **Privacy Policy URL** | `http://localhost:8501/privacy` | `https://pdf.yourdomain.com/privacy` |
| **Terms of Service URL** | `http://localhost:8501/terms` | `https://pdf.yourdomain.com/terms` |
| **Protocol** | HTTP (permitted for localhost only) | Strict HTTPS required |
