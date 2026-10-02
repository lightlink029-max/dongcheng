# LightLink Shopify 多站点配置手册

## 架构边界

- Shopify 负责主题、页面、导航、博客、结账和客户访问；这些页面不加载 Odoo 前端资源。
- Odoo 负责产品主数据、每店文案与价格、分类映射、库存、订单、履约、询盘、任务和异常。
- 一家店一个 `Shopify 店铺` 记录。新增第二家店只增加配置，不修改代码。
- 所有外部写入通过后台任务执行并记录；失败按店铺隔离。

## 首次连接

1. 在 Shopify Partner 或 Dev Dashboard 中创建应用，并为每家店完成应用安装授权。
2. 在 Odoo 的“Shopify 多站点 / 店铺管理”新建店铺，填写公司、价格表、币种、仓库和销售归属。
3. 系统管理员填写 Client ID 与 Client Secret。把店铺表单显示的 OAuth Callback URL 添加到 Shopify 应用允许的回调地址。
4. 点击“连接 Shopify”，授权后系统自动保存令牌、读取 Location 并注册订单与卸载 Webhook。
5. 在“库存与库位映射”检查每个 Shopify Location 对应的 Odoo 内部库位及安全库存。

应用至少需要以下 Admin API scopes：

`read_products, write_products, read_inventory, write_inventory, read_locations, read_orders, write_orders, read_fulfillments, write_fulfillments, read_merchant_managed_fulfillment_orders, write_merchant_managed_fulfillment_orders, read_customers`

若店铺的订单由第三方或 Shopify Fulfillment Service 管理，还需按实际履约类型申请对应的 assigned/third-party fulfillment order scopes，并在 Shopify 审核通过后重新授权店铺。

## 商品发布

1. 在 Odoo 产品列表选择产品，执行“发布到 Shopify”，或从产品工作台点击“发布当前结果到 Shopify”。
2. 选择目标店铺，查看产品 × 店铺预览；任何公司、币种、SKU 或连接错误都会阻止确认。
3. 确认后每个产品 × 店铺创建独立任务。每店标题、说明、SEO、Handle、价格、状态、分类集合和图片互不覆盖。
4. 在“发布任务与异常”查看结果并人工重试。相同内容重复点击不会产生重复任务。

为保证同步结果可核对，单个商品一次同步发布最多支持 100 个变体；超过时发布预检会明确阻止并提示拆分商品，不会静默漏传。

## 询盘接入 Shopify 主题

店铺表单会显示 Inquiry Endpoint URL。Shopify 主题向该 URL 发送 JSON：

```json
{
  "name": "Buyer Name",
  "email": "buyer@example.com",
  "phone": "+1 555 000 0000",
  "company_name": "Example Inc.",
  "message": "Need 500 units",
  "product_reference": "SKU-001",
  "page_url": "https://shop.example.com/products/example",
  "utm_source": "google",
  "utm_medium": "cpc",
  "utm_campaign": "brand",
  "consent": true,
  "website": ""
}
```

`website` 是蜜罐字段，必须保持空值。把 Shopify 正式域名逐行写入“允许来源”；接口只允许精确匹配的 HTTPS Origin，每个来源 IP 每小时最多提交 5 次。成功后会返回询盘编号，并在 Odoo 创建采购询盘和 CRM 线索。

## 上线前仍需的外部条件

- Shopify 应用 Client ID、Client Secret 与真实测试店铺。
- Shopify 对受保护客户数据与所需 API scopes 的授权。
- 真实店铺完成一次 OAuth、商品发布、库存、订单、发货回传、Webhook 和询盘全链路验收。
- 未完成上述外部回路时，验收合同中的相应项目保持“阻塞”，不能标记为已验证。
