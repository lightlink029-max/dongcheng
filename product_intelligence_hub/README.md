# Product Intelligence Hub

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

## Installation

1. Place `product_intelligence_hub` in the repository's custom addons root.
2. Commit to a development branch and wait for the Odoo.sh build.
3. Update the Apps list, remove the default `Apps` filter if necessary, search for
   `Product Intelligence Hub`, and install it.
4. Assign users either the Product Intelligence User or Manager role.
