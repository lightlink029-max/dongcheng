"""Odoo-aligned planning choices and local storyboard generation.

The fallback catalog mirrors the canonical role, track and content-scope codes in
``product_social_content_bridge``. Live Odoo values replace these labels and
guides whenever the worker connection is available.
"""


ROLES = [
    {"code": "direct_factory", "name": "直营工厂", "description": "以真实制造、质量控制、产能和交期建立信任。", "content_focus": "厂房、产线、工艺、质检、认证、产能、定制和交付"},
    {"code": "oem_factory", "name": "OEM/ODM 制造商", "description": "以打样、研发和定制生产服务品牌客户。", "content_focus": "定制流程、研发打样、材料、包装和量产衔接"},
    {"code": "integrator", "name": "系统集成商/解决方案商", "description": "围绕客户场景组织产品并交付整体方案。", "content_focus": "场景分析、选型、组合方案、安装培训和售后"},
    {"code": "trading_company", "name": "外贸公司", "description": "以多供应商、多品类、价格和交付组织能力服务海外客户。", "content_focus": "选品、供应商管理、验货、组合采购和国际交付"},
    {"code": "sourcing_agent", "name": "采购/寻源代理", "description": "代表客户寻找、筛选和管理供应商。", "content_focus": "产品搜索、比价、验厂、验货、跟单和风险控制"},
    {"code": "brand_owner", "name": "品牌商", "description": "以品牌、设计、产品差异和用户体验经营市场。", "content_focus": "品牌故事、产品差异、使用体验、案例和渠道合作"},
    {"code": "distributor", "name": "批发商/区域分销商", "description": "以库存、区域渠道、批量供货和本地服务经营市场。", "content_focus": "现货、价格梯度、经销政策、本地交付和售后"},
    {"code": "epc", "name": "工程/EPC 服务商", "description": "负责项目设计、施工、调试与整体交付。", "content_focus": "项目设计、现场实施、进度、质量、安全和交付"},
    {"code": "dtc", "name": "跨境零售/DTC", "description": "直接面向终端消费者销售和服务。", "content_focus": "使用场景、体验、短视频、评价、促销和售后"},
]


TRACKS = [
    {"code": "medical", "name": "医疗器械与医疗用品", "description": "医疗设备、耗材及整体方案"},
    {"code": "energy_storage", "name": "储能与新能源", "description": "储能系统、能源设备和项目交付"},
    {"code": "footwear_apparel", "name": "鞋服帽", "description": "鞋服产品、供应链、定制和交付"},
    {"code": "daily_goods", "name": "日用百货", "description": "日用品、消费品、包装和供应链"},
]


SCOPES = [
    {"code": "brand_positioning", "name": "项目品牌与定位", "description": "说明服务对象、价值主张、经营边界和可信身份。"},
    {"code": "sourcing_service", "name": "采购代理服务", "description": "展示寻源、比价、供应商筛选、跟单和风险控制。"},
    {"code": "china_supply_chain", "name": "中国供应链能力", "description": "展示产业带、供应商网络、成本、交期和出口协调能力。"},
    {"code": "industry_knowledge", "name": "行业知识", "description": "帮助目标买家理解选型、采购、合规和常见风险。"},
    {"code": "supplier_quality", "name": "供应商、验厂与质检", "description": "用真实记录展示供应商评估、生产跟进和质量检查。"},
    {"code": "oem_sampling", "name": "OEM/ODM 与打样", "description": "展示设计沟通、材料、样品迭代、定制和量产衔接。"},
    {"code": "packaging_delivery", "name": "包装、验货与交付", "description": "展示包装、装箱、出货前验货、物流和交付过程。"},
    {"code": "product_category", "name": "产品或品类介绍", "description": "介绍已核实的产品、款式、参数、用途和采购价值。"},
    {"code": "customer_case", "name": "客户案例", "description": "基于可公开、可核实和已授权的案例说明过程与结果。"},
    {"code": "market_trends", "name": "市场热点", "description": "结合目标市场、渠道和季节变化解释趋势及采购机会。"},
]


