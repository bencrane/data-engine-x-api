import { logger, task } from "@trigger.dev/sdk/v3";

interface BlitzCascadeRule {
  include_title: string[];
  exclude_title: string[];
  location: string[];
  include_headline_search: boolean;
}

interface ProviderWaterfallPayload {
  company_domain: string;
  max_results?: number;
  adyntel_email?: string;
  adyntel_url?: string;
  blitz_cascade?: BlitzCascadeRule[];
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object") return value as Record<string, unknown>;
  return {};
}

function deepFindString(value: unknown, candidateKeys: string[]): string | null {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) {
    for (const item of value) {
      const result = deepFindString(item, candidateKeys);
      if (result) return result;
    }
    return null;
  }

  if (typeof value !== "object") return null;
  const record = value as Record<string, unknown>;

  for (const [key, fieldValue] of Object.entries(record)) {
    if (
      typeof fieldValue === "string" &&
      candidateKeys.includes(key.toLowerCase()) &&
      fieldValue.trim().length > 0
    ) {
      return fieldValue.trim();
    }
  }

  for (const fieldValue of Object.values(record)) {
    const result = deepFindString(fieldValue, candidateKeys);
    if (result) return result;
  }
  return null;
}

const defaultCascade: BlitzCascadeRule[] = [
  {
    include_title: ["Marketing Director", "Head Marketing", "Chief Marketing Officer"],
    exclude_title: ["assistant", "intern", "product", "junior"],
    location: ["WORLD"],
    include_headline_search: false,
  },
  {
    include_title: ["Marketing Manager", "Head Growth", "Growth manager"],
    exclude_title: ["junior", "assistant", "intern", "hacker"],
    location: ["WORLD"],
    include_headline_search: false,
  },
  {
    include_title: ["Communication Director", "Brand Director", "Content Director"],
    exclude_title: ["junior", "assistant", "intern", "UX", "UI", "Design"],
    location: ["WORLD"],
    include_headline_search: false,
  },
  {
    include_title: ["Communication Manager", "Brand Manager", "Content Manager"],
    exclude_title: ["junior", "assistant", "intern"],
    location: ["WORLD"],
    include_headline_search: false,
  },
  {
    include_title: ["Communication", "marketing", "growth", "brand"],
    exclude_title: ["junior", "assistant", "intern", "product"],
    location: ["US", "CA"],
    include_headline_search: true,
  },
  {
    include_title: ["CEO", "founder", "cofounder", "owner", "General Director"],
    exclude_title: ["junior", "assistant", "intern"],
    location: ["WORLD"],
    include_headline_search: false,
  },
];

export const providerWaterfallTest = task({
  id: "provider-waterfall-test",
  run: async (payload: ProviderWaterfallPayload) => {
    const prospeoKey = requireEnv("PROSPEO_API_KEY");
    const blitzKey = requireEnv("BLITZAPI_API_KEY");
    const adyntelKey = requireEnv("ADYNTEL_API_KEY");
    const adyntelUrlFromEnv = process.env.ADYNTEL_API_URL;
    const adyntelDefaultEmail = process.env.ADYNTEL_DEFAULT_EMAIL;

    const domain = payload.company_domain.trim().toLowerCase();
    if (!domain) throw new Error("company_domain is required");

    logger.info("Step 1: Prospeo enrich-company start", { domain });
    const prospeoRes = await fetch("https://api.prospeo.io/enrich-company", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-KEY": prospeoKey,
      },
      body: JSON.stringify({
        data: {
          company_website: domain,
        },
      }),
    });
    const prospeoBody = await prospeoRes.json();
    if (!prospeoRes.ok) {
      throw new Error(`Prospeo failed (${prospeoRes.status}): ${JSON.stringify(prospeoBody)}`);
    }

    const companyLinkedinUrl =
      deepFindString(prospeoBody, [
        "company_linkedin_url",
        "linkedin_url",
        "linkedin_company_url",
        "linkedin",
      ]) || "";

    logger.info("Step 1: Prospeo enrich-company complete", {
      domain,
      companyLinkedinUrl,
    });

    if (!companyLinkedinUrl) {
      throw new Error("Prospeo response missing company_linkedin_url (or equivalent)");
    }

    logger.info("Step 2: Blitz waterfall ICP search start", { companyLinkedinUrl });
    const blitzRes = await fetch("https://api.blitz-api.ai/v2/search/waterfall-icp-keyword", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": blitzKey,
      },
      body: JSON.stringify({
        company_linkedin_url: companyLinkedinUrl,
        cascade: payload.blitz_cascade ?? defaultCascade,
        max_results: payload.max_results ?? 10,
      }),
    });
    const blitzBody = await blitzRes.json();
    if (!blitzRes.ok) {
      throw new Error(`Blitz failed (${blitzRes.status}): ${JSON.stringify(blitzBody)}`);
    }
    logger.info("Step 2: Blitz waterfall ICP search complete");

    const linkedinPageId =
      deepFindString(prospeoBody, ["linkedin_page_id", "company_page_id"]) ||
      deepFindString(blitzBody, ["linkedin_page_id", "company_page_id"]) ||
      null;

    logger.info("Step 3: Adyntel check start", { linkedinPageId });
    const adyntelUrl = payload.adyntel_url || adyntelUrlFromEnv;
    if (!adyntelUrl) {
      throw new Error("Missing adyntel_url payload value or ADYNTEL_API_URL env var");
    }
    if (!linkedinPageId) {
      throw new Error("Could not find linkedin_page_id from Prospeo/Blitz outputs");
    }

    const adyntelRes = await fetch(adyntelUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        api_key: adyntelKey,
        email: payload.adyntel_email || adyntelDefaultEmail || "ops@dataengine.run",
        linkedin_page_id: linkedinPageId,
      }),
    });
    const adyntelBody = await adyntelRes.json();
    if (!adyntelRes.ok) {
      throw new Error(`Adyntel failed (${adyntelRes.status}): ${JSON.stringify(adyntelBody)}`);
    }
    logger.info("Step 3: Adyntel check complete");

    const prospectCount = Array.isArray(asRecord(blitzBody).results)
      ? (asRecord(blitzBody).results as unknown[]).length
      : null;

    return {
      ok: true,
      input: {
        company_domain: domain,
      },
      derived: {
        company_linkedin_url: companyLinkedinUrl,
        linkedin_page_id: linkedinPageId,
        blitz_results_count: prospectCount,
      },
      prospeo: prospeoBody,
      blitz: blitzBody,
      adyntel: adyntelBody,
    };
  },
});
