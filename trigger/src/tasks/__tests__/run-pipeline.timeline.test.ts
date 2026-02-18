import assert from "node:assert/strict";
import test from "node:test";

import { __testables } from "../run-pipeline.js";

test("inferFieldsUpdatedFromOperationResult returns sorted non-null keys", () => {
  const fields = __testables.inferFieldsUpdatedFromOperationResult({
    output: {
      zeta: "value",
      alpha: 1,
      omit_null: null,
      omit_undefined: undefined,
    },
  });
  assert.deepEqual(fields, ["alpha", "zeta"]);
});

test("operationIdForStep falls back for missing operation", () => {
  assert.equal(__testables.operationIdForStep(undefined), "unknown.operation");
  assert.equal(
    __testables.operationIdForStep({
      id: "s1",
      position: 1,
      operation_id: "person.search",
    }),
    "person.search",
  );
});

test("getSkipIfFreshConfig parses valid step config", () => {
  const config = __testables.getSkipIfFreshConfig({
    id: "s2",
    position: 2,
    operation_id: "person.enrich.profile",
    step_config: {
      skip_if_fresh: {
        max_age_hours: 72,
        identity_fields: ["linkedin_url", "work_email"],
      },
    },
  });

  assert.deepEqual(config, {
    maxAgeHours: 72,
    identityFields: ["linkedin_url", "work_email"],
  });
});

test("extractFreshnessIdentifiers keeps only present identity fields", () => {
  const identifiers = __testables.extractFreshnessIdentifiers(
    {
      linkedin_url: "https://linkedin.com/in/alex",
      work_email: "",
      company_domain: "acme.com",
    },
    ["linkedin_url", "work_email", "company_domain"],
  );

  assert.deepEqual(identifiers, {
    linkedin_url: "https://linkedin.com/in/alex",
    company_domain: "acme.com",
  });
});
