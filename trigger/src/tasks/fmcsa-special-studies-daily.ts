import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_SPECIAL_STUDIES_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaSpecialStudiesDaily = schedules.task({
  id: FMCSA_SPECIAL_STUDIES_FEED.taskId,
  machine: "medium-2x",
  maxDuration: 3600,
  cron: {
    pattern: "46 12 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_SPECIAL_STUDIES_FEED,
      schedule: payload,
    });
  },
});
