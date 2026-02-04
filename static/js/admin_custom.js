(function () {
  function initClickableRows() {
    console.log("Admin Clickable Rows initializing...");
    const resultTable = document.querySelector("#result_list");
    if (!resultTable) {
      console.log("No #result_list found");
      return;
    }

    resultTable.addEventListener("click", function (event) {
      const tr = event.target.closest("tr");
      if (!tr || !tr.parentElement || tr.parentElement.tagName !== "TBODY")
        return;

      const forbiddenTags = [
        "A",
        "INPUT",
        "BUTTON",
        "LABEL",
        "SELECT",
        "TEXTAREA",
        "I",
        "SVG",
        "PATH",
      ];
      // Classes used by Select2, Unfold selects, and other interactive widgets
      const forbiddenClasses = [
        "select2-container",
        "select2-dropdown",
        "select2-results",
        "select2-selection",
        "select2-search",
        "unfold-select",
      ];
      let target = event.target;

      while (target && target !== tr) {
        if (forbiddenTags.includes(target.tagName.toUpperCase())) return;
        // Check if element has any forbidden class
        if (target.classList && forbiddenClasses.some(cls => target.classList.contains(cls))) return;
        target = target.parentElement;
      }

      const link =
        tr.querySelector("th a") ||
        tr.querySelector("td.field-original_filename a") ||
        tr.querySelector("td a");

      if (link && link.href) {
        console.log("Row clicked, navigating to:", link.href);
        if (event.ctrlKey || event.metaKey) {
          window.open(link.href, "_blank");
        } else {
          window.location.href = link.href;
        }
      }
    });

    const rows = resultTable.querySelectorAll("tbody tr");
    rows.forEach((row) => {
      if (row.querySelector("a")) {
        row.style.cursor = "pointer";
      }
    });
    console.log("Admin Clickable Rows initialized for", rows.length, "rows");
  }

  document.addEventListener("DOMContentLoaded", initClickableRows);
  document.addEventListener("htmx:afterSwap", initClickableRows);

  if (document.readyState !== "loading") {
    initClickableRows();
  }
})();

// Auto-fill DynamicPage slug from name while typing
(function () {
  function slugify(value, maxLength) {
    if (typeof window.URLify === "function") {
      return window.URLify(value || "", maxLength, true);
    }
    return (value || "")
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, "")
      .trim()
      .replace(/[\s_-]+/g, "-")
      .slice(0, maxLength);
  }

  function initDynamicPageSlugAutofill() {
    if (!window.location.pathname.startsWith("/admin/web/dynamicpage/")) return;

    const nameInput = document.querySelector("#id_name");
    const slugInput = document.querySelector("#id_slug");
    if (!nameInput || !slugInput) return;

    const maxLength = parseInt(slugInput.getAttribute("maxlength"), 10) || 50;
    const initialSlug = slugInput.value || "";
    const initialName = nameInput.value || "";
    let manualSlug =
      initialSlug && initialSlug !== slugify(initialName, maxLength);

    slugInput.addEventListener("input", () => {
      if (slugInput.value) manualSlug = true;
    });

    nameInput.addEventListener("input", () => {
      if (manualSlug) return;
      slugInput.value = slugify(nameInput.value, maxLength);
    });
  }

  document.addEventListener("DOMContentLoaded", initDynamicPageSlugAutofill);
  document.addEventListener("htmx:afterSwap", initDynamicPageSlugAutofill);

  if (document.readyState !== "loading") {
    initDynamicPageSlugAutofill();
  }
})();

// Timezone detection and sync for admin
(function () {
  function detectAndSyncTimezone() {
    if (typeof Intl === "undefined" || !Intl.DateTimeFormat) return;

    try {
      const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (!browserTz) return;

      // Check if we already synced this timezone in this session
      const syncedTz = sessionStorage.getItem("amplifier_admin_tz_synced");
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
            sessionStorage.setItem("amplifier_admin_tz_synced", browserTz);
          }
        })
        .catch(() => {});
    } catch (e) {}
  }

  document.addEventListener("DOMContentLoaded", detectAndSyncTimezone);
  if (document.readyState !== "loading") {
    detectAndSyncTimezone();
  }
})();

// Price formatting using Intl.NumberFormat
(function () {
  const CURRENCY_LOCALES = {
    PLN: "pl-PL",
    EUR: "de-DE",
    USD: "en-US",
  };

  function formatAdminPrices() {
    const priceElements = document.querySelectorAll("[data-price]");
    if (!priceElements.length) return;

    priceElements.forEach((el) => {
      const value = parseFloat(el.dataset.price);
      const currency = el.dataset.currency || "PLN";
      const locale = CURRENCY_LOCALES[currency] || "pl-PL";
      if (isNaN(value)) return;

      try {
        el.textContent = new Intl.NumberFormat(locale, {
          style: "currency",
          currency: currency,
        }).format(value);
      } catch (e) {
        // Keep original content on error
      }
    });
  }

  document.addEventListener("DOMContentLoaded", formatAdminPrices);
  document.addEventListener("htmx:afterSwap", formatAdminPrices);

  if (document.readyState !== "loading") {
    formatAdminPrices();
  }
})();

