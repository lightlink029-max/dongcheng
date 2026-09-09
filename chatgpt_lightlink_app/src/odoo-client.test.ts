import assert from "node:assert/strict";
import test from "node:test";

import { normalizeOdooUrl, OdooClient, OdooGatewayError } from "./odoo-client.js";

test("normalizeOdooUrl accepts HTTPS and removes trailing slashes", () => {
  assert.equal(normalizeOdooUrl("https://odoo.example.com///"), "https://odoo.example.com");
});

test("normalizeOdooUrl rejects insecure remote HTTP", () => {
  assert.throws(() => normalizeOdooUrl("http://odoo.example.com"), /HTTPS/);
});

test("OdooClient sends bearer auth and unwraps gateway data", async () => {
  const fakeFetch: typeof fetch = async (_input, init) => {
    assert.equal(new Headers(init?.headers).get("authorization"), "Bearer test-key");
    return new Response(JSON.stringify({ ok: true, data: { projects: [] } }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const client = new OdooClient("https://odoo.example.com", "test-key", fakeFetch);
  assert.deepEqual(await client.post("/psc/ai/v1/projects"), { projects: [] });
});

test("OdooClient returns a sanitized gateway error", async () => {
  const fakeFetch: typeof fetch = async () => new Response(JSON.stringify({
    ok: false,
    error: "access_denied",
    message: "No access",
  }), { status: 403, headers: { "content-type": "application/json" } });
  const client = new OdooClient("https://odoo.example.com", "test-key", fakeFetch);
  await assert.rejects(
    () => client.post("/psc/ai/v1/projects"),
    (error: unknown) => error instanceof OdooGatewayError && error.code === "access_denied",
  );
});
