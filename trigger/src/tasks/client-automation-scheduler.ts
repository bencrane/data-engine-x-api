import { schedules } from "@trigger.dev/sdk/v3";

import { createInternalApiClient } from "../workflows/internal-api.js";

export const CLIENT_AUTOMATION_SCHEDULER_TASK_ID = "client-automation-scheduler";

export const clientAutomationScheduler = schedules.task({
  id: CLIENT_AUTOMATION_SCHEDULER_TASK_ID,
  maxDuration: 3600,
  cron: {
    pattern: "*/15 * * * *",
    timezone: "UTC",
  },
  run: async () => {
    const client = createInternalApiClient({
      authContext: {
        orgId: "00000000-0000-0000-0000-000000000000",
      },
    });

    return client.post("/api/internal/client-automation/schedules/evaluate-due", {
      max_schedules: 200,
      scheduler_task_id: CLIENT_AUTOMATION_SCHEDULER_TASK_ID,
      scheduler_invoked_at: new Date().toISOString(),
    });
  },
});
