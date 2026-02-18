type Context = Record<string, unknown>;
type ComparisonOp =
  | "exists"
  | "eq"
  | "ne"
  | "lt"
  | "gt"
  | "lte"
  | "gte"
  | "contains"
  | "icontains"
  | "in";

type SingleCondition = {
  field: string;
  op: ComparisonOp;
  value?: unknown;
};

type GroupCondition = {
  all?: unknown;
  any?: unknown;
};

type Condition = SingleCondition | GroupCondition;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getValueByPath(context: Context, fieldPath: string): { found: boolean; value: unknown } {
  if (!fieldPath) {
    return { found: false, value: undefined };
  }

  const segments = fieldPath.split(".");
  let current: unknown = context;

  for (const segment of segments) {
    if (!isRecord(current) || !(segment in current)) {
      return { found: false, value: undefined };
    }
    current = current[segment];
  }

  return { found: true, value: current };
}

function isNonEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

function coerceToNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function evaluateSingleCondition(condition: SingleCondition, context: Context): boolean {
  const { found, value: fieldValue } = getValueByPath(context, condition.field);
  const { op, value: compareValue } = condition;

  if (op === "exists") {
    return found && isNonEmptyValue(fieldValue);
  }

  if (!found) {
    return false;
  }

  if (op === "eq") return fieldValue === compareValue;
  if (op === "ne") return fieldValue !== compareValue;

  if (op === "lt" || op === "gt" || op === "lte" || op === "gte") {
    const left = coerceToNumber(fieldValue);
    const right = coerceToNumber(compareValue);
    if (left === null || right === null) return false;
    if (op === "lt") return left < right;
    if (op === "gt") return left > right;
    if (op === "lte") return left <= right;
    return left >= right;
  }

  if (op === "contains" || op === "icontains") {
    if (compareValue === null || compareValue === undefined) return false;
    const haystack = String(fieldValue);
    const needle = String(compareValue);
    if (op === "contains") return haystack.includes(needle);
    return haystack.toLowerCase().includes(needle.toLowerCase());
  }

  if (op === "in") {
    if (!Array.isArray(compareValue)) return false;
    return compareValue.includes(fieldValue);
  }

  return false;
}

export function evaluateCondition(
  condition: object | null | undefined,
  context: Record<string, unknown>,
): boolean {
  if (condition === null || condition === undefined) {
    return true;
  }

  if (!isRecord(condition)) {
    return false;
  }

  if (Object.keys(condition).length === 0) {
    return true;
  }

  const conditionValue = condition as Condition;

  if ("all" in conditionValue) {
    const allConditions = conditionValue.all;
    if (!Array.isArray(allConditions)) return false;
    return allConditions.every((subCondition) =>
      evaluateCondition(isRecord(subCondition) ? subCondition : null, context),
    );
  }

  if ("any" in conditionValue) {
    const anyConditions = conditionValue.any;
    if (!Array.isArray(anyConditions)) return false;
    return anyConditions.some((subCondition) =>
      evaluateCondition(isRecord(subCondition) ? subCondition : null, context),
    );
  }

  if ("field" in conditionValue && "op" in conditionValue) {
    if (typeof conditionValue.field !== "string" || typeof conditionValue.op !== "string") {
      return false;
    }
    return evaluateSingleCondition(conditionValue as SingleCondition, context);
  }

  return false;
}
