// tasks/enrich-apollo.ts — Apollo.io enrichment step

import { task, logger } from "@trigger.dev/sdk/v3";

interface EnrichApolloPayload {
  data: Record<string, unknown>[];
  config?: {
    apiKey?: string;
  };
}

export const enrichApollo = task({
  id: "enrich-apollo",
  retry: {
    maxAttempts: 2,
  },
  run: async (payload: EnrichApolloPayload): Promise<Record<string, unknown>[]> => {
    const { data, config } = payload;
    const apiKey = config?.apiKey || process.env.APOLLO_API_KEY;

    if (!apiKey) {
      throw new Error("APOLLO_API_KEY not configured");
    }

    logger.info("Enriching with Apollo", { recordCount: data.length });

    const enriched: Record<string, unknown>[] = [];

    for (const record of data) {
      const result = { ...record };
      const email = record.email as string | undefined;

      if (!email) {
        result.apollo_enriched = false;
        result.apollo_error = "No email provided";
        enriched.push(result);
        continue;
      }

      try {
        const response = await fetch("https://api.apollo.io/v1/people/match", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Api-Key": apiKey,
          },
          body: JSON.stringify({ email }),
        });

        if (response.ok) {
          const apolloData = await response.json();
          const person = apolloData.person || {};

          result.apollo_enriched = true;
          result.apollo_title = person.title;
          result.apollo_company = person.organization?.name;
          result.apollo_linkedin = person.linkedin_url;
          result.apollo_phone = person.phone_numbers?.[0]?.number;
        } else {
          result.apollo_enriched = false;
          result.apollo_error = `API error: ${response.status}`;
        }
      } catch (error) {
        result.apollo_enriched = false;
        result.apollo_error = error instanceof Error ? error.message : String(error);
      }

      enriched.push(result);
    }

    const enrichedCount = enriched.filter((r) => r.apollo_enriched).length;
    logger.info("Apollo enrichment complete", {
      total: enriched.length,
      enriched: enrichedCount,
      failed: enriched.length - enrichedCount,
    });

    return enriched;
  },
});
