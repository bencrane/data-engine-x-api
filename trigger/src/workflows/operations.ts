import { InternalApiClient } from "./internal-api.js";

export type WorkflowEntityType = "company" | "person" | "job";

export interface OperationExecutionResult {
  run_id: string;
  operation_id: string;
  status: string;
  output?: Record<string, unknown> | null;
  provider_attempts?: Array<Record<string, unknown>>;
  missing_inputs?: string[];
}

export interface ExecuteOperationParams {
  operationId: string;
  entityType: WorkflowEntityType;
  input: Record<string, unknown>;
  options?: Record<string, unknown> | null;
  timeoutMs?: number;
}

function isOperationExecutionResult(value: unknown): value is OperationExecutionResult {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.run_id === "string" &&
    typeof candidate.operation_id === "string" &&
    typeof candidate.status === "string"
  );
}

export function isFailedOperationResult(result: OperationExecutionResult): boolean {
  return result.status === "failed";
}

export async function executeOperation(
  client: InternalApiClient,
  params: ExecuteOperationParams,
): Promise<OperationExecutionResult> {
  return client.post<OperationExecutionResult>(
    "/api/v1/execute",
    {
      operation_id: params.operationId,
      entity_type: params.entityType,
      input: params.input,
      options: params.options ?? undefined,
    },
    {
      timeoutMs: params.timeoutMs,
      validate: isOperationExecutionResult,
      validationErrorMessage: `Execute response failed validation: ${params.operationId}`,
    },
  );
}
