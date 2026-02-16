
window.Cart = (function () {
    const INLINE_SPINNER_SVG =
        '<svg class="w-5 h-5 animate-spin text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';

    function setCheckoutInputsDisabled(disabled) {
        document
            .querySelectorAll('input[name="delivery-method"], input[name="payment-method"]')
            .forEach((el) => {
                el.disabled = disabled;
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

    function setProceedToSummaryLoading(loading) {
        const proceedBtn = document.querySelector(
            'a[href="/cart/summary/"][data-nav-loading-btn]'
        );
        if (!proceedBtn) return;
        if (loading) {
            if (typeof window.btnLoading === "function") {
                window.btnLoading(proceedBtn);
            } else {
                proceedBtn.classList.add("btn-loading");
            }
        } else {
            if (typeof window.btnReset === "function") {
                window.btnReset(proceedBtn);
            } else {
                proceedBtn.classList.remove("btn-loading");
            }
        }
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

    function updateCartSummary(data) {
        const totalEls = document.querySelectorAll('[data-cart-total]');
        const subtotalEls = document.querySelectorAll('[data-cart-subtotal]');
        const deliveryEls = document.querySelectorAll('[data-delivery-cost]');
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
            cartLinesNumber.forEach(el => {
                const label = el.dataset.labelItems || "items";
                const count = parseInt(data.lines_count, 10) || 0;

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
                const priceEls = lineEl.querySelectorAll("[data-price]");
                priceEls.forEach(priceEl => {
                    priceEl.dataset.price = data.line_subtotal;
                    priceEl.textContent = data.line_subtotal;
                });
                const input = lineEl.querySelector("[data-counter-input]");
                if (input && data.product_quantity !== undefined) {
                    input.value = data.product_quantity;
                }
            }
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

        const methodId = input.value;
        const form = input.closest("form");

        const hostLabel = input.closest("label");
        setCheckoutInputsDisabled(true);
        startInlineLoader(hostLabel);
        setProceedToSummaryLoading(true);

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
            if (!data.success) return;

            document.querySelectorAll("[data-cart-total]").forEach(el => {
                el.textContent = data.total;
                el.dataset.price = data.total;
            });
            document.querySelectorAll("[data-delivery-cost]").forEach(el => {
                el.textContent = data.delivery_cost;
                el.dataset.price = data.delivery_cost;
            });
            formatPrices()
        })
        .catch(console.error)
        .finally(() => {
            stopInlineLoader(hostLabel);
            setProceedToSummaryLoading(false);
            setCheckoutInputsDisabled(false);
        });
    });

    // Select payment method
    document.addEventListener("change", function (e) {
        const input = e.target;
        if (!input.matches('input[name="payment-method"]')) return;

        const paymentId = input.value;
        const form = input.closest("form");

        const hostLabel = input.closest("label");
        setCheckoutInputsDisabled(true);
        startInlineLoader(hostLabel);
        setProceedToSummaryLoading(true);

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
            if (!data.success) return;

            document.querySelectorAll("[data-cart-total]").forEach(el => {
                el.textContent = data.total;
                el.dataset.price = data.total;
            });

            document.querySelectorAll("[data-delivery-cost]").forEach(el => {
                el.textContent = data.delivery_cost;
                el.dataset.price = data.delivery_cost;
            });

            document.querySelectorAll("[data-payment-cost]").forEach(el => {
                el.textContent = data.payment_cost;
                el.dataset.price = data.payment_cost;
            });

            formatPrices()
        })
        .catch(console.error)
        .finally(() => {
            stopInlineLoader(hostLabel);
            setProceedToSummaryLoading(false);
            setCheckoutInputsDisabled(false);
        });
    });


    return {
        addToCart,
        removeLine
    };
})();
