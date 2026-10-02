# LightLink Shopify 多站点验收合同

本文件是功能验收合同。任何项目只有同时具备可见入口、可操作交互、持久化数据、后台效果、成功/失败反馈和刷新后结果，才可标记为完成。

## 功能矩阵

| 编号 | 功能 | 实现入口 | 自动测试 | 产品验收 |
|---|---|---|---|---|
| S01 | 多店运营总览、店铺健康、商品/订单/任务指标 | Shopify 多站点 / 运营总览 | `test_dashboard_metrics` | 待执行 |
| S02 | 店铺、公司、币种、价格表、仓库、销售团队和同步开关 | 店铺管理 | `test_store_constraints` | 待执行 |
| S03 | OAuth连接、回调HMAC校验、连接测试、暂停与恢复 | 店铺表单 | `test_oauth_hmac`、`test_store_state` | 需要真实 Shopify 店铺 |
| S04 | 一个Odoo产品对应多个店铺商品，店铺字段相互隔离 | 产品 / Shopify渠道 | `test_channel_product_unique_per_store` | 待执行 |
| S05 | 每店独立标题、描述、SEO、Handle、价格、状态和图片排序 | 渠道商品表单 | `test_channel_payload` | 待执行 |
| S06 | 产品发布预览、必填检查、确认、后台执行和刷新后结果 | 产品发布预览 | `test_publish_preview_and_enqueue` | 需要真实 Shopify 店铺 |
| S07 | 批量选择产品和店铺，生成独立且幂等的任务 | 产品列表 / 发布到 Shopify | `test_batch_publish_idempotency` | 待执行 |
| S08 | Odoo分类到各店Collection映射、图片、同步和异常 | 分类与集合映射 | `test_collection_mapping` | 需要真实 Shopify 店铺 |
| S09 | Shopify Location到Odoo库位、安全库存和可售库存 | 库存与仓库映射 | `test_available_quantity` | 待执行 |
| S10 | 价格表驱动的每店价格与币种校验 | 渠道商品 | `test_pricelist_currency_validation` | 待执行 |
| S11 | Shopify订单幂等导入、客户匹配、来源店铺和订单行映射 | 订单与履约 | `test_order_import_idempotency` | 需要真实 Shopify 店铺 |
| S12 | Odoo完成发货后把物流公司和单号回传Shopify | 库存调拨 / Shopify履约任务 | `test_picking_enqueues_fulfillment` | 需要真实 Shopify 店铺 |
| S13 | Shopify采购需求进入CRM，保存来源、UTM、同意记录和提交结果 | 公开询盘接口 / CRM | `test_inquiry_creates_lead` | 待执行 |
| S14 | Webhook HMAC、事件去重、店铺隔离和快速入队 | Shopify Webhook接口 | `test_webhook_hmac_and_deduplication` | 需要真实 Shopify 店铺 |
| S15 | 后台任务、错误隔离、指数退避、人工重试和审计日志 | 发布任务 / 同步异常 | `test_job_retry_and_isolation` | 待执行 |
| S16 | 按公司和角色隔离，凭证仅系统管理员可见 | 用户权限 / 店铺表单 | `test_company_rules_and_secret_visibility` | 待执行 |
| S17 | 产品工作台显示渠道状态并可进入多店管理 | 产品工作台 | `test_workspace_channel_summary` | 待执行 |
| S18 | Odoo不可用时Shopify前端不依赖Odoo页面运行 | 架构约束 | 静态依赖检查 | 需要真实 Shopify 店铺 |
| S19 | 新增第二家店不修改代码，且单店失败不阻塞其他店 | 店铺管理 / 任务队列 | `test_store_failure_isolation` | 需要第二家 Shopify 店铺 |
| S20 | 删除/下架/批量操作具有预览、确认和历史记录保护 | 发布预览 / 归档 | `test_archiving_preserves_orders` | 待执行 |

## 完成规则

- 自动测试、模块安装、升级、权限、真实浏览器操作与外部 Shopify 回路全部通过后，方可把相关项目标为“已实现并验证”。
- 没有 Shopify OAuth Client ID、Client Secret 和测试店铺时，外部回路保持“阻塞”，不得伪报完成。
- Shopify主题、首页、导航、博客和普通页面不由本模块渲染，确保Odoo升级不影响网站前端。
- 订单、Webhook和库存写入必须幂等；一家店的失败不得回滚其他店任务。
