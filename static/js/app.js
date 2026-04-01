document.addEventListener("DOMContentLoaded", () => {
  const familyModeInput = document.querySelector("[data-family-mode-input]");
  const createPanel = document.querySelector("[data-family-create]");
  const joinPanel = document.querySelector("[data-family-join]");
  const acceptedTermsCheckbox = document.getElementById("accepted_terms");
  const registerSubmitButton = document.getElementById("register-submit");

  if (familyModeInput && createPanel && joinPanel) {
    const syncFamilyMode = (mode) => {
      const isJoin = mode === "join";
      createPanel.classList.toggle("hidden", isJoin);
      joinPanel.classList.toggle("hidden", !isJoin);
    };

    syncFamilyMode(familyModeInput.value);

    document.querySelectorAll("[data-family-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        const mode = button.dataset.familyMode;
        familyModeInput.value = mode;
        syncFamilyMode(mode);
      });
    });
  }

  if (acceptedTermsCheckbox && registerSubmitButton) {
    const syncRegisterSubmit = () => {
      registerSubmitButton.disabled = !acceptedTermsCheckbox.checked;
    };

    syncRegisterSubmit();
    acceptedTermsCheckbox.addEventListener("change", syncRegisterSubmit);
    acceptedTermsCheckbox.addEventListener("wa-change", syncRegisterSubmit);
  }

  const eventTypeSelect = document.querySelector("[data-event-type]");
  const unitInput = document.querySelector("[data-unit-input]");
  const amountInput = document.querySelector("[data-amount-input]");
  const endTimeWrap = document.querySelector("[data-end-time-wrap]");

  if (eventTypeSelect && unitInput && amountInput && endTimeWrap) {
    const suggestions = {
      feeding: { unit: "ml", showAmount: true, showEnd: false },
      sleep: { unit: "分钟", showAmount: false, showEnd: true },
      diaper: { unit: "次", showAmount: true, showEnd: false },
      health: { unit: "次", showAmount: false, showEnd: false },
      milestone: { unit: "", showAmount: false, showEnd: false }
    };

    const syncEventFields = (value) => {
      const config = suggestions[value] || suggestions.feeding;
      if (config.unit) {
        unitInput.value = config.unit;
      }
      amountInput.closest("wa-input")?.classList.toggle("hidden", !config.showAmount);
      endTimeWrap.classList.toggle("hidden", !config.showEnd);
    };

    syncEventFields(eventTypeSelect.value);
    eventTypeSelect.addEventListener("change", (event) => syncEventFields(event.target.value));
  }

  initDashboardAjax();
});

// ── Toast notification ──────────────────────────────────────────────────────

function showToast(message, type = "success") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.style.cssText =
      "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:9999;" +
      "display:flex;flex-direction:column;align-items:center;gap:10px;pointer-events:none;";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  const isSuccess = type === "success";
  toast.style.cssText =
    "padding:12px 20px;border-radius:12px;font-size:0.92rem;font-weight:500;" +
    "box-shadow:0 8px 28px rgba(0,0,0,0.18);pointer-events:auto;" +
    "opacity:0;transform:translateY(12px);transition:opacity 0.22s,transform 0.22s;" +
    (isSuccess
      ? "background:#5d9f7a;color:#fff;"
      : "background:#c0392b;color:#fff;");
  toast.textContent = message;
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.style.opacity = "1";
    toast.style.transform = "translateY(0)";
  });

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(12px)";
    setTimeout(() => toast.remove(), 250);
  }, 3200);
}

// ── Dashboard AJAX forms ────────────────────────────────────────────────────

function getActiveTabPanel() {
  const tabGroup = document.querySelector("wa-tab-group");
  if (!tabGroup) return null;
  // Try the web-component activeTab property first, fallback to attribute
  const activeTab = tabGroup.activeTab || tabGroup.getAttribute("active-tab");
  if (activeTab) return typeof activeTab === "string" ? activeTab : activeTab.panel;
  // Fallback: find the tab with [active] attribute
  const activeEl = document.querySelector("wa-tab[active]");
  return activeEl ? activeEl.getAttribute("panel") : null;
}

function restoreTabPanel(panelName) {
  if (!panelName) return;
  const tabGroup = document.querySelector("wa-tab-group");
  if (!tabGroup) return;
  const tab = document.querySelector(`wa-tab[panel="${panelName}"]`);
  if (tab) tab.click();
}

async function refreshDashboardSections() {
  const resp = await fetch(window.location.pathname, { headers: { "Cache-Control": "no-cache" } });
  if (!resp.ok) return;
  const html = await resp.text();
  const doc = new DOMParser().parseFromString(html, "text/html");

  // Stats bar (now inside hero card)
  const newStats = doc.querySelector(".hero-stats-row");
  const curStats = document.querySelector(".hero-stats-row");
  if (newStats && curStats) curStats.innerHTML = newStats.innerHTML;

  // Per-tab display panels (left-side result panels, not forms)
  const tabPanels = ["babies", "records", "photos", "growth", "vaccines"];
  tabPanels.forEach((name) => {
    const newPanel = doc.querySelector(`wa-tab-panel[name="${name}"]`);
    const curPanel = document.querySelector(`wa-tab-panel[name="${name}"]`);
    if (!newPanel || !curPanel) return;

    // Replace only the first child (display panel / timeline-card), keep the form panel
    const newDisplay = newPanel.firstElementChild;
    const curDisplay = curPanel.firstElementChild;
    if (newDisplay && curDisplay) curDisplay.replaceWith(newDisplay);
  });
}

function initDashboardAjax() {
  // Only activate on the dashboard page
  if (!document.querySelector("wa-tab-group")) return;

  document.querySelectorAll('form[method="post"]').forEach((form) => {
    // Skip forms that are outside the tabs section (e.g. hidden system forms)
    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const activePanel = getActiveTabPanel();
      const submitBtn = form.querySelector('wa-button[type="submit"]');
      if (submitBtn) submitBtn.setAttribute("loading", "");

      try {
        const resp = await fetch("/dashboard", {
          method: "POST",
          headers: { "X-Requested-With": "XMLHttpRequest" },
          body: new FormData(form),
        });

        if (!resp.ok) throw new Error("server error");
        const json = await resp.json();

        showToast(json.message, json.ok ? "success" : "error");

        if (json.ok) {
          // Reset only text/select/date fields; keep file input alone
          form.querySelectorAll("input:not([type=hidden]):not([type=file]), textarea").forEach((el) => {
            el.value = "";
          });
          form.querySelectorAll("wa-input, wa-textarea").forEach((el) => {
            el.value = "";
          });
          await refreshDashboardSections();
          restoreTabPanel(activePanel);
        }
      } catch (_err) {
        showToast("提交失败，请稍后重试。", "error");
      } finally {
        if (submitBtn) submitBtn.removeAttribute("loading");
      }
    });
  });
}
