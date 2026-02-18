import "../css/site.css";

const TAB_PARAM = "__tab";
const TAB_HEADER = "X-Tab-ID";

function normalizeTabId(rawValue) {
  if (!rawValue) return null;
  const value = String(rawValue).trim();
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(value)) return null;
  return value;
}

function getActiveTabId() {
  const fromUrl = normalizeTabId(
    new URLSearchParams(window.location.search).get(TAB_PARAM),
  );
  if (fromUrl) return fromUrl;
  return null;
}

function withTabParam(rawUrl, tabId) {
  if (!tabId) return rawUrl;
  const url = new URL(rawUrl, window.location.href);
  if (url.origin !== window.location.origin) return rawUrl;
  url.searchParams.set(TAB_PARAM, tabId);
  return `${url.pathname}${url.search}${url.hash}`;
}

function setTabHintCookie(tabId) {
  if (!tabId) return;
  document.cookie = `amper_tab_id=${encodeURIComponent(tabId)}; path=/; samesite=lax`;
}

function applyTabParamToAnchors(tabId, root = document) {
  if (!tabId || !root || !root.querySelectorAll) return;
  root.querySelectorAll("a[href]").forEach((anchor) => {
    const href = anchor.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("javascript:")) return;
    if (anchor.hasAttribute("data-tab-scoped")) return;

    const scopedHref = withTabParam(href, tabId);
    if (scopedHref !== href) {
      anchor.setAttribute("href", scopedHref);
    }
    anchor.setAttribute("data-tab-scoped", "1");
  });
}

function applyTabParamToForms(tabId, root = document) {
  if (!tabId || !root || !root.querySelectorAll) return;
  root.querySelectorAll("form[action]").forEach((form) => {
    const action = form.getAttribute("action");
    if (!action || action.startsWith("javascript:")) return;
    if (form.hasAttribute("data-tab-scoped")) return;

    const scopedAction = withTabParam(action, tabId);
    if (scopedAction !== action) {
      form.setAttribute("action", scopedAction);
    }
    form.setAttribute("data-tab-scoped", "1");
  });
}

function initTabScopedNavigation() {
  const tabId = getActiveTabId();
  if (!tabId) {
    sessionStorage.removeItem("amper_tab_id");
    return;
  }

  window.__AMPER_TAB_ID = tabId;
  setTabHintCookie(tabId);

  applyTabParamToAnchors(tabId, document);
  applyTabParamToForms(tabId, document);

  const originalFetch = window.fetch;
  if (typeof originalFetch === "function" && !window.__amperTabFetchWrapped) {
    window.fetch = function (input, init = {}) {
      const currentTabId = window.__AMPER_TAB_ID;
      if (!currentTabId) return originalFetch(input, init);

      const nextInit = { ...init };
      const headers = new Headers(nextInit.headers || {});
      headers.set(TAB_HEADER, currentTabId);
      nextInit.headers = headers;

      setTabHintCookie(currentTabId);
      return originalFetch(input, nextInit);
    };
    window.__amperTabFetchWrapped = true;
  }

  document.body?.addEventListener(
    "click",
    (event) => {
      const anchor = event.target.closest("a[href]");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#") || href.startsWith("javascript:"))
        return;
      const scopedHref = withTabParam(href, tabId);
      if (scopedHref !== href) {
        anchor.setAttribute("href", scopedHref);
      }
      setTabHintCookie(tabId);
    },
    true,
  );

  document.body?.addEventListener(
    "submit",
    (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      const action = form.getAttribute("action");
      if (action) {
        form.setAttribute("action", withTabParam(action, tabId));
      }
      setTabHintCookie(tabId);
    },
    true,
  );

  document.addEventListener("htmx:configRequest", (event) => {
    if (!window.__AMPER_TAB_ID) return;
    event.detail.headers = event.detail.headers || {};
    event.detail.headers[TAB_HEADER] = window.__AMPER_TAB_ID;
    setTabHintCookie(window.__AMPER_TAB_ID);
  });

  document.addEventListener("htmx:afterSwap", (event) => {
    applyTabParamToAnchors(tabId, event.target || document);
    applyTabParamToForms(tabId, event.target || document);
  });
}

initTabScopedNavigation();

document.addEventListener("DOMContentLoaded", function () {
  // Format prices using browser locale with Intl.NumberFormat
  formatPrices();

  // Keep Sign In link in sync with the current browser URL
  updateSignInLink();

  // Detect and sync browser timezone
  detectAndSyncTimezone();

  // Initialize scroll to top button
  initScrollToTop();

  // Initialize Swiper sliders
  initCategoryRecommendedSlider();
  initCategoryBannerSlider();

  // Initialize favourites
  initFavourites();

  // Initialize cart "Save as list" modal
  initCartSaveAsList();

  // Initialize product compare buttons state
  syncCompareButtons(document);

  // Initialize relative time labels (auto-refresh every 30s)
  initRelativeTimes();
});

function initCartSaveAsList() {
  const form = document.getElementById("save-as-list-form");
  if (!form || form.dataset.initialized) return;
  form.dataset.initialized = "1";

  const nameInput = document.getElementById("save-as-list-name");
  const submitBtn = document.getElementById("save-as-list-submit");
  const errorBox = document.getElementById("save-as-list-error");

  document
    .querySelectorAll('[data-modal-toggle="save-as-list-modal"]')
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        if (errorBox) errorBox.innerHTML = "";
        if (submitBtn) window.btnReset?.(submitBtn);
        // Flowbite shows the modal asynchronously; delay focus slightly.
        window.setTimeout(() => {
          nameInput?.focus();
          nameInput?.select?.();
        }, 50);
      });
    });

  form.addEventListener("htmx:beforeRequest", () => {
    if (errorBox) errorBox.innerHTML = "";
    if (submitBtn) window.btnLoading?.(submitBtn);
  });

  form.addEventListener("htmx:afterRequest", (event) => {
    const status = event?.detail?.xhr?.status;
    if (typeof status === "number" && status >= 400) {
      if (submitBtn) window.btnReset?.(submitBtn);
    }
  });

  form.addEventListener("htmx:responseError", () => {
    if (submitBtn) window.btnReset?.(submitBtn);
  });
}

/* ============================================
   PRODUCT SHARE / COMPARE / IMAGE FULLSCREEN
   ============================================ */

const COMPARE_STORAGE_KEY = "amper_compare_products";

function isPolishUi() {
  return (document.documentElement.lang || "").toLowerCase().startsWith("pl");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function copyTextToClipboard(text) {
  if (!text) return false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall back
  }

  try {
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
  } catch {
    return false;
  }
}

function getCompareList() {
  try {
    const raw = localStorage.getItem(COMPARE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((v) => parseInt(v, 10)).filter((n) => Number.isFinite(n));
  } catch {
    return [];
  }
}

function setCompareList(list) {
  try {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(list));
  } catch {
    // ignore (private mode / storage denied)
  }
}

function toggleComparedProduct(productId) {
  const list = getCompareList();
  const idx = list.indexOf(productId);
  if (idx >= 0) {
    list.splice(idx, 1);
    setCompareList(list);
    return { compared: false, list };
  }
  list.push(productId);
  setCompareList(list);
  return { compared: true, list };
}

