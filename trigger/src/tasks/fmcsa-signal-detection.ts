import { schedules, logger } from "@trigger.dev/sdk/v3";

import {
  resolveInternalApiConfig,
  createInternalApiClient,
} from "../workflows/internal-api.js";

interface SignalDetectionSummary {
  feed_date: string;
  total_signals: number;
  counts: Record<string, number>;
}

export const fmcsaSignalDetection = schedules.task({
  id: "fmcsa-signal-detection",
  maxDuration: 600,
  cron: {
    pattern: "0 17 * * *",
    timezone: "America/New_York",
  },
  run: async () => {
    const config = resolveInternalApiConfig();
    const client = createInternalApiClient({
      authContext: { orgId: "system" },
      apiUrl: config.apiUrl,
      internalApiKey: config.internalApiKey,
      defaultTimeoutMs: config.defaultTimeoutMs,
    });

    const today = new Date().toISOString().split("T")[0];
    logger.info(`Running FMCSA signal detection for feed_date=${today}`);

    const result = await client.post<SignalDetectionSummary>(
      "/api/internal/fmcsa-signals/detect",
      { feed_date: today },
      { timeoutMs: 300_000 },
    );

    logger.info("Signal detection complete", {
      feed_date: result.feed_date,
      total_signals: result.total_signals,
      counts: result.counts,
    });

    return result;
  },
});
