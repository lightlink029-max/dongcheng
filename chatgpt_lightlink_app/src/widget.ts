import { readFile } from "node:fs/promises";

export async function loadCockpitHtml(): Promise<string> {
  return readFile(new URL("../widget/cockpit.html", import.meta.url), "utf8");
}
