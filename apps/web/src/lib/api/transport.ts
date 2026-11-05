export type HttpMethod = "GET" | "POST" | "PUT";

export interface TransportRequest {
  method: HttpMethod;
  path: string;
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  headers: Record<string, string>;
}

export interface TransportResponse {
  status: number;
  body: unknown;
}

export interface Transport {
  /** LIVE means responses come from the Outcome API; FIXTURE means from local labeled fixtures. */
  readonly kind: "LIVE" | "FIXTURE";
  send(request: TransportRequest): Promise<TransportResponse>;
}

export function buildQuery(query: TransportRequest["query"]): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function createHttpTransport(baseUrl: string): Transport {
  const root = baseUrl.replace(/\/$/, "");
  return {
    kind: "LIVE",
    async send({ method, path, query, body, headers }) {
      const response = await fetch(`${root}/api/v1${path}${buildQuery(query)}`, {
        method,
        headers: body === undefined ? headers : { ...headers, "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
      });
      const text = await response.text();
      let parsed: unknown = null;
      if (text) {
        try {
          parsed = JSON.parse(text);
        } catch {
          parsed = { unparsable: text.slice(0, 200) };
        }
      }
      return { status: response.status, body: parsed };
    },
  };
}
