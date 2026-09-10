from .models.business_hub import NAVIGATION_CATEGORIES


def uninstall_hook(env):
    """Return grouped standard applications to the Odoo launcher before uninstall."""
    category_ids = [
        category.id
        for _code, _name, category_xmlid, _icon in NAVIGATION_CATEGORIES
        if category_xmlid
        if (category := env.ref(category_xmlid, raise_if_not_found=False))
    ]
    if category_ids:
        env["ir.ui.menu"].search([
            ("parent_id", "in", category_ids),
        ]).write({"parent_id": False})
