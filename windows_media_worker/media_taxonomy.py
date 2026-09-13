"""Controlled media tags and deterministic material matching.

AI may suggest these tags later, but selection always stays explainable and
human-controlled.  The functions here deliberately avoid model dependencies so
the local library remains usable offline and stable as it grows.
"""

import re


ROLE_TAGS = (
    "直营工厂", "OEM/ODM 制造商", "外贸公司", "供应链服务商", "采购/寻源代理",
    "品牌商", "批发商/区域分销商", "系统集成商/解决方案商", "工程/EPC 服务商",
    "跨境零售/DTC",
)

SCENE_TAGS = (
    "厂房", "车间", "生产线", "仓库", "办公室", "装货", "发货", "验货",
    "装柜", "客户接待", "客户参观", "展会", "产品展示", "打样", "包装",
    "供应商走访", "物流运输",
)

USAGE_TAGS = (
    "身份开场", "问题钩子", "实力证明", "产品展示", "生产过程", "质量控制",
    "供应链说明", "交付证明", "客户案例", "行业知识", "行动引导", "过渡画面",
)


def normalize_tags(value):
    """Return stable, unique labels from a list or comma-separated text."""
    if value is None:
        values = []
    elif isinstance(value, str):
        values = re.split(r"[,，;；\n]+", value)
    else:
        values = value
    result = []
    seen = set()
    for item in values:
        label = str(item or "").strip()
        key = label.casefold()
        if not label or key in seen:
            continue
        seen.add(key)
        result.append(label)
    return result


def format_tags(record):
    values = []
    for key in ("role_tags", "scene_tags", "usage_tags", "custom_tags"):
        values.extend(normalize_tags(record.get(key)))
    return "、".join(normalize_tags(values)) or "未打标签"


def infer_controlled_tags(text, choices):
    normalized = str(text or "").casefold()
    return [label for label in choices if label.casefold() in normalized]


def filter_media(records, role="", scene="", usage="", keyword=""):
    """Apply explicit user filters. Empty filters never hide records."""
    role, scene, usage = (str(value or "").strip() for value in (role, scene, usage))
    keyword = str(keyword or "").strip().casefold()
    result = []
    for record in records:
        if role and role not in normalize_tags(record.get("role_tags")):
            continue
        if scene and scene not in normalize_tags(record.get("scene_tags")):
            continue
        if usage and usage not in normalize_tags(record.get("usage_tags")):
            continue
        searchable = " ".join((
            str(record.get("name") or record.get("clip_name") or ""),
            str(record.get("caption") or ""),
            str(record.get("shot_purpose") or ""),
            format_tags(record),
        )).casefold()
        if keyword and keyword not in searchable:
            continue
        result.append(record)
    return result


def asset_match(asset, slot=None, task=None):
    """Score one shot asset against a plan slot and explain the result."""
    slot, task = slot or {}, task or {}
    role = task.get("business_role") or {}
    role_targets = normalize_tags([role.get("name"), role.get("code")])
    scene_targets = infer_controlled_tags(
        "%s %s" % (slot.get("visual_requirement") or "", slot.get("name") or ""),
        SCENE_TAGS,
    )
    usage_targets = infer_controlled_tags(
        "%s %s" % (slot.get("name") or "", slot.get("purpose") or ""),
        USAGE_TAGS,
    )
    asset_roles = normalize_tags(asset.get("role_tags"))
    asset_scenes = normalize_tags(asset.get("scene_tags"))
    asset_usages = normalize_tags(asset.get("usage_tags"))
    if not asset_roles:
        asset_roles = normalize_tags([asset.get("role_name"), asset.get("role_code")])
    if not asset_usages:
        asset_usages = normalize_tags([asset.get("shot_purpose")])
    score, matched, expected = 0, [], 0
    if role_targets:
        expected += 30
        if set(role_targets) & set(asset_roles):
            score += 30
            matched.append("经营角色")
    if scene_targets:
        expected += 40
        hits = set(scene_targets) & set(asset_scenes)
        if hits:
            score += 40
            matched.append("场景:" + "/".join(sorted(hits)))
    if usage_targets:
        expected += 30
        hits = set(usage_targets) & set(asset_usages)
        if hits:
            score += 30
            matched.append("用途:" + "/".join(sorted(hits)))
    if not expected:
        return {"score": 0, "level": "待人工判断", "reasons": []}
    if score == expected:
        level = "完全匹配"
    elif score:
        level = "部分匹配"
    else:
        level = "未匹配"
    return {"score": score, "level": level, "reasons": matched}


def rank_assets(records, slot=None, task=None, mode="recommended"):
    ranked = [(asset_match(item, slot, task), item) for item in records]
    if mode == "exact":
        ranked = [item for item in ranked if item[0]["level"] == "完全匹配"]
    ranked.sort(key=lambda item: (-item[0]["score"], str(item[1].get("name") or "").casefold()))
    return ranked
