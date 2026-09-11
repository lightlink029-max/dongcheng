/** @odoo-module **/

document.addEventListener("change", (event) => {
    const input = event.target.closest?.(".pi-image-search-input");
    if (!input || !input.files?.length) {
        return;
    }
    const file = input.files[0];
    const maxMb = Number(input.dataset.maxMb || 5);
    const allowedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
    if (!allowedTypes.has(file.type)) {
        window.alert("请选择 JPG、PNG 或 WebP 图片。");
        input.value = "";
        return;
    }
    if (file.size > maxMb * 1024 * 1024) {
        window.alert(`图片不能超过 ${maxMb} MB。`);
        input.value = "";
        return;
    }
    const form = input.closest("form");
    if (!form || form.dataset.submitting === "1") {
        return;
    }
    form.dataset.submitting = "1";
    form.classList.add("pi-image-search-loading");
    form.submit();
});
