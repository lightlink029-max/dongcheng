type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function isEmpty(value: unknown) {
  return value === null
    || value === undefined
    || value === ""
    || (Array.isArray(value) && value.length === 0)
    || (value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0);
}

function mergeRecord(previousValue: unknown, currentValue: unknown): JsonRecord {
  const previous = asRecord(previousValue);
  const current = asRecord(currentValue);
  const merged: JsonRecord = { ...previous };
  for (const [key, value] of Object.entries(current)) {
    if (isEmpty(value) && !isEmpty(previous[key])) continue;
    if (value && typeof value === "object" && !Array.isArray(value) && previous[key] && typeof previous[key] === "object" && !Array.isArray(previous[key])) {
      merged[key] = mergeRecord(previous[key], value);
    } else {
      merged[key] = value;
    }
  }
  return merged;
}

function textKey(value: unknown) {
  return String(value ?? "").trim().toLocaleLowerCase();
}

function stringArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : [];
}

function mergeRecordList(
  previousValue: unknown,
  currentValue: unknown,
  identity: (item: JsonRecord, index: number) => string,
  limit: number,
) {
  const previous = Array.isArray(previousValue) ? previousValue.map(asRecord) : [];
  const current = Array.isArray(currentValue) ? currentValue.map(asRecord) : [];
  const merged = new Map<string, JsonRecord>();
  for (const [index, item] of [...previous, ...current].entries()) {
    const key = identity(item, index) || `row-${index}`;
    merged.set(key, mergeRecord(merged.get(key), item));
  }
  return [...merged.values()].slice(0, limit);
}

function mergeStringList(previousValue: unknown, currentValue: unknown, limit: number) {
  return [...new Set([...stringArray(previousValue), ...stringArray(currentValue)])].slice(0, limit);
}

export function hasMeaningfulResearchReport(value: unknown) {
  const report = asRecord(value);
  return String(report.summary ?? "").trim().length > 0
    || [report.trackCategories, report.productPool, report.marketHypotheses, report.buyerProfiles, report.buyerFamilyMatrix].some((item) => Array.isArray(item) && item.length > 0)
    || Object.keys(asRecord(report.sections)).length > 0
    || Object.keys(asRecord(report.playbook)).length > 0;
}

export function latestResearchReportRun<T extends { status?: unknown; result_payload?: unknown }>(runs: T[] | undefined) {
  return (runs ?? []).find((run) => ["complete", "partial"].includes(String(run.status)) && hasMeaningfulResearchReport(run.result_payload));
}

export function mergeResearchReports(previousValue: unknown, currentValue: unknown) {
  const previous = asRecord(previousValue);
  const current = asRecord(currentValue);
  const merged = mergeRecord(previous, current);
  merged.trackCategories = mergeRecordList(
    previous.trackCategories,
    current.trackCategories,
    (item) => textKey(item.name) || textKey(item.id),
    100,
  );
  merged.productPool = mergeRecordList(
    previous.productPool,
    current.productPool,
    (item) => [
      textKey(item.trackCategory),
      textKey(item.subcategory),
      textKey(item.name),
      stringArray(item.targetMarkets).map((market) => market.toUpperCase()).sort().join(","),
    ].join("|"),
    2000,
  );
  merged.marketHypotheses = mergeRecordList(
    previous.marketHypotheses,
    current.marketHypotheses,
    (item) => textKey(item.marketCode) || textKey(item.marketName),
    100,
  );
  merged.buyerProfiles = mergeRecordList(
    previous.buyerProfiles,
    current.buyerProfiles,
    (item) => [textKey(item.companyName), textKey(item.country)].join("|"),
    1000,
  );
  merged.buyerFamilyMatrix = mergeRecordList(
    previous.buyerFamilyMatrix,
    current.buyerFamilyMatrix,
    (item) => [textKey(item.companyName), textKey(item.country), textKey(item.trackCategory), textKey(item.productFamily)].join("|"),
    5000,
  );
  merged.sections = mergeRecord(previous.sections, current.sections);
  merged.playbook = mergeRecord(previous.playbook, current.playbook);
  merged.risks = mergeStringList(previous.risks, current.risks, 100);
  merged.actionPlan = mergeStringList(previous.actionPlan, current.actionPlan, 100);
  return merged;
}
