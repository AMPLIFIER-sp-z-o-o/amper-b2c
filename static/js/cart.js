
window.Cart = (function () {
    function getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    }

    function updateCartSummary(data) {
        const totalEls = document.querySelectorAll('[data-cart-total]');
        const subtotalEls = document.querySelectorAll('[data-cart-subtotal]');
        const deliveryEls = document.querySelectorAll('[data-delivery-cost]');
        const cartLinesNumber =  document.querySelectorAll('[data-cart-lines-number]');
        const navCartLinesContainer = document.querySelector('#nav-cart-lines')
        if (!totalEls.length) return;
        if (data.updated_line_html) {
            const temp = document.createElement('div');
            temp.innerHTML = data.updated_line_html.trim();

            const newLine = temp.firstElementChild;
            const lineId = newLine.dataset.cartLineId;

            const existingLine = navCartLinesContainer.querySelector(
                `[data-cart-line-id="${lineId}"]`
            );

            if (existingLine) {
                existingLine.replaceWith(newLine);
                window.showToast(`Updated <strong>${data.product_name}</strong> in Cart`, 'success')

            } else {
                navCartLinesContainer.appendChild(newLine);
                window.showToast(`Added <strong>${data.product_name}</strong> to Cart`, 'success')
            }
        }
        if (data.removed_line_id) {
            document.querySelectorAll(
                `[data-cart-line-id="${data.removed_line_id}"]`
            ).forEach(el => el.remove());
            window.showToast(`Removed <strong>${data.product_name}</strong> from Cart`, 'success')
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
                el.textContent = data.cart_subtotal;
            });
            cartLinesNumber.forEach(el => {
                const label = el.dataset.labelItems || "items";

                el.dataset.lines_number = data.lines_count;
                el.textContent = `(${data.lines_count} ${label})`;
            });
        }

        if(data.line_id) {
            const cartPage = document.querySelector("#cart-page-lines");
            if (cartPage) {
            const lineEl = cartPage.querySelector(
            `[data-cart-line-id="${data.line_id}"]`
            );
            const priceEls = lineEl.querySelectorAll("[data-price]");
            priceEls.forEach(priceEl => {
                priceEl.dataset.price = data.line_subtotal;
                priceEl.textContent = data.line_subtotal;
            });
            const input = lineEl.querySelector("[data-counter-input]");
            if (input && data.product_quantity !== undefined) {
                input.value = data.product_quantity;
            }}
        }
        formatPrices()
    }

    function addToCart(productId, quantity = 1) {
        const cartId = localStorage.getItem("cart_id");

        const formData = new FormData();
        formData.append("product_id", productId);
        formData.append("quantity", quantity);

        if (cartId) {
        formData.append("cart_id", cartId);
        }

        fetch(window.ADD_TO_CART_URL, {
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
               
            }
        })
        .catch(console.error);
    }

    function removeLine(productId) {
        const formData = new FormData();
        formData.append("product_id", productId);

        fetch(window.REMOVE_FROM_CART_URL, {
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
            }
            })
            .catch(console.error);
    }

    // ADD TO CART
    document.addEventListener("click", function (e) {
        const btn = e.target.closest(".add-to-cart-btn");
        if (!btn) return;

        const productId = btn.dataset.productId;
        const quantity = parseInt(btn.dataset.quantity || "1", 10);

        addToCart(productId, quantity);
    });

    // REMOVE LINE
    document.addEventListener("click", function (e) {
        const btn = e.target.closest(".remove-cart-line");
        if (!btn) return;

        const productId = btn.dataset.productId;

        const row = btn.closest("[data-cart-line]");
        if (row) row.remove();

        removeLine(productId);
    });

    document.addEventListener("cart:updated", (e) => {
        updateCartSummary(e.detail);
    });

    // Disable negative values in product quantity input
    document.addEventListener("click", function(e) {
        const btn = e.target.closest("[data-action='decrement'], [data-action='increment']");
        if (!btn) return;

        const container = btn.closest("[data-counter]");
        if (!container) return;

        const input = container.querySelector("[data-counter-input]");

        if (!input) return;

        let value = parseInt(input.value.trim() || "0", 10);
        if (isNaN(value)) value = 0;

        if (btn.dataset.action === "decrement") {
            value = Math.max(0, value - 1);   
        } else {
            value = value + 1;
        }

        input.value = value;
    });

    document.addEventListener("mousedown", function(e) {
        const btn = e.target.closest("[data-action='increment'], [data-action='decrement']");
        if (!btn) return;

        const container = btn.closest("[data-counter]");
        const input = container?.querySelector("[data-counter-input]");
        if (!input) return;

        e.preventDefault();  
        input.focus();       
    });

    document.addEventListener("blur", function(e) {
        const input = e.target;
        if (!input.matches("[data-counter-input]")) return;

        const container = input.closest("[data-counter]");
        const productId = container.dataset.counter.split("-")[1];

        let value = parseInt(input.value || "0", 10);
        if (isNaN(value) || value < 0) value = 0;

        input.value = value;

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
        .catch(console.error);
    });

    return {
        addToCart,
        removeLine
    };
})();
