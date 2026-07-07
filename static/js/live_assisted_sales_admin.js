(function () {
  function enhanceSecretInput() {
    const input = document.querySelector("input[data-las-secret='true']");
    if (!input || input.dataset.lasSecretEnhanced === "true") {
      return;
    }

    input.dataset.lasSecretEnhanced = "true";

    // Wrap ONLY the input in a tight relative box. The field's rendered parent also holds the help
    // text below the input, so anchoring the toggle there centred the eye over the whole block and
    // pushed it below the input's bottom edge. A wrapper that hugs just the input keeps it centred.
    const wrapper = document.createElement("div");
    wrapper.className = "las-secret-input";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);
    input.classList.add("las-secret-input__field");

    const button = document.createElement("button");
    button.type = "button";
    button.className = "las-secret-input__toggle";
    button.setAttribute("aria-label", input.dataset.showLabel || "Show store API key");
    button.setAttribute("title", input.dataset.showLabel || "Show store API key");
    button.innerHTML = '<span class="material-symbols-outlined">visibility</span>';

    button.addEventListener("click", function () {
      const isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";

      const label = isHidden
        ? input.dataset.hideLabel || "Hide store API key"
        : input.dataset.showLabel || "Show store API key";
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.innerHTML = isHidden
        ? '<span class="material-symbols-outlined">visibility_off</span>'
        : '<span class="material-symbols-outlined">visibility</span>';
    });

    wrapper.appendChild(button);
  }

  function enhanceConnectionCheck() {
    const button = document.querySelector(".las-connection-panel__button");
    if (!button || button.dataset.lasCheckEnhanced === "true") {
      return;
    }
    const form = button.closest("form");
    if (!form) {
      return;
    }
    button.dataset.lasCheckEnhanced = "true";

    button.addEventListener("click", function (event) {
      // Save the form first so the check runs against the key the owner just typed. The plain link
      // hit a view that tested the *saved* record, so a freshly pasted-but-unsaved key looked empty
      // ("A store API key is required."). Saving persists it and save_model runs the connection test
      // in the same request, then admin's "_continue" keeps us on this page with the fresh result.
      event.preventDefault();
      const flag = document.createElement("input");
      flag.type = "hidden";
      flag.name = "_continue";
      flag.value = "1";
      form.appendChild(flag);
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.submit();
      }
    });
  }

  function enhance() {
    enhanceSecretInput();
    enhanceConnectionCheck();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhance);
  } else {
    enhance();
  }
})();
