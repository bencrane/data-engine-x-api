import { task } from "@trigger.dev/sdk/v3";

import {
  PersonIntelBriefingWorkflowPayload,
  runPersonIntelBriefingWorkflow,
} from "../workflows/person-intel-briefing.js";

export const personIntelBriefing = task({
  id: "person-intel-briefing",
  retry: { maxAttempts: 1 },
  run: async (payload: PersonIntelBriefingWorkflowPayload) => {
    return runPersonIntelBriefingWorkflow(payload);
  },
});
