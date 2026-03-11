import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_AUTHHIST_ALL_HISTORY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaAuthHistAllHistory = schedules.task({
  id: FMCSA_AUTHHIST_ALL_HISTORY_FEED.taskId,
  cron: {
    pattern: "29 11 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_AUTHHIST_ALL_HISTORY_FEED,
      schedule: payload,
    });
  },
});
