(function registerMarkdownUi(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.ui) throw new Error("Code namespace must load before markdown UI");

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

    function isClickablePath(value) {
      const path = String(value || "").trim();
      return /\.\w{1,8}$/.test(path) || /^[\/\\]|[A-Za-z]:[\/\\]/.test(path);
    }

    function renderInlineTokens(context, token) {
      if (context?.parser?.parseInline && Array.isArray(token.tokens)) {
        return context.parser.parseInline(token.tokens);
      }
      return escapeHtml(token.text || "");
    }

    renderer.codespan = function renderCodeSpan({ text }) {
      const source = String(text || "");
      const escaped = escapeHtml(source);
      if (!isClickablePath(source)) return `<code>${escaped}</code>`;
      return `<code class="clickable-path" data-path="${escapeHtml(source.trim())}" title="Click to open">${escaped}</code>`;
    };

    renderer.link = function renderLink(token) {
      const href = escapeHtml(String(token.href || ""));
      const title = token.title ? ` title="${escapeHtml(token.title)}"` : "";
      return `<a href="${href}"${title} target="_blank" rel="noopener">${renderInlineTokens(this, token)}</a>`;
    };

    renderer.image = function renderImage(token) {
      const source = String(token.href || "");
      const title = token.title ? ` title="${escapeHtml(token.title)}"` : "";
      const alt = escapeHtml(token.text || "");
      if (/^(https?:|data:|\/api\/)/i.test(source)) {
        return `<img src="${escapeHtml(source)}" alt="${alt}"${title}>`;
      }
      const imagePath = source.replace(/\\/g, "/").replace(/^\.?\/?/, "");
      const extension = (imagePath.split(".").pop() || "").toLowerCase();
      if (!/^(png|jpg|jpeg|gif|webp|svg|bmp|ico)$/i.test(extension)) {
        return `<img src="${escapeHtml(source)}" alt="${alt}"${title}>`;
      }
      const apiUrl = `/api/file?path=${encodeURIComponent(imagePath)}&raw=1`;
      return `<img src="${apiUrl}" alt="${alt}"${title} loading="lazy" class="msg-inline-img" data-message-image-preview>`;
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
        const highlighted = patterns ? highlightSyntax(source, lang) : escapeHtml(source);
        return `<span class="line-no">${index + 1}</span><code class="line-code">${highlighted}</code>`;
      }).join("");
      const codeId = `cb-${random().toString(36).slice(2, 10)}`;
      return `<div class="code-block"><div class="code-head"><span>${escapeHtml(lang || "text")}</span><button class="copy-code" type="button" data-code-id="${codeId}">copy</button></div><pre class="code-lines" id="${codeId}">${lineHtml}</pre></div>`;
    };
    markedRef.setOptions({ renderer, breaks: true, gfm: true });

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
      // Fenced blocks are removed before inline spans so math delimiters and
      // backticks inside a block can never be reinterpreted.
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
      // Markdown is parsed once, and trusted KaTeX HTML is restored last.
      const math = projectMath(String(text));
      return math.restore(markedRef.parse(math.source));
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
  });
})(window);
