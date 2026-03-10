export type WorkflowContext = Record<string, unknown>;

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function normalizeCompanyDomain(domain: string): string {
  const trimmed = domain.trim().toLowerCase();
  const withoutProtocol = trimmed.replace(/^[a-z]+:\/\//, "");
  const withoutPath = withoutProtocol.split("/")[0] ?? withoutProtocol;
  const withoutWww = withoutPath.startsWith("www.") ? withoutPath.slice(4) : withoutPath;

  if (!withoutWww) {
    throw new Error("company_domain is required");
  }

  return withoutWww;
}

export function mergeStepOutput(
  current: WorkflowContext,
  output: WorkflowContext | null | undefined,
): WorkflowContext {
  if (!output) {
    return { ...current };
  }

  return {
    ...current,
    ...output,
  };
}

export function buildCompanySeedContext(
  companyDomain: string,
  initialContext: WorkflowContext = {},
): WorkflowContext {
  const normalizedDomain = normalizeCompanyDomain(companyDomain);
  const seed: WorkflowContext = {
    domain: normalizedDomain,
    company_domain: normalizedDomain,
    canonical_domain: normalizedDomain,
  };

  const merged = mergeStepOutput(seed, initialContext);

  if (!isNonEmptyString(merged.company_domain) && !isNonEmptyString(merged.canonical_domain)) {
    return seed;
  }

  return {
    ...merged,
    ...(isNonEmptyString(merged.company_domain)
      ? { company_domain: normalizeCompanyDomain(merged.company_domain) }
      : {}),
    ...(isNonEmptyString(merged.canonical_domain)
      ? { canonical_domain: normalizeCompanyDomain(merged.canonical_domain) }
      : {}),
    ...(isNonEmptyString(merged.domain) ? { domain: normalizeCompanyDomain(merged.domain) } : {}),
  };
}

export function hasLinkedinUrl(context: WorkflowContext): boolean {
  return isNonEmptyString(context.linkedin_url) || isNonEmptyString(context.company_linkedin_url);
}
