import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_INSPECTIONS_PER_UNIT_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaInspectionsPerUnitDaily = schedules.task({
  id: FMCSA_INSPECTIONS_PER_UNIT_FEED.taskId,
  cron: {
    pattern: "39 12 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_INSPECTIONS_PER_UNIT_FEED,
      schedule: payload,
    });
  },
});
