from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


FOOTWEAR_SOURCING_READINESS_TEMPLATE = (
    ("strategy_positioning", 10, "strategy", "确认英文定位与服务边界", 4, True, "joint", 0,
     "确认 China Footwear Sourcing & Supply Chain Partner 定位、服务范围和不宣称自有工厂的边界。"),
    ("strategy_icp", 20, "strategy", "定义进口商、批发商与 Private Label 客户画像", 3, False, "ai", 0,
     "形成目标客户规模、采购角色、需求信号、排除条件和优先级规则。"),
    ("strategy_market_kpi", 30, "strategy", "确认美国与英国首发市场及指标", 3, False, "joint", 1,
     "首期使用英文内容覆盖美国和英国，并确定流量、询盘、报价、订单和净毛利指标。"),
    ("product_shortlist", 40, "product", "建立首批 5 个鞋款候选池", 5, False, "joint", 2,
     "录入真实鞋款或候选产品，不使用虚构产品作为正式发布依据。"),
    ("product_specs", 50, "product", "核实材质、尺码、颜色与包装资料", 6, True, "user", 3,
     "为每个首发鞋款补齐并核实材质、尺码范围、颜色、包装与图片证据。"),
    ("product_supplier_terms", 60, "product", "核实供应商报价、MOQ、产能与交期", 5, True, "user", 4,
     "使用供应商真实资料填写采购价、MOQ、打样周期、量产交期和产能。"),
    ("product_margin", 70, "product", "核算目标售价、样品成本与毛利", 5, True, "ai", 5,
     "基于已核实成本和物流条件计算报价区间、样品成本及目标毛利。"),
    ("product_approval", 80, "product", "完成市场适配评分并批准首发产品", 4, True, "joint", 6,
     "完成需求、价格、MOQ、质量与视觉素材评分，只批准通过硬门槛的产品。"),
    ("compliance_ip", 90, "compliance", "核实商标、图片和款式知识产权", 5, True, "user", 4,
     "确认商标授权、图片使用权和款式风险；未授权品牌或素材不得发布。"),
    ("compliance_us", 100, "compliance", "完成美国鞋类标签与合规清单", 5, True, "joint", 5,
     "按首发产品实际材料和用途核对美国标签、进口与宣传要求并保存依据。"),
    ("compliance_uk", 110, "compliance", "完成英国鞋类标签与合规清单", 5, True, "joint", 5,
     "按首发产品实际材料和用途核对英国标签、进口与宣传要求并保存依据。"),
    ("compliance_claims", 120, "compliance", "复核全部英文声明与证据", 5, True, "ai", 7,
     "价格、认证、环保、性能、产能、交期和案例声明必须与 Odoo 中的证据一致。"),
    ("commercial_rfq", 130, "commercial", "完成英文 RFQ 与报价模板", 5, True, "ai", 6,
     "模板包含 MOQ、价格有效期、Incoterms、付款条件、打样和量产交期。"),
    ("commercial_sample", 140, "commercial", "建立样品申请与跟进流程", 4, False, "ai", 7,
     "明确样品费用、寄送、反馈、改样和转订单的状态及响应时限。"),
    ("commercial_qc", 150, "commercial", "建立验货、质量与索赔规则", 3, True, "joint", 8,
     "明确产前、生产中、出货前检查和不合格处理规则。"),
    ("commercial_shipping", 160, "commercial", "补齐包装、装箱、HS 与运输资料", 3, True, "user", 8,
     "使用真实包装尺寸、重量、装箱量、HS 建议和物流条件。"),
    ("content_message", 170, "content", "完成英文价值主张与网站落地页结构", 4, False, "ai", 8,
     "围绕供应商筛选、验厂、质量控制、成本、交期和出口协调组织英文信息。"),
    ("content_assets", 180, "content", "准备首发产品图片、视频与事实表", 4, True, "user", 9,
     "素材必须真实、可授权，并能支持页面和社媒中的产品事实。"),
    ("content_linkedin", 190, "content", "完成 LinkedIn 首发内容包", 3, False, "ai", 10,
     "准备 4 条英文 B2B 内容，覆盖采购知识、供应商管理、质量控制和产品机会。"),
    ("content_instagram", 200, "content", "完成 Instagram 首发内容包", 3, False, "ai", 10,
     "准备 6 条英文图片或短视频内容，使用真实产品与供应链素材。"),
    ("content_cta", 210, "content", "完成询盘 CTA、表单与隐私说明", 1, True, "joint", 10,
     "网站和社媒统一指向可追踪的询盘入口，并提供必要的隐私说明。"),
    ("channel_website", 220, "channel", "配置英文网站与数据追踪", 4, True, "joint", 11,
     "完成网站发布目标、表单测试、分析工具和来源追踪。"),
    ("channel_linkedin", 230, "channel", "配置 LinkedIn 真实账号授权", 2, True, "user", 11,
     "由本人完成真实账号登录授权；密码和 Cookie 不录入 Odoo。"),
    ("channel_instagram", 240, "channel", "配置 Instagram 真实账号授权", 2, True, "user", 11,
     "由本人完成真实账号登录授权；密码和 Cookie 不录入 Odoo。"),
    ("channel_attribution", 250, "channel", "配置 UTM、来源归因与驾驶舱", 2, True, "ai", 12,
     "网站、LinkedIn、Instagram 的流量、询盘、报价和订单可回溯到渠道与内容。"),
    ("crm_stages", 260, "operations", "配置 ICP、CRM 阶段与响应时限", 2, False, "ai", 12,
     "覆盖新询盘、需求确认、报价、样品、谈判、赢单和流失原因。"),
    ("operations_rehearsal", 270, "operations", "完成询盘到订单的全流程演练", 2, True, "joint", 13,
     "用明确测试标识的数据验证询盘、报价、样品、采购、库存、交付和收款链路。"),
    ("operations_review", 280, "operations", "建立每周数据复盘与优化节奏", 1, False, "ai", 13,
     "每周基于渠道、产品、客户和净毛利数据生成保留、迭代或停止建议。"),
)

CONTENT_SCOPE_CODES = (
    "brand_positioning", "sourcing_service", "china_supply_chain", "industry_knowledge",
    "supplier_quality", "oem_sampling", "packaging_delivery", "product_category",
    "customer_case", "market_trends",
)

TRACK_CONTENT_WEIGHTS = {
    "medical": (10, 8, 10, 15, 18, 8, 8, 12, 7, 4),
    "energy_storage": (8, 5, 10, 15, 20, 8, 7, 12, 10, 5),
    "footwear_apparel": (8, 15, 15, 10, 15, 12, 10, 10, 3, 2),
    "daily_goods": (8, 12, 12, 10, 12, 12, 12, 15, 4, 3),
}

ROLE_CONTENT_MULTIPLIERS = {
    "direct_factory": (1.0, 0.4, 1.2, 0.8, 1.4, 1.3, 1.0, 1.2, 1.0, 0.7),
    "oem_factory": (0.9, 0.5, 1.0, 0.8, 1.2, 1.8, 1.2, 1.1, 1.0, 0.6),
    "integrator": (0.9, 0.8, 1.1, 1.4, 1.0, 0.6, 1.1, 0.8, 1.8, 0.8),
    "trading_company": (0.8, 1.4, 1.3, 1.0, 1.3, 0.8, 1.3, 1.2, 0.8, 1.0),
    "sourcing_agent": (0.8, 1.7, 1.5, 1.2, 1.6, 0.9, 1.3, 0.7, 0.8, 0.8),
    "brand_owner": (1.6, 0.5, 0.8, 1.0, 0.9, 1.3, 1.1, 1.5, 1.4, 1.2),
    "distributor": (1.0, 0.9, 1.0, 1.0, 1.0, 0.5, 1.4, 1.4, 1.2, 1.1),
    "epc": (0.8, 0.6, 1.0, 1.2, 1.3, 0.5, 1.5, 0.8, 2.0, 0.6),
    "dtc": (1.5, 0.3, 0.5, 0.9, 0.8, 0.6, 1.0, 1.8, 1.5, 1.5),
}

ROLE_VIDEO_MULTIPLIERS = {
    "direct_factory": 1.05, "oem_factory": 1.05, "integrator": 0.95,
    "trading_company": 0.95, "sourcing_agent": 1.0, "brand_owner": 1.1,
    "distributor": 1.0, "epc": 1.0, "dtc": 1.15,
}

TRACK_VIDEO_MULTIPLIERS = {
    "medical": 0.9, "energy_storage": 1.0,
    "footwear_apparel": 1.1, "daily_goods": 1.1,
}

TRACK_COPY_CONTEXT = {
    "medical": {
        "industry": "medical devices and medical supplies",
        "buyers": "hospitals, clinics, medical distributors and institutional procurement teams",
        "proof": "intended use, model/specification, applicable certification, registration status, training, warranty and delivery evidence",
    },
    "energy_storage": {
        "industry": "energy-storage and renewable-energy systems",
        "buyers": "installers, EPC contractors, energy distributors, project developers and commercial buyers",
        "proof": "capacity, power, voltage, cell and BMS configuration, safety/transport certification, compatibility, warranty and project conditions",
    },
    "footwear_apparel": {
        "industry": "footwear, apparel and accessories",
        "buyers": "importers, wholesalers, private-label brands, retailers and e-commerce buyers",
        "proof": "material, size range, colour, MOQ, sampling status, unit-price basis, production lead time, packaging, inspection and IP authorization",
    },
    "daily_goods": {
        "industry": "household and daily-use consumer goods",
        "buyers": "importers, wholesalers, supermarket chains, retailers and e-commerce sellers",
        "proof": "material, dimensions, intended use, set configuration, MOQ, packaging, carton data, testing/label requirements and delivery terms",
    },
}

