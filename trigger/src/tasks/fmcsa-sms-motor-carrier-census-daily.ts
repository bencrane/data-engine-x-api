import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaSmsMotorCarrierCensusDaily = schedules.task({
  id: FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED.taskId,
  maxDuration: 43200,
  cron: {
    pattern: "4 12 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED,
      schedule: payload,
    });
  },
});
