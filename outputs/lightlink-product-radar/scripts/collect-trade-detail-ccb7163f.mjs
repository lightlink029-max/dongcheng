#!/usr/bin/env node

import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const outputFile = resolve(process.argv[2] || "trade-detail-ccb7163f-8f0d-416b-ae09-af421a6742d5.json");
const collectedAt = new Date().toISOString();
const period = "2025";
const reporters = [
  { code: "GB", numeric: 826 },
  { code: "SE", numeric: 752, eurostatDataset: "DS-045409" },
  { code: "NO", numeric: 578, eurostatDataset: "DS-059341" },
  { code: "DK", numeric: 208, eurostatDataset: "DS-045409" },
  { code: "FI", numeric: 246, eurostatDataset: "DS-045409" },
];
const commodities = {
  "847180": "Units of automatic data-processing machines, n.e.c. in subheadings 8471.50, 8471.60 or 8471.70",
  "851762": "Machines for the reception, conversion and transmission or regeneration of voice, images or other data, including switching and routing apparatus",
};
const sleep = (milliseconds) => new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));

async function fetchJson(url, { attempts = 6, delayMs = 3_200 } = {}) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url, { headers: { accept: "application/json" } });
      if (response.status === 429) {
        lastError = new Error(`HTTP 429 from ${url}`);
        await sleep(delayMs * attempt);
        continue;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status} from ${url}`);
      return await response.json();
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await sleep(delayMs * attempt);
    }
  }
  throw lastError;
}

function chunks(items, size) {
  const result = [];
  for (let index = 0; index < items.length; index += size) result.push(items.slice(index, index + size));
  return result;
}

function topRows(rows, limit = 5) {
  return [...rows]
    .filter((row) => Number.isFinite(Number(row.value)))
    .sort((left, right) => Number(right.value) - Number(left.value))
    .slice(0, limit);
}

function observation(row) {
  return {
    reporterCode: row.reporterCode,
    partnerCode: row.partnerCode || "WORLD",
    classification: "HS2022",
    commodityCode: row.commodityCode,
    commodityLabel: commodities[row.commodityCode],
    flow: row.flow,
    period: row.period || period,
    frequency: "annual",
    metric: row.metric,
    value: row.value,
    unit: row.unit,
    sourceName: row.sourceName,
    sourceUrl: row.sourceUrl,
    sourceGrade: "official",
    status: row.status || "available",
    missingReason: row.missingReason || "",
    collectedAt,
  };
}

async function collectComtrade() {
  const referenceUrl = "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json";
  const reference = await fetchJson(referenceUrl, { attempts: 3, delayMs: 1_000 });
  const activePartners = reference.results
    .filter((item) => !item.isGroup && Number(item.PartnerCode) !== 0)
    .filter((item) => !item.entryExpiredDate || String(item.entryExpiredDate).slice(0, 4) >= period)
    .sort((left, right) => Number(left.PartnerCode) - Number(right.PartnerCode));
  const partnerByNumeric = new Map(activePartners.map((item) => [Number(item.PartnerCode), item]));
  const rawRows = [];

  for (const batch of chunks(activePartners, 18)) {
    const url = new URL("https://comtradeapi.un.org/public/v1/preview/C/A/HS");
    url.searchParams.set("period", period);
    url.searchParams.set("reporterCode", reporters.map((item) => item.numeric).join(","));
    url.searchParams.set("cmdCode", Object.keys(commodities).join(","));
    url.searchParams.set("flowCode", "M,X");
    url.searchParams.set("partnerCode", batch.map((item) => item.PartnerCode).join(","));
    url.searchParams.set("partner2Code", "0");
    url.searchParams.set("customsCode", "C00");
    url.searchParams.set("motCode", "0");
    url.searchParams.set("maxRecords", "500");
    url.searchParams.set("includeDesc", "true");
    url.searchParams.set("breakdownMode", "classic");
    const sourceUrl = url.toString();
    const response = await fetchJson(sourceUrl);
    for (const item of response.data || []) {
      if (!Object.hasOwn(commodities, String(item.cmdCode))) continue;
      if (!Number.isFinite(Number(item.primaryValue))) continue;
      const reporter = reporters.find((candidate) => candidate.numeric === Number(item.reporterCode));
      const partner = partnerByNumeric.get(Number(item.partnerCode));
      if (!reporter || !partner) continue;
      rawRows.push({
        reporterCode: reporter.code,
        partnerCode: String(partner.PartnerCodeIsoAlpha2 || partner.PartnerCodeIsoAlpha3 || partner.PartnerCode),
        commodityCode: String(item.cmdCode),
        flow: item.flowCode === "X" ? "export" : "import",
        metric: "trade_value_usd",
        value: Number(item.primaryValue),
        unit: "USD",
        sourceName: "UN Comtrade",
        sourceUrl,
      });
    }
    await sleep(3_200);
  }

  const selected = [];
  for (const reporter of reporters) {
    for (const commodityCode of Object.keys(commodities)) {
      for (const flow of ["import", "export"]) {
        const group = rawRows.filter((row) => row.reporterCode === reporter.code
          && row.commodityCode === commodityCode && row.flow === flow);
        const leaders = topRows(group);
        if (leaders.length) {
          selected.push(...leaders.map(observation));
          continue;
        }
        const sourceUrl = `https://comtradeapi.un.org/public/v1/preview/C/A/HS?period=${period}&reporterCode=${reporter.numeric}&cmdCode=${commodityCode}&flowCode=${flow === "export" ? "X" : "M"}&partnerCode=0&partner2Code=0&customsCode=C00&motCode=0&maxRecords=500`;
        selected.push(observation({
          reporterCode: reporter.code,
          partnerCode: "WORLD",
          commodityCode,
          flow,
          metric: "trade_value_usd",
          value: null,
          unit: "USD",
          sourceName: "UN Comtrade",
          sourceUrl,
          status: "missing",
          missingReason: "UN Comtrade public API returned no 2025 partner-level annual row for this reporter, HS6 code and flow at collection time.",
        }));
      }
    }
  }
  return selected;
}

