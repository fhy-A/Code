(function initializeCodeIcons(global) {
  "use strict";

  const core = global.Code && global.Code.core;
  if (!core) throw new Error("Code core namespace must load before icons");

  const paths = {
    plus: '<path d="M12 5v14M5 12h14"/>',
    chevronDown: '<path d="m7 10 5 5 5-5"/>',
    chevronRight: '<path d="m10 7 5 5-5 5"/>',
    up: '<path d="m5 11 7-7 7 7M12 4v16"/>',
    folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h5l2 2H20a1 1 0 0 1 1 1v10.5A1.5 1.5 0 0 1 19.5 20h-15A1.5 1.5 0 0 1 3 18.5v-12Z"/>',
    folderOpen: '<path d="M3 7V6.5A1.5 1.5 0 0 1 4.5 5h5l2 2H20a1 1 0 0 1 1 1v2"/><path d="M3.5 10h17a1 1 0 0 1 .94 1.34l-2.7 7.5A1.75 1.75 0 0 1 17.1 20H5.2a1.75 1.75 0 0 1-1.68-1.27L2.54 12A1.75 1.75 0 0 1 3.5 10Z"/>',
    folderPlus: '<path d="M3 7V6.5A1.5 1.5 0 0 1 4.5 5h5l2 2H20a1 1 0 0 1 1 1v10.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5V7Z"/><path d="M12 11v6M9 14h6"/>',
    refresh: '<path d="M20 6v5h-5"/><path d="M4 18v-5h5"/><path d="M18.7 9A7 7 0 0 0 6.2 6.2L4 9M5.3 15A7 7 0 0 0 17.8 17.8L20 15"/>',
    home: '<path d="m3 11 9-7 9 7"/><path d="M5.5 9.5V20h13V9.5M9.5 20v-6h5v6"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.1A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.1A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.1A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.13.37.35.7.65.96.3.26.68.4 1.08.4H21v4h-.1A1.7 1.7 0 0 0 19.4 15Z"/>',
    panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16"/>',
    download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>',
    tools: '<path d="M14.7 6.3a4 4 0 0 0-5-5L12 3.6 9.6 6 7.3 3.7a4 4 0 0 0 5 5L5 16l-1 4 4-1 7.3-7.3a4 4 0 0 0 5-5L18 9l-2.4-2.4 2.3-2.3a4 4 0 0 0-3.2 2Z"/>',
    preview: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7"/><path d="M14 3v5h5"/><circle cx="16" cy="15" r="3"/><path d="m18.2 17.2 2.3 2.3"/>',
    paperclip: '<path d="m21.4 11.6-8.9 8.9a6 6 0 0 1-8.5-8.5l9.5-9.5a4 4 0 0 1 5.7 5.7l-9.5 9.5a2 2 0 1 1-2.8-2.8l8.8-8.8"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    close: '<path d="M18 6 6 18M6 6l12 12"/>',
    more: '<circle cx="12" cy="5" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="19" r="1" fill="currentColor" stroke="none"/>',
    pin: '<path d="m12 17-5 4 1.5-7L4 9.5l6.2-.7L12 3l1.8 5.8 6.2.7-4.5 4.5L17 21l-5-4Z"/>',
    pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4L16.5 3.5Z"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6"/>',
    power: '<path d="M12 2v10"/><path d="M18.4 5.6a8 8 0 1 1-12.8 0"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    eyeOff: '<path d="m3 3 18 18M10.6 6.2A11.8 11.8 0 0 1 12 6c6.5 0 10 6 10 6a17.2 17.2 0 0 1-2.1 2.8M6.6 6.6C3.6 8.5 2 12 2 12s3.5 6 10 6a10 10 0 0 0 4-.8M9.9 9.9a3 3 0 0 0 4.2 4.2"/>'
  };

  function uiIcon(name, size = 16, className = "") {
    const iconPaths = paths[name] || paths.plus;
    return `<svg class="ui-icon${className ? ` ${className}` : ""}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths}</svg>`;
  }

  core.icons = Object.freeze({ paths: Object.freeze(paths), uiIcon });
})(window);