SHOT_TEMPLATES = {
    "brand_positioning": (
        ("身份开场", "说明我们是谁", "办公室、厂房或团队真实环境的建立镜头", "一句话说明经营身份和服务对象", 0.18),
        ("核心能力", "说明能解决什么", "展示与经营角色相符的人员、流程、设备或供应链资源", "说明核心能力及买家价值", 0.32),
        ("证据过程", "建立可信度", "展示真实工作过程、记录、样品或交付证据", "用可核实事实支持能力", 0.30),
        ("行动引导", "引导询盘", "负责人、团队或成果画面，画面保持干净", "邀请客户发送具体需求", 0.20),
    ),
    "sourcing_service": (
        ("客户需求", "提出采购问题", "需求表、产品参考或采购沟通场景", "说明客户需要采购什么", 0.18),
        ("供应商筛选", "展示寻源过程", "供应商比较、询价、工厂资料或现场筛选", "说明筛选和比较标准", 0.32),
        ("验厂与跟单", "展示风险控制", "验厂、生产跟进、抽检或问题处理记录", "说明如何控制质量和交期风险", 0.30),
        ("交付结果", "形成闭环", "包装、装柜、物流单据或交付成果", "邀请客户提交采购清单", 0.20),
    ),
    "china_supply_chain": (
        ("产业带开场", "建立供应链场景", "产业带、市场、园区或供应商分布画面", "说明所在供应链和品类", 0.18),
        ("供应商网络", "展示资源组织", "多家真实供应商、样品或比较过程", "说明如何匹配合适供应商", 0.30),
        ("质量与协调", "说明管理能力", "生产跟进、质检、沟通和问题闭环画面", "说明质量、成本和交期协调", 0.32),
        ("出口交付", "展示最终能力", "包装、仓库、装柜或国际物流画面", "说明可提供的出口协同", 0.20),
    ),
    "industry_knowledge": (
        ("问题钩子", "提出买家问题", "与问题直接相关的产品或应用特写", "提出一个明确采购问题", 0.18),
        ("关键比较", "解释判断标准", "参数、结构、材料或两种方案对比画面", "说明关键区别和适用条件", 0.34),
        ("风险示例", "避免错误决策", "缺陷、错误用法、测试或验证过程", "说明常见风险和验证方法", 0.28),
        ("采购建议", "给出下一步", "正确方案、检查清单或专业人员画面", "给出可执行建议并引导咨询", 0.20),
    ),
    "supplier_quality": (
        ("供应商现场", "确认真实来源", "工厂外景、车间、产线或供应商现场", "说明本次检查对象和范围", 0.18),
        ("审核过程", "展示评估方法", "资质、设备、人员、流程或生产记录核对", "说明审核项目和标准", 0.30),
        ("质量检查", "提供核心证据", "测量、测试、抽检、缺陷和整改画面", "说明检查结果与处理方式", 0.34),
        ("结论记录", "形成可追溯结果", "报告、合格产品、封样或交付前确认", "说明结论边界和下一步", 0.18),
    ),
    "oem_sampling": (
        ("定制需求", "明确目标", "设计稿、规格表、参考样或沟通画面", "说明需要定制的内容", 0.18),
        ("材料与方案", "展示研发过程", "材料、颜色、结构、模具或工艺选择", "说明方案选择依据", 0.30),
        ("样品迭代", "展示执行能力", "打样、试穿/测试、修改和确认过程", "说明样品如何迭代", 0.34),
        ("量产衔接", "说明交付路径", "确认样、包装、量产准备或生产线", "说明确认后如何进入量产", 0.18),
    ),
    "packaging_delivery": (
        ("订单与备货", "交代交付对象", "订单、备货区、成品或仓库全景", "说明本次交付内容", 0.18),
        ("包装检查", "展示包装标准", "单品包装、标签、外箱、数量和防护细节", "说明包装和标识要求", 0.28),
        ("验货装柜", "展示交付证据", "出货检验、称重、装箱、托盘或装柜过程", "说明出货前检查和装载", 0.36),
        ("物流完成", "形成交付闭环", "封柜、物流单据、车辆或发运画面", "说明交付状态和后续跟踪", 0.18),
    ),
    "product_category": (
        ("产品主视觉", "快速识别产品", "干净背景下的产品全貌或系列陈列", "说明产品名称和主要用途", 0.18),
        ("关键细节", "展示差异", "材料、结构、工艺、参数或功能特写", "说明已核实的核心卖点", 0.34),
        ("应用场景", "说明采购价值", "真实使用、安装、搭配或对比画面", "说明适用客户和场景", 0.28),
        ("采购信息", "引导下一步", "规格、包装、样品或业务人员画面", "邀请客户提供规格、数量和目的地", 0.20),
    ),
    "customer_case": (
        ("客户背景", "说明问题", "经授权的客户场景、需求或项目环境", "说明客户需求，不公开敏感信息", 0.18),
        ("执行方案", "说明怎么做", "选型、打样、生产、实施或协调过程", "说明采用的解决路径", 0.32),
        ("结果证据", "证明价值", "经授权的交付、测试、反馈或现场结果", "说明可核实结果及其边界", 0.32),
        ("经验总结", "引导相似客户", "项目团队、总结清单或最终成果", "总结适用条件并邀请沟通", 0.18),
    ),
    "market_trends": (
        ("趋势现象", "吸引注意", "市场、展会、平台或品类变化的真实画面", "说明观察到的趋势及时间范围", 0.18),
        ("证据与原因", "解释趋势", "公开数据、样品变化、询盘或供应链现场", "说明数据来源和主要原因", 0.32),
        ("买家影响", "连接采购决策", "成本、交期、规格或供应变化对比", "说明趋势对买家的具体影响", 0.30),
        ("行动建议", "给出下一步", "建议清单、产品方案或团队画面", "给出有边界的采购建议", 0.20),
    ),
}


