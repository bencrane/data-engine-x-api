import { task } from "@trigger.dev/sdk/v3";

import {
  CompanyEnrichmentWorkflowPayload,
  runCompanyEnrichmentWorkflow,
} from "../workflows/company-enrichment.js";

export const companyEnrichment = task({
  id: "company-enrichment",
  retry: { maxAttempts: 1 },
  run: async (payload: CompanyEnrichmentWorkflowPayload) => {
    return runCompanyEnrichmentWorkflow(payload);
  },
});
