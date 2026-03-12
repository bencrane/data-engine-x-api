type MockFetchResponse =
  | {
      status?: number;
      body?: unknown;
    }
  | {
      error: Error;
    };

export function createMockFetch(responses: MockFetchResponse[]): typeof fetch {
  let index = 0;

  return (async () => {
    const next = responses[index];
    index += 1;

    if (!next) {
      throw new Error(`Unexpected fetch call #${index}`);
    }

    if ("error" in next) {
      throw next.error;
    }

    return new Response(next.body === undefined ? null : JSON.stringify(next.body), {
      status: next.status ?? 200,
      headers: {
        "Content-Type": "application/json",
      },
    });
  }) as typeof fetch;
}

export interface CapturedRequest {
  url: string | URL | Request;
  init?: RequestInit;
}

export function createCapturingMockFetch(
  responses: MockFetchResponse[],
): { fetchImpl: typeof fetch; captured: CapturedRequest[] } {
  let index = 0;
  const captured: CapturedRequest[] = [];

  const fetchImpl = (async (input: string | URL | Request, init?: RequestInit) => {
    captured.push({ url: input, init });

    const next = responses[index];
    index += 1;

    if (!next) {
      throw new Error(`Unexpected fetch call #${index}`);
    }

    if ("error" in next) {
      throw next.error;
    }

    return new Response(next.body === undefined ? null : JSON.stringify(next.body), {
      status: next.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  return { fetchImpl, captured };
}

export function timeoutError(message = "Timed out"): Error {
  const error = new Error(message);
  error.name = "TimeoutError";
  return error;
}
