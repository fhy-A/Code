(function initializeCodeApiClient(global) {
  "use strict";

  const services = global.Code && global.Code.services;
  if (!services) {
    throw new Error("Code services namespace must load before api client");
  }

  async function apiJson(url, options = {}) {
    const response = await global.fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });

    let data;
    try {
      data = await response.json();
    } catch (_) {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      data = {};
    }

    if (!response.ok) {
      const error = new Error(data.error || data?.error?.message || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }

    return data;
  }

  services.apiClient = Object.freeze({
    apiJson,
  });
})(window);
