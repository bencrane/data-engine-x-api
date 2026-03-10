import { normalizeCompanyDomain } from "../context.js";

type CompanyCompetitorsInput = string | readonly string[] | null | undefined;

export interface CompanyIntelBriefingPromptInput {
  companyDomain: string;
  companyName?: string | null;
  companyDescription?: string | null;
  companyIndustry?: string | null;
  companySize?: string | null;
  companyFunding?: string | null;
  companyCompetitors?: CompanyCompetitorsInput;
  clientCompanyName: string;
  clientCompanyDomain: string;
  clientCompanyDescription: string;
}

export const COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE = `#CONTEXT#
You are a B2B sales intelligence researcher. You will receive inputs about a client company (the seller) and a target company (the prospect). Your job is to produce structured, verified intelligence about the target company that the client company's sales team can use to prepare for outreach.

#INPUTS#
client_company_name: {client_company_name}
client_company_domain: {client_company_domain}
client_company_description: {client_company_description}
target_company_name: {target_company_name}
target_company_domain: {target_company_domain}
target_company_description: {target_company_description}
target_company_industry: {target_company_industry}
target_company_size: {target_company_size}
target_company_funding: {target_company_funding}
target_company_competitors:
{target_company_competitors}

#OBJECTIVE#
Produce structured intelligence about the target company that covers their business context, financial position, strategic initiatives, posture and gaps in the domain relevant to what the client company sells, operational bottlenecks the client company's product addresses, and detailed competitor profiles. All claims must be cited with source URLs. Do not fabricate specific metrics, deal details, or quotes.

#INSTRUCTIONS#
Research and populate every field in the output schema. For each field:
- Use only verifiable, publicly available information
- Cite sources with URLs
- Assign a confidence score (high/medium/low)
- If information cannot be verified, state that explicitly rather than inferring

Focus research effort on:
1. Current business status, funding, and financial metrics
2. Strategic initiatives that expand the target company's need for what the client company sells
3. Key customer relationships and concentration risk
4. Where the target company's operations create bottlenecks that the client company's product category directly addresses
5. Current certifications, capabilities, and gaps in the domain relevant to the client company's product
6. Competitor positioning - pricing, procurement advantages, and posture in the client company's domain - with specifics

## OUTPUT SCHEMA

\`\`\`json
{
  "type": "object",
  "properties": {
    "target_business_summary": {
      "type": "string",
      "description": "Overview of the target company's current business status, market position, strategic focus, key partnerships, and recent developments."
    },
    "target_financial_highlights": {
      "type": "object",
      "description": "Key financial metrics including revenue, funding, valuation, growth trajectory, and any publicly available financial data."
    },
    "target_strategic_initiatives": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "initiative": { "type": "string" },
          "description": { "type": "string" },
          "expanded_risk_surface": { "type": "string", "description": "New risks or needs this initiative creates that are relevant to what the client company sells." }
        }
      }
    },
    "target_key_customers_and_concentration_risk": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "customer_name": { "type": "string" },
          "contract_details": { "type": "string" },
          "concentration_risk_analysis": { "type": "string" }
        }
      }
    },
    "target_operational_bottlenecks": {
      "type": "string",
      "description": "Analysis of where the target company's operations create pain points or bottlenecks that the client company's product category directly addresses."
    },
    "target_capabilities_and_gaps": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "category": { "type": "string" },
          "current_posture": { "type": "string" },
          "identified_gaps": { "type": "string" }
        }
      }
    },
    "competitor_analysis": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "competitor_name": { "type": "string" },
          "pricing_model": { "type": "string" },
          "procurement_advantages": { "type": "string" },
          "domain_posture": { "type": "string" }
        }
      }
    },
    "outbound_relevance_summary": {
      "type": "string",
      "description": "A concise summary of why this target company is relevant for the client company's outbound motion right now."
    },
    "citations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "claim": { "type": "string" },
          "url": { "type": "string" },
          "confidence": { "type": "string", "enum": ["high", "medium", "low"] }
        }
      }
    }
  }
}
\`\`\`

Return valid JSON only.`;

function normalizeOptionalText(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function requireText(value: string | null | undefined, fieldName: string): string {
  const normalized = normalizeOptionalText(value);
  if (!normalized) {
    throw new Error(`${fieldName} is required`);
  }
  return normalized;
}

function normalizeCompetitors(value: CompanyCompetitorsInput): string {
  if (Array.isArray(value)) {
    const normalized = value
      .map((item) => normalizeOptionalText(item))
      .filter((item): item is string => item !== null);
    return normalized.length > 0
      ? normalized.map((item) => `- ${item}`).join("\n")
      : "No competitor information provided.";
  }

  const normalized = typeof value === "string" ? normalizeOptionalText(value) : null;
  return normalized ?? "No competitor information provided.";
}

export function renderCompanyIntelBriefingPrompt(input: CompanyIntelBriefingPromptInput): string {
  const companyDomain = normalizeCompanyDomain(input.companyDomain);
  const companyName = normalizeOptionalText(input.companyName);
  const companyDescription = normalizeOptionalText(input.companyDescription);
  const companyIndustry = normalizeOptionalText(input.companyIndustry);
  const companySize = normalizeOptionalText(input.companySize);
  const companyFunding = normalizeOptionalText(input.companyFunding);
  const clientCompanyName = requireText(input.clientCompanyName, "client_company_name");
  const clientCompanyDomain = normalizeCompanyDomain(
    requireText(input.clientCompanyDomain, "client_company_domain"),
  );
  const clientCompanyDescription = requireText(
    input.clientCompanyDescription,
    "client_company_description",
  );

  return COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE.replaceAll(
    "{client_company_name}",
    clientCompanyName,
  )
    .replaceAll("{client_company_domain}", clientCompanyDomain)
    .replaceAll("{client_company_description}", clientCompanyDescription)
    .replaceAll(
      "{target_company_name}",
      companyName ?? `Not provided. Infer the company name from ${companyDomain} before finalizing the output.`,
    )
    .replaceAll("{target_company_domain}", companyDomain)
    .replaceAll(
      "{target_company_description}",
      companyDescription ??
        "Not provided. Infer the company description from the website and public sources before finalizing the output.",
    )
    .replaceAll("{target_company_industry}", companyIndustry ?? "Not specified")
    .replaceAll("{target_company_size}", companySize ?? "Not specified")
    .replaceAll("{target_company_funding}", companyFunding ?? "Not specified")
    .replaceAll("{target_company_competitors}", normalizeCompetitors(input.companyCompetitors));
}
