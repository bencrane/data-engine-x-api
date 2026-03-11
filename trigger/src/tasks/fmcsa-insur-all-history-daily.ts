import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_INSUR_ALL_HISTORY_CSV_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaInsurAllHistoryDaily = schedules.task({
  id: FMCSA_INSUR_ALL_HISTORY_CSV_FEED.taskId,
  cron: {
    pattern: "0 13 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_INSUR_ALL_HISTORY_CSV_FEED,
      schedule: payload,
    });
  },
});
