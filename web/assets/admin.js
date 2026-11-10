// Paperplane PDF — Owner Admin Dashboard Script
// Compliant with strict CSP (no inline scripts, no eval)

(function () {
  let activeKey = sessionStorage.getItem("pp_admin_key") || "";
  let usersData = [];
  let waitlistData = [];
  let currentTab = "users";

  // Check URL query param: /admin?key=...
  const urlParams = new URLSearchParams(window.location.search);
  const paramKey = urlParams.get("key");
  if (paramKey) {
    activeKey = paramKey;
    sessionStorage.setItem("pp_admin_key", activeKey);
  }

  // Setup DOM listeners once loaded
  document.addEventListener("DOMContentLoaded", () => {
    const inputKey = document.getElementById("admin-key-input");
    const btnUnlock = document.getElementById("btn-unlock");
    const btnRefresh = document.getElementById("btn-refresh");
    const btnLogout = document.getElementById("btn-logout");
    const tabUsersBtn = document.getElementById("tab-users-btn");
    const tabWaitlistBtn = document.getElementById("tab-waitlist-btn");
    const searchInput = document.getElementById("search-input");

    if (btnUnlock) btnUnlock.addEventListener("click", attemptLogin);
    if (btnRefresh) btnRefresh.addEventListener("click", fetchDashboardData);
    if (btnLogout) btnLogout.addEventListener("click", logoutAdmin);
    if (tabUsersBtn) tabUsersBtn.addEventListener("click", () => switchTab("users"));
    if (tabWaitlistBtn) tabWaitlistBtn.addEventListener("click", () => switchTab("waitlist"));
    if (searchInput) searchInput.addEventListener("input", filterTable);

    if (inputKey) {
      inputKey.addEventListener("keypress", (e) => {
        if (e.key === "Enter") attemptLogin();
      });
    }

    if (activeKey) {
      initDashboard();
    }
  });

  async function attemptLogin() {
    const input = document.getElementById("admin-key-input");
    const key = (input ? input.value : "").trim();
    const errBox = document.getElementById("auth-error");
    if (!key) return;

    try {
      const resp = await fetch("/api/admin/dashboard", {
        headers: { "X-Admin-Key": key }
      });
      if (resp.status === 200) {
        activeKey = key;
        sessionStorage.setItem("pp_admin_key", key);
        if (errBox) errBox.style.display = "none";
        initDashboard();
      } else {
        if (errBox) {
          errBox.textContent = "Invalid or unauthorized Admin Key.";
          errBox.style.display = "block";
        }
      }
    } catch (err) {
      if (errBox) {
        errBox.textContent = "Network error: unable to connect.";
        errBox.style.display = "block";
      }
    }
  }

  function logoutAdmin() {
    sessionStorage.removeItem("pp_admin_key");
    activeKey = "";
    document.getElementById("dashboard-view").style.display = "none";
    document.getElementById("header-actions").style.display = "none";
    document.getElementById("auth-screen").style.display = "block";
    const input = document.getElementById("admin-key-input");
    if (input) input.value = "";
  }

  function initDashboard() {
    document.getElementById("auth-screen").style.display = "none";
    document.getElementById("dashboard-view").style.display = "block";
    document.getElementById("header-actions").style.display = "flex";

    // Setup CSV download links
    const btnUsers = document.getElementById("btn-export-users");
    const btnWaitlist = document.getElementById("btn-export-waitlist");
    if (btnUsers) btnUsers.href = `/api/admin/users/export.csv?key=${encodeURIComponent(activeKey)}`;
    if (btnWaitlist) btnWaitlist.href = `/api/admin/waitlist/export.csv?key=${encodeURIComponent(activeKey)}`;

    fetchDashboardData();
  }

  async function fetchDashboardData() {
    try {
      const [dashResp, usersResp, waitlistResp] = await Promise.all([
        fetch("/api/admin/dashboard", { headers: { "X-Admin-Key": activeKey } }),
        fetch("/api/admin/users", { headers: { "X-Admin-Key": activeKey } }),
        fetch("/api/admin/waitlist", { headers: { "X-Admin-Key": activeKey } })
      ]);

      if (dashResp.status === 401) {
        logoutAdmin();
        return;
      }

      const metrics = await dashResp.json();
      const usersObj = await usersResp.json();
      const waitlistObj = await waitlistResp.json();

      // Update Metrics Cards
      setElText("m-total-users", metrics.total_users ?? 0);
      setElText("m-new-7d", `${metrics.new_signups_7d ?? 0} new last 7 days`);
      setElText("m-pro-users", metrics.pro_users ?? 0);
      setElText("m-dev-users", metrics.dev_users ?? 0);
      setElText("m-free-users", metrics.free_users ?? 0);
      setElText("m-today-active", metrics.today_active ?? 0);
      setElText("m-total-waitlist", metrics.total_waitlist ?? 0);
      setElText("m-total-jobs", metrics.total_jobs ?? 0);
      setElText("m-jobs-today", `${metrics.jobs_today ?? 0} processed today`);

      usersData = usersObj.users || [];
      waitlistData = waitlistObj.entries || [];

      setElText("count-users", usersData.length);
      setElText("count-waitlist", waitlistData.length);

      renderUsers(usersData);
      renderWaitlist(waitlistData);
    } catch (err) {
      console.error("Dashboard fetch error:", err);
    }
  }

  function renderUsers(list) {
    const tbody = document.getElementById("users-tbody");
    if (!tbody) return;
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No users found.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(u => {
      const tier = (u.tier || "free").toLowerCase();
      let badgeClass = "badge-free";
      if (tier.includes("pro")) badgeClass = "badge-pro";
      if (tier.includes("dev")) badgeClass = "badge-dev";

      const created = u.created_at ? new Date(u.created_at * 1000).toLocaleDateString() : "—";
      const lastActive = u.last_active_date || "—";
      const status = u.subscription_status || "active";

      return `<tr>
        <td><strong>${escapeHtml(u.email)}</strong></td>
        <td><span class="badge ${badgeClass}">${escapeHtml(tier.toUpperCase())}</span></td>
        <td>${created}</td>
        <td>${lastActive}</td>
        <td style="color: var(--text-muted);">${escapeHtml(status)}</td>
      </tr>`;
    }).join("");
  }

  function renderWaitlist(list) {
    const tbody = document.getElementById("waitlist-tbody");
    if (!tbody) return;
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No waitlist signups yet.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map((e, idx) => {
      const dateStr = e.created_at ? new Date(e.created_at * 1000).toLocaleString() : "—";
      return `<tr>
        <td>#${idx + 1}</td>
        <td><strong>${escapeHtml(e.email)}</strong></td>
        <td><span class="badge badge-platform">${escapeHtml(e.platform || "all")}</span></td>
        <td>${dateStr}</td>
        <td style="font-family: monospace; color: var(--text-muted);">${escapeHtml(e.ip_address || "—")}</td>
      </tr>`;
    }).join("");
  }

  function switchTab(tab) {
    currentTab = tab;
    const tabUsersBtn = document.getElementById("tab-users-btn");
    const tabWaitlistBtn = document.getElementById("tab-waitlist-btn");
    const panelUsers = document.getElementById("panel-users");
    const panelWaitlist = document.getElementById("panel-waitlist");

    if (tab === "users") {
      if (tabUsersBtn) tabUsersBtn.classList.add("active");
      if (tabWaitlistBtn) tabWaitlistBtn.classList.remove("active");
      if (panelUsers) panelUsers.style.display = "block";
      if (panelWaitlist) panelWaitlist.style.display = "none";
    } else {
      if (tabWaitlistBtn) tabWaitlistBtn.classList.add("active");
      if (tabUsersBtn) tabUsersBtn.classList.remove("active");
      if (panelWaitlist) panelWaitlist.style.display = "block";
      if (panelUsers) panelUsers.style.display = "none";
    }
    filterTable();
  }

  function filterTable() {
    const input = document.getElementById("search-input");
    const q = (input ? input.value : "").trim().toLowerCase();
    if (currentTab === "users") {
      const filtered = usersData.filter(u => (u.email || "").toLowerCase().includes(q));
      renderUsers(filtered);
    } else {
      const filtered = waitlistData.filter(e => (e.email || "").toLowerCase().includes(q));
      renderWaitlist(filtered);
    }
  }

  function setElText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();
