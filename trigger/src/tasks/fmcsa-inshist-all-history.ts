import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_INSHIST_ALL_HISTORY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaInsHistAllHistory = schedules.task({
  id: FMCSA_INSHIST_ALL_HISTORY_FEED.taskId,
  cron: {
    pattern: "1 11 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_INSHIST_ALL_HISTORY_FEED,
      schedule: payload,
    });
  },
});
