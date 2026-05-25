(function () {
  function enhanceSecretInput() {
    const input = document.querySelector("input[data-las-secret='true']");
    if (!input || input.dataset.lasSecretEnhanced === "true") {
      return;
    }

    const parent = input.parentElement;
    if (!parent) {
      return;
    }

    input.dataset.lasSecretEnhanced = "true";
    parent.classList.add("las-secret-input");
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

    parent.appendChild(button);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceSecretInput);
  } else {
    enhanceSecretInput();
  }
})();
