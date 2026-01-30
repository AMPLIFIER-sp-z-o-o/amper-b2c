(function () {
  "use strict";

  // Global references to Monaco editor instances
  window.monacoEditors = {
    html: null,
    css: null,
    js: null
  };

  /**
   * Monaco Editor Configuration
   */
  const MONACO_CDN = "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs";
  
  const EDITOR_DEFAULTS = {
    theme: "vs-dark",
    automaticLayout: true,
    minimap: { enabled: false },
    fontSize: 13,
    lineNumbers: "on",
    scrollBeyondLastLine: false,
    wordWrap: "on",
    tabSize: 2,
    insertSpaces: true,
    folding: true,
    lineDecorationsWidth: 8,
    lineNumbersMinChars: 3,
    formatOnPaste: true,
    formatOnType: true,
    bracketPairColorization: { enabled: true },
    autoClosingBrackets: "always",
    autoClosingQuotes: "always",
    fixedOverflowWidgets: true
  };

  /**
   * SVG Icons
   */
  const ICONS = {
    format: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="21" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="3" y2="18"/></svg>`,
    fullscreen: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`,
    exitFullscreen: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>`,
    popup: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/></svg>`,
    newTab: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`,
    refresh: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="m3.5 9a9 9 0 0 1 14.8-3.4L23 10M1 14l4.6 4.6A9 9 0 0 0 20.5 15"/></svg>`,
    upload: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/></svg>`,
    close: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    openAll: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`
  };

  /**
   * Create a resizable Monaco editor
   */
  function createEditor(container, language, initialValue, options = {}) {
    const mergedOptions = {
      ...EDITOR_DEFAULTS,
      ...options,
      value: initialValue || "",
      language: language
    };

    const editor = monaco.editor.create(container, mergedOptions);
    
    // Store global reference
    window.monacoEditors[language] = editor;
    
    return editor;
  }

  /**
   * Create editor container with actions
   */
  function createEditorContainer(fieldName, label, height = 250) {
    const iconClass = fieldName === "html" ? "html" : fieldName === "css" ? "css" : "js";
    
    const container = document.createElement("div");
    container.className = "monaco-editor-wrapper";
    container.id = `monaco-${fieldName}-wrapper`;
    
    container.innerHTML = `
      <div class="monaco-editor-header">
        <span class="monaco-editor-label">
          <span class="monaco-editor-label-icon ${iconClass}"></span>
          ${label}
        </span>
        <div class="monaco-editor-actions">
          <button type="button" class="monaco-btn monaco-btn-format" title="Format code">${ICONS.format}</button>
          <button type="button" class="monaco-btn monaco-btn-popup" title="Open in popup">${ICONS.popup}</button>
          <button type="button" class="monaco-btn monaco-btn-newtab" title="Open in new tab">${ICONS.newTab}</button>
          <button type="button" class="monaco-btn monaco-btn-fullscreen" title="Fullscreen">${ICONS.fullscreen}</button>
        </div>
      </div>
      <div class="monaco-editor-container" id="monaco-${fieldName}-editor" style="height: ${height}px;"></div>
    `;
    
    return container;
  }

  /**
   * Setup unified resize functionality for all editors
   */
  function setupUnifiedResizeHandle(handle, editorInstances) {
    let isResizing = false;
    let startY = 0;
    let startHeights = [];
    
    // Get all editor containers
    const editorContainers = [
      document.getElementById("monaco-html-editor"),
      document.getElementById("monaco-css-editor"),
      document.getElementById("monaco-js-editor")
    ].filter(Boolean);

    handle.addEventListener("mousedown", (e) => {
      isResizing = true;
      startY = e.clientY;
      startHeights = editorContainers.map(c => c.offsetHeight);
      document.body.style.cursor = "ns-resize";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
      if (!isResizing) return;
      const delta = e.clientY - startY;
      
      editorContainers.forEach((container, i) => {
        const newHeight = Math.max(100, startHeights[i] + delta);
        container.style.height = newHeight + "px";
      });
      
      // Layout all editors
      Object.values(editorInstances).forEach(editor => {
        if (editor && editor.layout) {
          editor.layout();
        }
      });
    });

    document.addEventListener("mouseup", () => {
      if (isResizing) {
        isResizing = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    });
  }

  /**
   * Create live preview panel
   */
  function createPreviewPanel() {
    const panel = document.createElement("div");
    panel.className = "monaco-preview-panel";
    panel.id = "monaco-preview-panel";
    
    panel.innerHTML = `
      <div class="monaco-preview-header">
        <span class="monaco-preview-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
          Preview
        </span>
        <div class="monaco-preview-actions">
          <button type="button" class="monaco-btn monaco-btn-refresh" title="Refresh preview">${ICONS.refresh}</button>
          <button type="button" class="monaco-btn monaco-btn-popup-preview" title="Open preview in popup">${ICONS.popup}</button>
          <button type="button" class="monaco-btn monaco-btn-newtab-preview" title="Open preview in new tab">${ICONS.newTab}</button>
        </div>
      </div>
      <div class="monaco-preview-content">
        <iframe id="monaco-preview-iframe" sandbox="allow-scripts allow-same-origin" title="Preview"></iframe>
      </div>
      <div class="monaco-resize-handle monaco-resize-handle-preview" data-target="monaco-preview-panel"></div>
    `;
    
    return panel;
  }

  /**
   * Create global toolbar with open all actions
   */
  function createGlobalToolbar() {
    const toolbar = document.createElement("div");
    toolbar.className = "monaco-global-toolbar";
    toolbar.innerHTML = `
      <button type="button" class="monaco-btn monaco-btn-global monaco-btn-openall-popup" title="Open all in popup">
        ${ICONS.openAll}
        <span>Open All in Popup</span>
      </button>
      <button type="button" class="monaco-btn monaco-btn-global monaco-btn-openall-newtab" title="Open all in new tab">
        ${ICONS.newTab}
        <span>Open All in New Tab</span>
      </button>
    `;
    return toolbar;
  }

  /**
   * Get combined preview HTML
   */
  function getPreviewHtml(html, css, js) {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { 
      background: transparent;
      min-height: 100%;
    }
    body { 
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      padding: 0 24px;
    }
    img { max-width: 100%; height: auto; }
    ${css || ""}
  </style>
</head>
<body>
  ${html || ""}
  <script>
    try {
      ${js || ""}
    } catch(e) {
      console.error("Preview JS Error:", e);
    }
    
    // Auto-resize iframe to fit content
    function resizeIframe() {
      if (window.frameElement) {
        window.frameElement.style.height = document.documentElement.offsetHeight + "px";
      }
    }
    
    // Resize on load and resize
    window.addEventListener("load", resizeIframe);
    window.addEventListener("resize", resizeIframe);
    
    // Resize when content changes (MutationObserver)
    new MutationObserver(resizeIframe).observe(document.body, { 
      subtree: true, 
      childList: true, 
      attributes: true 
    });
    
    // Initial resize
    if (document.readyState === "complete") {
      resizeIframe();
    }
  </script>
</body>
</html>`;
  }

  /**
   * Update the live preview iframe
   */
  function updatePreview(html, css, js) {
    const iframe = document.getElementById("monaco-preview-iframe");
    if (!iframe) return;
    iframe.srcdoc = getPreviewHtml(html, css, js);
  }

  /**
   * Debounce function for preview updates
   */
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  /**
   * Create image upload button for HTML editor
   */
  function createImageUploadButton(htmlEditor) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "monaco-btn monaco-btn-upload";
    button.title = "Upload image";
    button.innerHTML = ICONS.upload;
    
    // Create hidden file input
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/*";
    fileInput.style.display = "none";
    document.body.appendChild(fileInput);
    
    button.addEventListener("click", () => {
      fileInput.click();
    });
    
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      
      // Show loading state
      button.classList.add("loading");
      button.disabled = true;
      
      try {
        const formData = new FormData();
        formData.append("upload", file);
        
        const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
        
        const response = await fetch("/media/ckeditor/upload/", {
          method: "POST",
          headers: {
            "X-CSRFToken": csrfToken
          },
          body: formData
        });
        
        if (!response.ok) {
          throw new Error("Upload failed");
        }
        
        const data = await response.json();
        
        if (data.url) {
          // Insert image HTML at cursor position
          const imageHtml = `<img src="${data.url}" alt="${file.name}" />`;
          const selection = htmlEditor.getSelection();
          const id = { major: 1, minor: 1 };
          const op = { identifier: id, range: selection, text: imageHtml, forceMoveMarkers: true };
          htmlEditor.executeEdits("image-upload", [op]);
          
          // Show success message
          showNotification("Image uploaded successfully!", "success");
        }
      } catch (error) {
        console.error("Upload error:", error);
        showNotification("Failed to upload image. Please try again.", "error");
      } finally {
        button.classList.remove("loading");
        button.disabled = false;
        fileInput.value = "";
      }
    });
    
    return button;
  }

  /**
   * Show notification message
   */
  function showNotification(message, type = "info") {
    const notification = document.createElement("div");
    notification.className = `monaco-notification monaco-notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.classList.add("fade-out");
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }

  /**
   * Setup fullscreen toggle for editor
   */
  function setupFullscreen(wrapper, editorInstance) {
    const fullscreenBtn = wrapper.querySelector(".monaco-btn-fullscreen");
    if (!fullscreenBtn) return;
    
    let isFullscreen = false;
    
    fullscreenBtn.addEventListener("click", () => {
      isFullscreen = !isFullscreen;
      wrapper.classList.toggle("monaco-fullscreen", isFullscreen);
      document.body.classList.toggle("monaco-fullscreen-active", isFullscreen);
      
      // Update button icon
      fullscreenBtn.innerHTML = isFullscreen ? ICONS.exitFullscreen : ICONS.fullscreen;
      
      editorInstance.layout();
    });
    
    // Escape key to exit fullscreen
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && isFullscreen) {
        isFullscreen = false;
        wrapper.classList.remove("monaco-fullscreen");
        document.body.classList.remove("monaco-fullscreen-active");
        fullscreenBtn.innerHTML = ICONS.fullscreen;
        editorInstance.layout();
      }
    });
  }

  /**
   * Setup format button
   */
  function setupFormatButton(wrapper, editorInstance) {
    const formatBtn = wrapper.querySelector(".monaco-btn-format");
    if (!formatBtn) return;
    
    formatBtn.addEventListener("click", () => {
      editorInstance.getAction("editor.action.formatDocument").run();
    });
  }

  /**
   * Open editor in popup modal
   */
  function openEditorPopup(language, label, getValue, setValue) {
    const overlay = document.createElement("div");
    overlay.className = "monaco-popup-overlay";
    overlay.innerHTML = `
      <div class="monaco-popup-container" style="width: 80vw; height: 80vh;">
        <div class="monaco-popup-header">
          <span class="monaco-popup-title">
            <span class="monaco-editor-label-icon ${language}"></span>
            ${label}
          </span>
          <button type="button" class="monaco-popup-close" title="Close (ESC)">${ICONS.close}</button>
        </div>
        <div class="monaco-popup-content">
          <div id="monaco-popup-editor" style="height: 100%;"></div>
        </div>
      </div>
    `;
    
    document.body.appendChild(overlay);
    document.body.classList.add("monaco-fullscreen-active");
    
    // Create popup editor
    const popupContainer = overlay.querySelector("#monaco-popup-editor");
    const popupEditor = monaco.editor.create(popupContainer, {
      ...EDITOR_DEFAULTS,
      value: getValue(),
      language: language === "js" ? "javascript" : language
    });
    
    // Close popup
    const closePopup = () => {
      setValue(popupEditor.getValue());
      popupEditor.dispose();
      overlay.remove();
      document.body.classList.remove("monaco-fullscreen-active");
    };
    
    overlay.querySelector(".monaco-popup-close").addEventListener("click", closePopup);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closePopup();
    });
    
    const escHandler = (e) => {
      if (e.key === "Escape") {
        closePopup();
        document.removeEventListener("keydown", escHandler);
      }
    };
    document.addEventListener("keydown", escHandler);
  }

  /**
   * Open preview in popup modal
   */
  function openPreviewPopup(html, css, js) {
    const overlay = document.createElement("div");
    overlay.className = "monaco-popup-overlay";
    overlay.innerHTML = `
      <div class="monaco-popup-container" style="width: 90vw; height: 90vh;">
        <div class="monaco-popup-header">
          <span class="monaco-popup-title">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
            Preview
          </span>
          <button type="button" class="monaco-popup-close" title="Close (ESC)">${ICONS.close}</button>
        </div>
        <div class="monaco-popup-content" style="background: #fff;">
          <iframe style="width: 100%; height: 100%; border: none;" sandbox="allow-scripts allow-same-origin"></iframe>
        </div>
      </div>
    `;
    
    document.body.appendChild(overlay);
    document.body.classList.add("monaco-fullscreen-active");
    
    // Set iframe content
    const iframe = overlay.querySelector("iframe");
    iframe.srcdoc = getPreviewHtml(html, css, js);
    
    // Close popup
    const closePopup = () => {
      overlay.remove();
      document.body.classList.remove("monaco-fullscreen-active");
    };
    
    overlay.querySelector(".monaco-popup-close").addEventListener("click", closePopup);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closePopup();
    });
    
    const escHandler = (e) => {
      if (e.key === "Escape") {
        closePopup();
        document.removeEventListener("keydown", escHandler);
      }
    };
    document.addEventListener("keydown", escHandler);
  }

  /**
   * Open editor in new tab
   */
  function openEditorInNewTab(language, label, value) {
    const langMapping = { html: "html", css: "css", js: "javascript" };
    const monacoLang = langMapping[language] || language;
    
    const pageHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>${label} Editor</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/editor/editor.main.min.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #1e1e2e; }
    #editor { width: 100vw; height: 100vh; }
  </style>
</head>
<body>
  <div id="editor"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/loader.min.js"></script>
  <script>
    require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' }});
    require(['vs/editor/editor.main'], function() {
      const editor = monaco.editor.create(document.getElementById('editor'), {
        value: ${JSON.stringify(value)},
        language: '${monacoLang}',
        theme: 'vs-dark',
        automaticLayout: true,
        fontSize: 14,
        minimap: { enabled: true }
      });
      editor.onDidChangeModelContent(() => {
        if (window.opener) {
          window.opener.postMessage({
            type: 'monaco_sync',
            language: '${language}',
            value: editor.getValue()
          }, '*');
        }
      });
    });
  </script>
</body>
</html>`;
    
    const newWindow = window.open("", "_blank");
    newWindow.document.write(pageHtml);
    newWindow.document.close();
  }

  /**
   * Open preview in new tab
   */
  function openPreviewInNewTab(html, css, js) {
    const previewHtml = getPreviewHtml(html, css, js);
    const newWindow = window.open("", "_blank");
    newWindow.document.write(previewHtml);
    newWindow.document.close();
  }

  /**
   * Open all (editors + preview) in new tab - CodePen style
   */
  function openAllInNewTab(html, css, js) {
    const pageHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Code Editor</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/editor/editor.main.min.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #1e1e2e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .container { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
    .editors-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2px; height: 45%; background: #313244; overflow: hidden; min-height: 100px; }
    .editor-panel { display: flex; flex-direction: column; background: #1e1e1e; }
    .editor-header { padding: 8px 12px; background: #2d2d3a; color: #cdd6f4; font-size: 12px; font-weight: 600; text-transform: uppercase; display: flex; align-items: center; gap: 6px; }
    .editor-icon { width: 8px; height: 8px; border-radius: 50%; }
    .editor-icon.html { background: #fab387; }
    .editor-icon.css { background: #89b4fa; }
    .editor-icon.js { background: #f9e2af; }
    .editor-container { flex: 1; }
    .resize-handle { width: 100%; height: 8px; background: #2d2d3a; cursor: ns-resize; transition: background 0.2s; }
    .resize-handle:hover { background: #a6e3a1; }
    .preview-row { flex: 1; background: #fff; display: flex; flex-direction: column; min-height: 150px; }
    .preview-header { padding: 8px 12px; background: #2d2d3a; color: #cdd6f4; font-size: 12px; font-weight: 600; text-transform: uppercase; }
    .preview-content { flex: 1; }
    .preview-content iframe { width: 100%; height: 100%; border: none; }
  </style>
</head>
<body>
  <div class="container">
    <div id="editors-row" class="editors-row">
      <div class="editor-panel">
        <div class="editor-header"><span class="editor-icon html"></span> HTML</div>
        <div id="html-editor" class="editor-container"></div>
      </div>
      <div class="editor-panel">
        <div class="editor-header"><span class="editor-icon css"></span> CSS</div>
        <div id="css-editor" class="editor-container"></div>
      </div>
      <div class="editor-panel">
        <div class="editor-header"><span class="editor-icon js"></span> JavaScript</div>
        <div id="js-editor" class="editor-container"></div>
      </div>
    </div>
    <div id="resize-handle" class="resize-handle" title="Drag to resize editors"></div>
    <div class="preview-row">
      <div class="preview-header">Preview</div>
      <div class="preview-content">
        <iframe id="preview-frame" sandbox="allow-scripts allow-same-origin"></iframe>
      </div>
    </div>
  </div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/loader.min.js"></script>
  <script>
    const htmlValue = ${JSON.stringify(html)};
    const cssValue = ${JSON.stringify(css)};
    const jsValue = ${JSON.stringify(js)};
    
    function updatePreview() {
      const html = window.htmlEditor?.getValue() || '';
      const css = window.cssEditor?.getValue() || '';
      const js = window.jsEditor?.getValue() || '';
      const iframe = document.getElementById('preview-frame');
      iframe.srcdoc = \`<!DOCTYPE html><html><head><style>* { margin: 0; padding: 0; box-sizing: border-box; } body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #1f2937; padding: 16px; } img { max-width: 100%; height: auto; } \${css}</style></head><body>\${html}<script>try { \${js} } catch(e) { console.error(e); }<\\/script></body></html>\`;
    }
    
    let debounceTimer;
    function debounceUpdate() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(updatePreview, 300);
    }
    
    // Setup resize handle
    const resizeHandle = document.getElementById('resize-handle');
    const editorsRow = document.getElementById('editors-row');
    let isResizing = false;
    let startY = 0;
    let startHeight = 0;
    
    resizeHandle.addEventListener('mousedown', (e) => {
      isResizing = true;
      startY = e.clientY;
      startHeight = editorsRow.offsetHeight;
      document.body.style.cursor = 'ns-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    
    document.addEventListener('mousemove', (e) => {
      if (!isResizing) return;
      const delta = e.clientY - startY;
      const maxHeight = window.innerHeight * 0.75;
      const newHeight = Math.min(maxHeight, Math.max(100, startHeight + delta));
      editorsRow.style.height = newHeight + 'px';
      if (window.htmlEditor) window.htmlEditor.layout();
      if (window.cssEditor) window.cssEditor.layout();
      if (window.jsEditor) window.jsEditor.layout();
    });
    
    document.addEventListener('mouseup', () => {
      if (isResizing) {
        isResizing = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    });
    
    require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' }});
    require(['vs/editor/editor.main'], function() {
      const opts = { theme: 'vs-dark', automaticLayout: true, fontSize: 13, minimap: { enabled: false }, wordWrap: 'on' };
      
      window.htmlEditor = monaco.editor.create(document.getElementById('html-editor'), { ...opts, value: htmlValue, language: 'html' });
      window.cssEditor = monaco.editor.create(document.getElementById('css-editor'), { ...opts, value: cssValue, language: 'css' });
      window.jsEditor = monaco.editor.create(document.getElementById('js-editor'), { ...opts, value: jsValue, language: 'javascript' });
      
      function sync(lang, val) {
        if (window.opener) {
          window.opener.postMessage({
            type: 'monaco_sync',
            language: lang,
            value: val
          }, '*');
        }
      }

      window.htmlEditor.onDidChangeModelContent(() => {
        debounceUpdate();
        sync('html', window.htmlEditor.getValue());
      });
      window.cssEditor.onDidChangeModelContent(() => {
        debounceUpdate();
        sync('css', window.cssEditor.getValue());
      });
      window.jsEditor.onDidChangeModelContent(() => {
        debounceUpdate();
        sync('javascript', window.jsEditor.getValue());
      });
      
      updatePreview();
    });
  </script>
</body>
</html>`;
    
    const newWindow = window.open("", "_blank");
    newWindow.document.write(pageHtml);
    newWindow.document.close();
  }

  /**
   * Open all in popup modal - CodePen style
   */
  function openAllInPopup(html, css, js) {
    const overlay = document.createElement("div");
    overlay.className = "monaco-popup-overlay";
    overlay.innerHTML = `
      <div class="monaco-popup-container" style="width: 95vw; height: 95vh;">
        <div class="monaco-popup-header">
          <span class="monaco-popup-title">
            ${ICONS.openAll}
            Code Editor
          </span>
          <button type="button" class="monaco-popup-close" title="Close (ESC)">${ICONS.close}</button>
        </div>
        <div class="monaco-popup-content" style="display: flex; flex-direction: column; overflow: hidden;">
          <div id="popup-editors-row" style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2px; height: 45%; background: #313244; overflow: hidden; min-height: 100px;">
            <div style="display: flex; flex-direction: column; background: #1e1e1e;">
              <div style="padding: 6px 10px; background: #2d2d3a; color: #cdd6f4; font-size: 11px; font-weight: 600; text-transform: uppercase; display: flex; align-items: center; gap: 6px;">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: #fab387;"></span> HTML
              </div>
              <div id="popup-html-editor" style="flex: 1;"></div>
            </div>
            <div style="display: flex; flex-direction: column; background: #1e1e1e;">
              <div style="padding: 6px 10px; background: #2d2d3a; color: #cdd6f4; font-size: 11px; font-weight: 600; text-transform: uppercase; display: flex; align-items: center; gap: 6px;">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: #89b4fa;"></span> CSS
              </div>
              <div id="popup-css-editor" style="flex: 1;"></div>
            </div>
            <div style="display: flex; flex-direction: column; background: #1e1e1e;">
              <div style="padding: 6px 10px; background: #2d2d3a; color: #cdd6f4; font-size: 11px; font-weight: 600; text-transform: uppercase; display: flex; align-items: center; gap: 6px;">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: #f9e2af;"></span> JavaScript
              </div>
              <div id="popup-js-editor" style="flex: 1;"></div>
            </div>
          </div>
          <div id="popup-resize-handle" style="width: 100%; height: 8px; background: #2d2d3a; cursor: ns-resize; transition: background 0.2s; flex-shrink: 0;" title="Drag to resize"></div>
          <div style="flex: 1; background: #fff; display: flex; flex-direction: column; min-height: 150px; overflow: hidden;">
            <div style="padding: 6px 10px; background: #2d2d3a; color: #cdd6f4; font-size: 11px; font-weight: 600; text-transform: uppercase;">Preview</div>
            <iframe id="popup-preview-frame" style="flex: 1; border: none; width: 100%;" sandbox="allow-scripts allow-same-origin"></iframe>
          </div>
        </div>
      </div>
    `;
    
    document.body.appendChild(overlay);
    document.body.classList.add("monaco-fullscreen-active");
    
    // Create editors
    const opts = { ...EDITOR_DEFAULTS, minimap: { enabled: false } };
    
    const popupHtmlEditor = monaco.editor.create(overlay.querySelector("#popup-html-editor"), { ...opts, value: html, language: "html" });
    const popupCssEditor = monaco.editor.create(overlay.querySelector("#popup-css-editor"), { ...opts, value: css, language: "css" });
    const popupJsEditor = monaco.editor.create(overlay.querySelector("#popup-js-editor"), { ...opts, value: js, language: "javascript" });
    
    // Setup resize handle for popup
    const popupResizeHandle = overlay.querySelector("#popup-resize-handle");
    const popupEditorsRow = overlay.querySelector("#popup-editors-row");
    let isPopupResizing = false;
    let popupStartY = 0;
    let popupStartHeight = 0;
    
    popupResizeHandle.addEventListener("mouseenter", () => {
      popupResizeHandle.style.background = "#a6e3a1";
    });
    popupResizeHandle.addEventListener("mouseleave", () => {
      if (!isPopupResizing) popupResizeHandle.style.background = "#2d2d3a";
    });
    
    popupResizeHandle.addEventListener("mousedown", (e) => {
      isPopupResizing = true;
      popupStartY = e.clientY;
      popupStartHeight = popupEditorsRow.offsetHeight;
      document.body.style.cursor = "ns-resize";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });
    
    document.addEventListener("mousemove", (e) => {
      if (!isPopupResizing) return;
      const delta = e.clientY - popupStartY;
      const container = overlay.querySelector(".monaco-popup-content");
      const maxHeight = container ? container.offsetHeight * 0.75 : 600;
      const newHeight = Math.min(maxHeight, Math.max(100, popupStartHeight + delta));
      popupEditorsRow.style.height = newHeight + "px";
      popupHtmlEditor.layout();
      popupCssEditor.layout();
      popupJsEditor.layout();
    });
    
    document.addEventListener("mouseup", () => {
      if (isPopupResizing) {
        isPopupResizing = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        popupResizeHandle.style.background = "#2d2d3a";
      }
    });
    
    const popupUpdatePreview = () => {
      const iframe = overlay.querySelector("#popup-preview-frame");
      iframe.srcdoc = getPreviewHtml(popupHtmlEditor.getValue(), popupCssEditor.getValue(), popupJsEditor.getValue());
    };
    
    const debounced = debounce(popupUpdatePreview, 300);
    popupHtmlEditor.onDidChangeModelContent(debounced);
    popupCssEditor.onDidChangeModelContent(debounced);
    popupJsEditor.onDidChangeModelContent(debounced);
    
    popupUpdatePreview();
    
    // Close popup and sync values back
    const closePopup = () => {
      // Sync values back to original editors
      if (window.monacoEditors.html) {
        window.monacoEditors.html.setValue(popupHtmlEditor.getValue());
      }
      if (window.monacoEditors.css) {
        window.monacoEditors.css.setValue(popupCssEditor.getValue());
      }
      if (window.monacoEditors.javascript) {
        window.monacoEditors.javascript.setValue(popupJsEditor.getValue());
      }
      
      popupHtmlEditor.dispose();
      popupCssEditor.dispose();
      popupJsEditor.dispose();
      overlay.remove();
      document.body.classList.remove("monaco-fullscreen-active");
    };
    
    overlay.querySelector(".monaco-popup-close").addEventListener("click", closePopup);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closePopup();
    });
    
    const escHandler = (e) => {
      if (e.key === "Escape") {
        closePopup();
        document.removeEventListener("keydown", escHandler);
      }
    };
    document.addEventListener("keydown", escHandler);
  }

  /**
   * Setup popup button for editor
   */
  function setupPopupButton(wrapper, language, label, editorInstance) {
    const popupBtn = wrapper.querySelector(".monaco-btn-popup");
    if (!popupBtn) return;
    
    popupBtn.addEventListener("click", () => {
      openEditorPopup(
        language,
        label,
        () => editorInstance.getValue(),
        (value) => editorInstance.setValue(value)
      );
    });
  }

  /**
   * Setup new tab button for editor
   */
  function setupNewTabButton(wrapper, language, label, editorInstance) {
    const newTabBtn = wrapper.querySelector(".monaco-btn-newtab");
    if (!newTabBtn) return;
    
    newTabBtn.addEventListener("click", () => {
      openEditorInNewTab(language, label, editorInstance.getValue());
    });
  }

  /**
   * Main initialization function
   */
  function initMonacoEditors() {
    const htmlField = document.getElementById("id_custom_html");
    const cssField = document.getElementById("id_custom_css");
    const jsField = document.getElementById("id_custom_js");
    
    // If no HTML field exists, this page doesn't need Monaco editors
    if (!htmlField) return;

    // Listen for sync messages from popups/new tabs
    window.addEventListener("message", (event) => {
      const data = event.data;
      if (data && data.type === "monaco_sync") {
        let lang = data.language;
        if (lang === "js") lang = "javascript"; // Fix mapping for JS editor
        
        const editor = window.monacoEditors[lang];
        if (editor && editor.getValue() !== data.value) {
          editor.setValue(data.value);
        }
      }
    });

    console.log("Initializing Monaco Editors (CodePen-style)...");
    
    // Configure Monaco AMD loader
    require.config({ paths: { vs: MONACO_CDN } });
    
    require(["vs/editor/editor.main"], function () {
      // Find the form row containing custom_html
      const htmlFieldRow = htmlField.closest(".form-row") || htmlField.closest("div[class*='field-custom_html']");
      const cssFieldRow = cssField?.closest(".form-row") || cssField?.closest("div[class*='field-custom_css']");
      const jsFieldRow = jsField?.closest(".form-row") || jsField?.closest("div[class*='field-custom_js']");
      
      // Create main container
      const editorsContainer = document.createElement("div");
      editorsContainer.className = "monaco-editors-container";
      editorsContainer.id = "monaco-editors-container";
      
      // Create global toolbar
      const globalToolbar = createGlobalToolbar();
      editorsContainer.appendChild(globalToolbar);
      
      // Create editors row (3 columns)
      const editorsRow = document.createElement("div");
      editorsRow.className = "monaco-editors-row";
      editorsRow.id = "monaco-editors-row";
      editorsContainer.appendChild(editorsRow);
      
      // Create preview row
      const previewRow = document.createElement("div");
      previewRow.className = "monaco-preview-row";
      previewRow.id = "monaco-preview-row";
      editorsContainer.appendChild(previewRow);
      
      // Insert container after the HTML field row
      if (htmlFieldRow) {
        htmlFieldRow.parentNode.insertBefore(editorsContainer, htmlFieldRow);
      }
      
      // Hide original textareas
      htmlField.style.display = "none";
      if (cssField) cssField.style.display = "none";
      if (jsField) jsField.style.display = "none";
      
      // Hide original rows
      if (htmlFieldRow) htmlFieldRow.style.display = "none";
      if (cssFieldRow) cssFieldRow.style.display = "none";
      if (jsFieldRow) jsFieldRow.style.display = "none";
      
      // Create HTML editor
      const htmlWrapper = createEditorContainer("html", "HTML", 250);
      editorsRow.appendChild(htmlWrapper);
      const htmlEditorContainer = document.getElementById("monaco-html-editor");
      const htmlEditor = createEditor(htmlEditorContainer, "html", htmlField.value);
      
      // Add image upload button to HTML editor header
      const htmlHeader = htmlWrapper.querySelector(".monaco-editor-actions");
      const uploadBtn = createImageUploadButton(htmlEditor);
      htmlHeader.insertBefore(uploadBtn, htmlHeader.firstChild);
      
      // Setup HTML editor features
      setupFullscreen(htmlWrapper, htmlEditor);
      setupFormatButton(htmlWrapper, htmlEditor);
      setupPopupButton(htmlWrapper, "html", "HTML", htmlEditor);
      setupNewTabButton(htmlWrapper, "html", "HTML", htmlEditor);
      
      // Create CSS editor
      let cssEditor = null;
      if (cssField) {
        const cssWrapper = createEditorContainer("css", "CSS", 250);
        editorsRow.appendChild(cssWrapper);
        const cssEditorContainer = document.getElementById("monaco-css-editor");
        cssEditor = createEditor(cssEditorContainer, "css", cssField.value);
        setupFullscreen(cssWrapper, cssEditor);
        setupFormatButton(cssWrapper, cssEditor);
        setupPopupButton(cssWrapper, "css", "CSS", cssEditor);
        setupNewTabButton(cssWrapper, "css", "CSS", cssEditor);
        
        // Sync CSS back to textarea
        cssEditor.onDidChangeModelContent(() => {
          cssField.value = cssEditor.getValue();
          cssField.dispatchEvent(new Event("input", { bubbles: true }));
          cssField.dispatchEvent(new Event("change", { bubbles: true }));
          debouncedUpdatePreview();
        });
      }
      
      // Create JS editor
      let jsEditor = null;
      if (jsField) {
        const jsWrapper = createEditorContainer("js", "JavaScript", 250);
        editorsRow.appendChild(jsWrapper);
        const jsEditorContainer = document.getElementById("monaco-js-editor");
        jsEditor = createEditor(jsEditorContainer, "javascript", jsField.value);
        setupFullscreen(jsWrapper, jsEditor);
        setupFormatButton(jsWrapper, jsEditor);
        setupPopupButton(jsWrapper, "js", "JavaScript", jsEditor);
        setupNewTabButton(jsWrapper, "js", "JavaScript", jsEditor);
        
        // Sync JS back to textarea
        jsEditor.onDidChangeModelContent(() => {
          jsField.value = jsEditor.getValue();
          jsField.dispatchEvent(new Event("input", { bubbles: true }));
          jsField.dispatchEvent(new Event("change", { bubbles: true }));
          debouncedUpdatePreview();
        });
      }
      
      // Add unified resize handle for all editors (after editorsRow, not inside it)
      const unifiedResizeHandle = document.createElement("div");
      unifiedResizeHandle.className = "monaco-resize-handle monaco-unified-resize";
      unifiedResizeHandle.title = "Drag to resize all editors";
      editorsContainer.insertBefore(unifiedResizeHandle, previewRow);
      
      // Setup unified resize for all editors
      setupUnifiedResizeHandle(unifiedResizeHandle, { 
        html: htmlEditor, 
        css: cssEditor, 
        javascript: jsEditor 
      });
      
      // Create preview panel
      const previewPanel = createPreviewPanel();
      previewRow.appendChild(previewPanel);
      
      // Setup preview resize
      const previewResizeHandle = previewPanel.querySelector(".monaco-resize-handle-preview");
      if (previewResizeHandle) {
        let isResizing = false;
        let startY = 0;
        let startHeight = 0;
        const previewContent = previewPanel.querySelector(".monaco-preview-content");
        const previewIframe = previewPanel.querySelector("#monaco-preview-iframe");
        
        const onMouseMove = (e) => {
          if (!isResizing) return;
          const delta = e.clientY - startY;
          const newHeight = Math.max(300, startHeight + delta);
          previewPanel.style.height = newHeight + "px";
          previewPanel.style.maxHeight = "none";
          previewContent.style.flex = "1";
        };

        const onMouseUp = () => {
          if (isResizing) {
            isResizing = false;
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
            if (previewIframe) previewIframe.style.pointerEvents = "auto";
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
          }
        };

        previewResizeHandle.addEventListener("mousedown", (e) => {
          isResizing = true;
          startY = e.clientY;
          startHeight = previewPanel.offsetHeight;
          document.body.style.cursor = "ns-resize";
          document.body.style.userSelect = "none";
          if (previewIframe) previewIframe.style.pointerEvents = "none";
          
          window.addEventListener("mousemove", onMouseMove);
          window.addEventListener("mouseup", onMouseUp);
          
          e.preventDefault();
        });
      }
      
      // Debounced preview update
      const debouncedUpdatePreview = debounce(() => {
        updatePreview(
          window.monacoEditors.html?.getValue() || "",
          window.monacoEditors.css?.getValue() || "",
          window.monacoEditors.javascript?.getValue() || ""
        );
      }, 300);
      
      // Setup refresh button
      const refreshBtn = previewPanel.querySelector(".monaco-btn-refresh");
      if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
          updatePreview(
            window.monacoEditors.html?.getValue() || "",
            window.monacoEditors.css?.getValue() || "",
            window.monacoEditors.javascript?.getValue() || ""
          );
        });
      }
      
      // Setup preview popup button
      const previewPopupBtn = previewPanel.querySelector(".monaco-btn-popup-preview");
      if (previewPopupBtn) {
        previewPopupBtn.addEventListener("click", () => {
          openPreviewPopup(
            window.monacoEditors.html?.getValue() || "",
            window.monacoEditors.css?.getValue() || "",
            window.monacoEditors.javascript?.getValue() || ""
          );
        });
      }
      
      // Setup preview new tab button
      const previewNewTabBtn = previewPanel.querySelector(".monaco-btn-newtab-preview");
      if (previewNewTabBtn) {
        previewNewTabBtn.addEventListener("click", () => {
          openPreviewInNewTab(
            window.monacoEditors.html?.getValue() || "",
            window.monacoEditors.css?.getValue() || "",
            window.monacoEditors.javascript?.getValue() || ""
          );
        });
      }
      
      // Setup global toolbar buttons
      const openAllPopupBtn = globalToolbar.querySelector(".monaco-btn-openall-popup");
      if (openAllPopupBtn) {
        openAllPopupBtn.addEventListener("click", () => {
          openAllInPopup(
            window.monacoEditors.html?.getValue() || "",
            window.monacoEditors.css?.getValue() || "",
            window.monacoEditors.javascript?.getValue() || ""
          );
        });
      }
      
      const openAllNewTabBtn = globalToolbar.querySelector(".monaco-btn-openall-newtab");
      if (openAllNewTabBtn) {
        openAllNewTabBtn.addEventListener("click", () => {
          openAllInNewTab(
            window.monacoEditors.html?.getValue() || "",
            window.monacoEditors.css?.getValue() || "",
            window.monacoEditors.javascript?.getValue() || ""
          );
        });
      }
      
      // Sync HTML back to textarea and update preview
      htmlEditor.onDidChangeModelContent(() => {
        htmlField.value = htmlEditor.getValue();
        htmlField.dispatchEvent(new Event("input", { bubbles: true }));
        htmlField.dispatchEvent(new Event("change", { bubbles: true }));
        debouncedUpdatePreview();
      });
      
      // Initial preview
      updatePreview(
        htmlField.value || "",
        cssField?.value || "",
        jsField?.value || ""
      );
      
      // Dispatch event to tell draft system to resync baseline
      document.dispatchEvent(new Event("draft:resyncBaseline"));
      
      console.log("Monaco Editors initialized successfully (CodePen-style)!");
    });
  }

  // Initialize when DOM is ready
  document.addEventListener("DOMContentLoaded", initMonacoEditors);
})();
