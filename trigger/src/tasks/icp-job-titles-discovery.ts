import { task } from "@trigger.dev/sdk/v3";

import {
  IcpJobTitlesDiscoveryWorkflowPayload,
  runIcpJobTitlesDiscoveryWorkflow,
} from "../workflows/icp-job-titles-discovery.js";

export const icpJobTitlesDiscovery = task({
  id: "icp-job-titles-discovery",
  retry: { maxAttempts: 1 },
  run: async (payload: IcpJobTitlesDiscoveryWorkflowPayload) => {
    return runIcpJobTitlesDiscoveryWorkflow(payload);
  },
});
