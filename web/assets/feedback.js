// Paperplane PDF — Non-intrusive Floating Feedback Widget
// Bottom-right floating popover for user feedback and bug reporting
// CSP compliant: strictly uses addEventListener, no inline handlers

(function () {
  let selectedRating = 5;
  let selectedCategory = "general";
  let isSubmitting = false;
  let currentScope = "guest";
  let dismissedInMemory = false;
  let submittedInMemory = false;

  const storageKey = (kind, scope = currentScope) => `paperplane-feedback-${kind}:v1:${scope}`;

  function feedbackScope() {
    try {
      const userId = String(state?.user?.user_id || "").trim();
      return userId ? `account-${userId}` : "guest";
    } catch {
      return "guest";
    }
  }

  function readFlag(kind) {
    try { return localStorage.getItem(storageKey(kind)) === "1"; } catch { return false; }
  }

  function writeFlag(kind) {
    try { localStorage.setItem(storageKey(kind), "1"); } catch { /* This tab still remembers the state in memory. */ }
  }

  function hasSubmitted() { return submittedInMemory || readFlag("submitted"); }
  function isDismissed() { return dismissedInMemory || readFlag("dismissed"); }

  function syncVisibility({ keepCardOpen = false } = {}) {
    const button = document.getElementById("pp-btn-feedback-toggle");
    const card = document.getElementById("pp-feedback-popover");
    const hidden = hasSubmitted() || isDismissed();
    if (button) button.hidden = hidden;
    if (hidden && card && !keepCardOpen) card.style.display = "none";
  }

  function openFeedback() {
    const card = document.getElementById("pp-feedback-popover");
    const textArea = document.getElementById("pp-fb-text-input");
    if (!card) return;
    card.style.display = "flex";
    if (textArea) textArea.focus();
  }

  function dismissFeedback() {
    dismissedInMemory = true;
    writeFlag("dismissed");
    const card = document.getElementById("pp-feedback-popover");
    if (card) card.style.display = "none";
    syncVisibility();
  }

  function positionFeedbackButton(button) {
    const directory = document.getElementById("view-tool-desk-directory");
    const meta = document.getElementById("tool-desk-search-meta");
    const firstCard = document.querySelector("#tool-desk-tools-catalog .home-tool-card");
    const nav = document.querySelector(".mobile-workspace-bar");
    if (!directory || directory.hidden || !meta || !firstCard) {
      button.style.removeProperty("top");
      button.style.removeProperty("bottom");
      return;
    }

    const metaRect = meta.getBoundingClientRect();
    const cardRect = firstCard.getBoundingClientRect();
    const navRect = nav?.getBoundingClientRect();
    const height = button.getBoundingClientRect().height || 44;
    const lowestTop = metaRect.bottom + 1;
    const navTop = navRect && navRect.height > 0 ? navRect.top - height - 1 : Infinity;
    const highestTop = Math.min(cardRect.top - height - 1, navTop);
    if (highestTop < lowestTop) {
      button.style.removeProperty("top");
      button.style.removeProperty("bottom");
      return;
    }

    // Use the gap between the Tool Desk count and first card, keeping the pill
    // visible without covering either surface or the mobile navigation.
    const top = Math.round((lowestTop + highestTop) / 2);
    button.style.top = `${top}px`;
    button.style.bottom = "auto";
  }

  let obstructionFrame = 0;
  function scheduleObstructionCheck() {
    if (obstructionFrame) return;
    obstructionFrame = requestAnimationFrame(() => {
      obstructionFrame = 0;
      const container = document.getElementById("pp-feedback-container");
      const button = document.getElementById("pp-btn-feedback-toggle");
      if (!container || !button || button.hidden) return;
      positionFeedbackButton(button);
      const buttonRect = button.getBoundingClientRect();
      const obstructsImportantControl = [...document.querySelectorAll(".home-tool-card, #zoom-select")].some(target => {
        const rect = target.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        return buttonRect.left < rect.right && buttonRect.right > rect.left
          && buttonRect.top < rect.bottom && buttonRect.bottom > rect.top;
      });
      container.classList.toggle("pp-feedback-obstructed", obstructsImportantControl);
      if (obstructsImportantControl) {
        const card = document.getElementById("pp-feedback-popover");
        if (card) card.style.display = "none";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    injectFeedbackWidget();
    bindFeedbackEvents();
  });

  function injectFeedbackWidget() {
    // Only inject once
    if (document.getElementById("pp-feedback-container")) return;

    const style = document.createElement("style");
    style.id = "pp-feedback-styles";
    style.textContent = `
      .pp-feedback-btn {
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 80;
        bottom: calc(24px + env(safe-area-inset-bottom, 0px));
        background: #141f22;
        color: #f0f5f4;
        border: 1px solid #2d4145;
        border-radius: 999px;
        padding: 9px 16px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        font-family: inherit;
      }
      .pp-feedback-btn:hover {
        background: #1c2b2f;
        border-color: #ff4b26;
        transform: translateY(-2px);
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.5);
      }
      .pp-feedback-btn .fb-icon {
        font-size: 14px;
      }
      .pp-feedback-btn[hidden] { display: none !important; }
      #pp-feedback-container.pp-feedback-obstructed { visibility: hidden !important; pointer-events: none !important; }

      /* Floating Popover Card */
      .pp-feedback-card {
        position: fixed;
        bottom: 74px;
        right: 24px;
        width: 330px;
        max-width: calc(100vw - 32px);
        background: #121c1f;
        border: 1px solid #283a3f;
        border-radius: 14px;
        box-shadow: 0 20px 48px rgba(0, 0, 0, 0.6);
        z-index: 81;
        display: none;
        flex-direction: column;
        overflow: hidden;
        animation: ppFeedbackSlideIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        font-family: inherit;
        color: #f0f5f4;
      }
      @keyframes ppFeedbackSlideIn {
        from { opacity: 0; transform: translateY(12px) scale(0.97); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }

      .pp-fb-header {
        padding: 14px 16px;
        background: #162327;
        border-bottom: 1px solid #24363b;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .pp-fb-header h4 {
        font-size: 14px;
        font-weight: 700;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .pp-fb-close {
        background: none;
        border: none;
        color: #8ca3a2;
        font-size: 18px;
        cursor: pointer;
        padding: 2px 6px;
        border-radius: 4px;
        line-height: 1;
      }
      .pp-fb-close:hover { color: #fff; background: rgba(255,255,255,0.08); }

      .pp-fb-body {
        padding: 16px;
      }

      /* Star Rating */
      .pp-fb-stars {
        display: flex;
        gap: 6px;
        justify-content: center;
        margin-bottom: 14px;
      }
      .pp-fb-star {
        font-size: 24px;
        color: #3d5054;
        cursor: pointer;
        transition: transform 0.15s, color 0.15s;
        user-select: none;
      }
      .pp-fb-star.active { color: #fbbf24; }
      .pp-fb-star:hover { transform: scale(1.15); }

      /* Category Pills */
      .pp-fb-cats {
        display: flex;
        gap: 6px;
        margin-bottom: 12px;
      }
      .pp-fb-cat-pill {
        flex: 1;
        padding: 6px 8px;
        font-size: 11px;
        font-weight: 600;
        text-align: center;
        background: #0d1517;
        border: 1px solid #24363b;
        border-radius: 6px;
        color: #8ca3a2;
        cursor: pointer;
        transition: all 0.15s;
      }
      .pp-fb-cat-pill.active {
        background: #ff4b26;
        border-color: #ff4b26;
        color: #fff;
      }

      .pp-fb-textarea {
        width: 100%;
        box-sizing: border-box;
        padding: 10px 12px;
        background: #0d1517;
        border: 1px solid #24363b;
        border-radius: 8px;
        color: #f0f5f4;
        font-size: 13px;
        font-family: inherit;
        resize: none;
        outline: none;
        height: 80px;
        margin-bottom: 10px;
      }
      .pp-fb-textarea:focus { border-color: #ff4b26; }

      .pp-fb-email {
        width: 100%;
        box-sizing: border-box;
        padding: 9px 12px;
        background: #0d1517;
        border: 1px solid #24363b;
        border-radius: 8px;
        color: #f0f5f4;
        font-size: 12px;
        font-family: inherit;
        outline: none;
        margin-bottom: 14px;
      }
      .pp-fb-email:focus { border-color: #ff4b26; }

      .pp-fb-submit {
        width: 100%;
        padding: 10px;
        background: #ff4b26;
        border: none;
        border-radius: 8px;
        color: #fff;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.15s;
      }
      .pp-fb-submit:hover { background: #e03e1b; }
      .pp-fb-submit:disabled { opacity: 0.6; cursor: not-allowed; }

      .pp-fb-success {
        text-align: center;
        padding: 24px 16px;
        display: none;
      }
      .pp-fb-success h5 {
        font-size: 16px;
        margin-bottom: 6px;
        color: #10b981;
      }
      .pp-fb-success p {
        font-size: 13px;
        color: #8ca3a2;
        margin: 0;
        line-height: 1.4;
      }

      /* Mobile adjustment so it sits nicely above mobile bar */
      @media (max-width: 768px) {
        .pp-feedback-btn {
          bottom: calc(76px + env(safe-area-inset-bottom, 0px));
          right: 16px;
          padding: 7px 13px;
          font-size: 12px;
        }
        .pp-feedback-card {
          bottom: calc(126px + env(safe-area-inset-bottom, 0px));
          right: 16px;
          width: calc(100vw - 32px);
        }
      }

      @media (max-width: 479px) {
        .pp-feedback-btn { width: 44px; height: 44px; justify-content: center; padding: 0; }
        .pp-feedback-btn > span:last-child { display: none; }
      }
      body:has(.modal-backdrop:not([hidden])) #pp-feedback-container,
      body:has(.command-backdrop:not([hidden])) #pp-feedback-container,
      body:has(dialog[open]) #pp-feedback-container { display: none; }
    `;
    document.head.appendChild(style);

    const container = document.createElement("div");
    container.id = "pp-feedback-container";
    container.innerHTML = `
      <button type="button" class="pp-feedback-btn" id="pp-btn-feedback-toggle" aria-label="Open feedback widget">
        <span class="fb-icon">💬</span>
        <span>Feedback</span>
      </button>

      <div class="pp-feedback-card" id="pp-feedback-popover">
        <div class="pp-fb-header">
          <h4><span>💡</span> Share Feedback</h4>
          <button type="button" class="pp-fb-close" id="pp-btn-feedback-close" aria-label="Close feedback widget">&times;</button>
        </div>

        <div class="pp-fb-body" id="pp-feedback-form-body">
          <div class="pp-fb-stars" id="pp-fb-star-group">
            <span class="pp-fb-star active" data-rating="1">★</span>
            <span class="pp-fb-star active" data-rating="2">★</span>
            <span class="pp-fb-star active" data-rating="3">★</span>
            <span class="pp-fb-star active" data-rating="4">★</span>
            <span class="pp-fb-star active" data-rating="5">★</span>
          </div>

          <div class="pp-fb-cats">
            <span class="pp-fb-cat-pill active" data-cat="general">General</span>
            <span class="pp-fb-cat-pill" data-cat="suggestion">Idea</span>
            <span class="pp-fb-cat-pill" data-cat="bug">Bug</span>
          </div>

          <textarea class="pp-fb-textarea" id="pp-fb-text-input" placeholder="What can we improve? Have a feature request?" maxlength="1000"></textarea>
          <input type="email" class="pp-fb-email" id="pp-fb-email-input" placeholder="Your email (optional, for follow-up)" />

          <button type="button" class="pp-fb-submit" id="pp-btn-feedback-submit">Send Feedback →</button>
        </div>

        <div class="pp-fb-success" id="pp-feedback-success-body">
          <div style="font-size: 36px; margin-bottom: 8px;">🚀</div>
          <h5>Thank You!</h5>
          <p>Your feedback directly shapes our roadmap.</p>
        </div>
      </div>
    `;
    document.body.appendChild(container);
  }

  function bindFeedbackEvents() {
    const btnToggle = document.getElementById("pp-btn-feedback-toggle");
    const btnClose = document.getElementById("pp-btn-feedback-close");
    const card = document.getElementById("pp-feedback-popover");
    const btnSubmit = document.getElementById("pp-btn-feedback-submit");
    const formBody = document.getElementById("pp-feedback-form-body");
    const successBody = document.getElementById("pp-feedback-success-body");
    const stars = document.querySelectorAll(".pp-fb-star");
    const catPills = document.querySelectorAll(".pp-fb-cat-pill");
    const textArea = document.getElementById("pp-fb-text-input");
    const emailInput = document.getElementById("pp-fb-email-input");

    if (btnToggle && card) {
      btnToggle.addEventListener("click", () => {
        const isOpen = card.style.display === "flex";
        card.style.display = isOpen ? "none" : "flex";
        if (!isOpen && textArea) textArea.focus();
      });
    }

    if (btnClose && card) {
      btnClose.addEventListener("click", dismissFeedback);
    }

    document.getElementById("settings-feedback-open")?.addEventListener("click", () => {
      const settings = document.getElementById("settings-modal");
      if (settings) settings.hidden = true;
      openFeedback();
    });
    document.addEventListener("paperplane:open-feedback", openFeedback);
    document.addEventListener("paperplane:auth-changed", event => {
      currentScope = event.detail?.userId ? `account-${String(event.detail.userId).trim()}` : "guest";
      dismissedInMemory = false;
      submittedInMemory = false;
      syncVisibility();
    });
    document.addEventListener("paperplane:workspace-view-changed", scheduleObstructionCheck);
    document.addEventListener("scroll", scheduleObstructionCheck, { passive: true, capture: true });
    window.addEventListener("resize", scheduleObstructionCheck, { passive: true });

    // Star Selection
    stars.forEach(star => {
      star.addEventListener("click", () => {
        const rating = parseInt(star.getAttribute("data-rating"), 10) || 5;
        selectedRating = rating;
        stars.forEach(s => {
          const r = parseInt(s.getAttribute("data-rating"), 10) || 1;
          s.classList.toggle("active", r <= rating);
        });
      });
    });

    // Category Selection
    catPills.forEach(pill => {
      pill.addEventListener("click", () => {
        catPills.forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        selectedCategory = pill.getAttribute("data-cat") || "general";
      });
    });

    // Submission
    if (btnSubmit) {
      btnSubmit.addEventListener("click", async () => {
        if (isSubmitting) return;
        const msg = (textArea ? textArea.value : "").trim();
        if (!msg) {
          if (textArea) {
            textArea.style.borderColor = "#ef4444";
            textArea.focus();
          }
          return;
        }

        const email = (emailInput ? emailInput.value : "").trim();
        isSubmitting = true;
        btnSubmit.disabled = true;
        btnSubmit.textContent = "Sending...";

        try {
          const resp = await fetch("/api/feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              rating: selectedRating,
              category: selectedCategory,
              message: msg,
              email: email
            })
          });

          const result = resp.ok ? await resp.json().catch(() => null) : null;
          if (resp.ok && result?.status === "ok" && result.feedback_id) {
            submittedInMemory = true;
            writeFlag("submitted");
            syncVisibility({ keepCardOpen: true });
            if (formBody) formBody.style.display = "none";
            if (successBody) successBody.style.display = "block";

            // Automatically close popover after 2.5s and reset
            setTimeout(() => {
              if (card) card.style.display = "none";
              if (formBody) formBody.style.display = "block";
              if (successBody) successBody.style.display = "none";
              if (textArea) textArea.value = "";
              if (emailInput) emailInput.value = "";
              selectedRating = 5;
              stars.forEach(s => s.classList.add("active"));
            }, 2500);
          } else {
            alert("Unable to send feedback. Please try again.");
          }
        } catch (e) {
          alert("Network error sending feedback.");
        } finally {
          isSubmitting = false;
          btnSubmit.disabled = false;
          btnSubmit.textContent = "Send Feedback →";
        }
      });
    }

    currentScope = feedbackScope();
    syncVisibility();
    scheduleObstructionCheck();
  }
})();
