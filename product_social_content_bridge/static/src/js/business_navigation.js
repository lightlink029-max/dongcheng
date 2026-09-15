/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";

const SIDEBAR_COLLAPSED_KEY = "psc_business_sidebar_collapsed";
const SIDEBAR_CATEGORY_KEY = "psc_business_sidebar_category";

function getMenuIcon(menuService, item) {
    if (item.web_icon) {
        const separator = item.web_icon.indexOf(",");
        if (separator > 0) {
            const moduleName = item.web_icon.slice(0, separator);
            const iconPath = item.web_icon.slice(separator + 1);
            return `/${moduleName}/${iconPath}`;
        }
    }

    const iconData = menuService.getMenu(item.id)?.webIconData;
    if (!iconData || typeof iconData !== "string") {
        return false;
    }
    if (iconData.startsWith("data:image") || iconData.startsWith("/")) {
        return iconData;
    }
    const compactIconData = iconData.replace(/\s/g, "");
    const mimeType = compactIconData.startsWith("P") ? "image/svg+xml" : "image/png";
    return `data:${mimeType};base64,${compactIconData}`;
}

function findActionableMenu(menuService, menu) {
    if (!menu) {
        return false;
    }
    if (menu.actionID) {
        return menu;
    }
    for (const childId of menu.children || []) {
        const child = findActionableMenu(menuService, menuService.getMenu(childId));
        if (child) {
            return child;
        }
    }
    return false;
}

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
            newCategoryName: "",
            status: "",
        });
        this.draggedMenuId = null;
        onWillStart(() => this.loadNavigation());
    }

    async loadNavigation() {
        this.state.loading = true;
        try {
            const payload = await this.orm.call(
                "psc.business.hub",
                "get_managed_sidebar_navigation",
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
        this.state.status = this.state.editMode
            ? "整理模式：可拖动，也可使用移动按钮，调整后自动保存"
            : "";
    }

    isDraggable(item) {
        return this.state.editMode && !this.state.saving && !item.locked;
    }

    getMenuIcon(item) {
        return getMenuIcon(this.menu, item);
    }

    async openMenu(item) {
        if (this.state.editMode) {
            return;
        }
        const target = findActionableMenu(this.menu, this.menu.getMenu(item.id));
        if (!target) {
            this.notification.add(`“${item.name}”暂时没有可打开的功能入口。`, { type: "warning" });
            return;
        }
        await this.menu.selectMenu(target);
    }

    onDragStart(event) {
        if (!this.state.editMode || this.state.saving) {
            event.preventDefault();
            return;
        }
        const menuId = Number(event.currentTarget.dataset.menuId);
        this.draggedMenuId = menuId;
        event.currentTarget.classList.add("is-dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(menuId));
    }

    onDragEnd(event) {
        event.currentTarget.classList.remove("is-dragging");
        this.draggedMenuId = null;
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
        const menuId = this.draggedMenuId;
        if (menuId === beforeId) {
            this.draggedMenuId = null;
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
        this.draggedMenuId = null;
        await this.saveLayout();
    }

    async moveCategory(categoryIndex, offset) {
        if (!this.state.editMode || this.state.saving) {
            return;
        }
        const targetIndex = categoryIndex + offset;
        if (targetIndex < 0 || targetIndex >= this.state.categories.length) {
            return;
        }
        const [category] = this.state.categories.splice(categoryIndex, 1);
        this.state.categories.splice(targetIndex, 0, category);
        await this.saveLayout();
    }

    async moveItemWithinCategory(category, itemIndex, offset) {
        if (!this.state.editMode || this.state.saving) {
            return;
        }
        const targetIndex = itemIndex + offset;
        if (targetIndex < 0 || targetIndex >= category.items.length) {
            return;
        }
        const [item] = category.items.splice(itemIndex, 1);
        category.items.splice(targetIndex, 0, item);
        await this.saveLayout();
    }

    async moveItemToCategory(sourceCategory, item, event) {
        const targetCode = event.currentTarget.value;
        if (!this.state.editMode || this.state.saving || !targetCode) {
            return;
        }
        const targetCategory = this.state.categories.find(
            (category) => category.code === targetCode
        );
        const sourceIndex = sourceCategory.items.findIndex(
            (candidate) => candidate.id === item.id
        );
        if (!targetCategory || targetCategory === sourceCategory || sourceIndex < 0) {
            event.currentTarget.value = "";
            return;
        }
        sourceCategory.items.splice(sourceIndex, 1);
        targetCategory.items.push(item);
        await this.saveLayout();
    }

    serializeLayout() {
        return this.state.categories.map((category) => ({
            code: category.code,
            name: category.name,
            menu_ids: category.items.map((item) => item.id),
        }));
    }

    async addCategory() {
        if (!this.state.editMode || this.state.saving) {
            return;
        }
        const name = this.state.newCategoryName.trim();
        if (!name) {
            this.notification.add("请先填写新模块名称。", { type: "warning" });
            return;
        }
        if (this.state.categories.length >= 20) {
            this.notification.add("最多可以保留 20 个导航模块。", { type: "warning" });
            return;
        }
        this.state.categories.push({
            code: `custom_${Date.now().toString(36)}`,
            name,
            icon: "fa-folder-o",
            custom: true,
            items: [],
        });
        this.state.newCategoryName = "";
        await this.saveLayout();
    }

    onNewCategoryKeydown(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            this.addCategory();
        }
    }

    async renameCategory(category) {
        category.name = category.name.trim();
        if (!category.name) {
            this.notification.add("模块名称不能为空。", { type: "warning" });
            await this.loadNavigation();
            return;
        }
        await this.saveLayout();
    }

    async removeCategory(category) {
        if (!category.custom) {
            return;
        }
        if (category.items.length) {
            this.notification.add("请先把模块内的入口移到其他模块，再删除。", { type: "warning" });
            return;
        }
        this.state.categories = this.state.categories.filter(
            (candidate) => candidate.code !== category.code
        );
        await this.saveLayout();
    }

    async saveLayout() {
        this.state.saving = true;
        this.state.status = "正在保存…";
        try {
            const payload = await this.orm.call(
                "psc.business.hub",
                "save_sidebar_navigation",
                [this.serializeLayout()]
            );
            this.applyPayload(payload);
            this.env.bus.trigger("PSC:SIDEBAR-NAVIGATION-UPDATED");
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
                "reset_sidebar_navigation",
                []
            );
            this.applyPayload(payload);
            this.env.bus.trigger("PSC:SIDEBAR-NAVIGATION-UPDATED");
            this.state.status = "已恢复默认布局";
        } catch (error) {
            this.notification.add("恢复默认布局失败，请稍后重试。", { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }
}

export class BusinessSidebar extends Component {
    static template = "product_social_content_bridge.BusinessSidebar";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.menu = useService("menu");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            categories: [],
            openCategory: browser.localStorage.getItem(SIDEBAR_CATEGORY_KEY) || "today",
            collapsed: browser.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1",
            fullscreen: false,
            canGoBack: false,
        });
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", ({ detail: mode }) => {
            if (mode !== "new") {
                this.state.fullscreen = mode === "fullscreen";
                this.syncNavigationState();
            }
        });
        useBus(this.env.bus, "PSC:SIDEBAR-NAVIGATION-UPDATED", () => this.loadNavigation());
        onWillStart(() => this.loadNavigation());
        onMounted(() => this.syncNavigationState());
        onWillUnmount(() => this.clearBodyClasses());
    }

    syncNavigationState() {
        const breadcrumbs = this.action.currentController?.config?.breadcrumbs || [];
        this.state.canGoBack = breadcrumbs.length > 1;
        this.syncBodyClasses();
    }

    async loadNavigation() {
        this.state.loading = true;
        try {
            const payload = await this.orm.call(
                "psc.business.hub",
                "get_sidebar_navigation",
                []
            );
            this.state.categories = payload.categories;
            if (
                this.state.categories.length
                && !this.state.categories.some((category) => category.code === this.state.openCategory)
            ) {
                this.state.openCategory = this.state.categories[0].code;
            }
        } catch (error) {
            this.notification.add("左侧功能导航加载失败，请刷新页面后重试。", { type: "danger" });
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    syncBodyClasses() {
        document.body.classList.toggle("o_psc_has_business_sidebar", !this.state.fullscreen);
        document.body.classList.toggle(
            "o_psc_business_sidebar_collapsed",
            !this.state.fullscreen && this.state.collapsed
        );
    }

    clearBodyClasses() {
        document.body.classList.remove(
            "o_psc_has_business_sidebar",
            "o_psc_business_sidebar_collapsed"
        );
    }

    toggleCollapsed() {
        this.state.collapsed = !this.state.collapsed;
        browser.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, this.state.collapsed ? "1" : "0");
        this.syncBodyClasses();
    }

    async goBack() {
        if (!this.state.canGoBack) {
            return;
        }
        await this.action.restore();
    }

    toggleCategory(category) {
        if (this.state.collapsed) {
            this.state.collapsed = false;
            browser.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, "0");
        }
        this.state.openCategory = this.state.openCategory === category.code ? "" : category.code;
        browser.localStorage.setItem(SIDEBAR_CATEGORY_KEY, this.state.openCategory);
        this.syncBodyClasses();
    }

    getMenuIcon(item) {
        return getMenuIcon(this.menu, item);
    }

    async openMenu(item) {
        const target = findActionableMenu(this.menu, this.menu.getMenu(item.id));
        if (!target) {
            this.notification.add(`“${item.name}”暂时没有可打开的功能入口。`, { type: "warning" });
            return;
        }
        await this.menu.selectMenu(target);
    }

    onItemKeydown(event, item) {
        if (!this.state.editMode && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            this.openMenu(item);
        }
    }
}

registry.category("fields").add("psc_business_navigation", {
    component: BusinessNavigation,
    displayName: "LightLink 功能导航",
    supportedTypes: ["char"],
    isEmpty: () => false,
});

registry.category("main_components").add("product_social_content_bridge.BusinessSidebar", {
    Component: BusinessSidebar,
});
