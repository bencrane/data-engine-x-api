import { task } from "@trigger.dev/sdk/v3";

import {
  PersonSearchEnrichmentWorkflowPayload,
  runPersonSearchEnrichmentWorkflow,
} from "../workflows/person-search-enrichment.js";

export const personSearchEnrichment = task({
  id: "person-search-enrichment",
  retry: { maxAttempts: 1 },
  run: async (payload: PersonSearchEnrichmentWorkflowPayload) => {
    return runPersonSearchEnrichmentWorkflow(payload);
  },
});
