// Paperplane PDF — Owner Admin Dashboard Script v2.1
// 3-Factor Authentication (Key + Secret Code + Email OTP)
// Multi-segment Visual Analytics, Revenue & Bank Payouts, Feedback & AI Configuration
// Strict Content Security Policy (CSP) compliant — No inline event handlers

(function () {
  const urlParams = new URLSearchParams(window.location.search);
  let sessionToken = urlParams.get("session") || sessionStorage.getItem("pp_admin_session") || "";
  if (urlParams.has("session") && sessionToken) {
    sessionStorage.setItem("pp_admin_session", sessionToken);
    window.history.replaceState({}, document.title, window.location.pathname);
  }
  let usersData = [];
  let waitlistData = [];
  let auditData = [];
  let revenueData = null;
  let feedbackData = [];
  let aiConfigData = null;

  let currentTab = "users";
  let activeTierFilter = "all";
  let activeFeedbackFilter = "all";
  let lockoutTimer = null;

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
    const btnBack1 = document.getElementById("btn-back-step1");
    const btnCheckLock = document.getElementById("btn-check-lockout");
    const btnRefresh = document.getElementById("btn-refresh");
    const btnLogout = document.getElementById("btn-logout");
    const searchInput = document.getElementById("search-input");
    const btnCleanProbes = document.getElementById("btn-clean-probes");
    const btnSaveAi = document.getElementById("btn-save-ai");
    const btnTestAi = document.getElementById("btn-test-ai");

    if (btnSubmit1) btnSubmit1.addEventListener("click", handleStep1Submit);
    if (btnSubmit2) btnSubmit2.addEventListener("click", handleStep2Submit);
    if (btnBack1) btnBack1.addEventListener("click", () => switchScreen("step1"));
    if (btnCheckLock) btnCheckLock.addEventListener("click", checkInitialState);
    if (btnRefresh) btnRefresh.addEventListener("click", fetchDashboardData);
    if (btnLogout) btnLogout.addEventListener("click", handleLogout);
    if (btnCleanProbes) btnCleanProbes.addEventListener("click", handleCleanProbes);
    if (btnSaveAi) btnSaveAi.addEventListener("click", handleSaveAiConfig);
    if (btnTestAi) btnTestAi.addEventListener("click", handleTestAiConnection);

    // Enter key shortcuts
    const keyInput = document.getElementById("admin-key-input");
    const codeInput = document.getElementById("admin-code-input");
    const otpInput = document.getElementById("admin-otp-input");

    if (keyInput) keyInput.addEventListener("keypress", (e) => { if (e.key === "Enter") handleStep1Submit(); });
    if (codeInput) codeInput.addEventListener("keypress", (e) => { if (e.key === "Enter") handleStep1Submit(); });
    if (otpInput) otpInput.addEventListener("keypress", (e) => { if (e.key === "Enter") handleStep2Submit(); });

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
      const resp = await fetch("/api/admin/auth/status");
      const data = await resp.json();

      if (data.locked) {
        showLockout(data.remaining_seconds);
        return;
      }
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

  // --- Step 1 Submit (Key + Code) ---
  async function handleStep1Submit() {
    const keyInput = document.getElementById("admin-key-input");
    const codeInput = document.getElementById("admin-code-input");
    const errBox = document.getElementById("auth-error");
    const btn = document.getElementById("btn-submit-step1");

    const key = (keyInput ? keyInput.value : "").trim();
    const code = (codeInput ? codeInput.value : "").trim();

    if (!key || !code) {
      showError(errBox, "Both Admin Secret Key and Secret Code are required.");
      return;
    }

    btn.disabled = true;
    btn.textContent = "Verifying...";
    hideError(errBox);

    try {
      const resp = await fetch("/api/admin/auth/step1", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_key: key, admin_code: code })
      });

      const data = await resp.json().catch(() => ({}));

      if (resp.status === 200) {
        switchScreen("step2");
        const otpInput = document.getElementById("admin-otp-input");
        if (otpInput) {
          otpInput.value = "";
          otpInput.focus();
        }
      } else if (resp.status === 423) {
        showLockout(data.remaining_seconds || 86400);
      } else {
        showError(errBox, data.detail || "Invalid Key or Secret Code.");
      }
    } catch (err) {
      showError(errBox, "Network error: unable to reach authentication server.");
    } finally {
      btn.disabled = false;
      btn.textContent = "Verify & Send Email OTP →";
    }
  }

  // --- Step 2 Submit (OTP) ---
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
    btn.textContent = "Unlocking...";
    hideError(errBox);

    try {
      const resp = await fetch("/api/admin/auth/step2", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ otp: otp })
      });

      const data = await resp.json().catch(() => ({}));

      if (resp.status === 200 && data.session_token) {
        sessionToken = data.session_token;
        sessionStorage.setItem("pp_admin_session", sessionToken);
        switchScreen("dashboard");
        fetchDashboardData();
      } else if (resp.status === 423) {
        showLockout(data.remaining_seconds || 86400);
      } else {
        showError(errBox, data.detail || "Invalid or expired OTP code.");
      }
    } catch (err) {
      showError(errBox, "Network error: unable to verify OTP.");
    } finally {
      btn.disabled = false;
      btn.textContent = "Verify Code & Unlock Console →";
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
    switchScreen("step1");
  }

  // --- Lockout Countdown ---
  function showLockout(seconds) {
    switchScreen("lockout");
    let remaining = Math.max(1, Math.round(seconds || 86400));

    if (lockoutTimer) clearInterval(lockoutTimer);

    function updateTimer() {
      if (remaining <= 0) {
        clearInterval(lockoutTimer);
        switchScreen("step1");
        return;
      }
      const hrs = Math.floor(remaining / 3600);
      const mins = Math.floor((remaining % 3600) / 60);
      const secs = remaining % 60;
      const el = document.getElementById("lockout-countdown");
      if (el) el.textContent = `${hrs}h ${mins}m ${secs}s`;
      remaining--;
    }

    updateTimer();
    lockoutTimer = setInterval(updateTimer, 1000);
  }

  // --- Screen Switcher ---
  function switchScreen(screen) {
    const sLockout = document.getElementById("lockout-screen");
    const sStep1 = document.getElementById("step1-screen");
    const sStep2 = document.getElementById("step2-screen");
    const sDash = document.getElementById("dashboard-view");
    const headerActions = document.getElementById("header-actions");

    if (sLockout) sLockout.style.display = screen === "lockout" ? "block" : "none";
    if (sStep1) sStep1.style.display = screen === "step1" ? "block" : "none";
    if (sStep2) sStep2.style.display = screen === "step2" ? "block" : "none";
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
      const [dashResp, usersResp, waitlistResp, revResp, feedbackResp, aiResp] = await Promise.all([
        fetch("/api/admin/dashboard", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/users", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/waitlist", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/revenue", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/feedback", { headers: { "X-Admin-Session": sessionToken } }),
        fetch("/api/admin/ai-config", { headers: { "X-Admin-Session": sessionToken } })
      ]);

      if (dashResp.status === 401 || dashResp.status === 403) {
        handleLogout();
        return;
      }

      const metrics = await dashResp.json();
      const usersObj = await usersResp.json();
      const waitlistObj = await waitlistResp.json();
      revenueData = await revResp.json().catch(() => null);
      const feedbackObj = await feedbackResp.json().catch(() => ({ feedbacks: [] }));
      aiConfigData = await aiResp.json().catch(() => null);

      // Top Metric Cards
      setElText("m-total-users", metrics.total_users ?? 0);
      setElText("m-new-7d", `${metrics.new_signups_7d ?? 0} new last 7 days`);
      setElText("m-pro-users", metrics.pro_users ?? 0);
      setElText("m-dev-users", metrics.dev_users ?? 0);
      setElText("m-free-users", metrics.free_users ?? 0);
      setElText("m-today-active", metrics.today_active ?? 0);
      setElText("m-total-waitlist", metrics.total_waitlist ?? 0);
      setElText("m-total-jobs", metrics.total_jobs ?? 0);
      setElText("m-jobs-today", `${metrics.jobs_today ?? 0} processed today`);

      // System Banner
      setElText("live-db-path", `${metrics.db_location || "/data"}/paperplane.sqlite3 (${metrics.total_users} users)`);
      setElText("live-env-name", (metrics.environment || "production").toUpperCase());
      const headerEnv = document.getElementById("header-env");
      if (headerEnv) headerEnv.textContent = `${(metrics.environment || "Production").toUpperCase()} LIVE`;

      // Render Visual Charts
      renderTierMeter(metrics);
      renderBarChart(metrics.days_trend || []);

      usersData = usersObj.users || [];
      waitlistData = waitlistObj.entries || [];
      auditData = metrics.recent_audits || [];
      feedbackData = feedbackObj.feedbacks || [];

      setElText("count-users", usersData.length);
      setElText("count-waitlist", waitlistData.length);
      setElText("count-audit", auditData.length);
      setElText("count-feedback", feedbackData.length);

      applyFilters();
      renderWaitlist(waitlistData);
      renderAudits(auditData);
      renderRevenue(revenueData);
      renderAiConfig(aiConfigData);
    } catch (err) {
      console.error("Dashboard refresh error:", err);
    }
  }

  // --- Visual Analytics: Tier Meter ---
  function renderTierMeter(m) {
    const total = m.total_users || 1;
    const free = m.free_users || 0;
    const pro = m.pro_users || 0;
    const dev = m.dev_users || 0;

    const freePct = Math.round((free / total) * 100);
    const proPct = Math.round((pro / total) * 100);
    const devPct = Math.max(0, 100 - freePct - proPct);

    const mFree = document.getElementById("meter-free");
    const mPro = document.getElementById("meter-pro");
    const mDev = document.getElementById("meter-dev");

    if (mFree) mFree.style.width = `${freePct}%`;
    if (mPro) mPro.style.width = `${proPct}%`;
    if (mDev) mDev.style.width = `${devPct}%`;

    setElText("legend-free-val", `${free} (${freePct}%)`);
    setElText("legend-pro-val", `${pro} (${proPct}%)`);
    setElText("legend-dev-val", `${dev} (${devPct}%)`);
    setElText("tier-ratio-label", `${total} total accounts`);
  }

  // --- Visual Analytics: 14-Day Signup Bar Chart ---
  function renderBarChart(days) {
    const container = document.getElementById("bar-chart-container");
    if (!container) return;

    if (!days.length) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; margin: auto;">No trend data available.</div>';
      return;
    }

    const maxCount = Math.max(1, ...days.map(d => d.count || 0));

    container.innerHTML = days.map(d => {
      const count = d.count || 0;
      const heightPct = Math.max(6, Math.round((count / maxCount) * 100));
      return `<div class="bar-col">
        <span class="bar-value">${count > 0 ? count : ""}</span>
        <div class="bar-fill" style="height: ${heightPct}%;" title="${d.date}: ${count} signups"></div>
        <span class="bar-label">${d.date}</span>
      </div>`;
    }).join("");
  }

  // --- Tab Switcher ---
  function switchTab(tab) {
    currentTab = tab;
    const tabs = ["users", "revenue", "feedback", "ai", "waitlist", "audit"];

    tabs.forEach(t => {
      const btn = document.getElementById(`tab-${t}-btn`);
      const panel = document.getElementById(`panel-${t}`);
      if (btn) btn.classList.toggle("active", t === tab);
      if (panel) panel.style.display = t === tab ? "block" : "none";
    });

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
      const lastActive = u.last_active_date || "—";
      const status = u.subscription_status || "active";

      return `<tr>
        <td><strong>${escapeHtml(u.email)}</strong></td>
        <td><span class="badge ${badgeClass}">${escapeHtml(tier.toUpperCase())}</span></td>
        <td>${created}</td>
        <td>${lastActive}</td>
        <td style="color: var(--text-muted);">${escapeHtml(status)}</td>
        <td>
          <button type="button" class="btn btn-danger btn-xs btn-delete-user" data-user-id="${escapeHtml(u.id)}" data-user-email="${escapeHtml(u.email)}" title="Delete account">
            🗑️ Delete
          </button>
        </td>
      </tr>`;
    }).join("");
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
      tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">No recent security events.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(a => {
      const dateStr = a.created_at ? new Date(a.created_at * 1000).toLocaleString() : "—";
      return `<tr>
        <td><code style="color: var(--pro-color);">${escapeHtml(a.event_type || "audit")}</code></td>
        <td>${escapeHtml(a.email || "—")}</td>
        <td style="font-family: monospace;">${escapeHtml(a.ip_address || "—")}</td>
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

    const tbody = document.getElementById("revenue-tbody");
    if (!tbody) return;

    const orders = rev.recent_transactions || [];
    if (!orders.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">No payment transactions recorded yet.</td></tr>';
      return;
    }

    tbody.innerHTML = orders.map(ord => {
      const dateStr = ord.created_at ? new Date(ord.created_at * 1000).toLocaleString() : "—";
      return `<tr>
        <td><strong>${escapeHtml(ord.email || ord.customer_id)}</strong></td>
        <td><span class="badge badge-pro">${escapeHtml((ord.tier || "PRO").toUpperCase())}</span></td>
        <td><code style="color: var(--text-muted);">${escapeHtml(ord.order_id || ord.customer_id)}</code></td>
        <td><strong style="color: var(--green);">₹${(ord.amount || 0).toLocaleString("en-IN")}</strong></td>
        <td>${dateStr}</td>
        <td><span style="color: var(--green); font-weight: 600;">● Settled</span></td>
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

    if (providerSel && cfg.provider) providerSel.value = cfg.provider;
    if (baseUrlInput && cfg.base_url) baseUrlInput.value = cfg.base_url;
    if (modelInput && cfg.model) modelInput.value = cfg.model;
    if (apiKeyInput && cfg.api_key_masked) apiKeyInput.value = cfg.api_key_masked;
  }

  // --- Handle AI Config Save ---
  async function handleSaveAiConfig() {
    const providerSel = document.getElementById("ai-provider-select");
    const baseUrlInput = document.getElementById("ai-baseurl-input");
    const modelInput = document.getElementById("ai-model-input");
    const apiKeyInput = document.getElementById("ai-apikey-input");
    const msgBox = document.getElementById("ai-save-msg");
    const btn = document.getElementById("btn-save-ai");

    const provider = (providerSel ? providerSel.value : "").trim();
    const baseUrl = (baseUrlInput ? baseUrlInput.value : "").trim();
    const model = (modelInput ? modelInput.value : "").trim();
    const apiKey = (apiKeyInput ? apiKeyInput.value : "").trim();

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
          api_key: apiKey
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

      if (resp.ok && data.result && data.result.status === "ok") {
        if (statusEl) {
          statusEl.textContent = `✅ Connected (${latency}ms) — Model: ${data.result.model || "Active"}`;
          statusEl.style.color = "var(--green)";
        }
      } else {
        const msg = (data.result && data.result.message) || data.detail || "Connection failed";
        if (statusEl) {
          statusEl.textContent = `❌ ${msg} (${latency}ms)`;
          statusEl.style.color = "#f87171";
        }
      }
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = "❌ Network error testing AI connection.";
        statusEl.style.color = "#f87171";
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "⚡ Test Connection";
    }
  }

  // --- Handle Clean Probe Accounts ---
  async function handleCleanProbes() {
    const confirmClean = confirm(
      "Are you sure you want to clean all test probe accounts (example.com, tab.bot, sharklasers, etc.)?\n\nReal user accounts (mdhammad2906@gmail.com, etc.) will be 100% safe."
    );
    if (!confirmClean) return;

    const btn = document.getElementById("btn-clean-probes");
    btn.disabled = true;
    btn.textContent = "Cleaning...";

    try {
      const resp = await fetch("/api/admin/users/cleanup-probes", {
        method: "POST",
        headers: { "X-Admin-Session": sessionToken }
      });
      const data = await resp.json();
      if (resp.ok) {
        alert(`Cleaned ${data.deleted_count} test probe accounts successfully!`);
        fetchDashboardData();
      } else {
        alert(data.detail || "Failed to cleanup probe accounts.");
      }
    } catch (e) {
      alert("Network error cleaning probe accounts.");
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
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();
