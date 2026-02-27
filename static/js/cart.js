
window.Cart = (function () {
    const INLINE_SPINNER_SVG =
        '<svg class="w-5 h-5 animate-spin text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
    let cartStateSyncPromise = null;

    function getCartLinesLabelForCount(el, count) {
        const ds = el?.dataset || {};
        const lang =
            document.documentElement.getAttribute("lang") ||
            navigator.language ||
            "en";

        let category = "other";
        try {
            category = new Intl.PluralRules(lang).select(count);
        } catch (e) {
            category = count === 1 ? "one" : "other";
        }

        const byCategory = {
            one: ds.labelOne,
            few: ds.labelFew,
            many: ds.labelMany,
            other: ds.labelOther,
        };

        const label = (byCategory[category] || ds.labelItems || "items").trim();
        return label || "items";
    }

    function updateProceedToSummaryDisabledState() {
        const btn = document.getElementById("proceed-to-summary-btn");
        const form = document.getElementById("checkout-details-form");
        if (!btn || !form) return;

        const hint = document.getElementById("proceed-disabled-hint");

        const hasDelivery = !!document.querySelector('input[name="delivery-method"]:checked');
        const hasPayment = !!document.querySelector('input[name="payment-method"]:checked');
        const isValid = typeof form.checkValidity === "function" ? form.checkValidity() : true;
        const canProceed = Boolean(isValid && hasDelivery && hasPayment);

        btn.disabled = !canProceed;
        btn.setAttribute("aria-disabled", String(!canProceed));

        if (hint) {
            hint.classList.toggle("hidden", Boolean(canProceed));
        }
    }

    function initCheckoutCountryReload() {
        const countrySelect = document.getElementById("shipping_country");
        if (!countrySelect) return;

        // Only applies to whitelist-backed select (when a ShippingCountry list exists).
        if (countrySelect.tagName !== "SELECT") return;

        countrySelect.addEventListener("change", () => {
            // Reload checkout so available delivery/payment methods update.
            const value = String(countrySelect.value || "").trim();
            const url = new URL(window.location.href);
            if (value) {
                url.searchParams.set("country", value);
            } else {
                url.searchParams.delete("country");
            }
            window.location.href = url.toString();
        });
    }

    function initCartCountrySubmit() {
        const countrySelect = document.getElementById("cart-shipping-country");
        if (!countrySelect) return;
        if (countrySelect.tagName !== "SELECT") return;

        countrySelect.addEventListener("change", () => {
            const form = countrySelect.closest("form");
            if (form) form.submit();
        });
    }

    function startInlineLoader(hostEl) {
        if (!hostEl) return;
        hostEl.classList.add("btn-loading");
        // Requires `relative` on host (added in template) for correct positioning.
        if (hostEl.querySelector(':scope > [data-inline-loader]')) return;
        const wrap = document.createElement("span");
        wrap.setAttribute("data-inline-loader", "1");
        wrap.className =
            "absolute left-3 top-3 inline-flex items-center justify-center";
        wrap.innerHTML = INLINE_SPINNER_SVG;
        hostEl.appendChild(wrap);
    }

    function stopInlineLoader(hostEl) {
        if (!hostEl) return;
        hostEl.classList.remove("btn-loading");
        hostEl.querySelector(':scope > [data-inline-loader]')?.remove();
    }

    function updateCheckoutChoiceCardStates() {
        const cards = document.querySelectorAll('[data-checkout-choice-card]');
        if (!cards.length) return;

        cards.forEach((card) => {
            const input = card.querySelector('input[type="radio"]');
            if (!input) return;

            const isChecked = Boolean(input.checked);
            card.classList.toggle("ring-2", isChecked);
            card.classList.toggle("ring-primary-600", isChecked);
            card.classList.toggle("dark:ring-primary-500", isChecked);
        });
    }

    function showCartError(message) {
        if (typeof window.showToast === "function") {
            window.showToast(message, "error");
        }
    }

    function getCSRFToken() {
        const inputToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (inputToken) return inputToken;

        // Fallback: token is available globally on <body> for HTMX requests
        const hxHeaders = document.body?.getAttribute("hx-headers");
        if (hxHeaders) {
            try {
                const parsed = JSON.parse(hxHeaders);
                const headerToken = parsed?.["X-CSRFToken"];
                if (headerToken) return headerToken;
            } catch (_) {
                // ignore
            }
        }

        // Fallback: Django default cookie name
        const cookie = document.cookie
            .split(";")
            .map(c => c.trim())
            .find(c => c.startsWith("csrftoken="));
        if (cookie) {
            return decodeURIComponent(cookie.split("=")[1] || "");
        }

        return null;
    }

    function updateNavCartBadge(linesCount) {
        const count = Number(linesCount);
        if (!Number.isFinite(count)) return;

        const cartBtn = document.getElementById("cartDropdownButton");
        if (!cartBtn) return;

        let badge = cartBtn.querySelector("[data-cart-badge]");

        if (count > 0) {
            if (!badge) {
                badge = document.createElement("span");
                badge.setAttribute("data-cart-badge", "");
                badge.className =
                    "absolute -top-1 -right-1 flex items-center justify-center min-w-5 h-5 px-1.5 text-xs font-bold text-white bg-primary-600 rounded-full leading-none";
                cartBtn.appendChild(badge);
            }
            badge.textContent = String(count);
        } else {
            badge?.remove();
        }
    }

    function markLinePending(lineEl, pending) {
        if (!lineEl) return;
        if (pending) {
            const dropdown = lineEl.closest("#cartDropdown");
            if (dropdown) {
                // Keep dropdown open briefly while DOM updates happen (prevents hover-close flicker)
                dropdown.dataset.lockOpenUntil = String(Date.now() + 800);
            }
            lineEl.dataset.cartPending = "1";
            lineEl.classList.add("opacity-60");
            lineEl.querySelectorAll(".remove-cart-line, [data-counter] button").forEach((el) => {
                el.classList.add("pointer-events-none");
            });
        } else {
            delete lineEl.dataset.cartPending;
            lineEl.classList.remove("opacity-60");
            lineEl.querySelectorAll(".remove-cart-line, [data-counter] button").forEach((el) => {
                el.classList.remove("pointer-events-none");
            });
        }
    }

    function setNavCartEmptyState(linesCount) {
        const navCartLinesContainer = document.querySelector('#nav-cart-lines');
        if (!navCartLinesContainer) return;

        const emptyStateEl = navCartLinesContainer.querySelector('[data-cart-empty-state]');
        const dropdown = navCartLinesContainer.closest('#cartDropdown');
        const footerEl = dropdown?.querySelector('[data-cart-summary-footer]');

        const count = Number(linesCount);
        const hasLines = Number.isFinite(count) ? count > 0 : navCartLinesContainer.querySelector('[data-cart-line]');
        
        if (emptyStateEl) {
            emptyStateEl.classList.toggle('hidden', Boolean(hasLines));
        }
        if (footerEl) {
            footerEl.classList.toggle('hidden', !hasLines);
        }
    }

    function replaceNavCartLines(linesHtml) {
        const navCartLinesContainer = document.querySelector('#nav-cart-lines');
        if (!navCartLinesContainer) return;

        navCartLinesContainer
            .querySelectorAll('[data-cart-line]')
            .forEach((el) => el.remove());

        const normalizedHtml = String(linesHtml || "").trim();
        if (!normalizedHtml) return;

        const temp = document.createElement("div");
        temp.innerHTML = normalizedHtml;

        const emptyStateEl = navCartLinesContainer.querySelector('[data-cart-empty-state]');
        const fragment = document.createDocumentFragment();
        Array.from(temp.children).forEach((child) => fragment.appendChild(child));

        if (emptyStateEl) {
            navCartLinesContainer.insertBefore(fragment, emptyStateEl);
        } else {
            navCartLinesContainer.appendChild(fragment);
        }
    }

    function clearVisibleToasts() {
        const toastContainer = document.getElementById("favorite-toast-container");
        if (!toastContainer) return;

        toastContainer.querySelectorAll('[role="alert"]').forEach((toast) => {
            if (toast && toast._removeTimeout) {
                clearTimeout(toast._removeTimeout);
            }
            toast.remove();
        });
    }

    function setCartBadgeVisibility(hidden) {
        const badge = document.querySelector("#cartDropdownButton [data-cart-badge]");
        if (!badge) return;
        badge.style.visibility = hidden ? "hidden" : "";
    }

    function syncCartStateFromServer() {
        if (!window.CART_STATE_URL) {
            return Promise.resolve(null);
        }
        if (cartStateSyncPromise) {
            return cartStateSyncPromise;
        }

        cartStateSyncPromise = fetch(window.CART_STATE_URL, {
            method: "GET",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        })
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
                if (!data || data.success !== true) return null;

                if (data.nav_lines_html !== undefined) {
                    replaceNavCartLines(data.nav_lines_html);
                }

                updateCartSummary({
                    lines_count: data.lines_count,
                    cart_total: data.cart_total,
                    cart_subtotal: data.cart_subtotal,
                    discount_total: data.discount_total,
                    delivery_cost: data.delivery_cost,
                });
                setNavCartEmptyState(data.lines_count);

                return data;
            })
            .catch(() => null)
            .finally(() => {
                cartStateSyncPromise = null;
            });

        return cartStateSyncPromise;
    }

    function handleHistoryRestoreSync() {
        // bfcache/history snapshots can restore stale cart toasts and old cart badge values.
        clearVisibleToasts();
        setCartBadgeVisibility(true);
        syncCartStateFromServer().finally(() => {
            setCartBadgeVisibility(false);
        });
    }

    function isBackForwardNavigation(event) {
        if (event && event.persisted) return true;

        try {
            const navEntries = performance.getEntriesByType("navigation");
            if (Array.isArray(navEntries) && navEntries.length > 0) {
                return navEntries[0]?.type === "back_forward";
            }
        } catch (_) {
            // Ignore environments where navigation timing is unavailable.
        }

        return false;
    }

    function updateCartSummary(data) {
        const totalEls = document.querySelectorAll('[data-cart-total]');
        const subtotalEls = document.querySelectorAll('[data-cart-subtotal]');
        const deliveryEls = document.querySelectorAll('[data-delivery-cost]');
        const discountEls = document.querySelectorAll('[data-discount-total]');
        const discountRows = document.querySelectorAll('[data-discount-row]');
        const cartLinesNumber =  document.querySelectorAll('[data-cart-lines-number]');
        const navCartLinesContainer = document.querySelector('#nav-cart-lines');

        if (data?.lines_count !== undefined) {
            updateNavCartBadge(data.lines_count);
        }

        const cartPageLines = document.querySelector("#cart-page-lines");

        if (data.updated_line_html) {
            if (!navCartLinesContainer) {
                // No nav dropdown on this page (e.g. mobile layout); still update badge/count.
            } else {
            const temp = document.createElement('div');
            temp.innerHTML = data.updated_line_html.trim();

            const newLine = temp.firstElementChild;
            const lineId = newLine.dataset.cartLineId;

            const existingLine = navCartLinesContainer.querySelector(
                `[data-cart-line-id="${lineId}"]`
            );

            const showToast = typeof window.showToast === "function" ? window.showToast : null;
            const adjusted = data && data.quantity_adjusted === true;

            if (existingLine) {
                existingLine.replaceWith(newLine);
                if (showToast) {
                    if (adjusted) {
                        const available = Number(data.available_stock);
                        showToast(
                            `Only ${available} available for <strong>${data.product_name}</strong>. Added the maximum available quantity to your cart.`,
                            "warning",
                        );
                    } else {
                        showToast(`Updated <strong>${data.product_name}</strong> in Cart`, "success");
                    }
                }
            } else {
                navCartLinesContainer.appendChild(newLine);
                if (showToast) {
                    if (adjusted) {
                        const available = Number(data.available_stock);
                        showToast(
                            `Only ${available} available for <strong>${data.product_name}</strong>. Added the maximum available quantity to your cart.`,
                            "warning",
                        );
                    } else {
                        showToast(`Added <strong>${data.product_name}</strong> to Cart`, "success");
                    }
                }
            }

            setNavCartEmptyState(data.lines_count);
            }
        }
        if (data.removed_line_id) {
            document.querySelectorAll(
                `[data-cart-line-id="${data.removed_line_id}"]`
            ).forEach(el => el.remove());
            if (typeof window.showToast === "function") {
                window.showToast(`Removed <strong>${data.product_name}</strong> from Cart`, 'success');
            }

            setNavCartEmptyState(data.lines_count);
        }

        // Cart page: switch to empty-state layout without reloading.
        if (cartPageLines && data?.lines_count !== undefined) {
            const count = Number(data.lines_count);
            if (Number.isFinite(count) && count === 0) {
                cartPageLines
                    .querySelectorAll("[data-cart-line]")
                    .forEach((el) => el.remove());
                cartPageLines
                    .querySelector("[data-cart-page-empty-state]")
                    ?.classList.remove("hidden");
                document.querySelector("[data-cart-summary-card]")?.remove();
                document.querySelector("[data-cart-page-actions]")?.remove();
            }
        }

        if (data.cart_total !== undefined) {
            totalEls.forEach(el => {
                el.dataset.price = data.cart_total;
                el.textContent = data.cart_total;
            });
            subtotalEls.forEach(el => {
                el.dataset.price = data.cart_subtotal;
                el.textContent = data.cart_subtotal;
            });
            deliveryEls.forEach(el => {
                el.dataset.price = data.delivery_cost;
                el.textContent = data.delivery_cost;
            });

            if (data.discount_total !== undefined) {
                discountEls.forEach(el => {
                    el.dataset.price = data.discount_total;
                    el.textContent = `-${data.discount_total}`;
                });

                const discountValue = parseFloat(data.discount_total);
                const hideRow = !Number.isFinite(discountValue) || discountValue <= 0;
                discountRows.forEach((row) => row.classList.toggle('hidden', hideRow));
            }

            cartLinesNumber.forEach(el => {
                const count = parseInt(data.lines_count, 10) || 0;
                const label = getCartLinesLabelForCount(el, count);

                el.dataset.lines_number = String(count);
                el.textContent = `(${count} ${label})`;
                
                if (count === 0) {
                    el.style.display = 'none';
                } else {
                    el.style.display = '';
                }
            });
        }

        if(data.line_id) {
            const cartPage = document.querySelector("#cart-page-lines");
            if (cartPage) {
            const lineEl = cartPage.querySelector(
            `[data-cart-line-id="${data.line_id}"]`
            );
            if (lineEl) {
                const subtotalEls = lineEl.querySelectorAll("[data-cart-line-subtotal]");
                subtotalEls.forEach((subtotalEl) => {
                    subtotalEl.dataset.price = data.line_subtotal;
                    subtotalEl.textContent = data.line_subtotal;
                });
                const input = lineEl.querySelector("[data-counter-input]");
                if (input && data.product_quantity !== undefined) {
                    input.value = data.product_quantity;
                }

                // Show unit price only when quantity > 1
                const unitRow = lineEl.querySelector("[data-cart-unit-price-row]");
                if (unitRow && data.product_quantity !== undefined) {
                    const qty = parseInt(String(data.product_quantity || "0"), 10) || 0;
                    unitRow.classList.toggle("hidden", qty <= 1);
                }

                // Resolve stock issue state from current DOM values so UX updates immediately
                // even if backend response shape changes.
                const qtyInput = lineEl.querySelector("[data-counter-input]");
                const qtyWrap = lineEl.querySelector("[data-qty-wrap]");
                const currentQty = parseInt(String(qtyInput?.value || data.product_quantity || "0"), 10) || 0;
                const maxAttr = qtyInput?.getAttribute("max");
                const maxFromInput = parseInt(String(maxAttr || ""), 10);
                const maxFromResponse = parseInt(String(data.available_stock || ""), 10);
                const stockLimit = Number.isFinite(maxFromInput)
                    ? maxFromInput
                    : (Number.isFinite(maxFromResponse) ? maxFromResponse : NaN);

                if (Number.isFinite(stockLimit) && currentQty <= stockLimit) {
                    lineEl.querySelectorAll("[data-stock-issue]").forEach((el) => el.remove());
                    if (qtyWrap) {
                        qtyWrap.classList.remove("ring-red-500", "dark:ring-red-500");
                    }
                }
            }
            }
        }

        // After any cart update on the cart page: check if all stock issues are resolved
        // and update the orange warning banner + checkout CTA accordingly.
        const stockValidationRoot = document.querySelector("[data-checkout-stock-validation]");
        if (stockValidationRoot) {
            const remainingIssues = stockValidationRoot.querySelectorAll("[data-stock-issue='1']");
            const orangeBanner = document.querySelector("[data-cart-stock-warning]");
            const checkoutBtn = document.querySelector(".cart-checkout-btn");
            const fixHint = document.querySelector("[data-cart-fix-hint]");

            if (orangeBanner) {
                orangeBanner.classList.toggle("hidden", remainingIssues.length === 0);
            }
            if (checkoutBtn) {
                if (remainingIssues.length === 0) {
                    checkoutBtn.classList.remove("opacity-60", "pointer-events-none");
                    checkoutBtn.removeAttribute("aria-disabled");
                    checkoutBtn.removeAttribute("tabindex");
                } else {
                    checkoutBtn.classList.add("opacity-60", "pointer-events-none");
                    checkoutBtn.setAttribute("aria-disabled", "true");
                    checkoutBtn.setAttribute("tabindex", "-1");
                }
            }
            if (fixHint) {
                fixHint.classList.toggle("hidden", remainingIssues.length === 0);
            }
        }

        if (typeof window.formatPrices === "function") {
            window.formatPrices();
        }
    }

    function addToCart(productId, quantity = 1, mode = "set") {
        const cartId = localStorage.getItem("cart_id");

        const formData = new FormData();
        formData.append("product_id", productId);
        formData.append("quantity", quantity);
        formData.append("mode", mode);

        if (cartId) {
        formData.append("cart_id", cartId);
        }

        return fetch(window.ADD_TO_CART_URL, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCSRFToken()
        },
        body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                localStorage.setItem("cart_id", data.cart_id);

                document.dispatchEvent(
                    new CustomEvent("cart:updated", { detail: data })
                );
            } else {
                showCartError(data.message || "Failed to update cart.");
            }

            return data;
        })
        .catch(console.error);
    }

    function removeLine(productId) {
        const formData = new FormData();
        formData.append("product_id", productId);

        return fetch(window.REMOVE_FROM_CART_URL, {
            method: "POST",
            headers: {
            "X-CSRFToken": getCSRFToken()
            },
            body: formData
        })
            .then(res => res.json())
            .then(data => {
            if (data.success) {

                document.dispatchEvent(
                new CustomEvent("cart:updated", { detail: data })
                );
            } else {
                showCartError(data.message || "Failed to update cart.");
            }

            return data;
            })
            .catch(console.error);
    }

    // ADD TO CART
    document.addEventListener("click", function (e) {
        const btn = e.target.closest(".add-to-cart-btn");
        if (!btn) return;

        e.preventDefault();
        e.stopPropagation();

        if (btn.classList.contains("btn-loading")) return;

        const addMode = (btn.dataset.addToCartMode || "increment").toLowerCase();

        const productId = btn.dataset.productId;
        let quantity = 1;
        const quantityInputId = btn.dataset.quantityInput;
        if (quantityInputId) {
            const scopeRoot = btn.closest("[data-product-detail-card]") || document;
            const input = scopeRoot.querySelector(`#${CSS.escape(quantityInputId)}`);
            quantity = parseInt(input?.value || "1", 10);
        } else {
            quantity = parseInt(btn.dataset.quantity || "1", 10);
        }
        if (!Number.isFinite(quantity) || quantity <= 0) quantity = 1;

        if (typeof window.btnLoading === "function") {
            window.btnLoading(btn);
        }
        addToCart(productId, quantity, addMode)
            .then((data) => {
                // Keep product details quantity input in sync when backend clamps it.
                if (quantityInputId && data && data.success && data.applied_quantity !== undefined) {
                    const scopeRoot = btn.closest("[data-product-detail-card]") || document;
                    const input = scopeRoot.querySelector(`#${CSS.escape(quantityInputId)}`);
                    if (input) input.value = String(data.applied_quantity);
                }
            })
            .catch(() => {})
            .finally(() => {
                if (typeof window.btnReset === "function") {
                    window.btnReset(btn);
                }
            });
    });

    // Navigation/loading for key cart flow CTAs (Proceed / Place order).
    // We intentionally apply loading after the click is already in-flight, so we don't block the current navigation.
    document.addEventListener("click", function (e) {
        const btn = e.target.closest("[data-nav-loading-btn]");
        if (!btn) return;
        if (btn.classList.contains("btn-loading")) return;

        let submitForm = null;
        if (btn instanceof HTMLButtonElement || btn instanceof HTMLInputElement) {
            if (btn.form instanceof HTMLFormElement) {
                submitForm = btn.form;
            } else {
                const formId = btn.getAttribute("form");
                if (formId) {
                    const linkedForm = document.getElementById(formId);
                    if (linkedForm instanceof HTMLFormElement) {
                        submitForm = linkedForm;
                    }
                }
            }
        }

        if (
            submitForm &&
            typeof submitForm.checkValidity === "function" &&
            !submitForm.checkValidity()
        ) {
            // Prevent the browser's native (silent) validation on hidden required fields.
            // Instead, open the address modal so the user sees what needs to be filled in.
            e.preventDefault();
            const addressModalToggle = document.querySelector(
                '[data-modal-toggle="shipping-details-modal"]'
            );
            if (addressModalToggle) {
                addressModalToggle.click();
            }
            return;
        }

        if (typeof window.btnLoading === "function") {
            window.btnLoading(btn);
        }
    });

    // REMOVE LINE
    document.addEventListener("click", function (e) {
        const btn = e.target.closest(".remove-cart-line");
        if (!btn) return;
        if (btn.classList.contains("btn-loading")) return;

        const productId = btn.dataset.productId;

        const row = btn.closest("[data-cart-line]");
        if (row?.dataset.cartPending === "1") return;
        markLinePending(row, true);
        if (typeof window.btnLoading === "function") {
            window.btnLoading(btn);
        }

        removeLine(productId)
            .catch(() => {
                showCartError("Failed to remove item from cart.");
            })
            .finally(() => {
                if (typeof window.btnReset === "function") {
                    window.btnReset(btn);
                }
                // If the line was replaced/removed by updateCartSummary, this is a no-op.
                markLinePending(row, false);
            });
    });

    document.addEventListener("cart:updated", (e) => {
        updateCartSummary(e.detail);
    });

    // Quantity +/- should immediately sync with the server
    document.addEventListener("click", function(e) {
        const btn = e.target.closest("[data-action='decrement'], [data-action='increment']");
        if (!btn) return;
        if (btn.classList.contains("btn-loading")) return;

        const container = btn.closest("[data-counter]");
        if (!container) return;

        const row = btn.closest("[data-cart-line]");
        if (row?.dataset.cartPending === "1") return;

        const input = container.querySelector("[data-counter-input]");
        if (!input) return;

        const productId = container.dataset.counter?.split("-")[1];
        if (!productId) return;

        let value = parseInt(input.value.trim() || "0", 10);
        if (isNaN(value)) value = 0;

        const prevValue = value;
        if (btn.dataset.action === "decrement") {
            value = Math.max(0, value - 1);
        } else {
            value = value + 1;
        }

        input.value = value;
        container.dataset.syncedValue = String(value);

        markLinePending(row, true);
        if (typeof window.btnLoading === "function") {
            window.btnLoading(btn);
        }

        if (value > 0) {
            addToCart(productId, value)
                .then((data) => {
                    if (!data || !data.success) {
                        input.value = prevValue;
                        container.dataset.syncedValue = String(prevValue);
                    }
                })
                .catch(() => {
                    input.value = prevValue;
                    container.dataset.syncedValue = String(prevValue);
                    showCartError("Failed to update cart quantity.");
                })
                .finally(() => {
                    if (typeof window.btnReset === "function") {
                        window.btnReset(btn);
                    }
                    markLinePending(row, false);
                });
        } else {
            removeLine(productId)
                .then((data) => {
                    if (!data || !data.success) {
                        input.value = prevValue;
                        container.dataset.syncedValue = String(prevValue);
                    }
                })
                .catch(() => {
                    input.value = prevValue;
                    container.dataset.syncedValue = String(prevValue);
                    showCartError("Failed to update cart quantity.");
                })
                .finally(() => {
                    if (typeof window.btnReset === "function") {
                        window.btnReset(btn);
                    }
                    markLinePending(row, false);
                });
        }
    });

    document.addEventListener("mousedown", function(e) {
        const btn = e.target.closest("[data-action='increment'], [data-action='decrement']");
        if (!btn) return;

        const container = btn.closest("[data-counter]");
        const input = container?.querySelector("[data-counter-input]");
        if (!input) return;

        if (input.dataset.readonly === "true") {
            e.preventDefault();
            return;
        }

        e.preventDefault();  
        input.focus();       
    });

    // Clicking on cart line whitespace navigates to the product page
    document.addEventListener("click", function (e) {
        const row = e.target.closest("[data-cart-line][data-product-url]");
        if (!row) return;

        // Let normal interactive elements handle their own clicks
        if (e.target.closest("a, button, input, textarea, select, [data-counter]")) return;

        const url = row.dataset.productUrl;
        if (url) window.location.href = url;
    });

    // Clicking inside the cart dropdown (but not on a product line) should go to the cart page
    document.addEventListener("click", function (e) {
        const dropdown = e.target.closest("#cartDropdown");
        if (!dropdown) return;

        // Ignore clicks on product lines and on interactive elements
        if (e.target.closest("[data-cart-line], a, button, input, textarea, select")) return;

        const cartHref = document.getElementById("cartDropdownButton")?.getAttribute("href") || "/cart/";
        window.location.href = cartHref;
    });

    // Keep the checkout CTA disabled until the form is valid and delivery/payment are selected.
    document.addEventListener(
        "input",
        function (e) {
            if (!e.target.closest("#checkout-details-form")) return;
            updateProceedToSummaryDisabledState();
        },
        true
    );

    document.addEventListener(
        "change",
        function (e) {
            const el = e.target;
            if (
                el.closest("#checkout-details-form") ||
                el.matches('input[name="delivery-method"], input[name="payment-method"]')
            ) {
                updateProceedToSummaryDisabledState();
                updateCheckoutChoiceCardStates();
            }
        },
        true
    );

    // Initial state on page load (if present)
    updateProceedToSummaryDisabledState();
    updateCheckoutChoiceCardStates();
    initCheckoutCountryReload();
    initCartCountrySubmit();

    // Initialize blur-sync baseline so focusing and blurring without changes doesn't trigger a sync/toast.
    document.addEventListener(
        "focusin",
        function (e) {
            const input = e.target;
            if (!input.matches("[data-counter-input]")) return;
            const container = input.closest("[data-counter]");
            if (!container) return;
            container.dataset.syncedValue = String(input.value ?? "");
        },
        true
    );

    document.addEventListener("blur", function(e) {
        const input = e.target;
        if (!input.matches("[data-counter-input]")) return;

        if (input.dataset.readonly === "true") return;

        const container = input.closest("[data-counter]");
        const productId = container.dataset.counter.split("-")[1];

        let value = parseInt(input.value || "0", 10);
        if (isNaN(value) || value < 0) value = 0;

        input.value = value;

        // Avoid duplicate sync when value was already updated via +/- click
        const syncedValue = container.dataset.syncedValue;
        if (syncedValue === undefined) {
            container.dataset.syncedValue = String(value);
            return;
        }
        if (syncedValue !== undefined && syncedValue === String(value)) {
            return;
        }

        container.dataset.syncedValue = String(value);

        if(value > 0) {
            addToCart(productId, value);
        } else {
            removeLine(productId)
        }

    }, true);

    // Select delivery method
    document.addEventListener("change", function (e) {
        const input = e.target;
        if (!input.matches('input[name="delivery-method"]')) return;

        updateCheckoutChoiceCardStates();

        const methodId = input.value;
        const form = input.closest("form");

        const hostLabel = input.closest("label");
        startInlineLoader(hostLabel);

        fetch(form.action || window.location.href, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: new URLSearchParams({
                "delivery-method": methodId
            })
        })
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                if (data.message) {
                    showCartError(data.message);
                }
                return;
            }

            document.querySelectorAll("[data-cart-total]").forEach(el => {
                el.textContent = data.total;
                el.dataset.price = data.total;
            });

            if (data.discount_total !== undefined) {
                document.querySelectorAll("[data-discount-total]").forEach(el => {
                    el.textContent = `-${data.discount_total}`;
                    el.dataset.price = data.discount_total;
                });
            }

            document.querySelectorAll("[data-delivery-cost]").forEach(el => {
                el.textContent = data.delivery_cost;
                el.dataset.price = data.delivery_cost;
            });
            formatPrices()
        })
        .catch(console.error)
        .finally(() => {
            stopInlineLoader(hostLabel);
        });
    });

    // Select payment method
    document.addEventListener("change", function (e) {
        const input = e.target;
        if (!input.matches('input[name="payment-method"]')) return;

        updateCheckoutChoiceCardStates();

        const paymentId = input.value;
        const form = input.closest("form");

        const hostLabel = input.closest("label");
        startInlineLoader(hostLabel);

        fetch(form.action || window.location.href, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: new URLSearchParams({
                "payment-method": paymentId
            })
        })
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                if (data.message) {
                    showCartError(data.message);
                }
                return;
            }

            document.querySelectorAll("[data-cart-total]").forEach(el => {
                el.textContent = data.total;
                el.dataset.price = data.total;
            });

            if (data.discount_total !== undefined) {
                document.querySelectorAll("[data-discount-total]").forEach(el => {
                    el.textContent = `-${data.discount_total}`;
                    el.dataset.price = data.discount_total;
                });
            }

            document.querySelectorAll("[data-delivery-cost]").forEach(el => {
                el.textContent = data.delivery_cost;
                el.dataset.price = data.delivery_cost;
            });

            formatPrices()
        })
        .catch(console.error)
        .finally(() => {
            stopInlineLoader(hostLabel);
        });
    });

    // Clear cart (standard POST form submit)
    document.addEventListener("submit", function (e) {
        const form = e.target;
        if (!form || !(form instanceof HTMLFormElement)) return;
        if (!form.matches("[data-clear-cart-form]")) return;

        const btn = form.querySelector("[data-clear-cart-btn]");
        if (btn && typeof window.btnLoading === "function") {
            window.btnLoading(btn);
        }
    });

    // Checkout details modal: show loading on "Done" (save_only) submit.
    document.addEventListener("submit", function (e) {
        const form = e.target;
        if (!form || !(form instanceof HTMLFormElement)) return;
        if (!form.matches("#checkout-details-form")) return;

        const submitter = e.submitter instanceof HTMLElement ? e.submitter : null;
        const loadingBtn =
            submitter?.matches("[data-checkout-save-btn], #proceed-to-summary-btn")
                ? submitter
                : null;
        if (!loadingBtn) return;
        if (loadingBtn.classList.contains("btn-loading")) return;

        if (typeof window.btnLoading === "function") {
            window.btnLoading(loadingBtn);
        }
    });

    // Intercept "Review Order" submit for soft-nav (no white-flash full-page reload).
    document.addEventListener("submit", function (e) {
        const form = e.target;
        if (!form || !(form instanceof HTMLFormElement)) return;
        if (!form.matches("#checkout-details-form")) return;

        const submitter = e.submitter instanceof HTMLElement ? e.submitter : null;
        if (!submitter || !submitter.matches("#proceed-to-summary-btn")) return;

        const wrapper = document.getElementById("page-content-wrapper");
        if (!wrapper) return;

        e.preventDefault();

        const formData = new FormData(form);
        formData.set("checkout_action", "review_order");

        fetch(form.action, {
            method: "POST",
            headers: { "X-CSRFToken": getCSRFToken() },
            body: formData,
            redirect: "follow",
        })
            .then(function (res) {
                const finalUrl = res.url;
                return res.text().then(function (html) {
                    return { html: html, finalUrl: finalUrl };
                });
            })
            .then(function (result) {
                const parser = new DOMParser();
                const doc = parser.parseFromString(result.html, "text/html");
                const newContent = doc.getElementById("page-content");
                if (!newContent || !wrapper) return;

                wrapper.innerHTML = newContent.outerHTML;
                history.pushState({}, "", result.finalUrl);
                window.scrollTo({ top: 0, left: 0, behavior: "auto" });

                // Trigger htmx:afterSwap so site.js re-initialises the swapped content.
                wrapper.dispatchEvent(
                    new CustomEvent("htmx:afterSwap", {
                        bubbles: true,
                        detail: { target: wrapper },
                    })
                );

                if (typeof window.initSoftNavigation === "function") {
                    window.initSoftNavigation();
                }
            })
            .catch(function () {
                // Fallback: native form submit
                form.submit();
            });
    });

    // Apply/remove coupon (standard POST form submit)
    document.addEventListener("submit", function (e) {
        const form = e.target;
        if (!form || !(form instanceof HTMLFormElement)) return;
        if (!form.matches("[data-apply-coupon-form], [data-remove-coupon-form]")) return;

        e.preventDefault();

        const submitter = e.submitter instanceof HTMLElement ? e.submitter : null;
        const btn =
            submitter?.closest?.("[data-apply-coupon-btn], [data-remove-coupon-btn]") ||
            form.querySelector("[data-apply-coupon-btn]") ||
            form.querySelector("[data-remove-coupon-btn]");

        if (btn && btn.classList.contains("btn-loading")) return;
        if (btn && typeof window.btnLoading === "function") {
            window.btnLoading(btn);
        }

        fetch(form.action, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": getCSRFToken(),
            },
            body: new FormData(form),
        })
            .then((res) =>
                res
                    .json()
                    .catch(() => null)
                    .then((data) => ({ ok: res.ok, status: res.status, data }))
            )
            .then(({ ok, data }) => {
                if (!data) {
                    throw new Error("Invalid response");
                }

                const type = data.message_type || (ok ? "success" : "error");
                if (typeof window.showToast === "function" && data.message) {
                    window.showToast(data.message, type);
                }

                // Update totals
                if (data.cart_total !== undefined) {
                    document.querySelectorAll("[data-cart-total]").forEach((el) => {
                        el.textContent = data.cart_total;
                        el.dataset.price = data.cart_total;
                    });
                }
                if (data.cart_subtotal !== undefined) {
                    document.querySelectorAll("[data-cart-subtotal]").forEach((el) => {
                        el.textContent = data.cart_subtotal;
                        el.dataset.price = data.cart_subtotal;
                    });
                }
                if (data.discount_total !== undefined) {
                    document.querySelectorAll("[data-discount-total]").forEach((el) => {
                        el.textContent = `-${data.discount_total}`;
                        el.dataset.price = data.discount_total;
                    });

                    const discountValue = parseFloat(data.discount_total);
                    const hideRow = !Number.isFinite(discountValue) || discountValue <= 0;
                    document.querySelectorAll("[data-discount-row]").forEach((row) => {
                        row.classList.toggle("hidden", hideRow);
                    });
                }
                if (data.delivery_cost !== undefined) {
                    document.querySelectorAll("[data-delivery-cost]").forEach((el) => {
                        el.textContent = data.delivery_cost;
                        el.dataset.price = data.delivery_cost;
                    });
                }

                // Update promo code UI (no full reload)
                const couponCode = (data.coupon_code || "").trim();
                const display = document.querySelector("[data-coupon-code-display]");
                const removeForm = document.querySelector("[data-remove-coupon-form]");
                const applyForm = document.querySelector("[data-apply-coupon-form]");
                const input = applyForm?.querySelector("input[name='coupon_code']");
                const removeBtn = document.querySelector("[data-remove-coupon-btn]");

                if (display) {
                    display.textContent = couponCode;
                    display.classList.toggle("hidden", !couponCode);
                }
                if (removeForm) {
                    // Form is kept in the DOM; the Remove button is toggled to intentionally allow layout shift.
                }
                if (removeBtn) {
                    const hasCoupon = Boolean(couponCode);
                    removeBtn.disabled = !hasCoupon;
                    removeBtn.classList.toggle("hidden", !hasCoupon);
                }
                if (input) {
                    input.value = couponCode;
                }

                if (typeof window.formatPrices === "function") {
                    window.formatPrices();
                }

                return data;
            })
            .catch((err) => {
                console.error(err);
                if (typeof window.showToast === "function") {
                    window.showToast("Failed to apply promo code.", "error");
                }
            })
            .finally(() => {
                if (btn && typeof window.btnReset === "function") {
                    window.btnReset(btn);
                }
            });
    });

    // Keep cart UI in sync when browser restores history snapshots/back-forward cache.
    document.addEventListener("htmx:historyRestore", handleHistoryRestoreSync);

    window.addEventListener("pageshow", function (event) {
        if (!isBackForwardNavigation(event)) return;
        handleHistoryRestoreSync();
    });

    window.addEventListener("popstate", function () {
        handleHistoryRestoreSync();
    });


    return {
        addToCart,
        removeLine,
        syncState: syncCartStateFromServer,
        reinitCheckout: () => {
            updateProceedToSummaryDisabledState();
            updateCheckoutChoiceCardStates();
            initCheckoutCountryReload();
            initCartCountrySubmit();
        },
    };
})();
