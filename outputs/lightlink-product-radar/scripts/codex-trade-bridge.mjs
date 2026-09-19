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
    cache: data.cache,
    observations: (data.observations ?? []).map((item) => ({
      reporterCode: item.reporter_code,
      partnerCode: item.partner_code,
      classification: item.classification,
      commodityCode: item.commodity_code,
      commodityLabel: item.commodity_label,
      flow: item.flow,
      period: item.period,
      frequency: item.frequency,
      metric: item.metric,
      value: item.value,
      unit: item.unit,
      sourceName: item.source_name,
      sourceUrl: item.source_url,
      sourceGrade: item.source_grade,
      status: item.data_status,
      missingReason: item.missing_reason,
      collectedAt: item.collected_at,
    })),
    requests: data.requests,
  };
}

function help() {
  return [
    "LightLink 商机贸易数据 Bridge",
    "",
    "  status --opportunity-id UUID [--url URL]",
    "  import --file observations.json --opportunity-id UUID --run-id UUID [--url URL]",
    "",
    "导入格式：{ observations: [{ reporterCode, partnerCode, classification, commodityCode, commodityLabel, flow, period, frequency, metric, value, unit, sourceName, sourceUrl, sourceGrade, status, missingReason, collectedAt }] }",
    "贸易数据按产品家族与地区增量写入本地；缺失值必须是 null，确认零才可写 0。",
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
    const data = await request(baseUrl, `?view=trade_data_cache&opportunityId=${encodeURIComponent(opportunityId)}`);
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
      body: JSON.stringify({ action: "import_trade_data", opportunityId, runId, observations: report.observations }),
    });
    console.log(JSON.stringify({ imported: result.imported, available: result.available, cache: result.cache?.cache ?? null }, null, 2));
    return;
  }
  throw new Error(`未知命令：${command}\n\n${help()}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
