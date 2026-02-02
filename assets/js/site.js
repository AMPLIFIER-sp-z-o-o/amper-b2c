document.addEventListener("DOMContentLoaded", function () {
  // Format prices using browser locale with Intl.NumberFormat
  formatPrices();

  // Detect and sync browser timezone
  detectAndSyncTimezone();

  // Initialize scroll to top button
  initScrollToTop();
});

const CURRENCY_LOCALES = {
  PLN: "pl-PL",
  EUR: "de-DE",
  USD: "en-US",
};

/**
 * Detect browser timezone and sync with server.
 * Uses Intl.DateTimeFormat to get IANA timezone (e.g., "Europe/Warsaw").
 * Sends to server once per session to avoid unnecessary requests.
 */
function detectAndSyncTimezone() {
  if (typeof Intl === "undefined" || !Intl.DateTimeFormat) {
    return;
  }

  try {
    const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!browserTz) return;

    // Check if we already synced this timezone in this session
    const syncedTz = sessionStorage.getItem("amplifier_tz_synced");
    if (syncedTz === browserTz) return;

    // Send timezone to server
    fetch("/users/set-timezone/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ timezone: browserTz }),
      credentials: "same-origin",
    })
      .then((response) => {
        if (response.ok) {
          sessionStorage.setItem("amplifier_tz_synced", browserTz);
        }
      })
      .catch(() => {
        // Silently fail - timezone detection is non-critical
      });
  } catch (e) {
    // Silently fail
  }
}

/**
 * Format all elements with data-price attribute using Intl.NumberFormat.
 * Locale is determined by currency: PLN→pl-PL, EUR→de-DE, USD→en-US.
 *
 * Usage in templates:
 *   <span data-price="12.99" data-currency="PLN">12.99</span>
 */
function formatPrices() {
  if (typeof Intl === "undefined" || !Intl.NumberFormat) {
    return; // Keep server-rendered fallback
  }

  const priceElements = document.querySelectorAll("[data-price]");

  priceElements.forEach((el) => {
    const value = parseFloat(el.dataset.price);
    const currency = el.dataset.currency || "PLN";
    const locale = CURRENCY_LOCALES[currency] || "pl-PL";

    if (isNaN(value)) return;

    try {
      el.textContent = new Intl.NumberFormat(locale, {
        style: "currency",
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
    } catch (e) {
      // Keep server-rendered fallback on error
      console.warn("Price formatting error:", e);
    }
  });
}

// Re-format prices after HTMX swaps (for dynamic content)
document.addEventListener("htmx:afterSwap", formatPrices);

/**
 * Initialize scroll to top button behavior.
 * Shows button after scrolling 300px and scrolls to top on click.
 */
function initScrollToTop() {
  const scrollBtn = document.getElementById("scroll-to-top");
  if (!scrollBtn) return;

  window.addEventListener("scroll", () => {
    if (window.scrollY > 300) {
      scrollBtn.classList.remove("hidden");
      // Use a small timeout to allow "hidden" removal to register for transitions
      setTimeout(() => {
        scrollBtn.classList.add("opacity-100");
        scrollBtn.classList.remove("opacity-0");
      }, 10);
    } else {
      scrollBtn.classList.add("opacity-0");
      scrollBtn.classList.remove("opacity-100");
      // Wait for transition before hiding
      setTimeout(() => {
        if (window.scrollY <= 300) {
          scrollBtn.classList.add("hidden");
        }
      }, 300);
    }
  });

  scrollBtn.addEventListener("click", () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  });
}

