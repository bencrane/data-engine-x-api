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
