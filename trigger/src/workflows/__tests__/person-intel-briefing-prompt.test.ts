import assert from "node:assert/strict";
import test from "node:test";

import { renderPersonIntelBriefingPrompt } from "../prompts/person-intel-briefing.js";

test("renderPersonIntelBriefingPrompt includes person and client context", () => {
  const prompt = renderPersonIntelBriefingPrompt({
    personFullName: "Jane Doe",
    personLinkedinUrl: "https://www.linkedin.com/in/jane-doe/",
    personCurrentJobTitle: "VP of Security",
    personCurrentCompanyName: "Acme",
    personCurrentCompanyDomain: "https://www.acme.com/platform",
    personCurrentCompanyDescription: "Acme builds procurement orchestration software.",
    clientCompanyName: "SellerCo",
    clientCompanyDomain: "https://sellerco.com",
    clientCompanyDescription: "SellerCo sells security workflow automation.",
    customerCompanyName: "BigBank",
    customerCompanyDomain: "bigbank.com",
  });

  assert.match(prompt, /client_company_name: SellerCo/);
  assert.match(prompt, /client_company_domain: sellerco\.com/);
  assert.match(prompt, /customer_company_name: BigBank/);
  assert.match(prompt, /customer_company_domain: bigbank\.com/);
  assert.match(prompt, /person_full_name: Jane Doe/);
  assert.match(prompt, /person_linkedin_url: https:\/\/www\.linkedin\.com\/in\/jane-doe/);
  assert.match(prompt, /person_current_job_title: VP of Security/);
  assert.match(prompt, /person_current_company_name: Acme/);
  assert.match(prompt, /person_current_company_domain: acme\.com/);
  assert.match(prompt, /Return valid JSON only\./);
});

test("renderPersonIntelBriefingPrompt falls back cleanly for missing optional inputs", () => {
  const prompt = renderPersonIntelBriefingPrompt({
    personFullName: "Jane Doe",
    personCurrentCompanyName: "Acme",
    clientCompanyName: "SellerCo",
    clientCompanyDomain: "sellerco.com",
    clientCompanyDescription: "SellerCo sells security workflow automation.",
  });

  assert.match(prompt, /customer_company_name: Not provided/);
  assert.match(prompt, /customer_company_domain: Not provided/);
  assert.match(prompt, /person_linkedin_url: Not provided/);
  assert.match(prompt, /person_current_job_title: Not provided/);
  assert.match(prompt, /person_current_company_domain: Not provided/);
  assert.match(
    prompt,
    /person_current_company_description: Not provided\. Infer relevant company context from public sources before finalizing the output\./,
  );
});
