import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_SMS_AB_PASSPROPERTY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaSmsAbPassPropertyDaily = schedules.task({
  id: FMCSA_SMS_AB_PASSPROPERTY_FEED.taskId,
  maxDuration: 43200,
  cron: {
    pattern: "36 11 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_SMS_AB_PASSPROPERTY_FEED,
      schedule: payload,
    });
  },
});
