import { normalizeCompanyDomain } from "../context.js";

export interface IcpJobTitlesPromptInput {
  companyDomain: string;
  companyName?: string | null;
  companyDescription?: string | null;
}

export const ICP_JOB_TITLES_PROMPT_TEMPLATE = `CONTEXT
You are a B2B buyer persona researcher. You will be given a company name, domain, and optionally a company description. Your job is to research this company thoroughly and produce an exhaustive list of job titles that represent realistic buyers, champions, evaluators, and decision-makers for this company's product(s).

INPUTS
companyName: {company_name}
domain: {domain}
companyDescription: {company_description}

RESEARCH INSTRUCTIONS

1. Research the company
   - Visit the company website to understand what they sell, who they sell to, and how they position their product.
   - Review case studies, testimonials, and customer logos to identify real buyers and users.
   - Check G2, TrustRadius, Capterra, and similar review platforms. Look specifically at reviewer job titles.
   - Review the company's LinkedIn presence and any published ICP or buyer persona content.
   - Search: "[{research_seed}] case study" "[{research_seed}] customer story"
   - Capture any named roles or titles.

2. Identify the buying committee
   Determine realistic roles for:
   - **Champions** - Day-to-day users or people experiencing the problem directly. They discover, evaluate, and advocate internally.
   - **Evaluators** - Technical or operational stakeholders who run POCs or compare alternatives.
   - **Decision makers** - Budget owners and signers. Only include if appropriate for this product category and price point.

3. Generate title variations
   For each persona:
   - Include realistic seniority variants (Manager, Senior Manager, Director, Head, VP, Lead) only where appropriate.
   - Include function-specific variants where relevant (e.g., Security, Compliance, GRC, IT, Engineering, Legal, Risk).

CRITICAL GUARDRAILS
- Every title must be grounded in evidence from the company website, reviews, case studies, or known buyer patterns for this category.
- Do not guess or hallucinate titles.
- Exclude roles that would reasonably not care about or buy this product.
- Do not include generic functional labels (e.g., "Information Security").
- Quantity target: 30-60 titles. More is fine if grounded. Fewer is fine if narrow. Never pad.

OUTPUT FORMAT
companyName: {company_name}
domain: {domain}
inferredProduct: One sentence describing what the company sells and to whom, based on your research.
buyerPersonaSummary: 2-3 sentences describing the buying committee - who champions it, who evaluates it, who signs off.
titles: For each title include the title, buyerRole (champion | evaluator | decision_maker), and reasoning (one sentence grounding this title in research evidence).`;

function normalizeOptionalText(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

export function renderIcpJobTitlesPrompt(input: IcpJobTitlesPromptInput): string {
  const companyDomain = normalizeCompanyDomain(input.companyDomain);
  const companyName = normalizeOptionalText(input.companyName);
  const companyDescription = normalizeOptionalText(input.companyDescription);
  const researchSeed = companyName ?? companyDomain;

  return ICP_JOB_TITLES_PROMPT_TEMPLATE.replaceAll(
    "{company_name}",
    companyName ?? `Not provided. Infer the company name from ${companyDomain} before finalizing the output.`,
  )
    .replaceAll("{domain}", companyDomain)
    .replaceAll(
      "{company_description}",
      companyDescription ??
        "Not provided. Infer the company description from the website and public sources before finalizing the output.",
    )
    .replaceAll("{research_seed}", researchSeed);
}
