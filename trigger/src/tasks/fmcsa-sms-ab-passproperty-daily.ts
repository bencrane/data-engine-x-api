import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_SMS_AB_PASSPROPERTY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaSmsAbPassPropertyDaily = schedules.task({
  id: FMCSA_SMS_AB_PASSPROPERTY_FEED.taskId,
  machine: "medium-2x",
  maxDuration: 43200,
  // cron disabled pending temp-file OOM fix validation
  // cron: {
  //   pattern: "36 11 * * *",
  //   timezone: "America/New_York",
  // },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_SMS_AB_PASSPROPERTY_FEED,
      schedule: payload,
    });
  },
});
