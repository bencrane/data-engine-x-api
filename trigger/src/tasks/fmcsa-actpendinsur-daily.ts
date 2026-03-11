import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_ACTPENDINSUR_DAILY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaActPendInsurDaily = schedules.task({
  id: FMCSA_ACTPENDINSUR_DAILY_FEED.taskId,
  cron: {
    pattern: "26 10 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_ACTPENDINSUR_DAILY_FEED,
      schedule: payload,
    });
  },
});
