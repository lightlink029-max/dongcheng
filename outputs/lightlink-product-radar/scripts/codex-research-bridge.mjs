#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { compactResearchStatus } from "../lib/research-context.mjs";

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
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(body?.error || `雷达返回 HTTP ${response.status}`);
  return body;
}

function help() {
  return [
    "LightLink 产品与市场调研 Bridge",
    "",
    "  status --project-id UUID [--candidate-id UUID | --review | --full] [--url URL]",
    "  import --file report.json --project-id UUID --run-id UUID [--url URL]",
    "  assist-import --file result.json --project-id UUID --candidate-id UUID --run-id UUID [--url URL]",
    "  images-import --file result.json --project-id UUID --run-id UUID [--url URL]",
    "",
    "报告格式：{ status, summary, recommendation, scorecard, buyerProfiles, buyerFamilyMatrix, trackCategories, productPool, marketHypotheses, playbook, sections, risks, actionPlan, evidence }",
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
  const projectId = option(args, "--project-id").trim();
  if (!projectId) throw new Error("需要 --project-id");

  if (command === "status") {
    const data = await request(baseUrl, `?view=research_project&projectId=${encodeURIComponent(projectId)}`);
    const output = args.includes("--full")
      ? data
      : compactResearchStatus(data, {
          candidateId: option(args, "--candidate-id").trim(),
          includeCandidates: args.includes("--review"),
        });
    console.log(JSON.stringify(output, null, 2));
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
      body: JSON.stringify({ action: "import_research_result", projectId, researchRunId: runId, report }),
    });
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  if (command === "assist-import") {
    const file = option(args, "--file").trim();
    const candidateId = option(args, "--candidate-id").trim();
    if (!file || !candidateId) throw new Error("assist-import 需要 --file 和 --candidate-id");
    const report = JSON.parse(await readFile(resolve(file), "utf8"));
    const result = await request(baseUrl, "", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "import_candidate_assist", projectId, candidateId, report }),
    });
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  if (command === "images-import") {
    const file = option(args, "--file").trim();
    if (!file) throw new Error("images-import 需要 --file");
    const report = JSON.parse(await readFile(resolve(file), "utf8"));
    const result = await request(baseUrl, "", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "import_candidate_images", projectId, report }),
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
