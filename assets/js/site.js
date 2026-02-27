const TAB_PARAM = "__tab";
const TAB_HEADER = "X-Tab-ID";

// Global compatibility shim:
// If code registers DOMContentLoaded after the document is already ready
// (e.g., scripts executed after HTMX soft-nav swap), run it automatically.
(function installDomContentLoadedShim() {
  if (document.__amperDomContentLoadedShimInstalled) return;
  document.__amperDomContentLoadedShimInstalled = true;

  const originalAddEventListener = document.addEventListener.bind(document);

  function invokeDomReadyListener(listener) {
    const event = new Event("DOMContentLoaded");
    if (typeof listener === "function") {
      listener.call(document, event);
      return;
    }
    if (listener && typeof listener.handleEvent === "function") {
      listener.handleEvent(event);
    }
  }

  document.addEventListener = function (type, listener, options) {
    if (type === "DOMContentLoaded" && document.readyState !== "loading") {
      queueMicrotask(() => {
        try {
          invokeDomReadyListener(listener);
        } catch (error) {
          setTimeout(() => {
            throw error;
          }, 0);
        }
      });
      return;
    }
    return originalAddEventListener(type, listener, options);
  };
})();

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

/**
 * Soft navigation: converts all qualifying internal <a> links to HTMX partial
 * page swaps (same pattern as cart-stepper links). The nav persists; only
 * #page-content is replaced. Called on DOMContentLoaded and after each
 * htmx:afterSwap to pick up freshly-injected links.
 */
function initSoftNavigation() {
  if (typeof htmx === "undefined") return;

  function processLinks(root) {
    root.querySelectorAll("a[href]").forEach(function (link) {
      if (link.dataset.softNavInit) return;
      link.dataset.softNavInit = "1";

      // Skip links that already carry explicit HTMX verbs
      if (
        link.hasAttribute("hx-get") ||
        link.hasAttribute("hx-post") ||
        link.hasAttribute("hx-put") ||
        link.hasAttribute("hx-patch") ||
        link.hasAttribute("hx-delete")
      )
        return;

      // Skip opted-out links or containers
      if (
        link.dataset.softNav === "false" ||
        link.closest("[data-soft-nav='false']")
      )
        return;

      // Skip new-tab, download
      if (link.target === "_blank") return;
      if (link.hasAttribute("download")) return;

      // Must resolve to a valid http/https URL
      var href = link.href;
      if (!href) return;
      var url;
      try {
        url = new URL(href);
      } catch (e) {
        return;
      }

      // Same origin only
      if (url.origin !== window.location.origin) return;

      // Skip admin, API, media paths
      var path = url.pathname;
      if (
        path.startsWith("/admin") ||
        path.startsWith("/api/") ||
        path.startsWith("/media/")
      )
        return;

      // Skip non-http protocols (mailto, tel, …)
      if (!url.protocol.startsWith("http")) return;

      // Skip pure hash anchors on the same page
      if (
        path === window.location.pathname &&
        url.search === window.location.search &&
        url.hash
      )
        return;

      // Only soft-nav if #page-content-wrapper exists
      if (!document.getElementById("page-content-wrapper")) return;

      // Target the stable outer wrapper; select only #page-content from the
      // response and inject it as innerHTML of the wrapper.  This keeps the
      // wrapper div permanently in the DOM (avoiding the HTMX 2.x bug where
      // outerHTML-swapping an element from outside that element removes it).
      link.setAttribute("hx-get", href);
      link.setAttribute("hx-target", "#page-content-wrapper");
      link.setAttribute("hx-select", "#page-content");
      link.setAttribute("hx-swap", "innerHTML");
      link.setAttribute("hx-push-url", "true");
      // Tell the server this is a full-page soft-nav request (not a partial
      // filter/pagination update) so it returns the complete page HTML.
      link.setAttribute("hx-headers", '{"HX-Soft-Nav": "true"}');
      htmx.process(link);
    });
  }

  processLinks(document);

  // Re-process links that arrive inside HTMX-swapped content
  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.target) processLinks(event.target);
  });
}

