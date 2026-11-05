import type { ErrorCode } from "@/lib/contracts";

export type ClientErrorCode = ErrorCode | "NETWORK" | "BAD_RESPONSE";

export class ApiError extends Error {
  readonly status: number;
  readonly code: ClientErrorCode;
  readonly retryable: boolean;
  readonly details: Record<string, unknown>;
  readonly correlationId: string | null;

  constructor(init: {
    status: number;
    code: ClientErrorCode;
    message: string;
    retryable?: boolean;
    details?: Record<string, unknown>;
    correlationId?: string | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.retryable = init.retryable ?? false;
    this.details = init.details ?? {};
    this.correlationId = init.correlationId ?? null;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Operator-facing explanation and recovery for each error code. */
export function describeError(error: unknown): { title: string; body: string } {
  if (!isApiError(error)) {
    return {
      title: "Something went wrong in the browser",
      body: error instanceof Error ? error.message : "An unexpected error occurred.",
    };
  }
  switch (error.code) {
    case "UNAUTHENTICATED":
      return { title: "Your session has ended", body: "Sign in again to continue." };
    case "FORBIDDEN":
      return {
        title: "You don't have access to this",
        body: "Your membership in this organization doesn't allow this action. Ask an owner, or switch organization.",
      };
    case "NOT_FOUND":
      return {
        title: "Not found in this organization",
        body: "It may belong to another organization, or it doesn't exist.",
      };
    case "CONFLICT":
      return {
        title: "This changed while you were looking at it",
        body: `${error.message} Reload to see the current version, then try again.`,
      };
    case "RECIPIENT_NOT_ALLOWED":
      return {
        title: "Recipient isn't on the consent allowlist",
        body: error.message,
      };
    case "DOMAIN_INVALID":
      return { title: "Setup isn't complete for this action", body: error.message };
    case "VALIDATION_FAILED":
      return { title: "Some fields need attention", body: error.message };
    case "RATE_LIMITED":
      return { title: "A workspace limit was reached", body: error.message };
    case "DEPENDENCY_UNAVAILABLE":
      return {
        title: "A dependency is unavailable",
        body: `${error.message} Work already accepted is kept and resumes when it recovers.`,
      };
    case "NETWORK":
      return {
        title: "Can't reach the Outcome API",
        body: "Check that the API is running and reachable, then retry.",
      };
    default:
      return { title: "The server returned an error", body: error.message };
  }
}
