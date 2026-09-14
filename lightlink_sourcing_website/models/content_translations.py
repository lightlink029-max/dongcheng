"""One-time bilingual seed used by install and versioned migrations."""


def _lines(*items):
    return "\n".join(items)


ASSET_ENGLISH = {
    "asset_sourcing_hero": {
        "name": "Homepage hero",
        "caption": "Sourcing team and international buyer reviewing the product plan",
    },
    "asset_product_development": {
        "name": "Product development and sampling",
        "caption": "Move from requirement, material and packaging to an approved production sample",
    },
    "asset_quality_inspection": {
        "name": "Inspection and quality control",
        "caption": "Record quality evidence against confirmed specifications and checkpoints",
    },
    "asset_shipping_consolidation": {
        "name": "Consolidation and international shipping",
        "caption": "Coordinate packaging, carton data, consolidation and delivery milestones",
    },
}


ASSET_CHINESE = {
    "asset_sourcing_hero": {
        "name": "首页主视觉",
        "alt_text": "国际买家与采购团队在工厂旁审核产品样品",
        "caption": "采购团队与国际买家共同核对产品方案",
    },
    "asset_product_development": {
        "name": "产品开发与打样",
        "alt_text": "买家与采购专员审核无品牌产品原型和材料",
        "caption": "从需求、材料和包装到可确认的生产样品",
    },
    "asset_quality_inspection": {
        "name": "验货与质量控制",
        "alt_text": "质检人员在生产线上测量无品牌零部件",
        "caption": "按照已确认的规格和检查点记录质量证据",
    },
    "asset_shipping_consolidation": {
        "name": "集货与国际物流",
        "alt_text": "采购协调人员在国际发货前核对纸箱",
        "caption": "统一核对包装、装箱数据、集货和交付节点",
    },
    "asset_dropshipping_fulfillment": {
        "name": "一件代发与订单履约",
        "alt_text": "履约团队在整洁仓库中扫描无品牌包裹",
        "caption": "按订单完成拣货、包装和发运协调",
    },
    "asset_product_photography": {
        "name": "产品摄影与视频",
        "alt_text": "创意团队在专业影棚拍摄通用产品",
        "caption": "按照已确认的方案制作产品图片和视频",
    },
    "asset_packaging_design": {
        "name": "包装与平面设计",
        "alt_text": "设计师与采购专员比较通用包装样品",
        "caption": "生产前统一确认设计稿、材料和包装结构",
    },
    "asset_warehousing_kitting": {
        "name": "仓储、换标与组合包装",
        "alt_text": "仓库团队把通用产品组合成统一零售套装",
        "caption": "集货、清点、重包装并为下一销售渠道备货",
    },
    "asset_factory_audit": {
        "name": "工厂与供应商审核",
        "alt_text": "采购审核人员与工厂负责人检查生产线",
        "caption": "在依赖供应商前核实能力和流程证据",
    },
}


