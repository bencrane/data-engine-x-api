import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_CARRIER_DAILY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaCarrierDaily = schedules.task({
  id: FMCSA_CARRIER_DAILY_FEED.taskId,
  maxDuration: 43200,
  cron: {
    pattern: "40 10 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_CARRIER_DAILY_FEED,
      schedule: payload,
    });
  },
});
