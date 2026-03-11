import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_INSURANCE_DAILY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaInsuranceDaily = schedules.task({
  id: FMCSA_INSURANCE_DAILY_FEED.taskId,
  cron: {
    pattern: "19 10 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_INSURANCE_DAILY_FEED,
      schedule: payload,
    });
  },
});
