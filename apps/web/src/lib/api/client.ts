import type {
  CampaignCreate,
  CampaignLaunchView,
  CampaignList,
  ConnectionSummary,
  ControlInput,
  DecisionView,
  ErrorEnvelope,
  GoogleConnectStart,
  HealthReady,
  LedgerPage,
  MembershipView,
  MissionDetail,
  OrganizationView,
  PolicyUpdate,
  ProfileUpdate,
  ResolveInput,
  SourceInput,
  TaskAccepted,
} from "@/lib/contracts";
import { SCHEMA_VERSION } from "@/lib/contracts";
import { ApiError } from "./errors";
import type { HttpMethod, Transport, TransportRequest } from "./transport";

export interface Session {
  accessToken: string;
  organizationId: string | null;
}

export interface ApiResult<T> {
  data: T;
  correlationId: string;
  status: number;
}

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  return typeof body === "object" && body !== null && "error" in body;
}

function stripFixtureTag<T>(data: T): T {
  if (data && typeof data === "object" && "_fixture" in data) {
    const { _fixture: _ignored, ...rest } = data as Record<string, unknown>;
    return rest as T;
  }
  return data;
}

export function newIdempotencyKey(scope: string): string {
  return `${scope}-${crypto.randomUUID()}`;
}

export class OutcomeClient {
  constructor(
    readonly transport: Transport,
    private readonly getSession: () => Session | null,
  ) {}

  get provenance(): "LIVE" | "FIXTURE" {
    return this.transport.kind;
  }

  private async call<T>(
    method: HttpMethod,
    path: string,
    options: {
      body?: unknown;
      query?: TransportRequest["query"];
      idempotencyKey?: string;
      auth?: boolean;
    } = {},
  ): Promise<ApiResult<T>> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (options.auth !== false) {
      const session = this.getSession();
      if (!session) {
        throw new ApiError({ status: 401, code: "UNAUTHENTICATED", message: "No session." });
      }
      headers.Authorization = `Bearer ${session.accessToken}`;
      if (session.organizationId) headers["X-Organization-ID"] = session.organizationId;
    }
    if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

    let response;
    try {
      response = await this.transport.send({
        method,
        path,
        query: options.query,
        body: options.body,
        headers,
      });
    } catch (cause) {
      throw new ApiError({
        status: 0,
        code: "NETWORK",
        message: cause instanceof Error ? cause.message : "Network request failed.",
        retryable: true,
      });
    }

    const body = stripFixtureTag(response.body);
    if (isErrorEnvelope(body)) {
      throw new ApiError({
        status: response.status,
        code: body.error.code,
        message: body.error.message,
        retryable: body.error.retryable,
        details: (body.error.details ?? {}) as Record<string, unknown>,
        correlationId: body.correlation_id,
      });
    }
    if (
      response.status >= 400 ||
      typeof body !== "object" ||
      body === null ||
      !("data" in body) ||
      (body as { schema_version?: string }).schema_version !== SCHEMA_VERSION
    ) {
      throw new ApiError({
        status: response.status,
        code: response.status >= 500 ? "INTERNAL" : "BAD_RESPONSE",
        message: `Unexpected response (HTTP ${response.status}).`,
      });
    }
    const envelope = body as { data: T; correlation_id: string };
    return {
      data: stripFixtureTag(envelope.data),
      correlationId: envelope.correlation_id,
      status: response.status,
    };
  }

  health = {
    ready: () => this.call<HealthReady>("GET", "/health/ready", { auth: false }),
  };

  memberships = {
    list: () => this.call<{ items: MembershipView[] }>("GET", "/me/memberships"),
  };

  workspace = {
    get: () => this.call<OrganizationView>("GET", "/workspace"),
    updateProfile: (input: ProfileUpdate, idempotencyKey: string) =>
      this.call<OrganizationView>("PUT", "/workspace/profile", { body: input, idempotencyKey }),
    addSource: (input: SourceInput, idempotencyKey: string) =>
      this.call<TaskAccepted>("POST", "/workspace/sources", { body: input, idempotencyKey }),
    updatePolicy: (input: PolicyUpdate, idempotencyKey: string) =>
      this.call<OrganizationView>("PUT", "/workspace/policy", { body: input, idempotencyKey }),
  };

  google = {
    connect: (idempotencyKey: string) =>
      this.call<GoogleConnectStart>("POST", "/google/connect", {
        body: { purpose: "seller", return_path: "setup" },
        idempotencyKey,
      }),
    status: () => this.call<ConnectionSummary | null>("GET", "/google/status"),
  };

  campaigns = {
    list: (cursor?: string | null, limit = 25) =>
      this.call<CampaignList>("GET", "/campaigns", { query: { cursor: cursor ?? undefined, limit } }),
    create: (input: CampaignCreate, idempotencyKey: string) =>
      this.call<CampaignLaunchView>("POST", "/campaigns", { body: input, idempotencyKey }),
    get: (id: string) => this.call<MissionDetail>("GET", `/campaigns/${encodeURIComponent(id)}`),
    ledger: (id: string, cursor?: string | null, limit = 25) =>
      this.call<LedgerPage>("GET", `/campaigns/${encodeURIComponent(id)}/ledger`, {
        query: { cursor: cursor ?? undefined, limit },
      }),
    control: (id: string, input: ControlInput, idempotencyKey: string) =>
      this.call<TaskAccepted & { campaign_status: string; version: number }>(
        "POST",
        `/campaigns/${encodeURIComponent(id)}/control`,
        { body: input, idempotencyKey },
      ),
    poll: (id: string, idempotencyKey: string) =>
      this.call<TaskAccepted>("POST", `/campaigns/${encodeURIComponent(id)}/poll`, { idempotencyKey }),
  };

  decisions = {
    resolve: (id: string, input: ResolveInput, idempotencyKey: string) =>
      this.call<{ decision: DecisionView; task_id: string | null }>(
        "POST",
        `/decisions/${encodeURIComponent(id)}/resolve`,
        { body: input, idempotencyKey },
      ),
  };
}
