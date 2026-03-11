import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaRevocationAllHistoryDaily = schedules.task({
  id: FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED.taskId,
  machine: "small-2x",
  maxDuration: 1800,
  cron: {
    pattern: "53 12 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED,
      schedule: payload,
    });
  },
});
