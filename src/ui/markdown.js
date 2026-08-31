(function registerMarkdownUi(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.ui) throw new Error("Code namespace must load before markdown UI");

  const LANG_LABELS = Object.freeze({
    js: "JavaScript", javascript: "JavaScript", jsx: "JSX", ts: "TypeScript", typescript: "TypeScript",
    tsx: "TSX", py: "Python", python: "Python", html: "HTML", css: "CSS", json: "JSON",
    md: "Markdown", markdown: "Markdown", sh: "Shell", bash: "Bash", zsh: "Zsh",
    yaml: "YAML", yml: "YAML", sql: "SQL", java: "Java", c: "C", cpp: "C++", "c++": "C++",
    go: "Go", rs: "Rust", rust: "Rust", rb: "Ruby", php: "PHP", swift: "Swift",
    kt: "Kotlin", kotlin: "Kotlin", dockerfile: "Dockerfile", toml: "TOML", ini: "INI",
    diff: "Diff", text: "text", plaintext: "text",
  });

  function langLabel(lang) {
    const key = String(lang || "").toLowerCase();
    return LANG_LABELS[key] || key || "text";
  }

  const ADMONITION_TYPES = Object.freeze(["note", "tip", "important", "warning", "caution"]);

  function slugify(text) {
    const slug = String(text || "")
      .toLowerCase().trim()
      .replace(/[^\w\u4e00-\u9fa5]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .replace(/-{2,}/g, "-");
    return slug || "section";
  }

  const IMAGE_PATH_EXTENSIONS = /\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i;

  // Common compound public suffixes that must not be split when deriving the
  // registrable-domain fallback chain for favicon lookups (R016).
  const COMPOUND_SUFFIXES = Object.freeze(new Set([
    "com.cn", "org.cn", "net.cn", "gov.cn", "edu.cn", "co.uk", "org.uk",
    "com.hk", "com.tw", "com.au", "com.br", "com.mx", "co.jp", "co.za",
  ]));

  /**
   * Favicon host fallback chain: exact host first, then strip leading www.
   * and drop leftmost labels until the registrable domain (last two parts, or
   * three parts when the last two form a compound public suffix) is reached.
   * chat.deepseek.com → [chat.deepseek.com, deepseek.com];
   * www.doubao.com → [www.doubao.com, doubao.com];
   * b.baidu.com.cn → [b.baidu.com.cn, baidu.com.cn] (com.cn never split).
   */
  function faviconHostCandidates(host) {
    const h = String(host || "").toLowerCase().trim().replace(/^\.+|\.+$/g, "");
    if (!h) return [];
    const out = [h];
    let current = h;
    if (current.startsWith("www.")) {
      current = current.slice(4);
      if (current && !out.includes(current)) out.push(current);
    }
    const parts = current.split(".");
    while (parts.length > 2) {
      parts.shift();
      const candidate = parts.join(".");
      if (candidate && !out.includes(candidate)) out.push(candidate);
      if (parts.length === 3 && COMPOUND_SUFFIXES.has(parts.slice(1).join("."))) {
        break; // registrable domain reached (protected compound suffix)
      }
    }
    return out;
  }

  function normalizePathSegments(parts, minimumDepth = 0) {
    const normalized = [];
    for (const part of parts) {
      if (!part || part === ".") continue;
      if (part === "..") {
        if (normalized.length <= minimumDepth) return null;
        normalized.pop();
        continue;
      }
      normalized.push(part);
    }
    return normalized;
  }

  /**
   * Canonical identity for local references emitted in final answers.
   * Relative/bare paths are deliberately rejected instead of being resolved
   * against the current project. Windows drive, /C:/, UNC and POSIX absolute
   * forms are normalized to forward slashes without touching the filesystem.
   */
  function normalizeAbsolutePath(value) {
    const raw = String(value || "").trim();
    if (!raw || /[\u0000-\u001f]/.test(raw)) return "";
    const path = raw.replace(/\\/g, "/");
    const drive = path.match(/^\/?([A-Za-z]):\/(.*)$/);
    if (drive) {
      const parts = normalizePathSegments(drive[2].split("/"));
      return parts ? `${drive[1].toUpperCase()}:/${parts.join("/")}` : "";
    }
    if (path.startsWith("//")) {
      const parts = normalizePathSegments(path.slice(2).split("/"), 2);
      if (!parts || parts.length < 2) return "";
      return `//${parts.join("/")}`;
    }
    if (path.startsWith("/")) {
      const parts = normalizePathSegments(path.slice(1).split("/"));
      return parts ? `/${parts.join("/")}` : "";
    }
    return "";
  }

  function isClickablePath(value) {
    return Boolean(normalizeAbsolutePath(value));
  }

  const PREVIEW_IMAGE_EXT = Object.freeze(["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"]);
  const PREVIEW_DERIVED_EXT = Object.freeze(["tif", "tiff"]);
  const BINARY_EXT = Object.freeze([
    "exe", "dll", "so", "zip", "rar", "7z", "gz", "tar", "pdf",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "mp3", "mp4", "wav", "avi", "mkv", "mov", "webm", "flac",
    "iso", "msi", "apk", "jar", "class",
  ]);

  /**
   * Preview-vs-external routing category for a local path (answer-render R008):
   * image → internal image preview; derived → internal derived preview;
   * binary → external system open; text (default) → internal code/text preview.
   */
  function classifyLocalPath(path) {
    const ext = (String(path || "").split(".").pop() || "").toLowerCase();
    if (PREVIEW_IMAGE_EXT.includes(ext)) return "image";
    if (PREVIEW_DERIVED_EXT.includes(ext)) return "derived";
    if (BINARY_EXT.includes(ext)) return "binary";
    return "text";
  }

  /**
   * Parse a code/file reference with an optional line suffix:
   * `path (line 91)`, `path (91)`, `path（91）`, `path:123`. Returns
   * { path, line } or null when the text is not a recognizable reference.
   */
  function parseLineRef(value) {
    const s = String(value || "").trim();
    if (!s) return null;
    let path = s;
    let line = null;
    const paren = s.match(/^(.+?)[\s]*[（(](?:line\s*)?(\d+)[)）]$/i);
    if (paren) {
      path = paren[1].trim();
      line = Number(paren[2]);
    } else {
      const colon = s.match(/^(.+?):(\d+)$/);
      if (colon && /[.\\/]/.test(colon[1])) {
        path = colon[1].trim();
        line = Number(colon[2]);
      }
    }
    const normalizedPath = normalizeAbsolutePath(path);
    if (!line || !normalizedPath) return null;
    return { path: normalizedPath, line };
  }

  function isImagePath(path) {
    return IMAGE_PATH_EXTENSIONS.test(String(path || ""));
  }

  /**
   * Recognise every absolute-path shape used on Windows:
   * drive letters (C:\\...), forward-slash drive variants (/C:/...),
   * backslash drive variants (\\C:\\...) and UNC shares (//server/share).
   * Everything else (relative paths, plain names) is project-scoped.
   */
  function isAbsolutePath(path) {
    return Boolean(normalizeAbsolutePath(path));
  }

  /**
   * Short display alias for a clickable local path (A):
   * - project-scoped relative path: shown as-is (already an alias);
   * - absolute path inside the project root: shown relative to the root;
   * - absolute path outside the project root: shown as the file name.
   */
  function pathAlias(path, projectRoot) {
    const p = String(path || "").trim();
    if (!p) return p;
    const normalized = normalizeAbsolutePath(p);
    if (!normalized) return p;
    const root = normalizeAbsolutePath(projectRoot);
    if (root && normalized.toLowerCase().startsWith(root.toLowerCase() + "/")) {
      return normalized.slice(root.length + 1);
    }
    return normalized.split("/").pop() || normalized;
  }

  const SYNTAX_PATTERNS = Object.freeze({
    json: [],
    javascript: [
      [/\b(function|const|let|var|return|if|else|for|while|async|await|class|import|export|from|default|try|catch|throw|new|this|typeof|instanceof|of|in|null|undefined|true|false)\b/g, "syn-kw"],
      [/(["'`])(?:\\.|(?!\1).)*?\1/g, "syn-str"],
      [/(\/\/.*$)/gm, "syn-com"],
      [/(\/\*[\s\S]*?\*\/)/g, "syn-com"],
      [/\b(\d+\.?\d*)\b/g, "syn-num"],
      [/(=>|\b(?:===?|!==?|[+\-*/%])\b)/g, "syn-op"],
    ],
    js: "javascript",
    jsx: "javascript",
    ts: "javascript",
    typescript: "javascript",
    python: [
      [/\b(def|class|return|if|elif|else|for|while|import|from|as|try|except|raise|with|and|or|not|in|is|None|True|False|pass|break|continue|yield|async|await|lambda|global|nonlocal)\b/g, "syn-kw"],
      [/(["'])(?:\\.|(?!\1).)*?\1/g, "syn-str"],
      [/(#.*$)/gm, "syn-com"],
      [/("""[\s\S]*?""")|('''[\s\S]*?''')/g, "syn-com"],
      [/\b(\d+\.?\d*)\b/g, "syn-num"],
      [/@\w+/g, "syn-op"],
    ],
    py: "python",
    html: [
      [/(<\/?)(\w+)/g, "syn-kw"],
      [/("(?:[^"\\]|\\.)*")/g, "syn-str"],
      [/(<!--[\s\S]*?-->)/g, "syn-com"],
      [/(\w+)=/g, "syn-fn"],
    ],
    css: [
      [/([.#]?[a-zA-Z_-]+)(?=\s*\{)/g, "syn-fn"],
      [/(:(?:[^;{]+))/g, "syn-str"],
      [/(\/\*[\s\S]*?\*\/)/g, "syn-com"],
      [/\b(\d+\.?\d*(?:px|em|rem|%|vh|vw|s)?)\b/g, "syn-num"],
      [/\b(important|bold|normal|italic|none|block|inline|flex|grid|hidden|visible|auto|inherit|initial)\b/g, "syn-kw"],
    ],
  });

  function resolveSyntaxPatterns(lang) {
    if (!lang) return null;
    const patterns = SYNTAX_PATTERNS[lang];
    if (!patterns) return null;
    if (typeof patterns === "string") return resolveSyntaxPatterns(patterns);
    return Array.isArray(patterns) ? patterns : null;
  }

  function createTokenFactory(source, label) {
    let prefix = `\uE000CODE_${label}_`;
    while (source.includes(prefix)) prefix += "_";
    return (index) => `${prefix}${index}\uE001`;
  }

  function protectCodeRegions(value) {
    const original = String(value || "");
    const regions = [];
    const tokenFor = createTokenFactory(original, "REGION");
    const protect = (match) => {
      const token = tokenFor(regions.length);
      regions.push({ token, value: match });
      return token;
    };
    // Fenced blocks are removed before inline spans so later projections can
    // never reinterpret URLs, math delimiters, or backticks inside code.
    const lines = original.split("\n");
    const projectedLines = [];
    for (let index = 0; index < lines.length; index += 1) {
      const opening = lines[index].match(/^[ \t]{0,3}(`{3,}|~{3,})[^\n]*$/);
      if (!opening) {
        projectedLines.push(lines[index]);
        continue;
      }
      const fenceChar = opening[1][0];
      const fenceLength = opening[1].length;
      const block = [lines[index]];
      while (index + 1 < lines.length) {
        index += 1;
        block.push(lines[index]);
        const closing = lines[index].match(/^[ \t]{0,3}(`+|~+)[ \t]*$/);
        if (closing && closing[1][0] === fenceChar && closing[1].length >= fenceLength) break;
      }
      projectedLines.push(protect(block.join("\n")));
    }
    let source = projectedLines.join("\n");
    source = source.replace(/(`+)([\s\S]*?)\1/g, protect);
    return {
      source,
      restore(projected) {
        let restored = projected;
        regions.forEach((region) => {
          restored = restored.split(region.token).join(region.value);
        });
        return restored;
      },
    };
  }

  function explicitMarkdownLinkEnd(source, start) {
    let labelStart = start;
    if (source[start] === "!" && source[start + 1] === "[") labelStart += 1;
    if (source[labelStart] !== "[") return -1;

    let bracketDepth = 0;
    for (let index = labelStart; index < source.length; index += 1) {
      const char = source[index];
      if (char === "\\") {
        index += 1;
        continue;
      }
      if (char === "[") bracketDepth += 1;
      else if (char === "]") {
        bracketDepth -= 1;
        if (bracketDepth !== 0) continue;
        let cursor = index + 1;
        while (source[cursor] === " " || source[cursor] === "\t") cursor += 1;
        if (source[cursor] !== "(") return -1;
        let parenDepth = 1;
        for (cursor += 1; cursor < source.length; cursor += 1) {
          const destinationChar = source[cursor];
          if (destinationChar === "\\") {
            cursor += 1;
            continue;
          }
          if (destinationChar === "(") parenDepth += 1;
          else if (destinationChar === ")") {
            parenDepth -= 1;
            if (parenDepth === 0) return cursor + 1;
          }
        }
        return -1;
      }
    }
    return -1;
  }

  function isUnicodePunctuationBoundary(char) {
    return Boolean(char) && /^\p{P}$/u.test(char);
  }

  function trimBareUrlTail(candidate) {
    let url = candidate;
    let tail = "";
    while (/[.,;:!]$/.test(url)) {
      tail = url.slice(-1) + tail;
      url = url.slice(0, -1);
    }
    const pairs = [["(", ")"], ["[", "]"], ["{", "}"]];
    for (const [opening, closing] of pairs) {
      while (url.endsWith(closing)) {
        const opens = [...url].filter((char) => char === opening).length;
        const closes = [...url].filter((char) => char === closing).length;
        if (closes <= opens) break;
        tail = closing + tail;
        url = url.slice(0, -1);
      }
    }
    return { url, tail };
  }

  /**
   * marked's bare-URL tokenizer accepts Unicode letters as part of an href, so
   * `https://a.test。下一项` becomes one encoded link. Project only ordinary
   * Markdown text whose ASCII HTTP(S) URL is immediately followed by explicit
   * Unicode punctuation into a standard angle autolink. Unicode letters stay
   * under marked's existing behavior so legitimate `/中文` and `/한글` paths
   * are never truncated. Code, explicit links, images, existing angle
   * autolinks, and raw HTML are copied byte-for-byte.
   */
  function projectCjkBareUrlBoundaries(value) {
    const original = String(value || "");
    if (!original || !/https?:\/\//i.test(original)) return original;
    const protectedCode = protectCodeRegions(original);
    const source = protectedCode.source;
    let projected = "";
    let index = 0;

    while (index < source.length) {
      if (source[index] === "[" || (source[index] === "!" && source[index + 1] === "[")) {
        const explicitEnd = explicitMarkdownLinkEnd(source, index);
        if (explicitEnd > index) {
          projected += source.slice(index, explicitEnd);
          index = explicitEnd;
          continue;
        }
      }
      if (source[index] === "<") {
        const angleEnd = source.indexOf(">", index + 1);
        if (angleEnd >= 0) {
          projected += source.slice(index, angleEnd + 1);
          index = angleEnd + 1;
          continue;
        }
      }

      const rest = source.slice(index);
      const prefix = rest.match(/^https?:\/\//i)?.[0] || "";
      const previous = index > 0 ? source[index - 1] : "";
      if (prefix && !/[A-Za-z0-9_]/.test(previous)) {
        let end = index + prefix.length;
        while (end < source.length) {
          const char = source[end];
          const code = char.codePointAt(0);
          if (code <= 0x20 || code >= 0x7f || char === "<" || char === ">" || char === "`") break;
          end += char.length;
        }
        if (end > index + prefix.length && isUnicodePunctuationBoundary(source[end])) {
          const { url, tail } = trimBareUrlTail(source.slice(index, end));
          const UrlCtor = global.URL || globalThis.URL;
          let valid = false;
          try {
            const parsed = new UrlCtor(url);
            valid = /^https?:$/i.test(parsed.protocol) && Boolean(parsed.hostname);
          } catch (_) { /* keep marked's original behavior */ }
          if (valid) {
            projected += `<${url}>${tail}`;
            index = end;
            continue;
          }
        }
      }

      projected += source[index];
      index += 1;
    }
    return protectedCode.restore(projected);
  }

  function createMarkdownFeature(options = {}) {
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const renderDiff = options.renderDiff || ((text) => escapeHtml(text));
    const markedRef = options.marked || global.marked;
    const random = options.random || Math.random;

    if (!markedRef?.Renderer || typeof markedRef.parse !== "function" || typeof markedRef.setOptions !== "function") {
      throw new Error("markdown UI requires marked");
    }

    function highlightSyntax(code, lang) {
      const source = String(code ?? "");
      if (lang === "json") {
        const tokenPattern = /"(?:\\.|[^"\\])*"|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b|\b(?:true|false|null)\b/g;
        let result = "";
        let cursor = 0;
        for (const match of source.matchAll(tokenPattern)) {
          const index = match.index ?? 0;
          const token = match[0];
          result += escapeHtml(source.slice(cursor, index));
          let className = "syn-num";
          if (token.startsWith('"')) {
            className = /^\s*:/.test(source.slice(index + token.length)) ? "syn-key" : "syn-str";
          } else if (/^(?:true|false|null)$/.test(token)) {
            className = "syn-kw";
          }
          result += `<span class="${className}">${escapeHtml(token)}</span>`;
          cursor = index + token.length;
        }
        return result + escapeHtml(source.slice(cursor));
      }

      const patterns = resolveSyntaxPatterns(lang);
      if (!patterns) return escapeHtml(source);
      const tokens = [];
      patterns.forEach(([regex, className], priority) => {
        const flags = regex.flags.includes("g") ? regex.flags : `${regex.flags}g`;
        const matcher = new RegExp(regex.source, flags);
        for (const match of source.matchAll(matcher)) {
          const text = match[0];
          if (!text) continue;
          const start = match.index ?? 0;
          tokens.push({ start, end: start + text.length, text, className, priority });
        }
      });
      tokens.sort((a, b) => a.start - b.start || b.end - a.end || a.priority - b.priority);
      let cursor = 0;
      let result = "";
      tokens.forEach((token) => {
        if (token.start < cursor) return;
        result += escapeHtml(source.slice(cursor, token.start));
        result += `<span class="${token.className}">${escapeHtml(token.text)}</span>`;
        cursor = token.end;
      });
      return result + escapeHtml(source.slice(cursor));
    }

    function renderAnsi(text) {
      let stack = [];
      let result = escapeHtml(text).replace(/\x1b\[(\d+(?:;\d+)*)m/g, (_, codes) => {
        let html = "";
        while (stack.length) {
          html += "</span>";
          stack.pop();
        }
        codes.split(";").map(Number).forEach((code) => {
          if (code >= 30 && code <= 37) stack.push(`ansi-${code}`);
          else if (code === 1 || code === 3 || code === 4) stack.push(`ansi-${code}`);
        });
        stack.forEach((className) => { html += `<span class="${className}">`; });
        return html;
      });
      while (stack.length) {
        result += "</span>";
        stack.pop();
      }
      return result;
    }

    const renderer = new markedRef.Renderer();


    function renderInlineTokens(context, token) {
      if (context?.parser?.parseInline && Array.isArray(token.tokens)) {
        return context.parser.parseInline(token.tokens);
      }
      return escapeHtml(token.text || "");
    }

    function parseInlineSafe(parser, tokens) {
      if (parser?.parseInline && Array.isArray(tokens)) return parser.parseInline(tokens);
      return escapeHtml((tokens || []).map((t) => t?.text ?? "").join(""));
    }

    function parseBlocksSafe(parser, tokens) {
      if (parser?.parse && Array.isArray(tokens)) return parser.parse(tokens);
      return escapeHtml((tokens || []).map((t) => t?.text ?? "").join("\n"));
    }

    function normalizeAdmonitionBodyHtml(body) {
      return String(body || "").replace(
        /^\s*(<p>)(?:\s*<br\s*\/?>)+\s*/i,
        "$1",
      );
    }

    const headingIds = new Map();

    renderer.blockquote = function renderBlockquote(token) {
      const raw = String(token.text || "");
      const m = raw.match(/^\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(?:\n|$)/i);
      if (m && Array.isArray(token.tokens)) {
        const type = m[1].toLowerCase();
        // marked usually folds the whole quote into a single paragraph token;
        // strip the marker line from the first token instead of slicing it off.
        const rest = token.tokens.map((t, i) => {
          if (i !== 0) return t;
          const inner = Array.isArray(t.tokens) ? [...t.tokens] : null;
          if (!inner) return t;
          for (let k = 0; k < inner.length; k += 1) {
            if (typeof inner[k].text === "string" && inner[k].text.includes("[!")) {
              const nl = inner[k].text.indexOf("\n");
              inner[k] = nl >= 0 ? { ...inner[k], text: inner[k].text.slice(nl + 1) } : { ...inner[k], text: "" };
              break;
            }
          }
          const filtered = inner.filter((tk) => tk.text !== "");
          return filtered.length ? { ...t, tokens: filtered } : { ...t, tokens: filtered, text: "" };
        }).filter((t) => !(t.text === "" && (!Array.isArray(t.tokens) || t.tokens.length === 0)));
        const body = normalizeAdmonitionBodyHtml(parseBlocksSafe(this.parser, rest));
        // Title is filled by app.js from i18n (data-admonition attribute).
        return `<div class="admonition admonition-${type}"><div class="admonition-title" data-admonition="${type}"></div><div class="admonition-body">${body}</div></div>`;
      }
      return `<blockquote>${parseBlocksSafe(this.parser, token.tokens)}</blockquote>`;
    };

    renderer.heading = function renderHeading(token) {
      const level = token.depth;
      const text = parseInlineSafe(this.parser, token.tokens);
      const base = slugify(token.text);
      const seen = (headingIds.get(base) || 0) + 1;
      headingIds.set(base, seen);
      const id = seen > 1 ? `${base}-${seen}` : base;
      return `<h${level} id="${escapeHtml(id)}">${text}</h${level}>`;
    };

    let taskItemSequence = 0;

    function withoutTaskCheckbox(tokens) {
      const body = Array.isArray(tokens) ? [...tokens] : [];
      if (body[0]?.type === "checkbox") {
        body.shift();
        return body;
      }
      if (Array.isArray(body[0]?.tokens) && body[0].tokens[0]?.type === "checkbox") {
        body[0] = { ...body[0], tokens: body[0].tokens.slice(1) };
      }
      return body;
    }

    renderer.list = function renderList(token) {
      const ordered = Boolean(token.ordered);
      const type = ordered ? "ol" : "ul";
      const start = Number(token.start);
      const startAttr = ordered && Number.isInteger(start) && start !== 1
        ? ` start="${start}"`
        : "";
      const hasTasks = token.items.some((item) => item.task);
      const className = `md-list md-list-${ordered ? "ordered" : "unordered"}${hasTasks ? " task-list" : ""}`;
      const body = token.items.map((item) => this.listitem(item)).join("");
      return `<${type} class="${className}"${startAttr}>\n${body}</${type}>\n`;
    };

    renderer.listitem = function renderListItem(token) {
      if (!token.task) return `<li>${parseBlocksSafe(this.parser, token.tokens)}</li>\n`;
      taskItemSequence += 1;
      const contentId = `md-task-content-${taskItemSequence}`;
      const checked = Boolean(token.checked);
      const checkbox = `<input class="task-list-checkbox" type="checkbox" disabled${checked ? " checked" : ""} aria-labelledby="${contentId}">`;
      const content = parseBlocksSafe(this.parser, withoutTaskCheckbox(token.tokens));
      return `<li class="task-list-item" data-task-state="${checked ? "checked" : "unchecked"}">${checkbox}<div class="task-list-content" id="${contentId}">${content}</div></li>\n`;
    };

    renderer.checkbox = function renderCheckbox(token) {
      return `<input class="task-list-checkbox" type="checkbox" disabled${token.checked ? " checked" : ""}>`;
    };

    function tableCellAttributes(cell) {
      const align = ["left", "center", "right"].includes(cell?.align) ? cell.align : "";
      return align
        ? ` align="${align}" data-align="${align}" class="md-align-${align}"`
        : "";
    }

    renderer.table = function renderTable(token) {
      const header = token.header.map((cell) => `<th scope="col"${tableCellAttributes(cell)}>${parseInlineSafe(this.parser, cell.tokens)}</th>`).join("");
      const body = token.rows.map((row) => `<tr>${row.map((cell) => `<td${tableCellAttributes(cell)}>${parseInlineSafe(this.parser, cell.tokens)}</td>`).join("")}</tr>`).join("");
      return `<div class="table-wrap" data-overflow="false"><div class="table-scroll" tabindex="-1"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div><span class="table-overflow-hint" aria-hidden="true">↔</span></div>`;
    };

    renderer.codespan = function renderCodeSpan({ text }) {
      const source = String(text || "");
      const escaped = escapeHtml(source);
      const ref = parseLineRef(source);
      if (ref) {
        return `<code class="clickable-path answer-local-path" data-path="${escapeHtml(ref.path)}" data-line="${ref.line}" title="Click to open">${escaped}</code>`;
      }
      const path = normalizeAbsolutePath(source);
      if (!path) return `<code>${escaped}</code>`;
      return `<code class="clickable-path answer-local-path" data-path="${escapeHtml(path)}" title="Click to open">${escaped}</code>`;
    };

    renderer.link = function renderLink(token) {
      const rawHref = String(token.href || "");
      const href = escapeHtml(rawHref);
      let title = token.title ? ` title="${escapeHtml(token.title)}"` : "";
      let inner = renderInlineTokens(this, token);
      if (!/^https?:\/\//i.test(rawHref)) {
        const localPath = normalizeAbsolutePath(rawHref);
        if (!localPath) return `<span class="local-link-text">${inner}</span>`;
        return `<a class="clickable-path answer-local-path local-path-link" href="#" data-path="${escapeHtml(localPath)}"${title}>${inner}</a>`;
      }
      // C: bare URL (link text equals the URL) shows the domain alias. The
      // full URL is shown by the custom sb-path-tooltip instead of the native
      // title (which duplicated it); an explicit markdown title ([text](url
      // "title")) is still kept because the author wrote it.
      const rawText = String(token.text || "");
      if (rawText === rawHref && /^https?:\/\//i.test(rawHref)) {
        try {
          const host = new URL(rawHref).hostname;
          if (host) inner = escapeHtml(host);
        } catch (_) { /* keep the original text */ }
      }
      // The icon slot ships with an inline link glyph so no blank gap ever
      // shows; bindExtLinkFavicons replaces it with the site favicon on load
      // or keeps it when every source fails.
      return `<a class="ext-link" href="${href}"${title} target="_blank" rel="noopener"><span class="link-ext-icon" data-favicon="" aria-hidden="true"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="6.5"/><path d="M1.5 8h13M8 1.5c2 1.8 3 3.9 3 6.5s-1 4.7-3 6.5c-2-1.8-3-3.9-3-6.5s1-4.7 3-6.5z"/></svg></span>${inner}</a>`;
    };

    renderer.image = function renderImage(token) {
      const source = String(token.href || "");
      const title = token.title ? ` title="${escapeHtml(token.title)}"` : "";
      const alt = escapeHtml(token.text || "");
      let src;
      let localPath = "";
      if (/^(https?:|data:|\/api\/)/i.test(source)) {
        src = source;
      } else {
        localPath = normalizeAbsolutePath(source);
        if (!localPath) return `<code>${escapeHtml(source)}</code>`;
        const extension = (localPath.split(".").pop() || "").toLowerCase();
        if (!/^(png|jpg|jpeg|gif|webp|svg|bmp|ico)$/i.test(extension)) {
          return `<code>${escapeHtml(localPath)}</code>`;
        }
        src = `/api/file?path=${encodeURIComponent(localPath)}&raw=1`;
      }
      const localClass = localPath ? " answer-local-image" : "";
      const localAttrs = localPath
        ? ` data-path="${escapeHtml(localPath)}" data-tooltip="${escapeHtml(localPath)}"`
        : "";
      return `<span class="msg-inline-img-slot${localClass}"${localAttrs} data-img-src="${escapeHtml(src)}" data-img-name="${escapeHtml((localPath || source).split("/").pop() || alt)}"><img src="${escapeHtml(src)}" alt="${alt}"${title} loading="lazy" class="msg-inline-img" data-message-image-preview></span>`;
    };

    renderer.code = function renderCodeBlock({ text, lang }) {
      if (lang === "diff" || lang === "diff ") return renderDiff(text);
      if (lang === "terminal" || lang === "ansi") {
        return `<div class="code-block"><div class="code-head"><span>terminal</span></div><div class="ansi-block">${renderAnsi(text)}</div></div>`;
      }
      const patterns = resolveSyntaxPatterns(lang);
      const lines = text.split("\n");
      const lineHtml = lines.map((line, index) => {
        const source = line || " ";
        const ref = parseLineRef(source);
        const highlighted = patterns ? highlightSyntax(source, lang) : escapeHtml(source);
        if (ref) {
          return `<span class="line-no">${index + 1}</span><code class="line-code"><code class="clickable-path answer-local-path code-ref" data-path="${escapeHtml(ref.path)}" data-line="${ref.line}" title="Click to open">${highlighted}</code></code>`;
        }
        return `<span class="line-no">${index + 1}</span><code class="line-code">${highlighted}</code>`;
      }).join("");
      const codeId = `cb-${random().toString(36).slice(2, 10)}`;
      return `<div class="code-block"><div class="code-head"><span class="lang-label">${escapeHtml(langLabel(lang))}</span><button class="copy-code" type="button" data-code-id="${codeId}">copy</button></div><pre class="code-lines" id="${codeId}">${lineHtml}</pre></div>`;
    };
    markedRef.setOptions({ renderer, breaks: true, gfm: true });

    function projectMath(value) {
      const source = String(value || "");
      if (!source || typeof global.katex === "undefined") {
        return { source, restore: (html) => html };
      }

      const protectedCode = protectCodeRegions(source);
      const expressions = [];
      const tokenFor = createTokenFactory(source, "MATH");
      const capture = (raw, math, displayMode) => {
        const token = tokenFor(expressions.length);
        expressions.push({ token, raw, math: math.trim(), displayMode });
        return token;
      };

      let projected = protectedCode.source;
      projected = projected.replace(/\$\$([\s\S]*?)\$\$/g, (raw, math) => capture(raw, math, true));
      projected = projected.replace(/\\\[([\s\S]*?)\\\]/g, (raw, math) => capture(raw, math, true));
      projected = projected.replace(/\$([^$\s](?:[^$\n]*[^$\s])?)\$/g, (raw, math) => capture(raw, math, false));
      projected = projected.replace(/\\\(([\s\S]*?)\\\)/g, (raw, math) => capture(raw, math, false));
      projected = protectedCode.restore(projected);

      return {
        source: projected,
        restore(html) {
          let restored = html;
          expressions.forEach(({ token, raw, math, displayMode }) => {
            let replacement;
            try {
              const rendered = global.katex.renderToString(math, { displayMode, throwOnError: true });
              const className = displayMode ? "math-block" : "math-inline";
              replacement = `<span class="${className}" data-latex="${escapeHtml(math)}">${rendered}</span>`;
            } catch (_) {
              replacement = escapeHtml(raw);
            }
            restored = restored.split(token).join(replacement);
          });
          return restored;
        },
      };
    }

    function renderMarkdownLite(text) {
      if (!text) return "";
      // Keep source semantics intact. Math is tokenized outside code, standard
      // Markdown is parsed once, and trusted KaTeX HTML is restored last. The
      // CJK projection only supplies a boundary that marked's URL tokenizer
      // otherwise lacks; it does not alter explicit Markdown or code regions.
      const math = projectMath(String(text));
      const bounded = projectCjkBareUrlBoundaries(math.source);
      return math.restore(markedRef.parse(bounded));
    }

    function setupMathCopyHandler(messagesEl) {
      if (!messagesEl) return;
      messagesEl.addEventListener("copy", (e) => {
        const sel = global.getSelection();
        if (!sel || sel.isCollapsed) return;
        const range = sel.getRangeAt(0);
        if (!messagesEl.contains(range.commonAncestorContainer)) return;

        const clone = range.cloneContents();
        const mathEls = clone.querySelectorAll(".math-inline, .math-block");
        mathEls.forEach((el) => {
          const latex = el.getAttribute("data-latex") || el.textContent || "";
          if (!latex) return;
          const isBlock = el.classList.contains("math-block");
          const replacement = isBlock ? `$$\n${latex}\n$$` : `$${latex}$`;
          el.replaceWith(global.document.createTextNode(replacement));
        });

        e.preventDefault();
        e.clipboardData.setData("text/plain", clone.textContent || "");
      });
    }

    return Object.freeze({
      highlightSyntax,
      renderAnsi,
      renderMarkdownLite,
      renderer,
      setupMathCopyHandler,
    });
  }

  Code.ui.markdown = Object.freeze({
    SYNTAX_PATTERNS,
    createMarkdownFeature,
    resolveSyntaxPatterns,
    pathAlias,
    isImagePath,
    isAbsolutePath,
    isClickablePath,
    normalizeAbsolutePath,
    parseLineRef,
    classifyLocalPath,
    faviconHostCandidates,
    projectCjkBareUrlBoundaries,
  });
})(window);