function syncCompareButtons(root = document) {
  const comparedSet = new Set(getCompareList());
  root
    .querySelectorAll(".product-compare-btn[data-product-id]")
    .forEach((btn) => {
      const productId = parseInt(btn.dataset.productId, 10);
      if (!Number.isFinite(productId)) return;

      const isCompared = comparedSet.has(productId);
      btn.setAttribute("aria-pressed", isCompared ? "true" : "false");
      btn.classList.toggle("is-compared", isCompared);

      const usesHoverOpacity =
        btn.classList.contains("opacity-0") ||
        btn.classList.contains("group-hover:opacity-100");
      if (usesHoverOpacity) {
        if (isCompared) {
          btn.classList.remove("opacity-0");
          btn.classList.add("opacity-100");
        } else {
          btn.classList.remove("opacity-100");
          btn.classList.add("opacity-0");
        }
      }

      const icon = btn.querySelector(".compare-icon");
      if (icon) {
        icon.classList.toggle("text-gray-400", !isCompared);
        icon.classList.toggle("text-primary-600", isCompared);
        icon.classList.toggle("dark:text-primary-500", isCompared);
      }

      if (isCompared) {
        btn.title = isPolishUi()
          ? "Usuń z porównania"
          : "Remove from comparison";
      } else {
        btn.title = isPolishUi() ? "Dodaj do porównania" : "Add to comparison";
      }
    });
}

function ensureProductImageFullscreenOverlay() {
  let overlay = document.getElementById("product-image-fullscreen-overlay");
  if (overlay) return overlay;

  overlay = document.createElement("div");
  overlay.id = "product-image-fullscreen-overlay";
  overlay.className =
    "fixed inset-0 z-[90] hidden items-center justify-center bg-black/80 p-4";
  overlay.innerHTML = `
    <div class="absolute inset-0" data-fullscreen-backdrop></div>
    <div class="relative w-full max-w-5xl">
      <button type="button" class="absolute -top-2 -right-2 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors" data-fullscreen-close aria-label="Close" title="Close">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
        </svg>
      </button>
      <img data-fullscreen-img class="w-full max-h-[85vh] object-contain rounded-xl" alt="" src="" />
    </div>
  `;

  document.body.appendChild(overlay);

  const close = () => {
    overlay.classList.add("hidden");
    overlay.classList.remove("flex");
    document.body.classList.remove("overflow-hidden");
    const img = overlay.querySelector("[data-fullscreen-img]");
    if (img) {
      img.removeAttribute("src");
      img.setAttribute("alt", "");
    }
  };

  overlay
    .querySelector("[data-fullscreen-close]")
    ?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      close();
    });
  overlay
    .querySelector("[data-fullscreen-backdrop]")
    ?.addEventListener("click", (e) => {
      e.preventDefault();
      close();
    });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!overlay.classList.contains("hidden")) close();
  });

  overlay._close = close;
  return overlay;
}

async function handleProductShare(btn) {
  const rawUrl = btn.dataset.shareUrl || window.location.href;
  const url = /^https?:\/\//i.test(rawUrl)
    ? rawUrl
    : new URL(rawUrl, window.location.origin).toString();
  const title = btn.dataset.shareTitle || document.title;

  if (navigator.share) {
    try {
      // Fire-and-forget: on many platforms the returned Promise resolves only
      // after the share sheet closes. We don't want to keep the button in a
      // loading state for that long.
      navigator.share({ title, url }).catch(() => {});
      return;
    } catch {
      // fall back to copy
    }
  }

  const ok = await copyTextToClipboard(url);
  if (ok) {
    window.showToast?.(
      isPolishUi() ? "Link skopiowany do schowka" : "Link copied to clipboard",
      "success",
    );
  } else {
    window.showToast?.(
      isPolishUi()
        ? "Nie udało się skopiować linku"
        : "Could not copy the link",
      "error",
    );
  }
}

// Event delegation for product actions
document.addEventListener("click", async (e) => {
  const shareBtn = e.target.closest?.(".product-share-btn");
  if (shareBtn) {
    e.preventDefault();
    e.stopPropagation();
    if (shareBtn.classList.contains("btn-loading")) return;
    try {
      window.btnLoading?.(shareBtn);
      await handleProductShare(shareBtn);
    } finally {
      window.btnReset?.(shareBtn);
    }
    return;
  }

  const compareBtn = e.target.closest?.(".product-compare-btn");
  if (compareBtn) {
    e.preventDefault();
    e.stopPropagation();

    const productId = parseInt(compareBtn.dataset.productId, 10);
    if (!Number.isFinite(productId)) return;

    const productName = compareBtn.dataset.productName || "";
    const nameEsc = escapeHtml(productName);

    const { compared } = toggleComparedProduct(productId);
    syncCompareButtons(document);

    if (window.showToast) {
      if (compared) {
        window.showToast(
          isPolishUi()
            ? `Dodano <strong>${nameEsc}</strong> do porównania`
            : `Added <strong>${nameEsc}</strong> to comparison`,
          "success",
        );
      } else {
        window.showToast(
          isPolishUi()
            ? `Usunięto <strong>${nameEsc}</strong> z porównania`
            : `Removed <strong>${nameEsc}</strong> from comparison`,
          "success",
        );
      }
    }
    return;
  }

  const fsBtn = e.target.closest?.(".product-image-fullscreen-btn");
  if (fsBtn) {
    e.preventDefault();
    e.stopPropagation();
    const src = fsBtn.dataset.fullscreenSrc;
    if (!src) return;

    const alt = fsBtn.dataset.fullscreenAlt || "";
    const overlay = ensureProductImageFullscreenOverlay();
    const img = overlay.querySelector("[data-fullscreen-img]");
    if (img) {
      img.setAttribute("src", src);
      img.setAttribute("alt", alt);
    }
    overlay.classList.remove("hidden");
    overlay.classList.add("flex");
    document.body.classList.add("overflow-hidden");
  }
});

/* ============================================
   BUTTON LOADING STATE UTILITIES
   ============================================ */

const SPINNER_SVG =
  '<svg fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';

// Prevent unpleasant flicker when requests finish very fast.
// Keep the loading state visible for at least this many milliseconds.
const BTN_LOADING_MIN_DURATION_MS = 350;

function resetBtnNow(btn) {
  if (!btn) return;
  btn.classList.remove("btn-loading");
  btn.removeAttribute("aria-disabled");
  btn.querySelector(".btn-spinner")?.remove();
  // Restore hidden SVG icon
  const hiddenIcon = btn.querySelector(":scope > svg[data-btn-hidden]");
  if (hiddenIcon) {
    delete hiddenIcon.dataset.btnHidden;
    hiddenIcon.style.display = "";
  }
  // Remove temporarily added flex classes
  if (btn.dataset.btnFlexAdded) {
    btn.classList.remove(
      "inline-flex",
      "items-center",
      "justify-center",
      "gap-2",
    );
    delete btn.dataset.btnFlexAdded;
  }
  if (btn.dataset.btnGapAdded) {
    btn.classList.remove("gap-2");
    delete btn.dataset.btnGapAdded;
  }
  delete btn._btnLoadingStartedAt;
}

/**
 * Set a button into loading state: disable it, dim it, show a spinner.
 * @param {HTMLButtonElement} btn
 */
function btnLoading(btn) {
  if (!btn || btn.classList.contains("btn-loading")) return;

  // If a reset was scheduled (min-duration), cancel it.
  if (btn._btnLoadingResetTimeoutId) {
    clearTimeout(btn._btnLoadingResetTimeoutId);
    delete btn._btnLoadingResetTimeoutId;
  }

  btn._btnLoadingStartedAt =
    typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : Date.now();

  btn.classList.add("btn-loading");
  btn.setAttribute("aria-disabled", "true");
  // Ensure button has flex layout for proper spinner + text alignment
  if (
    !btn.classList.contains("inline-flex") &&
    !btn.classList.contains("flex")
  ) {
    btn.classList.add("inline-flex", "items-center", "justify-center", "gap-2");
    btn.dataset.btnFlexAdded = "1";
  } else {
    // If it already has flex, ensure it has a gap for the spinner
    const hasGap = Array.from(btn.classList).some((c) => c.startsWith("gap-"));
    if (!hasGap) {
      btn.classList.add("gap-2");
      btn.dataset.btnGapAdded = "1";
    }
  }
  // Hide existing SVG icon (direct child) to replace with spinner.
  // Allow opting out for icons that must stay visible (e.g. cart/checkout arrows).
  const existingIcon = btn.querySelector(
    ":scope > svg:not([data-keep-on-loading])",
  );
  if (existingIcon) {
    existingIcon.dataset.btnHidden = "1";
    existingIcon.style.display = "none";
  }
  const spinner = document.createElement("span");
  spinner.className = "btn-spinner";
  spinner.innerHTML = SPINNER_SVG;
  btn.prepend(spinner);
}

