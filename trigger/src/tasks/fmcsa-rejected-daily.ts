import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_REJECTED_DAILY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaRejectedDaily = schedules.task({
  id: FMCSA_REJECTED_DAILY_FEED.taskId,
  cron: {
    pattern: "47 10 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_REJECTED_DAILY_FEED,
      schedule: payload,
    });
  },
});
