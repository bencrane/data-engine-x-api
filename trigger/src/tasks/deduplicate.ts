// tasks/deduplicate.ts — Record deduplication step

import { task, logger } from "@trigger.dev/sdk/v3";

interface DeduplicatePayload {
  data: Record<string, unknown>[];
  config?: {
    keyFields?: string[];
  };
}

export const deduplicate = task({
  id: "deduplicate",
  retry: {
    maxAttempts: 3,
  },
  run: async (payload: DeduplicatePayload): Promise<Record<string, unknown>[]> => {
    const { data, config } = payload;
    const keyFields = config?.keyFields || ["email"];

    logger.info("Deduplicating records", { recordCount: data.length, keyFields });

    const seen = new Set<string>();
    const deduplicated: Record<string, unknown>[] = [];

    for (const record of data) {
      // Build composite key from specified fields
      const keyParts = keyFields.map((field) => {
        const value = record[field];
        if (typeof value === "string") {
          return value.toLowerCase().trim();
        }
        return String(value ?? "");
      });
      const key = keyParts.join("|");

      if (!seen.has(key)) {
        seen.add(key);
        deduplicated.push({
          ...record,
          is_duplicate: false,
        });
      }
    }

    const removedCount = data.length - deduplicated.length;
    logger.info("Deduplication complete", {
      originalCount: data.length,
      deduplicatedCount: deduplicated.length,
      removedCount,
    });

    return deduplicated;
  },
});
