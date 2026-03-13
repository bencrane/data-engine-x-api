import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_SMS_INPUT_INSPECTION_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaSmsInputInspectionDaily = schedules.task({
  id: FMCSA_SMS_INPUT_INSPECTION_FEED.taskId,
  machine: "large-2x",
  maxDuration: 43200,
  // cron disabled pending temp-file OOM fix validation
  // cron: {
  //   pattern: "57 11 * * *",
  //   timezone: "America/New_York",
  // },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_SMS_INPUT_INSPECTION_FEED,
      schedule: payload,
    });
  },
});
