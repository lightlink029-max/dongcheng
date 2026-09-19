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

function compactStatus(data, personaCode = "") {
  const library = data?.buyerLibrary ?? {};
  const taxonomy = library.taxonomy ?? {};
  const personas = Array.isArray(taxonomy.personaCategories) ? taxonomy.personaCategories : [];
  const selected = personaCode ? personas.filter((item) => item.code === personaCode) : personas;
  return {
    counts: {
      regions: library.stats?.regionCount ?? 0,
      personas: library.stats?.personaCategoryCount ?? 0,
      retiredPersonas: library.stats?.retiredPersonaCategoryCount ?? 0,
      pendingProposals: library.stats?.pendingPersonaProposalCount ?? 0,
      productTracks: library.stats?.trackCount ?? 0,
      productFamilies: library.stats?.masterFamilyCount ?? 0,
    },
    targetPersona: personaCode || null,
    personas: selected.map((item) => ({
      code: item.code,
      groupName: item.group_name,
      name: item.name,
      description: item.description,
      valueChainRole: item.value_chain_role,
      customerGroups: item.customer_groups,
      salesChannels: item.sales_channels,
      purchaseScenarios: item.purchase_scenarios,
      buyingTriggers: item.buying_triggers,
      orderCharacteristics: item.order_characteristics,
      complianceFocus: item.compliance_focus,
      sourceRefs: item.source_refs,
      version: item.version,
    })),
    regions: (taxonomy.regions ?? []).map((item) => ({ code: item.code, name: item.name, countries: item.countries })),
    productTracks: (taxonomy.productTracks ?? []).map((item) => ({ code: item.code, name: item.name, buyerValue: item.buyer_value })),
  };
}

function help() {
  return [
    "LightLink 全球买家画像分类 Bridge",
    "",
    "  status [--persona-code CODE] [--url URL]",
    "  import --file proposals.json --run-id UUID [--url URL]",
    "",
    "导入格式：{ mode, targetCode, personas: [{ code, groupName, name, description, valueChainRole, customerGroups, salesChannels, purchaseScenarios, buyingTriggers, orderCharacteristics, complianceFocus, sourceRefs, rationale }] }",
    "AI导入只生成待审核建议，不会直接覆盖正式画像。",
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
    const data = await request(baseUrl, "?view=research");
    console.log(JSON.stringify(compactStatus(data, option(args, "--persona-code").trim().toUpperCase()), null, 2));
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
      body: JSON.stringify({ action: "import_buyer_persona_proposals", runId, report }),
    });
    console.log(JSON.stringify({ imported: result.imported, pending: result.buyerLibrary?.stats?.pendingPersonaProposalCount ?? null }, null, 2));
    return;
  }
  throw new Error(`未知命令：${command}\n\n${help()}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
