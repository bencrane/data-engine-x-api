import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_CARRIER_ALL_HISTORY_CSV_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaCarrierAllHistoryDaily = schedules.task({
  id: FMCSA_CARRIER_ALL_HISTORY_CSV_FEED.taskId,
  cron: {
    pattern: "32 12 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_CARRIER_ALL_HISTORY_CSV_FEED,
      schedule: payload,
    });
  },
});
