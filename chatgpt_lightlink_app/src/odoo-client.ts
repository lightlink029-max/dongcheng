export type JsonObject = Record<string, unknown>;

export class OdooGatewayError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "odoo_gateway_error",
  ) {
    super(message);
  }
}

export function normalizeOdooUrl(value: string): string {
  const normalized = value.trim().replace(/\/+$/, "");
  if (!/^https:\/\//i.test(normalized) && !/^http:\/\/localhost(?::\d+)?$/i.test(normalized)) {
    throw new Error("ODOO_URL must use HTTPS (or localhost for local development). ");
  }
  return normalized;
}

export class OdooClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;

  constructor(
    baseUrl = process.env.ODOO_URL ?? "",
    apiKey = process.env.ODOO_API_KEY ?? "",
    private readonly fetchImpl: typeof fetch = fetch,
  ) {
    if (!baseUrl || !apiKey) {
      throw new Error("Configure ODOO_URL and ODOO_API_KEY before using LightLink tools.");
    }
    this.baseUrl = normalizeOdooUrl(baseUrl);
    this.apiKey = apiKey;
  }

  async post<T extends JsonObject>(path: string, payload: JsonObject = {}): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        "authorization": `Bearer ${this.apiKey}`,
        "content-type": "application/json",
        "accept": "application/json",
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(30_000),
    });
    const body = await response.json().catch(() => null) as {
      ok?: boolean;
      data?: T;
      error?: string;
      message?: string;
    } | null;
    if (!response.ok || !body?.ok || !body.data) {
      throw new OdooGatewayError(
        body?.message || `Odoo request failed with HTTP ${response.status}.`,
        response.status,
        body?.error,
      );
    }
    return body.data;
  }
}
