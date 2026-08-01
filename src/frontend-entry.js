// Stage 6A compatibility entry.
// Keep this order identical to the internal classic scripts in index.html.
import "./core/namespace.js";
import "./core/state.js";
import "./core/platform.js";
import "./core/icons.js";
import "./core/utils.js";
import "./core/i18n.js";
import "./core/theme-engine.js";
import "./services/notifications.js";
import "./services/api-client.js";
import "./services/persistence.js";
import "./ui/diff.js";
import "./ui/markdown.js";
import "./ui/timeline.js";
import "./ui/messages.js";
import "./ui/panels.js";
import "./features/sessions.js";
import "./features/branches.js";
import "./features/settings.js";
import "./features/skills-memory.js";
import "./features/preview.js";
import "./features/files.js";
import "./features/session-import.js";
import "./agent/model-request.js";
import "./agent/tools.js";
import "./agent/permissions.js";
import "./agent/questionnaire.js";
import "./agent/subagents.js";
import "./agent/compaction.js";
import "./agent/model-stream.js";
import "../agent-runtime.js";
import "../app.js";

window.Code.frontendBundleLoaded = true;
