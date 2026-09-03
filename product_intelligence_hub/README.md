# Product Intelligence Hub

## 1688 国内货源研判（第一期）

1. 产品机会进入“研判”阶段，在“货源研判”页确认检索关键词和参考图片。
2. 点击“打开1688关键词搜索”，登录1688并正常浏览、滚动加载商品。
3. 打开 LightLink 选品情报助手，点击“采集当前页并推送”。
4. 回到产品机会，对采购价、起订量、国内运费和预计交期进行复核，点击“推荐”选择货源。
5. 审批后创建 Odoo 产品，系统同时创建/更新供应商及产品采购价目。

联系方式只读取1688当前页面公开显示的内容；未公开的电话或联系人需要人工补充。

Odoo 19 module implementing the first stage of an OODA product-selection system.

The interface uses English as its source language and includes Simplified Chinese
translations in `i18n/zh_CN.po`. Odoo displays the language selected on each
user account.

## Included

- Product opportunity records and OODA kanban workflow.
- Commercial and market evidence fields.
- Configurable weighted scoring and recommendation thresholds.
- Multi-company access rules and manager approval permissions.
- Conversion of approved candidates into Odoo product templates.
- Extensible data-source model and disabled-by-default scheduled synchronization.

## Connector contract

Create a small connector module, inherit `product.intelligence.source`, and override
`_fetch_candidates()`. Return a list of candidate value dictionaries. Credentials
should be stored in `Settings > Technical > System Parameters`, referenced through
the source's `credential_parameter` field, and never committed to Git.

## Push ingestion (Shunxi and other browser tools)

Managers can open a data source and choose **Generate push credential**. The token
is displayed once and stored as a SHA-256 hash. Send batches of at most 1,000 items
to the displayed endpoint using either `Authorization: Bearer TOKEN` or the
`X-PIH-Token` header.

```json
{
  "items": [
    {
      "product_id": "ALIBABA-123",
      "product_title": "Solar street light",
      "product_url": "https://www.alibaba.com/product-detail/example.html",
      "main_image": "https://example.com/image.jpg",
      "category_name": "Outdoor Lighting",
      "supplier": "Example Supplier",
      "keywords": "solar light, street light",
      "min_price": 19.5,
      "moq": 10,
      "inquiries": 25,
      "transactions": 8,
      "rank": 12
    }
  ]
}
```

The endpoint also recognizes common Chinese export headers. Existing candidates
are updated by `(source, external_id)`; when no external ID is supplied, a stable
ID is derived from the product URL. Shunxi does not currently document a public
API, so its vendor or an approved browser-side sender must call this endpoint.

## Alibaba browser capture

The companion Chrome/Edge extension in `browser_extension/` reads only product
information visibly rendered on an Alibaba.com search result page and pushes it
to the configured source endpoint. Alibaba search pages do not expose reliable
7/30/180-day sales figures; those fields remain empty unless another authorized
provider supplies them.

Version 1.0.2 selects Alibaba's visible product image element before applying
the generic CDN fallback, preventing badges and placeholder images from being
stored as the product's main image.

## Installation

1. Place `product_intelligence_hub` in the repository's custom addons root.
2. Commit to a development branch and wait for the Odoo.sh build.
3. Update the Apps list, remove the default `Apps` filter if necessary, search for
   `Product Intelligence Hub`, and install it.
4. Assign users either the Product Intelligence User or Manager role.