window.initSoftNavigation = initSoftNavigation;

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
  initHeroBannerSlider();

  // Set up soft navigation (partial page swaps that keep the nav intact)
  initSoftNavigation();

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
  overlay.className = "fixed inset-0 z-[90] hidden items-center justify-center";
  overlay.style.cssText = "background: rgba(25,25,25,0.96); padding: 1.5rem;";
  overlay.innerHTML = `
    <div data-fullscreen-content style="position:relative;width:100%;max-width:72rem;margin:0 auto;">
      <button
        type="button"
        data-fullscreen-close
        aria-label="Close"
        title="Close"
        style="position:absolute;top:-1.25rem;right:-1.25rem;z-index:30;width:2.5rem;height:2.5rem;display:flex;align-items:center;justify-content:center;border-radius:9999px;background:white;box-shadow:0 4px 14px rgba(0,0,0,0.35);cursor:pointer;border:none;color:#1f2937;"
      >
        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>

      <div
        class="product-gallery-swiper swiper"
        data-gallery-main
        style="height:calc(100vh - 8.5rem);background:#111;border-radius:0.75rem;overflow:hidden;"
      >
        <div class="swiper-wrapper" data-fullscreen-slides></div>
        <button
          type="button"
          data-gallery-prev
          aria-label="Previous image"
          style="position:absolute;left:12px;top:50%;transform:translateY(-50%);z-index:10;width:2.25rem;height:2.25rem;display:flex;align-items:center;justify-content:center;border-radius:6px;background:rgba(255,255,255,0.95);box-shadow:0 2px 10px rgba(0,0,0,0.3);border:none;cursor:pointer;color:#1f2937;transition:background 0.15s,box-shadow 0.15s;"
        >
          <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="m15 19-7-7 7-7"/>
          </svg>
        </button>
        <button
          type="button"
          data-gallery-next
          aria-label="Next image"
          style="position:absolute;right:12px;top:50%;transform:translateY(-50%);z-index:10;width:2.25rem;height:2.25rem;display:flex;align-items:center;justify-content:center;border-radius:6px;background:rgba(255,255,255,0.95);box-shadow:0 2px 10px rgba(0,0,0,0.3);border:none;cursor:pointer;color:#1f2937;transition:background 0.15s,box-shadow 0.15s;"
        >
          <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="m9 5 7 7-7 7"/>
          </svg>
        </button>
        <div class="swiper-pagination"></div>
      </div>

      <div
        class="product-gallery-thumbs swiper"
        data-gallery-thumbs
        style="height:72px;margin-top:8px;"
      >
        <div class="swiper-wrapper" data-fullscreen-thumbs></div>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  const close = () => {
    overlay.classList.add("hidden");
    overlay.classList.remove("flex");
    document.body.classList.remove("overflow-hidden");
    if (overlay._thumbsSwiper) {
      try {
        overlay._thumbsSwiper.destroy(true, true);
      } catch (_) {}
      overlay._thumbsSwiper = null;
    }
    if (overlay._swiper) {
      try {
        overlay._swiper.destroy(true, true);
      } catch (_) {}
      overlay._swiper = null;
    }
    const sc = overlay.querySelector("[data-fullscreen-slides]");
    if (sc) sc.innerHTML = "";
    const tc = overlay.querySelector("[data-fullscreen-thumbs]");
    if (tc) tc.innerHTML = "";
  };

  overlay
    .querySelector("[data-fullscreen-close]")
    ?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      close();
    });
  overlay.addEventListener("click", (e) => {
    const mEl = overlay.querySelector("[data-gallery-main]");
    const tEl = overlay.querySelector("[data-gallery-thumbs]");
    if (mEl?.contains(e.target) || tEl?.contains(e.target)) return;
    close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!overlay.classList.contains("hidden")) close();
  });

  overlay._close = close;

  const prevBtnEl = overlay.querySelector("[data-gallery-prev]");
  const nextBtnEl = overlay.querySelector("[data-gallery-next]");
  [prevBtnEl, nextBtnEl].forEach((btn) => {
    if (!btn) return;
    btn.style.transition = "background 0.15s, box-shadow 0.15s, transform 0.1s";
    btn.addEventListener("mouseenter", () => {
      btn.style.background = "rgba(209,213,219,0.95)";
    });
    btn.addEventListener("mouseleave", () => {
      btn.style.background = "rgba(255,255,255,0.95)";
      btn.style.transform = "translateY(-50%)";
    });
    btn.addEventListener("mousedown", () => {
      btn.style.transform = "translateY(-50%) scale(0.9)";
    });
    btn.addEventListener("mouseup", () => {
      btn.style.transform = "translateY(-50%)";
    });
  });

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

    // Collect all product image fullscreen buttons on the page to build the gallery
    const allBtns = Array.from(
      document.querySelectorAll(
        ".product-image-fullscreen-btn[data-fullscreen-src]",
      ),
    );
    const startIndex = Math.max(0, allBtns.indexOf(fsBtn));

    const overlay = ensureProductImageFullscreenOverlay();
    const slidesContainer = overlay.querySelector("[data-fullscreen-slides]");
    const thumbsContainer = overlay.querySelector("[data-fullscreen-thumbs]");

    if (slidesContainer) {
      slidesContainer.innerHTML = allBtns
        .map((btn) => {
          const imgSrc = btn.dataset.fullscreenSrc || "";
          const imgAlt = (btn.dataset.fullscreenAlt || "").replace(
            /"/g,
            "&quot;",
          );
          return `<div class="swiper-slide" style="display:flex;align-items:center;justify-content:center;background:#111;">
  <div class="swiper-zoom-container">
    <img src="${imgSrc}" alt="${imgAlt}" style="max-width:100%;max-height:calc(100vh - 11rem);object-fit:contain;display:block;" />
  </div>
