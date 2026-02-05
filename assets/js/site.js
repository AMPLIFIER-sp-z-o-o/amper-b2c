import "../css/site.css";

document.addEventListener("DOMContentLoaded", function () {
  // Format prices using browser locale with Intl.NumberFormat
  formatPrices();

  // Detect and sync browser timezone
  detectAndSyncTimezone();

  // Initialize scroll to top button
  initScrollToTop();

  // Initialize Swiper sliders
  initCategoryRecommendedSlider();
  initCategoryBannerSlider();

  // Initialize favourites
  initFavourites();
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
    );
    if (!response.ok) return;

    const data = await response.json();
    // status is a dict mapping product_id -> list of wishlist_ids
    const status = data.status || {};
    const favouriteIds = new Set(
      Object.keys(status).map((id) => parseInt(id, 10)),
    );

    // Update all favourite buttons
    document.querySelectorAll(".favourite-btn").forEach((btn) => {
      const productId = parseInt(btn.dataset.productId, 10);
      if (favouriteIds.has(productId)) {
        setFavouriteState(btn, true);
      }
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
 * Shows wishlists dropdown or toggles default wishlist.
 */
async function handleFavouriteClick(e) {
  e.preventDefault();
  e.stopPropagation();

  const btn = e.currentTarget;
  const productId = btn.dataset.productId;
  if (!productId) return;

  // Check if product is already favourited
  const isFavourited =
    btn
      .querySelector(".favourite-icon-filled")
      ?.classList.contains("hidden") === false;

  if (isFavourited) {
    // Remove from all wishlists
    await removeFromFavourites(productId, btn);
  } else {
    // Add to default wishlist
    await addToFavourites(productId, btn);
  }
}

/**
 * Add product to default wishlist.
 */
async function addToFavourites(productId, btn) {
  // Optimistic UI update
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
      // Revert on error
      setFavouriteState(btn, false);
      showToast(data.message || "Failed to add to favourites", "error");
    } else {
      // Update all buttons for this product
      updateAllFavouriteButtons(productId, data.action === "added");
      showToast(data.message || "Added to favourites", "success");

      // If on favourites page, update the UI stats
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
    // Revert on error
    setFavouriteState(btn, false);
    showToast("Failed to add to favourites", "error");
  }
}

/**
 * Remove product from all wishlists.
 */
async function removeFromFavourites(productId, btn) {
  // Optimistic UI update
  setFavouriteState(btn, false);

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
      // Revert on error
      setFavouriteState(btn, true);
      showToast(data.message || "Failed to remove from favourites", "error");
    } else {
      // Update all buttons for this product
      updateAllFavouriteButtons(productId, data.action === "added");
      showToast(data.message || "Removed from favourites", "success");

      // If on favourites page, remove the product card and update UI
      if (isOnFavouritesPage()) {
        removeProductCardFromFavouritesPage(productId, data);
      }
    }
  } catch (e) {
    // Revert on error
    setFavouriteState(btn, true);
    showToast("Failed to remove from favourites", "error");
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
 * @param {string} type - The type of toast: 'success' or 'error'
 */
function showToast(message, type = "success") {
  // Check if there's an existing toast container
  let toastContainer = document.getElementById("favourite-toast-container");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "favourite-toast-container";
    toastContainer.className =
      "fixed bottom-4 right-4 z-50 flex flex-col gap-2";
    document.body.appendChild(toastContainer);
  }

  const toastId = `toast-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const isSuccess = type === "success";
  const toast = document.createElement("div");
  const iconWrapperClass = isSuccess
    ? "inline-flex items-center justify-center shrink-0 w-8 h-8 text-green-500 bg-green-100 rounded-lg dark:bg-green-800 dark:text-green-200"
    : "inline-flex items-center justify-center shrink-0 w-8 h-8 text-red-500 bg-red-100 rounded-lg dark:bg-red-800 dark:text-red-200";
  const iconPath = isSuccess
    ? "M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5Zm3.707 8.207-4 4a1 1 0 0 1-1.414 0l-2-2a1 1 0 0 1 1.414-1.414L9 10.586l3.293-3.293a1 1 0 0 1 1.414 1.414Z"
    : "M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5Zm3.707 11.793a1 1 0 1 1-1.414 1.414L10 11.414l-2.293 2.293a1 1 0 0 1-1.414-1.414L8.586 10 6.293 7.707a1 1 0 0 1 1.414-1.414L10 8.586l2.293-2.293a1 1 0 0 1 1.414 1.414L11.414 10l2.293 2.293Z";

  toast.id = toastId;
  toast.setAttribute("role", "alert");
  toast.className =
    "flex items-center w-full max-w-xs p-4 mb-4 text-gray-900 bg-white rounded-lg shadow-sm dark:text-white dark:bg-gray-800 transform transition-all duration-300 ease-out opacity-0 translate-y-4";
  toast.innerHTML = `
    <div class="${iconWrapperClass}">
      <svg class="w-5 h-5" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 20 20">
        <path d="${iconPath}" />
      </svg>
      <span class="sr-only">${isSuccess ? "Check icon" : "Error icon"}</span>
    </div>
    <div class="mx-4 text-sm font-medium">${message}</div>
    <button type="button" class="ms-auto -mx-1.5 -my-1.5 bg-white text-gray-500 hover:text-gray-900 rounded-lg focus:ring-2 focus:ring-gray-300 p-1.5 hover:bg-gray-200 inline-flex items-center justify-center h-8 w-8 dark:text-gray-400 dark:hover:text-white dark:bg-gray-800 dark:hover:bg-gray-700 cursor-pointer" data-dismiss-target="#${toastId}" aria-label="Close">
      <span class="sr-only">Close</span>
      <svg class="w-3 h-3" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 14 14">
        <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6" />
      </svg>
    </button>
  `;

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

  // Add click listener to close button to trigger animation
  const closeBtn = toast.querySelector("button[data-dismiss-target]");
  closeBtn.addEventListener("click", (e) => {
    e.preventDefault();
    removeToast();
  });

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
});

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

  // Get currency from existing price display or default to PLN
  const priceElement = headerDiv.querySelector("[data-price]");
  const currency = priceElement?.dataset.currency || "PLN";

  // Format the total value
  const locale = CURRENCY_LOCALES[currency] || "pl-PL";
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

  const addAllBtn = document.querySelector(".add-all-to-cart-btn");
  addAllBtn?.classList.add("hidden");
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
