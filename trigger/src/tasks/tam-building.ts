import { task } from "@trigger.dev/sdk/v3";

import {
  TamBuildingWorkflowPayload,
  runTamBuildingWorkflow,
} from "../workflows/tam-building.js";

export const tamBuilding = task({
  id: "tam-building",
  retry: { maxAttempts: 1 },
  run: async (payload: TamBuildingWorkflowPayload) => {
    return runTamBuildingWorkflow(payload);
  },
});
