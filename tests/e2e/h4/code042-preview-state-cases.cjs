const assert = require("node:assert/strict");
const path = require("node:path");

// Native DOM plus deterministic transport/storage. No application test hooks.
module.exports = async function stateCases(browser, baseUrl) {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.route("**/__preview_state_fixture", (route) => route.fulfill({ contentType: "text/html", body: `<!doctype html>
      <div id="workbench"><div id="previewTabs"></div><div id="filePreview"></div></div>
      <div id="previewTitle"></div><div id="previewMeta"></div><div id="previewLanguage"></div><div id="previewModeActions"></div>
      <button id="refreshPreview"></button><button id="copyPreview"></button><button id="togglePreview"></button><button id="closePreview"></button><div id="previewResizer"></div>` }));
    await page.goto(baseUrl + "/__preview_state_fixture");
    await page.evaluate(() => { window.Code = { features: {} }; });
    await page.addScriptTag({ path: path.resolve(__dirname, "../../..", "src/features/preview.js") });
    const result = await page.evaluate(async () => {
      const assertions = [];
      const check = (condition, name) => { if (!condition) throw new Error(name); assertions.push(name); };
      const store = new Map(), messages = [], held = [], calls = [];
      let failStorage = false, delay = false, sourceId = "a".repeat(32), incarnation = "b".repeat(32);
      const storage = { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => {
        if (failStorage) throw new Error("quota"); store.set(key, value);
      } };
      const state = { sessionId: "A", previewWidth: 420 };
      const elements = Object.fromEntries(["workbench", "filePreview", "previewTitle", "previewMeta", "previewLanguage", "previewModeActions",
        "refreshPreview", "copyPreview", "togglePreview", "closePreview", "previewResizer"].map((id) => [id, document.getElementById(id)]));
      const digest = async (value) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)))].map((n) => n.toString(16).padStart(2,"0")).join("");
      const apiJson = async (url, options = {}) => {
        calls.push(url);
        if (url === "/api/preview/context") {
          const body = JSON.parse(options.body);
          return { dataSourceId: sourceId, sessionId: body.sessionId, sessionInstanceId: body.sessionId ? incarnation : body.draftId,
            draftId: body.draftId, contextRevision: "context", serverInstanceId: "process" };
        }
        const request = new URL(url, location.origin), name = request.searchParams.get("path").split("/").pop();
        const data = { name, path: name, canonicalAbsolutePath: `/fixture/${name}`, locator: `/fixture/${name}`,
          fileKey: await digest(name), contentRevision: name, content: name, size: name.length, binary: false };
        if (delay) return new Promise((resolve, reject) => held.push({resolve: () => resolve(data), reject}));
        return data;
      };
      const options = { state, elements, storage, apiJson,
        renderMarkdown: (s) => s, showToast: (s) => messages.push(s) };
      const feature = window.Code.features.preview.createPreviewFeature(options);
      feature.bind();
      await feature.restore();
      delay = true;
      const slowExplicit = feature.loadFile("slow-explicit.txt", undefined, {newTab:true});
      while (!held.length) await new Promise((r) => setTimeout(r, 0));
      delay = false; await feature.loadFile("fast-explicit.txt", undefined, {newTab:true});
      held.shift().resolve(); await slowExplicit;
      check([...document.querySelectorAll("#previewTabs [role=tab]")].map((tab)=>tab.textContent).join(",") === "slow-explicit.txt,fast-explicit.txt"
        && document.querySelector("#previewTabs [aria-selected=true]").textContent === "fast-explicit.txt",
        "slow explicit open keeps its tab and creation order without taking focus");
      const ids = [...document.querySelectorAll("#previewTabs [role=tab]")].map((tab)=>tab.dataset.previewTab);
      ids.forEach((id)=>feature.closeTab(id));
      const linkA = feature.captureOpenIntent();
      const linkB = feature.captureOpenIntent();
      await feature.loadFile("link-b.txt", undefined, {newTab:true,intent:linkB});
      check(feature.isOpenIntentCurrent(linkA, true), "slow explicit link probe remains in scope");
      await feature.loadFile("link-a.txt", undefined, {newTab:true,intent:linkA});
      check([...document.querySelectorAll("#previewTabs [role=tab]")].map((tab)=>tab.textContent).join(",") === "link-a.txt,link-b.txt"
        && document.querySelector("#previewTabs [aria-selected=true]").textContent === "link-b.txt",
        "out-of-order link probes keep both explicit intents and latest focus");
      [...document.querySelectorAll("#previewTabs [role=tab]")].map((tab)=>tab.dataset.previewTab).forEach((id)=>feature.closeTab(id));
      await feature.loadFile("a.txt");
      delay = true;
      const old = feature.loadFile("late.txt");
      while (!held.length) await new Promise((r) => setTimeout(r, 0));
      feature.beginNavigation(); state.sessionId = "B"; delay = false; await feature.restore();
      await feature.loadFile("b.txt"); held.shift().resolve(); await old;
      check(elements.filePreview.textContent.includes("b.txt") && !elements.filePreview.textContent.includes("late.txt"), "late response cannot cross session");
      delay = true;
      const failed = feature.loadFile("late-error.txt");
      while (!held.length) await new Promise((r) => setTimeout(r, 0));
      feature.beginNavigation(); state.sessionId = "A"; delay = false; await feature.restore();
      held.shift().reject(new Error("old error")); await failed;
      check(elements.filePreview.textContent.includes("a.txt"), "late error cannot replace restored content");
      feature.close();
      const countBefore = calls.length;
      await new Promise((r) => setTimeout(r, 3200));
      check(calls.length === countBefore && elements.filePreview.querySelectorAll("img,iframe,.code-line").length === 0, "closed pane has no renderer or refresh");
      await feature.toggle();
      check(elements.filePreview.textContent.includes("a.txt"), "closing pane preserves descriptors");
      for (let index=0; index<19; index++) await feature.loadFile(`limit-${index}.txt`, undefined, {newTab:true});
      await feature.loadFile("overflow.txt", undefined, {newTab:true});
      check(document.querySelectorAll("#previewTabs [role=tab]").length === 20 && messages.includes("previewTabLimit"), "20-tab limit preserves existing files");
      const beforeFailure = store.get("code-preview-workspaces-v1"); failStorage = true;
      await feature.loadFile("replacement.txt");
      check(elements.filePreview.textContent.includes("replacement.txt") && store.get("code-preview-workspaces-v1") === beforeFailure
        && messages.filter((m) => m === "previewStateUnsaved").length === 1, "storage failure stays usable and warns once");
      failStorage = false;
      feature.beginNavigation(); incarnation = "c".repeat(32); await feature.restore();
      check(document.querySelectorAll("#previewTabs [role=tab]").length === 0, "same id new incarnation does not inherit");
      await feature.loadFile("new-identity.txt");
      feature.beginNavigation(); sourceId = "d".repeat(32); await feature.restore();
      check(document.querySelectorAll("#previewTabs [role=tab]").length === 0, "new source does not inherit");
      feature.beginNavigation(); state.sessionId = null; await feature.newDraft();
      await feature.loadFile("draft.txt");
      const creation = feature.beginNavigation();
      check(feature.contextWillChange() === null, "saveRoot during creation does not begin a second navigation");
      state.sessionId = "created"; await feature.restore(creation);
      check(elements.filePreview.textContent.includes("draft.txt"), "own draft transfers once into created session");
      feature.beginNavigation(); state.sessionId = null; await feature.newDraft();
      check(document.querySelectorAll("#previewTabs [role=tab]").length === 0, "next draft starts empty");
      // Existing future formats remain byte-for-byte intact.
      feature.beginNavigation(); store.set("code-preview-workspaces-v1", '{"version":99}');
      state.sessionId = "future"; await feature.restore(); await feature.loadFile("ephemeral.txt");
      check(store.get("code-preview-workspaces-v1") === '{"version":99}', "unknown store is preserved");
      feature.close();
      store.clear(); store.set("code-preview-open", "1"); store.set("code-preview-path", "legacy.txt");
      state.sessionId = "legacy";
      const legacy = window.Code.features.preview.createPreviewFeature(options);
      failStorage = true; await legacy.restore();
      check(!store.has("code-preview-workspaces-v1") && store.get("code-preview-path") === "legacy.txt", "failed migration preserves legacy state");
      failStorage = false; await legacy.restore();
      check(JSON.parse(store.get("code-preview-workspaces-v1")).migrated && elements.filePreview.textContent.includes("legacy.txt")
        && store.get("code-preview-open") === "1", "successful migration commits marker and preserves old keys");
      legacy.beginNavigation(); state.sessionId = "after-legacy"; await legacy.restore();
      check(document.querySelectorAll("#previewTabs [role=tab]").length === 0, "legacy state is consumed once across sessions");
      legacy.close(); store.clear();
      store.set("code-preview-workspaces-v1", JSON.stringify({version:1,records:Object.fromEntries(
        Array.from({length:50}, (_,i) => [`record-${i}`, {tabs:[],mru:[],active:null,reuse:null,paneOpen:false}]))}));
      state.sessionId = "capacity";
      const capacity = window.Code.features.preview.createPreviewFeature(options);
      await capacity.restore(); await capacity.loadFile("memory-only.txt");
      check(Object.keys(JSON.parse(store.get("code-preview-workspaces-v1")).records).length === 50
        && elements.filePreview.textContent.includes("memory-only.txt"), "50-record limit degrades without eviction");
      capacity.close(); store.clear();
      const oversized = JSON.stringify({version:1,records:{},padding:"x".repeat(1048576)});
      store.set("code-preview-workspaces-v1", oversized); state.sessionId = "large-store";
      const largeStore = window.Code.features.preview.createPreviewFeature(options);
      await largeStore.restore(); await largeStore.loadFile("memory-only.txt");
      check(store.get("code-preview-workspaces-v1") === oversized, "1MiB limit preserves oversized store");
      largeStore.close();
      return { assertions, messages, requestCount: calls.length };
    });
    assert(result.assertions.length >= 11);
    return result;
  } finally { await context.close(); }
};
