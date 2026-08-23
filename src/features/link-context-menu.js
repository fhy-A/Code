(function initializeLinkContextMenu(global) {
  "use strict";

  const features = global.Code && global.Code.features;
  if (!features) throw new Error("Code features namespace must load before link context menu");

  const MENU_CLASS = "file-ctx-menu";
  const MENU_WIDTH = 200;
  const MENU_HEIGHT = 150;

  /**
   * Right-click menu for links in final answers (answer-render R009).
   * Reuses the file-tree context-menu styles; the caller supplies t() and
   * action callbacks so this module stays DOM-only and testable.
   */
  function showLinkContextMenu(options) {
    const {
      x,
      y,
      kind,
      pathOptions = null,
      linkOptions = null,
      t,
      copyText,
      callbacks = {},
    } = options || {};
    const documentRoot = (typeof global.document !== "undefined" ? global.document : null);
    if (!documentRoot) return;

    documentRoot.querySelectorAll("." + MENU_CLASS).forEach((el) => el.remove());

    const menu = documentRoot.createElement("div");
    menu.className = MENU_CLASS;
    menu.style.left = Math.min(x, (global.innerWidth || 0) - MENU_WIDTH) + "px";
    menu.style.top = Math.min(y, (global.innerHeight || 0) - MENU_HEIGHT) + "px";

    const filename = pathOptions?.filename || "";
    const items = [];
    if (kind === "path" && pathOptions) {
      if (filename) items.push({ html: `<div class="file-ctx-name">${String(filename)}</div>` });
      if (pathOptions.previewable) {
        items.push({ label: t("openInPreview") || "Open", action: "open" });
      }
      items.push({ label: t("openDefaultApp") || "Open with default app", action: "system" });
      if (pathOptions.previewable) {
        items.push({ label: t("revealInFolder") || "Show in folder", action: "reveal" });
      }
      items.push({ label: t("copyPath") || "Copy path", action: "copy-path" });
      if (filename) items.push({ label: t("copyFileName") || "Copy file name", action: "copy-name" });
    } else if (kind === "link" && linkOptions) {
      items.push({ label: t("openInNewTab") || "Open in new tab", action: "open-tab" });
      items.push({ label: t("copyLink") || "Copy link", action: "copy-link" });
    }
    menu.innerHTML = items.map((item) => item.html || `<button type="button" data-action="${item.action}">${String(item.label)}</button>`).join("");

    menu.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.action;
        if (action === "open") callbacks.open?.();
        else if (action === "system") callbacks.system?.();
        else if (action === "reveal") callbacks.reveal?.();
        else if (action === "copy-path") copyText?.(pathOptions?.path || "");
        else if (action === "copy-name") copyText?.(filename || "");
        else if (action === "open-tab") callbacks.openTab?.(linkOptions?.url || "");
        else if (action === "copy-link") copyText?.(linkOptions?.url || "");
        menu.remove();
      });
    });

    documentRoot.body.appendChild(menu);
    const close = (event) => {
      if (!menu.contains(event.target)) {
        menu.remove();
        documentRoot.removeEventListener("click", close);
        documentRoot.removeEventListener("contextmenu", close);
      }
    };
    const scheduleClose = (global.setTimeout || globalThis.setTimeout).bind(globalThis);
    scheduleClose(() => {
      documentRoot.addEventListener("click", close);
      documentRoot.addEventListener("contextmenu", close);
    }, 0);
  }

  features.linkContextMenu = Object.freeze({
    showLinkContextMenu,
  });
})(typeof window !== "undefined" ? window : globalThis);