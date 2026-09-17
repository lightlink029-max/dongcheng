/** @odoo-module **/

function activateAccordion(title) {
    const container = title.closest(".elementor-accordion-item, .elementor-toggle-item");
    const content = container && container.querySelector(
        ".elementor-tab-content, .elementor-toggle-content"
    );
    if (!content) {
        return;
    }
    const active = title.classList.toggle("elementor-active");
    title.setAttribute("aria-expanded", active ? "true" : "false");
    content.classList.toggle("elementor-active", active);
    content.hidden = !active;
}

document.addEventListener("click", (event) => {
    const title = event.target.closest(
        ".ll-mirror-page .elementor-tab-title, .ll-mirror-page .elementor-toggle-title"
    );
    if (title) {
        event.preventDefault();
        activateAccordion(title);
    }
});

document.addEventListener("submit", (event) => {
    const form = event.target.closest(".ll-mirror-page form");
    if (!form) {
        return;
    }
    event.preventDefault();
    window.location.assign("/sourcing/request");
});

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(
        ".ll-mirror-page .elementor-tab-content, .ll-mirror-page .elementor-toggle-content"
    ).forEach((content) => {
        content.hidden = !content.classList.contains("elementor-active");
    });
});
