(function registerSessionImportFeature(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.features) throw new Error("Code namespace must load before session import feature");

  function createImportCounts() {
    return {
      created: 0,
      updated: 0,
      snapshot: 0,
      unchanged: 0,
      continued: 0,
      failed: 0,
    };
  }

  function countImportAction(counts, result) {
    const action = result?.action;
    if (action === "updated") counts.updated++;
    else if (action === "snapshot-created") counts.snapshot++;
    else if (action === "unchanged") counts.unchanged++;
    else if (action === "continued") counts.continued++;
    else counts.created++;
  }

  function normalizeFailure(error, item) {
    const retryable = error?.retryable === true;
    return {
      item,
      sourcePath: String(item?.sourcePath || ""),
      title: String(item?.title || ""),
      errorCode: String(error?.errorCode || "import_failed"),
      message: String(error?.message || "Import failed"),
      retryable,
    };
  }

  function createImportBatchRunner(options = {}) {
    const importOne = options.importOne;
    if (typeof importOne !== "function") {
      throw new Error("session import batch runner requires importOne");
    }

    const onProgress = typeof options.onProgress === "function"
      ? options.onProgress
      : () => {};
    const yieldControl = typeof options.yieldControl === "function"
      ? options.yieldControl
      : () => new Promise((resolve) => global.setTimeout(resolve, 0));
    let activeBatch = null;

    function snapshot(batch, phase) {
      return {
        phase,
        source: batch.source,
        mode: batch.mode,
        running: batch.running,
        cancelRequested: batch.cancelRequested,
        total: batch.total,
        processed: batch.processed,
        cancelled: batch.cancelled,
        current: batch.current,
        counts: {...batch.counts},
        failures: batch.failures.map((failure) => ({...failure})),
      };
    }

    function emit(batch, phase) {
      const currentSnapshot = snapshot(batch, phase);
      try {
        onProgress(currentSnapshot);
      } catch (error) {
        // Rendering must never interrupt a batch or cause an item to be replayed.
      }
      return currentSnapshot;
    }

    function cancel() {
      if (!activeBatch || !activeBatch.running) return false;
      if (activeBatch.cancelRequested) return true;
      activeBatch.cancelRequested = true;
      emit(activeBatch, "stopping");
      return true;
    }

    async function run({source, items, mode = "import"} = {}) {
      if (activeBatch?.running) {
        const error = new Error("An import batch is already running");
        error.errorCode = "import_batch_running";
        error.retryable = false;
        throw error;
      }

      const batchItems = Array.isArray(items) ? items.filter(Boolean).slice() : [];
      const batch = {
        source: String(source || ""),
        mode,
        items: batchItems,
        total: batchItems.length,
        processed: 0,
        cancelled: 0,
        counts: createImportCounts(),
        failures: [],
        current: null,
        cancelRequested: false,
        running: true,
      };
      activeBatch = batch;
      emit(batch, "started");

      try {
        for (let index = 0; index < batch.items.length; index++) {
          if (batch.cancelRequested) break;

          const item = batch.items[index];
          batch.current = item;
          emit(batch, "item-started");
          try {
            const result = await importOne(batch.source, item);
            countImportAction(batch.counts, result);
          } catch (error) {
            batch.counts.failed++;
            batch.failures.push(normalizeFailure(error, item));
          }
          batch.processed++;
          batch.current = null;
          emit(batch, "item-finished");

          if (batch.cancelRequested) break;
          if (index < batch.items.length - 1) await yieldControl();
        }

        batch.cancelled = batch.cancelRequested
          ? Math.max(0, batch.total - batch.processed)
          : 0;
        batch.running = false;
        return emit(batch, batch.cancelled ? "cancelled" : "completed");
      } finally {
        batch.running = false;
        if (activeBatch === batch) activeBatch = null;
      }
    }

    return Object.freeze({
      run,
      cancel,
      isRunning: () => !!activeBatch?.running,
      snapshot: () => activeBatch ? snapshot(activeBatch, "snapshot") : null,
    });
  }

  Code.features.sessionImport = Object.freeze({
    createImportBatchRunner,
    createImportCounts,
  });
})(window);
