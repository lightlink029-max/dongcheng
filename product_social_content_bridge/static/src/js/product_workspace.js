/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";


export class ProductWorkspace extends Component {
    static template = "product_social_content_bridge.ProductWorkspace";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: false,
            products: [],
            options: { categories: [], attribute_values: [], tags: [] },
            total: 0,
            hasMore: false,
            filters: {
                keyword: "",
                category_id: "",
                attribute_value_id: "",
                tag_id: "",
                image_status: "all",
                active_status: "active",
            },
        });
        onWillStart(() => this.loadProducts());
    }

    async loadProducts(append = false) {
        if (this.state.loading) {
            return;
        }
        this.state.loading = true;
        try {
            const offset = append ? this.state.products.length : 0;
            const payload = await this.orm.call(
                "psc.business.hub",
                "get_product_workspace",
                [{ ...this.state.filters }, offset, 24]
            );
            if (append) {
                this.state.products.push(...payload.products);
            } else {
                this.state.products = payload.products;
            }
            this.state.options = payload.filters;
            this.state.total = payload.total;
            this.state.hasMore = payload.has_more;
        } catch (error) {
            this.notification.add("产品工作台加载失败，请刷新后重试。", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    applyFilters() {
        return this.loadProducts();
    }

    onSearchKeydown(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            this.applyFilters();
        }
    }

    clearFilters() {
        Object.assign(this.state.filters, {
            keyword: "",
            category_id: "",
            attribute_value_id: "",
            tag_id: "",
            image_status: "all",
            active_status: "active",
        });
        return this.loadProducts();
    }

    async newProduct() {
        const categoryId = Number(this.state.filters.category_id) || false;
        await this.action.doAction(
            "product_social_content_bridge.action_psc_product_quick_create",
            {
                additionalContext: {
                default_categ_id: categoryId,
                default_sale_ok: true,
                default_purchase_ok: true,
                },
            }
        );
    }

    async newCategory() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "新建产品分类",
            res_model: "product.category",
            views: [[false, "form"]],
            target: "new",
        });
        await this.loadProducts();
    }

    openProduct(product) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: product.name,
            res_model: "product.template",
            res_id: product.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openProductList() {
        return this.action.doAction("product.product_template_action_all");
    }

    manageCategories() {
        return this.action.doAction("product.product_category_action_form");
    }

    manageAttributes() {
        return this.action.doAction("product.attribute_action");
    }
}

registry.category("fields").add("psc_product_workspace", {
    component: ProductWorkspace,
    displayName: "LightLink 产品工作台",
    supportedTypes: ["char"],
    isEmpty: () => false,
});
