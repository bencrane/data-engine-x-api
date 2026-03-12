import { schedules } from "@trigger.dev/sdk/v3";

import {
  FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED,
  runFmcsaDailyDiffWorkflow,
} from "../workflows/fmcsa-daily-diff.js";

export const fmcsaVehicleInspectionsViolationsDaily = schedules.task({
  id: FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED.taskId,
  machine: "small-2x",
  maxDuration: 43200,
  cron: {
    pattern: "21 13 * * *",
    timezone: "America/New_York",
  },
  run: async (payload) => {
    return runFmcsaDailyDiffWorkflow({
      feed: FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED,
      schedule: payload,
    });
  },
});
