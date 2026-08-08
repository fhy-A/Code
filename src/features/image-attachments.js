(function initializeImageAttachments(global) {
  "use strict";

  const features = global.Code && global.Code.features;
  if (!features) throw new Error("Code features namespace must load before image attachments");

  const MODEL_IMAGE_MIMES = Object.freeze(["image/png", "image/jpeg", "image/webp"]);
  const SERVER_CONVERTIBLE_IMAGE_MIMES = Object.freeze([
    "image/bmp",
    "image/gif",
    "image/x-icon",
    "image/tiff",
  ]);
  const DERIVED_BROWSER_PREVIEW_MIMES = Object.freeze(["image/tiff"]);
  const EXTENSION_MIMES = Object.freeze({
    bmp: "image/bmp",
    gif: "image/gif",
    ico: "image/x-icon",
    jpeg: "image/jpeg",
    jpg: "image/jpeg",
    png: "image/png",
    svg: "image/svg+xml",
    tif: "image/tiff",
    tiff: "image/tiff",
    webp: "image/webp",
  });
  const MIME_EXTENSIONS = Object.freeze({
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
  });

  function normalizeImageMime(value) {
    const mime = String(value || "").split(";", 1)[0].trim().toLowerCase();
    if (mime === "image/jpg" || mime === "image/pjpeg") return "image/jpeg";
    if (["image/ico", "image/icon", "image/vnd.microsoft.icon"].includes(mime)) {
      return "image/x-icon";
    }
    if (mime === "image/x-tiff") return "image/tiff";
    return mime;
  }

  function imageMimeFromName(name) {
    const match = String(name || "").toLowerCase().match(/\.([a-z0-9]+)$/);
    return match ? EXTENSION_MIMES[match[1]] || "" : "";
  }

  function sniffImageMime(bytes) {
    const data = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || 0);
    const startsWith = (...values) => values.every((value, index) => data[index] === value);
    if (startsWith(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) return "image/png";
    if (startsWith(0xff, 0xd8, 0xff)) return "image/jpeg";
    if (
      data.length >= 12
      && String.fromCharCode(...data.slice(0, 4)) === "RIFF"
      && String.fromCharCode(...data.slice(8, 12)) === "WEBP"
    ) return "image/webp";
    if (data.length >= 6) {
      const signature = String.fromCharCode(...data.slice(0, 6));
      if (signature === "GIF87a" || signature === "GIF89a") return "image/gif";
    }
    if (startsWith(0x42, 0x4d)) return "image/bmp";
    if (startsWith(0x00, 0x00, 0x01, 0x00)) return "image/x-icon";
    if (
      startsWith(0x49, 0x49, 0x2a, 0x00)
      || startsWith(0x4d, 0x4d, 0x00, 0x2a)
    ) return "image/tiff";
    return "";
  }

  function imageMimeForFile(file, bytes = null) {
    return sniffImageMime(bytes)
      || normalizeImageMime(file?.type)
      || imageMimeFromName(file?.name);
  }

  function isImageFileCandidate(file) {
    return Boolean(file && (
      normalizeImageMime(file.type).startsWith("image/")
      || imageMimeFromName(file.name)
    ));
  }

  function modelImageOutputMime(sourceMime) {
    const normalized = normalizeImageMime(sourceMime);
    return MODEL_IMAGE_MIMES.includes(normalized) ? normalized : "image/png";
  }

  function canDeferImageConversion(sourceMime) {
    const normalized = normalizeImageMime(sourceMime);
    return MODEL_IMAGE_MIMES.includes(normalized)
      || SERVER_CONVERTIBLE_IMAGE_MIMES.includes(normalized);
  }

  function requiresDerivedBrowserPreview(imageOrMime) {
    const image = imageOrMime && typeof imageOrMime === "object" ? imageOrMime : null;
    const mime = normalizeImageMime(image?.mime || imageOrMime)
      || imageMimeFromName(image?.name || image?.path || "");
    return DERIVED_BROWSER_PREVIEW_MIMES.includes(mime);
  }

  function imagePreviewSource(image = {}) {
    if (requiresDerivedBrowserPreview(image)) {
      if (image._previewUrl) return String(image._previewUrl);
      return image.path
        ? `/api/attachments/preview?path=${encodeURIComponent(image.path)}`
        : "";
    }
    if (image.path) return `/api/file?path=${encodeURIComponent(image.path)}&raw=1`;
    if (!image.base64) return "";
    return `data:${normalizeImageMime(image.mime) || "image/png"};base64,${image.base64}`;
  }

  async function requestDerivedBrowserPreview(image = {}, options = {}) {
    if (!requiresDerivedBrowserPreview(image) || (!image.base64 && !image.path)) return "";
    const fetchImpl = options.fetchImpl || global.fetch;
    const urlApi = options.urlApi || global.URL;
    if (typeof fetchImpl !== "function" || typeof urlApi?.createObjectURL !== "function") {
      throw new Error("derived image preview is unavailable");
    }
    const response = image.path
      ? await fetchImpl(imagePreviewSource(image), { method: "GET" })
      : await fetchImpl("/api/attachments/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mime: normalizeImageMime(image.mime),
          contentBase64: image.base64,
        }),
      });
    if (!response?.ok) throw new Error("derived image preview failed");
    const blob = await response.blob();
    if (!blob?.size || normalizeImageMime(blob.type) !== "image/png") {
      throw new Error("derived image preview is invalid");
    }
    return urlApi.createObjectURL(blob);
  }

  function derivedBrowserPreviewCacheKey(image = {}) {
    const mime = normalizeImageMime(image.mime)
      || imageMimeFromName(image.name || image.path || "");
    const path = String(image.path || "");
    if (!DERIVED_BROWSER_PREVIEW_MIMES.includes(mime) || !path) return "";
    return `${mime}\u0000${path}`;
  }

  function createDerivedBrowserPreviewCache(options = {}) {
    const requestPreview = options.requestPreview || requestDerivedBrowserPreview;
    const urlApi = options.urlApi || global.URL;
    const onSettled = typeof options.onSettled === "function" ? options.onSettled : () => {};
    const entries = new Map();

    function notifySettled(key, entry) {
      try {
        const result = onSettled({ key, image: entry.image, status: entry.status });
        if (result && typeof result.catch === "function") result.catch(() => {});
      } catch (_) {}
    }

    function revokeEntryUrl(entry, url = entry.url) {
      if (!url || entry.urlRevoked) return;
      entry.urlRevoked = true;
      try {
        urlApi?.revokeObjectURL?.(url);
      } catch (_) {}
    }

    function ensure(image = {}) {
      const key = derivedBrowserPreviewCacheKey(image);
      if (!key) return Promise.resolve("");
      const existing = entries.get(key);
      if (existing) return existing.promise;

      const entry = {
        image: {
          mime: normalizeImageMime(image.mime),
          path: String(image.path || ""),
        },
        promise: null,
        status: "pending",
        url: "",
        urlRevoked: false,
      };
      entry.promise = Promise.resolve()
        .then(() => requestPreview(entry.image, { urlApi }))
        .then((url) => {
          if (!url) throw new Error("derived image preview is unavailable");
          if (entries.get(key) !== entry) {
            revokeEntryUrl(entry, url);
            return "";
          }
          entry.status = "ready";
          entry.url = String(url);
          notifySettled(key, entry);
          return entry.url;
        })
        .catch(() => {
          if (entries.get(key) === entry) {
            entry.status = "failed";
            notifySettled(key, entry);
          }
          return "";
        });
      entries.set(key, entry);
      return entry.promise;
    }

    function source(image = {}) {
      const entry = entries.get(derivedBrowserPreviewCacheKey(image));
      return entry?.status === "ready" ? entry.url : "";
    }

    function status(image = {}) {
      return entries.get(derivedBrowserPreviewCacheKey(image))?.status || "";
    }

    function clear() {
      const currentEntries = Array.from(entries.values());
      entries.clear();
      currentEntries.forEach((entry) => {
        if (entry.status === "ready") revokeEntryUrl(entry);
      });
    }

    return Object.freeze({ clear, ensure, source, status });
  }

  function parseImageDataUrl(value) {
    const match = String(value || "").match(/^data:([^;,]+);base64,([a-z0-9+/=\s]+)$/i);
    if (!match) return null;
    const mime = normalizeImageMime(match[1]);
    const base64 = match[2].replace(/\s+/g, "");
    return mime.startsWith("image/") && base64 ? { mime, base64 } : null;
  }

  function storageNameForImage(name, outputMime) {
    const desiredExtension = MIME_EXTENSIONS[normalizeImageMime(outputMime)];
    const originalName = String(name || "image").trim() || "image";
    if (!desiredExtension) return originalName;
    const currentMime = imageMimeFromName(originalName);
    if (currentMime === normalizeImageMime(outputMime)) return originalName;
    if (/\.[^./\\]+$/.test(originalName)) {
      return originalName.replace(/\.[^./\\]+$/, `.${desiredExtension}`);
    }
    return `${originalName}.${desiredExtension}`;
  }

  features.imageAttachments = Object.freeze({
    DERIVED_BROWSER_PREVIEW_MIMES,
    MODEL_IMAGE_MIMES,
    SERVER_CONVERTIBLE_IMAGE_MIMES,
    canDeferImageConversion,
    createDerivedBrowserPreviewCache,
    derivedBrowserPreviewCacheKey,
    imageMimeForFile,
    imageMimeFromName,
    imagePreviewSource,
    isImageFileCandidate,
    modelImageOutputMime,
    normalizeImageMime,
    parseImageDataUrl,
    requestDerivedBrowserPreview,
    requiresDerivedBrowserPreview,
    sniffImageMime,
    storageNameForImage,
  });
})(window);