def fallback_options():
    return {
        "source": "内置 Odoo 标准模板",
        "roles": [dict(item) for item in ROLES],
        "tracks": [dict(item) for item in TRACKS],
        "scopes": [dict(item) for item in SCOPES],
        "guides": [],
    }


def _record(records, code):
    return next((item for item in records if item.get("code") == code), None)


def build_video_plan(options, role_code, track_code, scope_code, duration_seconds=30):
    role = _record(options.get("roles") or ROLES, role_code)
    track = _record(options.get("tracks") or TRACKS, track_code)
    scope = _record(options.get("scopes") or SCOPES, scope_code)
    if not role or not track or not scope:
        raise ValueError("请选择经营角色、项目赛道和内容模板")
    guide = next((item for item in options.get("guides") or [] if (
        item.get("role_code") == role_code
        and item.get("track_code") == track_code
        and item.get("scope_code") == scope_code
    )), {})
    goal = guide.get("execution_goal") or (
        f"面向{track['name']}目标客户，以{role['name']}身份制作“{scope['name']}”内容。"
    )
    copy_template = guide.get("copy_template_zh") or (
        f"开场提出买家关心的问题；以{role['name']}身份说明实际做法；"
        "用真实画面和可核实事实证明价值；最后邀请客户发送具体需求。"
    )
    evidence = guide.get("required_evidence") or scope.get("description") or "真实、可核实的业务画面"
    duration = max(12, int(duration_seconds or 30))
    shots = []
    templates = SHOT_TEMPLATES.get(scope_code, SHOT_TEMPLATES["industry_knowledge"])
    assigned = 0.0
    for index, (name, purpose, visual, narration, weight) in enumerate(templates, 1):
        shot_duration = round(duration * weight, 1)
        if index == len(templates):
            shot_duration = round(duration - assigned, 1)
        assigned += shot_duration
        shots.append({
            "slot_key": f"{scope_code}-{index:02d}",
            "sequence": index * 10,
            "name": name,
            "purpose": purpose,
            "visual_requirement": f"{visual}；重点证据：{evidence}",
            "narration": narration,
            "target_duration": shot_duration,
            "required": True,
            "state": "missing",
        })
    return {
        "role": role,
        "track": track,
        "scope": scope,
        "goal": goal,
        "copy_template": copy_template,
        "visual_requirements": evidence,
        "summary": (
            f"{role['name']}｜{track['name']}｜{scope['name']}｜约{duration}秒\n"
            f"目标：{goal}\n画面证据：{evidence}"
        ),
        "storyboard": shots,
    }
