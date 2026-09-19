export const PLATFORM_CREDENTIAL_ID_BY_NAME: Record<string, string> = {
  TikTok: "tiktok_business",
  "Meta Ads": "meta_graph",
  Instagram: "meta_graph",
  "Google Trends": "google_ads_keyword_planner",
  "Alibaba.com": "alibaba_open",
  Amazon: "amazon_sp_api",
  Temu: "temu_open",
  SHEIN: "shein_open",
  eBay: "ebay_developer",
  Walmart: "walmart_marketplace",
  Etsy: "etsy_open_api",
  AliExpress: "aliexpress_open",
  Shopee: "shopee_open",
  Lazada: "lazada_open",
  "Mercado Libre": "mercado_libre",
  Rakuten: "rakuten_web_service",
};

export function platformCredentialId(platform: string) {
  return PLATFORM_CREDENTIAL_ID_BY_NAME[platform] ?? null;
}
