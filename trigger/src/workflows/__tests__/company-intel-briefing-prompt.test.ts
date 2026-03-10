import assert from "node:assert/strict";
import test from "node:test";

import { renderCompanyIntelBriefingPrompt } from "../prompts/company-intel-briefing.js";

test("renderCompanyIntelBriefingPrompt supports a domain-first target company input", () => {
  const prompt = renderCompanyIntelBriefingPrompt({
    companyDomain: "https://www.acme.com/platform",
    clientCompanyName: "SellerCo",
    clientCompanyDomain: "sellerco.com",
    clientCompanyDescription: "SellerCo sells workflow automation for revenue teams.",
  });

  assert.match(prompt, /client_company_name: SellerCo/);
  assert.match(prompt, /client_company_domain: sellerco\.com/);
  assert.match(prompt, /target_company_domain: acme\.com/);
  assert.match(
    prompt,
    /target_company_name: Not provided\. Infer the company name from acme\.com before finalizing the output\./,
  );
  assert.match(prompt, /target_company_description: Not provided\./);
  assert.match(prompt, /target_company_competitors:\nNo competitor information provided\./);
});

test("renderCompanyIntelBriefingPrompt includes full client and target company context", () => {
  const prompt = renderCompanyIntelBriefingPrompt({
    companyDomain: "acme.com",
    companyName: "Acme",
    companyDescription: "Acme sells procurement software for enterprise finance teams.",
    companyIndustry: "Fintech",
    companySize: "500-1000 employees",
    companyFunding: "Series C",
    companyCompetitors: ["Competitor One", "Competitor Two"],
    clientCompanyName: "SellerCo",
    clientCompanyDomain: "sellerco.com",
    clientCompanyDescription: "SellerCo sells security workflow automation.",
  });

  assert.match(prompt, /client_company_name: SellerCo/);
  assert.match(prompt, /client_company_domain: sellerco\.com/);
  assert.match(prompt, /target_company_name: Acme/);
  assert.match(prompt, /target_company_industry: Fintech/);
  assert.match(prompt, /target_company_size: 500-1000 employees/);
  assert.match(prompt, /target_company_funding: Series C/);
  assert.match(prompt, /- Competitor One/);
  assert.match(prompt, /- Competitor Two/);
  assert.match(prompt, /Return valid JSON only\./);
});
