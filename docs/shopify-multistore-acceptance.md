# LightLink Shopify 多站点验收合同

本文件是功能验收合同。任何项目只有同时具备可见入口、可操作交互、持久化数据、后台效果、成功/失败反馈和刷新后结果，才可标记为完成。

## 功能矩阵

| 编号 | 功能 | 实现入口 | 自动测试 | 产品验收 |
|---|---|---|---|---|
| S01 | 多店运营总览、店铺健康、商品/订单/任务指标 | Shopify 多站点 / 运营总览 | `test_dashboard_metrics` | 部分验证：生产API与资源通过；管理员UI待验 |
| S02 | 店铺、公司、币种、价格表、仓库、销售团队和同步开关 | 店铺管理 | `test_store_constraints` | 部分验证：生产表单解析通过；管理员UI待验 |
| S03 | OAuth连接、回调HMAC校验、连接测试、暂停与恢复 | 店铺表单 | `test_oauth_hmac`、`test_store_state`、`test_store_required_scopes` | 阻塞：需要真实 Shopify 店铺与应用凭证 |
| S04 | 一个Odoo产品对应多个店铺商品，店铺字段相互隔离 | 产品 / Shopify渠道 | `test_channel_product_unique_per_store` | 部分验证：生产模型与视图通过；真实多店待验 |
| S05 | 每店独立标题、描述、SEO、Handle、价格、状态和图片排序 | 渠道商品表单 | `test_channel_payload` | 部分验证：生产模型与视图通过；远端结果待验 |
| S06 | 产品发布预览、必填检查、确认、后台执行和刷新后结果 | 产品发布预览 | `test_publish_preview_and_enqueue` | 阻塞：需要真实 Shopify 店铺 |
| S07 | 批量选择产品和店铺，生成独立且幂等的任务 | 产品列表 / 发布到 Shopify | `test_batch_publish_idempotency` | 部分验证：生产列表操作已绑定；管理员交互待验 |
| S08 | Odoo分类到各店Collection映射、图片、同步和异常 | 分类与集合映射 | `test_collection_mapping` | 阻塞：需要真实 Shopify 店铺 |
| S09 | Shopify Location到Odoo库位、安全库存和可售库存 | 库存与仓库映射 | `test_available_quantity` | 阻塞：需要真实 Shopify Location |
| S10 | 价格表驱动的每店价格与币种校验 | 渠道商品 | `test_pricelist_currency_validation` | 部分验证：生产模型与视图通过；真实价格待验 |
| S11 | Shopify订单幂等导入、客户匹配、来源店铺和订单行映射 | 订单与履约 | `test_order_import_idempotency`、`test_order_sku_match_prefers_store_mapping`、`test_order_nested_connections_are_fully_loaded` | 阻塞：需要真实 Shopify 订单 |
| S12 | Odoo完成发货后把本次实际发货数量、物流公司和单号回传Shopify | 库存调拨 / Shopify履约任务 | `test_picking_enqueues_fulfillment`、`test_partial_fulfillment_allocates_only_done_quantity` | 阻塞：需要真实 Shopify 订单与发货 |
| S13 | Shopify采购需求进入CRM，保存来源、UTM、同意记录和提交结果 | 公开询盘接口 / CRM | `test_inquiry_creates_lead` | 部分验证：生产无效令牌安全返回404；真实来源待验 |
| S14 | Webhook HMAC、事件去重、店铺隔离和快速入队 | Shopify Webhook接口 | `test_webhook_hmac_and_deduplication`、`test_webhook_event_deduplication` | 阻塞：需要真实 Shopify Webhook |
| S15 | 后台任务、错误隔离、指数退避、人工重试和审计日志 | 发布任务 / 同步异常 | `test_job_retry_and_isolation` | 部分验证：生产任务视图和2个定时任务通过；真实失败重试待验 |
| S16 | 按公司和角色隔离，凭证仅系统管理员可见 | 用户权限 / 店铺表单 | `test_company_rules_and_secret_visibility` | 部分验证：生产3角色与10条规则通过；角色实操待验 |
| S17 | 产品工作台显示渠道状态并可进入多店管理 | 产品工作台 | `test_workspace_channel_summary` | 部分验证：生产工作台API已返回Shopify字段；管理员UI待验 |
| S18 | Odoo不可用时Shopify前端不依赖Odoo页面运行 | 架构约束 | `test_shopify_frontend_independence` | 阻塞：需要真实 Shopify 前端断连验收 |
| S19 | 新增第二家店不修改代码，且单店失败不阻塞其他店 | 店铺管理 / 任务队列 | `test_store_failure_isolation` | 阻塞：需要第二家 Shopify 店铺 |
| S20 | 删除/下架/批量操作具有预览、确认和历史记录保护 | 发布预览 / 归档 | `test_archiving_preserves_orders` | 部分验证：归档状态与历史保护已实现；远端下架待验 |

## 完成规则

- 自动测试、模块安装、升级、权限、真实浏览器操作与外部 Shopify 回路全部通过后，方可把相关项目标为“已实现并验证”。
- 没有 Shopify OAuth Client ID、Client Secret 和测试店铺时，外部回路保持“阻塞”，不得伪报完成。
- Shopify主题、首页、导航、博客和普通页面不由本模块渲染，确保Odoo升级不影响网站前端。
- 订单、Webhook和库存写入必须幂等；一家店的失败不得回滚其他店任务。

## 生产验收记录

### 2026-10-02 / 模块 19.0.1.2.1

- 已在生产升级并确认状态为 `installed`，已安装版本与最新版本均为 `19.0.1.2.1`。
- 生产加载 13 个 Shopify 模型、9 个窗口操作、2 个启用中的定时任务。
- 8 个核心模型的列表与表单视图均在生产完成解析；后台 CSS 和 JavaScript 调试资源均返回 200 且包含本模块资源。
- 产品列表的“发布到 Shopify”服务端操作已绑定 Shopify 运营角色；生产存在只读、运营、管理员 3 个角色和 10 条公司/角色规则。
- 产品工作台生产 API 返回 Shopify 渠道摘要字段；公开询盘与 Webhook 的无效令牌均安全返回 404。
- 已修正店铺优先的 SKU 映射、公司范围兜底、大订单行与 Location 分页、取消订单行、实际部分发货数量分配、履约权限校验、归档状态和受限凭证恢复读取。
- 发布预览中的“发布后同步库存”已贯通到后台任务；失败任务可原任务重试，重复的已完成内容不会产生新任务或错误停留在“排队中”。
- 发布、下架、图片删除、分类同步和任务重试按钮已按运营角色限制；只读角色只保留查看能力。
- 当前浏览器会话是门户用户，不能进入内部后台完成管理员可视化验收；生产升级也不会自动执行 `post_install` 测试。因此所有需要管理员真实操作或 Shopify 外部回路的项目保持“部分验证”或“阻塞”。
