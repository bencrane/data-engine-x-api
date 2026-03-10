export type WorkflowContext = Record<string, unknown>;

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function normalizeLinkedinUrl(value: string): string {
  return value.trim().replace(/\/+$/, "").toLowerCase();
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

export function buildPersonSearchSeedContext(
  companyDomain: string,
  initialContext: WorkflowContext = {},
): WorkflowContext {
  return buildCompanySeedContext(companyDomain, initialContext);
}

export function buildPersonCandidateContext(
  sharedContext: WorkflowContext,
  candidateContext: WorkflowContext,
): WorkflowContext {
  return mergeStepOutput(sharedContext, buildPersistablePersonContext(candidateContext));
}

export function buildPersistablePersonContext(context: WorkflowContext): WorkflowContext {
  const merged = { ...context };
  const title =
    isNonEmptyString(merged.title)
      ? merged.title
      : isNonEmptyString(merged.current_title)
        ? merged.current_title
        : isNonEmptyString(merged.headline)
          ? merged.headline
          : undefined;
  const workEmail =
    isNonEmptyString(merged.work_email)
      ? merged.work_email.toLowerCase()
      : isNonEmptyString(merged.email)
        ? merged.email.toLowerCase()
        : undefined;
  const phone =
    isNonEmptyString(merged.phone_e164)
      ? merged.phone_e164
      : isNonEmptyString(merged.mobile_phone)
        ? merged.mobile_phone
        : undefined;

  return {
    ...merged,
    ...(title ? { title } : {}),
    ...(workEmail ? { work_email: workEmail, email: workEmail } : {}),
    ...(phone ? { phone_e164: phone, mobile_phone: phone } : {}),
    ...(isNonEmptyString(merged.linkedin_url)
      ? { linkedin_url: normalizeLinkedinUrl(merged.linkedin_url) }
      : {}),
    ...(isNonEmptyString(merged.current_company_domain)
      ? { current_company_domain: normalizeCompanyDomain(merged.current_company_domain) }
      : {}),
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
