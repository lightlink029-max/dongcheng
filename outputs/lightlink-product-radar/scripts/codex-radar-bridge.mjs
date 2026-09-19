#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { compactRadarStatus } from "../lib/radar-context.mjs";

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

async function request(baseUrl, init) {
  const response = await fetch(`${baseUrl}/api/radar`, init);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `雷达返回 HTTP ${response.status}`);
  return body;
}

function help() {
  return [
    "LightLink Radar Codex Bridge",
    "",
    "  status [--full] [--url URL]",
    "  create --query TEXT --market GB --language en --days 30 [--mode seed|discover] [--url URL]",
    "  import --file result.json [--run-id UUID] [--url URL]",
    "",
    "import 文件格式：{ query, market, language, windowDays, scanMode, resultLimit, rows: [...] }",
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
  if (command === "status") {
    const data = await request(baseUrl);
    console.log(JSON.stringify(args.includes("--full") ? data : compactRadarStatus(data), null, 2));
    return;
  }
  if (command === "create") {
    const query = option(args, "--query").trim();
    const market = option(args, "--market", "US").toUpperCase();
    const language = option(args, "--language", "en").toLowerCase();
    const windowDays = Number(option(args, "--days", "30"));
    const mode = option(args, "--mode", "seed") === "discover" ? "discover" : "seed";
    if (!query) throw new Error("create 需要 --query");
    const result = await request(baseUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "create_scan", mode, query, market, language, windowDays }),
    });
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  if (command === "import") {
    const file = option(args, "--file");
    if (!file) throw new Error("import 需要 --file result.json");
    const input = JSON.parse(await readFile(resolve(file), "utf8"));
    const runId = option(args, "--run-id", input.runId || "");
    const result = await request(baseUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...input, action: "import_observations", origin: "assistant", runId: runId || undefined }),
    });
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  throw new Error(`未知命令：${command}\n\n${help()}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