OFFERING_CHINESE = {
    "offering_supplier_sourcing": {
        "name": "采购寻源与下单协调",
        "kicker": "寻找新供应商",
        "summary": "把产品需求、目标成本和市场要求整理成可比较的供应商候选清单。",
        "introduction": "先把需求结构化，再比较供应商匹配度、规格、商务条件和可核实证据，由客户确认下一步。",
        "benefits": _lines("结构化采购需求", "可比较的供应商与报价信息", "MOQ、交期和规格核对", "决策历史保留在 Odoo 中"),
        "process": _lines("确认产品、数量、市场和目标", "建立并筛选供应商清单", "比较证据、样品和商务条件", "确认供应商和采购路径"),
    },
    "offering_supplier_management": {
        "name": "现有供应商管理",
        "kicker": "管理已有供应商",
        "summary": "通过一个有责任人的本地流程，协调现有工厂、订单、质量问题和交付节点。",
        "introduction": "保留客户已有供应商，同时增加本地规格确认、跟进、质量证据和交付异常管理。",
        "benefits": _lines("统一的工作需求记录", "供应商跟进与问题追踪", "验货证据与整改行动", "可复用的订单与供应商历史"),
        "process": _lines("导入现有供应商和订单背景", "确认责任人与检查节点", "跟踪样品、生产和质量问题", "复盘交付与供应商表现"),
    },
    "offering_product_development": {
        "name": "产品开发",
        "kicker": "从想法到确认样品",
        "summary": "在生产前协调规格、材料、原型和版本修改。",
        "introduction": "可生产的产品需求不只是参考图片，还需要明确用途、尺寸、材料、包装、目标市场和验收标准。",
        "benefits": _lines("可用于生产的需求方案", "材料与结构选项", "样品版本和反馈历史", "量产前的确认关口"),
        "process": _lines("明确用途和目标规格", "评估可行材料与结构", "制作、审核并修改样品", "冻结已确认的生产标准"),
    },
    "offering_private_label": {
        "name": "自有品牌与产品定制",
        "kicker": "建立一致的品牌产品",
        "summary": "把产品修改、Logo、包装、标签和市场要求统一到一个受控方案。",
        "introduction": "品牌要求会同时影响产品、包装、标签、成本和交期，应在量产前把这些依赖关系确认清楚。",
        "benefits": _lines("产品与包装需求统一管理", "设计稿与标签检查节点", "生产前确认实物样品", "可供复购使用的产品规格"),
        "process": _lines("确认品牌和目标市场要求", "定义产品与包装修改", "审核设计稿和实物样品", "确认最终生产资料包"),
    },
    "offering_quality_inspection": {
        "name": "验货与质量管理",
        "kicker": "依据证据做决定",
        "summary": "定义检查节点，并保留测量、图片、问题和整改记录。",
        "introduction": "只有验收标准明确，验货才有意义。系统把确认样品与规格关联到检查发现和放行决定。",
        "benefits": _lines("产前和出货前检查节点", "测量与图片证据", "问题等级与整改行动", "由人工控制最终放行"),
        "process": _lines("确认验货标准", "选择检查时间和抽样方法", "记录发现和不合格项", "决定放行、返工或暂停发货"),
    },
    "offering_shipping": {
        "name": "集货与国际物流",
        "kicker": "一次受控的交付衔接",
        "summary": "协调包装、标签、多供应商集货和国际运输节点。",
        "introduction": "围绕已核实的箱规数据、约定贸易条款和可见交接节点组织发货，运费报价与清关决定保持明确。",
        "benefits": _lines("多供应商集货方案", "包装与箱规数据核对", "贸易条款与交接节点可见", "运输异常跟进"),
        "process": _lines("确认货物数据和交付条款", "协调供应商备货与提货", "集货并核对整票货物", "跟踪交接与送达节点"),
    },
    "solution_importers": {
        "name": "进口商与批发商",
        "kicker": "重复采购",
        "summary": "建立可比较的产品、供应商、价格和交付记录，让每次采购都能复用经验。",
        "introduction": "面对多品类和重复订单，持续积累的运营记录与第一次找到供应商同样重要。",
        "benefits": _lines("可复用的产品与供应商事实", "MOQ 与混合订单规划", "多供应商集货", "复购使用的表现历史"),
        "process": _lines("定义品类和采购目标", "建立受控产品候选清单", "确认供应商与样品", "利用历史记录持续复购"),
    },
    "solution_online_sellers": {
        "name": "电商与平台卖家",
        "kicker": "验证后再扩大",
        "summary": "从参考产品推进到可测试的采购需求、样品和小批量决策。",
        "introduction": "速度很重要，但缺少依据的产品宣传和不清楚的规格会带来高额退货，应在扩大库存前先核实产品事实。",
        "benefits": _lines("可从参考图片开始", "样品与试单流程", "可用于内容制作的真实产品信息", "明确的放量检查点"),
        "process": _lines("提供目标产品或参考资料", "确认最低可行规格", "测试样品或小批量订单", "审核证据后再扩大采购"),
    },
    "solution_private_brands": {
        "name": "自有品牌",
        "kicker": "形成差异化产品",
        "summary": "把产品、包装和质量标准作为可持续更新的品牌资产管理。",
        "introduction": "让修改记录、设计稿、样品和验收标准保持关联，以便稳定复制已确认的产品。",
        "benefits": _lines("统一受控的品牌规格", "样品和设计稿确认关口", "质量标准关联确认样品", "复购一致性"),
        "process": _lines("把品牌概念转成产品要求", "开发并比较可行方案", "确认产品与包装样品", "按已确认标准控制生产"),
    },
    "solution_enterprise": {
        "name": "企业与项目采购",
        "kicker": "更多控制，更清晰的责任",
        "summary": "协调多方需求、供应商证据、质量关口和交付节点。",
        "introduction": "复杂采购需要明确责任、审批关口和核实证据。Odoo 将客户、报价、采购和交付历史保持关联。",
        "benefits": _lines("结构化的多方需求", "供应商与合规证据", "正式质量与放行节点", "可追溯的商务和交付历史"),
        "process": _lines("统一相关方和验收标准", "筛选供应商与商务方案", "控制样品、质量和审批", "管理交付与最终验收"),
    },
    "plan_basic": {
        "name": "基础采购服务",
        "kicker": "启动并验证",
        "summary": "适合需要寻找供应商、比较报价并控制首单的买家。",
        "introduction": "从明确需求开始，只为采购方案中已确认的服务付费。",
        "benefits": _lines("结构化采购需求", "供应商清单与报价比较", "样品与首单协调", "可选验货与物流支持"),
        "price_label": "根据工作范围报价",
    },
    "plan_managed": {
        "name": "持续采购管理",
        "kicker": "运营并扩大",
        "summary": "适合需要持续供应商、质量、集货和交付协调的复购买家。",
        "introduction": "面向现有或新开发供应商的持续运营服务，在开始前明确责任和检查节点。",
        "benefits": _lines("现有或新供应商管理", "订单与生产跟进", "质量证据与问题处理", "集货与交付协调"),
        "price_label": "服务方案单独报价",
        "badge": "推荐给重复采购客户",
    },
    "offering_dropshipping_fulfillment": {
        "name": "一件代发与订单履约",
        "kicker": "从供应商直达终端客户",
        "summary": "协调采购、库存、拣货、包装和包裹发运，同时保留订单级可见性。",
        "introduction": "只有产品信息、库存、包装规则和目的地数据保持关联，一件代发流程才能稳定运行；接单前先确认实际运营范围。",
        "benefits": _lines("供应商与 SKU 建档", "订单级拣货与包装", "定制卡片与包装规则", "物流跟踪与异常处理"),
        "process": _lines("确认产品、渠道和目标国家", "核实供应商、库存和包装规则", "接收并处理已确认订单", "回传物流单号并跟进异常"),
    },
    "offering_product_photography_video": {
        "name": "产品摄影与视频",
        "kicker": "根据真实样品制作内容",
        "summary": "根据已确认样品、拍摄清单和渠道要求制作产品图片及短视频。",
        "introduction": "拍摄前确认产品样品、宣传点和目标销售渠道，确保视觉内容与客户实际供应的产品一致。",
        "benefits": _lines("产品图与场景图拍摄", "产品演示短视频", "适配渠道的画幅与文件", "可重复使用的已审核内容资产"),
        "process": _lines("确认样品与内容目标", "制定拍摄清单和视觉参考", "制作并审核内容", "确认并交付选定文件"),
    },
    "offering_packaging_graphic_design": {
        "name": "包装与平面设计",
        "kicker": "让设计稿真正用于生产",
        "summary": "把包装结构、设计稿、标签和印刷文件关联到已确认的产品规格。",
        "introduction": "结合实际尺寸、材料、印刷工艺和市场要求审核设计，使确认文件能够进入打样。",
        "benefits": _lines("包装结构与材料方案", "Logo、标签与设计稿协调", "生产文件检查节点", "量产前确认实物样品"),
        "process": _lines("确认产品尺寸和包装目标", "准备结构与视觉方向", "审核设计稿和实物样品", "向生产释放已确认文件"),
    },
    "offering_warehousing_kitting": {
        "name": "仓储、换标与组合包装",
        "kicker": "把多个输入整理成一个交付结果",
        "summary": "在下一次发货前完成收货、清点、存储、换标、重包装或产品组合。",
        "introduction": "每项操作要求都关联到具体 SKU、数量和目的地，避免集货过程产生新的质量或库存不确定性。",
        "benefits": _lines("入库数量与状态记录", "短期仓储与集货", "换标、重包装和套装组合", "最终数量与箱规核对"),
        "process": _lines("确认入库方案和操作规则", "接收并记录已确认货物", "执行重包装或组合工作", "核对并放行出库货物"),
    },
    "offering_supplier_factory_audit": {
        "name": "工厂与供应商审核",
        "kicker": "承诺前先核实",
        "summary": "围绕实际采购需求审核供应商身份、场地、生产能力和流程证据。",
        "introduction": "审核围绕采购决策确定范围，记录可观察证据和未解决风险，不把一次现场检查包装成没有依据的保证。",
        "benefits": _lines("供应商身份与现场证据", "相关设备和流程审核", "产能与质量控制观察", "未解决风险与后续行动"),
        "process": _lines("定义决策目标与审核范围", "收集供应商和场地证据", "审核相关生产过程", "报告发现、风险和下一步"),
    },
    "offering_marketplace_prep": {
        "name": "电商平台与 FBA 备货",
        "kicker": "为渠道交接准备库存",
        "summary": "协调验货、单品标签、套装准备、箱规数据和平台库存发运交接。",
        "introduction": "平台要求会随国家、品类和账号变化。客户确认当前平台规则，我们按照约定清单处理实物货物。",
        "benefits": _lines("单品与外箱处理清单", "标签和套装组合", "数量与包装核对", "发运交接记录"),
        "process": _lines("确认目的地与当前平台规则", "制定 SKU 级操作清单", "验货、贴标、组合和包装", "核对箱规数据并放行发货"),
    },
    "solution_dropshipping_brands": {
        "name": "一件代发业务",
        "kicker": "先验证完整运营链路",
        "summary": "围绕受控产品范围关联供应商、库存、包装、订单数据和包裹发运。",
        "introduction": "从少量产品和目的地开始，验证订单流程；了解库存准确性、操作质量和交付异常后再扩大。",
        "benefits": _lines("受控的供应商与 SKU 建档", "明确的包装与履约规则", "订单和物流可见", "可衡量的扩张检查点"),
        "process": _lines("选择首批产品和市场范围", "核实供应商、库存和包装", "运行受控履约测试", "复盘异常后再扩大"),
    },
}


