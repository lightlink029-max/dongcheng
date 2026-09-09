import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

test("registered tools expose valid MCP schemas and accept a cockpit snapshot", async () => {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [fileURLToPath(new URL("./server.js", import.meta.url))],
    stderr: "pipe",
  });
  const client = new Client({ name: "schema-test", version: "1.0.0" });

  try {
    await client.connect(transport);
    const result = await client.listTools();
    assert.equal(result.tools.length, 14);
    for (const tool of result.tools) {
      assert.equal(tool.inputSchema.type, "object", tool.name);
    }

    const rendered = await client.callTool({
      name: "render_operations_cockpit",
      arguments: { snapshot: { summary: {} } },
    });
    assert.notEqual(rendered.isError, true, JSON.stringify(rendered));
    assert.deepEqual(rendered.structuredContent, { summary: {} });
  } finally {
    await client.close();
  }
});