</div>`;
        })
        .join("");
    }

    if (thumbsContainer) {
      thumbsContainer.innerHTML = allBtns
        .map((btn) => {
          const imgSrc = btn.dataset.fullscreenSrc || "";
          const imgAlt = (btn.dataset.fullscreenAlt || "").replace(
            /"/g,
            "&quot;",
          );
          return `<div class="swiper-slide" style="width:64px!important;height:64px;border-radius:6px;overflow:hidden;cursor:pointer;border:2px solid transparent;box-sizing:border-box;opacity:0.5;transition:border-color 0.2s,opacity 0.2s;flex-shrink:0;">
  <img src="${imgSrc}" alt="${imgAlt}" style="width:100%;height:100%;object-fit:cover;" />
</div>`;
        })
        .join("");
    }

    overlay.classList.remove("hidden");
    overlay.classList.add("flex");
    document.body.classList.add("overflow-hidden");

    if (window.Swiper) {
      const mainEl = overlay.querySelector("[data-gallery-main]");
      const thumbsEl = overlay.querySelector("[data-gallery-thumbs]");
      const prevBtn = overlay.querySelector("[data-gallery-prev]");
      const nextBtn = overlay.querySelector("[data-gallery-next]");

      const thumbsSwiper = new Swiper(thumbsEl, {
        slidesPerView: "auto",
        spaceBetween: 8,
        watchSlidesProgress: true,
        freeMode: true,
        centeredSlides: false,
      });
      overlay._thumbsSwiper = thumbsSwiper;

      const mainSwiper = new Swiper(mainEl, {
        initialSlide: startIndex,
        zoom: { maxRatio: 3, minRatio: 1 },
        pagination: {
          el: mainEl.querySelector(".swiper-pagination"),
          type: "fraction",
        },
        thumbs: { swiper: thumbsSwiper },
        keyboard: { enabled: true },
        loop: true,
        watchOverflow: true,
      });
      overlay._swiper = mainSwiper;

      // Style the fraction pagination as a pill at top-right
      const paginationEl = mainEl.querySelector(".swiper-pagination");
      if (paginationEl) {
        paginationEl.style.cssText =
          "position:absolute;top:10px;right:10px;bottom:auto;left:auto;width:auto;background:rgba(0,0,0,0.5);color:white;font-size:0.8rem;font-weight:600;padding:3px 10px;border-radius:9999px;z-index:10;line-height:1.5;text-align:center;";
      }

      // Use onclick to avoid listener accumulation across re-opens
      if (prevBtn) prevBtn.onclick = () => mainSwiper.slidePrev();
      if (nextBtn) nextBtn.onclick = () => mainSwiper.slideNext();

      // Zoom cursor management
      const updateZoomCursor = () => {
        const zoomed = mainSwiper.zoom.scale > 1;
        mainEl.querySelectorAll(".swiper-zoom-container").forEach((zc) => {
          zc.style.cursor = zoomed ? "zoom-out" : "zoom-in";
        });
      };

      // Single click to zoom in/out; distinguish from drag so panning doesn't trigger zoom
      // Compare pointerdown vs pointerup coordinates directly — no mousemove needed,
      // which is important because Swiper intercepts mousemove during pan.
      let _galleryPanStart = null;
      mainEl.addEventListener(
        "pointerdown",
        (e) => {
          if (
            e.button !== 0 ||
            e.target.closest("[data-gallery-prev],[data-gallery-next]")
          )
            return;
          _galleryPanStart = { x: e.clientX, y: e.clientY };
          if (mainSwiper.zoom.scale > 1) {
            mainEl.querySelectorAll(".swiper-zoom-container").forEach((zc) => {
              zc.style.cursor = "grabbing";
            });
          }
        },
        { passive: true },
      );
      mainEl.addEventListener("pointerup", (e) => {
        if (
          !_galleryPanStart ||
          e.target.closest("[data-gallery-prev],[data-gallery-next]")
        )
          return;
        const dx = Math.abs(e.clientX - _galleryPanStart.x);
        const dy = Math.abs(e.clientY - _galleryPanStart.y);
        _galleryPanStart = null;
        updateZoomCursor();
        if (dx > 8 || dy > 8) return; // drag/pan — don't toggle zoom
        if (mainSwiper.zoom.scale > 1) {
          mainSwiper.zoom.out();
        } else {
          mainSwiper.zoom.in();
        }
        updateZoomCursor();
      });
      mainSwiper.on("zoomChange", updateZoomCursor);
      updateZoomCursor();

      // Add click-to-navigate on thumbnail slides
      thumbsEl.querySelectorAll(".swiper-slide").forEach((slide, i) => {
        slide.onclick = () => mainSwiper.slideToLoop(i);
      });

      // Highlight active thumbnail
      const updateThumbs = (index) => {
        if (!thumbsEl) return;
        thumbsEl.querySelectorAll(".swiper-slide").forEach((s, i) => {
          s.style.borderColor = i === index ? "rgb(37,99,235)" : "transparent";
          s.style.opacity = i === index ? "1" : "0.5";
        });
      };
      mainSwiper.on("slideChange", () => {
        _galleryPanStart = null;
        updateThumbs(mainSwiper.realIndex);
        updateZoomCursor();
      });
      updateThumbs(startIndex);
    }
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

    const recommendedSection = swiperContainer.closest(
      ".category-recommended-products",
    );
    const nextButton = document.querySelector(
      '.category-recommended-next[data-category-id="' + categoryId + '"]',
    );
    const prevButton = document.querySelector(
      '.category-recommended-prev[data-category-id="' + categoryId + '"]',
    );

    if (recommendedSection) {
      recommendedSection.classList.remove("category-recommended-nav-ready");
    }

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
      slidesPerView: 2,
      slidesPerGroup: 2,
      spaceBetween: 8,
      loop: false,
      autoHeight: false,
      navigation: {
        nextEl: nextButton,
        prevEl: prevButton,
        disabledClass: "swiper-button-disabled",
      },
      breakpoints: {
        640: {
          slidesPerView: 2,
          slidesPerGroup: 2,
          spaceBetween: 12,
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

    const syncRecommendedNavState = () => {
      if (!recommendedSection || !nextButton || !prevButton) return;
      recommendedSection.classList.toggle(
        "category-recommended-nav-ready",
        !swiper.isLocked,
      );
    };

    syncRecommendedNavState();
    swiper.on("lock", syncRecommendedNavState);
    swiper.on("unlock", syncRecommendedNavState);
    swiper.on("resize", syncRecommendedNavState);
    swiper.on("breakpoint", syncRecommendedNavState);

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
 * Initialize the hero banner / content-banner Swiper.
 * Called on DOMContentLoaded and after HTMX swaps of #page-content.
 * Banner count is read from data-banner-count on the swiper element.
 * Cleans up existing instance and resize listener to prevent leaks on re-init.
 */
function initHeroBannerSlider() {
  const swiperEl = document.querySelector(".content-banner-swiper");
  if (!swiperEl) return;

  if (typeof Swiper === "undefined") {
    window.setTimeout(initHeroBannerSlider, 100);
    return;
  }

  // Destroy previous instance if it exists
  if (swiperEl.swiper) {
    try {
      swiperEl.swiper.destroy(true, true);
    } catch (e) {
      // ignore
    }
  }

  // Remove previous resize listener to avoid accumulation
  if (swiperEl._bannerResizeHandler) {
    window.removeEventListener("resize", swiperEl._bannerResizeHandler);
    delete swiperEl._bannerResizeHandler;
  }

  const totalBanners = parseInt(swiperEl.dataset.bannerCount, 10) || 1;
  let swiperInstance = null;

  function getHeroTopOffset() {
    let anchor = document.getElementById("categories-row-wrapper");
    if (!anchor || window.getComputedStyle(anchor).display === "none") {
      anchor = document.querySelector(".top-nav-standard");
    }
    if (anchor) {
      const bottom = Math.round(anchor.getBoundingClientRect().bottom);
      if (bottom > 0) {
        return bottom;
      }
    }

    const fallbackTop = Math.round(swiperEl.getBoundingClientRect().top);
    return Math.max(fallbackTop, 0);
  }

  // Prevent black/partial hero rendering by revealing the banner only
  // after the first hero image is loaded (with a short failsafe fallback).
  swiperEl.classList.remove("is-ready");
  const markHeroReady = () => {
    updateBannerHeight();
    if (!swiperEl.classList.contains("is-ready")) {
      swiperEl.classList.add("is-ready");
    }
  };
  const firstHeroImage = swiperEl.querySelector(".swiper-slide img");
  if (firstHeroImage) {
    if (firstHeroImage.complete && firstHeroImage.naturalWidth > 0) {
      window.requestAnimationFrame(markHeroReady);
    } else {
      firstHeroImage.addEventListener("load", markHeroReady, { once: true });
      firstHeroImage.addEventListener("error", markHeroReady, { once: true });
      window.setTimeout(markHeroReady, 1500);
    }
  } else {
    markHeroReady();
  }

  function updateBannerHeight() {
    if (window.innerWidth < 768) {
      swiperEl.style.height = "580px";
      swiperEl.classList.remove("h-screen");
      swiperEl.style.minHeight = "580px";
      if (swiperInstance) swiperInstance.update();
      return;
    }

    const heroTopOffset = getHeroTopOffset();
    // Update CSS variable so the calc() in the template <style> resolves correctly.
    document.documentElement.style.setProperty(
      "--hero-banner-top",
      `${heroTopOffset}px`,
    );
    swiperEl.classList.remove("h-screen");
    if (swiperInstance) swiperInstance.update();
  }

  updateBannerHeight();
  swiperEl._bannerResizeHandler = updateBannerHeight;
  window.addEventListener("resize", updateBannerHeight);
  window.requestAnimationFrame(updateBannerHeight);
  if (document.fonts?.ready) {
    document.fonts.ready
      .then(() => {
        window.requestAnimationFrame(updateBannerHeight);
      })
      .catch(() => {
        // no-op
      });
  }

  if (document.readyState === "complete") {
    window.requestAnimationFrame(updateBannerHeight);
  } else {
    window.addEventListener("load", updateBannerHeight, { once: true });
  }

  const swiper = new Swiper(swiperEl, {
    loop: totalBanners > 1,
    autoplay: {
      delay: 7000,
      disableOnInteraction: false,
    },
    pagination: {
      el: swiperEl.querySelector(".content-pagination"),
      clickable: true,
      renderBullet: function (index, className) {
        return (
          '<button type="button" class="' +
          className +
          ' h-3 w-3 rounded-full" aria-label="Slide ' +
          (index + 1) +
          '"></button>'
        );
      },
    },
    navigation: {
      nextEl: swiperEl.querySelector(".swiper-button-next"),
      prevEl: swiperEl.querySelector(".swiper-button-prev"),
    },
    effect: "slide",
    speed: 600,
    slidesPerView: 1,
    spaceBetween: 0,
  });

  swiperInstance = swiper;

  // Full-height navigation areas (desktop)
  const navPrev = swiperEl.querySelector(".banner-nav-prev");
  const navNext = swiperEl.querySelector(".banner-nav-next");
  if (navPrev) navPrev.addEventListener("click", () => swiper.slidePrev());
  if (navNext) navNext.addEventListener("click", () => swiper.slideNext());

  // Mobile navigation buttons
  const mobilePrev = swiperEl.querySelector(".banner-mobile-prev");
  const mobileNext = swiperEl.querySelector(".banner-mobile-next");
  if (mobilePrev)
    mobilePrev.addEventListener("click", () => swiper.slidePrev());
  if (mobileNext)
    mobileNext.addEventListener("click", () => swiper.slideNext());

  function updateMobilePagination() {
    const container = swiperEl.querySelector(".banner-mobile-pagination");
    if (!container || typeof swiper.realIndex === "undefined") return;
    try {
      const activeIndex = swiper.realIndex;
      let dotsHtml = "";
      for (let i = 0; i < totalBanners; i++) {
        dotsHtml +=
          '<span class="mobile-dot ' +
          (i === activeIndex ? "active" : "") +
          '"></span>';
      }
      container.innerHTML = dotsHtml;
    } catch (e) {
      // silent
    }
  }

  if (totalBanners > 1) {
    updateMobilePagination();
    swiper.on("slideChange", updateMobilePagination);
  }
}

window.initHeroBannerSlider = initHeroBannerSlider;

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
// Show top progress bar when a soft-nav page-change request begins
document.addEventListener("htmx:beforeRequest", (event) => {
  const targetId =
    event.detail && event.detail.target && event.detail.target.id;
  if (targetId === "page-content-wrapper") {
    const snpBar = document.getElementById("soft-nav-progress");
    if (snpBar) {
      snpBar.classList.remove("snp-done", "snp-loading");
      // Force reflow so width resets to 0 before animating
      void snpBar.getBoundingClientRect();
      snpBar.classList.add("snp-loading");
    }
  }
});

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

  // Fires for cart-flow links (trigger inside #page-content, outerHTML swap)
  // and for soft-nav links (trigger in nav, innerHTML swap on #page-content-wrapper)
  const isPageContentSwap =
    (event.target && event.target.id === "page-content") ||
    (event.target && event.target.id === "page-content-wrapper");

  if (isPageContentSwap) {
    // Finish the progress bar
    const snpBar = document.getElementById("soft-nav-progress");
    if (snpBar) {
      snpBar.classList.remove("snp-loading");
      snpBar.classList.add("snp-done");
      setTimeout(() => snpBar.classList.remove("snp-done"), 500);
    }
    // Re-apply entrance animation on every swap so page content fades in smoothly.
    // Target the wrapper (stable element) rather than #page-content (the swapped-in element)
    // because HTMX marks swapped-in elements with htmx-added and its settle phase clears
    // ALL classes on those elements, wiping order-flow-enter before the animation can play.
    // The wrapper only gets htmx-settling removed (via classList.remove), so order-flow-enter
    // is preserved and the animation runs correctly.
    const pw = document.getElementById("page-content-wrapper");
    if (pw) {
      pw.classList.remove("order-flow-enter");
      void pw.offsetWidth;
      pw.classList.add("order-flow-enter");
      // Remove the class once the animation finishes so that the animation's
      // `transform: translateY(0)` (kept by fill-mode:both) no longer creates a
      // stacking context on this wrapper. Without this cleanup, every position:fixed
      // modal inside page-content-wrapper is trapped in an isolated stacking context
      // and cannot cover the navbar, and fixed-positioned backdrops are clipped to
      // this wrapper instead of the full viewport.
      pw.addEventListener(
        "animationend",
        () => {
          pw.classList.remove("order-flow-enter");
        },
        { once: true },
      );
    }

    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    window.requestAnimationFrame(() => {
      window.dispatchEvent(new Event("scroll"));
    });

    if (typeof window.initFlowbite === "function") {
      window.initFlowbite();
    }
    initCartSaveAsList();
    initHeroBannerSlider();
    initCategoryRecommendedSlider();
    initCategoryBannerSlider();
    initFavourites();
    syncCompareButtons(document);
    formatPrices();
    // Re-init checkout disabled-state and choice-card state after HTMX swap
    // (these run at cart.js boot but the checkout DOM may not exist yet at that point).
    if (typeof window.Cart?.reinitCheckout === "function") {
      window.Cart.reinitCheckout();
    }
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
function _positionToastContainer(container) {
  if (window.innerWidth < 640) {
    // Mobile: anchor below the sticky navbar
    const nav = document.querySelector(".storefront-top-nav");
    const navBottom = nav ? Math.round(nav.getBoundingClientRect().bottom) : 72;
    container.style.top = navBottom + 12 + "px";
    container.style.bottom = "";
  } else {
    // Desktop: keep at bottom-right
    container.style.top = "";
    container.style.bottom = "1rem";
  }
}

function showToast(message, type = "success") {
  // Check if there's an existing toast container
  let toastContainer = document.getElementById("favourite-toast-container");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "favourite-toast-container";
    toastContainer.className =
      "fixed right-4 sm:right-5 z-50 flex flex-col gap-2";
    document.body.appendChild(toastContainer);
  }
  _positionToastContainer(toastContainer);

  const normalizedType =
    type === "success" || type === "warning" || type === "error"
      ? type
      : "success";

  const isSuccess = normalizedType === "success";
  const isWarning = normalizedType === "warning";
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

  let toast = toastContainer.querySelector('[role="alert"]');

  if (toast) {
    // Update existing toast
    const msgEl = toast.querySelector(".ms-3");
    if (msgEl) msgEl.innerHTML = message;

    const iconWrapper = toast.querySelector("div:first-child");
    if (iconWrapper) {
      iconWrapper.className = iconWrapperClass;
      const pathEl = iconWrapper.querySelector("path");
      if (pathEl) pathEl.setAttribute("d", iconPath);

      const srOnly = iconWrapper.querySelector(".sr-only");
      if (srOnly)
        srOnly.textContent = isSuccess
          ? "Check icon"
          : isWarning
            ? "Warning icon"
            : "Error icon";
    }

    if (toast._removeTimeout) {
      clearTimeout(toast._removeTimeout);
    }

    // Bounce effect to indicate update
    toast.style.transform = "scale(1.05)";
    setTimeout(() => {
      toast.style.transform = "";
    }, 150);
  } else {
    // Create new toast
    toast = document.createElement("div");
    const toastId = `toast-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    toast.id = toastId;
    toast.setAttribute("role", "alert");
    toast.className =
      "relative flex items-center w-full max-w-xs p-4 mb-4 text-gray-900 bg-white rounded-xl border border-gray-100 dark:border-gray-700 shadow-[0_4px_20px_rgba(0,0,0,0.18),0_1px_6px_rgba(0,0,0,0.12)] dark:text-white dark:bg-gray-800 transform transition-all duration-300 ease-out opacity-0 translate-y-4";
    toast.innerHTML = `
      <div class="${iconWrapperClass}">
        <svg class="w-5 h-5" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 20 20">
          <path d="${iconPath}" />
        </svg>
        <span class="sr-only">${isSuccess ? "Check icon" : isWarning ? "Warning icon" : "Error icon"}</span>
      </div>
      <div class="ms-3 flex-1 min-w-0 text-sm font-medium transition-all duration-200">${message}</div>
    `;

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Close");
    closeBtn.className =
      "absolute -top-3.5 -right-3.5 z-10 inline-flex h-7 w-7 items-center justify-center rounded-full bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 shadow-sm text-gray-600 hover:bg-gray-200 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-600 dark:hover:text-white transition-colors cursor-pointer";
    closeBtn.innerHTML =
      '<svg class="h-4 w-4" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18 18 6M6 6l12 12"/></svg>';
    closeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (toast._removeToast) toast._removeToast();
    });
    toast.appendChild(closeBtn);

    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.classList.remove("opacity-0", "translate-y-4");
      toast.classList.add("opacity-100", "translate-y-0");
    }, 20);

    toast.addEventListener("click", () => {
      if (toast._removeToast) toast._removeToast();
    });
    toast.style.cursor = "pointer";
  }

  // Function to remove toast with animation
  toast._removeToast = () => {
    toast.classList.remove("opacity-100", "translate-y-0");
    toast.classList.add("opacity-0", "translate-y-4");
    setTimeout(() => {
      toast.remove();
    }, 300);
  };

  // Auto-dismiss after 5 seconds
  toast._removeTimeout = setTimeout(() => {
    if (toast.isConnected && toast._removeToast) {
      toast._removeToast();
    }
  }, 5000);
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
