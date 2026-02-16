// trigger.config.ts — Trigger.dev project configuration

import { defineConfig } from "@trigger.dev/sdk/v3";

export default defineConfig({
  project: "data-engine-x",
  runtime: "node",
  logLevel: "log",
  retries: {
    enabledInDev: true,
    default: {
      maxAttempts: 3,
      minTimeoutInMs: 1000,
      maxTimeoutInMs: 10000,
      factor: 2,
    },
  },
  dirs: ["./src"],
});