PAGE_CHINESE = {
    "page_about_us": {
        "name": "我们的采购方法",
        "kicker": "关于 LightLink",
        "summary": "在买家需求与可追责的供应商执行之间建立务实连接。",
        "body_html": "<h2>先明确需求，再讨论供应商承诺</h2><p>LightLink 围绕产品、用途、目标市场、数量、质量标准和交付要求组织采购需求，让买家与供应商使用同一份工作依据。</p><h2>证据始终关联项目</h2><p>供应商方案、报价、样品、验货结果、审批和交付节点保留在 Odoo 中。AI 可以整理和翻译信息，商业与质量决定仍由人员确认。</p><h2>为重复采购而设计</h2><p>已确认的产品事实、供应商历史和运营决定可在复购与扩品时继续使用。</p>",
    },
    "page_payment_information": {
        "name": "付款信息",
        "kicker": "安全的商务交接",
        "summary": "依据已批准的报价单或发票，确认范围、收款主体、币种、费用和付款节点。",
        "body_html": "<h2>只使用已批准项目发出的付款信息</h2><p>付款方式取决于服务范围、供应商安排、目的地和交易金额。付款前，项目负责人会提供正式报价单或发票。</p><h2>汇款前核实任何变更</h2><p>不要依赖公开网页、转发消息或异常邮件中的账户信息。收款人或银行信息变化时，请通过第二个已验证渠道确认。</p><h2>保留完整付款记录</h2><p>关联报价单、发票、项目和付款节点，便于财务与运营在 Odoo 中核对。</p>",
    },
    "page_founder": {
        "name": "创始人与管理团队",
        "kicker": "责任始于明确的负责人",
        "summary": "身份、履历和媒体资料核实后，可在这里维护创始人介绍、运营原则与已授权内容。",
        "body_html": "<h2>公司为什么存在</h2><p>在这里说明创始人真正要解决的业务问题、与服务相关的经验，以及困难采购决策采用的原则。</p><h2>客户可以要求我们承担什么责任</h2><p>只发布团队确实能交付的责任：清晰需求、可见检查点、基于证据的建议和未解决风险的及时升级。</p><h2>个人资料发布前</h2><p>请在 Odoo 中添加已核实的姓名、履历、获准使用的肖像和公开职业链接。</p>",
    },
    "page_resources": {
        "name": "中国采购资源",
        "kicker": "实用学习资料库",
        "summary": "通过指南和项目经验，学习准备需求、比较供应商并控制采购风险。",
        "body_html": "<h2>按照采购流程的顺序学习</h2><p>从产品和市场需求开始，再学习寻找供应商、比较报价、打样、质量控制、商务条款和交付计划。</p><p>单篇文章继续使用 Odoo 博客发布；结构化指南负责把文章组织成可重复的学习路径。</p>",
    },
    "page_importing_from_china": {
        "name": "从中国进口：实操指南",
        "kicker": "从需求到交付",
        "summary": "围绕产品定义、供应验证、质量批准和交付计划组织的学习路径。",
        "body_html": "<h2>1. 明确商业目标</h2><p>明确目标客户、产品用途、采购数量、利润要求、目的市场和上市时间。</p><h2>2. 把想法转成可报价需求</h2><p>记录尺寸、材料、功能、包装、标签、合规要求和不可变更项。</p><h2>3. 使用一致证据比较供应商</h2><p>确认范围、起订量、交期、样品条件、付款条款和价格包含项后再比较。</p><h2>4. 批准样品和质量检查点</h2><p>以已批准样品和验收标准作为生产与验货决定的依据。</p><h2>5. 规划商务与物流交接</h2><p>发运前确认箱规、贸易条款、文件、运输路线和每次交接的责任。</p>",
    },
    "page_sourcing_agent_guide": {
        "name": "采购代理选择指南",
        "kicker": "选择可追责的执行伙伴",
        "summary": "从范围、证据、利益关系、沟通、控制和项目记录评估采购伙伴。",
        "body_html": "<h2>明确代理负责什么</h2><p>寻找供应商、供应商管理、产品开发、验货、集货和物流属于不同范围，需要明确代理准备哪些决定、哪些决定由买家保留。</p><h2>询问信息如何核实</h2><p>合格的伙伴会区分供应商说法与观察证据，并记录未解决风险。</p><h2>理解费用和激励关系</h2><p>确认服务费、供应商佣金、第三方成本及可能影响建议的商业关系。</p><h2>检查工作记录</h2><p>了解需求、报价、样品、验货、批准和交付异常如何记录并交付给你。</p>",
    },
}


