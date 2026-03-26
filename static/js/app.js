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
});
