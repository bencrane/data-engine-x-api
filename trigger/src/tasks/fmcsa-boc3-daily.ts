import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_BOC3_DAILY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaBoc3Daily = schedules.task({
  id: FMCSA_BOC3_DAILY_FEED.taskId,
  cron: {
    pattern: "54 10 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_BOC3_DAILY_FEED,
      schedule: payload,
    });
  },
});
