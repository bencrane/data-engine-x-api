// tasks/normalize.ts — Company name normalization step

import { task, logger } from "@trigger.dev/sdk/v3";

interface NormalizePayload {
  data: Record<string, unknown>[];
  config?: {
    field?: string;
  };
}

const SUFFIXES = [
  ", Inc.",
  ", Inc",
  " Inc.",
  " Inc",
  ", LLC",
  " LLC",
  ", Ltd.",
  ", Ltd",
  " Ltd.",
  " Ltd",
  ", Corp.",
  ", Corp",
  " Corp.",
  " Corp",
  ", Co.",
  " Co.",
];

export const normalize = task({
  id: "normalize",
  retry: {
    maxAttempts: 3,
  },
  run: async (payload: NormalizePayload): Promise<Record<string, unknown>[]> => {
    const { data, config } = payload;
    const field = config?.field || "company_name";

    logger.info("Normalizing company names", { recordCount: data.length, field });

    const normalized = data.map((record) => {
      const result = { ...record };
      const value = record[field];

      if (typeof value === "string" && value.trim()) {
        let name = value.trim();

        // Remove common suffixes
        for (const suffix of SUFFIXES) {
          if (name.endsWith(suffix)) {
            name = name.slice(0, -suffix.length).trim();
            break;
          }
        }

        result[field] = name;
        result[`${field}_normalized`] = true;
      }

      return result;
    });

    logger.info("Normalization complete", { recordCount: normalized.length });
    return normalized;
  },
});