// Image file input preview functionality
(function () {
  const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico'];

  function shouldSkipPreview(input) {
    if (!input) return false;
    if (input.closest('.tab-product-images')) return true;
    if (input.dataset && input.dataset.productImageUpload === 'true') return true;
    if (input.closest('[data-product-image-upload="true"]')) return true;
    if (input.closest('.product-image-upload')) return true;
    return false;
  }

  function isImageFile(file) {
    if (!file) return false;
    const ext = file.name.split('.').pop().toLowerCase();
    return imageExtensions.includes(ext) || file.type.startsWith('image/');
  }

  function createPreviewElement(input) {
    if (shouldSkipPreview(input)) return null;
    const previewId = `preview-${input.name.replace(/[^a-zA-Z0-9]/g, '-')}`;
    let preview = document.getElementById(previewId);
    
    if (!preview) {
      preview = document.createElement('div');
      preview.id = previewId;
      preview.className = 'file-input-preview mr-4';
      preview.style.cssText = 'display: none; flex-shrink: 0;';
      
      // Get the container and ensure it's flex for vertical/horizontal alignment
      const container = input.closest('.flex') || input.parentElement;
      if (container) {
        // Ensure container is flex and items are centered
        container.classList.add('flex', 'items-center', 'w-full');
        container.prepend(preview);
      }
    }
    
    return preview;
  }

  function showPreview(input, file) {
    if (shouldSkipPreview(input)) return;
    if (!isImageFile(file)) return;
    
    const preview = createPreviewElement(input);
    if (!preview) return;
    
    // Hide Unfold's default file info if it appears
    const container = input.closest('.flex') || input.parentElement;
    if (container) {
      setTimeout(() => {
        // Unfold often adds a span or div with file info after the label
        const siblings = Array.from(container.children);
        siblings.forEach(child => {
          if (child !== preview && !child.contains(input) && child.tagName !== 'LABEL') {
            const text = child.textContent || "";
            if (text.includes('KB') || text.includes('MB') || text.includes('GB') || text.toLowerCase().includes('ready')) {
              child.style.display = 'none';
            }
          }
        });
      }, 50);
    }
    
    const reader = new FileReader();
    reader.onload = function(e) {
      preview.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
          <div style="width: 64px; height: 64px; display: flex; align-items: center; justify-content: center; background: #fff; border-radius: 12px; border: 2px solid #f3f4f6; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); transition: all 0.2s; cursor: pointer;"
               onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 10px 15px -3px rgba(0, 0, 0, 0.1)';"
               onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 6px -1px rgba(0, 0, 0, 0.1)';"
               onclick="openFullscreen(this.querySelector('img'))">
            <img src="${e.target.result}" 
                 alt="${file.name}" 
                 style="width: 100%; height: 100%; object-fit: contain;" />
          </div>
          <div style="font-size: 10px; font-weight: 700; color: #6b7280; background: #f3f4f6; padding: 1px 6px; border-radius: 4px; line-height: 1.2;">
            ${formatFileSize(file.size)}
          </div>
        </div>
      `;
      preview.style.display = 'block';
    };
    reader.readAsDataURL(file);
  }

  function hidePreview(input) {
    if (shouldSkipPreview(input)) return;
    const previewId = `preview-${input.name.replace(/[^a-zA-Z0-9]/g, '-')}`;
    const preview = document.getElementById(previewId);
    if (preview) {
      preview.style.display = 'none';
      preview.innerHTML = '';
    }
  }

  function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function initFilePreview(input) {
    if (!input || input.dataset.previewInitialized) return;
    if (shouldSkipPreview(input)) return;
    input.dataset.previewInitialized = 'true';
    
    input.addEventListener('change', function() {
      const file = this.files && this.files[0];
      if (file) {
        showPreview(this, file);
      } else {
        hidePreview(this);
      }
    });
  }

  function initAllFilePreviews() {
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(initFilePreview);
  }

  // Initialize on page load and after dynamic content changes
  document.addEventListener('DOMContentLoaded', initAllFilePreviews);
  document.addEventListener('formset:added', initAllFilePreviews);
  document.addEventListener('htmx:afterSwap', initAllFilePreviews);
  
  // Also watch for new file inputs being added dynamically
  const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      mutation.addedNodes.forEach(function(node) {
        if (node.nodeType === 1) {
          const inputs = node.querySelectorAll ? node.querySelectorAll('input[type="file"]') : [];
          inputs.forEach(initFilePreview);
          if (node.tagName === 'INPUT' && node.type === 'file') {
            initFilePreview(node);
          }
        }
      });
    });
  });
  
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    document.addEventListener('DOMContentLoaded', function() {
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }
})();

function openFullscreen(imgElement) {
  if (!imgElement || !imgElement.src) return;

  const existingOverlay = document.getElementById("fullscreen-overlay");
  if (existingOverlay) {
    existingOverlay.remove();
  }

  const overlay = document.createElement("div");
  overlay.id = "fullscreen-overlay";
  overlay.setAttribute(
    "style",
    `
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    z-index: 2147483647 !important;
    background: rgba(0, 0, 0, 0.98) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 20px !important;
    opacity: 0;
    transition: opacity 0.3s ease;
    margin: 0 !important;
    border: none !important;
    box-sizing: border-box !important;
  `
  );

  overlay.innerHTML = `
    <button type="button" id="fullscreen-close" style="
      position: absolute !important;
      top: 20px !important;
      right: 20px !important;
      padding: 12px !important;
      background: rgba(255, 255, 255, 0.15) !important;
      border: none !important;
      border-radius: 50% !important;
      color: white !important;
      cursor: pointer !important;
      z-index: 10 !important;
      transition: background 0.2s !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      width: 48px !important;
      height: 48px !important;
    " onmouseover="this.style.background='rgba(255,255,255,0.25)'" onmouseout="this.style.background='rgba(255,255,255,0.15)'">
      <span class="material-symbols-outlined" style="font-size: 24px !important; color: white !important;">close</span>
    </button>
    <button type="button" id="fullscreen-download" style="
      position: absolute !important;
      top: 20px !important;
      right: 80px !important;
      padding: 12px !important;
      background: rgba(255, 255, 255, 0.15) !important;
      border: none !important;
      border-radius: 50% !important;
      color: white !important;
      cursor: pointer !important;
      z-index: 10 !important;
      transition: background 0.2s !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      width: 48px !important;
      height: 48px !important;
    " onmouseover="this.style.background='rgba(255,255,255,0.25)'" onmouseout="this.style.background='rgba(255,255,255,0.15)'">
      <span class="material-symbols-outlined" style="font-size: 24px !important; color: white !important;">download</span>
    </button>
    <div id="fullscreen-info" style="
      position: absolute !important;
      bottom: 20px !important;
      left: 50% !important;
      transform: translateX(-50%) !important;
      padding: 8px 16px !important;
      background: rgba(0, 0, 0, 0.6) !important;
      border-radius: 8px !important;
      color: white !important;
      font-size: 14px !important;
      white-space: nowrap !important;
    "></div>
    <img id="fullscreen-image" src="" alt="" style="
      max-width: 90% !important;
      max-height: 90% !important;
      object-fit: contain !important;
      user-select: none !important;
      border-radius: 8px !important;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5) !important;
    " draggable="false" />
  `;

  document.body.appendChild(overlay);

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) {
      closeFullscreen();
    }
  });

  document
    .getElementById("fullscreen-close")
    .addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      closeFullscreen();
    });

  document
    .getElementById("fullscreen-download")
    .addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const img = document.getElementById("fullscreen-image");
      if (img && img.src) {
        const link = document.createElement("a");
        link.href = img.src;
        link.download = img.alt || "image";
        link.target = "_blank";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    });

  function handleEscape(e) {
    if (e.key === "Escape") {
      closeFullscreen();
      document.removeEventListener("keydown", handleEscape);
    }
  }
  document.addEventListener("keydown", handleEscape);

  const fullscreenImg = document.getElementById("fullscreen-image");
  const infoEl = document.getElementById("fullscreen-info");
  fullscreenImg.src = imgElement.src;
  
  // Try to get filename: prefer data-filename, then alt, then extract from URL
  let fileName = imgElement.dataset.filename || imgElement.getAttribute("data-filename") || "";
  if (!fileName) {
    fileName = imgElement.alt || "";
  }
  if (!fileName && imgElement.src) {
    try {
      const url = new URL(imgElement.src, window.location.origin);
      let pathName = url.pathname.split('/').pop();
      // Decode URL encoding (e.g., %20 to space)
      pathName = decodeURIComponent(pathName);
      // Skip UUID-like filenames (e.g., 56fc36f5-3ecb-4916-aea1-9878a9839964.webp)
      const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[a-z]+$/i;
      if (!uuidPattern.test(pathName)) {
        fileName = pathName;
      }
    } catch (e) {
      fileName = "";
    }
  }
  
  fullscreenImg.alt = fileName;

  if (fileName) {
    infoEl.textContent = fileName;
    infoEl.style.display = "block";
  } else {
    infoEl.style.display = "none";
  }

  document.body.style.overflow = "hidden";

  requestAnimationFrame(() => {
    overlay.style.opacity = "1";
  });
}

function closeFullscreen() {
  const overlay = document.getElementById("fullscreen-overlay");
  if (overlay) {
    overlay.style.opacity = "0";
    setTimeout(() => {
      overlay.remove();
      document.body.style.overflow = "";
    }, 300);
  }
}

window.openFullscreen = openFullscreen;
window.closeFullscreen = closeFullscreen;

(function () {
  function cacheOptions(optionSelect) {
    if (!optionSelect || optionSelect.dataset.allOptions) return;

    const allOptions = [];
    let placeholderText = "---------";

    Array.from(optionSelect.options).forEach((opt) => {
      if (!opt.value) {
        placeholderText = opt.text || placeholderText;
        return;
      }
      allOptions.push({
        value: opt.value,
        text: opt.text,
        attributeId: opt.getAttribute("data-attribute-id") || "",
      });
    });

    optionSelect.dataset.allOptions = JSON.stringify(allOptions);
    optionSelect.dataset.placeholder = placeholderText;
  }

  function applyFilter(attributeSelect, optionSelect) {
    if (!attributeSelect || !optionSelect) return;

    const attributeId = attributeSelect.value;
    const allOptions = JSON.parse(optionSelect.dataset.allOptions || "[]");
    const placeholderText = optionSelect.dataset.placeholder || "---------";
    const currentValue = optionSelect.value;

    optionSelect.innerHTML = "";
    optionSelect.add(new Option(placeholderText, ""));

    const filtered = attributeId
      ? allOptions.filter((opt) => opt.attributeId === attributeId)
      : [];

    filtered.forEach((opt) => {
      optionSelect.add(new Option(opt.text, opt.value));
    });

    if (filtered.some((opt) => opt.value === currentValue)) {
      optionSelect.value = currentValue;
    } else {
      optionSelect.value = "";
    }
  }

  function initRow(row) {
    if (!row) return;
    const attributeSelect = row.querySelector('select[name$="-attribute"]');
    const optionSelect = row.querySelector('select[name$="-option"]');
    if (!attributeSelect || !optionSelect) return;

    cacheOptions(optionSelect);

    if (!attributeSelect.dataset.optionFilterInitialized) {
      attributeSelect.addEventListener("change", () => applyFilter(attributeSelect, optionSelect));
      attributeSelect.dataset.optionFilterInitialized = "true";
    }

    applyFilter(attributeSelect, optionSelect);
  }

  function initAttributeOptionFilters() {
    const inlineGroup = document.getElementById("attribute_values-group");
    if (!inlineGroup) return;

    const rows = inlineGroup.querySelectorAll(".inline-related, tr, .form-row");
    rows.forEach((row) => initRow(row));
  }

  document.addEventListener("DOMContentLoaded", initAttributeOptionFilters);
  document.addEventListener("formset:added", initAttributeOptionFilters);
  document.addEventListener("htmx:afterSwap", initAttributeOptionFilters);

  if (document.readyState !== "loading") {
    initAttributeOptionFilters();
  }
})();

(function () {
  let draftAutosaveInitialized = false;

  function isDraftEligiblePage() {
    if (!document.body) return false;
    if (!getChangeForm()) return false;
    return Boolean(parseAdminMeta());
  }

  function getChangeForm() {
    return (
      document.querySelector("form#change-form") ||
      document.querySelector("#content-main form") ||
      document.querySelector("form[action][method='post']")
    );
  }

  function parseAdminMeta() {
    const path = window.location.pathname;
    const match = path.match(/\/admin\/([^/]+)\/([^/]+)\/(add|\d+)(?:\/change)?\//);
    if (!match) return null;
    const appLabel = match[1];
    const modelName = match[2];
    const objectId = match[3] !== "add" ? match[3] : null;
    return { appLabel, modelName, objectId };
  }

  function getDraftToken() {
    const storageKey = `draft-token:${window.location.pathname}`;
    let token = sessionStorage.getItem(storageKey);
    if (!token) {
      token = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
      sessionStorage.setItem(storageKey, token);
    }
    return token;
  }

  function hasFormErrors() {
    return Boolean(document.querySelector(".errorlist, .errornote, .errors"));
  }

  function normalizeValue(value) {
    if (Array.isArray(value)) return value;
    if (value === "on") return true;
    return value;
  }

  function normalizeStyleValue(styleValue) {
    if (!styleValue) return "";
    const declarations = styleValue
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => {
        const parts = item.split(":");
        const prop = (parts.shift() || "").trim().toLowerCase();
        const val = parts.join(":").trim();
        if (!prop) return null;
        return [prop, val];
      })
      .filter(Boolean)
      .sort((a, b) => a[0].localeCompare(b[0]));

    return declarations.map(([prop, val]) => `${prop}:${val}`).join(";");
  }

  function normalizeClassValue(classValue) {
    if (!classValue) return "";
    return classValue
      .split(/\s+/)
      .filter(Boolean)
      .sort()
      .join(" ");
  }

  function normalizeHtmlValue(value) {
    if (typeof value !== "string") return value;
    const trimmed = value.trim();
    if (!trimmed) return value;

    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(trimmed, "text/html");
      const root = doc.body;
      const showElement = (window.NodeFilter && NodeFilter.SHOW_ELEMENT) || 1;
      const showText = (window.NodeFilter && NodeFilter.SHOW_TEXT) || 4;
      const walker = doc.createTreeWalker(root, showElement, null);

      let node = walker.currentNode;
      while (node) {
        const attributes = Array.from(node.attributes || []);
        if (attributes.length) {
          const normalized = attributes
            .map((attr) => {
              let normalizedValue = attr.value;
              if (attr.name === "style") {
                normalizedValue = normalizeStyleValue(normalizedValue);
              } else if (attr.name === "class") {
                normalizedValue = normalizeClassValue(normalizedValue);
              }
              return { name: attr.name, value: normalizedValue };
            })
            .sort((a, b) => a.name.localeCompare(b.name));

          attributes.forEach((attr) => node.removeAttribute(attr.name));
          normalized.forEach((attr) => {
            node.setAttribute(attr.name, attr.value);
          });
        }

        node = walker.nextNode();
      }

      const textWalker = doc.createTreeWalker(root, showText, null);
      let textNode = textWalker.nextNode();
      while (textNode) {
        const text = textNode.textContent || "";
        if (!text.trim() && /[\r\n\t]/.test(text)) {
          const toRemove = textNode;
          textNode = textWalker.nextNode();
          if (toRemove.parentNode) {
            toRemove.parentNode.removeChild(toRemove);
          }
          continue;
        }
        if (/[\r\n\t]/.test(text)) {
          const normalizedText = text.replace(/\s+/g, " ").trim();
          textNode.textContent = normalizedText;
        }
        textNode = textWalker.nextNode();
      }

      return root.innerHTML;
    } catch (error) {
      return value;
    }
  }

  function applyDraftNormalization(form, data) {
    if (!form) return data;
    const normalizeFields = form.querySelectorAll("[data-draft-normalize]");
    normalizeFields.forEach((field) => {
      if (!field.name || !(field.name in data)) return;
      const rule = field.dataset.draftNormalize;
      if (rule === "html") {
        data[field.name] = normalizeHtmlValue(String(data[field.name] ?? ""));
      }
    });
    return data;
  }

  function collectFormData(form) {
    const data = {};
    const formData = new FormData(form);

    for (const [name, value] of formData.entries()) {
      if (!name || name === "csrfmiddlewaretoken" || name.startsWith("_")) continue;
      if (data[name] === undefined) {
        data[name] = normalizeValue(value);
      } else if (Array.isArray(data[name])) {
        data[name].push(normalizeValue(value));
      } else {
        data[name] = [data[name], normalizeValue(value)];
      }
    }

    const checkboxes = form.querySelectorAll("input[type='checkbox']");
    checkboxes.forEach((checkbox) => {
      if (!checkbox.name || checkbox.name.startsWith("_")) return;
      if (data[checkbox.name] !== undefined) return;
      data[checkbox.name] = checkbox.checked;
    });

    return applyDraftNormalization(form, data);
  }

  function stableStringify(obj) {
    const keys = Object.keys(obj).sort();
    const normalized = {};
    keys.forEach((key) => {
      const value = obj[key];
      normalized[key] = value;
    });
    return JSON.stringify(normalized);
  }

  function getCsrfToken(form) {
    const input = form.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }

  function refreshDraftPreviewLinks() {
    const container = document.getElementById("draft-preview-links");
    if (!container) return;

    const url = container.dataset.previewLinksUrl;
    if (!url) return;

    const adminChangeUrl = window.location.pathname + window.location.search;
    const linksUrl = new URL(url, window.location.origin);
    linksUrl.searchParams.set("admin_change_url", adminChangeUrl);

    fetch(linksUrl.toString(), { credentials: "same-origin" })
      .then((response) => response.text())
      .then((html) => {
        container.innerHTML = html;
        const wrapper = document.getElementById("draft-preview-wrapper");
        if (!wrapper) return;
        const hasLinks = Boolean(container.querySelector(".draft-preview-link"));
        wrapper.classList.toggle("hidden", !hasLinks);
      })
      .catch(() => {});
  }

  function saveDraft(payload, csrfToken) {
    return fetch("/support/drafts/save/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    }).then((response) => {
      refreshDraftPreviewLinks();
      return response;
    });
  }

  function clearDraft(draftToken, csrfToken, options = {}) {
    if (!draftToken) return;
    const fetchOptions = {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({ draft_token: draftToken }),
      credentials: "same-origin",
    };
    if (options.keepalive) {
      fetchOptions.keepalive = true;
    }
    return fetch("/support/drafts/clear/", fetchOptions).then((response) => {
      refreshDraftPreviewLinks();
      return response;
    });
  }

  function initDraftAutosave() {
    if (draftAutosaveInitialized) return;
    if (!isDraftEligiblePage()) return;

    draftAutosaveInitialized = true;

    const form = getChangeForm();
    if (!form) return;

    const meta = parseAdminMeta();
    if (!meta) return;

    const draftToken = getDraftToken();
    console.log('[DraftAutosave] Draft token:', draftToken);
    const serializedKey = `draft-serialized:${window.location.pathname}`;
    const baselineKey = `draft-baseline:${window.location.pathname}`;
    const previousSerialized = sessionStorage.getItem(serializedKey);
    const csrfToken = getCsrfToken(form);
    const objectRepr = (document.querySelector("h1") || {}).textContent || "";
    const adminChangeUrl = window.location.pathname + window.location.search;
    const formAction = form.getAttribute("action") || window.location.href;

    const draftFileMap = {};

    const initialData = collectFormData(form);

    function serializeState(formData) {
      return stableStringify({ ...formData, __draft_files__: draftFileMap });
    }

    let initialSerialized = serializeState(initialData);
    sessionStorage.setItem(baselineKey, initialSerialized);
    let lastSerialized = initialSerialized;
    
    // Listen for baseline resync (e.g., from CKEditor after normalization)
    document.addEventListener("draft:resyncBaseline", () => {
      const currentData = collectFormData(form);
      initialSerialized = serializeState(currentData);
      lastSerialized = initialSerialized;
      sessionStorage.setItem(baselineKey, initialSerialized);
    });
    let pendingTimeout = null;

    const submittedTokenKey = "draft-submitted-token";
    const submittedToken = sessionStorage.getItem(submittedTokenKey);
    if (submittedToken && !hasFormErrors()) {
      clearDraft(submittedToken, csrfToken);
      sessionStorage.removeItem(submittedTokenKey);
    } else if (submittedToken && hasFormErrors()) {
      sessionStorage.removeItem(submittedTokenKey);
    }

    function scheduleSave(formData, serializedValue) {
      if (pendingTimeout) {
        clearTimeout(pendingTimeout);
      }
      pendingTimeout = setTimeout(() => {
        const payload = {
          app_label: meta.appLabel,
          model_name: meta.modelName,
          object_id: meta.objectId,
          draft_token: draftToken,
          object_repr: objectRepr.trim(),
          admin_change_url: adminChangeUrl,
          page_url: window.location.href,
          form_action: formAction,
          form_data: formData,
          temp_files: draftFileMap,
        };
        saveDraft(payload, csrfToken).then(() => {
          if (serializedValue) {
            sessionStorage.setItem(serializedKey, serializedValue);
          }
        });
      }, 900);
    }

    // Always clear any existing draft on page load if form is in initial state.
    // This handles the case where user made changes, then refreshed the page -
    // the form shows DB values but draft may still exist in session.
    clearDraft(draftToken, csrfToken);
    sessionStorage.removeItem(serializedKey);

    function handlePageHide() {
      // clearDraft(draftToken, csrfToken, { keepalive: true });
      // sessionStorage.removeItem(serializedKey);
    }

    window.addEventListener("pagehide", handlePageHide);

    function updateClearCheckboxes() {
      const clearCheckboxes = form.querySelectorAll("input[type='checkbox'][name$='-clear']");
      clearCheckboxes.forEach((checkbox) => {
        if (!checkbox.name) return;
        const fieldName = checkbox.name.replace(/-clear$/, "");
        if (checkbox.checked) {
          draftFileMap[fieldName] = null;
        }
      });
    }

    function handleChange() {
      updateClearCheckboxes();
      const currentData = collectFormData(form);
      const currentSerialized = serializeState(currentData);

      // Helper to strip all whitespace for loose comparison
      const stripWhitespace = (str) => str.replace(/\s+/g, '');

      // Check strict equality OR loose equality (ignoring whitespace differences mostly caused by HTML formatting)
      const isBackToInitial = currentSerialized === initialSerialized || stripWhitespace(currentSerialized) === stripWhitespace(initialSerialized);

      if (isBackToInitial) {
        if (currentSerialized !== lastSerialized) {
          lastSerialized = currentSerialized;
          clearDraft(draftToken, csrfToken);
          sessionStorage.removeItem(serializedKey);
        }
        return;
      }
      if (currentSerialized === lastSerialized) return;
      lastSerialized = currentSerialized;
      scheduleSave(currentData, currentSerialized);
    }

    function uploadDraftFile(input) {
      const file = input.files && input.files[0];
      const fieldName = input.name;
      if (!fieldName) return;

      if (!file) {
        if (draftFileMap[fieldName]) {
          draftFileMap[fieldName] = null;
          handleChange();
        }
        return;
      }

      const data = new FormData();
      data.append("file", file);
      data.append("draft_token", draftToken);
      data.append("field_name", fieldName);
      data.append("app_label", meta.appLabel);
      data.append("model_name", meta.modelName);
      if (meta.objectId) {
        data.append("object_id", meta.objectId);
      }
      data.append("object_repr", objectRepr.trim());
      data.append("admin_change_url", adminChangeUrl);

      fetch("/support/drafts/upload/", {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken,
        },
        body: data,
        credentials: "same-origin",
      })
        .then((response) => response.json())
        .then((result) => {
          if (result && result.file) {
            draftFileMap[fieldName] = result.file;
            handleChange();
          }
        })
        .catch(() => {});
    }

    const fileInputs = form.querySelectorAll("input[type='file']");
    fileInputs.forEach((input) => {
      input.addEventListener("change", () => uploadDraftFile(input));
    });

    form.addEventListener("input", handleChange);
    form.addEventListener("change", handleChange);
    form.addEventListener("submit", () => {
      sessionStorage.setItem(submittedTokenKey, draftToken);
    });

    // Hook into CKEditor changes - CKEditor doesn't fire native DOM events
    let ckEditorBaselineResynced = false;
    
    function hookCKEditorChanges() {
      if (!window.editors) return;
      
      let newlyHooked = false;
      
      Object.entries(window.editors).forEach(([id, editor]) => {
        if (editor._draftChangeHooked) return;
        editor._draftChangeHooked = true;
        newlyHooked = true;
        
        try {
          // First, sync current CKEditor content to textarea (captures normalized HTML)
          const textarea = document.getElementById(id);
          if (textarea) {
            textarea.value = editor.getData();
          }
          
          // Listen to CKEditor's model changes
          editor.model.document.on('change:data', () => {
            // Sync CKEditor content to textarea first
            if (textarea) {
              textarea.value = editor.getData();
            }
            // Then trigger draft change detection
            handleChange();
          });
          console.log('[DraftAutosave] Hooked CKEditor change listener for:', id);
        } catch (e) {
          console.warn('[DraftAutosave] Could not hook CKEditor changes for:', id, e);
        }
      });
      
      // After hooking editors, resync baseline to capture CKEditor's normalized HTML
      // This ensures the baseline matches CKEditor's output format
      if (newlyHooked && !ckEditorBaselineResynced) {
        ckEditorBaselineResynced = true;
        // Slight delay to ensure all editors have synced their content
        setTimeout(() => {
          document.dispatchEvent(new CustomEvent("draft:resyncBaseline"));
          console.log('[DraftAutosave] Baseline resynced after CKEditor initialization');
        }, 100);
      }
    }

    // Try to hook CKEditor changes periodically until all editors are found
    let ckCheckCount = 0;
    const ckCheckInterval = setInterval(() => {
      hookCKEditorChanges();
      ckCheckCount++;
      if (ckCheckCount > 30) { // Stop after 15 seconds
        clearInterval(ckCheckInterval);
      }
    }, 500);

    // Also hook when DOM changes (e.g., new inline editors added)
    const ckObserver = new MutationObserver(() => {
      setTimeout(hookCKEditorChanges, 200);
    });
    ckObserver.observe(document.body, { childList: true, subtree: true });
  }

  document.addEventListener("DOMContentLoaded", initDraftAutosave);
  document.addEventListener("DOMContentLoaded", refreshDraftPreviewLinks);

  // Refresh preview links on tab focus/visibility change
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshDraftPreviewLinks();
    }
  });
  window.addEventListener("focus", refreshDraftPreviewLinks);

  if (document.readyState !== "loading") {
    initDraftAutosave();
    refreshDraftPreviewLinks();
  }
})();

// Ensure submit buttons outside forms still submit reliably.
(function () {
  function bindExternalSubmitButtons() {
    const buttons = document.querySelectorAll('button[type="submit"][form]');

    buttons.forEach((btn) => {
      if (btn.dataset.externalSubmitBound) return;
      btn.dataset.externalSubmitBound = "true";

      btn.addEventListener("click", (event) => {
        const formId = btn.getAttribute("form");
        if (!formId) return;
        const form = document.getElementById(formId);
        if (!form) return;
        if (btn.closest("form") === form) return;

        // Some browsers fail to submit when the button is outside the form.
        event.preventDefault();
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit(btn);
          return;
        }

        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = btn.name || "_save";
        hidden.value = btn.value || "";
        form.appendChild(hidden);
        form.submit();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", bindExternalSubmitButtons);
  document.addEventListener("htmx:afterSwap", bindExternalSubmitButtons);

  if (document.readyState !== "loading") {
    bindExternalSubmitButtons();
  }
})();

// CKEditor Deferred Upload System
// Intercepts CKEditor image uploads to store as base64 temporarily,
// then uploads them on form submission
(function () {
  const UPLOAD_URL = '/ckeditor5/image_upload/';
  
  // Track all CKEditor instances and their pending images
  const pendingUploads = new Map(); // fieldName -> [{base64, file, element}]
  
  function getCsrfToken() {
    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }
  
  function dataURLtoBlob(dataURL) {
    const arr = dataURL.split(',');
    const mime = arr[0].match(/:(.*?);/)[1];
    const bstr = atob(arr[1]);
    let n = bstr.length;
    const u8arr = new Uint8Array(n);
    while (n--) {
      u8arr[n] = bstr.charCodeAt(n);
    }
    return new Blob([u8arr], { type: mime });
  }
  
  function generateFileName(mimeType) {
    const ext = mimeType.split('/')[1] || 'png';
    return `image_${Date.now()}_${Math.random().toString(36).substr(2, 9)}.${ext}`;
  }
  
  // Custom upload adapter that converts to base64 instead of uploading
  class Base64UploadAdapter {
    constructor(loader, fieldName) {
      this.loader = loader;
      this.fieldName = fieldName;
    }

    upload() {
      return this.loader.file.then(file => new Promise((resolve, reject) => {
        const reader = new FileReader();
        
        reader.onload = () => {
          const base64 = reader.result;
          
          // Store for later upload
          if (!pendingUploads.has(this.fieldName)) {
            pendingUploads.set(this.fieldName, []);
          }
          pendingUploads.get(this.fieldName).push({
            base64: base64,
            file: file,
            mimeType: file.type
          });
          
          // Return base64 as the image URL for now
          resolve({ default: base64 });
        };
        
        reader.onerror = () => {
          reject(reader.error);
        };
        
        reader.readAsDataURL(file);
      }));
    }

    abort() {
      // No-op for base64 adapter
    }
  }
  
  // Override the upload adapter for a specific editor
  function overrideEditorUploadAdapter(editor, fieldName) {
    try {
      const fileRepository = editor.plugins.get('FileRepository');
      if (fileRepository) {
        fileRepository.createUploadAdapter = (loader) => {
          return new Base64UploadAdapter(loader, fieldName);
        };
        console.log('[CKEditor Deferred Upload] Override successful for:', fieldName);
      }
    } catch (e) {
      console.warn('[CKEditor Deferred Upload] Could not override adapter:', e);
    }
  }
  
  // Hook into CKEditor creation
  function hookCKEditorCreation() {
    // Use the callback system provided by django-ckeditor-5
    if (typeof window.ckeditorRegisterCallback === 'function') {
      // Register callbacks for editors as they're created
      const originalCreateEditors = window.createEditors;
      
      // Watch for new editors via MutationObserver
      const observer = new MutationObserver((mutations) => {
        setTimeout(() => {
          if (window.editors) {
            Object.entries(window.editors).forEach(([id, editor]) => {
              if (!editor._deferredUploadHooked) {
                editor._deferredUploadHooked = true;
                overrideEditorUploadAdapter(editor, id);
              }
            });
          }
        }, 100);
      });
      
      observer.observe(document.body, { childList: true, subtree: true });
    }
    
    // Also hook into existing editors after DOM load
    function hookExistingEditors() {
      if (window.editors) {
        Object.entries(window.editors).forEach(([id, editor]) => {
          if (!editor._deferredUploadHooked) {
            editor._deferredUploadHooked = true;
            overrideEditorUploadAdapter(editor, id);
          }
        });
      }
    }
    
    // Check periodically for new editors (fallback)
    let checkCount = 0;
    const checkInterval = setInterval(() => {
      hookExistingEditors();
      checkCount++;
      if (checkCount > 20) { // Stop after 10 seconds
        clearInterval(checkInterval);
      }
    }, 500);
  }
  
  // Upload all pending base64 images and update the content
  async function uploadPendingImages() {
    const csrfToken = getCsrfToken();
    const uploadPromises = [];
    
    // Find all CKEditor textareas with base64 images
    const textareas = document.querySelectorAll('textarea');
    
    for (const textarea of textareas) {
      let content = textarea.value;
      if (!content) continue;
      
      // Find all base64 images in the content
      const base64Pattern = /src="(data:image\/[^;]+;base64,[^"]+)"/g;
      let match;
      const replacements = [];
      
      while ((match = base64Pattern.exec(content)) !== null) {
        const base64 = match[1];
        replacements.push({
          original: base64,
          placeholder: `__UPLOADING_${replacements.length}__`
        });
      }
      
      if (replacements.length === 0) continue;
      
      // Upload each image
      for (const replacement of replacements) {
        try {
          const blob = dataURLtoBlob(replacement.original);
          const fileName = generateFileName(blob.type);
          const formData = new FormData();
          formData.append('upload', blob, fileName);
          
          const response = await fetch(UPLOAD_URL, {
            method: 'POST',
            headers: {
              'X-CSRFToken': csrfToken
            },
            body: formData,
            credentials: 'same-origin'
          });
          
          if (response.ok) {
            const data = await response.json();
            if (data.url) {
              replacement.uploadedUrl = data.url;
            }
          }
        } catch (error) {
          console.error('Failed to upload image:', error);
          // Keep the base64 if upload fails
          replacement.uploadedUrl = null;
        }
      }
      
      // Replace base64 with uploaded URLs
      for (const replacement of replacements) {
        if (replacement.uploadedUrl) {
          content = content.replace(
            `src="${replacement.original}"`,
            `src="${replacement.uploadedUrl}"`
          );
        }
      }
      
      // Update the textarea value
      textarea.value = content;
      
      // Also update the CKEditor instance if it exists
      const wrapper = textarea.closest('.django-ckeditor-5');
      if (wrapper) {
        const editorElement = wrapper.querySelector('.ck-editor__editable');
        if (editorElement && editorElement.ckeditorInstance) {
          editorElement.ckeditorInstance.setData(content);
        }
      }
    }
  }
  
  // Intercept form submission
  function initFormSubmitInterceptor() {
    const forms = document.querySelectorAll('form');
    
    for (const form of forms) {
      if (form.dataset.ckUploadIntercepted) continue;
      form.dataset.ckUploadIntercepted = 'true';
      
      form.addEventListener('submit', async function(e) {
        // Check if there are any base64 images in CKEditor fields
        const textareas = form.querySelectorAll('textarea');
        let hasBase64Images = false;
        
        for (const textarea of textareas) {
          if (textarea.value && textarea.value.includes('data:image/')) {
            hasBase64Images = true;
            break;
          }
        }
        
        if (!hasBase64Images) return;
        
        // Prevent default submission
        e.preventDefault();
        
        // Show loading indicator
        const submitBtn = form.querySelector('button[type="submit"][name="_save"], button[type="submit"]:last-child');
        const originalText = submitBtn ? submitBtn.innerHTML : '';
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.innerHTML = '<span class="animate-pulse">Uploading images...</span>';
        }
        
        try {
          // Upload all pending images
          await uploadPendingImages();
          
          // Now submit the form normally
          // Remove the interceptor temporarily to avoid infinite loop
          form.dataset.ckUploadIntercepted = '';
          
          // Use a hidden submit button to preserve the original button's name/value
          const hiddenSubmit = document.createElement('input');
          hiddenSubmit.type = 'hidden';
          if (submitBtn && submitBtn.name) {
            hiddenSubmit.name = submitBtn.name;
            hiddenSubmit.value = submitBtn.value || '';
          } else {
            hiddenSubmit.name = '_save';
            hiddenSubmit.value = '';
          }
          form.appendChild(hiddenSubmit);
          form.submit();
        } catch (error) {
          console.error('Error uploading images:', error);
          // Restore button
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
          }
          form.dataset.ckUploadIntercepted = 'true';
          alert('Failed to upload some images. Please try again.');
        }
      });
    }
  }
  
  // Initialize on page load
  function init() {
    hookCKEditorCreation();
    initFormSubmitInterceptor();
  }
  
  document.addEventListener('DOMContentLoaded', init);
  if (document.readyState !== 'loading') {
    init();
  }
  
  // Re-init when new content is added (e.g., inline formsets)
  document.addEventListener('formset:added', initFormSubmitInterceptor);
  document.addEventListener('htmx:afterSwap', initFormSubmitInterceptor);
})();

// ProductImageInline: preview + alt text autofill + file action tooltips
(function () {
  const INLINE_CLASS = "tab-product-images";
  const SINGLE_ATTR = "data-product-image-upload";

  function filenameToAlt(filename) {
    if (!filename) return "";
    const base = filename
      .replace(/^.*[\\/]/, "")
      .replace(/\.[^/.]+$/, "")
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!base) return "";
    return base.charAt(0).toUpperCase() + base.slice(1);
  }

  function ensureAltAutofill(row, altText) {
    const altInput = row.querySelector('input[name$="-alt_text"]');
    if (!altInput) return;

    if (!altInput.dataset.autofillBound) {
      altInput.dataset.autofillBound = "true";
      altInput.addEventListener("input", () => {
        altInput.dataset.autofilled = "";
      });
    }

    if (!altInput.value || altInput.dataset.autofilled === "true") {
      altInput.value = altText;
      altInput.dataset.autofilled = "true";
    }
  }

  function updateInlinePreview(input) {
    const file = input.files && input.files[0];
    if (!file) return;

    const row = input.closest("tr") || input.closest(".inline-related, .form-row");
    if (!row) return;

    const altText = filenameToAlt(file.name) || file.name;
    ensureAltAutofill(row, altText);

    const reader = new FileReader();
    reader.onload = function (e) {
      input.dataset.previewDataUrl = e.target.result;
      input.dataset.previewFileName = file.name;
      updateInlineImageChip(row, e.target.result, altText, file.name);
      updateFilenameDisplay(row, file.name);
      syncRowFileActions(row);
    };
    reader.readAsDataURL(file);
  }

  function updateFilenameDisplay(row, filename) {
    const input = row.querySelector('td.field-image input[type="text"][aria-label="Choose file to upload"]');
    if (!input) return;
    if (!filename) return;
    input.value = filename;
    input.title = filename;

    const label = input.closest('label');
    if (label) {
      label.title = filename;
      const overlay = label.querySelector('span');
      if (overlay) {
        overlay.title = filename;
      }
    }

    const container = row.querySelector('td.field-image .bg-white.border');
    if (container) {
      container.title = filename;
      container.setAttribute("title", filename);
      container.setAttribute("aria-label", filename);
    }
  }

  function updateInlineImageChip(row, url, altText, filename) {
    if (!row) return;
    const fieldCell = row.querySelector("td.field-image");
    if (!fieldCell) return;

    const container = fieldCell.querySelector(".bg-white.border");
    if (!container) return;

    let chip = container.querySelector(".product-image-inline-chip");
    if (!chip) {
      chip = document.createElement("div");
      chip.className = "product-image-inline-chip";
      container.insertBefore(chip, container.firstChild);
    }

    chip.innerHTML = "";
    if (!url) {
      chip.classList.add("is-empty");
      chip.title = "No image selected";
      chip.innerHTML = '<span class="material-symbols-outlined">image</span>';
      return;
    }

    chip.classList.remove("is-empty");
    chip.title = filename || "";

    const img = document.createElement("img");
    img.src = url;
    img.alt = altText || filename || "";
    img.title = filename || "";
    img.dataset.filename = filename || "";
    img.style.cursor = "pointer";
    img.addEventListener("click", function(e) {
      e.preventDefault();
      e.stopPropagation();
      openFullscreen(this);
    });
    chip.appendChild(img);
  }

  function getSingleUploadContainer(input) {
    if (!input) return null;
    const closestWrapper =
      input.closest(".bg-white.border") || input.closest(".form-row") || input.parentElement;
    const container =
      closestWrapper && closestWrapper.classList && closestWrapper.classList.contains("bg-white") && closestWrapper.classList.contains("border")
        ? closestWrapper
        : closestWrapper && closestWrapper.querySelector
          ? closestWrapper.querySelector(".bg-white.border") || closestWrapper
          : closestWrapper;

    if (container && container.classList) {
      container.classList.add("product-image-upload");
    }
    return container;
  }

  function updateSingleImageChip(container, url, altText, filename) {
    if (!container) return;

    let chip = container.querySelector(".product-image-inline-chip");
    if (!chip) {
      chip = document.createElement("div");
      chip.className = "product-image-inline-chip";
      container.insertBefore(chip, container.firstChild);
    }

    chip.innerHTML = "";
    if (!url) {
      chip.classList.add("is-empty");
      chip.title = "No image selected";
      chip.innerHTML = '<span class="material-symbols-outlined">image</span>';
      return;
    }

    chip.classList.remove("is-empty");
    chip.title = filename || "";

    const img = document.createElement("img");
    img.src = url;
    img.alt = altText || filename || "";
    img.title = filename || "";
    img.dataset.filename = filename || "";
    img.style.cursor = "pointer";
    img.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      openFullscreen(this);
    });
    chip.appendChild(img);
  }

  function updateSingleFilenameDisplay(container, filename) {
    if (!container) return;
    if (!filename) return;
    const input = container.querySelector('input[type="text"][aria-label="Choose file to upload"]');
    if (!input) return;

    input.value = filename;
    input.title = filename;

    const label = input.closest("label");
    if (label) {
      label.title = filename;
      const overlay = label.querySelector("span");
      if (overlay) {
        overlay.title = filename;
      }
    }

    container.title = filename;
    container.setAttribute("title", filename);
    container.setAttribute("aria-label", filename);
  }

  function isDataUrl(value) {
    return typeof value === "string" && value.startsWith("data:");
  }

  function getFileUrl(fieldCell) {
    if (!fieldCell) return "";
    
    // PRIORITY: Check if there's a pending file upload (new file selected by user)
    // This should take precedence over existing saved file URLs
    const fileInput = fieldCell.querySelector('input[type="file"]');
    if (fileInput) {
      // If user selected a new file, use the preview data URL
      if (fileInput.dataset.previewDataUrl) {
        return fileInput.dataset.previewDataUrl;
      }
      // If file input has files but no previewDataUrl yet, return empty to avoid showing old image
      if (fileInput.files && fileInput.files.length > 0) {
        return "";
      }
    }
    
    // No pending upload - check for existing saved file
    const previewLink = fieldCell.querySelector('a[style*="background-image"]');
    if (previewLink && previewLink.href) return previewLink.href;

    const textInput = fieldCell.querySelector('input[type="text"][aria-label="Choose file to upload"]');
    const placeholder = "Choose file to upload";
    let value = textInput && textInput.value ? textInput.value.trim() : "";
    if (!value || value === placeholder) {
      value = "";
    }
    if (value && (value.startsWith("/") || value.startsWith("http") || value.startsWith("data:"))) {
      return value;
    }

    return "";
  }

  function getOpenUrl(fieldCell) {
    const url = getFileUrl(fieldCell);
    if (!url || isDataUrl(url)) return "";
    return url;
  }

  /**
   * Get the direct file URL for opening in new tab.
   * For S3, the presigned URL already includes response-content-disposition=inline.
   */
  function getDirectFileUrl(fieldCell) {
    return getFileUrl(fieldCell);
  }

  function getFileNameFromUrl(value, fieldCell) {
    if (!value) return "";
    if (value.startsWith("data:")) {
      const fileInput = fieldCell ? fieldCell.querySelector('input[type="file"]') : null;
      return fileInput ? fileInput.dataset.previewFileName || "" : "";
    }
    try {
      const url = new URL(value, window.location.origin);
      const name = url.pathname.split("/").pop() || "";
      return decodeURIComponent(name);
    } catch (e) {
      return value.split("/").pop() || value;
    }
  }

  function ensureOpenAction(fieldCell) {
    if (!fieldCell) return;
    let actionContainer = fieldCell.querySelector("div.flex.flex-none.items-center");
    if (!actionContainer && fieldCell.closest) {
      const wrapper =
        fieldCell.closest(".form-row") ||
        fieldCell.closest(".field-box") ||
        fieldCell.closest(".field") ||
        fieldCell.parentElement;
      actionContainer = wrapper ? wrapper.querySelector("div.flex.flex-none.items-center") : null;
    }
    if (!actionContainer) return;

    // Get full file URL (including base64 for unsaved files)
    const fullFileUrl = getFileUrl(fieldCell);
    const isBase64 = isDataUrl(fullFileUrl);
    let openBtn = actionContainer.querySelector(".js-open-file");

    if (!fullFileUrl) {
      if (openBtn) openBtn.remove();
      return;
    }

    if (!openBtn) {
      // Use button for base64, link for real URLs
      if (isBase64) {
        openBtn = document.createElement("button");
        openBtn.type = "button";
      } else {
        openBtn = document.createElement("a");
        openBtn.target = "_blank";
        openBtn.rel = "noopener";
      }
      openBtn.className =
        "border-r border-base-200 cursor-pointer text-base-400 px-3 hover:text-base-700 " +
        "dark:border-base-700 dark:text-base-500 dark:hover:text-base-200 js-open-file";
      openBtn.innerHTML = '<span class="material-symbols-outlined">open_in_new</span>';
      openBtn.title = isBase64 ? "Preview image (not yet saved)" : "Open in new tab";

      const uploadLabel = actionContainer.querySelector("label[for]");
      if (uploadLabel) {
        actionContainer.insertBefore(openBtn, uploadLabel);
      } else {
        actionContainer.appendChild(openBtn);
      }
    } else {
      // Update existing button - might need to switch from link to button or vice versa
      const currentIsLink = openBtn.tagName === "A";
      if (isBase64 && currentIsLink) {
        // Replace link with button
        const newBtn = document.createElement("button");
        newBtn.type = "button";
        newBtn.className = openBtn.className;
        newBtn.innerHTML = openBtn.innerHTML;
        newBtn.title = "Preview image (not yet saved)";
        openBtn.replaceWith(newBtn);
        openBtn = newBtn;
      } else if (!isBase64 && !currentIsLink) {
        // Replace button with link
        const newLink = document.createElement("a");
        newLink.target = "_blank";
        newLink.rel = "noopener";
        newLink.className = openBtn.className;
        newLink.innerHTML = openBtn.innerHTML;
        newLink.title = "Open in new tab";
        openBtn.replaceWith(newLink);
        openBtn = newLink;
      }
    }

    if (isBase64) {
      // For base64, open fullscreen on click
      openBtn.onclick = function(e) {
        e.preventDefault();
        e.stopPropagation();
        const chip = fieldCell.querySelector(".product-image-inline-chip img");
        if (chip) {
          openFullscreen(chip);
        } else {
          // Fallback: create temp image and show fullscreen
          const tempImg = document.createElement("img");
          tempImg.src = fullFileUrl;
          const fileInput = fieldCell.querySelector('input[type="file"]');
          tempImg.alt = fileInput ? (fileInput.dataset.previewFileName || "Preview") : "Preview";
          openFullscreen(tempImg);
        }
      };
      openBtn.removeAttribute("href");
    } else {
      // Use direct URL - S3 presigned URLs already have response-content-disposition=inline
      openBtn.href = fullFileUrl;
      openBtn.onclick = null;
    }
  }

  function syncRowFileActions(row) {
    if (!row) return;
    const fieldCell = row.querySelector("td.field-image");
    if (!fieldCell) return;
    ensureOpenAction(fieldCell);

    const fileUrl = getFileUrl(fieldCell);
    const fileName = getFileNameFromUrl(fileUrl, fieldCell);
    updateInlineImageChip(row, fileUrl, filenameToAlt(fileName), fileName);
    if (fileUrl) {
      updateFilenameDisplay(row, fileName);
    }
  }

  function syncSingleFileActions(input) {
    const container = getSingleUploadContainer(input);
    if (!container) return;

    ensureOpenAction(container);

    const fileUrl = getFileUrl(container);
    const fileName = getFileNameFromUrl(fileUrl, container);
    updateSingleImageChip(container, fileUrl, filenameToAlt(fileName), fileName);
    if (fileUrl) {
      updateSingleFilenameDisplay(container, fileName);
    }
  }

  function initProductImageSinglePreview(root = document) {
    const inputs = root.querySelectorAll(`input[type="file"][${SINGLE_ATTR}="true"]`);
    inputs.forEach((input) => {
      if (input.dataset.singlePreviewAttached) return;
      input.dataset.singlePreviewAttached = "true";

      const container = getSingleUploadContainer(input);
      if (container) {
        const legacyPreviews = container.querySelectorAll('.file-input-preview');
        legacyPreviews.forEach((preview) => preview.remove());
      }

      input.addEventListener("change", () => {
        const file = input.files && input.files[0];
        if (!file) {
          syncSingleFileActions(input);
          return;
        }

        const altText = filenameToAlt(file.name) || file.name;
        const reader = new FileReader();
        reader.onload = function (e) {
          input.dataset.previewDataUrl = e.target.result;
          input.dataset.previewFileName = file.name;
          const target = getSingleUploadContainer(input);
          updateSingleImageChip(target, e.target.result, altText, file.name);
          updateSingleFilenameDisplay(target, file.name);
          ensureOpenAction(target);
        };
        reader.readAsDataURL(file);
      });

      syncSingleFileActions(input);
    });
  }

  function initProductImageInlinePreview(root = document) {
    const inlineGroup = root.querySelector(`.${INLINE_CLASS}`);
    if (!inlineGroup) return;

    const legacyPreviews = inlineGroup.querySelectorAll('.file-input-preview');
    legacyPreviews.forEach((preview) => preview.remove());

    const inputs = inlineGroup.querySelectorAll('input[type="file"]');
    inputs.forEach((input) => {
      if (input.dataset.inlinePreviewListenerAttached) return;
      input.dataset.inlinePreviewListenerAttached = "true";
      input.dataset.inlinePreviewAttached = "true";
      input.addEventListener("change", () => updateInlinePreview(input));
    });

    const rows = inlineGroup.querySelectorAll("tbody tr.form-row");
    rows.forEach((row) => syncRowFileActions(row));
  }

  function scheduleRowSync() {
    setTimeout(() => {
      const inlineGroup = document.querySelector(`.${INLINE_CLASS}`);
      if (!inlineGroup) return;
      const rows = inlineGroup.querySelectorAll("tbody tr.form-row");
      rows.forEach((row) => syncRowFileActions(row));
      removeInlineDownloadActions();
    }, 50);
  }

  function setIconTooltip(icon, title) {
    const target = icon.closest("a, button");
    if (!target) return;
    if (!target.getAttribute("title")) {
      target.setAttribute("title", title);
    }
    if (!target.getAttribute("aria-label")) {
      target.setAttribute("aria-label", title);
    }
  }

  function removeInlineDownloadActions(root = document) {
    const targets = root.querySelectorAll(`.${INLINE_CLASS}, .product-image-upload`);
    if (!targets.length) return;

    targets.forEach((targetRoot) => {
      const icons = targetRoot.querySelectorAll("span.material-symbols-outlined");
      icons.forEach((icon) => {
        const text = (icon.textContent || "").trim();
        if (text !== "download") return;
        const target = icon.closest("a, button");
        if (target) {
          target.remove();
        } else {
          icon.remove();
        }
      });
    });
  }

  function initFileActionTooltips(root = document) {
    const icons = root.querySelectorAll("span.material-symbols-outlined");
    icons.forEach((icon) => {
      const text = (icon.textContent || "").trim();
      if (text === "download") {
        setIconTooltip(icon, "Download file");
      }
      if (text === "open_in_new" || text === "open_in_browser" || text === "launch") {
        setIconTooltip(icon, "Open in new tab");
      }
    });
  }

  function initAll() {
    initProductImageInlinePreview();
    initProductImageSinglePreview();
    removeInlineDownloadActions();
    initFileActionTooltips();
    scheduleRowSync();
  }

  document.addEventListener("DOMContentLoaded", initAll);
  document.addEventListener("formset:added", initAll);
  document.addEventListener("htmx:afterSwap", initAll);
  if (document.readyState !== "loading") {
    initAll();
  }
})();

// Immediate save for Boolean toggles in the changelist (list_editable)
(function () {
  function initChangelistToggles() {
    const changelistForm = document.getElementById("changelist-form");
    if (!changelistForm) return;

    // Target checkboxes that are part of list_editable (their name starts with "form-")
    // and are used for activation (is_active, is_enabled).
    // Using immediate save provides a better UX for toggle switches in list view.
    const toggles = changelistForm.querySelectorAll('input[type="checkbox"][name^="form-"][name$="-is_active"], input[type="checkbox"][name^="form-"][name$="-is_enabled"]');
    
    toggles.forEach((toggle) => {
      if (toggle.dataset.immediateSaveBound) return;
      toggle.dataset.immediateSaveBound = "true";

      toggle.addEventListener("change", function () {
        // Find the save button (might be outside the form in Unfold)
        const saveBtn = document.querySelector(`button[name="_save"][form="${changelistForm.id}"], input[name="_save"][form="${changelistForm.id}"]`) || 
                       changelistForm.querySelector('button[name="_save"], input[name="_save"]');
        
        if (saveBtn) {
          // Provide visual feedback that saving is in progress
          const container = toggle.closest("label") || toggle.parentElement;
          if (container) {
            container.style.opacity = "0.5";
            container.style.pointerEvents = "none";
          }
          
          // Submit the form by clicking the save button
          saveBtn.click();
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", initChangelistToggles);
  document.addEventListener("htmx:afterSwap", initChangelistToggles);

  if (document.readyState !== "loading") {
    initChangelistToggles();
  }
})();
