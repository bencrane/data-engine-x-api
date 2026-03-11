import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_VEHICLE_INSPECTION_FILE_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaVehicleInspectionFileDaily = schedules.task({
  id: FMCSA_VEHICLE_INSPECTION_FILE_FEED.taskId,
  machine: "medium-2x",
  maxDuration: 10800,
  cron: {
    pattern: "35 13 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_VEHICLE_INSPECTION_FILE_FEED,
      schedule: payload,
    });
  },
});
