import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_INSUR_ALL_HISTORY_CSV_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaInsurAllHistoryDaily = schedules.task({
  id: FMCSA_INSUR_ALL_HISTORY_CSV_FEED.taskId,
  machine: "medium-2x",
  maxDuration: 43200,
  // cron disabled pending temp-file OOM fix validation
  // cron: {
  //   pattern: "0 13 * * *",
  //   timezone: "America/New_York",
  // },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_INSUR_ALL_HISTORY_CSV_FEED,
      schedule: payload,
    });
  },
});
