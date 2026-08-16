import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import * as esbuild from "esbuild";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(scriptDir, "..");
const entryPath = path.join(rootDir, "src", "frontend-entry.js");

function parseArgs(argv) {
  let checkOnly = false;
  let outputDir = path.join(rootDir, "dist", "frontend");
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--check") {
      checkOnly = true;
      continue;
    }
    if (value === "--outdir" && argv[index + 1]) {
      outputDir = path.resolve(process.cwd(), argv[index + 1]);
      index += 1;
      continue;
    }
    throw new Error(
      "Usage: node scripts/build-frontend.mjs [--check] [--outdir <directory>]",
    );
  }
  return { checkOnly, outputDir };
}

const { checkOnly, outputDir } = parseArgs(process.argv.slice(2));
const bundlePath = path.join(outputDir, "code.bundle.js");
const sourceMapPath = `${bundlePath}.map`;
const metadataPath = path.join(outputDir, "code.bundle.meta.json");
const statePath = path.join(outputDir, "code.bundle.state.json");
const previewPath = path.join(outputDir, "index.html");
const classicFallbackPath = path.join(outputDir, "index.classic.html");
const runtimeBlockPattern = /  <!-- code-frontend-runtime:start -->[\s\S]*?  <!-- code-frontend-runtime:end -->/;
const defaultBundlePath = "/dist/frontend/code.bundle.js";
const defaultFallbackPath = "/dist/frontend/index.classic.html";

function toPosix(value) {
  return value.split(path.sep).join("/");
}

