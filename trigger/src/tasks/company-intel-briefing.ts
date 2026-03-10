import { task } from "@trigger.dev/sdk/v3";

import {
  CompanyIntelBriefingWorkflowPayload,
  runCompanyIntelBriefingWorkflow,
} from "../workflows/company-intel-briefing.js";

export const companyIntelBriefing = task({
  id: "company-intel-briefing",
  retry: { maxAttempts: 1 },
  run: async (payload: CompanyIntelBriefingWorkflowPayload) => {
    return runCompanyIntelBriefingWorkflow(payload);
  },
});
