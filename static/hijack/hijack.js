/**
 * Given function will be executed when DOM is ready. If DOM is already ready, function
 * will be executed immediately.
 *
 * @param {Function} fn - Function to be executed.
 * @param {object} context - Context to be used when executing function.
 * @returns {void}
 */
export function ready(fn, context) {
  context = context || document;
  if (context.readyState !== "loading") {
    fn();
  } else {
    context.addEventListener("DOMContentLoaded", fn);
  }
}

/**
 * Given function will be executed when DOM is ready and the element exists.
 *
 * @param {Function} fn - Function to be executed.
 * @param {string} query - Query selector to find element.
 * @returns {void}
 */
export function mount(fn, query) {
  ready(() => {
    document.querySelectorAll(query).forEach((element) => fn(element));
  });
}

/**
 * Hijack user session.
 *
 * @param {Event} event - Click event.
 * @returns {void}
 */
export function hijack(event) {
  event.preventDefault();
  event.stopPropagation();
  if (typeof event.stopImmediatePropagation === "function") {
    event.stopImmediatePropagation();
  }

  const element = event.currentTarget;
  const form = document.createElement("form");
  form.method = "POST";
  form.style.display = "none";
  form.action = element.dataset.hijackUrl;

  const target = element.dataset.hijackTarget;
  if (target === "_blank") {
    const popupWindow = window.open("about:blank", "_blank");
    if (popupWindow && !popupWindow.closed) {
      const popupName = `hijack_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      popupWindow.name = popupName;
      form.target = popupName;
    } else {
      form.target = "_blank";
    }
  } else if (target) {
    form.target = target;
  }

  const csrfTokenInput = document.createElement("input");
  csrfTokenInput.type = "hidden";
  csrfTokenInput.name = "csrfmiddlewaretoken";
  csrfTokenInput.value = document.querySelector(
    "input[name=csrfmiddlewaretoken]",
  ).value;
  form.appendChild(csrfTokenInput);

  const userPkInput = document.createElement("input");
  userPkInput.type = "hidden";
  userPkInput.name = "user_pk";
  userPkInput.value = element.dataset.hijackUser;
  form.appendChild(userPkInput);

  if (element.dataset.hijackNext) {
    const nextInput = document.createElement("input");
    nextInput.type = "hidden";
    nextInput.name = "next";
    nextInput.value = element.dataset.hijackNext;
    form.appendChild(nextInput);
  }

  document.body.appendChild(form);
  form.submit();
  setTimeout(() => form.remove(), 0);
}

document.addEventListener(
  "pointerdown",
  (event) => {
    const element = event.target.closest("[data-hijack-user]");
    if (!element) return;
    if (element.tagName === "A" && element.getAttribute("href")) return;

    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") {
      event.stopImmediatePropagation();
    }
  },
  true,
);

document.addEventListener(
  "click",
  (event) => {
    const element = event.target.closest("[data-hijack-user]");
    if (!element) return;
    if (element.tagName === "A" && element.getAttribute("href")) return;

    hijack({
      preventDefault: () => event.preventDefault(),
      stopPropagation: () => event.stopPropagation(),
      stopImmediatePropagation: () => event.stopImmediatePropagation(),
      currentTarget: element,
    });
  },
  true,
);