/**
 * Reset a button from loading state back to normal.
 * @param {HTMLButtonElement} btn
 */
function btnReset(btn) {
  if (!btn) return;

  const startedAt = btn._btnLoadingStartedAt;
  if (typeof startedAt === "number") {
    const now =
      typeof performance !== "undefined" &&
      typeof performance.now === "function"
        ? performance.now()
        : Date.now();
    const elapsed = now - startedAt;
    const remaining = BTN_LOADING_MIN_DURATION_MS - elapsed;

    if (remaining > 0) {
      if (btn._btnLoadingResetTimeoutId) {
        clearTimeout(btn._btnLoadingResetTimeoutId);
      }
      btn._btnLoadingResetTimeoutId = setTimeout(() => {
        // Button might have been removed from DOM; in that case this is harmless.
        delete btn._btnLoadingResetTimeoutId;
        resetBtnNow(btn);
      }, remaining);
      return;
    }
  }

  resetBtnNow(btn);
}

window.btnLoading = btnLoading;
window.btnReset = btnReset;

// Global guard: while a control is in loading state, prevent any click/keyboard re-activation.
// This keeps UX consistent across the whole storefront, even if some handlers forget to check btn-loading.
document.addEventListener(
  "click",
  function (e) {
    const el = e.target.closest(".btn-loading");
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
  },
  true,
);

document.addEventListener(
  "keydown",
  function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest?.(".btn-loading");
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
  },
  true,
);

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
 * Locale is determined by currency: USD→en-US, EUR→de-DE, PLN→pl-PL.
 *
 * Usage in templates:
 *   <span data-price="12.99" data-currency="USD">12.99</span>
 */
