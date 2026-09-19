const endpoint = process.env.LIGHTLINK_INTELLIGENCE_ENDPOINT || "http://127.0.0.1:8787/api/radar";
const intervalMs = Math.max(60_000, Number(process.env.LIGHTLINK_INTELLIGENCE_INTERVAL_MS) || 300_000);
let stopped = false;
let lastError = "";

async function executeDueMonitors() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "run_due_market_signal_monitors", limit: 20 }),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || `HTTP ${response.status}`);
    if (result.processed > 0) console.log(`[intelligence-scheduler] processed ${result.processed} due monitor(s)`);
    lastError = "";
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message !== lastError) console.error(`[intelligence-scheduler] ${message}`);
    lastError = message;
  } finally {
    clearTimeout(timeout);
  }
}

process.on("SIGINT", () => { stopped = true; });
process.on("SIGTERM", () => { stopped = true; });

while (!stopped) {
  await executeDueMonitors();
  await new Promise((resolve) => setTimeout(resolve, intervalMs));
}
