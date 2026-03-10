import { normalizeCompanyDomain } from "../context.js";

export interface PersonIntelBriefingPromptInput {
  personFullName: string;
  personLinkedinUrl?: string | null;
  personCurrentJobTitle?: string | null;
  personCurrentCompanyName: string;
  personCurrentCompanyDomain?: string | null;
  personCurrentCompanyDescription?: string | null;
  clientCompanyName: string;
  clientCompanyDomain: string;
  clientCompanyDescription: string;
  customerCompanyName?: string | null;
  customerCompanyDomain?: string | null;
}

export const PERSON_INTEL_BRIEFING_PROMPT_TEMPLATE = `#CONTEXT#
You are a B2B sales intelligence researcher. You will receive inputs about a person at a target company, along with information about the client company whose product is being sold. Your job is to produce structured, verified intelligence about this person that a sales team can use to prepare for personalized outreach.

#INPUTS#
client_company_name: {client_company_name}
client_company_domain: {client_company_domain}
client_company_description: {client_company_description}
customer_company_name: {customer_company_name}
customer_company_domain: {customer_company_domain}
person_full_name: {person_full_name}
person_linkedin_url: {person_linkedin_url}
person_current_job_title: {person_current_job_title}
person_current_company_name: {person_current_company_name}
person_current_company_domain: {person_current_company_domain}
person_current_company_description: {person_current_company_description}

#OBJECTIVE#
Produce structured intelligence about this person - their identity, career history, public professional philosophy, advisory roles, and the context of their current company relevant to what the client company sells. All claims must be cited with source URLs. Do not fabricate specific quotes, dates, or biographical details.

#INSTRUCTIONS#
Research and populate every field in the output schema. For each field:
- Use only verifiable, publicly available information
- Cite sources with URLs
- Assign a confidence score (high/medium/low)
- If information cannot be verified, state that explicitly rather than inferring

Focus research effort on:
1. Verify the person's identity using the provided name, LinkedIn URL, title, and company
2. Full career history with dates, titles, companies, and durations
3. Public statements, blog posts, conference talks about their professional priorities
4. Advisory board roles, industry affiliations, published thought leadership
5. Current company's infrastructure, partnerships, and certifications relevant to this person's role and to what the client company sells
6. Current company's operational model or documentation structure relevant to the client company's domain

## OUTPUT SCHEMA

\`\`\`json
{
  "type": "object",
  "properties": {
    "executive_summary": {
      "type": "string",
      "description": "Brief strategic overview of who this person is, their role, and why they matter for outreach. 2-3 sentences max."
    },
    "person_full_name": {
      "type": "string",
      "description": "The person's verified full name."
    },
    "person_current_title": {
      "type": "string",
      "description": "Current job title."
    },
    "person_current_company": {
      "type": "string",
      "description": "Current employer."
    },
    "person_current_role_start_date": {
      "type": "string",
      "description": "When they started their current role (month/year)."
    },
    "person_linkedin_url": {
      "type": "string",
      "description": "LinkedIn profile URL."
    },
    "person_total_experience": {
      "type": "string",
      "description": "Approximate total years in their professional domain."
    },
    "career_history": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "company": { "type": "string" },
          "title": { "type": "string" },
          "start_date": { "type": "string" },
          "end_date": { "type": "string" },
          "notable_details": { "type": "string", "description": "Key achievements, scope, or context relevant to their professional domain." }
        }
      },
      "description": "Full career history in reverse chronological order with dates, titles, and relevant details."
    },
    "professional_philosophy_public_statements": {
      "type": "string",
      "description": "Direct quotes or paraphrased positions from blog posts, conference talks, interviews, or podcasts. Cite each with source URL and date."
    },
    "professional_key_priorities": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Their stated professional priorities and areas of focus based on public statements and content."
    },
    "professional_frameworks_and_standards": {
      "type": "string",
      "description": "Any frameworks, standards, or methodologies they've publicly advocated for in their domain."
    },
    "advisory_and_affiliations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "organization": { "type": "string" },
          "role": { "type": "string" }
        }
      },
      "description": "Advisory board seats, industry group memberships, academic affiliations."
    },
    "current_company_domain_leadership_strategy": {
      "type": "string",
      "description": "How this person is shaping strategy in their domain at their current company, based on public statements, blog posts, or company pages."
    },
    "current_company_certifications_and_standards": {
      "type": "string",
      "description": "Current certifications and standards held by the company relevant to the client company's product domain, with scope details."
    },
    "current_company_relevant_infrastructure": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Key infrastructure, architecture, or operational details at the current company relevant to the client company's product domain."
    },
    "current_company_domain_partnerships": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "partner_name": { "type": "string" },
          "partnership_scope": { "type": "string" }
        }
      },
      "description": "Vendor partnerships at the current company relevant to the client company's product domain."
    },
    "current_company_operational_model": {
      "type": "string",
      "description": "How the company structures operational responsibilities in the domain relevant to the client company's product, if publicly documented."
    },
    "client_outreach_relevance": {
      "type": "string",
      "description": "Identify the specific responsibilities, mandates, and workflows this person is accountable for in their current role at this company. Then explain what concrete pain points the client company's product solves for them - tied directly to the workflows, decisions, or outcomes they must deliver successfully. Ground in evidence from the research above."
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

function normalizeLinkedinUrl(value: string | null | undefined): string | null {
  const normalized = normalizeOptionalText(value);
  return normalized ? normalized.replace(/\/+$/, "").toLowerCase() : null;
}

export function renderPersonIntelBriefingPrompt(input: PersonIntelBriefingPromptInput): string {
  const personFullName = requireText(input.personFullName, "person_full_name");
  const personCurrentCompanyName = requireText(
    input.personCurrentCompanyName,
    "person_current_company_name",
  );
  const clientCompanyName = requireText(input.clientCompanyName, "client_company_name");
  const clientCompanyDomain = normalizeCompanyDomain(
    requireText(input.clientCompanyDomain, "client_company_domain"),
  );
  const clientCompanyDescription = requireText(
    input.clientCompanyDescription,
    "client_company_description",
  );
  const personLinkedinUrl = normalizeLinkedinUrl(input.personLinkedinUrl);
  const personCurrentJobTitle = normalizeOptionalText(input.personCurrentJobTitle);
  const personCurrentCompanyDomain = normalizeOptionalText(input.personCurrentCompanyDomain);
  const normalizedCurrentCompanyDomain = personCurrentCompanyDomain
    ? normalizeCompanyDomain(personCurrentCompanyDomain)
    : null;
  const personCurrentCompanyDescription = normalizeOptionalText(input.personCurrentCompanyDescription);
  const customerCompanyName = normalizeOptionalText(input.customerCompanyName);
  const customerCompanyDomain = normalizeOptionalText(input.customerCompanyDomain);

  return PERSON_INTEL_BRIEFING_PROMPT_TEMPLATE.replaceAll(
    "{client_company_name}",
    clientCompanyName,
  )
    .replaceAll("{client_company_domain}", clientCompanyDomain)
    .replaceAll("{client_company_description}", clientCompanyDescription)
    .replaceAll("{customer_company_name}", customerCompanyName ?? "Not provided")
    .replaceAll(
      "{customer_company_domain}",
      customerCompanyDomain ? normalizeCompanyDomain(customerCompanyDomain) : "Not provided",
    )
    .replaceAll("{person_full_name}", personFullName)
    .replaceAll("{person_linkedin_url}", personLinkedinUrl ?? "Not provided")
    .replaceAll("{person_current_job_title}", personCurrentJobTitle ?? "Not provided")
    .replaceAll("{person_current_company_name}", personCurrentCompanyName)
    .replaceAll("{person_current_company_domain}", normalizedCurrentCompanyDomain ?? "Not provided")
    .replaceAll(
      "{person_current_company_description}",
      personCurrentCompanyDescription ??
        "Not provided. Infer relevant company context from public sources before finalizing the output.",
    );
}
