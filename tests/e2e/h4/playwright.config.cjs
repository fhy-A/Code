const { defineConfig } = require("@playwright/test");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../../..");

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: "smoke.spec.cjs",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: {
    timeout: 8_000,
  },
  outputDir: path.join(ROOT, "output", "h4-playwright"),
  reporter: [["line"]],
  use: {
    browserName: "chromium",
    headless: true,
    viewport: { width: 1280, height: 800 },
    actionTimeout: 8_000,
    navigationTimeout: 10_000,
    acceptDownloads: false,
    serviceWorkers: "block",
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
