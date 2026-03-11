import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_ACTPENDINSUR_ALL_HISTORY_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaActPendInsurAllHistory = schedules.task({
  id: FMCSA_ACTPENDINSUR_ALL_HISTORY_FEED.taskId,
  machine: "large-2x",
  maxDuration: 43200,
  cron: {
    pattern: "15 11 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_ACTPENDINSUR_ALL_HISTORY_FEED,
      schedule: payload,
    });
  },
});