ROLE_COPY_CONTEXT = {
    "direct_factory": (
        "the verified manufacturer",
        "show the real facility, process, quality controls, capacity and delivery capability",
        "Send your specification and target quantity for a manufacturability review",
    ),
    "oem_factory": (
        "an OEM/ODM manufacturing partner",
        "show how a buyer brief becomes a sample, approved specification and repeatable production order",
        "Share your reference, specification and launch date to start a sampling review",
    ),
    "integrator": (
        "a solution and system-integration partner",
        "connect buyer requirements to product selection, system design, implementation and after-sales support",
        "Send the application scenario and constraints for an initial solution review",
    ),
    "trading_company": (
        "a multi-supplier export and trading partner",
        "show product selection, supplier coordination, consolidated quality control and international delivery",
        "Send your product list, quantities and destination for a coordinated quotation",
    ),
    "sourcing_agent": (
        "a China sourcing and supplier-management partner",
        "show supplier search, comparison, factory verification, inspection, follow-up and risk control without claiming partner factories as owned",
        "Send your product brief, target price, quantity and delivery date for a sourcing assessment",
    ),
    "brand_owner": (
        "the product brand owner",
        "show the brand promise, differentiated product experience and channel value",
        "Contact us for product details, wholesale terms or channel cooperation",
    ),
    "distributor": (
        "a wholesale and regional distribution partner",
        "show assortment, volume tiers, stock or replenishment capability, local delivery and service",
        "Send your territory, channel and expected volume for wholesale terms",
    ),
    "epc": (
        "an engineering and EPC delivery partner",
        "show design assumptions, site execution, schedule, safety, commissioning and accountable delivery",
        "Share the site conditions, scope and target schedule for a project review",
    ),
    "dtc": (
        "the customer-facing product team",
        "translate product facts into clear use cases, experience, proof and after-sales confidence",
        "View the verified product details or contact support before ordering",
    ),
}

ROLE_CTA_ZH = {
    "direct_factory": "请发送产品规格和目标数量，我们先评估生产可行性",
    "oem_factory": "请发送参考样、规格和上市时间，我们先评估打样方案",
    "integrator": "请发送应用场景和限制条件，我们先进行方案初审",
    "trading_company": "请发送产品清单、数量和目的地，我们组织统一报价",
    "sourcing_agent": "请发送产品需求、目标价格、数量和交期，我们先做寻源评估",
    "brand_owner": "请联系我们获取产品资料、批发条件或渠道合作方案",
    "distributor": "请发送销售区域、渠道和预计数量，我们提供批发合作条件",
    "epc": "请发送现场条件、项目范围和计划时间，我们先做项目评估",
    "dtc": "请先查看已核实的产品资料，订购前如有问题请联系客户支持",
}

CONTENT_EXECUTION_GOALS = {
    "brand_positioning": "讲清服务谁、解决什么采购问题、承担什么角色，以及不承担什么；让客户在 10 秒内理解项目定位。",
    "sourcing_service": "把寻源、筛选、比价、验厂、跟单和验货拆成透明步骤，说明客户每一步能得到的结果。",
    "china_supply_chain": "用产业带、供应商网络、交期和协同实例说明中国供应链能力，不用空泛的资源宣传。",
    "industry_knowledge": "围绕买家真实决策问题做一条可收藏的选型、采购、合规或风险清单。",
    "supplier_quality": "展示供应商准入、验厂、生产检查或出货前验货的真实过程、判定标准和整改结果。",
    "oem_sampling": "解释从需求、设计和材料确认到样品迭代及量产封样的完整路径。",
    "packaging_delivery": "用真实包装、装箱、验货和运输信息说明如何降低破损、延误和到货差异。",
    "product_category": "只基于已核实产品资料，说明适用买家、规格、采购价值和限制，并引导索取报价或样品。",
    "customer_case": "在获得授权且事实可核实的前提下，用问题—行动—结果结构复盘客户案例；无授权时不得发布。",
    "market_trends": "把市场、季节或渠道变化转成买家可执行的选品和采购建议，并标明数据时间与来源。",
}

CONTENT_EVIDENCE_GUIDES = {
    "brand_positioning": "目标客户、服务范围、团队真实能力、合作边界和统一询盘入口",
    "sourcing_service": "客户需求表、候选供应商比较、报价条件、检查节点和交付记录",
    "china_supply_chain": "可核实产业带、合作供应商、MOQ、产能、交期和出口协调记录",
    "industry_knowledge": "可追溯标准、法规、规格、采购数据或内部验证记录，并注明适用范围和日期",
    "supplier_quality": "供应商授权、验厂清单、质检照片/视频、抽检标准、不合格项和整改证据",
    "oem_sampling": "客户需求、材料/颜色/尺寸确认、样品版本、修改记录、封样和量产条件",
    "packaging_delivery": "包装规格、装箱数据、验货结果、运输节点、交付文件和异常处理记录",
    "product_category": "真实产品、规格、材质、MOQ、价格基础、交期、包装、测试和图片授权",
    "customer_case": "客户书面授权、脱敏要求、问题背景、过程记录、可量化结果和结果口径",
    "market_trends": "来源链接、发布日期、目标市场、样本口径、趋势期限和对应采购建议",
}

CONTENT_COPY_TEMPLATES = {
    "brand_positioning": """Headline: We help [buyer segment] source {industry} from China with [verified outcome].
Problem: [Describe one costly sourcing or delivery problem in the buyer's words].
Our role: We work as {role_identity}. We {role_value}.
How it works: 1) [requirement check] 2) [execution step] 3) [quality/delivery control].
Proof: [Insert 2-3 verified facts from Odoo; remove this line if evidence is unavailable].
Boundary: State clearly what is handled directly and what is delivered by verified partner factories.
CTA: {cta}.""",
    "sourcing_service": """Hook: Need a reliable source for [specific {industry} requirement] without losing visibility?
Buyer brief: [specification] / [quantity] / [target price] / [delivery date].
Our workflow as {role_identity}: requirement validation → supplier shortlist → comparable quotations → verification → sample/order follow-up → inspection and delivery coordination.
Decision output: [what the buyer receives at each stage].
Proof: [Insert a verified comparison, timeline, inspection record or delivery milestone].
CTA: {cta}.""",
    "china_supply_chain": """Headline: What China's {industry} supply chain can realistically deliver for [buyer segment].
Buyer need: [product/specification/volume/timeline].
Supply-chain map: [relevant production cluster] → [supplier type] → [key process] → [quality gate] → [export hand-off].
Trade-off: [Explain the verified MOQ, cost, speed or customization trade-off].
Our role: As {role_identity}, we {role_value}.
CTA: {cta}.""",
    "industry_knowledge": """Title: [Number] checks before buying [specific product/category] for [market or use case].
1. [Selection criterion] — why it matters: [buyer impact].
2. [Specification/compliance criterion] — verify: [document or test].
3. [Commercial criterion] — compare: [MOQ, price basis, lead time or warranty].
Common mistake: [one evidence-backed risk and how to avoid it].
Buyer checklist: [3 questions to send suppliers].
CTA: Save this checklist, then {cta_lower}.""",
    "supplier_quality": """Hook: A supplier quote is not the same as a verified supply option.
Scope: [factory audit / pre-production check / during-production inspection / pre-shipment inspection] for [product].
We checked: [criterion 1], [criterion 2], [criterion 3].
Finding: [verified pass/fail/observation; never invent a result].
Action: [corrective action, recheck or buyer decision].
Role clarity: We act as {role_identity}; identify partner factories accurately.
CTA: {cta}.""",
    "oem_sampling": """Title: From [buyer idea/reference] to an approved {industry} sample.
Step 1 — brief: [use, target buyer, specification, quantity and launch date].
Step 2 — development: [material/component/colour/branding decisions].
Step 3 — sample review: [fit/function/appearance/test criteria].
Step 4 — revision and approval: [version change and sign-off evidence].
Step 5 — production hand-off: [sealed sample, specification and quality checkpoints].
CTA: {cta}.""",
    "packaging_delivery": """Hook: Good products still fail when packaging and delivery details are left too late.
Order: [product] / [quantity] / [destination] / [required date].
Packaging plan: [unit pack], [inner/carton], [dimensions/weight], [label and barcode].
Pre-shipment check: [quantity, appearance, function and carton checks].
Delivery control: [Incoterm], [documents], [handover milestone] and [exception plan].
Verified result: [real inspection or delivery status].
CTA: {cta}.""",
    "product_category": """Headline: [Verified product/category] for [buyer segment and use case].
Buyer value: [specific commercial or operational benefit supported by facts].
Verified specification: [material/model/size/capacity] | MOQ: [value] | Lead time: [value] | Packaging: [value].
Customization: [available verified options].
Best fit: [buyer/use case]. Not suitable for: [known limitation].
Proof: [approved product images, test documents or sample status].
CTA: Request the verified specification sheet, sample terms or quotation.""",
    "customer_case": """Title: How [authorized customer type, anonymized if required] solved [specific problem].
Starting point: [verified requirement, constraint and target].
Our role as {role_identity}: [actions actually completed].
Solution: [selection, supplier, customization, quality and delivery steps].
Result: [authorized measurable result with period and calculation basis].
What we learned: [one reusable buyer insight].
Authorization note: [record approval scope; do not publish without it].
CTA: {cta}.""",
    "market_trends": """Headline: What [dated market/channel trend] means for {industry} buyers in [target market].
Signal: [verified data point] from [source and date].
Interpretation: [what changed and what did not].
Buyer impact: [effect on assortment, specification, MOQ, price, inventory or lead time].
Recommended action: [one action now], [one item to validate], [one trigger to monitor].
Limit: State the geography, period and sample limitations.
CTA: {cta}.""",
}

