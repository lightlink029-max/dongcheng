import { randomUUID } from "node:crypto";

import express, { type Request, type Response } from "express";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import * as z from "zod/v4";

import { OdooClient, type JsonObject } from "./odoo-client.js";
import { loadCockpitHtml } from "./widget.js";

const COCKPIT_URI = "ui://lightlink/operations-cockpit-v1.html";

const projectId = z.number().int().positive();
const optionalProjectId = projectId.optional();
const outputObject = z.looseObject({});

function textResult(label: string, data: JsonObject) {
  return {
    structuredContent: data,
    content: [{ type: "text" as const, text: label }],
  };
}

function client(): OdooClient {
  return new OdooClient();
}

export async function createServer(): Promise<McpServer> {
  const cockpitHtml = await loadCockpitHtml();
  const server = new McpServer(
    { name: "lightlink-ai-operations", version: "1.0.0" },
    {
      instructions: "Odoo is the source of truth. Read evidence before proposing a change. Never invent product specifications, certifications, prices, stock, customer cases, or delivery promises. For writes, call prepare_ai_action, show the preview, wait for explicit user confirmation, then call commit_ai_action once with a fresh idempotency key. Never expose API keys or raw customer exports.",
    },
  );

  server.registerResource("lightlink-operations-cockpit", COCKPIT_URI, {}, async () => ({
    contents: [{
      uri: COCKPIT_URI,
      mimeType: "text/html;profile=mcp-app",
      text: cockpitHtml,
      _meta: { ui: { prefersBorder: true } },
    }],
  }));

  server.registerTool("list_operations_projects", {
    title: "列出市场运营项目",
    description: "查找用户在Odoo中有权访问的运营项目，并返回项目ID、赛道、市场、负责人和状态。",
    inputSchema: { limit: z.number().int().min(1).max(100).default(50) },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async ({ limit }) => textResult("已读取可访问的运营项目。", await client().post(
    "/psc/ai/v1/projects", { limit },
  )));

  server.registerTool("start_ai_run", {
    title: "开始AI运营任务",
    description: "开始一次可审计的ChatGPT运营任务。执行一组相关分析或行动前调用，并把返回的run_id传给后续行动。",
    inputSchema: {
      intent: z.string().min(1).max(500),
      project_id: optionalProjectId,
      input_summary: z.string().max(4000).optional(),
    },
    outputSchema: outputObject,
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("AI运营任务已开始并记录。", await client().post(
    "/psc/ai/v1/runs/start", input,
  )));

  server.registerTool("finish_ai_run", {
    title: "结束AI运营任务",
    description: "在本次运营分析和已批准行动处理完毕后，写入结果摘要与关联记录。",
    inputSchema: {
      run_id: projectId,
      state: z.enum(["done", "partial", "failed"]).default("done"),
      summary: z.string().max(4000).optional(),
      related_records: z.array(z.record(z.string(), z.unknown())).optional(),
    },
    outputSchema: outputObject,
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("AI运营任务结果已记录。", await client().post(
    "/psc/ai/v1/runs/finish", input,
  )));

  server.registerTool("get_daily_operations_snapshot", {
    title: "读取今日运营驾驶舱",
    description: "读取项目阻塞、发布异常、高价值客户和待批准行动。用户询问今天做什么、有什么异常或增长机会时使用。",
    inputSchema: { project_id: optionalProjectId, limit: z.number().int().min(1).max(50).default(12) },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已读取今日运营快照。", await client().post(
    "/psc/ai/v1/daily-snapshot", input,
  )));

  server.registerTool("get_product_market_context", {
    title: "读取产品市场依据",
    description: "读取一个项目产品的价格、MOQ、交期、核实属性、合规门槛和评分。分析产品上市或生成内容前使用。",
    inputSchema: { project_product_id: projectId },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已读取产品与市场事实。", await client().post(
    "/psc/ai/v1/product-context", input,
  )));

  server.registerTool("get_content_backlog", {
    title: "读取内容计划",
    description: "读取项目中尚未发布的结构化内容计划及其产品、市场、渠道和要求。",
    inputSchema: { project_id: projectId, limit: z.number().int().min(1).max(100).default(30) },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已读取内容计划。", await client().post(
    "/psc/ai/v1/content-backlog", input,
  )));

  server.registerTool("get_publication_exceptions", {
    title: "读取发布异常",
    description: "读取发布失败任务及环境、账号、渠道和错误依据。不要自动重试；先判断是否属于安全的临时故障。",
    inputSchema: { project_id: optionalProjectId, limit: z.number().int().min(1).max(100).default(30) },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已读取发布异常。", await client().post(
    "/psc/ai/v1/publication-exceptions", input,
  )));

  server.registerTool("get_account_environment_health", {
    title: "读取账号与环境健康",
    description: "读取账号集群、渠道账号、Windows节点关联和最近环境校验状态；不会返回密码、Token或固定IP。",
    inputSchema: { project_id: optionalProjectId, limit: z.number().int().min(1).max(100).default(30) },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已读取账号与环境健康状态。", await client().post(
    "/psc/ai/v1/account-health", input,
  )));

  server.registerTool("get_priority_leads", {
    title: "读取优先客户",
    description: "读取近期高价值客户、阶段、来源、需求、下一活动和负责人，用于生成可核实的跟进建议。",
    inputSchema: {
      project_id: optionalProjectId,
      days: z.number().int().min(1).max(365).default(7),
      limit: z.number().int().min(1).max(100).default(20),
    },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已读取优先客户。", await client().post(
    "/psc/ai/v1/priority-leads", input,
  )));

  server.registerTool("get_campaign_performance", {
    title: "读取经营效果",
    description: "汇总曝光、点击、询盘、有效客户、报价、订单、收入和毛利漏斗，用于复盘和提出可衡量实验。",
    inputSchema: {
      project_id: projectId,
      date_from: z.string().date().optional(),
      date_to: z.string().date().optional(),
    },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已读取经营效果。", await client().post(
    "/psc/ai/v1/campaign-performance", input,
  )));

  server.registerTool("prepare_ai_action", {
    title: "准备Odoo行动",
    description: "准备一项受控写操作并返回变更预览和短期确认令牌。调用后必须向用户展示预览，不能在同一轮自动提交。",
    inputSchema: {
      action_type: z.enum([
        "launch_project", "create_content_plan", "create_content_draft",
        "create_lead_followup", "create_project_task", "create_optimization",
        "close_optimization", "retry_publication", "record_feedback",
        "initialize_medical_test_data", "complete_medical_test_scenario",
        "cleanup_medical_test_data",
      ]),
      title: z.string().min(1).max(200),
      reason: z.string().min(1).max(4000),
      payload: z.record(z.string(), z.unknown()),
      priority: z.enum(["0", "1", "2", "3"]).default("2"),
      risk_level: z.enum(["low", "medium", "high"]).default("medium"),
      estimated_impact: z.string().max(500).optional(),
      evidence: z.array(z.record(z.string(), z.unknown())).optional(),
      run_id: projectId.optional(),
    },
    outputSchema: outputObject,
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("行动预览已创建，等待用户明确批准。", await client().post(
    "/psc/ai/v1/actions/prepare", input,
  )));

  server.registerTool("commit_ai_action", {
    title: "执行已批准的Odoo行动",
    description: "仅在用户明确批准刚刚展示的行动预览后调用。使用prepare返回的令牌，并为本次逻辑操作生成唯一幂等键。",
    inputSchema: {
      action_token: z.string().min(20),
      idempotency_key: z.string().uuid().default(() => randomUUID()),
    },
    outputSchema: outputObject,
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已执行获批行动。", await client().post(
    "/psc/ai/v1/actions/commit", input,
  )));

  server.registerTool("get_ai_action_status", {
    title: "查询AI行动状态",
    description: "查询行动是否已执行、失败或仍待批准。",
    inputSchema: { action_id: projectId },
    outputSchema: outputObject,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async (input) => textResult("已读取行动状态。", await client().post(
    "/psc/ai/v1/actions/status", input,
  )));

  server.registerTool("render_operations_cockpit", {
    title: "显示LightLink运营驾驶舱",
    description: "把get_daily_operations_snapshot返回的最终快照显示为集中式驾驶舱。必须先读取快照，再原样传入本工具。",
    inputSchema: { snapshot: z.record(z.string(), z.unknown()) },
    outputSchema: outputObject,
    _meta: {
      ui: { resourceUri: COCKPIT_URI },
      "openai/outputTemplate": COCKPIT_URI,
      "openai/toolInvocation/invoking": "正在打开运营驾驶舱…",
      "openai/toolInvocation/invoked": "运营驾驶舱已打开。",
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  }, async ({ snapshot }) => textResult("正在显示LightLink运营驾驶舱。", snapshot));

  return server;
}

async function startStdio(): Promise<void> {
  const server = await createServer();
  await server.connect(new StdioServerTransport());
}

async function startHttp(): Promise<void> {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  app.get("/health", (_request, response) => response.json({ ok: true, service: "lightlink-ai-operations" }));
  app.post("/mcp", async (request: Request, response: Response) => {
    const sharedSecret = process.env.MCP_SHARED_SECRET;
    if (!sharedSecret || request.headers.authorization !== `Bearer ${sharedSecret}`) {
      response.status(401).json({ error: "unauthorized" });
      return;
    }
    const server = await createServer();
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    response.on("close", () => {
      void transport.close();
      void server.close();
    });
    await server.connect(transport);
    await transport.handleRequest(request, response, request.body);
  });
  app.get("/mcp", (_request, response) => response.status(405).json({ error: "method_not_allowed" }));
  app.delete("/mcp", (_request, response) => response.status(405).json({ error: "method_not_allowed" }));
  const port = Number(process.env.MCP_PORT || 8787);
  app.listen(port, "0.0.0.0", () => {
    process.stderr.write(`LightLink MCP listening on port ${port}.\n`);
  });
}

const transport = (process.env.MCP_TRANSPORT || "stdio").toLowerCase();
if (transport === "http") {
  await startHttp();
} else {
  await startStdio();
}