CHAPTER_CHINESE = {
    "guide_import_budget": ("规划落地成本预算", "联系供应商前估算产品、样品、检测、运费、税费和风险预留。"),
    "guide_import_product": ("选择可行的产品和市场", "检查需求、利润、限制、差异化和测试市场所需数量。"),
    "guide_import_research": ("把调研转成产品需求", "把参考产品和客户需求整理成供应商可一致报价的规格。"),
    "guide_import_online_suppliers": ("通过线上渠道寻找供应商", "建立候选清单，不把平台标识或供应商陈述当成最终证据。"),
    "guide_import_offline_suppliers": ("利用展会和产业带", "围绕相关产业集群、明确问题和需要收集的证据安排拜访。"),
    "guide_import_verify": ("核实供应商能力", "检查主体、产能、质量控制、沟通和具体产品范围的匹配度。"),
    "guide_import_quote": ("取得可比较的报价", "比较前统一规格、起订量、模具、包装、贸易条款和排除项。"),
    "guide_import_select": ("用一致标准选择供应商", "综合商业匹配、技术能力、响应、证据与风险，而不是只看价格。"),
    "guide_import_confirm": ("确认样品和订单细节", "锁定样品、验收标准、文件、付款节点和变更流程。"),
    "guide_import_shipping": ("准备验货与运输", "规划验货时间、箱规、运输方案、报关文件和交付节点。"),
    "guide_agent_scope": ("采购伙伴应负责什么？", "把资源介绍、采购支持和完整项目管理拆成明确交付物。"),
    "guide_agent_services": ("应该包含哪些服务？", "根据实际缺口匹配采购、开发、跟进、验货、集货和运输。"),
    "guide_agent_fit": ("什么时候使用代理更有价值？", "评估产品复杂度、供应商数量、本地跟进需求和协调失败成本。"),
    "guide_agent_fees": ("如何审查费用和激励？", "明确服务范围、第三方成本、佣金和费用变化条件。"),
    "guide_agent_selection": ("如何选择可追责的伙伴？", "检查品类匹配、证据、沟通节奏、风险升级和最终项目记录。"),
}


