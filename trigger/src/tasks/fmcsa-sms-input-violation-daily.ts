import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_SMS_INPUT_VIOLATION_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaSmsInputViolationDaily = schedules.task({
  id: FMCSA_SMS_INPUT_VIOLATION_FEED.taskId,
  maxDuration: 43200,
  cron: {
    pattern: "50 11 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_SMS_INPUT_VIOLATION_FEED,
      schedule: payload,
    });
  },
});
