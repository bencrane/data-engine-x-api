import { WorkflowContext } from "./context.js";
import { InternalApiClient } from "./internal-api.js";
import { WorkflowEntityType } from "./operations.js";

export class PersistenceConfirmationError extends Error {
  readonly path: string;
  readonly responseData: unknown;

  constructor(params: { path: string; message: string; responseData?: unknown }) {
    super(params.message);
    this.name = "PersistenceConfirmationError";
    this.path = params.path;
    this.responseData = params.responseData;
  }
}

export interface ConfirmedWriteParams<TResponse> {
  path: string;
  payload: unknown;
  timeoutMs?: number;
  validate?: (response: TResponse) => boolean;
  confirmationErrorMessage?: string;
}

export interface EntityStateUpsertResult {
  entity_id: string;
  [key: string]: unknown;
}

export interface UpsertEntityStateParams {
  pipelineRunId: string;
  entityType: WorkflowEntityType;
  cumulativeContext: WorkflowContext;
  lastOperationId?: string | null;
  timeoutMs?: number;
}

function hasEntityId(value: unknown): value is EntityStateUpsertResult {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    typeof (value as Record<string, unknown>).entity_id === "string"
  );
}

export async function confirmedInternalWrite<TResponse>(
  client: InternalApiClient,
  params: ConfirmedWriteParams<TResponse>,
): Promise<TResponse> {
  const response = await client.post<TResponse>(params.path, params.payload, {
    timeoutMs: params.timeoutMs,
  });

  if (params.validate && !params.validate(response)) {
    throw new PersistenceConfirmationError({
      path: params.path,
      message:
        params.confirmationErrorMessage ||
        `Persistence write could not be confirmed: ${params.path}`,
      responseData: response,
    });
  }

  return response;
}

export async function upsertEntityStateConfirmed(
  client: InternalApiClient,
  params: UpsertEntityStateParams,
): Promise<EntityStateUpsertResult> {
  return confirmedInternalWrite<EntityStateUpsertResult>(client, {
    path: "/api/internal/entity-state/upsert",
    payload: {
      pipeline_run_id: params.pipelineRunId,
      entity_type: params.entityType,
      cumulative_context: params.cumulativeContext,
      last_operation_id: params.lastOperationId ?? undefined,
    },
    timeoutMs: params.timeoutMs,
    validate: hasEntityId,
    confirmationErrorMessage: "Entity state upsert did not return an entity_id",
  });
}

export async function writeDedicatedTableConfirmed<TResponse>(
  client: InternalApiClient,
  params: ConfirmedWriteParams<TResponse>,
): Promise<TResponse> {
  return confirmedInternalWrite(client, params);
}