function jsonStatValue(dataset, coordinates) {
  let offset = 0;
  for (let index = 0; index < dataset.id.length; index += 1) {
    offset = offset * dataset.size[index] + coordinates[dataset.id[index]];
  }
  const value = dataset.value?.[String(offset)];
  return value === undefined || value === null ? null : Number(value);
}

async function collectEurostat() {
  const selected = [];
  for (const reporter of reporters.filter((item) => item.eurostatDataset)) {
    for (const commodityCode of Object.keys(commodities)) {
      const url = new URL(`https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/${reporter.eurostatDataset}`);
      url.searchParams.set("lang", "EN");
      url.searchParams.set("freq", "A");
      url.searchParams.set("reporter", reporter.code);
      url.searchParams.set("product", commodityCode);
      url.searchParams.set("time", period);
      const sourceUrl = url.toString();
      const dataset = await fetchJson(sourceUrl, { attempts: 4, delayMs: 1_500 });
      const partnerIndexes = dataset.dimension?.partner?.category?.index || {};
      const flowIndexes = dataset.dimension?.flow?.category?.index || {};
      const indicatorIndexes = dataset.dimension?.indicators?.category?.index || {};
      const euroValueIndicator = indicatorIndexes.VALUE_IN_EUROS ?? indicatorIndexes.VALUE_EUR;
      const countryPartners = Object.entries(partnerIndexes)
        .filter(([partnerCode]) => /^[A-Z]{2}$/.test(partnerCode) && partnerCode !== reporter.code);

      for (const [flowCode, flow] of [["1", "import"], ["2", "export"]]) {
        const group = countryPartners.map(([partnerCode, partnerIndex]) => ({
          reporterCode: reporter.code,
          partnerCode,
          commodityCode,
          flow,
          metric: "trade_value_eur",
          value: jsonStatValue(dataset, {
            freq: 0,
            reporter: 0,
            partner: Number(partnerIndex),
            product: 0,
            flow: Number(flowIndexes[flowCode]),
            indicators: Number(euroValueIndicator),
            time: 0,
          }),
          unit: "EUR",
          sourceName: "Eurostat Comext",
          sourceUrl,
        })).filter((row) => row.value !== null);
        const leaders = topRows(group);
        if (leaders.length) {
          selected.push(...leaders.map(observation));
          continue;
        }
        selected.push(observation({
          reporterCode: reporter.code,
          partnerCode: "WORLD",
          commodityCode,
          flow,
          metric: "trade_value_eur",
          value: null,
          unit: "EUR",
          sourceName: "Eurostat Comext",
          sourceUrl,
          status: "missing",
          missingReason: "Eurostat Comext official API returned no 2025 country-partner annual value for this reporter, HS6 code and flow at collection time.",
        }));
      }
    }
  }

  for (const commodityCode of Object.keys(commodities)) {
    const sourceUrl = `https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409?lang=EN&freq=A&reporter=GB&product=${commodityCode}&time=${period}`;
    for (const flow of ["import", "export"]) {
      selected.push(observation({
        reporterCode: "GB",
        partnerCode: "WORLD",
        commodityCode,
        flow,
        metric: "trade_value_eur",
        value: null,
        unit: "EUR",
        sourceName: "Eurostat Comext",
        sourceUrl,
        status: "missing",
        missingReason: "Eurostat Comext has no 2025 United Kingdom partner series in this dataset; UN Comtrade is used for the UK partner detail.",
      }));
    }
  }
  return selected;
}

const observations = [...await collectComtrade(), ...await collectEurostat()];
if (observations.length > 500) throw new Error(`Import limit exceeded: ${observations.length}`);
await writeFile(outputFile, `${JSON.stringify({ observations }, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ outputFile, observations: observations.length, available: observations.filter((row) => row.status === "available").length, missing: observations.filter((row) => row.status === "missing").length }, null, 2));