function formatPrices() {
  if (typeof Intl === "undefined" || !Intl.NumberFormat) {
    return; // Keep server-rendered fallback
  }

  const priceElements = document.querySelectorAll("[data-price]");

  priceElements.forEach((el) => {
    const value = parseFloat(el.dataset.price);
    const currency = el.dataset.currency || "USD";
    const locale = CURRENCY_LOCALES[currency] || "en-US";

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
window.formatPrices = formatPrices;

function initCategoryRecommendedSlider() {
  const swiperContainers = document.querySelectorAll(
    ".category-recommended-swiper",
  );
  if (!swiperContainers.length) return;

  if (typeof Swiper === "undefined") {
    window.setTimeout(initCategoryRecommendedSlider, 100);
    return;
  }

  window.__categoryRecommendedSwipers =
    window.__categoryRecommendedSwipers || {};

  swiperContainers.forEach((swiperContainer) => {
    const categoryId = swiperContainer.dataset.categoryId;
    if (!categoryId) return;

    if (window.__categoryRecommendedSwipers[categoryId]) {
      try {
        window.__categoryRecommendedSwipers[categoryId].destroy(true, true);
      } catch (e) {
        // Ignore destroy errors
      }
      delete window.__categoryRecommendedSwipers[categoryId];
    }

    if (swiperContainer.swiper) {
      try {
        swiperContainer.swiper.destroy(true, true);
      } catch (e) {
        // Ignore destroy errors
      }
    }

    const productCount =
      parseInt(swiperContainer.dataset.productCount, 10) || 0;

    const swiper = new Swiper(swiperContainer, {
      slidesPerView: 1,
      slidesPerGroup: 1,
      spaceBetween: 12,
      loop: false,
      autoHeight: false,
      navigation: {
        nextEl:
          '.category-recommended-next[data-category-id="' + categoryId + '"]',
        prevEl:
          '.category-recommended-prev[data-category-id="' + categoryId + '"]',
        disabledClass: "swiper-button-disabled",
      },
      breakpoints: {
        480: {
          slidesPerView: 2,
          slidesPerGroup: 2,
          spaceBetween: 12,
        },
        640: {
          slidesPerView: 2,
          slidesPerGroup: 2,
          spaceBetween: 16,
        },
        768: {
          slidesPerView: 3,
          slidesPerGroup: 3,
          spaceBetween: 16,
        },
        1024: {
          slidesPerView: 4,
          slidesPerGroup: 4,
          spaceBetween: 16,
        },
      },
    });

    window.__categoryRecommendedSwipers[categoryId] = swiper;
  });

  formatPrices();
}

window.initCategoryRecommendedSlider = initCategoryRecommendedSlider;

/**
 * Initialize category banner sliders.
 * Uses data-category-id and data-banner-count attributes from markup.
 * Called on DOMContentLoaded and after HTMX swaps.
 *
 * Note: Multiple swipers can share the same categoryId (e.g., header and mobile versions).
 * Each is initialized independently using scoped selectors within its parent container.
 */
function initCategoryBannerSlider() {
  const swiperContainers = document.querySelectorAll(".category-banner-swiper");
  if (!swiperContainers.length) return;

  if (typeof Swiper === "undefined") {
    window.setTimeout(initCategoryBannerSlider, 100);
    return;
  }

  window.__categoryBannerSwipers = window.__categoryBannerSwipers || {};

  swiperContainers.forEach((swiperContainer) => {
    const categoryId = swiperContainer.dataset.categoryId;
    if (!categoryId) return;

    // Skip if already initialized
    if (swiperContainer.swiper) return;

    // Find the parent container to scope navigation/tabs selectors
    const parentContainer = swiperContainer.closest(".category-banner-slider");
    if (!parentContainer) return;

    // Use parent container ID for unique registry key (each slider has unique parent ID)
    const registryKey = parentContainer.id || categoryId;

    // Clean up old instance if exists in registry
    if (window.__categoryBannerSwipers[registryKey]) {
      try {
        window.__categoryBannerSwipers[registryKey].destroy(true, true);
      } catch (e) {
        // Ignore destroy errors
      }
      delete window.__categoryBannerSwipers[registryKey];
    }

    const bannerCount = parseInt(swiperContainer.dataset.bannerCount, 10) || 0;

    // Scope tabs to this parent container only
    const tabs = parentContainer.querySelectorAll(".category-banner-tab");

    // Scope navigation buttons to this parent container only
    const nextEl = parentContainer.querySelector(".category-banner-next");
    const prevEl = parentContainer.querySelector(".category-banner-prev");

    function updateActiveTabs(activeIndex) {
      tabs.forEach((tab, index) => {
        if (index === activeIndex) {
          tab.classList.add("active");
          tab.classList.remove(
            "text-gray-500",
            "dark:text-gray-400",
            "font-medium",
            "border-transparent",
          );
          tab.classList.add(
            "text-primary-600",
            "dark:text-primary-500",
            "font-semibold",
            "border-primary-600",
            "dark:border-primary-500",
          );
        } else {
          tab.classList.remove(
            "active",
            "font-semibold",
            "border-primary-600",
            "dark:border-primary-500",
          );
          tab.classList.add(
            "text-gray-500",
            "dark:text-gray-400",
            "font-medium",
            "border-transparent",
          );
          tab.classList.remove("text-primary-600", "dark:text-primary-500");
        }
      });
    }

    const swiper = new Swiper(swiperContainer, {
      slidesPerView: 1,
      spaceBetween: 0,
      loop: bannerCount > 1,
      autoplay: {
        delay: 5000,
        disableOnInteraction: false,
        pauseOnMouseEnter: true,
      },
      navigation: {
        nextEl: nextEl,
        prevEl: prevEl,
      },
      on: {
        slideChange: function () {
          updateActiveTabs(this.realIndex);
        },
      },
    });

    // Tab click handlers
    tabs.forEach((tab) => {
      tab.addEventListener("click", function () {
        const slideIndex = parseInt(this.dataset.slideIndex, 10);
        swiper.slideToLoop(slideIndex);
        updateActiveTabs(slideIndex);
      });
    });

    window.__categoryBannerSwipers[registryKey] = swiper;
  });
}

window.initCategoryBannerSlider = initCategoryBannerSlider;

/**
 * Keep the navbar "Sign In" link in sync with the current browser URL.
 * Uses window.location instead of server-rendered request.get_full_path
 * so that HTMX pushState / filter changes are always reflected.
 * Skips adding ?next= when on the homepage since "/" is the default redirect.
 */
function updateSignInLink() {
  const link = document.getElementById("nav-sign-in-link");
  if (!link) return;
  const baseUrl = link.dataset.loginUrl;
  const path = window.location.pathname + window.location.search;
  if (path === "/" || path === "") {
    link.href = baseUrl;
  } else {
    link.href = baseUrl + "?next=" + encodeURIComponent(path);
  }
}
window.updateSignInLink = updateSignInLink;

// Re-format prices after HTMX swaps (for dynamic content)
document.addEventListener("htmx:afterSwap", formatPrices);
document.addEventListener("htmx:afterSwap", updateSignInLink);
// Also update on htmx:pushedIntoHistory (fired after hx-push-url updates the URL)
document.addEventListener("htmx:pushedIntoHistory", updateSignInLink);
// Update on browser back/forward navigation
window.addEventListener("popstate", updateSignInLink);
document.addEventListener("htmx:afterSwap", (event) => {
  if (event.target && event.target.id === "products-container") {
    initCategoryRecommendedSlider();
    initCategoryBannerSlider();
  }
});

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

/* ============================================
   FAVOURITES / WISHLISTS
   ============================================ */

/**
 * Initialize favourites functionality.
 * - Loads favourite status for all product cards
 * - Attaches click handlers to favourite buttons
 * - Shows wishlists dropdown on click
 */
function initFavourites() {
  // Load favourite status for all visible products
  loadFavouriteStatus();

  // Attach click handlers to favourite buttons
  attachFavouriteHandlers();
}

window.initFavourites = initFavourites;

/**
 * Load favourite status for all product cards on the page.
 * Updates the heart icon to filled if product is in any wishlist.
 */
async function loadFavouriteStatus() {
  // Get product IDs from product cards AND favourite buttons
  const productCards = document.querySelectorAll("[data-product-card]");
  const favouriteButtons = document.querySelectorAll(
    ".favourite-btn[data-product-id]",
  );

  // Collect all product IDs
  const productIdsFromCards = Array.from(productCards).map(
    (card) => card.dataset.productCard,
  );
  const productIdsFromButtons = Array.from(favouriteButtons).map(
    (btn) => btn.dataset.productId,
  );

  const uniqueIds = [
    ...new Set([...productIdsFromCards, ...productIdsFromButtons]),
  ];

  if (!uniqueIds.length) return;

  try {
    const response = await fetch(
      `/favourites/api/status/?product_ids=${uniqueIds.join(",")}`,
      { cache: "no-store" },
    );
    if (!response.ok) return;

    const data = await response.json();
    // status is a dict mapping product_id -> list of wishlist_ids
    const status = data.status || {};
    const favouriteIds = new Set(
      Object.keys(status).map((id) => parseInt(id, 10)),
    );

    // Update all favourite buttons – set filled or unfilled
    document.querySelectorAll(".favourite-btn").forEach((btn) => {
      // Skip buttons managed by favourites page (it has its own logic)
      if (btn.dataset.favouritePageManaged === "true") return;
      const productId = parseInt(btn.dataset.productId, 10);
      setFavouriteState(btn, favouriteIds.has(productId));
    });
  } catch (e) {
    console.warn("Failed to load favourite status:", e);
  }
}

/**
 * Attach click handlers to all favourite buttons.
 */
function attachFavouriteHandlers() {
  document.querySelectorAll(".favourite-btn").forEach((btn) => {
    if (btn.dataset.favouriteHandlerAttached) return;
    btn.dataset.favouriteHandlerAttached = "true";

    btn.addEventListener("click", handleFavouriteClick);
  });
}

/**
 * Handle click on favourite button.
 * Always shows wishlists dropdown when multiple lists exist so the user can
 * pick which list to add to / remove from.  For single-list users it
 * toggles the default list immediately.
 */
async function handleFavouriteClick(e) {
  e.preventDefault();
  e.stopPropagation();

  const btn = e.currentTarget;
  const productId = btn.dataset.productId;
  if (!productId) return;

  // Skip if a page-specific handler is managing this button (e.g., FavouritesPage)
  if (btn.dataset.favouritePageManaged === "true") return;

  // If picker is already open for this button, close it
  const existingPicker = document.getElementById("wishlist-picker-dropdown");
  if (existingPicker && existingPicker._sourceBtn === btn) {
    closeWishlistPicker();
    return;
  }

  // Prevent double-clicks while loading
  if (btn.classList.contains("btn-loading")) return;

  // Heart click animation
  btn.classList.add("favourite-btn-pulse");
  setTimeout(() => btn.classList.remove("favourite-btn-pulse"), 500);

  try {
    // Fetch wishlists with containment info for this product
    const res = await fetch(
      `/favourites/api/wishlists/?product_id=${productId}`,
      { credentials: "same-origin" },
    );
    const data = await res.json();
    const wishlists = data.wishlists || [];

    // Single list: quick toggle without showing picker
    if (wishlists.length === 1) {
      const wl = wishlists[0];
      if (wl.contains_product) {
        // Already in the only list → remove and toggle heart off
        await removeFromSpecificWishlist(productId, wl.id, btn);
        return;
      }
      // Not in the list yet → add, then show picker
      try {
        const csrfToken = getCsrfToken();
        const addRes = await fetch("/favourites/add/", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": csrfToken,
          },
          body: `product_id=${productId}&wishlist_id=${wl.id}`,
          credentials: "same-origin",
        });
        if (addRes.ok) {
          const addData = await addRes.json();
          wl.contains_product = true;
          setFavouriteState(btn, true);
          updateAllFavouriteButtons(productId, true);
          if (addData.message) showToast(addData.message, "success");
        }
      } catch (_) {
        /* show picker anyway */
      }
      showWishlistPicker(btn, productId, wishlists);
      return;
    }

    // Multiple lists → show picker so user can manage which lists
    if (wishlists.length > 1) {
      showWishlistPicker(btn, productId, wishlists);
      return;
    }

    // No lists yet → add to default list (creates it), then show picker
    const isFavourited =
      btn
        .querySelector(".favourite-icon-filled")
        ?.classList.contains("hidden") === false;

    if (isFavourited) {
      await removeFromSpecificWishlist(productId, null, btn);
    } else {
      await addToFavourites(productId, btn);
      // Re-fetch wishlists so the picker shows the newly created default list
      try {
        const res2 = await fetch(
          `/favourites/api/wishlists/?product_id=${productId}`,
          { credentials: "same-origin" },
        );
        const data2 = await res2.json();
        const newWishlists = data2.wishlists || [];
        if (newWishlists.length >= 1) {
          showWishlistPicker(btn, productId, newWishlists);
        }
      } catch (_) {
        /* picker is a nice-to-have; toast already shown */
      }
    }
  } catch (_) {
    // Fetch failed → fall back to simple toggle
    const isFavourited =
      btn
        .querySelector(".favourite-icon-filled")
        ?.classList.contains("hidden") === false;
    if (isFavourited) {
      await removeFromSpecificWishlist(productId, null, btn);
    } else {
      await addToFavourites(productId, btn);
    }
  }
}

/* ---- SVG icon constants for the picker ---- */
const CHECKBOX_CHECKED_SVG =
  '<svg class="w-5 h-5 text-primary-600 shrink-0" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="4" fill="currentColor"/><path d="M9 12l2 2 4-4" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const CHECKBOX_UNCHECKED_SVG =
  '<svg class="w-5 h-5 text-gray-500 dark:text-gray-400 shrink-0" viewBox="0 0 24 24" fill="none"><rect x="3.5" y="3.5" width="17" height="17" rx="3.5" stroke="currentColor" stroke-width="1.5"/></svg>';

/**
 * Show a floating dropdown near the favourite button with per-list
 * add / remove options.  Lists that already contain the product display a
 * checkbox and clicking them will remove the product from that list.
 */
function showWishlistPicker(btn, productId, wishlists) {
  // Close any existing picker
  closeWishlistPicker();

  const picker = document.createElement("div");
  picker.id = "wishlist-picker-dropdown";
  picker._sourceBtn = btn; // track source button
  picker.className =
    "fixed z-[100] w-72 bg-white dark:bg-gray-800 rounded-2xl shadow-[0_4px_8px_0_rgba(0,0,0,0.16),0_0_2px_1px_rgba(0,0,0,0.08)] dark:shadow-[0_4px_10px_-2px_rgb(0_0_0/0.5)] border border-gray-100 dark:border-gray-700 overflow-hidden opacity-0 scale-95 pointer-events-none transition-all duration-150 ease-out";

  const isLoggedIn = document.body.dataset.authenticated === "true";

  const list = wishlists
    .map((wl) => {
      const inList = !!wl.contains_product;
      const checkboxSvg = inList
        ? '<svg class="w-5 h-5 text-primary-600 shrink-0" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="4" fill="currentColor"/><path d="M9 12l2 2 4-4" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        : '<svg class="w-5 h-5 text-gray-400 dark:text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none"><rect x="3.5" y="3.5" width="17" height="17" rx="3.5" stroke="currentColor" stroke-width="1.5"/></svg>';

      return `
    <button type="button"
      class="wishlist-pick-option w-full flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors cursor-pointer text-left
        ${inList ? "text-gray-900 dark:text-white" : "text-gray-700 dark:text-gray-300"} hover:bg-gray-200 dark:hover:bg-gray-700"
      data-wishlist-id="${wl.id}"
      data-wishlist-name="${wl.name}"
      data-contains-product="${inList}"
      data-is-default="${wl.is_default}">
      ${checkboxSvg}
      <span class="truncate">${wl.name}</span>
    </button>`;
    })
    .join("");

  const loginHintHtml = !isLoggedIn
    ? `<p class="text-subtitle mt-1.5 leading-relaxed">Sign in to keep your lists saved and access them from any device.</p>`
    : "";

  picker.innerHTML = `<div>
    <div class="px-5 py-4">
      <div class="flex items-center justify-between">
        <h3 class="text-base font-bold text-gray-900 dark:text-white leading-none">Save to list</h3>
        <button type="button" class="wishlist-picker-close p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer" aria-label="Close">
          <svg class="w-4 h-4 text-gray-500 dark:text-gray-400" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      ${loginHintHtml}
    </div>
    <div class="border-t border-gray-100 dark:border-gray-700">
      <button type="button" id="wishlist-picker-create-btn" class="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer border-b border-gray-100 dark:border-gray-700">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/></svg>
        Add new list
      </button>
    </div>
    <div id="wishlist-picker-create-form" class="hidden px-4 py-3 border-b border-gray-100 dark:border-gray-700 bg-gray-100 dark:bg-gray-700/30">
      <div class="flex gap-2">
        <input type="text" id="wishlist-picker-new-name" class="flex-1 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-0 focus:border-gray-300 dark:focus:border-gray-500 focus:shadow-[0_4px_8px_0_rgba(0,0,0,0.08)]" placeholder="List name..." maxlength="64" />
        <button type="button" id="wishlist-picker-create-submit" class="px-3 py-2 text-sm font-semibold text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors cursor-pointer">Save</button>
      </div>
      <div id="wishlist-picker-create-error" class="hidden text-xs text-red-500 mt-1.5"></div>
    </div>
    <div class="py-1">
      ${list}
    </div>
    <div class="px-4 pb-4 pt-2">
      <button type="button" class="wishlist-picker-done w-full py-2.5 text-sm font-semibold text-white bg-primary-600 rounded-xl hover:bg-primary-700 transition-colors cursor-pointer">Done</button>
    </div>
  </div>`;
  document.body.appendChild(picker);

  // Close button handler
  picker
    .querySelector(".wishlist-picker-close")
    ?.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      closeWishlistPicker();
    });

  // Done button handler
  picker
    .querySelector(".wishlist-picker-done")
    ?.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      closeWishlistPicker();
    });

  // Create new list - toggle form
  const createBtn = picker.querySelector("#wishlist-picker-create-btn");
  const createForm = picker.querySelector("#wishlist-picker-create-form");
  const createInput = picker.querySelector("#wishlist-picker-new-name");
  const createSubmit = picker.querySelector("#wishlist-picker-create-submit");
  const createError = picker.querySelector("#wishlist-picker-create-error");

  createBtn?.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    createBtn.classList.add("hidden");
    createForm.classList.remove("hidden");
    createInput?.focus();
  });

  // Submit new list
  const handleCreateSubmit = async (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const name = createInput.value.trim();
    if (!name) {
      createError.textContent = "Please enter a name.";
      createError.classList.remove("hidden");
      return;
    }
    if (createSubmit.classList.contains("btn-loading")) return;
    window.btnLoading(createSubmit);
    createError.classList.add("hidden");

    try {
      const csrfToken = getCsrfToken();
      const res = await fetch("/favourites/create/", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-CSRFToken": csrfToken,
          "HX-Request": "true",
        },
        body: `name=${encodeURIComponent(name)}&product_ids=${productId}`,
        credentials: "same-origin",
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        createError.textContent = data.message || "Failed to create list.";
        createError.classList.remove("hidden");
        return;
      }
      // Success - add new list item to picker
      const newWl = data.wishlist;
      wishlists.push({
        id: newWl.id,
        name: newWl.name,
        is_default: newWl.is_default,
        item_count: 1,
        contains_product: true,
      });
      const listContainer = picker.querySelector(".py-1");
      const newBtn = document.createElement("button");
      newBtn.type = "button";
      newBtn.className =
        "wishlist-pick-option w-full flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors cursor-pointer text-left text-gray-900 dark:text-white hover:bg-gray-200 dark:hover:bg-gray-700";
      newBtn.dataset.wishlistId = String(newWl.id);
      newBtn.dataset.wishlistName = newWl.name;
      newBtn.dataset.containsProduct = "true";
      newBtn.dataset.isDefault = String(newWl.is_default);
      newBtn.innerHTML = `<svg class="w-5 h-5 text-primary-600 shrink-0" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="4" fill="currentColor"/><path d="M9 12l2 2 4-4" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg><span class="truncate">${newWl.name}</span>`;
      listContainer.appendChild(newBtn);
      attachOptionHandler(newBtn, productId, btn, wishlists, picker);
      // Reset form
      createInput.value = "";
      createForm.classList.add("hidden");
      createBtn.classList.remove("hidden");
      // Update heart state
      setFavouriteState(btn, true);
      updateAllFavouriteButtons(productId, true);
      showToast(data.message || `Created "${newWl.name}"`, "success");
    } catch (_e) {
      createError.textContent = "Something went wrong.";
      createError.classList.remove("hidden");
    } finally {
      window.btnReset(createSubmit);
    }
  };

  createSubmit?.addEventListener("click", handleCreateSubmit);
  createInput?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") handleCreateSubmit(ev);
    if (ev.key === "Escape") {
      createForm.classList.add("hidden");
      createBtn.classList.remove("hidden");
    }
  });

  // Position relative to the button
  const btnRect = btn.getBoundingClientRect();
  const pickerWidth = 288; // w-72 = 18rem = 288px
  let left = btnRect.right - pickerWidth;
  let top = btnRect.bottom + 6;

  // Keep within viewport
  if (left < 8) left = 8;
  if (top + 350 > window.innerHeight) {
    top = btnRect.top - 6;
    picker.style.left = `${left}px`;
    picker.style.bottom = `${window.innerHeight - top}px`;
    picker.style.top = "auto";
  } else {
    picker.style.left = `${left}px`;
    picker.style.top = `${top}px`;
  }

  // Animate in
  requestAnimationFrame(() => {
    picker.classList.remove("opacity-0", "scale-95", "pointer-events-none");
    picker.classList.add("opacity-100", "scale-100");
  });

  // Handle option clicks – add or remove depending on current state
  picker.querySelectorAll(".wishlist-pick-option").forEach((optBtn) => {
    attachOptionHandler(optBtn, productId, btn, wishlists, picker);
  });

  // Close on outside click (delayed to skip the current event)
  setTimeout(() => {
    document.addEventListener("click", _closePickerOnOutsideClick);
    document.addEventListener("scroll", closeWishlistPicker, { once: true });
  }, 0);
}

