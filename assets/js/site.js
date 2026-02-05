document.addEventListener("DOMContentLoaded", function () {
  // Format prices using browser locale with Intl.NumberFormat
  window.formatPrices();

  // Detect and sync browser timezone
  detectAndSyncTimezone();

  // Initialize scroll to top button
  initScrollToTop();

  // Initialize Swiper sliders
  initCategoryRecommendedSlider();
  initCategoryBannerSlider();
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
window.formatPrices = function () {
  if (typeof Intl === "undefined" || !Intl.NumberFormat) return;

  document.querySelectorAll("[data-price]").forEach((el) => {
    const value = parseFloat(el.dataset.price);
    const currency = el.dataset.currency || "PLN";
    const locale = CURRENCY_LOCALES?.[currency] || "pl-PL";

    if (isNaN(value)) return;

    el.textContent = new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      currencyDisplay: "symbol", // 👈 gwarantuje „zł”
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  });
};

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

// Re-format prices after HTMX swaps (for dynamic content)
document.addEventListener("htmx:afterSwap", formatPrices);
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
