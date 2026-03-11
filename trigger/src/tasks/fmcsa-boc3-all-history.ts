import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_BOC3_ALL_HISTORY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaBoc3AllHistory = schedules.task({
  id: FMCSA_BOC3_ALL_HISTORY_FEED.taskId,
  cron: {
    pattern: "8 11 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_BOC3_ALL_HISTORY_FEED,
      schedule: payload,
    });
  },
});
