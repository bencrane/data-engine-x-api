import assert from "node:assert/strict";
import test from "node:test";

import { evaluateCondition } from "../evaluate-condition";

test("exists op handles present, null, missing, and empty string", () => {
  assert.equal(evaluateCondition({ field: "pricing_page_url", op: "exists" }, { pricing_page_url: "https://acme.com/pricing" }), true);
  assert.equal(evaluateCondition({ field: "pricing_page_url", op: "exists" }, { pricing_page_url: null }), false);
  assert.equal(evaluateCondition({ field: "pricing_page_url", op: "exists" }, {}), false);
  assert.equal(evaluateCondition({ field: "pricing_page_url", op: "exists" }, { pricing_page_url: "" }), false);
});

test("eq op matches value and handles null field", () => {
  assert.equal(evaluateCondition({ field: "has_raised_vc", op: "eq", value: true }, { has_raised_vc: true }), true);
  assert.equal(evaluateCondition({ field: "has_raised_vc", op: "eq", value: true }, { has_raised_vc: false }), false);
  assert.equal(evaluateCondition({ field: "has_raised_vc", op: "eq", value: true }, { has_raised_vc: null }), false);
});

test("ne op is inverse of eq", () => {
  assert.equal(evaluateCondition({ field: "segment", op: "ne", value: "enterprise" }, { segment: "midmarket" }), true);
  assert.equal(evaluateCondition({ field: "segment", op: "ne", value: "enterprise" }, { segment: "enterprise" }), false);
});

test("numeric ops support string-to-number coercion", () => {
  const context = { employee_count: "120" };
  assert.equal(evaluateCondition({ field: "employee_count", op: "lt", value: 200 }, context), true);
  assert.equal(evaluateCondition({ field: "employee_count", op: "gt", value: 50 }, context), true);
  assert.equal(evaluateCondition({ field: "employee_count", op: "lte", value: 120 }, context), true);
  assert.equal(evaluateCondition({ field: "employee_count", op: "gte", value: 121 }, context), false);
});

test("contains op is case-sensitive", () => {
  assert.equal(
    evaluateCondition(
      { field: "current_job_title", op: "contains", value: "VP" },
      { current_job_title: "VP of Engineering" },
    ),
    true,
  );
  assert.equal(
    evaluateCondition(
      { field: "current_job_title", op: "contains", value: "vp" },
      { current_job_title: "VP of Engineering" },
    ),
    false,
  );
});

test("icontains op is case-insensitive", () => {
  assert.equal(
    evaluateCondition(
      { field: "current_job_title", op: "icontains", value: "director" },
      { current_job_title: "Director of Marketing" },
    ),
    true,
  );
});

test("in op checks membership in list", () => {
  assert.equal(
    evaluateCondition(
      { field: "country_code", op: "in", value: ["US", "CA", "GB"] },
      { country_code: "CA" },
    ),
    true,
  );
  assert.equal(
    evaluateCondition(
      { field: "country_code", op: "in", value: ["US", "CA", "GB"] },
      { country_code: "DE" },
    ),
    false,
  );
});

test("all op requires all conditions to pass", () => {
  assert.equal(
    evaluateCondition(
      {
        all: [
          { field: "pricing_page_url", op: "exists" },
          { field: "employee_count", op: "gt", value: 10 },
        ],
      },
      { pricing_page_url: "https://acme.com/pricing", employee_count: 50 },
    ),
    true,
  );
  assert.equal(
    evaluateCondition(
      {
        all: [
          { field: "pricing_page_url", op: "exists" },
          { field: "employee_count", op: "gt", value: 10 },
        ],
      },
      { pricing_page_url: "https://acme.com/pricing", employee_count: 5 },
    ),
    false,
  );
});

test("any op requires at least one condition to pass", () => {
  assert.equal(
    evaluateCondition(
      {
        any: [
          { field: "current_job_title", op: "icontains", value: "VP" },
          { field: "current_job_title", op: "icontains", value: "Director" },
          { field: "current_job_title", op: "icontains", value: "Head of" },
        ],
      },
      { current_job_title: "Head of Sales" },
    ),
    true,
  );
  assert.equal(
    evaluateCondition(
      {
        any: [
          { field: "current_job_title", op: "icontains", value: "VP" },
          { field: "current_job_title", op: "icontains", value: "Director" },
        ],
      },
      { current_job_title: "Engineering Manager" },
    ),
    false,
  );
});

test("dot notation resolves nested fields", () => {
  assert.equal(
    evaluateCondition(
      { field: "company_profile.industry", op: "eq", value: "SaaS" },
      { company_profile: { industry: "SaaS" } },
    ),
    true,
  );
});

test("null and empty conditions default to true", () => {
  assert.equal(evaluateCondition(null, {}), true);
  assert.equal(evaluateCondition(undefined, {}), true);
  assert.equal(evaluateCondition({}, {}), true);
});
