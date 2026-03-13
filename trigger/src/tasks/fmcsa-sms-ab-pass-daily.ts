import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_SMS_AB_PASS_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaSmsAbPassDaily = schedules.task({
  id: FMCSA_SMS_AB_PASS_FEED.taskId,
  maxDuration: 43200,
  // cron disabled pending temp-file OOM fix validation
  // cron: {
  //   pattern: "11 12 * * *",
  //   timezone: "America/New_York",
  // },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_SMS_AB_PASS_FEED,
      schedule: payload,
    });
  },
});
