(function initializeCodeNotifications(global) {
  "use strict";

  const services = global.Code && global.Code.services;
  if (!services) {
    throw new Error("Code services namespace must load before notifications");
  }

  function showToast(message, type = "error", options = {}) {
    const container = global.document.getElementById("toastContainer");
    if (!container) return;
    const requestedDuration = Number(options.duration);
    const duration = Number.isFinite(requestedDuration)
      ? Math.max(1000, Math.min(requestedDuration, 15000))
      : 3000;

    const toast = global.document.createElement("div");
    toast.className = `toast ${type}`;
    const urgent = type === "error";
    toast.setAttribute("role", urgent ? "alert" : "status");
    toast.setAttribute("aria-live", urgent ? "assertive" : "polite");
    toast.setAttribute("aria-atomic", "true");
    const text = String(message ?? "");
    const emphasis = String(options.emphasis || "");
    const emphasisIndex = emphasis ? text.indexOf(emphasis) : -1;
    if (emphasisIndex >= 0 && typeof global.document.createTextNode === "function") {
      if (emphasisIndex > 0) {
        toast.appendChild(global.document.createTextNode(text.slice(0, emphasisIndex)));
      }
      const highlighted = global.document.createElement("span");
      highlighted.className = "toast-emphasis";
      highlighted.textContent = emphasis;
      toast.appendChild(highlighted);
      const suffix = text.slice(emphasisIndex + emphasis.length);
      if (suffix) toast.appendChild(global.document.createTextNode(suffix));
    } else {
      toast.textContent = text;
    }
    container.appendChild(toast);

    global.setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity .2s";
      global.setTimeout(() => toast.remove(), 200);
    }, duration);
  }

  function notify(title, body) {
    try {
      if ("Notification" in global && global.Notification.permission === "granted") {
        return new global.Notification(title, { body, icon: "code-icon.png" });
      }
    } catch (_) {}
    return null;
  }

  services.notifications = Object.freeze({
    showToast,
    notify,
  });
})(window);
