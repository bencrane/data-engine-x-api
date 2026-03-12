import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_CRASH_FILE_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaCrashFileDaily = schedules.task({
  id: FMCSA_CRASH_FILE_FEED.taskId,
  machine: "medium-2x",
  maxDuration: 43200,
  cron: {
    pattern: "25 12 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_CRASH_FILE_FEED,
      schedule: payload,
    });
  },
});