function relativeToRoot(filePath) {
  const relative = path.relative(rootDir, filePath);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Frontend input escapes the project root: ${filePath}`);
  }
  return toPosix(relative);
}

async function collectSourceState() {
  const entrySource = await readFile(entryPath, "utf8");
  const importSpecifiers = [...entrySource.matchAll(/^import "([^"]+)";$/gm)]
    .map((match) => match[1]);
  if (importSpecifiers.length !== 37) {
    throw new Error(
      `Expected 37 frontend entry imports, found ${importSpecifiers.length}`,
    );
  }

  const bundleInputs = [
    relativeToRoot(entryPath),
    ...importSpecifiers.map((specifier) => (
      relativeToRoot(path.resolve(path.dirname(entryPath), specifier))
    )),
  ].sort();
  const fingerprintInputs = [...new Set([
    ...bundleInputs,
    "index.html",
    "package.json",
    "package-lock.json",
    "scripts/build-frontend.mjs",
  ])].sort();
  const hash = createHash("sha256");
  for (const relativePath of fingerprintInputs) {
    hash.update(`file:${relativePath}\0`);
    hash.update(await readFile(path.join(rootDir, relativePath)));
    hash.update("\0");
  }
  return {
    bundleInputs,
    fingerprintInputs,
    importSpecifiers,
    sourceFingerprint: hash.digest("hex"),
  };
}

async function fileRecord(filePath) {
  const contents = await readFile(filePath);
  return {
    bytes: contents.length,
    sha256: createHash("sha256").update(contents).digest("hex"),
  };
}

function sameList(left, right) {
  return left.length === right.length
    && left.every((value, index) => value === right[index]);
}

function toPublicBundlePath(directory) {
  const relative = path.relative(rootDir, directory);
  if (!relative || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    const publicDir = relative.split(path.sep).join("/");
    return `/${publicDir ? `${publicDir}/` : ""}code.bundle.js`;
  }
  return "./code.bundle.js";
}

function createPreviewHtml(source, publicBundlePath) {
  if (!runtimeBlockPattern.test(source)) {
    throw new Error("Default index.html is missing the frontend runtime block");
  }
  if (source.split(defaultBundlePath).length !== 2) {
    throw new Error("Default index.html must reference exactly one frontend bundle");
  }
  if (source.split(defaultFallbackPath).length !== 2) {
    throw new Error("Default index.html must reference exactly one classic fallback");
  }

  return source
    .replace('href="./styles.css"', 'href="/styles.css"')
    .replace('href="./code-icon.ico', 'href="/code-icon.ico')
    .replace(defaultBundlePath, publicBundlePath)
    .replace(defaultFallbackPath, "./index.classic.html");
}

function classicScriptTags(importSpecifiers) {
  return importSpecifiers.map((specifier) => {
    const absolutePath = path.resolve(path.dirname(entryPath), specifier);
    return `  <script src="/${relativeToRoot(absolutePath)}"></script>`;
  }).join("\n");
}

function createClassicFallbackHtml(source, importSpecifiers) {
  if (!runtimeBlockPattern.test(source)) {
    throw new Error("Default index.html is missing the frontend runtime block");
  }
  return source
    .replace('data-frontend-runtime="bundle"', 'data-frontend-runtime="classic-fallback"')
    .replace('href="./styles.css"', 'href="/styles.css"')
    .replace('href="./code-icon.ico', 'href="/code-icon.ico')
    .replace(runtimeBlockPattern, classicScriptTags(importSpecifiers));
}

const outputPaths = Object.freeze({
  "code.bundle.js": bundlePath,
  "code.bundle.js.map": sourceMapPath,
  "code.bundle.meta.json": metadataPath,
  "index.html": previewPath,
  "index.classic.html": classicFallbackPath,
});

async function verifyBuildState() {
  let state;
  try {
    state = JSON.parse(await readFile(statePath, "utf8"));
  } catch (error) {
    throw new Error(`Frontend build state is missing or invalid: ${statePath}`, { cause: error });
  }
  if (state.schemaVersion !== 1) {
    throw new Error(`Unsupported frontend build state schema: ${state.schemaVersion}`);
  }

  const currentSource = await collectSourceState();
  if (!sameList(state.inputs || [], currentSource.fingerprintInputs)) {
    throw new Error("Frontend build input list is stale");
  }
  if (state.sourceFingerprint !== currentSource.sourceFingerprint) {
    throw new Error("Frontend bundle is stale: source fingerprint changed");
  }

  for (const [name, filePath] of Object.entries(outputPaths)) {
    const expected = state.outputs?.[name];
    if (!expected) throw new Error(`Frontend build state is missing output: ${name}`);
    let actual;
    try {
      actual = await fileRecord(filePath);
    } catch (error) {
      throw new Error(`Frontend build output is missing: ${name}`, { cause: error });
    }
    if (actual.bytes !== expected.bytes || actual.sha256 !== expected.sha256) {
      throw new Error(`Frontend build output hash mismatch: ${name}`);
    }
  }

  process.stdout.write(`Frontend build is fresh: ${path.relative(rootDir, outputDir)}\n`);
}

if (checkOnly) {
  await verifyBuildState();
  process.exit(0);
}

await mkdir(outputDir, { recursive: true });
await rm(statePath, { force: true });
const sourceBeforeBuild = await collectSourceState();

const result = await esbuild.build({
  absWorkingDir: rootDir,
  entryPoints: ["src/frontend-entry.js"],
  outfile: bundlePath,
  bundle: true,
  platform: "browser",
  format: "iife",
  target: ["es2020"],
  charset: "utf8",
  keepNames: true,
  treeShaking: false,
  minify: false,
  sourcemap: "external",
  sourcesContent: true,
  legalComments: "none",
  metafile: true,
  logLevel: "silent",
  banner: {
    js: "/* Generated by scripts/build-frontend.mjs. Do not edit directly. */",
  },
});

const actualBundleInputs = Object.keys(result.metafile.inputs).map(toPosix).sort();
if (!sameList(actualBundleInputs, sourceBeforeBuild.bundleInputs)) {
  throw new Error("esbuild input list does not match src/frontend-entry.js");
}

await writeFile(metadataPath, `${JSON.stringify(result.metafile, null, 2)}\n`, "utf8");
const indexSource = await readFile(path.join(rootDir, "index.html"), "utf8");
const previewHtml = createPreviewHtml(indexSource, toPublicBundlePath(outputDir));
await writeFile(previewPath, previewHtml, "utf8");
await writeFile(
  classicFallbackPath,
  createClassicFallbackHtml(indexSource, sourceBeforeBuild.importSpecifiers),
  "utf8",
);

const sourceAfterBuild = await collectSourceState();
if (
  sourceBeforeBuild.sourceFingerprint !== sourceAfterBuild.sourceFingerprint
  || !sameList(sourceBeforeBuild.fingerprintInputs, sourceAfterBuild.fingerprintInputs)
) {
  throw new Error("Frontend sources changed while the bundle was being built; retry the build");
}

const outputs = {};
for (const [name, filePath] of Object.entries(outputPaths)) {
  outputs[name] = await fileRecord(filePath);
}
await writeFile(statePath, `${JSON.stringify({
  schemaVersion: 1,
  esbuildVersion: esbuild.version,
  sourceFingerprint: sourceAfterBuild.sourceFingerprint,
  inputs: sourceAfterBuild.fingerprintInputs,
  outputs,
}, null, 2)}\n`, "utf8");
await verifyBuildState();

const relativeBundle = path.relative(rootDir, bundlePath) || bundlePath;
process.stdout.write(`Frontend bundle written: ${relativeBundle}\n`);
const relativePreview = path.relative(rootDir, previewPath) || previewPath;
process.stdout.write(`Bundle preview written: ${relativePreview}\n`);
const relativeFallback = path.relative(rootDir, classicFallbackPath) || classicFallbackPath;
process.stdout.write(`Classic fallback written: ${relativeFallback}\n`);
