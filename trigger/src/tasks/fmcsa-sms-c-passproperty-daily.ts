import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_SMS_C_PASSPROPERTY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaSmsCPassPropertyDaily = schedules.task({
  id: FMCSA_SMS_C_PASSPROPERTY_FEED.taskId,
  machine: "medium-2x",
  maxDuration: 43200,
  cron: {
    pattern: "43 11 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_SMS_C_PASSPROPERTY_FEED,
      schedule: payload,
    });
  },
});
