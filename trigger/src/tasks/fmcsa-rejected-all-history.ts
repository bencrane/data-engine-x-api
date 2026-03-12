import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_REJECTED_ALL_HISTORY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaRejectedAllHistory = schedules.task({
  id: FMCSA_REJECTED_ALL_HISTORY_FEED.taskId,
  maxDuration: 43200,
  cron: {
    pattern: "22 11 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_REJECTED_ALL_HISTORY_FEED,
      schedule: payload,
    });
  },
});
