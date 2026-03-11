import { task } from "@trigger.dev/sdk/v3";

import {
  JobPostingDiscoveryWorkflowPayload,
  runJobPostingDiscoveryWorkflow,
} from "../workflows/job-posting-discovery.js";

export const jobPostingDiscovery = task({
  id: "job-posting-discovery",
  retry: { maxAttempts: 1 },
  run: async (payload: JobPostingDiscoveryWorkflowPayload) => {
    return runJobPostingDiscoveryWorkflow(payload);
  },
});
