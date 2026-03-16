#!/usr/bin/env npx tsx
/**
 * One-off script to manually trigger fmcsa-sms-motor-carrier-census-daily in Trigger.dev production.
 * Requires TRIGGER_SECRET_KEY (production) in env. Run: doppler run -- npx tsx scripts/trigger-fmcsa-motor-carrier-census.ts
 */
import { tasks } from "@trigger.dev/sdk/v3";

const TASK_ID = "fmcsa-sms-motor-carrier-census-daily";

async function main() {
  const handle = await tasks.trigger(TASK_ID, {
    timestamp: new Date(),
    timezone: "America/New_York",
    scheduleId: "manual",
  });
  console.log("Triggered:", TASK_ID);
  console.log("Run ID:", handle.id);
  console.log("Dashboard:", `https://cloud.trigger.dev/runs/${handle.id}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
