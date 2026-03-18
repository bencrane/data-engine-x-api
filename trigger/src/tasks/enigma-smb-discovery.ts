import { task } from "@trigger.dev/sdk/v3";

import {
  EnigmaSmBDiscoveryWorkflowPayload,
  runEnigmaSmBDiscoveryWorkflow,
} from "../workflows/enigma-smb-discovery.js";

export const enigmaSmBDiscovery = task({
  id: "enigma-smb-discovery",
  retry: { maxAttempts: 1 },
  run: async (payload: EnigmaSmBDiscoveryWorkflowPayload) => {
    return runEnigmaSmBDiscoveryWorkflow(payload);
  },
});
