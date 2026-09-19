import http from "node:http";

const host = "127.0.0.1";
const port = Number.parseInt(process.env.LIGHTLINK_GOOGLE_API_BRIDGE_PORT ?? "8791", 10);
const maxBodyBytes = 1_000_000;

function sendJson(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
  });
  response.end(body);
}

async function readBody(request) {
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    length += chunk.length;
    if (length > maxBodyBytes) throw new Error("request_too_large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

function copyResponseHeaders(upstream, response) {
  const contentType = upstream.headers.get("content-type");
  const requestId = upstream.headers.get("request-id");
  if (contentType) response.setHeader("content-type", contentType);
  if (requestId) response.setHeader("request-id", requestId);
  response.setHeader("cache-control", "no-store");
}

const server = http.createServer(async (request, response) => {
  try {
    const requestUrl = new URL(request.url ?? "/", `http://${host}:${port}`);
    if (request.method === "GET" && requestUrl.pathname === "/health") {
      sendJson(response, 200, { ok: true });
      return;
    }
    if (request.method !== "POST") {
      sendJson(response, 405, { error: "method_not_allowed" });
      return;
    }

    const body = await readBody(request);
    let upstreamUrl;
    const headers = { accept: "application/json" };
    if (requestUrl.pathname === "/oauth/token") {
      upstreamUrl = "https://oauth2.googleapis.com/token";
      headers["content-type"] = "application/x-www-form-urlencoded";
    } else if (requestUrl.pathname === "/ads/keyword-ideas") {
      const customerId = requestUrl.searchParams.get("customerId") ?? "";
      if (!/^\d{10}$/.test(customerId)) {
        sendJson(response, 400, { error: "invalid_customer_id" });
        return;
      }
      upstreamUrl = `https://googleads.googleapis.com/v25/customers/${customerId}:generateKeywordIdeas`;
      headers["content-type"] = "application/json";
      for (const name of ["authorization", "developer-token", "login-customer-id"]) {
        const value = request.headers[name];
        if (typeof value === "string" && value) headers[name] = value;
      }
    } else {
      sendJson(response, 404, { error: "route_not_allowed" });
      return;
    }

    const upstream = await fetch(upstreamUrl, {
      method: "POST",
      headers,
      body,
      signal: AbortSignal.timeout(25_000),
    });
    copyResponseHeaders(upstream, response);
    response.writeHead(upstream.status);
    response.end(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    const timeout = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
    sendJson(response, timeout ? 504 : 502, { error: timeout ? "upstream_timeout" : "upstream_unavailable" });
  }
});

server.listen(port, host, () => {
  process.stdout.write(`LightLink Google API bridge listening on http://${host}:${port}\n`);
});

function shutdown() {
  server.close(() => process.exit(0));
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
