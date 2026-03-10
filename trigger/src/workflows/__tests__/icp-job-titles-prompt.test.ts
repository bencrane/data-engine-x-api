import assert from "node:assert/strict";
import test from "node:test";

import { renderIcpJobTitlesPrompt } from "../prompts/icp-job-titles.js";

test("renderIcpJobTitlesPrompt supports domain-only input", () => {
  const prompt = renderIcpJobTitlesPrompt({
    companyDomain: "https://www.acme.com/platform",
  });

  assert.match(prompt, /domain: acme\.com/);
  assert.match(prompt, /companyName: Not provided\. Infer the company name from acme\.com/);
  assert.match(prompt, /\[acme\.com\] case study/);
  assert.match(prompt, /companyDescription: Not provided\./);
});

test("renderIcpJobTitlesPrompt includes provided company inputs", () => {
  const prompt = renderIcpJobTitlesPrompt({
    companyDomain: "acme.com",
    companyName: "Acme",
    companyDescription: "Acme sells workflow software for B2B sales teams.",
  });

  assert.match(prompt, /companyName: Acme/);
  assert.match(prompt, /companyDescription: Acme sells workflow software for B2B sales teams\./);
  assert.match(prompt, /\[Acme\] customer story/);
});
