// Paperplane PDF — Owner Admin Dashboard Script v2.1
// 3-Factor Authentication (Key + Secret Code + Email OTP)
// Multi-segment Visual Analytics, Revenue & Bank Payouts, Feedback & AI Configuration
// Strict Content Security Policy (CSP) compliant — No inline event handlers

(function () {
  const planDisplayNames = {
    free: "Free",
    exam_pass: "Exam Pass",
    student_pro: "Student & Educator",
    pro: "Pro",
    developer: "Developer",
    dev: "Developer (legacy)",
    cyber_cafe: "All-In-One Pro & Developer",
  };
  const planDisplayName = tier => planDisplayNames[tier] || String(tier || "unknown").replaceAll("_", " ");

  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has("session") || urlParams.has("key")) {
    urlParams.delete("session");
    urlParams.delete("key");
    const query = urlParams.toString();
    window.history.replaceState({}, document.title, `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  }
  let sessionToken = sessionStorage.getItem("pp_admin_session") || "";
  let adminChallenge = "";
  let adminCodeChallenge = "";
  let recoveryChallenge = "";
  let usersData = [];
  let waitlistData = [];
  let auditData = [];
  let revenueData = null;
  let feedbackData = [];
  let feedbackRequestPending = false;
  let feedbackTimer = null;
  let supportData = [];
  let activeSupportFilter = "all";
  let aiConfigData = null;

  let currentTab = "users";
  let activeTierFilter = "all";
  let activeFeedbackFilter = "all";

  document.addEventListener("DOMContentLoaded", () => {
    initEyeToggles();
    initEventListeners();
    checkInitialState();
  });

  // --- Password Reveal (Eye Toggle) ---
  function initEyeToggles() {
    setupToggle("toggle-key-eye", "admin-key-input");
    setupToggle("toggle-code-eye", "admin-code-input");
    setupToggle("toggle-ai-key-eye", "ai-apikey-input");
  }

  function setupToggle(btnId, inputId) {
    const btn = document.getElementById(btnId);
    const input = document.getElementById(inputId);
    if (!btn || !input) return;

    btn.addEventListener("click", () => {
      if (input.type === "password") {
        input.type = "text";
        btn.textContent = "🙈";
      } else {
        input.type = "password";
        btn.textContent = "👁️";
      }
    });
  }

  // --- Event Listeners Setup ---
  function initEventListeners() {
    const btnSubmit1 = document.getElementById("btn-submit-step1");
    const btnSubmit2 = document.getElementById("btn-submit-step2");
    const btnSubmit3 = document.getElementById("btn-submit-step3");
    const btnBack1 = document.getElementById("btn-back-step1");
    const btnBackFrom3 = document.getElementById("btn-back-step1-from-3");
    const btnVerifyRecovery = document.getElementById("btn-verify-recovery");
    const btnResendRecovery = document.getElementById("btn-resend-recovery");
    const btnRefresh = document.getElementById("btn-refresh");
    const btnLogout = document.getElementById("btn-logout");
    const searchInput = document.getElementById("search-input");
    const btnCleanProbes = document.getElementById("btn-clean-probes");
    const btnSaveAi = document.getElementById("btn-save-ai");
    const btnTestAi = document.getElementById("btn-test-ai");

    if (btnSubmit1) btnSubmit1.addEventListener("click", handleStep1Submit);
    if (btnSubmit2) btnSubmit2.addEventListener("click", handleStep2Submit);
    if (btnSubmit3) btnSubmit3.addEventListener("click", handleStep3Submit);
    if (btnBack1) btnBack1.addEventListener("click", () => switchScreen("step1"));
    if (btnBackFrom3) btnBackFrom3.addEventListener("click", () => { adminCodeChallenge = ""; switchScreen("step1"); });
    if (btnVerifyRecovery) btnVerifyRecovery.addEventListener("click", handleRecoveryVerify);
    if (btnResendRecovery) btnResendRecovery.addEventListener("click", handleRecoverySend);
    if (btnRefresh) btnRefresh.addEventListener("click", fetchDashboardData);
    if (btnLogout) btnLogout.addEventListener("click", handleLogout);
    if (btnCleanProbes) btnCleanProbes.addEventListener("click", handleCleanProbes);
    if (btnSaveAi) btnSaveAi.addEventListener("click", handleSaveAiConfig);
    if (btnTestAi) btnTestAi.addEventListener("click", handleTestAiConnection);

    // Enter key shortcuts
    const keyInput = document.getElementById("admin-key-input");
    const codeInput = document.getElementById("admin-code-input");
    const otpInput = document.getElementById("admin-otp-input");
    const recoveryOtpInput = document.getElementById("recovery-otp-input");

    if (keyInput) keyInput.addEventListener("keypress", (e) => { if (e.key === "Enter") handleStep1Submit(); });
    if (otpInput) otpInput.addEventListener("keypress", (e) => { if (e.key === "Enter") handleStep2Submit(); });
    if (codeInput) codeInput.addEventListener("keypress", (e) => { if (e.key === "Enter") handleStep3Submit(); });
    if (recoveryOtpInput) recoveryOtpInput.addEventListener("keypress", (e) => { if (e.key === "Enter") handleRecoveryVerify(); });

    // Tabs
    const tabUsersBtn = document.getElementById("tab-users-btn");
    const tabRevenueBtn = document.getElementById("tab-revenue-btn");
    const tabFeedbackBtn = document.getElementById("tab-feedback-btn");
    const tabAiBtn = document.getElementById("tab-ai-btn");
    const tabWaitlistBtn = document.getElementById("tab-waitlist-btn");
    const tabAuditBtn = document.getElementById("tab-audit-btn");

    if (tabUsersBtn) tabUsersBtn.addEventListener("click", () => switchTab("users"));
    if (tabRevenueBtn) tabRevenueBtn.addEventListener("click", () => switchTab("revenue"));
    if (tabFeedbackBtn) tabFeedbackBtn.addEventListener("click", () => switchTab("feedback"));
    document.getElementById("tab-support-btn")?.addEventListener("click", () => switchTab("support"));
    document.getElementById("tab-sessions-btn")?.addEventListener("click", () => switchTab("sessions"));
    document.getElementById("sessions-tbody")?.addEventListener("click", logoutOtherAdmin);
    document.getElementById("users-tbody")?.addEventListener("click", updateUserAccess);
    if (tabAiBtn) tabAiBtn.addEventListener("click", () => switchTab("ai"));
    if (tabWaitlistBtn) tabWaitlistBtn.addEventListener("click", () => switchTab("waitlist"));
    if (tabAuditBtn) tabAuditBtn.addEventListener("click", () => switchTab("audit"));

    // Quick filter pills for Users
    document.querySelectorAll(".filter-pills:not(.feedback-pills) .pill").forEach(pill => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".filter-pills:not(.feedback-pills) .pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        activeTierFilter = pill.getAttribute("data-filter") || "all";
        applyFilters();
      });
    });

    // Quick filter pills for Feedback
    document.querySelectorAll(".feedback-pills .pill").forEach(pill => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".feedback-pills .pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        activeFeedbackFilter = pill.getAttribute("data-fb-filter") || "all";
        applyFilters();
      });
    });

    // Quick filter pills & actions for Support Tickets
    document.querySelectorAll(".support-pills .pill").forEach(pill => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".support-pills .pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        activeSupportFilter = pill.getAttribute("data-support-filter") || "all";
        applyFilters();
      });
    });
    document.getElementById("support-tbody")?.addEventListener("click", (e) => {
      const statusBtn = e.target.closest(".btn-support-status");
      if (statusBtn) {
        const ticketId = statusBtn.getAttribute("data-ticket-id");
        const nextStatus = statusBtn.getAttribute("data-next-status");
        handleSupportStatus(ticketId, nextStatus);
        return;
      }
      const delBtn = e.target.closest(".btn-delete-support");
      if (delBtn) {
        const ticketId = delBtn.getAttribute("data-ticket-id");
        handleDeleteSupport(ticketId);
      }
    });

    if (searchInput) searchInput.addEventListener("input", applyFilters);

    // CSV Exports (secured via session header)
    const btnExportUsers = document.getElementById("btn-export-users");
    const btnExportWaitlist = document.getElementById("btn-export-waitlist");

    if (btnExportUsers) btnExportUsers.addEventListener("click", () => downloadCsv("/api/admin/users/export.csv", "paperplane_users.csv"));
    if (btnExportWaitlist) btnExportWaitlist.addEventListener("click", () => downloadCsv("/api/admin/waitlist/export.csv", "paperplane_waitlist.csv"));

    // Event delegation for dynamically rendered table buttons
    document.addEventListener("click", (e) => {
      const deleteUserBtn = e.target.closest(".btn-delete-user");
      if (deleteUserBtn) {
        const userId = deleteUserBtn.getAttribute("data-user-id");
        const userEmail = deleteUserBtn.getAttribute("data-user-email");
        handleDeleteUser(userId, userEmail);
        return;
      }

      const deleteFeedbackBtn = e.target.closest(".btn-delete-feedback");
      if (deleteFeedbackBtn) {
        const feedbackId = deleteFeedbackBtn.getAttribute("data-feedback-id");
        handleDeleteFeedback(feedbackId);
        return;
      }
    });
  }

  // --- Initial State Checking ---
  async function checkInitialState() {
    try {
      const resp = await fetch("/api/admin/auth/status", { cache: "no-store" });
      const data = await resp.json();

      if (data.verification_required) {
        showRecoveryGate("");
        return;
      }
      sessionStorage.removeItem("pp_admin_recovery_challenge");
    } catch (e) {
      console.warn("Status check failed:", e);
    }

    if (sessionToken) {
      validateSession();
    } else {
      switchScreen("step1");
    }
  }

  async function validateSession() {
    try {
      const resp = await fetch("/api/admin/dashboard", {
        headers: { "X-Admin-Session": sessionToken }
      });

      if (resp.status === 200) {
        switchScreen("dashboard");
        fetchDashboardData();
      } else {
        sessionStorage.removeItem("pp_admin_session");
        sessionToken = "";
        switchScreen("step1");
      }
    } catch (err) {
      switchScreen("step1");
    }
  }

  function showRecoveryGate(challenge = "") {
    const resolvedChallenge = challenge || sessionStorage.getItem("pp_admin_recovery_challenge") || "";
    if (resolvedChallenge) {
      recoveryChallenge = resolvedChallenge;
      sessionStorage.setItem("pp_admin_recovery_challenge", resolvedChallenge);
    } else {
      recoveryChallenge = "";
    }
    adminChallenge = "";
    adminCodeChallenge = "";
    switchScreen("recovery");
    const statusBox = document.getElementById("recovery-status");
    const errBox = document.getElementById("recovery-error");
    hideError(errBox);
    if (statusBox) {
      statusBox.textContent = resolvedChallenge
        ? "A 6-digit verification code was sent to the configured superadmin email address. Enter it below to unlock 3 fresh attempts."
        : "3 consecutive failed attempts detected. Click Send / Resend Verification Code below to get a 6-digit code in the superadmin inbox.";
    }
    const input = document.getElementById("recovery-otp-input");
    if (input) {
      input.value = "";
      input.focus();
    }
  }

  async function handleRecoverySend() {
    const errBox = document.getElementById("recovery-error");
    const statusBox = document.getElementById("recovery-status");
    const btn = document.getElementById("btn-resend-recovery");
    hideError(errBox);
    if (btn) { btn.disabled = true; btn.textContent = "Sending..."; }
    try {
      const resp = await fetch("/api/admin/auth/recovery/send", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.challenge) {
        recoveryChallenge = data.challenge;
        sessionStorage.setItem("pp_admin_recovery_challenge", recoveryChallenge);
        if (statusBox) statusBox.textContent = "Fresh 6-digit verification code sent to the configured superadmin email address.";
      } else {
        showError(errBox, data.detail || "Could not send superadmin verification email.");
      }
    } catch {
      showError(errBox, "Network error sending verification code.");
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "📬 Send / Resend Verification Code"; }
    }
  }

  async function handleRecoveryVerify() {
    const input = document.getElementById("recovery-otp-input");
    const errBox = document.getElementById("recovery-error");
    const btn = document.getElementById("btn-verify-recovery");
    const otp = (input ? input.value : "").trim();
    if (!otp || otp.length < 6) {
      showError(errBox, "Enter the complete 6-digit superadmin verification code.");
      return;
    }
    if (!recoveryChallenge) {
      showError(errBox, "Click Send / Resend Verification Code first.");
      return;
    }
    hideError(errBox);
    if (btn) { btn.disabled = true; btn.textContent = "Verifying..."; }
    try {
      const resp = await fetch("/api/admin/auth/recovery/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otp, challenge: recoveryChallenge })
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.status === "unlocked") {
        recoveryChallenge = "";
        sessionStorage.removeItem("pp_admin_recovery_challenge");
        if (input) input.value = "";
        hideError(document.getElementById("auth-error"));
        switchScreen("step1");
      } else {
        showError(errBox, data.detail || "Invalid or expired verification code.");
      }
    } catch {
      showError(errBox, "Network error verifying recovery OTP.");
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Verify Code & Grant 3 Attempts →"; }
    }
  }

  // --- Step 1 Submit (Owner Email + Secret Key -> OTP) ---
  async function handleStep1Submit() {
    const keyInput = document.getElementById("admin-key-input");
    const errBox = document.getElementById("auth-error");
    const btn = document.getElementById("btn-submit-step1");

    const key = (keyInput ? keyInput.value : "").trim();
    const email = document.getElementById("admin-email-input")?.value.trim();
    if (!email || !key) {
      showError(errBox, "Enter your owner email and admin secret key.");
      return;
    }

    btn.disabled = true;
    btn.textContent = "Verifying...";
    hideError(errBox);

    try {
      const resp = await fetch("/api/admin/auth/step1", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, admin_key: key })
      });

      const data = await resp.json().catch(() => ({}));

      if (resp.status === 200 && data.challenge) {
        adminChallenge = data.challenge;
        if (keyInput) keyInput.value = "";
        switchScreen("step2");
        const otpInput = document.getElementById("admin-otp-input");
        if (otpInput) {
          otpInput.value = "";
          otpInput.focus();
        }
      } else if (data.verification_required) {
        showRecoveryGate(data.recovery_challenge || "");
      } else {
        showError(errBox, data.detail || "Invalid owner email or admin secret key.");
      }
    } catch (err) {
      showError(errBox, "Network error: unable to reach authentication server.");
    } finally {
      btn.disabled = false;
      btn.textContent = "Verify Key & Send Email OTP →";
    }
  }

  // --- Step 2 Submit (OTP -> Secret Code Step 3) ---
  async function handleStep2Submit() {
    const otpInput = document.getElementById("admin-otp-input");
    const errBox = document.getElementById("otp-error");
    const btn = document.getElementById("btn-submit-step2");

    const otp = (otpInput ? otpInput.value : "").trim();
    if (!otp || otp.length < 6) {
      showError(errBox, "Please enter the complete 6-digit verification code.");
      return;
    }

    btn.disabled = true;
    btn.textContent = "Verifying OTP...";
    hideError(errBox);

    try {
      const resp = await fetch("/api/admin/auth/step2", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otp, challenge: adminChallenge })
      });

      const data = await resp.json().catch(() => ({}));

      if (resp.status === 200 && data.code_challenge) {
        adminChallenge = "";
        adminCodeChallenge = data.code_challenge;
        if (otpInput) otpInput.value = "";
        switchScreen("step3");
        const codeInput = document.getElementById("admin-code-input");
        if (codeInput) {
          codeInput.value = "";
          codeInput.focus();
        }
      } else if (data.verification_required) {
        showRecoveryGate(data.recovery_challenge || "");
      } else {
        showError(errBox, data.detail || "Invalid or expired OTP code.");
      }
    } catch (err) {
      showError(errBox, "Network error: unable to verify OTP.");
    } finally {
      btn.disabled = false;
      btn.textContent = "Verify Code & Continue →";
    }
  }

  // --- Step 3 Submit (Post-OTP Admin Secret Code) ---
  async function handleStep3Submit() {
    const codeInput = document.getElementById("admin-code-input");
    const errBox = document.getElementById("code-error");
    const btn = document.getElementById("btn-submit-step3");

    const adminCode = (codeInput ? codeInput.value : "").trim();
    if (!adminCode) {
      showError(errBox, "Please enter your Admin Secret Code.");
      return;
    }

    btn.disabled = true;
    btn.textContent = "Unlocking...";
    hideError(errBox);

    try {
      const resp = await fetch("/api/admin/auth/step3", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code_challenge: adminCodeChallenge, admin_code: adminCode })
      });

      const data = await resp.json().catch(() => ({}));

      if (resp.status === 200 && data.session_token) {
        adminChallenge = "";
        adminCodeChallenge = "";
        if (codeInput) codeInput.value = "";
        sessionToken = data.session_token;
        sessionStorage.setItem("pp_admin_session", sessionToken);
        switchScreen("dashboard");
        fetchDashboardData();
      } else if (data.verification_required) {
        showRecoveryGate(data.recovery_challenge || "");
      } else {
        showError(errBox, data.detail || "Invalid Admin Secret Code.");
      }
    } catch (err) {
      showError(errBox, "Network error: unable to verify Admin Secret Code.");
    } finally {
      btn.disabled = false;
      btn.textContent = "Verify Secret Code & Unlock Console →";
    }
  }

  // --- Logout ---
  async function handleLogout() {
    try {
      await fetch("/api/admin/auth/logout", {
        method: "POST",
        headers: { "X-Admin-Session": sessionToken }
      });
    } catch (e) {}

    sessionStorage.removeItem("pp_admin_session");
    sessionToken = "";
    adminChallenge = "";
    adminCodeChallenge = "";
    clearInterval(feedbackTimer);
    feedbackTimer = null;
    feedbackData = [];
    supportData = [];
    switchScreen("step1");
  }

  // --- Screen Switcher ---
  function switchScreen(screen) {
    const sRecovery = document.getElementById("recovery-screen");
    const sStep1 = document.getElementById("step1-screen");
    const sStep2 = document.getElementById("step2-screen");
    const sStep3 = document.getElementById("step3-screen");
    const sDash = document.getElementById("dashboard-view");
    const headerActions = document.getElementById("header-actions");

    if (sRecovery) sRecovery.style.display = screen === "recovery" ? "block" : "none";
    if (sStep1) sStep1.style.display = screen === "step1" ? "block" : "none";
    if (sStep2) sStep2.style.display = screen === "step2" ? "block" : "none";
    if (sStep3) sStep3.style.display = screen === "step3" ? "block" : "none";
    if (sDash) sDash.style.display = screen === "dashboard" ? "block" : "none";
    if (headerActions) headerActions.style.display = screen === "dashboard" ? "flex" : "none";

    if (screen === "dashboard") {
      updateClock();
    }
  }

  function showError(el, msg) {
    if (!el) return;
    el.textContent = msg;
    el.style.display = "block";
  }

  function hideError(el) {
    if (!el) return;
    el.style.display = "none";
  }

  // --- Dashboard Data Fetching ---
  async function fetchDashboardData() {
    try {
      const [dashResp, usersResp, waitlistResp, revResp, aiResp, aiHealthResp] = await Promise.all([
        fetch("/api/admin/dashboard", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/users", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/waitlist", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/revenue", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/ai-config", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/ai-health", { headers: { "X-Admin-Session": sessionToken } })
      ]);

      if (dashResp.status === 401 || dashResp.status === 403) {
        handleLogout();
        return;
      }

      const metrics = await dashResp.json();
      const usersObj = await usersResp.json();
      const waitlistObj = await waitlistResp.json();
      revenueData = await revResp.json().catch(() => null);
      aiConfigData = await aiResp.json().catch(() => null);
      const aiHealth = await aiHealthResp.json().catch(() => null);

      // Top Metric Cards
      setElText("m-total-users", metrics.total_users ?? 0);
      setElText("m-new-7d", `${metrics.new_signups_7d ?? 0} new last 7 days`);
      setElText("m-pro-users", metrics.pro_users ?? 0);
      setElText("m-dev-users", metrics.dev_users ?? 0);
      setElText("m-free-users", metrics.free_users ?? 0);
      setElText("m-today-active", metrics.today_active ?? 0);
      setElText("m-total-waitlist", metrics.total_waitlist ?? 0);
      setElText("m-total-jobs", metrics.total_jobs ?? 0);
      setElText("m-jobs-today", `${metrics.jobs_today ?? 0} jobs created today (UTC)`);

      // System Banner
      setElText("live-env-name", (metrics.environment || "production").toUpperCase());
      const headerEnv = document.getElementById("header-env");
      if (headerEnv) headerEnv.textContent = `${(metrics.environment || "Production").toUpperCase()} LIVE`;

      // Render Visual Charts
      renderTierMeter(metrics);
      renderBarChart(metrics.days_trend || []);

      usersData = usersObj.users || [];
      waitlistData = waitlistObj.entries || [];
      auditData = metrics.recent_audits || [];

      setElText("count-users", usersData.length);
      setElText("count-waitlist", waitlistData.length);
      setElText("count-audit", auditData.length);
      setElText("count-feedback", feedbackData.length);

      applyFilters();
      renderWaitlist(waitlistData);
      renderAudits(auditData);
      renderRevenue(revenueData);
      renderAiConfig(aiConfigData);
      renderAiHealth(aiHealth);
      void refreshFeedback();
      void refreshSupport();
      void refreshAdminSessions();
    } catch (err) {
      console.error("Dashboard refresh error:", err);
    }
  }

  async function refreshAdminSessions() {
    if (!sessionToken) return;
    try {
      const response = await fetch("/api/admin/sessions", {
        headers: { "X-Admin-Session": sessionToken }, cache: "no-store"
      });
      if (!response.ok) return;
      const data = await response.json();
      const sessions = data.sessions || [];
      const canRevoke = Boolean(data.can_revoke);
      setElText("count-sessions", sessions.length);
      const note = document.getElementById("sessions-permission-note");
      if (note) {
        note.textContent = canRevoke
          ? "Superadmin access: you can view every active session with device names and remove any unknown or unwanted session."
          : "Read-only session list: view active admin sessions with device names. Only the superadmin (mdhammad2906@gmail.com) can remove sessions.";
      }
      const rows = document.getElementById("sessions-tbody");
      rows.replaceChildren();
      for (const session of sessions) {
        const row = rows.insertRow();
        row.insertCell().textContent = session.email;
        row.insertCell().textContent = session.role === "superadmin" ? "Superadmin" : "Admin";
        row.insertCell().textContent = session.device_name || "Unknown device";
        const ipLoc = [session.client_ip || "unknown", session.location || ""].filter(Boolean).join(" · ");
        row.insertCell().textContent = ipLoc;
        row.insertCell().textContent = new Date(session.created_at * 1000).toLocaleString();
        row.insertCell().textContent = new Date((session.last_active_at || session.created_at) * 1000).toLocaleString();
        row.insertCell().textContent = new Date(session.expires_at * 1000).toLocaleString();
        const action = row.insertCell();
        if (session.current) {
          action.textContent = "This session";
        } else if (canRevoke) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "btn btn-danger btn-xs";
          button.dataset.sessionId = session.id;
          button.textContent = "Remove / Log out";
          action.append(button);
        } else {
          action.textContent = "Superadmin only";
        }
      }
    } catch {
      setElText("count-sessions", "—");
    }
  }

  async function logoutOtherAdmin(event) {
    const button = event.target.closest("[data-session-id]");
    if (!button || !confirm("Log out this admin session?")) return;
    button.disabled = true;
    try {
      const response = await fetch("/api/admin/sessions/" + encodeURIComponent(button.dataset.sessionId), {
        method: "DELETE", headers: { "X-Admin-Session": sessionToken }
      });
      if (!response.ok && response.status !== 404) throw new Error("Logout failed");
      await refreshAdminSessions();
    } catch {
      alert("Could not log out that admin session.");
    } finally {
      button.disabled = false;
    }
  }

  async function refreshFeedback() {
    if (!sessionToken || feedbackRequestPending || document.hidden) return;
    feedbackRequestPending = true;
    const currentSession = sessionToken;
    try {
      const response = await fetch("/api/admin/feedback", {
        headers: { "X-Admin-Session": currentSession },
        cache: "no-store"
      });
      if (currentSession !== sessionToken) return;
      if (response.status === 401) {
        await handleLogout();
        return;
      }
      if (!response.ok) throw new Error("Feedback unavailable");
      const data = await response.json();
      if (currentSession !== sessionToken) return;
      feedbackData = data.feedbacks || [];
      setElText("count-feedback", feedbackData.length);
      setElText("feedback-refresh-status", "Updated " + new Date().toLocaleTimeString());
      if (currentTab === "feedback") applyFilters();
    } catch {
      setElText("feedback-refresh-status", "Could not refresh feedback. Retrying while this tab is open.");
    } finally {
      feedbackRequestPending = false;
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (currentTab === "feedback" && !document.hidden) void refreshFeedback();
  });

  // --- Visual Analytics: Tier Meter ---
  function renderTierMeter(m) {
    const total = Number(m.total_users) || 0;
    const analyticsPlanNames = {
      ...planDisplayNames,
      free: "Free Accounts",
      pro: "Pro Subscribers",
      developer: "Developer Users",
      dev: "Developer Users (legacy)",
    };
    const colors = ["#6b8f71", "#d5a84b", "#5996a8", "#8a75c7", "#d17c61", "#9aabb1", "#aa78a1"];
    const counts = m.tier_breakdown && typeof m.tier_breakdown === "object" ? { ...m.tier_breakdown } : {};
    // Keep the chart's categories stable when a plan currently has no users.
    // Otherwise a missing SQL GROUP BY row hides that plan from the legend.
    ["free", "exam_pass", "pro", "student_pro", "developer", "cyber_cafe"].forEach(tier => {
      if (!Object.hasOwn(counts, tier)) counts[tier] = 0;
    });
    const tiers = Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));
    const meter = document.getElementById("meter-plan-segments");
    const rows = document.getElementById("plan-breakdown-rows");
    if (!meter || !rows) return;
    meter.replaceChildren();
    rows.replaceChildren();
    tiers.forEach(([tier, rawCount], index) => {
      const count = Number(rawCount) || 0;
      const percent = total ? Math.round((count / total) * 100) : 0;
      const label = analyticsPlanNames[tier] || `${planDisplayName(tier)} (other)`;
      const color = colors[index % colors.length];
      if (count > 0) {
        const segment = document.createElement("div");
        segment.className = "meter-seg-plan";
        segment.style.cssText = `background:${color};height:100%;width:${(count / Math.max(total, 1)) * 100}%`;
        segment.title = `${label}: ${count} (${percent}%)`;
        meter.append(segment);
      }
      const tableRow = document.createElement("tr");
      const name = document.createElement("th");
      name.scope = "row";
      const dot = document.createElement("span");
      dot.className = "legend-dot";
      dot.style.backgroundColor = color;
      name.append(dot, document.createTextNode(label));
      const accountCount = document.createElement("td");
      accountCount.textContent = String(count);
      const share = document.createElement("td");
      share.textContent = `${percent}%`;
      tableRow.append(name, accountCount, share);
      rows.append(tableRow);
    });
    setElText("tier-ratio-label", `${total} total accounts`);
  }

  // --- Visual Analytics: 14-Day Signup Bar Chart ---
  function renderBarChart(days) {
    const container = document.getElementById("bar-chart-container");
    if (!container) return;

    const trendDays = (Array.isArray(days) ? days : []).slice(-14);

    if (!trendDays.length) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; margin: auto;">No trend data available.</div>';
      return;
    }

    const countFor = day => {
      const value = Number(day?.count);
      return Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
    };
    const maxCount = Math.max(1, ...trendDays.map(countFor));

    container.innerHTML = trendDays.map(d => {
      const count = countFor(d);
      const dateLabel = escapeHtml(d?.date || "");
      const heightPct = Math.max(6, Math.round((count / maxCount) * 100));
      return `<div class="bar-col">
        <span class="bar-value">${count > 0 ? count : ""}</span>
        <div class="bar-fill" style="height: ${heightPct}%;" title="${dateLabel}: ${count} signups"></div>
        <span class="bar-label">${dateLabel}</span>
      </div>`;
    }).join("");
  }

  // --- Tab Switcher ---
  function switchTab(tab) {
    currentTab = tab;
    const tabs = ["users", "revenue", "feedback", "support", "ai", "waitlist", "audit", "sessions"];

    tabs.forEach(t => {
      const btn = document.getElementById(`tab-${t}-btn`);
      const panel = document.getElementById(`panel-${t}`);
      if (btn) btn.classList.toggle("active", t === tab);
      if (panel) panel.style.display = t === tab ? "block" : "none";
    });

    clearInterval(feedbackTimer);
    feedbackTimer = null;
    if (tab === "sessions") void refreshAdminSessions();
    if (tab === "support") void refreshSupport();
    if (tab === "feedback") {
      void refreshFeedback();
      feedbackTimer = setInterval(refreshFeedback, 8000);
    }
    applyFilters();
  }

  // --- Filters ---
  function applyFilters() {
    const input = document.getElementById("search-input");
    const q = (input ? input.value : "").trim().toLowerCase();

    if (currentTab === "users") {
      let filtered = usersData.filter(u => {
        const matchesQuery = (u.email || "").toLowerCase().includes(q);
        if (!matchesQuery) return false;
        if (activeTierFilter === "all") return true;
        const tier = (u.tier || "free").toLowerCase();
        if (activeTierFilter === "pro") return tier.includes("pro");
        if (activeTierFilter === "developer") return tier.includes("dev") || tier.includes("developer");
        if (activeTierFilter === "free") return tier === "free";
        return true;
      });
      renderUsers(filtered);
    } else if (currentTab === "waitlist") {
      let filtered = waitlistData.filter(e => {
        return (e.email || "").toLowerCase().includes(q) || (e.platform || "").toLowerCase().includes(q);
      });
      renderWaitlist(filtered);
    } else if (currentTab === "audit") {
      let filtered = auditData.filter(a => {
        return (a.email || "").toLowerCase().includes(q) || (a.event_type || "").toLowerCase().includes(q);
      });
      renderAudits(filtered);
    } else if (currentTab === "feedback") {
      let filtered = feedbackData.filter(f => {
        const matchesQuery = (f.email || "").toLowerCase().includes(q) || (f.message || "").toLowerCase().includes(q);
        if (!matchesQuery) return false;
        if (activeFeedbackFilter === "all") return true;
        const cat = (f.category || "general").toLowerCase();
        return cat.includes(activeFeedbackFilter);
      });
      renderFeedback(filtered);
    } else if (currentTab === "support") {
      let filtered = supportData.filter(t => {
        const matchesQuery =
          (t.ticket_ref || "").toLowerCase().includes(q) ||
          (t.email || "").toLowerCase().includes(q) ||
          (t.subject || "").toLowerCase().includes(q) ||
          (t.message || "").toLowerCase().includes(q) ||
          (t.order_id || "").toLowerCase().includes(q);
        if (!matchesQuery) return false;
        if (activeSupportFilter === "all") return true;
        return String(t.status || "open").toLowerCase() === activeSupportFilter;
      });
      renderSupport(filtered);
    }
  }

  // --- Render Tables ---
  function renderUsers(list) {
    const tbody = document.getElementById("users-tbody");
    if (!tbody) return;
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">No matching users found.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(u => {
      const tier = (u.tier || "free").toLowerCase();
      let badgeClass = "badge-free";
      if (tier.includes("pro")) badgeClass = "badge-pro";
      if (tier.includes("dev")) badgeClass = "badge-dev";

      const created = u.created_at ? new Date(u.created_at * 1000).toLocaleString() : "—";
      const lastActive = u.last_active_at ? new Date(u.last_active_at * 1000).toLocaleString() : (u.last_active_date || "—");
      const status = u.subscription_status || "active";

      return `<tr>
        <td><strong>${escapeHtml(u.email)}</strong></td>
        <td><span class="badge ${badgeClass}">${escapeHtml(planDisplayName(tier))}</span></td>
        <td>${created}</td>
        <td>${lastActive}</td>
        <td style="color: var(--text-muted);">${escapeHtml(status)}</td>
        <td>
          <select aria-label="Choose plan for ${escapeHtml(u.email)}">
            <option value="">Choose plan</option><option value="free">Free</option>
            <option value="exam_pass">Exam Pass</option><option value="student_pro">Student &amp; Educator</option>
            <option value="cyber_cafe">All-In-One Pro &amp; Developer</option>
          </select>
          <button type="button" class="btn btn-xs" data-admin-user-action="set-plan" data-user-id="${escapeHtml(u.id)}">Set plan</button>
          <button type="button" class="btn btn-xs" data-admin-user-action="reset-usage" data-user-id="${escapeHtml(u.id)}">Reset usage</button>
          <button type="button" class="btn btn-danger btn-xs btn-delete-user" data-user-id="${escapeHtml(u.id)}" data-user-email="${escapeHtml(u.email)}" title="Delete account">
            🗑️ Delete
          </button>
        </td>
      </tr>`;
    }).join("");
  }

  async function updateUserAccess(event) {
    const button = event.target.closest("[data-admin-user-action]");
    if (!button) return;
    const action = button.dataset.adminUserAction;
    const selected = button.parentElement.querySelector("select");
    const tier = selected.value;
    if (action === "set-plan" && !tier) {
      selected.focus();
      return;
    }
    const message = action === "set-plan"
      ? "Set this account to " + selected.selectedOptions[0].textContent + "?"
      : "Reset today's web and API usage for this account?";
    if (!confirm(message)) return;
    button.disabled = true;
    try {
      const response = await fetch("/api/admin/users/" + action, {
        method: "POST",
        headers: { "X-Admin-Session": sessionToken, "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: button.dataset.userId, tier }),
      });
      if (!response.ok) throw new Error("Update failed");
      await fetchDashboardData();
    } catch {
      alert("Could not update this account. Refresh the dashboard and try again.");
    } finally {
      button.disabled = false;
    }
  }

  function renderWaitlist(list) {
    const tbody = document.getElementById("waitlist-tbody");
    if (!tbody) return;
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">No waitlist signups recorded.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map((e, idx) => {
      const dateStr = e.created_at ? new Date(e.created_at * 1000).toLocaleString() : "—";
      return `<tr>
        <td><strong>#${idx + 1}</strong></td>
        <td><strong>${escapeHtml(e.email)}</strong></td>
        <td><span class="badge badge-platform">${escapeHtml(e.platform || "all")}</span></td>
        <td>${dateStr}</td>
        <td style="font-family: monospace; color: var(--text-muted);">${escapeHtml(e.ip_address || "—")}</td>
      </tr>`;
    }).join("");
  }

  function renderAudits(list) {
    const tbody = document.getElementById("audit-tbody");
    if (!tbody) return;
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">No recent security events.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(a => {
      const dateStr = a.created_at ? new Date(a.created_at * 1000).toLocaleString() : "—";
      return `<tr>
        <td><code style="color: var(--pro-color);">${escapeHtml(a.event_type || "audit")}</code></td>
        <td>${escapeHtml(a.email || "—")}</td>
        <td style="font-family: monospace;">${escapeHtml(a.ip_address || "—")}</td>
        <td>${escapeHtml(a.location || "—")}</td>
        <td>${dateStr}</td>
        <td style="color: var(--text-muted);">${escapeHtml(a.details || "—")}</td>
      </tr>`;
    }).join("");
  }

  // --- Render Revenue & Bank Payouts ---
  function renderRevenue(rev) {
    if (!rev) return;

    setElText("rev-paying-count", rev.paying_users_count ?? 0);
    setElText("rev-gross-revenue", `₹${(rev.gross_revenue_inr ?? 0).toLocaleString("en-IN")}`);
    setElText("rev-gateway-fees", `₹${(rev.estimated_gateway_fees_inr ?? 0).toLocaleString("en-IN")}`);
    setElText("rev-net-payout", `₹${(rev.net_bank_payout_inr ?? 0).toLocaleString("en-IN")}`);
    setElText("rev-fee-rate", `${Number(rev.gateway_fee_rate_percent ?? 0).toFixed(2)}%`);
    setElText("rev-revenue-basis", (rev.revenue_basis || "") + " Sandbox: ₹"
      + (rev.sandbox_gross_inr ?? 0).toLocaleString("en-IN") + ". Unclassified: ₹"
      + (rev.unclassified_gross_inr ?? 0).toLocaleString("en-IN") + ".");

    const tbody = document.getElementById("revenue-tbody");
    if (!tbody) return;

    const orders = rev.recent_transactions || [];
    if (!orders.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">No payment transactions recorded yet.</td></tr>';
      return;
    }

    tbody.innerHTML = orders.map(ord => {
      const dateStr = ord.created_at ? new Date(ord.created_at * 1000).toLocaleString() : "—";
      const amount = Number(ord.amount);
      const amountLabel = Number.isFinite(amount) ? amount.toLocaleString("en-IN") : "0";
      const environment = String(ord.gateway_environment || "UNKNOWN").toUpperCase();
      const isProduction = environment === "PROD";
      const statusColor = isProduction ? "var(--green)" : "var(--amber, #b7791f)";
      return `<tr>
        <td><strong>${escapeHtml(ord.email || ord.customer_id)}</strong></td>
        <td><span class="badge badge-pro">${escapeHtml(planDisplayName((ord.tier || "pro").toLowerCase()))}</span></td>
        <td><code style="color: var(--text-muted);">${escapeHtml(ord.order_id || ord.customer_id)}</code></td>
        <td><strong style="color: ${statusColor};">₹${amountLabel}</strong></td>
        <td><span style="color: ${statusColor}; font-weight: 600;">${escapeHtml(environment)}</span></td>
        <td>${dateStr}</td>
        <td><span style="color: ${statusColor}; font-weight: 600;">● ${escapeHtml(ord.status || (isProduction ? "Paid" : "Unclassified paid"))}</span></td>
      </tr>`;
    }).join("");
  }

  // --- Render User Feedback ---
  function renderFeedback(list) {
    const tbody = document.getElementById("feedback-tbody");
    const countEl = document.getElementById("feedback-summary-count");
    if (countEl) countEl.textContent = `${list.length} reviews`;
    if (!tbody) return;

    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">No user feedbacks submitted yet.</td></tr>';
      return;
    }

    tbody.innerHTML = list.map(f => {
      const dateStr = f.created_at ? new Date(f.created_at * 1000).toLocaleString() : "—";
      const rating = Math.max(1, Math.min(5, f.rating || 5));
      const stars = "★".repeat(rating) + "☆".repeat(5 - rating);

      let catBadge = "badge-free";
      if (f.category === "bug") catBadge = "badge-dev";
      if (f.category === "suggestion") catBadge = "badge-pro";

      return `<tr>
        <td><span class="star-gold" style="font-size: 15px; letter-spacing: 2px;">${stars}</span></td>
        <td><span class="badge ${catBadge}">${escapeHtml((f.category || "general").toUpperCase())}</span></td>
        <td style="max-width: 320px; line-height: 1.4;">${escapeHtml(f.message)}</td>
        <td>${escapeHtml(f.email || "Anonymous")}</td>
        <td>${dateStr}</td>
        <td style="font-family: monospace; color: var(--text-muted); font-size: 11px;">${escapeHtml(f.ip_address || "—")}</td>
        <td>
          <button type="button" class="btn btn-danger btn-xs btn-delete-feedback" data-feedback-id="${escapeHtml(f.id)}" title="Delete feedback">
            🗑️
          </button>
        </td>
      </tr>`;
    }).join("");
  }

  // --- Render AI Settings Form ---
  function renderAiConfig(data) {
    if (!data || !data.config) return;
    const cfg = data.config;

    const providerSel = document.getElementById("ai-provider-select");
    const baseUrlInput = document.getElementById("ai-baseurl-input");
    const modelInput = document.getElementById("ai-model-input");
    const apiKeyInput = document.getElementById("ai-apikey-input");
    const fallbackProvider = document.getElementById("ai-fallback-provider-select");
    const fallbackBaseUrl = document.getElementById("ai-fallback-baseurl-input");
    const fallbackModel = document.getElementById("ai-fallback-model-input");
    const fallbackKey = document.getElementById("ai-fallback-apikey-input");

    if (providerSel && cfg.provider) providerSel.value = cfg.provider;
    if (baseUrlInput && cfg.base_url) baseUrlInput.value = cfg.base_url;
    if (modelInput && cfg.model) modelInput.value = cfg.model;
    if (apiKeyInput) {
      // Show a non-reusable mask as a placeholder. Never round-trip a partial
      // credential as though it were the real key.
      apiKeyInput.value = "";
      apiKeyInput.placeholder = cfg.has_key
        ? `Saved: ${cfg.api_key_masked || "configured"} · leave blank to keep`
        : "Enter provider API key";
      apiKeyInput.autocomplete = "new-password";
    }
    if (fallbackProvider) fallbackProvider.value = cfg.fallback_provider || "";
    if (fallbackBaseUrl) fallbackBaseUrl.value = cfg.fallback_base_url || "";
    if (fallbackModel) fallbackModel.value = cfg.fallback_model || "";
    if (fallbackKey) {
      fallbackKey.value = "";
      fallbackKey.placeholder = cfg.fallback_has_key
        ? `Saved: ${cfg.fallback_api_key_masked || "configured"} · leave blank to keep`
        : "Enter fallback provider API key";
      fallbackKey.autocomplete = "new-password";
    }
    const saveMsg = document.getElementById("ai-save-msg");
    if (saveMsg && cfg.key_needs_encryption) {
      saveMsg.textContent = "Existing saved AI credential needs the server encryption key configured before it can be used. Re-enter it after deployment setup.";
      saveMsg.style.background = "#3b1414";
      saveMsg.style.borderColor = "#7f1d1d";
      saveMsg.style.color = "#f87171";
      saveMsg.style.display = "block";
    }
  }

  function renderAiHealth(data) {
    const alert = document.getElementById("ai-provider-health-alert");
    if (!alert || !data) return;
    alert.textContent = data.message || "AI provider health is unavailable.";
    alert.style.display = "block";
    const ready = data.status === "configured";
    alert.style.background = ready ? "#0d221c" : "#3b1414";
    alert.style.border = `1px solid ${ready ? "#10b981" : "#7f1d1d"}`;
    alert.style.color = ready ? "#10b981" : "#f87171";
  }

  // --- Handle AI Config Save ---
  async function handleSaveAiConfig() {
    const providerSel = document.getElementById("ai-provider-select");
    const baseUrlInput = document.getElementById("ai-baseurl-input");
    const modelInput = document.getElementById("ai-model-input");
    const apiKeyInput = document.getElementById("ai-apikey-input");
    const fallbackProviderInput = document.getElementById("ai-fallback-provider-select");
    const fallbackBaseUrlInput = document.getElementById("ai-fallback-baseurl-input");
    const fallbackModelInput = document.getElementById("ai-fallback-model-input");
    const fallbackApiKeyInput = document.getElementById("ai-fallback-apikey-input");
    const msgBox = document.getElementById("ai-save-msg");
    const btn = document.getElementById("btn-save-ai");

    const provider = (providerSel ? providerSel.value : "").trim();
    const baseUrl = (baseUrlInput ? baseUrlInput.value : "").trim();
    const model = (modelInput ? modelInput.value : "").trim();
    const apiKey = (apiKeyInput ? apiKeyInput.value : "").trim();
    const fallbackProvider = (fallbackProviderInput ? fallbackProviderInput.value : "").trim();
    const fallbackBaseUrl = (fallbackBaseUrlInput ? fallbackBaseUrlInput.value : "").trim();
    const fallbackModel = (fallbackModelInput ? fallbackModelInput.value : "").trim();
    const fallbackApiKey = (fallbackApiKeyInput ? fallbackApiKeyInput.value : "").trim();

    btn.disabled = true;
    btn.textContent = "Saving...";
    if (msgBox) msgBox.style.display = "none";

    try {
      const resp = await fetch("/api/admin/ai-config", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Session": sessionToken
        },
        body: JSON.stringify({
          provider: provider,
          base_url: baseUrl,
          model: model,
          api_key: apiKey,
          fallback_provider: fallbackProvider,
          fallback_base_url: fallbackBaseUrl,
          fallback_model: fallbackModel,
          fallback_api_key: fallbackApiKey
        })
      });

      const res = await resp.json();
      if (resp.ok) {
        if (msgBox) {
          msgBox.textContent = "✅ AI Configuration successfully saved and activated live!";
          msgBox.style.background = "#0d221c";
          msgBox.style.borderColor = "#10b981";
          msgBox.style.color = "#10b981";
          msgBox.style.display = "block";
        }
        renderAiConfig(res);
      } else {
        if (msgBox) {
          msgBox.textContent = res.detail || "Failed to save AI configuration.";
          msgBox.style.background = "#3b1414";
          msgBox.style.borderColor = "#7f1d1d";
          msgBox.style.color = "#f87171";
          msgBox.style.display = "block";
        }
      }
    } catch (e) {
      if (msgBox) {
        msgBox.textContent = "Network error: Unable to save AI settings.";
        msgBox.style.display = "block";
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "💾 Save AI Configuration";
    }
  }

  // --- Handle AI Test Connection ---
  async function handleTestAiConnection() {
    const btn = document.getElementById("btn-test-ai");
    const statusEl = document.getElementById("ai-test-status");

    btn.disabled = true;
    btn.textContent = "Testing...";
    if (statusEl) {
      statusEl.textContent = "⚡ Pinging AI gateway...";
      statusEl.style.color = "var(--text-muted)";
    }

    const t0 = performance.now();
    try {
      const resp = await fetch("/api/admin/ai-test", {
        method: "POST",
        headers: { "X-Admin-Session": sessionToken }
      });
      const data = await resp.json();
      const latency = Math.round(performance.now() - t0);

      if (resp.ok && data.result && ["ok", "inference_succeeded"].includes(data.result.status)) {
        if (statusEl) {
          statusEl.textContent = `✅ Connected (${latency}ms) — Model: ${data.result.model || "Active"}`;
          statusEl.style.color = "var(--green)";
        }
        renderAiHealth({
          status: "configured",
          message: data.result.fallback_active
            ? `Primary provider was unavailable; the configured fallback is reachable (${latency} ms).`
            : `AI provider reachable (${latency} ms).`
        });
      } else {
        const msg = (data.result && data.result.message) || data.detail || "Connection failed";
        if (statusEl) {
          statusEl.textContent = `❌ ${msg} (${latency}ms)`;
          statusEl.style.color = "#f87171";
        }
        const rateLimited = data.result && data.result.http_status === 429;
        renderAiHealth({
          status: rateLimited ? "rate_limited" : "unreachable",
          message: rateLimited
            ? `AI provider is rate limited (HTTP 429). Check provider quota or configure a fallback. ${msg}`
            : `AI provider connection failed: ${msg}`
        });
      }
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = "❌ Network error testing AI connection.";
        statusEl.style.color = "#f87171";
      }
      renderAiHealth({ status: "unreachable", message: "AI provider connection failed. Check server network access and the saved provider settings." });
    } finally {
      btn.disabled = false;
      btn.textContent = "⚡ Test Connection";
    }
  }

  // --- Handle Clean Probe Accounts ---
  async function handleCleanProbes() {
    const btn = document.getElementById("btn-clean-probes");
    btn.disabled = true;
    btn.textContent = "Reviewing...";

    try {
      const previewResp = await fetch("/api/admin/users/cleanup-probes", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Session": sessionToken },
        body: JSON.stringify({})
      });
      const preview = await previewResp.json();
      if (!previewResp.ok) {
        alert(preview.detail || "Unable to preview matching accounts.");
        return;
      }
      const candidates = preview.candidates || [];
      if (!candidates.length) {
        alert("No matching probe accounts were found.");
        return;
      }
      const review = candidates.map(item => `• ${item.email}`).join("\n");
      if (!confirm(`Review these ${candidates.length} matching accounts before deletion:\n\n${review}\n\nDelete only these listed accounts?`)) return;

      btn.textContent = "Cleaning...";
      const resp = await fetch("/api/admin/users/cleanup-probes", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Session": sessionToken },
        body: JSON.stringify({ confirm: true, candidate_ids: candidates.map(item => item.id) })
      });
      const data = await resp.json();
      if (!resp.ok) {
        alert(data.detail || "Failed to cleanup probe accounts. Review the latest preview and try again.");
        return;
      }
      const pending = data.job_artifacts_pending || [];
      alert(`Deleted ${data.deleted_count} reviewed accounts. ${pending.length ? `${pending.length} job artifact folder(s) need manual cleanup.` : "Associated job files were removed."}`);
      fetchDashboardData();
    } catch (e) {
      alert("Network error reviewing or cleaning probe accounts.");
    } finally {
      btn.disabled = false;
      btn.textContent = "🧹 Clean Test Probes";
    }
  }

  // --- Handle Single User Delete ---
  async function handleDeleteUser(userId, userEmail) {
    if (!userId) return;
    const confirmDel = confirm(`Are you sure you want to permanently delete user account: ${userEmail}? This will delete all jobs, API keys, and sessions.`);
    if (!confirmDel) return;

    try {
      const resp = await fetch("/api/admin/users/delete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Session": sessionToken
        },
        body: JSON.stringify({ user_id: userId })
      });
      const data = await resp.json();
      if (resp.ok) {
        alert(`User ${userEmail} was permanently deleted.`);
        fetchDashboardData();
      } else {
        alert(data.detail || "Failed to delete user.");
      }
    } catch (e) {
      alert("Network error deleting user.");
    }
  }

  async function refreshSupport() {
    if (!sessionToken) return;
    const currentSession = sessionToken;
    try {
      const resp = await fetch("/api/admin/support", {
        headers: { "X-Admin-Session": currentSession },
        cache: "no-store"
      });
      if (currentSession !== sessionToken) return;
      if (resp.status === 401) {
        await handleLogout();
        return;
      }
      if (!resp.ok) return;
      const data = await resp.json();
      supportData = data.tickets || [];
      setElText("count-support", supportData.length);
      if (currentTab === "support") applyFilters();
    } catch {}
  }

  function renderSupport(list) {
    const tbody = document.getElementById("support-tbody");
    const countEl = document.getElementById("support-summary-count");
    if (countEl) countEl.textContent = `${list.length} tickets`;
    if (!tbody) return;
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">No support tickets yet.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(t => {
      const dateStr = t.created_at ? new Date(t.created_at * 1000).toLocaleString() : "—";
      const isResolved = String(t.status || "open").toLowerCase() === "resolved";
      const statusBadge = isResolved ? "badge-pro" : "badge-dev";
      const nextStatus = isResolved ? "open" : "resolved";
      const nextLabel = isResolved ? "Reopen" : "Resolve";
      return `<tr>
        <td><code>${escapeHtml(t.ticket_ref || t.id)}</code></td>
        <td><span class="badge ${statusBadge}">${escapeHtml((t.status || "open").toUpperCase())}</span></td>
        <td>${escapeHtml(t.category || "general")}</td>
        <td style="max-width: 340px; line-height: 1.4;"><strong>${escapeHtml(t.subject)}</strong><br><span style="color:var(--text-muted);font-size:12px;">${escapeHtml(t.message)}</span></td>
        <td>${escapeHtml(t.email)}${t.order_id ? `<br><small style="color:var(--text-muted);">Order: ${escapeHtml(t.order_id)}</small>` : ""}</td>
        <td>${dateStr}</td>
        <td style="white-space: nowrap;">
          <button type="button" class="btn btn-xs btn-support-status" data-ticket-id="${escapeHtml(t.id)}" data-next-status="${nextStatus}">${nextLabel}</button>
          <button type="button" class="btn btn-danger btn-xs btn-delete-support" data-ticket-id="${escapeHtml(t.id)}" title="Delete ticket">🗑️</button>
        </td>
      </tr>`;
    }).join("");
  }

  async function handleSupportStatus(ticketId, nextStatus) {
    if (!ticketId) return;
    try {
      const resp = await fetch(`/api/admin/support/${encodeURIComponent(ticketId)}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Session": sessionToken },
        body: JSON.stringify({ status: nextStatus })
      });
      if (resp.ok) await refreshSupport();
      else alert("Could not update ticket status.");
    } catch {
      alert("Network error updating ticket.");
    }
  }

  async function handleDeleteSupport(ticketId) {
    if (!ticketId || !confirm("Delete this support ticket?")) return;
    try {
      const resp = await fetch(`/api/admin/support/${encodeURIComponent(ticketId)}`, {
        method: "DELETE",
        headers: { "X-Admin-Session": sessionToken }
      });
      if (resp.ok) {
        supportData = supportData.filter(t => t.id !== ticketId);
        setElText("count-support", supportData.length);
        applyFilters();
      } else {
        alert("Failed to delete ticket.");
      }
    } catch {
      alert("Network error deleting ticket.");
    }
  }

  // --- Handle Feedback Delete ---
  async function handleDeleteFeedback(feedbackId) {
    if (!feedbackId) return;
    if (!confirm("Delete this feedback entry?")) return;

    try {
      const resp = await fetch(`/api/admin/feedback/${feedbackId}`, {
        method: "DELETE",
        headers: { "X-Admin-Session": sessionToken }
      });
      if (resp.ok) {
        feedbackData = feedbackData.filter(f => f.id !== feedbackId);
        setElText("count-feedback", feedbackData.length);
        applyFilters();
      } else {
        alert("Failed to delete feedback entry.");
      }
    } catch (e) {
      alert("Network error deleting feedback.");
    }
  }

  // --- Secure CSV Downloads (No Secrets in URL) ---
  async function downloadCsv(endpoint, filename) {
    try {
      const resp = await fetch(endpoint, {
        headers: { "X-Admin-Session": sessionToken }
      });

      if (!resp.ok) {
        alert("Failed to download CSV: Session expired or unauthorized.");
        return;
      }

      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("Network error while downloading CSV.");
    }
  }

  function updateClock() {
    const el = document.getElementById("live-time-now");
    if (el) {
      el.textContent = new Date().toUTCString();
    }
  }
  setInterval(updateClock, 1000);

  function setElText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
})();
