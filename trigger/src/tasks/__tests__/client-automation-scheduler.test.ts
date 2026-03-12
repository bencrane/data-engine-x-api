import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

test("client automation scheduler task is locked to internal evaluate endpoint", () => {
  const filePath = resolve(process.cwd(), "src", "tasks", "client-automation-scheduler.ts");
  const source = readFileSync(filePath, "utf8");

  assert.match(source, /schedules\.task\(/);
  assert.match(source, /id:\s*CLIENT_AUTOMATION_SCHEDULER_TASK_ID/);
  assert.match(source, /pattern:\s*"\*\/15 \* \* \* \*"/);
  assert.match(source, /timezone:\s*"UTC"/);
  assert.match(source, /"\/api\/internal\/client-automation\/schedules\/evaluate-due"/);
});
