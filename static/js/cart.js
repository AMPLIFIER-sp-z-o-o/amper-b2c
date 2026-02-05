window.Cart = (function () {

    function getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    }

    function updateCartSummary(data) {
        const totalEl = document.querySelector('[data-cart-total]');
        if (!totalEl) return;

        if (data.cart_total !== undefined) {
            totalEl.dataset.price = data.cart_total;
            totalEl.textContent = data.cart_total; 
            window.formatPrices();                 
        }
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

    function removeLine(lineId) {
        const formData = new FormData();
        formData.append("line_id", lineId);

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
                updateCartSummary(data);

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

        const lineId = btn.dataset.lineId;

        const row = btn.closest("[data-cart-line]");
        if (row) row.remove();

        removeLine(lineId);
    });

    return {
        addToCart,
        removeLine
    };
})();