function attachOptionHandler(optBtn, productId, btn, wishlists, picker) {
  optBtn.addEventListener("click", async (ev) => {
    ev.preventDefault();
    ev.stopPropagation();

    if (optBtn.classList.contains("btn-loading")) return;

    const wishlistId = optBtn.dataset.wishlistId;
    const wishlistName = optBtn.dataset.wishlistName;
    const isInList = optBtn.dataset.containsProduct === "true";

    // Show spinner on the checkbox
    const checkboxEl = optBtn.querySelector("svg:first-child");
    const originalCheckbox = checkboxEl ? checkboxEl.outerHTML : "";
    if (checkboxEl) {
      const tempDiv = document.createElement("div");
      tempDiv.innerHTML =
        '<svg class="w-5 h-5 animate-spin text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
      checkboxEl.replaceWith(tempDiv.firstChild);
    }
    optBtn.classList.add("btn-loading");

    try {
      if (isInList) {
        await removeFromSpecificWishlist(productId, wishlistId, btn);
        optBtn.dataset.containsProduct = "false";
        optBtn.classList.remove("text-gray-900", "dark:text-white");
        optBtn.classList.add("text-gray-700", "dark:text-gray-300");
        // Update checkbox to unchecked
        const currentSvg = optBtn.querySelector("svg:first-child");
        if (currentSvg) {
          const tempDiv = document.createElement("div");
          tempDiv.innerHTML = CHECKBOX_UNCHECKED_SVG;
          currentSvg.replaceWith(tempDiv.firstChild);
        }
      } else {
        await addToWishlist(productId, wishlistId, wishlistName, btn);
        optBtn.dataset.containsProduct = "true";
        optBtn.classList.remove("text-gray-700", "dark:text-gray-300");
        optBtn.classList.add("text-gray-900", "dark:text-white");
        // Update checkbox to checked
        const currentSvg = optBtn.querySelector("svg:first-child");
        if (currentSvg) {
          const tempDiv = document.createElement("div");
          tempDiv.innerHTML = CHECKBOX_CHECKED_SVG;
          currentSvg.replaceWith(tempDiv.firstChild);
        }
      }
    } catch (_err) {
      // Restore original checkbox on error
      const currentSvg = optBtn.querySelector("svg:first-child");
      if (currentSvg) {
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = originalCheckbox;
        currentSvg.replaceWith(tempDiv.firstChild);
      }
    } finally {
      optBtn.classList.remove("btn-loading");
    }

    // After toggling, update heart icon: filled if product is in ANY list
    const anyInList = picker.querySelector(
      '.wishlist-pick-option[data-contains-product="true"]',
    );
    const isInAny = !!anyInList;
    setFavouriteState(btn, isInAny);
    updateAllFavouriteButtons(productId, isInAny);
  });
}

