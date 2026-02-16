// pipeline.ts — Main pipeline workflow that processes submissions through blueprint steps

import { task, logger } from "@trigger.dev/sdk/v3";
import { normalize } from "./tasks/normalize";
import { deduplicate } from "./tasks/deduplicate";
import { enrichApollo } from "./tasks/enrich-apollo";

// Step registry - maps step slugs to task functions
const stepRegistry: Record<string, typeof normalize> = {
  normalize: normalize,
  deduplicate: deduplicate,
  "enrich-apollo": enrichApollo,
};

interface BlueprintStep {
  stepId: string;
  slug: string;
  order: number;
  config?: Record<string, unknown>;
}

interface PipelinePayload {
  submissionId: string;
  orgId: string;
  data: Record<string, unknown>[];
  steps: BlueprintStep[];
  callbackUrl?: string;
}

interface StepResult {
  stepId: string;
  slug: string;
  order: number;
  status: "completed" | "failed";
  outputData?: Record<string, unknown>[];
  error?: string;
}

export const runPipeline = task({
  id: "run-pipeline",
  retry: {
    maxAttempts: 1, // Pipeline itself doesn't retry; individual steps do
  },
  run: async (payload: PipelinePayload) => {
    const { submissionId, orgId, data, steps, callbackUrl } = payload;

    logger.info("Starting pipeline", { submissionId, orgId, stepCount: steps.length });

    let currentData = data;
    const stepResults: StepResult[] = [];
    let allSuccessful = true;

    // Execute steps in sequence (waterfall)
    for (const step of steps.sort((a, b) => a.order - b.order)) {
      logger.info(`Executing step: ${step.slug}`, { stepId: step.stepId, order: step.order });

      const stepTask = stepRegistry[step.slug];
      if (!stepTask) {
        logger.error(`Unknown step slug: ${step.slug}`);
        stepResults.push({
          stepId: step.stepId,
          slug: step.slug,
          order: step.order,
          status: "failed",
          error: `Unknown step: ${step.slug}`,
        });
        allSuccessful = false;
        break;
      }

      try {
        // Execute the step task
        const result = await stepTask.triggerAndWait({
          data: currentData,
          config: step.config,
        });

        if (result.ok) {
          currentData = result.output;
          stepResults.push({
            stepId: step.stepId,
            slug: step.slug,
            order: step.order,
            status: "completed",
            outputData: result.output,
          });
          logger.info(`Step completed: ${step.slug}`, { recordCount: result.output.length });
        } else {
          throw new Error(result.error || "Step failed");
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        logger.error(`Step failed: ${step.slug}`, { error: errorMessage });
        stepResults.push({
          stepId: step.stepId,
          slug: step.slug,
          order: step.order,
          status: "failed",
          error: errorMessage,
        });
        allSuccessful = false;
        break;
      }
    }

    const pipelineResult = {
      submissionId,
      orgId,
      status: allSuccessful ? "completed" : "failed",
      stepResults,
      finalData: allSuccessful ? currentData : undefined,
    };

    // Callback to API if provided
    if (callbackUrl) {
      try {
        await fetch(callbackUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(pipelineResult),
        });
      } catch (error) {
        logger.error("Failed to send callback", { error });
      }
    }

    logger.info("Pipeline completed", { status: pipelineResult.status });
    return pipelineResult;
  },
});
