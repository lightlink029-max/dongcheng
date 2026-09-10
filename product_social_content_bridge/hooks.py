from .models.business_hub import APP_MENU_GROUPS


def uninstall_hook(env):
    """Return grouped standard applications to the Odoo launcher before uninstall."""
    category_ids = [
        category.id
        for category_xmlid in APP_MENU_GROUPS
        if (category := env.ref(category_xmlid, raise_if_not_found=False))
    ]
    if category_ids:
        env["ir.ui.menu"].search([
            ("parent_id", "in", category_ids),
        ]).write({"parent_id": False})
