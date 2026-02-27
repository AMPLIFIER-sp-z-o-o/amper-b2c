(function () {
  async function copyToClipboard(text) {
    if (!text) return false;

    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "readonly");
    textarea.style.position = "fixed";
    textarea.style.top = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  }

  function initShareIdCopy() {
    const buttons = document.querySelectorAll("[data-share-id-copy-btn]");
    if (!buttons.length) return;

    buttons.forEach((button) => {
      if (button.dataset.copyInit === "true") return;
      button.dataset.copyInit = "true";

      button.addEventListener("click", async function () {
        const shareId = this.getAttribute("data-share-id") || "";
        if (!shareId) return;

        const icon = this.querySelector(".material-symbols-outlined");
        const prev = icon ? icon.textContent : null;
        const label = this.querySelector(".share-id-copy-label");
        const copyLabel = this.dataset.copyLabel || "Copy";
        const copiedLabel = this.dataset.copiedLabel || "Copied";
        const errorLabel = this.dataset.errorLabel || "Error";

        try {
          const copied = await copyToClipboard(shareId);
          if (copied) {
            if (icon) {
              icon.textContent = "check";
            }
            if (label) {
              label.textContent = copiedLabel;
            }
            this.classList.add("is-copied");
            setTimeout(() => {
              if (icon) {
                icon.textContent = prev || "content_copy";
              }
              if (label) {
                label.textContent = copyLabel;
              }
              this.classList.remove("is-copied");
            }, 1400);
          }
        } catch (e) {
          if (icon) {
            icon.textContent = "error";
          }
          if (label) {
            label.textContent = errorLabel;
          }
          setTimeout(() => {
            if (icon) {
              icon.textContent = prev || "content_copy";
            }
            if (label) {
              label.textContent = copyLabel;
            }
          }, 1400);
        }
      });
    });
  }

  function initWishlistRowClick() {
    const body = document.body;
    if (!body.classList.contains("app-favorites") || !body.classList.contains("model-wishlist")) {
      return;
    }
    if (!body.classList.contains("change-list")) {
      return;
    }

    const rows = document.querySelectorAll("#result_list tbody tr");
    rows.forEach((row) => {
      if (row.dataset.rowNavInit === "true") return;
      row.dataset.rowNavInit = "true";

      const targetLink = row.querySelector("th a, td.field-name a");
      if (!targetLink) return;

      row.addEventListener("click", function (event) {
        const target = event.target;
        if (target.closest("a, button, input, textarea, select, label")) {
          return;
        }
        targetLink.click();
      });
    });
  }

  function initWishlistAdminEnhancements() {
    initShareIdCopy();
    initWishlistRowClick();
  }

  document.addEventListener("DOMContentLoaded", initWishlistAdminEnhancements);
  if (document.readyState !== "loading") {
    initWishlistAdminEnhancements();
  }
})();
