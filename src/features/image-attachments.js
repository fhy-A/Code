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
    MODEL_IMAGE_MIMES,
    SERVER_CONVERTIBLE_IMAGE_MIMES,
    canDeferImageConversion,
    imageMimeForFile,
    imageMimeFromName,
    isImageFileCandidate,
    modelImageOutputMime,
    normalizeImageMime,
    parseImageDataUrl,
    sniffImageMime,
    storageNameForImage,
  });
})(window);