CONTENT_COPY_TEMPLATES_ZH = {
    "brand_positioning": """标题：我们帮助[买家类型]从中国采购{industry_zh}，实现[已核实的结果]。
客户问题：[用买家的语言描述一个代价较高的采购或交付问题]。
我们的角色：我们以“{role_identity_zh}”身份开展工作，重点体现：{role_value_zh}。
工作方式：1）[需求确认] 2）[执行步骤] 3）[质量/交付控制]。
事实依据：[填写 Odoo 中 2—3 项已核实事实；没有依据时删除此项]。
身份边界：明确哪些工作由我们直接完成，哪些由已核实的合作工厂完成。
行动引导：{cta_zh}。""",
    "sourcing_service": """开头：需要为[具体{industry_zh}需求]找到可靠供应商，同时保持过程透明吗？
买家需求：[规格] / [数量] / [目标价格] / [交付日期]。
我们的流程：以“{role_identity_zh}”身份，依次完成需求确认 → 供应商初选 → 可比报价 → 供应商核实 → 样品/订单跟进 → 验货与交付协调。
阶段交付：[说明客户在每一步能获得的文件、结论或选择]。
事实依据：[填写已核实的供应商比较、时间节点、验货记录或交付里程碑]。
行动引导：{cta_zh}。""",
    "china_supply_chain": """标题：中国{industry_zh}供应链能够为[买家类型]实际提供什么？
买家需求：[产品/规格/数量/时间]。
供应链路径：[相关产业带] → [供应商类型] → [关键工序] → [质量门槛] → [出口交接]。
取舍说明：[基于真实数据解释 MOQ、成本、速度或定制范围之间的取舍]。
我们的角色：以“{role_identity_zh}”身份，重点体现：{role_value_zh}。
行动引导：{cta_zh}。""",
    "industry_knowledge": """标题：为[目标市场/使用场景]采购[具体产品/品类]前必须检查的[数字]项内容。
1．[选型标准]——为什么重要：[对买家的影响]。
2．[规格/合规标准]——需要核实：[文件或测试]。
3．[商务标准]——需要比较：[MOQ、价格基础、交期或质保]。
常见错误：[一个有事实依据的风险，以及避免方法]。
买家清单：[询问供应商的 3 个具体问题]。
行动引导：收藏这份清单，然后{cta_zh}。""",
    "supplier_quality": """开头：收到供应商报价，不等于已经获得可靠的供应方案。
本次范围：[验厂 / 产前检查 / 生产中检查 / 出货前验货]，对象为[产品]。
检查项目：[标准 1]、[标准 2]、[标准 3]。
检查发现：[只填写已核实的通过/不通过/观察结果，不得虚构]。
后续处理：[整改、复检或买家决策]。
身份说明：我们以“{role_identity_zh}”身份工作，必须准确说明合作工厂关系。
行动引导：{cta_zh}。""",
    "oem_sampling": """标题：从[买家想法/参考样]到获得批准的{industry_zh}样品。
第 1 步—需求：确认[用途、目标客户、规格、数量和上市时间]。
第 2 步—开发：确认[材料/部件/颜色/品牌标识]。
第 3 步—样品评审：检查[尺寸或适配、功能、外观和测试标准]。
第 4 步—修改与批准：记录[版本变化和确认依据]。
第 5 步—量产交接：固定[封样、规格和质量检查点]。
行动引导：{cta_zh}。""",
    "packaging_delivery": """开头：产品本身合格，如果包装和交付细节处理太晚，订单仍可能失败。
订单信息：[产品] / [数量] / [目的地] / [要求到货时间]。
包装方案：[单品包装]、[内盒/外箱]、[尺寸/重量]、[标签和条码]。
出货前检查：[数量、外观、功能和外箱检查]。
交付控制：[贸易条款]、[单据]、[交接节点]和[异常预案]。
已核实结果：[真实验货或交付状态]。
行动引导：{cta_zh}。""",
    "product_category": """标题：[已核实产品/品类]，适合[买家类型和使用场景]。
采购价值：[有事实支持的具体商业或使用价值]。
已核实规格：[材料/型号/尺码/容量]｜MOQ：[数值]｜交期：[数值]｜包装：[数值]。
定制范围：[已经核实可提供的选项]。
适合：[买家/场景]；不适合：[已知限制]。
事实依据：[已批准产品图片、测试文件或样品状态]。
行动引导：索取已核实的规格表、样品条件或报价。""",
    "customer_case": """标题：[已授权的客户类型；必要时匿名]如何解决[具体问题]。
初始情况：[已核实的需求、限制条件和目标]。
我们的角色：以“{role_identity_zh}”身份，实际完成了[具体行动]。
解决过程：[选型、供应商、定制、质量和交付步骤]。
结果：[已授权的量化结果，并说明周期和计算口径]。
经验总结：[一个其他买家可以复用的结论]。
授权说明：[记录客户允许公开的范围；未授权不得发布]。
行动引导：{cta_zh}。""",
    "market_trends": """标题：[注明日期的市场/渠道趋势]对[目标市场]的{industry_zh}买家意味着什么？
趋势信号：[已核实的数据]，来源：[来源和日期]。
趋势解释：[哪些发生了变化，哪些没有变化]。
买家影响：[对选品、规格、MOQ、价格、库存或交期的影响]。
建议行动：[现在做一项行动]、[核实一个问题]、[持续观察一个触发指标]。
适用边界：注明地区、时间范围和样本限制。
行动引导：{cta_zh}。""",
}


