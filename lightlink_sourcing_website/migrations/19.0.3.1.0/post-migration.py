import gzip
import json

from odoo import api, SUPERUSER_ID, tools


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    website = env.ref(
        "lightlink_sourcing_website.website_global_sourcing",
        raise_if_not_found=False,
    )
    if not website:
        return

    bundle_path = tools.file_path(
        "lightlink_sourcing_website/data/mirror_pages.json.gz"
    )
    with gzip.open(bundle_path, "rt", encoding="utf-8") as archive:
        payload = json.load(archive)
    style_by_path = {
        item["path"]: item.get("style_hash") or False
        for item in payload.get("pages", [])
    }
    pages = env["ll.sourcing.content.page"].search([
        ("website_id", "=", website.id),
        ("imported_from_mirror", "=", True),
    ])
    for page in pages:
        page.source_style_hash = style_by_path.get(page.source_path) or False
