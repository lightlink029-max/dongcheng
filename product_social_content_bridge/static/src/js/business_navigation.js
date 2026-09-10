/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class BusinessNavigation extends Component {
    static template = "product_social_content_bridge.BusinessNavigation";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            saving: false,
            editMode: false,
            canEdit: false,
            categories: [],
            draggedMenuId: null,
            status: "",
        });
        onWillStart(() => this.loadNavigation());
    }

    async loadNavigation() {
        this.state.loading = true;
        try {
            const payload = await this.orm.call(
                "psc.business.hub",
                "get_application_navigation",
                []
            );
            this.applyPayload(payload);
        } catch (error) {
            this.notification.add("功能导航加载失败，请刷新页面后重试。", { type: "danger" });
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    applyPayload(payload) {
        this.state.canEdit = Boolean(payload.can_edit);
        this.state.categories = payload.categories;
    }

    toggleEditMode() {
        if (!this.state.canEdit || this.state.saving) {
            return;
        }
        this.state.editMode = !this.state.editMode;
        this.state.status = this.state.editMode ? "整理模式：拖动图标即可自动保存" : "";
    }

    isDraggable(item) {
        return this.state.editMode && !this.state.saving && !item.locked;
    }

    getMenuIcon(item) {
        return this.menu.getMenu(item.id)?.webIconData || false;
    }

    findActionableMenu(menu) {
        if (!menu) {
            return false;
        }
        if (menu.actionID) {
            return menu;
        }
        for (const childId of menu.children || []) {
            const child = this.findActionableMenu(this.menu.getMenu(childId));
            if (child) {
                return child;
            }
        }
        return false;
    }

    async openMenu(item) {
        if (this.state.editMode) {
            return;
        }
        const target = this.findActionableMenu(this.menu.getMenu(item.id));
        if (!target) {
            this.notification.add(`“${item.name}”暂时没有可打开的功能入口。`, { type: "warning" });
            return;
        }
        await this.menu.selectMenu(target);
    }

    onDragStart(event) {
        if (!this.state.editMode) {
            event.preventDefault();
            return;
        }
        const menuId = Number(event.currentTarget.dataset.menuId);
        this.state.draggedMenuId = menuId;
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(menuId));
    }

    onDragEnd() {
        this.state.draggedMenuId = null;
    }

    allowDrop(event) {
        if (
            this.state.editMode
            && !this.state.saving
            && event.currentTarget.dataset.category !== "business"
        ) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
        }
    }

    async dropBefore(event) {
        event.preventDefault();
        event.stopPropagation();
        await this.moveDraggedItem(
            event.currentTarget.dataset.category,
            Number(event.currentTarget.dataset.beforeId)
        );
    }

    async dropAtEnd(event) {
        event.preventDefault();
        await this.moveDraggedItem(event.currentTarget.dataset.category, null);
    }

    async moveDraggedItem(targetCode, beforeId) {
        if (!this.state.editMode || this.state.saving || targetCode === "business") {
            return;
        }
        const menuId = this.state.draggedMenuId;
        if (menuId === beforeId) {
            this.state.draggedMenuId = null;
            return;
        }
        let sourceCategory;
        let sourceIndex = -1;
        for (const category of this.state.categories) {
            const index = category.items.findIndex((item) => item.id === menuId);
            if (index >= 0) {
                sourceCategory = category;
                sourceIndex = index;
                break;
            }
        }
        const targetCategory = this.state.categories.find((category) => category.code === targetCode);
        if (!sourceCategory || !targetCategory || sourceCategory.items[sourceIndex].locked) {
            return;
        }

        const [item] = sourceCategory.items.splice(sourceIndex, 1);
        const targetIndex = beforeId
            ? targetCategory.items.findIndex((candidate) => candidate.id === beforeId)
            : targetCategory.items.length;
        targetCategory.items.splice(targetIndex < 0 ? targetCategory.items.length : targetIndex, 0, item);
        this.state.draggedMenuId = null;
        await this.saveLayout();
    }

    serializeLayout() {
        return this.state.categories.map((category) => ({
            code: category.code,
            menu_ids: category.items.map((item) => item.id),
        }));
    }

    async saveLayout() {
        this.state.saving = true;
        this.state.status = "正在保存…";
        try {
            const payload = await this.orm.call(
                "psc.business.hub",
                "save_application_navigation",
                [this.serializeLayout()]
            );
            this.applyPayload(payload);
            await this.menu.reload();
            this.state.status = "已自动保存";
        } catch (error) {
            await this.loadNavigation();
            this.state.status = "保存失败";
            this.notification.add("功能分类保存失败，已恢复保存前的布局。", { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async resetLayout() {
        if (!this.state.canEdit || this.state.saving) {
            return;
        }
        this.state.saving = true;
        this.state.status = "正在恢复默认布局…";
        try {
            const payload = await this.orm.call(
                "psc.business.hub",
                "reset_application_navigation",
                []
            );
            this.applyPayload(payload);
            await this.menu.reload();
            this.state.status = "已恢复默认布局";
        } catch (error) {
            this.notification.add("恢复默认布局失败，请稍后重试。", { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }
}

registry.category("fields").add("psc_business_navigation", {
    component: BusinessNavigation,
    displayName: "LightLink 功能导航",
    supportedTypes: ["char"],
    isEmpty: () => false,
});
