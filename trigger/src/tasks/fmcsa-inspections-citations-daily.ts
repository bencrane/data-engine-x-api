import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_INSPECTIONS_AND_CITATIONS_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaInspectionsCitationsDaily = schedules.task({
  id: FMCSA_INSPECTIONS_AND_CITATIONS_FEED.taskId,
  machine: "small-2x",
  maxDuration: 43200,
  // cron disabled pending temp-file OOM fix validation
  // cron: {
  //   pattern: "14 13 * * *",
  //   timezone: "America/New_York",
  // },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_INSPECTIONS_AND_CITATIONS_FEED,
      schedule: payload,
    });
  },
});
