import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_REVOCATION_DAILY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaRevocationDaily = schedules.task({
  id: FMCSA_REVOCATION_DAILY_FEED.taskId,
  maxDuration: 43200,
  cron: {
    pattern: "12 10 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_REVOCATION_DAILY_FEED,
      schedule: payload,
    });
  },
});