function _closePickerOnOutsideClick(e) {
  const picker = document.getElementById("wishlist-picker-dropdown");
  if (
    picker &&
    !picker.contains(e.target) &&
    !e.target.closest(".favourite-btn")
  ) {
    closeWishlistPicker();
  }
}

function closeWishlistPicker() {
  const picker = document.getElementById("wishlist-picker-dropdown");
  if (picker) {
    picker.classList.add("opacity-0", "scale-95", "pointer-events-none");
    picker.classList.remove("opacity-100", "scale-100");
    setTimeout(() => picker.remove(), 150);
  }
  document.removeEventListener("click", _closePickerOnOutsideClick);
  document.removeEventListener("scroll", closeWishlistPicker);
}

/**
 * Add product to a specific wishlist by ID.
 */
async function addToWishlist(productId, wishlistId, wishlistName, btn) {
  const csrfToken = getCsrfToken();
  const response = await fetch("/favourites/add/", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrfToken,
    },
    body: `product_id=${productId}&wishlist_id=${wishlistId}`,
    credentials: "same-origin",
  });

  const data = await response.json();

  if (!response.ok || !data.success) {
    if (data.already_in_list) {
      showToast(data.message || "Product is already in this list.", "error");
    } else {
      showToast(data.message || "Failed to add to list", "error");
      throw new Error("add failed");
    }
  } else {
    setFavouriteState(btn, true);
    updateAllFavouriteButtons(productId, true);
    showToast(data.message || `Added to ${wishlistName}`, "success");
  }
}

/**
 * Add product to default wishlist (single-list shortcut).
 */
async function addToFavourites(productId, btn) {
  setFavouriteState(btn, true);

  try {
    const csrfToken = getCsrfToken();
    const response = await fetch("/favourites/toggle/", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrfToken,
      },
      body: `product_id=${productId}`,
      credentials: "same-origin",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      setFavouriteState(btn, false);
      showToast(data.message || "Failed to add to favourites", "error");
    } else {
      updateAllFavouriteButtons(productId, data.action === "added");
      showToast(data.message || "Added to favourites", "success");

      if (isOnFavouritesPage() && data.wishlist_id) {
        updateFavouritesSidebarCount(
          data.wishlist_id,
          data.wishlist_item_count,
        );
        updateFavouritesHeaderStats(
          data.wishlist_item_count,
          data.wishlist_total_value,
        );
        updateFavouritesItemsCount(data.wishlist_item_count);
      }
    }
  } catch (e) {
    setFavouriteState(btn, false);
    showToast("Failed to add to favourites", "error");
  }
}

/**
 * Remove product from a specific wishlist, or from the default list
 * when wishlistId is null.
 */
async function removeFromSpecificWishlist(productId, wishlistId, btn) {
  try {
    const csrfToken = getCsrfToken();
    let url, body;

    if (wishlistId) {
      // Remove from specific list
      url = "/favourites/remove/";
      body = `product_id=${productId}&wishlist_id=${wishlistId}`;
    } else {
      // Toggle off default list
      url = "/favourites/toggle/";
      body = `product_id=${productId}`;
    }

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrfToken,
      },
      body,
      credentials: "same-origin",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error" || data.success === false) {
      showToast(data.message || "Failed to remove from list", "error");
      throw new Error("remove failed");
    }

    showToast(data.message || "Removed from list", "success");

    // After removing, check if product is still in any list
    // If picker is open, it will update via the caller.
    // For single-list mode, just unfill the heart.
    if (!wishlistId) {
      setFavouriteState(btn, false);
      updateAllFavouriteButtons(productId, false);
    } else if (btn) {
      // Specific list removal — check if product is still in any other list
      try {
        const statusRes = await fetch(
          `/favourites/api/status/?product_ids=${productId}`,
          { cache: "no-store", credentials: "same-origin" },
        );
        const statusData = await statusRes.json();
        const stillInLists = (statusData.status || {})[productId];
        if (!stillInLists || stillInLists.length === 0) {
          setFavouriteState(btn, false);
          updateAllFavouriteButtons(productId, false);
        }
      } catch (_) {
        // Assume removed if we can't verify
        setFavouriteState(btn, false);
        updateAllFavouriteButtons(productId, false);
      }
    }

    // Update favourites page UI if applicable
    if (isOnFavouritesPage()) {
      if (data.wishlist_id) {
        updateFavouritesSidebarCount(
          data.wishlist_id,
          data.wishlist_item_count,
        );
        updateFavouritesHeaderStats(
          data.wishlist_item_count,
          data.wishlist_total_value,
        );
        updateFavouritesItemsCount(data.wishlist_item_count);
      }
      removeProductCardFromFavouritesPage(productId, data);
    }
  } catch (e) {
    if (e.message !== "remove failed") {
      showToast("Failed to remove from list", "error");
    }
    throw e;
  }
}

