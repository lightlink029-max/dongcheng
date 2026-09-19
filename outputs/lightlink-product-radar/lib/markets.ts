type MarketOption = {
  code: string;
  label: string;
  defaultLanguage: string;
};

type MarketGroup = {
  label: string;
  options: readonly MarketOption[];
};

export const MARKET_GROUPS = [
  {
    label: "全球",
    options: [{ code: "GLOBAL", label: "全球 · 多地区", defaultLanguage: "en" }],
  },
  {
    label: "北美",
    options: [
      { code: "US", label: "美国", defaultLanguage: "en" },
      { code: "CA", label: "加拿大", defaultLanguage: "en" },
      { code: "MX", label: "墨西哥", defaultLanguage: "es" },
    ],
  },
  {
    label: "拉丁美洲",
    options: [
      { code: "BR", label: "巴西", defaultLanguage: "pt" },
      { code: "AR", label: "阿根廷", defaultLanguage: "es" },
      { code: "CL", label: "智利", defaultLanguage: "es" },
      { code: "CO", label: "哥伦比亚", defaultLanguage: "es" },
      { code: "PE", label: "秘鲁", defaultLanguage: "es" },
    ],
  },
  {
    label: "欧洲",
    options: [
      { code: "GB", label: "英国", defaultLanguage: "en" },
      { code: "DE", label: "德国", defaultLanguage: "de" },
      { code: "FR", label: "法国", defaultLanguage: "fr" },
      { code: "ES", label: "西班牙", defaultLanguage: "es" },
      { code: "IT", label: "意大利", defaultLanguage: "it" },
      { code: "NL", label: "荷兰", defaultLanguage: "nl" },
      { code: "BE", label: "比利时", defaultLanguage: "nl" },
      { code: "PL", label: "波兰", defaultLanguage: "pl" },
      { code: "PT", label: "葡萄牙", defaultLanguage: "pt" },
      { code: "SE", label: "瑞典", defaultLanguage: "sv" },
      { code: "NO", label: "挪威", defaultLanguage: "no" },
      { code: "DK", label: "丹麦", defaultLanguage: "da" },
      { code: "FI", label: "芬兰", defaultLanguage: "fi" },
      { code: "CH", label: "瑞士", defaultLanguage: "de" },
      { code: "AT", label: "奥地利", defaultLanguage: "de" },
      { code: "CZ", label: "捷克", defaultLanguage: "cs" },
      { code: "RO", label: "罗马尼亚", defaultLanguage: "ro" },
      { code: "GR", label: "希腊", defaultLanguage: "el" },
      { code: "UA", label: "乌克兰", defaultLanguage: "uk" },
      { code: "RU", label: "俄罗斯", defaultLanguage: "ru" },
    ],
  },
  {
    label: "中东与非洲",
    options: [
      { code: "AE", label: "阿联酋", defaultLanguage: "ar" },
      { code: "SA", label: "沙特阿拉伯", defaultLanguage: "ar" },
      { code: "TR", label: "土耳其", defaultLanguage: "tr" },
      { code: "IL", label: "以色列", defaultLanguage: "he" },
      { code: "EG", label: "埃及", defaultLanguage: "ar" },
      { code: "ZA", label: "南非", defaultLanguage: "en" },
      { code: "NG", label: "尼日利亚", defaultLanguage: "en" },
      { code: "KE", label: "肯尼亚", defaultLanguage: "en" },
      { code: "MA", label: "摩洛哥", defaultLanguage: "fr" },
    ],
  },
  {
    label: "亚洲",
    options: [
      { code: "CN", label: "中国", defaultLanguage: "zh" },
      { code: "IN", label: "印度", defaultLanguage: "en" },
      { code: "JP", label: "日本", defaultLanguage: "ja" },
      { code: "KR", label: "韩国", defaultLanguage: "ko" },
      { code: "SG", label: "新加坡", defaultLanguage: "en" },
      { code: "MY", label: "马来西亚", defaultLanguage: "ms" },
      { code: "ID", label: "印度尼西亚", defaultLanguage: "id" },
      { code: "TH", label: "泰国", defaultLanguage: "th" },
      { code: "VN", label: "越南", defaultLanguage: "vi" },
      { code: "PH", label: "菲律宾", defaultLanguage: "en" },
      { code: "PK", label: "巴基斯坦", defaultLanguage: "en" },
      { code: "BD", label: "孟加拉国", defaultLanguage: "bn" },
    ],
  },
  {
    label: "大洋洲",
    options: [
      { code: "AU", label: "澳大利亚", defaultLanguage: "en" },
      { code: "NZ", label: "新西兰", defaultLanguage: "en" },
    ],
  },
] as const satisfies readonly MarketGroup[];

export const LANGUAGE_OPTIONS = [
  { code: "en", label: "英语" },
  { code: "zh", label: "中文" },
  { code: "es", label: "西班牙语" },
  { code: "pt", label: "葡萄牙语" },
  { code: "fr", label: "法语" },
  { code: "de", label: "德语" },
  { code: "it", label: "意大利语" },
  { code: "nl", label: "荷兰语" },
  { code: "pl", label: "波兰语" },
  { code: "sv", label: "瑞典语" },
  { code: "no", label: "挪威语" },
  { code: "da", label: "丹麦语" },
  { code: "fi", label: "芬兰语" },
  { code: "cs", label: "捷克语" },
  { code: "ro", label: "罗马尼亚语" },
  { code: "el", label: "希腊语" },
  { code: "uk", label: "乌克兰语" },
  { code: "ru", label: "俄语" },
  { code: "ar", label: "阿拉伯语" },
  { code: "tr", label: "土耳其语" },
  { code: "he", label: "希伯来语" },
  { code: "hi", label: "印地语" },
  { code: "ja", label: "日语" },
  { code: "ko", label: "韩语" },
  { code: "ms", label: "马来语" },
  { code: "id", label: "印尼语" },
  { code: "th", label: "泰语" },
  { code: "vi", label: "越南语" },
  { code: "bn", label: "孟加拉语" },
] as const;

export const MARKET_OPTIONS = MARKET_GROUPS.reduce<MarketOption[]>(
  (options, group) => [...options, ...group.options],
  [],
);
export const MARKET_CODES = MARKET_OPTIONS.map((option) => option.code);
export const LANGUAGE_CODES = LANGUAGE_OPTIONS.map((option) => option.code);
export const SUPPORTED_MARKETS = new Set<string>(MARKET_CODES);
export const SUPPORTED_LANGUAGES = new Set<string>(LANGUAGE_CODES);

export function defaultLanguageForMarket(market: string) {
  return MARKET_OPTIONS.find((option) => option.code === market.toUpperCase())?.defaultLanguage ?? "en";
}

export function marketNameForCode(market: string) {
  const normalized = market.trim().toUpperCase();
  return MARKET_OPTIONS.find((option) => option.code === normalized)?.label ?? normalized;
}

export function languageNameForCode(language: string) {
  const normalized = language.trim().toLowerCase();
  return LANGUAGE_OPTIONS.find((option) => option.code === normalized)?.label ?? normalized.toUpperCase();
}
