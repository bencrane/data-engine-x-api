import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_COMPANY_CENSUS_FILE_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaCompanyCensusFileDaily = schedules.task({
  id: FMCSA_COMPANY_CENSUS_FILE_FEED.taskId,
  cron: {
    pattern: "28 13 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_COMPANY_CENSUS_FILE_FEED,
      schedule: payload,
    });
  },
});
