(function initializeImageOverlay(global) {
  "use strict";

  const features = global.Code && global.Code.features;
  if (!features) throw new Error("Code features namespace must load before image overlay");

  /** Keep only usable image sources; empty lists degrade to single-image mode. */
  function normalizeSources(sources) {
    return Array.isArray(sources)
      ? sources.filter((s) => typeof s === "string" && s !== "")
      : [];
  }

  /**
   * Pure navigation model for the composer image overlay gallery.
   * Boundary policy: arrows are disabled at the ends (no wrap-around).
   */
  function createImageOverlayModel(sources, startIndex) {
    const list = normalizeSources(sources);
    let index = list.length === 0
      ? 0
      : Math.max(0, Math.min(Number(startIndex) || 0, list.length - 1));
    return Object.freeze({
      get list() {
        return list;
      },
      get index() {
        return index;
      },
      get count() {
        return list.length;
      },
      current() {
        return list[index] ?? "";
      },
      canPrev() {
        return index > 0;
      },
      canNext() {
        return index < list.length - 1;
      },
      prev() {
        if (index > 0) index -= 1;
        return this.current();
      },
      next() {
        if (index < list.length - 1) index += 1;
        return this.current();
      },
    });
  }

  features.imageOverlay = Object.freeze({
    createImageOverlayModel,
    normalizeSources,
  });
})(typeof window !== "undefined" ? window : globalThis);
