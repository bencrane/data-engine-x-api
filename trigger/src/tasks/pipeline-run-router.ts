import { task } from "@trigger.dev/sdk/v3";

import { companyEnrichment } from "./company-enrichment.js";
import { companyIntelBriefing } from "./company-intel-briefing.js";
import { icpJobTitlesDiscovery } from "./icp-job-titles-discovery.js";
import { personIntelBriefing } from "./person-intel-briefing.js";
import { personSearchEnrichment } from "./person-search-enrichment.js";
import { runPipeline } from "./run-pipeline.js";
import { PipelineRunRouterPayload, runPipelineRouter } from "../workflows/pipeline-run-router.js";

export const pipelineRunRouter = task({
  id: "pipeline-run-router",
  retry: { maxAttempts: 1 },
  run: async (payload: PipelineRunRouterPayload) => {
    return runPipelineRouter(payload, {
      dispatchers: {
        companyEnrichment: (childPayload, options) =>
          companyEnrichment.trigger(childPayload, { idempotencyKey: options.idempotencyKey }),
        personSearchEnrichment: (childPayload, options) =>
          personSearchEnrichment.trigger(childPayload, { idempotencyKey: options.idempotencyKey }),
        icpJobTitlesDiscovery: (childPayload, options) =>
          icpJobTitlesDiscovery.trigger(childPayload, { idempotencyKey: options.idempotencyKey }),
        companyIntelBriefing: (childPayload, options) =>
          companyIntelBriefing.trigger(childPayload, { idempotencyKey: options.idempotencyKey }),
        personIntelBriefing: (childPayload, options) =>
          personIntelBriefing.trigger(childPayload, { idempotencyKey: options.idempotencyKey }),
        runPipeline: (childPayload, options) =>
          runPipeline.trigger(childPayload, { idempotencyKey: options.idempotencyKey }),
      },
    });
  },
});