class BusinessCapability(models.Model):
    _name = "psc.business.capability"
    _description = "经营能力标签"
    _order = "sequence, name"

    name = fields.Char(string="能力名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string="能力说明", translate=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "经营能力代码不能重复。")


class BusinessRole(models.Model):
    _name = "psc.business.role"
    _description = "主要经营角色"
    _order = "sequence, name"

    name = fields.Char(string="角色名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string="角色说明", translate=True)
    content_focus = fields.Text(string="默认内容重点", translate=True)
    capability_ids = fields.Many2many(
        "psc.business.capability", "psc_role_capability_rel", "role_id", "capability_id",
        string="默认能力",
    )
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "经营角色代码不能重复。")


class IndustryTrack(models.Model):
    _name = "psc.industry.track"
    _description = "经营赛道模板"
    _order = "sequence, name"

    name = fields.Char(string="赛道名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string="赛道说明", translate=True)
    role_ids = fields.Many2many(
        "psc.business.role", "psc_track_role_rel", "track_id", "role_id",
        string="适用经营角色",
    )
    default_customer_profile = fields.Text(string="默认客户画像", translate=True)
    compliance_notes = fields.Text(string="合规与硬性门槛", translate=True)
    customer_requirement_template = fields.Text(string="客户需求采集模板", translate=True)
    default_kpis = fields.Text(string="默认经营指标", translate=True)
    product_attribute_ids = fields.One2many(
        "psc.track.product.attribute", "track_id", string="产品属性模板",
    )
    scoring_rule_ids = fields.One2many(
        "psc.track.scoring.rule", "track_id", string="产品评分规则",
    )
    content_pillar_ids = fields.One2many(
        "psc.content.pillar", "track_id", string="内容栏目",
    )
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "经营赛道代码不能重复。")


class TrackProductAttribute(models.Model):
    _name = "psc.track.product.attribute"
    _description = "赛道产品属性模板"
    _order = "track_id, sequence, id"

    track_id = fields.Many2one(
        "psc.industry.track", string="经营赛道", required=True, ondelete="cascade", index=True,
    )
    name = fields.Char(string="属性名称", required=True, translate=True)
    code = fields.Char(string="属性代码", required=True)
    value_type = fields.Selection([
        ("text", "文本"), ("number", "数值"), ("boolean", "是/否"),
        ("selection", "选项"), ("date", "日期"),
    ], string="值类型", required=True, default="text")
    unit = fields.Char(string="单位")
    selection_values = fields.Text(string="可选值", help="每行一个可选值。")
    required_for_publish = fields.Boolean(string="发布前必填")
    hard_gate = fields.Boolean(string="硬性门槛")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _track_code_unique = models.Constraint(
        "UNIQUE(track_id, code)", "同一赛道的产品属性代码不能重复。",
    )


class TrackScoringRule(models.Model):
    _name = "psc.track.scoring.rule"
    _description = "赛道产品评分规则"
    _order = "track_id, sequence, id"

    track_id = fields.Many2one(
        "psc.industry.track", string="经营赛道", required=True, ondelete="cascade", index=True,
    )
    name = fields.Char(string="评分维度", required=True, translate=True)
    code = fields.Char(string="代码", required=True)
    weight = fields.Float(string="权重 %", required=True, default=10.0)
    hard_gate = fields.Boolean(string="硬性门槛")
    criteria = fields.Text(string="评分及通过标准", translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _track_code_unique = models.Constraint(
        "UNIQUE(track_id, code)", "同一赛道的评分规则代码不能重复。",
    )

    @api.constrains("weight")
    def _check_weight(self):
        for rule in self:
            if not 0.0 <= rule.weight <= 100.0:
                raise ValidationError(_("评分权重必须在 0 到 100 之间。"))


class ContentPillar(models.Model):
    _name = "psc.content.pillar"
    _description = "赛道内容栏目"
    _order = "track_id, sequence, id"

    name = fields.Char(string="栏目名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True)
    track_id = fields.Many2one(
        "psc.industry.track", string="经营赛道", required=True, ondelete="cascade", index=True,
    )
    role_ids = fields.Many2many(
        "psc.business.role", "psc_pillar_role_rel", "pillar_id", "role_id",
        string="适用角色",
    )
    objective = fields.Char(string="栏目目标", translate=True)
    default_ratio = fields.Float(string="建议占比 %", default=10.0)
    instructions = fields.Text(string="生成规则", translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _track_code_unique = models.Constraint(
        "UNIQUE(track_id, code)", "同一赛道的内容栏目代码不能重复。",
    )

    @api.constrains("default_ratio")
    def _check_ratio(self):
        for pillar in self:
            if not 0.0 <= pillar.default_ratio <= 100.0:
                raise ValidationError(_("内容栏目占比必须在 0 到 100 之间。"))


class ContentScope(models.Model):
    _name = "psc.content.scope"
    _description = "社媒内容类型"
    _order = "sequence, name"

    name = fields.Char(string="内容类型", required=True, translate=True)
    code = fields.Char(string="代码", required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string="定义与使用场景", translate=True)
    default_video_ratio = fields.Float(string="默认视频占比 %", default=60.0)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "内容类型代码不能重复。")

    @api.constrains("default_video_ratio")
    def _check_default_video_ratio(self):
        for record in self:
            if not 0 <= record.default_video_ratio <= 100:
                raise ValidationError(_("默认视频占比必须在 0 到 100 之间。"))


class MediaTag(models.Model):
    _name = "psc.media.tag"
    _description = "社媒素材标签"
    _order = "name"

    name = fields.Char(string="标签", required=True)
    color = fields.Integer(string="颜色")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "素材标签不能重复。")


class ContentMixRule(models.Model):
    _name = "psc.content.mix.rule"
    _description = "赛道与角色内容比例"
    _order = "track_id, role_id, sequence, id"

    track_id = fields.Many2one(
        "psc.industry.track", string="经营赛道", required=True, ondelete="cascade", index=True,
    )
    role_id = fields.Many2one(
        "psc.business.role", string="主要经营角色", required=True, ondelete="cascade", index=True,
    )
    scope_id = fields.Many2one(
        "psc.content.scope", string="内容类型", required=True, ondelete="cascade", index=True,
    )
    sequence = fields.Integer(related="scope_id.sequence", store=True, readonly=True)
    content_ratio = fields.Float(string="建议内容占比 %", required=True)
    video_ratio = fields.Float(string="其中视频占比 %", required=True)
    execution_goal = fields.Char(string="具体要做什么", translate=True)
    copy_template_zh = fields.Text(string="中文文案模板")
    copy_template = fields.Text(string="英文文案模板", translate=True)
    required_evidence = fields.Text(string="发布前准备", translate=True)
    notes = fields.Text(string="运营说明", translate=True)
    active = fields.Boolean(default=True)

    _profile_scope_unique = models.Constraint(
        "UNIQUE(track_id, role_id, scope_id)", "同一赛道和角色的内容类型不能重复。",
    )

    @api.constrains("content_ratio", "video_ratio")
    def _check_ratios(self):
        for record in self:
            if not 0 <= record.content_ratio <= 100 or not 0 <= record.video_ratio <= 100:
                raise ValidationError(_("内容占比和视频占比必须在 0 到 100 之间。"))

    @api.model
    def _default_guide_values(self, track, role, scope):
        track_context = TRACK_COPY_CONTEXT.get(track.code, {
            "industry": track.name,
            "buyers": track.default_customer_profile or _("目标买家"),
            "proof": track.customer_requirement_template or track.compliance_notes or _("已核实业务事实"),
        })
        role_identity, role_value, cta = ROLE_COPY_CONTEXT.get(role.code, (
            role.name,
            role.content_focus or role.description or _("explain the verified value delivered to the buyer"),
            _("Send your requirements for an initial review"),
        ))
        execution = CONTENT_EXECUTION_GOALS.get(scope.code, scope.description or scope.name)
        evidence = CONTENT_EVIDENCE_GUIDES.get(scope.code, track_context["proof"])
        if track.compliance_notes:
            evidence = _("%(evidence)s；赛道合规边界：%(compliance)s", evidence=evidence,
                         compliance=track.compliance_notes)
        template = CONTENT_COPY_TEMPLATES.get(scope.code, CONTENT_COPY_TEMPLATES["industry_knowledge"])
        template_zh = CONTENT_COPY_TEMPLATES_ZH.get(
            scope.code, CONTENT_COPY_TEMPLATES_ZH["industry_knowledge"],
        )
        return {
            "execution_goal": _(
                "面向“%(track)s”的目标客户，以“%(role)s”身份：%(execution)s",
                track=track.name, role=role.name, execution=execution,
            ),
            "copy_template_zh": template_zh.format(
                industry_zh=track.name,
                buyers_zh=track.default_customer_profile or _("目标买家"),
                role_identity_zh=role.name,
                role_value_zh=role.content_focus or role.description or _("说明可核实的客户价值"),
                cta_zh=ROLE_CTA_ZH.get(role.code, _("请发送具体需求，我们先进行初步评估")),
            ),
            "copy_template": template.format(
                industry=track_context["industry"],
                buyers=track_context["buyers"],
                proof=track_context["proof"],
                role_identity=role_identity,
                role_value=role_value,
                cta=cta,
                cta_lower=cta[:1].lower() + cta[1:],
            ),
            "required_evidence": evidence,
        }

    @api.onchange("track_id", "role_id", "scope_id")
    def _onchange_content_guide(self):
        for record in self:
            if not (record.track_id and record.role_id and record.scope_id):
                continue
            defaults = record._default_guide_values(record.track_id, record.role_id, record.scope_id)
            for field_name, value in defaults.items():
                if not record[field_name]:
                    record[field_name] = value

    def action_open_guide(self):
        self.ensure_one()
        return {
            "name": _("内容执行模板"),
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def ensure_default_profiles(self):
        scopes = self.env["psc.content.scope"].search([
            ("code", "in", CONTENT_SCOPE_CODES),
        ])
        scope_by_code = {scope.code: scope for scope in scopes}
        if len(scope_by_code) != len(CONTENT_SCOPE_CODES):
            return False
        existing = set(self.search([]).mapped(lambda row: (
            row.track_id.id, row.role_id.id, row.scope_id.id,
        )))
        roles = self.env["psc.business.role"].search([
            ("code", "in", tuple(ROLE_CONTENT_MULTIPLIERS)), ("active", "=", True),
        ])
        values_list = []
        for track in self.env["psc.industry.track"].search([
            ("code", "in", tuple(TRACK_CONTENT_WEIGHTS)),
        ]):
            base_weights = TRACK_CONTENT_WEIGHTS[track.code]
            for role in roles:
                multipliers = ROLE_CONTENT_MULTIPLIERS.get(role.code, (1.0,) * len(CONTENT_SCOPE_CODES))
                weighted = [base * multiplier for base, multiplier in zip(base_weights, multipliers)]
                total = sum(weighted) or 1.0
                ratios = [round(100.0 * value / total) for value in weighted]
                ratios[weighted.index(max(weighted))] += 100 - sum(ratios)
                video_multiplier = (
                    TRACK_VIDEO_MULTIPLIERS.get(track.code, 1.0)
                    * ROLE_VIDEO_MULTIPLIERS.get(role.code, 1.0)
                )
                for code, ratio in zip(CONTENT_SCOPE_CODES, ratios):
                    scope = scope_by_code[code]
                    key = (track.id, role.id, scope.id)
                    if key in existing:
                        continue
                    values_list.append({
                        "track_id": track.id,
                        "role_id": role.id,
                        "scope_id": scope.id,
                        "content_ratio": ratio,
                        "video_ratio": min(100.0, round(scope.default_video_ratio * video_multiplier)),
                        "notes": _("系统经验初始值；可按真实发布、流量、询盘和成交数据调整。"),
                    })
        if values_list:
            self.create(values_list)
        profile_rules = self.search([
            ("track_id.code", "in", tuple(TRACK_CONTENT_WEIGHTS)),
            ("role_id.code", "in", tuple(ROLE_CONTENT_MULTIPLIERS)),
            ("scope_id.code", "in", CONTENT_SCOPE_CODES),
        ])
        for rule in profile_rules:
            defaults = self._default_guide_values(rule.track_id, rule.role_id, rule.scope_id)
            missing = {name: value for name, value in defaults.items() if not rule[name]}
            if missing:
                rule.write(missing)
        return True

class ProjectProduct(models.Model):
    _name = "psc.project.product"
    _description = "市场运营项目产品"
    _order = "priority, fit_score desc, id desc"

    name = fields.Char(string="项目产品", compute="_compute_name", store=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    product_id = fields.Many2one(
        "product.template", string="Odoo 正式产品", ondelete="restrict", index=True,
    )
    candidate_id = fields.Many2one(
        "product.intelligence.candidate", string="产品智能候选", ondelete="restrict", index=True,
    )
    source = fields.Selection([
        ("odoo", "Odoo 产品库"), ("intelligence", "产品智能"),
        ("manual", "人工录入"),
    ], string="产品来源", required=True, default="odoo")
    market_ids = fields.Many2many(
        "psc.target.market", "psc_project_product_market_rel", "project_product_id", "market_id",
        string="适用市场",
    )
    status = fields.Selection([
        ("candidate", "候选"), ("quotation", "待询价"),
        ("market_review", "待市场分析"), ("compliance_review", "待合规确认"),
        ("active", "可运营"), ("paused", "暂停推广"), ("rejected", "淘汰"),
    ], string="产品状态", required=True, default="candidate", index=True)
    priority = fields.Selection([
        ("1", "最高"), ("2", "高"), ("3", "普通"), ("4", "低"),
    ], string="推广优先级", default="3", required=True)
    positioning = fields.Text(string="项目产品定位", translate=True)
    selling_points = fields.Text(string="项目核心卖点", translate=True)
    recommendation = fields.Text(string="推荐/不推荐理由", translate=True)
    compliance_state = fields.Selection([
        ("unknown", "未检查"), ("review", "待复核"),
        ("passed", "通过"), ("blocked", "禁止发布"),
    ], string="合规状态", default="unknown", required=True)
    material_state = fields.Selection([
        ("missing", "资料不足"), ("partial", "部分完整"), ("complete", "完整"),
    ], string="产品资料", default="missing", required=True)
    currency_id = fields.Many2one(
        "res.currency", related="project_id.company_id.currency_id", readonly=True,
    )
    target_purchase_price = fields.Monetary(string="目标采购价", currency_field="currency_id")
    target_sale_price = fields.Monetary(string="目标销售价", currency_field="currency_id")
    minimum_order_qty = fields.Float(string="MOQ")
    lead_time_days = fields.Integer(string="交期（天）")
    score_line_ids = fields.One2many(
        "psc.project.product.score", "project_product_id", string="适配评分",
    )
    attribute_value_ids = fields.One2many(
        "psc.project.product.attribute.value", "project_product_id", string="赛道产品属性",
    )
    fit_score = fields.Float(string="市场适配评分", compute="_compute_fit_score", store=True)
    hard_gate_passed = fields.Boolean(string="硬性门槛通过", compute="_compute_fit_score", store=True)
    last_reviewed_at = fields.Datetime(string="最近检查时间")
    next_review_date = fields.Date(string="下次检查日期")

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            project = self.env["psc.publishing.project"].browse(values.get("project_id")).exists()
            candidate = self.env["product.intelligence.candidate"].browse(values.get("candidate_id")).exists()
            if project and not values.get("market_ids"):
                values["market_ids"] = [(6, 0, project.market_ids.ids)]
            if candidate:
                values.setdefault("source", "intelligence")
                values.setdefault("target_purchase_price", candidate.supplier_price)
                values.setdefault("target_sale_price", candidate.target_sale_price)
                values.setdefault("minimum_order_qty", candidate.minimum_order_qty)
                values.setdefault("lead_time_days", candidate.lead_time_days)
            if project and project.track_id and not values.get("score_line_ids"):
                values["score_line_ids"] = [(0, 0, {
                    "rule_id": rule.id, "name": rule.name, "sequence": rule.sequence,
                    "weight": rule.weight, "hard_gate": rule.hard_gate,
                    "gate_passed": not rule.hard_gate,
                }) for rule in project.track_id.scoring_rule_ids.filtered("active")]
            if project and project.track_id and not values.get("attribute_value_ids"):
                values["attribute_value_ids"] = [(0, 0, {
                    "attribute_id": attribute.id, "name": attribute.name,
                    "required_for_publish": attribute.required_for_publish,
                    "hard_gate": attribute.hard_gate, "sequence": attribute.sequence,
                }) for attribute in project.track_id.product_attribute_ids.filtered("active")]
        return super().create(vals_list)

    @api.depends("product_id", "candidate_id", "candidate_id.name")
    def _compute_name(self):
        for record in self:
            record.name = record.product_id.display_name or record.candidate_id.name or _("未命名候选产品")

    @api.depends(
        "score_line_ids.score", "score_line_ids.weight", "score_line_ids.hard_gate",
        "score_line_ids.gate_passed",
    )
    def _compute_fit_score(self):
        for record in self:
            lines = record.score_line_ids
            total_weight = sum(lines.mapped("weight"))
            record.fit_score = (
                sum(line.score * line.weight for line in lines) / total_weight
                if total_weight else 0.0
            )
            record.hard_gate_passed = not any(
                line.hard_gate and not line.gate_passed for line in lines
            )

    @api.constrains("product_id", "candidate_id")
    def _check_source_record(self):
        for record in self:
            if not record.product_id and not record.candidate_id:
                raise ValidationError(_("项目产品必须选择 Odoo 正式产品或产品智能候选。"))
            duplicate = self.search_count([
                ("id", "!=", record.id), ("project_id", "=", record.project_id.id),
                "|", "&", ("product_id", "!=", False), ("product_id", "=", record.product_id.id),
                "&", ("candidate_id", "!=", False), ("candidate_id", "=", record.candidate_id.id),
            ])
            if duplicate:
                raise ValidationError(_("该产品已经存在于当前项目产品池。"))

    def action_link_candidate_product(self):
        for record in self:
            candidate = record.candidate_id
            if not candidate:
                raise UserError(_("当前记录没有产品智能候选。"))
            if candidate.stage not in ("approved", "executed"):
                raise UserError(_("请先在产品智能中审核并批准该候选产品。"))
            if not candidate.product_tmpl_id:
                candidate.action_create_product()
            record.write({"product_id": candidate.product_tmpl_id.id, "source": "intelligence"})
        return True

    def action_mark_active(self):
        for record in self:
            if not record.product_id:
                raise UserError(_("进入可运营状态前，必须先关联 Odoo 正式产品。"))
            if record.material_state != "complete":
                raise UserError(_("产品资料尚未完整，不能批准运营。"))
            missing_attributes = record.attribute_value_ids.filtered(
                lambda line: line.required_for_publish and (not line.value or not line.verified)
            )
            if missing_attributes:
                raise UserError(_("以下发布必填属性尚未填写并核实：%s") % ", ".join(missing_attributes.mapped("name")))
            blocked_attributes = record.attribute_value_ids.filtered(
                lambda line: line.hard_gate and not line.verified
            )
            if blocked_attributes:
                raise UserError(_("以下硬性门槛尚未通过：%s") % ", ".join(blocked_attributes.mapped("name")))
            if record.compliance_state != "passed" or not record.hard_gate_passed:
                raise UserError(_("合规检查或硬性门槛尚未通过，不能对外运营。"))
            record.write({"status": "active", "last_reviewed_at": fields.Datetime.now()})
        return True

    def action_open_source(self):
        self.ensure_one()
        record = self.product_id or self.candidate_id
        if not record:
            return False
        return {
            "type": "ir.actions.act_window", "res_model": record._name,
            "res_id": record.id, "view_mode": "form", "target": "current",
        }


class CandidateMarketFit(models.Model):
    _name = "psc.candidate.market.fit"
    _description = "候选产品市场适配分析"
    _order = "fit_score desc, id desc"

    candidate_id = fields.Many2one(
        "product.intelligence.candidate", string="候选产品", required=True,
        ondelete="cascade", index=True,
    )
    track_id = fields.Many2one("psc.industry.track", string="经营赛道", required=True)
    market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    business_role_id = fields.Many2one("psc.business.role", string="适合角色")
    fit_score = fields.Float(string="市场适配评分", default=50.0)
    demand_evidence = fields.Text(string="需求依据")
    target_customer = fields.Text(string="适合客户")
    recommendation = fields.Text(string="推荐理由")
    compliance_state = fields.Selection([
        ("unknown", "未检查"), ("review", "待复核"),
        ("passed", "通过"), ("blocked", "不适合"),
    ], string="合规判断", default="unknown", required=True)
    state = fields.Selection([
        ("draft", "待分析"), ("review", "待人工复核"),
        ("approved", "确认适合"), ("rejected", "不适合"),
    ], string="结论", default="draft", required=True)

    _candidate_market_track_unique = models.Constraint(
        "UNIQUE(candidate_id, market_id, track_id)",
        "同一候选产品在同一赛道和市场只能有一份适配分析。",
    )

    @api.constrains("fit_score")
    def _check_fit_score(self):
        for fit in self:
            if not 0.0 <= fit.fit_score <= 100.0:
                raise ValidationError(_("市场适配评分必须在 0 到 100 之间。"))


class ProductIntelligenceCandidateMarket(models.Model):
    _inherit = "product.intelligence.candidate"

    psc_market_fit_ids = fields.One2many(
        "psc.candidate.market.fit", "candidate_id", string="适合市场分析",
    )


class ProjectProductScore(models.Model):
    _name = "psc.project.product.score"
    _description = "项目产品适配评分"
    _order = "project_product_id, sequence, id"

    project_product_id = fields.Many2one(
        "psc.project.product", string="项目产品", required=True, ondelete="cascade", index=True,
    )
    rule_id = fields.Many2one("psc.track.scoring.rule", string="评分规则", ondelete="restrict")
    name = fields.Char(string="评分维度", required=True)
    sequence = fields.Integer(default=10)
    weight = fields.Float(string="权重 %", required=True, default=10.0)
    score = fields.Float(string="得分", required=True, default=50.0)
    hard_gate = fields.Boolean(string="硬性门槛")
    gate_passed = fields.Boolean(string="已通过", default=True)
    notes = fields.Text(string="依据与说明")

    @api.onchange("rule_id")
    def _onchange_rule_id(self):
        if self.rule_id:
            self.name = self.rule_id.name
            self.sequence = self.rule_id.sequence
            self.weight = self.rule_id.weight
            self.hard_gate = self.rule_id.hard_gate

    @api.constrains("weight", "score")
    def _check_values(self):
        for line in self:
            if not 0.0 <= line.weight <= 100.0 or not 0.0 <= line.score <= 100.0:
                raise ValidationError(_("权重和得分必须在 0 到 100 之间。"))


class ProjectProductAttributeValue(models.Model):
    _name = "psc.project.product.attribute.value"
    _description = "项目产品赛道属性值"
    _order = "project_product_id, sequence, id"

    project_product_id = fields.Many2one(
        "psc.project.product", string="项目产品", required=True, ondelete="cascade", index=True,
    )
    attribute_id = fields.Many2one(
        "psc.track.product.attribute", string="属性模板", required=True, ondelete="restrict",
    )
    name = fields.Char(string="属性名称", required=True)
    sequence = fields.Integer(default=10)
    value = fields.Char(string="属性值")
    required_for_publish = fields.Boolean(string="发布前必填")
    hard_gate = fields.Boolean(string="硬性门槛")
    verified = fields.Boolean(string="已核实")
    evidence = fields.Text(string="依据/附件说明")

    _product_attribute_unique = models.Constraint(
        "UNIQUE(project_product_id, attribute_id)", "同一个项目产品的赛道属性不能重复。",
    )


class ContentPlan(models.Model):
    _name = "psc.content.plan"
    _description = "社媒内容任务"
    _order = "scheduled_at, id"

    name = fields.Char(string="内容主题", required=True, translate=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    scope_id = fields.Many2one("psc.content.scope", string="内容类型", ondelete="restrict", index=True)
    pillar_id = fields.Many2one("psc.content.pillar", string="原内容栏目", ondelete="set null")
    content_format = fields.Selection([
        ("short_video", "短视频"), ("image", "单图"),
        ("carousel", "多图/轮播"), ("article", "文章/长文"),
    ], string="内容形式", required=True, default="short_video", index=True)
    objective = fields.Selection([
        ("awareness", "建立认知"), ("trust", "建立信任"),
        ("lead", "获取询盘"), ("conversion", "促进成交"),
        ("retention", "客户维护"),
    ], string="内容目标", required=True, default="trust")
    product_id = fields.Many2one("product.template", string="主关联产品", ondelete="set null")
    product_ids = fields.Many2many(
        "product.template", "psc_content_plan_product_rel", "plan_id", "product_id",
        string="关联产品",
    )
    market_id = fields.Many2one("psc.target.market", string="主目标市场")
    market_ids = fields.Many2many(
        "psc.target.market", "psc_content_plan_market_rel", "plan_id", "market_id",
        string="目标市场",
    )
    channel_id = fields.Many2one("psc.publishing.channel", string="主发布渠道")
    channel_ids = fields.Many2many(
        "psc.publishing.channel", "psc_content_plan_channel_rel", "plan_id", "channel_id",
        string="发布渠道",
    )
    cluster_ids = fields.Many2many(
        "psc.social.account.cluster", "psc_content_plan_cluster_rel", "plan_id", "cluster_id",
        string="目标账号集群",
    )
    tag_ids = fields.Many2many(
        "psc.media.tag", "psc_content_plan_tag_rel", "plan_id", "tag_id",
        string="内容标签",
    )
    scheduled_at = fields.Datetime(string="计划发布时间")
    brief = fields.Text(string="内容要求", translate=True)
    state = fields.Selection([
        ("draft", "计划"), ("prepared", "已生成草稿"),
        ("ready", "待发布"), ("published", "已发布"), ("cancelled", "取消"),
    ], string="状态", default="draft", required=True, index=True)
    content_id = fields.Many2one("psc.content.variant", string="首个渠道版本", readonly=True)
    content_ids = fields.One2many("psc.content.variant", "plan_id", string="渠道内容版本", readonly=True)
    content_count = fields.Integer(string="渠道版本数", compute="_compute_content_count")

    @api.depends("content_ids")
    def _compute_content_count(self):
        for plan in self:
            plan.content_count = len(plan.content_ids)

    @api.onchange("project_id")
    def _onchange_project(self):
        for plan in self:
            if not plan.project_id:
                continue
            plan.market_ids = plan.project_id.market_ids
            plan.channel_ids = plan.project_id.channel_ids
            plan.cluster_ids = plan.project_id.account_cluster_ids

    def action_prepare_content(self):
        for plan in self:
            markets = plan.market_ids or plan.market_id or plan.project_id.market_ids
            channels = plan.channel_ids or plan.channel_id or plan.project_id.channel_ids
            market_channel_pairs = {(market, channel) for market in markets for channel in channels}
            if plan.cluster_ids:
                cluster_channels = plan.cluster_ids.mapped("account_ids.channel_id")
                if not cluster_channels:
                    raise UserError(_("所选账号集群还没有可用的平台账号，请先配置集群账号。"))
                market_channel_pairs = {
                    (cluster.target_market_id, account.channel_id)
                    for cluster in plan.cluster_ids
                    for account in cluster.account_ids
                    if cluster.target_market_id in markets and account.channel_id in channels
                }
                market_channel_pairs |= {
                    (market, channel)
                    for market in markets
                    for channel in channels.filtered(lambda item: item.platform == "website")
                }
            if not market_channel_pairs:
                raise UserError(_("请先选择目标市场和发布渠道，或选择已经配置账号的目标集群。"))
            products = plan.product_ids | plan.product_id
            if plan.scope_id.code == "product_category" and not products:
                raise UserError(_("“产品或品类介绍”内容必须至少关联一个真实产品。"))
            if plan.scope_id.code == "product_category":
                approved_products = plan.project_id.project_product_ids.filtered(
                    lambda item: item.product_id in products
                    and item.status == "active"
                    and item.compliance_state == "passed"
                    and item.material_state == "complete"
                    and item.hard_gate_passed
                ).mapped("product_id")
                if products - approved_products:
                    raise UserError(_("产品类内容只能使用已完成资料、合规和硬门槛审核的项目产品。"))
            existing = {(content.market_id.id, content.channel_id.id) for content in plan.content_ids}
            created = self.env["psc.content.variant"]
            for market, channel in market_channel_pairs:
                if (market.id, channel.id) in existing:
                    continue
                created |= self.env["psc.content.variant"].create({
                    "project_id": plan.project_id.id,
                    "plan_id": plan.id,
                    "pillar_id": plan.pillar_id.id,
                    "product_id": plan.product_id.id or products[:1].id or False,
                    "product_ids": [(6, 0, products.ids)],
                    "market_id": market.id,
                    "channel_id": channel.id,
                    "language_id": market.lang_id.id,
                    "title": plan.name,
                    "caption": plan.brief or plan.pillar_id.instructions or plan.scope_id.description or "",
                    "tag_ids": [(6, 0, plan.tag_ids.ids)],
                    "state": "draft",
                })
            contents = plan.content_ids | created
            if contents:
                plan.write({
                    "content_id": plan.content_id.id or contents[:1].id,
                    "state": "prepared",
                })
                if plan.project_id.state == "draft":
                    plan.project_id.state = "generated"
        return self.action_open_content()

    def action_open_content(self):
        self.ensure_one()
        contents = self.content_ids | self.content_id
        if not contents:
            raise UserError(_("尚未生成渠道内容草稿。"))
        if len(contents) == 1:
            return {
                "type": "ir.actions.act_window", "res_model": "psc.content.variant",
                "res_id": contents.id, "view_mode": "form", "target": "current",
            }
        action = self.env["ir.actions.actions"]._for_xml_id(
            "product_social_content_bridge.action_psc_content"
        )
        action["domain"] = [("plan_id", "=", self.id)]
        action["context"] = {"default_project_id": self.project_id.id, "default_plan_id": self.id}
        return action


class SocialAccountCluster(models.Model):
    _name = "psc.social.account.cluster"
    _description = "社媒账号集群"
    _order = "name"

    name = fields.Char(string="账号集群", required=True)
    active = fields.Boolean(default=True)
    project_ids = fields.Many2many(
        "psc.publishing.project", "psc_project_account_cluster_rel", "cluster_id", "project_id",
        string="允许发布的项目",
    )
    track_id = fields.Many2one("psc.industry.track", string="主赛道")
    product_line_id = fields.Many2one("psc.product.line", string="品牌/产品线")
    target_market_id = fields.Many2one("psc.target.market", string="目标市场", required=True)
    persona = fields.Char(string="品牌/运营身份", required=True)
    positioning = fields.Text(string="账号定位")
    worker_node_id = fields.Many2one(
        "psc.local.worker.node", string="Windows 工作节点", required=True,
    )
    bitbrowser_environment_id = fields.Many2one(
        "psc.bitbrowser.environment", string="比特浏览器环境", required=True,
        domain="[('worker_node_id', '=', worker_node_id), ('available', '=', True)]",
    )
    expected_ip = fields.Char(string="预期固定 IP", required=True)
    expected_country_id = fields.Many2one("res.country", string="预期国家/地区", required=True)
    expected_timezone = fields.Char(string="预期时区", required=True, default="UTC")
    state = fields.Selection([
        ("draft", "待配置"), ("ready", "可使用"),
        ("busy", "环境占用"), ("failed", "环境异常"), ("paused", "暂停"),
    ], string="集群状态", required=True, default="draft", index=True)
    account_ids = fields.One2many(
        "psc.social.publishing.account", "cluster_id", string="平台账号",
    )
    last_validation_at = fields.Datetime(string="最后环境校验", readonly=True)
    last_validation_message = fields.Text(string="环境校验结果", readonly=True)

    _environment_unique = models.Constraint(
        "UNIQUE(bitbrowser_environment_id)", "一个比特浏览器环境只能绑定一个账号集群。",
    )

    @api.onchange("target_market_id")
    def _onchange_target_market_id(self):
        if self.target_market_id:
            self.expected_country_id = self.target_market_id.country_id

    @api.constrains("worker_node_id", "bitbrowser_environment_id")
    def _check_environment_worker(self):
        for cluster in self:
            if cluster.bitbrowser_environment_id.worker_node_id != cluster.worker_node_id:
                raise ValidationError(_("比特环境不属于所选 Windows 工作节点。"))

    def action_mark_ready(self):
        for cluster in self:
            if not cluster.account_ids.filtered(lambda account: account.account_state == "available"):
                raise UserError(_("账号集群至少需要一个可发布的平台账号。"))
            cluster.state = "ready"
        return True

    def action_pause(self):
        self.write({"state": "paused"})
        return True


class CustomerTouchpoint(models.Model):
    _name = "psc.customer.touchpoint"
    _description = "客户来源触点"
    _order = "occurred_at desc, id desc"

    lead_id = fields.Many2one("crm.lead", string="客户/线索", required=True, ondelete="cascade", index=True)
    occurred_at = fields.Datetime(string="发生时间", required=True, default=fields.Datetime.now, index=True)
    event_type = fields.Selection([
        ("impression", "看到内容"), ("click", "点击"), ("visit", "访问网站"),
        ("download", "下载资料"), ("inquiry", "询盘"), ("message", "沟通"),
        ("quote", "报价"), ("sample", "样品"), ("order", "订单"),
        ("offline", "线下接触"),
    ], string="触点类型", required=True, default="inquiry")
    source_type = fields.Selection([
        ("website", "独立站"), ("facebook", "Facebook"),
        ("instagram", "Instagram"), ("tiktok", "TikTok"),
        ("linkedin", "LinkedIn"), ("youtube", "YouTube"),
        ("alibaba", "阿里国际站"), ("exhibition", "展会"),
        ("offline", "线下"), ("referral", "客户介绍"),
        ("manual", "人工录入"), ("unknown", "未知"),
    ], string="来源", required=True, default="unknown", index=True)
    project_id = fields.Many2one("psc.publishing.project", string="市场运营项目", index=True)
    market_id = fields.Many2one("psc.target.market", string="市场")
    channel_id = fields.Many2one("psc.publishing.channel", string="渠道")
    cluster_id = fields.Many2one("psc.social.account.cluster", string="账号集群")
    account_id = fields.Many2one("psc.social.publishing.account", string="平台账号")
    content_id = fields.Many2one("psc.content.variant", string="来源内容")
    product_id = fields.Many2one("product.template", string="感兴趣产品")
    landing_url = fields.Char(string="入口链接")
    external_reference = fields.Char(string="平台询盘/消息编号")
    utm_source = fields.Char(string="UTM Source")
    utm_medium = fields.Char(string="UTM Medium")
    utm_campaign = fields.Char(string="UTM Campaign")
    utm_content = fields.Char(string="UTM Content")
    utm_term = fields.Char(string="UTM Term")
    verified = fields.Boolean(string="来源已确认")
    notes = fields.Text(string="说明")


class CustomerRequirement(models.Model):
    _name = "psc.customer.requirement"
    _description = "客户行业需求单"
    _order = "create_date desc"

    name = fields.Char(string="需求主题", required=True)
    lead_id = fields.Many2one("crm.lead", string="客户/线索", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one("psc.publishing.project", string="市场运营项目", required=True)
    track_id = fields.Many2one(related="project_id.track_id", string="经营赛道", store=True, readonly=True)
    product_ids = fields.Many2many("product.template", string="感兴趣产品")
    organization_type = fields.Char(string="机构类型")
    contact_role = fields.Char(string="联系人角色")
    requirement_details = fields.Text(string="行业需求详情")
    quantity = fields.Float(string="预计数量")
    budget = fields.Monetary(string="预算", currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    certification_requirements = fields.Text(string="认证/合规要求")
    delivery_country_id = fields.Many2one("res.country", string="交付国家")
    delivery_port = fields.Char(string="交付港口/地点")
    target_purchase_date = fields.Date(string="预计采购日期")
    stage = fields.Selection([
        ("new", "新需求"), ("qualified", "已确认"), ("quoted", "已报价"),
        ("sample", "样品中"), ("negotiation", "谈判中"),
        ("won", "已成交"), ("lost", "未成交"),
    ], string="采购阶段", default="new", required=True)
    lost_reason = fields.Text(string="未成交原因")


class PerformanceSnapshot(models.Model):
    _name = "psc.performance.snapshot"
    _description = "渠道经营数据快照"
    _order = "snapshot_date desc, id desc"

    snapshot_date = fields.Date(string="数据日期", required=True, default=fields.Date.context_today, index=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    destination_id = fields.Many2one("psc.publishing.destination", string="发布目标")
    cluster_id = fields.Many2one("psc.social.account.cluster", string="账号集群")
    account_id = fields.Many2one("psc.social.publishing.account", string="平台账号")
    content_id = fields.Many2one("psc.content.variant", string="内容")
    product_id = fields.Many2one("product.template", string="产品")
    impressions = fields.Integer(string="曝光")
    views = fields.Integer(string="播放/浏览")
    clicks = fields.Integer(string="点击")
    inquiries = fields.Integer(string="询盘")
    qualified_leads = fields.Integer(string="有效客户")
    quotations = fields.Integer(string="报价")
    orders = fields.Integer(string="订单")
    currency_id = fields.Many2one("res.currency", related="project_id.company_id.currency_id", readonly=True)
    revenue = fields.Monetary(string="销售额", currency_field="currency_id")
    purchase_cost = fields.Monetary(string="采购成本", currency_field="currency_id")
    traffic_cost = fields.Monetary(string="流量成本", currency_field="currency_id")
    notes = fields.Text(string="数据说明")


class OptimizationAction(models.Model):
    _name = "psc.optimization.action"
    _description = "经营优化任务"
    _order = "priority, due_date, id desc"

    name = fields.Char(string="优化任务", required=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    category = fields.Selection([
        ("market", "市场需求"), ("product", "产品"), ("content", "内容"),
        ("channel", "渠道/账号"), ("customer", "客户转化"),
        ("supplier", "供应与采购"),
    ], string="优化类型", required=True, default="content")
    priority = fields.Selection([
        ("1", "紧急"), ("2", "高"), ("3", "普通"), ("4", "低"),
    ], default="3", required=True)
    evidence = fields.Text(string="数据依据", required=True)
    proposed_action = fields.Text(string="建议动作", required=True)
    owner_id = fields.Many2one("res.users", string="负责人", default=lambda self: self.env.user)
    due_date = fields.Date(string="计划完成日期")
    state = fields.Selection([
        ("draft", "待评估"), ("approved", "已批准"), ("doing", "执行中"),
        ("done", "已完成"), ("rejected", "不执行"),
    ], string="状态", default="draft", required=True)
    result = fields.Text(string="执行结果")

    def action_approve(self):
        self.write({"state": "approved"})
        return True

    def action_start(self):
        self.write({"state": "doing"})
        return True

    def action_done(self):
        self.write({"state": "done"})
        return True


class ProjectReadinessItem(models.Model):
    _name = "psc.project.readiness.item"
    _description = "项目上线准备项"
    _order = "due_date, sequence, id"

    name = fields.Char(string="准备事项", required=True)
    template_key = fields.Char(string="模板键", required=True, index=True)
    project_id = fields.Many2one(
        "psc.publishing.project", string="市场运营项目", required=True,
        ondelete="cascade", index=True,
    )
    sequence = fields.Integer(default=10)
    category = fields.Selection([
        ("strategy", "定位与市场"), ("product", "产品与供应"),
        ("compliance", "合规与知识产权"), ("commercial", "交易与交付"),
        ("content", "英文内容与素材"), ("channel", "渠道与数据"),
        ("operations", "CRM与运营演练"),
    ], string="阶段", required=True, default="strategy", index=True)
    weight = fields.Float(string="进度权重 %", required=True, default=1.0)
    hard_gate = fields.Boolean(string="上线硬门槛")
    responsibility = fields.Selection([
        ("ai", "ChatGPT主办"), ("user", "本人配置"), ("joint", "共同完成"),
    ], string="责任归属", required=True, default="joint", index=True)
    owner_id = fields.Many2one(
        "res.users", string="Odoo负责人", required=True, default=lambda self: self.env.user,
    )
    due_date = fields.Date(string="计划完成日期", index=True)
    state = fields.Selection([
        ("todo", "待开始"), ("doing", "进行中"),
        ("blocked", "阻塞"), ("done", "已完成"),
    ], string="状态", required=True, default="todo", index=True)
    description = fields.Text(string="完成标准")
    evidence = fields.Text(string="完成依据")
    block_reason = fields.Text(string="阻塞原因")
    completed_at = fields.Datetime(string="完成时间", readonly=True)

    _project_template_unique = models.Constraint(
        "UNIQUE(project_id, template_key)", "同一项目不能重复创建相同的准备事项。",
    )

    @api.constrains("weight")
    def _check_weight(self):
        for item in self:
            if not 0.0 < item.weight <= 100.0:
                raise ValidationError(_("准备事项权重必须大于0且不超过100。"))

    def action_start(self):
        self.write({"state": "doing", "block_reason": False, "completed_at": False})
        return True

    def action_block(self):
        for item in self:
            if not item.block_reason:
                raise UserError(_("请先填写阻塞原因。"))
        self.write({"state": "blocked", "completed_at": False})
        return True

    def action_done(self):
        for item in self:
            if item.hard_gate and not item.evidence:
                raise UserError(_("上线硬门槛必须填写真实完成依据。"))
        self.write({
            "state": "done", "block_reason": False,
            "completed_at": fields.Datetime.now(),
        })
        return True

    def action_reopen(self):
        self.write({"state": "todo", "completed_at": False})
        return True


class PublishingProjectOperations(models.Model):
    _inherit = "psc.publishing.project"

    track_id = fields.Many2one("psc.industry.track", string="经营赛道", tracking=True)
    business_role_id = fields.Many2one("psc.business.role", string="主要经营角色", tracking=True)
    content_brief_zh = fields.Text(string="项目内容总规则（中文）")
    capability_ids = fields.Many2many(
        "psc.business.capability", "psc_project_capability_rel", "project_id", "capability_id",
        string="经营能力",
    )
    operation_state = fields.Selection([
        ("planning", "筹备"), ("active", "运营中"),
        ("paused", "暂停"), ("closed", "已结束"),
    ], string="运营状态", default="planning", required=True, tracking=True)
    business_goal = fields.Text(string="项目经营目标", translate=True)
    project_product_ids = fields.One2many("psc.project.product", "project_id", string="项目产品池")
    content_plan_ids = fields.One2many("psc.content.plan", "project_id", string="内容计划")
    account_cluster_ids = fields.Many2many(
        "psc.social.account.cluster", "psc_project_account_cluster_rel", "project_id", "cluster_id",
        string="账号集群",
    )
    content_mix_rule_ids = fields.Many2many(
        "psc.content.mix.rule", string="建议内容与视频比例",
        compute="_compute_content_mix_rules",
    )
    lead_ids = fields.One2many("crm.lead", "psc_project_id", string="客户与线索")
    performance_snapshot_ids = fields.One2many(
        "psc.performance.snapshot", "project_id", string="经营数据",
    )
    optimization_action_ids = fields.One2many(
        "psc.optimization.action", "project_id", string="优化任务",
    )
    readiness_item_ids = fields.One2many(
        "psc.project.readiness.item", "project_id", string="上线准备清单",
    )
    readiness_progress = fields.Float(
        string="上线准备进度 %", compute="_compute_readiness", store=True,
    )
    readiness_total_count = fields.Integer(
        string="准备项总数", compute="_compute_readiness", store=True,
    )
    readiness_done_count = fields.Integer(
        string="已完成", compute="_compute_readiness", store=True,
    )
    readiness_blocked_count = fields.Integer(
        string="阻塞项", compute="_compute_readiness", store=True,
    )
    readiness_overdue_count = fields.Integer(string="逾期项", compute="_compute_readiness")
    launch_ready = fields.Boolean(
        string="允许上线", compute="_compute_readiness", store=True,
    )
    readiness_blocker_summary = fields.Text(
        string="上线阻塞摘要", compute="_compute_readiness",
    )

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        for project in projects:
            if project.track_id and project.business_role_id and not project.content_brief_zh:
                project.content_brief_zh = project._default_content_brief_zh()
        return projects

    @api.depends("track_id", "business_role_id")
    def _compute_content_mix_rules(self):
        rule_model = self.env["psc.content.mix.rule"]
        for project in self:
            project.content_mix_rule_ids = rule_model.search([
                ("track_id", "=", project.track_id.id),
                ("role_id", "=", project.business_role_id.id),
                ("active", "=", True),
            ]) if project.track_id and project.business_role_id else rule_model

    @api.depends(
        "readiness_item_ids.state", "readiness_item_ids.weight",
        "readiness_item_ids.hard_gate", "readiness_item_ids.due_date",
    )
    def _compute_readiness(self):
        today = fields.Date.context_today(self)
        for project in self:
            items = project.readiness_item_ids
            done = items.filtered(lambda item: item.state == "done")
            blocked = items.filtered(lambda item: item.state == "blocked")
            overdue = items.filtered(
                lambda item: item.state != "done" and item.due_date and item.due_date < today
            )
            total_weight = sum(items.mapped("weight"))
            progress = 100.0 * sum(done.mapped("weight")) / total_weight if total_weight else 0.0
            incomplete_hard_gates = items.filtered(
                lambda item: item.hard_gate and item.state != "done"
            )
            project.readiness_progress = progress
            project.readiness_total_count = len(items)
            project.readiness_done_count = len(done)
            project.readiness_blocked_count = len(blocked)
            project.readiness_overdue_count = len(overdue)
            project.launch_ready = bool(items) and progress >= 100.0 and not incomplete_hard_gates
            blockers = blocked or incomplete_hard_gates[:5]
            project.readiness_blocker_summary = "\n".join(
                "%s：%s" % (item.name, item.block_reason or _("尚未完成"))
                for item in blockers[:5]
            )

    def _check_readiness_before_launch(self):
        for project in self:
            if project.readiness_item_ids and not project.launch_ready:
                raise UserError(_(
                    "项目上线准备进度为 %.1f%%，仍有%s个阻塞项和%s个未完成硬门槛。"
                ) % (
                    project.readiness_progress,
                    project.readiness_blocked_count,
                    len(project.readiness_item_ids.filtered(
                        lambda item: item.hard_gate and item.state != "done"
                    )),
                ))
        return True

    def _check_products_before_launch(self):
        for project in self.filtered("readiness_item_ids"):
            if not project.project_product_ids:
                raise UserError(_("至少需要一个已核实并批准运营的项目产品。"))
            invalid_products = project.project_product_ids.filtered(
                lambda item: item.status != "active"
                or item.compliance_state != "passed"
                or item.material_state != "complete"
                or not item.hard_gate_passed
            )
            if invalid_products:
                raise UserError(_("以下产品尚未通过全部上线门槛：%s") % ", ".join(
                    invalid_products.mapped("name")
                ))
        return True

    def action_open_readiness_items(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "product_social_content_bridge.action_psc_project_readiness_items"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {
            "default_project_id": self.id,
            "search_default_my_work": 1,
        }
        return action

    def action_open_content_mix_rules(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "product_social_content_bridge.action_psc_content_mix_rules"
        )
        action["domain"] = [
            ("track_id", "=", self.track_id.id),
            ("role_id", "=", self.business_role_id.id),
        ]
        action["context"] = {
            "default_track_id": self.track_id.id,
            "default_role_id": self.business_role_id.id,
        }
        return action

    def action_open_video_content_share(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "product_social_content_bridge.action_psc_video_content_share"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {
            "search_default_published": 1,
            "search_default_video": 1,
            "search_default_group_cluster": 1,
            "search_default_group_scope": 1,
        }
        return action

    def ensure_footwear_sourcing_readiness(self):
        item_model = self.env["psc.project.readiness.item"]
        today = fields.Date.context_today(self)
        for project in self:
            existing_keys = set(project.readiness_item_ids.mapped("template_key"))
            values_list = []
            for key, sequence, category, name, weight, hard_gate, responsibility, due_days, description in FOOTWEAR_SOURCING_READINESS_TEMPLATE:
                if key in existing_keys:
                    continue
                values_list.append({
                    "project_id": project.id,
                    "template_key": key,
                    "sequence": sequence,
                    "category": category,
                    "name": name,
                    "weight": weight,
                    "hard_gate": hard_gate,
                    "responsibility": responsibility,
                    "owner_id": project.user_id.id or self.env.user.id,
                    "due_date": today + relativedelta(days=due_days),
                    "description": description,
                })
            if values_list:
                item_model.create(values_list)
        return True

    @api.onchange("track_id")
    def _onchange_track_id(self):
        for project in self:
            if project.track_id and not project.content_brief:
                project.content_brief = project.track_id.compliance_notes
            if project.track_id and project.business_role_id and not project.content_brief_zh:
                project.content_brief_zh = project._default_content_brief_zh()

    @api.onchange("business_role_id")
    def _onchange_business_role_id(self):
        for project in self:
            if project.business_role_id:
                project.capability_ids = project.business_role_id.capability_ids
            if project.track_id and project.business_role_id and not project.content_brief_zh:
                project.content_brief_zh = project._default_content_brief_zh()

    def _default_content_brief_zh(self):
        self.ensure_one()
        if not (self.track_id and self.business_role_id):
            return ""
        focus = (
            self.business_role_id.content_focus
            or self.business_role_id.description
            or _("可核实的客户价值")
        ).rstrip("。；; ")
        return _(
            "面向“%(track)s”赛道的目标客户，以“%(role)s”身份进行内容创作。重点展示：%(focus)s。"
            "所有产品、供应商、认证、价格、交期、案例和结果只能使用 Odoo 中已核实的事实；合规边界：%(compliance)s",
            track=self.track_id.name,
            role=self.business_role_id.name,
            focus=focus,
            compliance=self.track_id.compliance_notes or _("不得虚构或夸大任何业务事实。"),
        )

    @api.model
    def ensure_bilingual_content_briefs(self):
        projects = self.search([
            ("track_id", "!=", False),
            ("business_role_id", "!=", False),
        ])
        for project in projects:
            if not project.content_brief_zh or "。。" in project.content_brief_zh:
                project.content_brief_zh = project._default_content_brief_zh()
        return True

    def action_activate_operation(self):
        for project in self:
            if not project.track_id or not project.business_role_id or not project.market_ids:
                raise UserError(_("请先配置经营赛道、主要角色和目标市场。"))
            project._check_readiness_before_launch()
            project._check_products_before_launch()
            project.operation_state = "active"
        return True

    def action_mark_ready(self):
        self._check_readiness_before_launch()
        self._check_products_before_launch()
        return super().action_mark_ready()

    def action_create_publication_tasks(self):
        self._check_readiness_before_launch()
        self._check_products_before_launch()
        return super().action_create_publication_tasks()

    def action_sync_product_pool(self):
        pool_model = self.env["psc.project.product"]
        for project in self:
            existing = project.project_product_ids.mapped("product_id")
            for product in project.product_ids - existing:
                pool_model.create({
                    "project_id": project.id, "product_id": product.id, "source": "odoo",
                    "market_ids": [(6, 0, project.market_ids.ids)],
                })
        return True


class ContentVariantOperations(models.Model):
    _inherit = "psc.content.variant"

    plan_id = fields.Many2one("psc.content.plan", string="内容计划", ondelete="set null", index=True)
    pillar_id = fields.Many2one("psc.content.pillar", string="内容栏目")
    scope_id = fields.Many2one(
        related="plan_id.scope_id", string="内容类型", store=True, readonly=True, index=True,
    )
    content_format = fields.Selection(
        related="plan_id.content_format", string="内容形式", store=True, readonly=True,
    )
    product_ids = fields.Many2many(
        "product.template", "psc_content_variant_product_rel", "content_id", "product_id",
        string="关联产品",
    )
    tag_ids = fields.Many2many(
        "psc.media.tag", "psc_content_variant_tag_rel", "content_id", "tag_id",
        string="内容标签",
    )


class SocialPublishingAccountCluster(models.Model):
    _inherit = "psc.social.publishing.account"

    cluster_id = fields.Many2one(
        "psc.social.account.cluster", string="账号集群", ondelete="restrict", index=True,
    )

    @api.model
    def _values_from_cluster(self, cluster):
        return {
            "product_line_id": cluster.product_line_id.id,
            "target_market_id": cluster.target_market_id.id,
            "worker_node_id": cluster.worker_node_id.id,
            "bitbrowser_environment_id": cluster.bitbrowser_environment_id.id,
            "expected_ip": cluster.expected_ip,
            "expected_country_id": cluster.expected_country_id.id,
            "expected_timezone": cluster.expected_timezone,
        }

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            cluster = self.env["psc.social.account.cluster"].browse(values.get("cluster_id")).exists()
            if cluster:
                values.update(self._values_from_cluster(cluster))
        return super().create(vals_list)

    def write(self, values):
        if "cluster_id" in values:
            cluster = self.env["psc.social.account.cluster"].browse(values.get("cluster_id")).exists()
            if cluster:
                values = dict(values, **self._values_from_cluster(cluster))
        return super().write(values)

    @api.onchange("cluster_id")
    def _onchange_cluster_id(self):
        for account in self:
            if account.cluster_id:
                cluster = account.cluster_id
                account.product_line_id = cluster.product_line_id
                account.target_market_id = cluster.target_market_id
                account.worker_node_id = cluster.worker_node_id
                account.bitbrowser_environment_id = cluster.bitbrowser_environment_id
                account.expected_ip = cluster.expected_ip
                account.expected_country_id = cluster.expected_country_id
                account.expected_timezone = cluster.expected_timezone

    @api.constrains(
        "cluster_id", "worker_node_id", "bitbrowser_environment_id", "expected_ip",
        "expected_country_id", "expected_timezone", "target_market_id",
    )
    def _check_cluster_environment(self):
        for account in self.filtered("cluster_id"):
            cluster = account.cluster_id
            if (
                account.worker_node_id != cluster.worker_node_id
                or account.bitbrowser_environment_id != cluster.bitbrowser_environment_id
                or account.expected_ip != cluster.expected_ip
                or account.expected_country_id != cluster.expected_country_id
                or account.expected_timezone != cluster.expected_timezone
                or account.target_market_id != cluster.target_market_id
            ):
                raise ValidationError(_("平台账号的环境、IP、国家、时区和市场必须与账号集群一致。"))


class CrmLeadOperations(models.Model):
    _inherit = "crm.lead"

    psc_touchpoint_ids = fields.One2many("psc.customer.touchpoint", "lead_id", string="来源触点")
    psc_first_touchpoint_id = fields.Many2one(
        "psc.customer.touchpoint", string="首次来源", compute="_compute_psc_touchpoints", store=True,
    )
    psc_last_touchpoint_id = fields.Many2one(
        "psc.customer.touchpoint", string="最近来源", compute="_compute_psc_touchpoints", store=True,
    )
    psc_requirement_ids = fields.One2many("psc.customer.requirement", "lead_id", string="行业需求")

    @api.depends("psc_touchpoint_ids.occurred_at", "psc_touchpoint_ids.verified")
    def _compute_psc_touchpoints(self):
        for lead in self:
            verified = lead.psc_touchpoint_ids.filtered("verified").sorted(
                key=lambda item: (item.occurred_at, item.id)
            )
            touches = verified or lead.psc_touchpoint_ids.sorted(
                key=lambda item: (item.occurred_at, item.id)
            )
            lead.psc_first_touchpoint_id = touches[:1]
            lead.psc_last_touchpoint_id = touches[-1:] if touches else False


class SocialRegistrationTaskCluster(models.Model):
    _inherit = "psc.social.registration.task"

    cluster_id = fields.Many2one(
        "psc.social.account.cluster", string="账号集群", ondelete="restrict", index=True,
    )

    @api.onchange("cluster_id")
    def _onchange_cluster_id(self):
        for task in self:
            if task.cluster_id:
                cluster = task.cluster_id
                task.worker_node_id = cluster.worker_node_id
                task.bitbrowser_environment_id = cluster.bitbrowser_environment_id
                task.expected_ip = cluster.expected_ip
                task.expected_country_id = cluster.expected_country_id
                task.expected_timezone = cluster.expected_timezone

    @api.constrains(
        "cluster_id", "worker_node_id", "bitbrowser_environment_id", "expected_ip",
        "expected_country_id", "expected_timezone",
    )
    def _check_cluster_environment(self):
        for task in self.filtered("cluster_id"):
            cluster = task.cluster_id
            if (
                task.worker_node_id != cluster.worker_node_id
                or task.bitbrowser_environment_id != cluster.bitbrowser_environment_id
                or task.expected_ip != cluster.expected_ip
                or task.expected_country_id != cluster.expected_country_id
                or task.expected_timezone != cluster.expected_timezone
            ):
                raise ValidationError(_("注册任务的环境、IP、国家和时区必须与账号集群一致。"))
