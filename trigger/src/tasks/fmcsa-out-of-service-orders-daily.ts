import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_OUT_OF_SERVICE_ORDERS_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaOutOfServiceOrdersDaily = schedules.task({
  id: FMCSA_OUT_OF_SERVICE_ORDERS_FEED.taskId,
  cron: {
    pattern: "7 13 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_OUT_OF_SERVICE_ORDERS_FEED,
      schedule: payload,
    });
  },
});
