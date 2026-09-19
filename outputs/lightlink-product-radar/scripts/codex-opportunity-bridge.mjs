#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

function option(args, name, fallback = "") {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
}

function radarUrl(args) {
  const candidate = option(args, "--url", process.env.LIGHTLINK_RADAR_URL || "http://127.0.0.1:8787");
  const parsed = new URL(candidate);
  if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("雷达地址必须使用 http 或 https");
  return parsed.toString().replace(/\/$/, "");
}

async function request(baseUrl, path = "", init) {
  const response = await fetch(`${baseUrl}/api/radar${path}`, init);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `雷达返回 HTTP ${response.status}`);
  return body;
}

function compactStatus(data) {
  return {
    opportunity: data.opportunity,
    matrix: data.matrix,
    evidence: (data.evidence ?? []).map((item) => ({
      evidenceType: item.evidence_type,
      sourceGrade: item.source_grade,
      title: item.title,
      sourceUrl: item.source_url,
      note: item.note,
      marketCode: item.market_code,
      period: item.period,
      metrics: item.metrics,
    })),
    tradeSummary: {
      rowCount: data.tradeData?.length ?? 0,
      availableCount: (data.tradeData ?? []).filter((item) => item.data_status === "available").length,
      sources: [...new Set((data.tradeData ?? []).map((item) => item.source_name).filter(Boolean))],
      commodityCodes: [...new Set((data.tradeData ?? []).map((item) => item.commodity_code).filter(Boolean))],
      periods: [...new Set((data.tradeData ?? []).map((item) => item.period).filter(Boolean))].sort(),
    },
    requests: data.requests,
  };
}

function help() {
  return [
    "LightLink 商机公开证据 Bridge",
    "",
    "  status --opportunity-id UUID [--url URL]",
    "  import --file result.json --opportunity-id UUID --run-id UUID [--url URL]",
    "",
    "导入格式：{ summary, suggestedNextAction, evidence: [{ evidenceType, sourceGrade, title, sourceUrl, note, marketCode, period, metrics, capturedAt }] }",
    "只导入可直接核验的公开链接；不能把公司品类页描述成真实询盘或采购意向。",
  ].join("\n");
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || "help";
  if (["help", "--help", "-h"].includes(command)) {
    console.log(help());
    return;
  }
  const baseUrl = radarUrl(args);
  const opportunityId = option(args, "--opportunity-id").trim();
  if (!opportunityId) throw new Error(`${command} 需要 --opportunity-id`);
  if (command === "status") {
    const data = await request(baseUrl, `?view=opportunity_validation_context&opportunityId=${encodeURIComponent(opportunityId)}`);
    console.log(JSON.stringify(compactStatus(data), null, 2));
    return;
  }
  if (command === "import") {
    const file = option(args, "--file").trim();
    const runId = option(args, "--run-id").trim();
    if (!file || !runId) throw new Error("import 需要 --file 和 --run-id");
    const report = JSON.parse(await readFile(resolve(file), "utf8"));
    const result = await request(baseUrl, "", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "import_opportunity_validation", opportunityId, runId, report }),
    });
    console.log(JSON.stringify({ imported: result.imported, evidenceCount: result.context?.evidence?.length ?? 0 }, null, 2));
    return;
  }
  throw new Error(`未知命令：${command}\n\n${help()}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