PAYMENT_CHINESE = {
    "payment_method_bank_transfer_draft": {"name": "银行转账", "summary": "核实收款人与银行信息后，用于已批准的报价单或发票。", "instructions": "<p>请替换为已核实的公司收款人、币种、银行和附言要求。敏感付款信息应尽量保留在正式发票中。</p>", "fee_note": "付款前确认银行及中转行费用。", "verification_notice": "财务完成收款人和审批流程核实前不要发布。"},
    "payment_method_online_link_draft": {"name": "已批准的在线付款链接", "summary": "只使用与已批准报价单或发票关联的付款链接。", "instructions": "<p>请替换为实际服务商、支持币种、交易限制和对账流程。</p>", "fee_note": "核实服务商和当前费率后再发布费用。", "verification_notice": "付款前确认域名、收款人和发票编号。"},
    "payment_method_trade_protection_draft": {"name": "平台交易保障", "summary": "仅在项目已确认交易方式和适用保障条款时使用。", "instructions": "<p>请替换为实际平台流程、交易限制和服务费承担方式。</p>", "fee_note": "保障范围和费用以平台当前条款为准。", "verification_notice": "不要暗示超过已批准订单书面条款的保障。"},
}


FOOTER_COLUMN_CHINESE = {
    "footer_column_main": "主菜单", "footer_column_services": "我们的服务", "footer_column_solutions": "解决方案",
    "footer_column_contact_draft": "联系我们", "footer_column_hours_draft": "工作时间",
}