/**
 * Set the visual state of a favourite button.
 */
function setFavouriteState(btn, isFavourited) {
  const outlineIcon = btn.querySelector(".favourite-icon");
  const filledIcon = btn.querySelector(".favourite-icon-filled");

  if (isFavourited) {
    outlineIcon?.classList.add("hidden");
    filledIcon?.classList.remove("hidden");
    btn.classList.add("is-favourited");
  } else {
    outlineIcon?.classList.remove("hidden");
    filledIcon?.classList.add("hidden");
    btn.classList.remove("is-favourited");
  }
}

/**
 * Update all favourite buttons for a specific product.
 */
function updateAllFavouriteButtons(productId, isFavourited) {
  document
    .querySelectorAll(`.favourite-btn[data-product-id="${productId}"]`)
    .forEach((btn) => {
      setFavouriteState(btn, isFavourited);
    });
}

/**
 * Show a toast notification.
 * @param {string} message - The message to display
 * @param {string} type - The type of toast: 'success', 'warning' or 'error'
 */
function showToast(message, type = "success") {
  // Check if there's an existing toast container
  let toastContainer = document.getElementById("favourite-toast-container");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "favourite-toast-container";
    toastContainer.className = "fixed right-4 z-50 flex flex-col gap-2";
    document.body.appendChild(toastContainer);
  }
  toastContainer.classList.add("bottom-4");

  const toastId = `toast-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const normalizedType =
    type === "success" || type === "warning" || type === "error"
      ? type
      : "success";

  const isSuccess = normalizedType === "success";
  const isWarning = normalizedType === "warning";
  const toast = document.createElement("div");
  const iconWrapperClass = isSuccess
    ? "inline-flex items-center justify-center shrink-0 w-8 h-8 text-green-500 bg-green-100 rounded-lg dark:bg-green-800 dark:text-green-200"
    : isWarning
      ? "inline-flex items-center justify-center shrink-0 w-8 h-8 text-orange-500 bg-orange-100 rounded-lg dark:bg-orange-800 dark:text-orange-200"
      : "inline-flex items-center justify-center shrink-0 w-8 h-8 text-red-500 bg-red-100 rounded-lg dark:bg-red-800 dark:text-red-200";
  const iconPath = isSuccess
    ? "M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5Zm3.707 8.207-4 4a1 1 0 0 1-1.414 0l-2-2a1 1 0 0 1 1.414-1.414L9 10.586l3.293-3.293a1 1 0 0 1 1.414 1.414Z"
    : isWarning
      ? "M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5Zm0 12a1 1 0 1 1 0-2 1 1 0 0 1 0 2Zm1-9a1 1 0 0 0-2 0v5a1 1 0 0 0 2 0v-5Z"
      : "M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5Zm3.707 11.793a1 1 0 1 1-1.414 1.414L10 11.414l-2.293 2.293a1 1 0 0 1-1.414-1.414L8.586 10 6.293 7.707a1 1 0 0 1 1.414-1.414L10 8.586l2.293-2.293a1 1 0 0 1 1.414 1.414L11.414 10l2.293 2.293Z";

  toast.id = toastId;
  toast.setAttribute("role", "alert");
  toast.className =
    "relative overflow-visible flex items-center w-full max-w-xs p-4 pr-10 mb-4 text-gray-900 bg-white rounded-lg shadow-lg dark:text-white dark:bg-gray-800 transform transition-all duration-300 ease-out opacity-0 translate-y-4";
  toast.innerHTML = `
    <div class="${iconWrapperClass}">
      <svg class="w-5 h-5" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 20 20">
        <path d="${iconPath}" />
      </svg>
      <span class="sr-only">${isSuccess ? "Check icon" : isWarning ? "Warning icon" : "Error icon"}</span>
    </div>
    <div class="ms-3 text-sm font-medium">${message}</div>
  `;

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "Close");
  closeBtn.className =
    "absolute -right-3 -top-3 inline-flex h-8 w-8 items-center justify-center rounded-full bg-white text-gray-900 shadow-md hover-bg btn-press border border-gray-100 dark:bg-gray-800 dark:text-white dark:border-gray-700 cursor-pointer";
  closeBtn.innerHTML =
    '<svg class="h-4 w-4" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18 18 6M6 6l12 12"/></svg>';
  closeBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    removeToast();
  });
  toast.appendChild(closeBtn);

  toastContainer.appendChild(toast);

  // Trigger animation after the element is added to the DOM and the browser has a chance to layout
  setTimeout(() => {
    toast.classList.remove("opacity-0", "translate-y-4");
    toast.classList.add("opacity-100", "translate-y-0");
  }, 20);

  // Function to remove toast with animation
  const removeToast = () => {
    toast.classList.remove("opacity-100", "translate-y-0");
    toast.classList.add("opacity-0", "translate-y-4");
    setTimeout(() => {
      toast.remove();
    }, 300);
  };

  // Click anywhere on the toast to dismiss it
  toast.addEventListener("click", () => {
    removeToast();
  });
  toast.style.cursor = "pointer";

  // Auto-dismiss after 5 seconds
  setTimeout(removeToast, 5000);
}

// Make showToast available globally for use in templates
window.showToast = showToast;

/**
 * Get CSRF token from cookie.
 */
function getCsrfToken() {
  const name = "csrftoken";
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Re-initialize favourites after HTMX swaps
document.addEventListener("htmx:afterSwap", () => {
  attachFavouriteHandlers();
  loadFavouriteStatus();
  syncCompareButtons(document);
  initRelativeTimes();
});

// Sync heart state when navigating back/forward via browser history (bfcache)
// Always reload status on pageshow — on bfcache restore the DOM is stale,
// and on fresh loads this is a harmless second call that ensures correctness.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    loadFavouriteStatus();
  }
});

/**
 * Format a timestamp as a human-readable relative time string.
 * Returns "Just now" for < 1 minute, then "X minutes ago", "X hours ago", etc.
 */
function formatRelativeTime(timestamp) {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);
  const diffWeek = Math.floor(diffDay / 7);
  const diffMonth = Math.floor(diffDay / 30);

  // Determine the correct language from <html lang="...">
  const lang = document.documentElement.lang || "en";
  const isPl = lang.startsWith("pl");

  if (diffMin < 1) {
    return isPl ? "Zmieniono w\u0142a\u015bnie teraz" : "Modified just now";
  } else if (diffMin === 1) {
    return isPl ? "Zmieniono 1 minut\u0119 temu" : "Modified 1 minute ago";
  } else if (diffMin < 60) {
    return isPl
      ? `Zmieniono ${diffMin} minut temu`
      : `Modified ${diffMin} minutes ago`;
  } else if (diffHr === 1) {
    return isPl ? "Zmieniono 1 godzin\u0119 temu" : "Modified 1 hour ago";
  } else if (diffHr < 24) {
    return isPl
      ? `Zmieniono ${diffHr} godzin temu`
      : `Modified ${diffHr} hours ago`;
  } else if (diffDay === 1) {
    return isPl ? "Zmieniono 1 dzie\u0144 temu" : "Modified 1 day ago";
  } else if (diffDay < 7) {
    return isPl
      ? `Zmieniono ${diffDay} dni temu`
      : `Modified ${diffDay} days ago`;
  } else if (diffWeek === 1) {
    return isPl ? "Zmieniono 1 tydzie\u0144 temu" : "Modified 1 week ago";
  } else if (diffDay < 30) {
    return isPl
      ? `Zmieniono ${diffWeek} tygodni temu`
      : `Modified ${diffWeek} weeks ago`;
  } else if (diffMonth === 1) {
    return isPl ? "Zmieniono 1 miesi\u0105c temu" : "Modified 1 month ago";
  } else {
    return isPl
      ? `Zmieniono ${diffMonth} miesi\u0119cy temu`
      : `Modified ${diffMonth} months ago`;
  }
}

/**
 * Initialize all .relative-time elements and start auto-refresh interval.
 */
let _relativeTimeInterval = null;
function initRelativeTimes() {
  updateRelativeTimes();
  if (!_relativeTimeInterval) {
    _relativeTimeInterval = setInterval(updateRelativeTimes, 30000); // every 30s
  }
}

function updateRelativeTimes() {
  document.querySelectorAll(".relative-time[data-timestamp]").forEach((el) => {
    el.textContent = formatRelativeTime(el.dataset.timestamp);
  });
}
window.initRelativeTimes = initRelativeTimes;

/**
 * Check if currently on favourites page.
 */
function isOnFavouritesPage() {
  return window.location.pathname.startsWith("/favourites");
}

/**
 * Remove a product card from the favourites page and update stats.
 */
function removeProductCardFromFavouritesPage(productId, data) {
  // Find all product cards with this product ID
  const productCards = document.querySelectorAll(
    `[data-product-card="${productId}"]`,
  );

  productCards.forEach((card) => {
    // Animate and remove
    card.style.transition = "all 0.3s ease";
    card.style.transform = "scale(0.95)";
    card.style.opacity = "0";
    setTimeout(() => {
      card.remove();
      checkIfFavouritesListEmpty();
    }, 300);
  });

  // Update sidebar item count
  if (data.wishlist_id) {
    updateFavouritesSidebarCount(data.wishlist_id, data.wishlist_item_count);
  }

  // Update header stats
  updateFavouritesHeaderStats(
    data.wishlist_item_count,
    data.wishlist_total_value,
  );

  // Update the items count display in the content area
  updateFavouritesItemsCount(data.wishlist_item_count);
}

/**
 * Update the item count in the sidebar for a specific wishlist.
 */
function updateFavouritesSidebarCount(wishlistId, newCount) {
  const sidebarItem = document.querySelector(
    `.wishlist-nav-item[data-wishlist-id="${wishlistId}"]`,
  );
  if (!sidebarItem) return;

  const countSpan = sidebarItem.querySelector(".text-xs");
  if (countSpan) {
    const itemsText =
      newCount === 1
        ? window.FAVOURITES_ITEM_TEXT || "item"
        : window.FAVOURITES_ITEMS_TEXT || "items";
    countSpan.textContent = `${newCount} ${itemsText}`;
  }
}

/**
 * Update header stats (product count and total value).
 */
function updateFavouritesHeaderStats(itemCount, totalValue) {
  // Find the header subtitle that shows "X products · Y total"
  const headerDiv = document.querySelector("#wishlist-content .text-subtitle");
  if (!headerDiv) return;

  // Get currency from existing price display or default to USD
  const priceElement = headerDiv.querySelector("[data-price]");
  const currency = priceElement?.dataset.currency || "USD";

  // Format the total value
  const locale = CURRENCY_LOCALES[currency] || "en-US";
  let formattedTotal;
  try {
    formattedTotal = new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(totalValue);
  } catch (e) {
    formattedTotal = `${totalValue.toFixed(2)} ${currency}`;
  }

  const productsText =
    itemCount === 1
      ? window.FAVOURITES_PRODUCT_TEXT || "product"
      : window.FAVOURITES_PRODUCTS_TEXT || "products";
  const totalText = window.FAVOURITES_TOTAL_TEXT || "total";

  headerDiv.innerHTML = `${itemCount} ${productsText} · <span data-price="${totalValue}" data-currency="${currency}">${formattedTotal}</span> ${totalText}`;
}

/**
 * Update the items count display in the content view controls.
 */
function updateFavouritesItemsCount(count) {
  // Find the items count span in the view controls
  const countSpan = document.querySelector(
    "#wishlist-items-container .text-sm.text-gray-500",
  );
  if (!countSpan) return;

  const itemsText =
    count === 1
      ? window.FAVOURITES_ITEM_TEXT || "item"
      : window.FAVOURITES_ITEMS_TEXT || "items";
  countSpan.textContent = `${count} ${itemsText}`;
}

function renderWishlistEmptyState() {
  const container = document.getElementById("wishlist-items-container");
  const template = document.getElementById("wishlist-empty-state-template");
  if (!container || !template) return false;

  if (template.content) {
    container.replaceChildren(template.content.cloneNode(true));
  } else {
    container.innerHTML = template.innerHTML;
  }

  return true;
}

window.renderWishlistEmptyState = renderWishlistEmptyState;

/**
 * Check if the favourites list is empty and show empty state if so.
 */
function checkIfFavouritesListEmpty() {
  const container = document.getElementById("wishlist-items-container");
  if (!container) return;

  const listView = container.querySelector(".view-list");
  const gridView = container.querySelector(".view-grid");

  const listItems = listView?.children.length || 0;
  const gridItems = gridView?.children.length || 0;

  // If both views are empty, render the empty state
  if (listItems === 0 && gridItems === 0) {
    renderWishlistEmptyState();
  }
}

// ─── Email Verification Banner ────────────────────────────────────
function initEmailVerificationBanner() {
  const banner = document.getElementById("email-verification-banner");
  if (!banner) return;

  // Use a user-specific dismiss key so dismissing as user A
  // doesn't hide the banner for a newly-registered user B.
  const userId = banner.dataset.userId || "";
  const dismissKey = `email_verified_dismiss_${userId}`;

  // Clean up legacy non-user-specific key
  sessionStorage.removeItem("email_verified_dismiss");

  // If already dismissed this browser session, hide immediately
  if (sessionStorage.getItem(dismissKey) === "1") {
    banner.style.display = "none";
    return;
  }

  // Dismiss button – hide banner for this browser session
  const dismissBtn = document.getElementById("dismiss-verification-banner");
  if (dismissBtn) {
    dismissBtn.addEventListener("click", () => {
      banner.style.transition = "opacity .2s ease, max-height .3s ease";
      banner.style.opacity = "0";
      banner.style.maxHeight = "0";
      banner.style.overflow = "hidden";
      sessionStorage.setItem(dismissKey, "1");
      setTimeout(() => banner.remove(), 300);
    });
  }

  // Resend button – POST to resend endpoint
  const resendBtn = document.getElementById("resend-verification-btn");
  if (resendBtn) {
    resendBtn.addEventListener("click", async () => {
      if (resendBtn.classList.contains("btn-loading")) return;
      window.btnLoading(resendBtn);
      try {
        const csrfToken = getCsrfToken();
        const res = await fetch("/users/resend-verification-email/", {
          method: "POST",
          headers: {
            "X-CSRFToken": csrfToken || "",
            "Content-Type": "application/json",
          },
          credentials: "same-origin",
        });
        if (res.ok) {
          window.showToast?.("Verification email sent!", "success");
        } else {
          window.showToast?.("Could not send email. Try again later.", "error");
        }
      } catch {
        window.showToast?.("Could not send email. Try again later.", "error");
      } finally {
        window.btnReset(resendBtn);
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", initEmailVerificationBanner);
