/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";


export class ShopifyDashboard extends Component {
    static template = "lightlink_shopify_multistore.ShopifyDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            summary: { stores: 0, connected: 0, products: 0, orders: 0, pending_jobs: 0, failed_jobs: 0 },
            stores: [],
        });
        onWillStart(() => this.refresh());
    }

    async refresh() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("ll.shopify.dashboard", "get_dashboard", []);
            this.state.summary = data.summary;
            this.state.stores = data.stores;
        } catch (error) {
            this.notification.add("Shopify 运营总览加载失败，请检查权限或稍后重试。", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    openStores() {
        return this.action.doAction("lightlink_shopify_multistore.action_shopify_store");
    }

    openStore(store) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: store.name,
            res_model: "ll.shopify.store",
            res_id: store.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openProducts() {
        return this.action.doAction("lightlink_shopify_multistore.action_shopify_channel_product");
    }

    openOrders() {
        return this.action.doAction("lightlink_shopify_multistore.action_shopify_order_binding");
    }

    openJobs(failed = false) {
        return this.action.doAction("lightlink_shopify_multistore.action_shopify_job", {
            additionalContext: failed ? { search_default_failed: 1, search_default_pending: 0 } : {},
        });
    }
}

registry.category("fields").add("ll_shopify_dashboard", {
    component: ShopifyDashboard,
    displayName: "Shopify 多站点运营总览",
    supportedTypes: ["char"],
    isEmpty: () => false,
});
