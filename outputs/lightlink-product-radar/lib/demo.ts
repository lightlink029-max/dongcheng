import type { IncomingObservation } from "@/lib/radar";

export const DEMO_AS_OF = "2026-09-15T06:30:00.000Z";

export const DEMO_CLUSTERS = [
  {
    keyword: "solar parking lot light",
    groupName: "停车场照明",
    aliases: ["solar car park light", "commercial solar parking light"],
    category: "户外照明",
  },
  {
    keyword: "all in one solar street light",
    groupName: "一体化路灯",
    aliases: ["integrated solar street light", "all-in-one solar lamp"],
    category: "户外照明",
  },
  {
    keyword: "solar street light with camera",
    groupName: "安防一体灯",
    aliases: ["solar security street light", "camera solar lamp"],
    category: "安防照明",
  },
  {
    keyword: "commercial solar street light",
    groupName: "工程路灯",
    aliases: ["industrial solar street light", "project solar lighting"],
    category: "工程照明",
  },
  {
    keyword: "outdoor solar lamp",
    groupName: "户外太阳能灯",
    aliases: ["solar outdoor light", "outside solar lamp"],
    category: "户外照明",
  },
];

const signals: Record<string, { tiktok: [number, number, number, number]; instagram: [number, number, number, number]; meta: [number, number, number, number]; alibaba: [number, number, number, number] }> = {
  "solar parking lot light": {
    tiktok: [1480, 760, 126, 42],
    instagram: [630, 420, 58, 25],
    meta: [74, 41, 74, 18],
    alibaba: [1810, 1690, 180, 82],
  },
  "all in one solar street light": {
    tiktok: [2360, 2100, 184, 61],
    instagram: [1270, 1120, 93, 38],
    meta: [118, 104, 118, 31],
    alibaba: [5420, 5200, 400, 188],
  },
  "solar street light with camera": {
    tiktok: [1120, 430, 97, 36],
    instagram: [460, 190, 44, 19],
    meta: [51, 19, 51, 16],
    alibaba: [920, 810, 115, 49],
  },
  "commercial solar street light": {
    tiktok: [1750, 1260, 141, 47],
    instagram: [780, 610, 67, 29],
    meta: [103, 77, 103, 29],
    alibaba: [3190, 3000, 260, 116],
  },
  "outdoor solar lamp": {
    tiktok: [3210, 3050, 238, 70],
    instagram: [2450, 2390, 179, 65],
    meta: [132, 129, 132, 39],
    alibaba: [7980, 7760, 520, 241],
  },
};

export const DEMO_OBSERVATIONS: IncomingObservation[] = DEMO_CLUSTERS.flatMap((cluster) => {
  const signal = signals[cluster.keyword];
  const common = {
    keyword: cluster.keyword,
    groupName: cluster.groupName,
    aliases: cluster.aliases,
    category: cluster.category,
    coverageDays: 30,
    sourceKind: "demo" as const,
    geoScope: "US",
    status: "ok" as const,
    collectedAt: DEMO_AS_OF,
  };

  return [
    {
      ...common,
      platform: "TikTok",
      metric: "attention" as const,
      currentValue: signal.tiktok[0],
      previousValue: signal.tiktok[1],
      sampleN: signal.tiktok[2],
      uniqueActorN: signal.tiktok[3],
      sourceRef: "demo://tiktok-creative-center",
    },
    {
      ...common,
      platform: "Instagram",
      metric: "attention" as const,
      currentValue: signal.instagram[0],
      previousValue: signal.instagram[1],
      sampleN: signal.instagram[2],
      uniqueActorN: signal.instagram[3],
      sourceRef: "demo://instagram-sample",
    },
    {
      ...common,
      platform: "Meta Ads",
      metric: "commercial" as const,
      currentValue: signal.meta[0],
      previousValue: signal.meta[1],
      sampleN: signal.meta[2],
      uniqueActorN: signal.meta[3],
      sourceRef: "demo://meta-ad-library",
    },
    {
      ...common,
      platform: "Alibaba.com",
      metric: "competition" as const,
      currentValue: signal.alibaba[0],
      previousValue: signal.alibaba[1],
      sampleN: signal.alibaba[2],
      uniqueActorN: signal.alibaba[3],
      sourceRef: "demo://alibaba-search",
    },
  ];
});
