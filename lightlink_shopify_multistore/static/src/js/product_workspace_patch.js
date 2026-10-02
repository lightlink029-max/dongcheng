/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductWorkspace } from "@product_social_content_bridge/js/product_workspace";


patch(ProductWorkspace.prototype, {
    openShopifyDashboard() {
        return this.action.doAction("lightlink_shopify_multistore.action_shopify_dashboard");
    },

    publishVisibleProducts() {
        const productIds = this.state.products.map((product) => product.id);
        if (!productIds.length) {
            this.notification.add("当前没有可发布的产品。", { type: "warning" });
            return;
        }
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "发布到 Shopify",
            res_model: "ll.shopify.publish.wizard",
            views: [[false, "form"]],
            target: "new",
            context: { default_product_ids: [[6, 0, productIds]] },
        });
    },
});