FOOTER_LINK_CHINESE = {
    "footer_link_home": "首页", "footer_link_products": "产品", "footer_link_about": "关于我们", "footer_link_payment": "付款信息", "footer_link_guide": "进口指南", "footer_link_blog": "博客",
    "footer_link_sourcing": "采购代理", "footer_link_development": "产品开发", "footer_link_inspection": "验货与质量控制", "footer_link_shipping": "集货与运输", "footer_link_more_services": "查看全部服务",
    "footer_link_private_brands": "自有品牌", "footer_link_online_sellers": "在线卖家", "footer_link_dropshipping": "一件代发业务", "footer_link_quality": "质量控制", "footer_link_agent_guide": "采购代理指南",
}


MENU_CHINESE = {
    "menu_sourcing_home": "首页",
    "menu_sourcing_services": "服务",
    "menu_sourcing_solutions": "解决方案",
    "menu_sourcing_products": "产品",
    "menu_sourcing_pricing": "服务方案",
    "menu_sourcing_insights": "采购知识",
    "menu_sourcing_blog": "博客",
    "menu_sourcing_import_guide": "从中国进口指南",
    "menu_sourcing_agent_guide": "采购代理指南",
    "menu_sourcing_about": "关于我们",
    "menu_sourcing_payment": "付款信息",
    "menu_sourcing_about_us": "关于我们",
    "menu_sourcing_founder": "创始人与管理团队",
    "menu_sourcing_quote": "提交采购需求",
}


def apply_sourcing_translations(env):
    website = env.ref("lightlink_sourcing_website.website_global_sourcing", raise_if_not_found=False)
    if not website:
        return False

    chinese = env["res.lang"].search([("code", "=", "zh_CN"), ("active", "=", True)], limit=1)
    english = env["res.lang"].search([("code", "=", "en_US"), ("active", "=", True)], limit=1)
    if english and chinese:
        website.write({"language_ids": [(6, 0, (english | chinese).ids)]})

    for xmlid, values in ASSET_ENGLISH.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="en_US").write(values)

    if not chinese:
        return True

    website.with_context(lang="zh_CN").write({
        "sourcing_brand_name": "LightLink 全球采购服务",
        "sourcing_tagline": "中国采购、产品开发与交付过程管理",
    })
    for xmlid, values in ASSET_CHINESE.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="zh_CN").write(values)
    for xmlid, values in OFFERING_CHINESE.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="zh_CN").write(values)
    for xmlid, values in PAGE_CHINESE.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="zh_CN").write(values)
    for xmlid, values in CHAPTER_CHINESE.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="zh_CN").write({
                "name": values[0], "summary": values[1],
                "reading_time": "%s 分钟阅读" % record.reading_time.split(" ")[0],
            })
    for xmlid, values in PAYMENT_CHINESE.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="zh_CN").write(values)
    for xmlid, name in FOOTER_COLUMN_CHINESE.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="zh_CN").write({"name": name})
    for xmlid, name in FOOTER_LINK_CHINESE.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="zh_CN").write({"name": name})
    for xmlid, name in MENU_CHINESE.items():
        record = env.ref("lightlink_sourcing_website.%s" % xmlid, raise_if_not_found=False)
        if record:
            record.with_context(lang="zh_CN").write({"name": name})

    project = env["psc.publishing.project"].search([
        ("website_id", "=", website.id),
        ("website_inquiry_enabled", "=", True),
    ], order="create_date desc, id desc", limit=1)
    if project:
        project.with_context(lang="zh_CN").write({
            "website_public_name": "用清晰方案和可追责执行完成中国采购。",
            "website_public_summary": "从寻找供应商、产品开发到质量控制、集货和交付协调。",
        })
    return True
