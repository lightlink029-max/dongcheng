import math
import re
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlencode

from markupsafe import escape

from odoo import http, tools
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import email_split


_ALLOWED_MIMETYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_FILES = 5
_RATE_LIMIT = 8
_RATE_WINDOW_SECONDS = 600
_RATE_LOCK = threading.Lock()
_RATE_HITS = defaultdict(deque)
_REQUEST_TYPES = {
    "find_supplier",
    "manage_supplier",
    "product_development",
    "private_label",
    "quality_inspection",
    "shipping_consolidation",
    "dropshipping",
    "design_customization",
    "photography_video",
    "warehousing_kitting",
    "supplier_audit",
    "marketplace_prep",
}
_OFFERING_KINDS = {"services": "service", "solutions": "solution"}
_BUSINESS_STAGES = {"idea", "testing", "buying", "scaling"}
_VALUE_SERVICE_SLUGS = {
    "dropshipping-fulfillment",
    "product-photography-video",
    "packaging-graphic-design",
    "warehousing-repacking-kitting",
    "factory-supplier-audit",
    "marketplace-fba-preparation",
}


class LightLinkSourcingWebsite(http.Controller):
    @staticmethod
    def _clean(value, limit=500):
        return str(value or "").strip()[:limit]

    @staticmethod
    def _consume_rate_limit(client_key):
        now = time.monotonic()
        with _RATE_LOCK:
            hits = _RATE_HITS[client_key]
            while hits and hits[0] <= now - _RATE_WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= _RATE_LIMIT:
                return False
            hits.append(now)
            if len(_RATE_HITS) > 5000:
                stale_keys = [
                    key for key, values in _RATE_HITS.items()
                    if not values or values[-1] <= now - _RATE_WINDOW_SECONDS
                ]
                for key in stale_keys[:1000]:
                    _RATE_HITS.pop(key, None)
            return True

    @staticmethod
    def _sourcing_website():
        """Use the dedicated site even before its standalone domain is assigned."""
        if request.website.sourcing_enabled:
            return request.website
        website = request.env.ref(
            "lightlink_sourcing_website.website_global_sourcing",
            raise_if_not_found=False,
        )
        return website.sudo() if website else request.website

    @staticmethod
    def _active_project():
        website = LightLinkSourcingWebsite._sourcing_website()
        Project = request.env["psc.publishing.project"].sudo()
        domain = [
            ("website_inquiry_enabled", "=", True),
            ("website_id", "=", website.id),
        ]
        return (
            Project.search(domain + [("operation_state", "=", "active")], limit=1)
            or Project.search(domain, order="create_date desc, id desc", limit=1)
        )

    @staticmethod
    def _base_values(**extra):
        website = LightLinkSourcingWebsite._sourcing_website()
        project = LightLinkSourcingWebsite._active_project()
        assets = request.env["ll.sourcing.asset"].sudo().search([
            ("website_id", "=", website.id), ("active", "=", True),
        ])
        offerings = request.env["ll.sourcing.offering"].sudo().search([
            ("website_id", "=", website.id), ("active", "=", True),
        ], order="kind, sequence, id")
        metrics = request.env["ll.sourcing.metric"].sudo().search([
            ("website_id", "=", website.id),
            ("active", "=", True),
            ("verified", "=", True),
            ("published", "=", True),
        ], order="sequence, id")
        testimonials = request.env["ll.sourcing.testimonial"].sudo().search([
            ("website_id", "=", website.id),
            ("active", "=", True),
            ("verified", "=", True),
            ("permission_confirmed", "=", True),
            ("published", "=", True),
        ], order="sequence, id")
        footer_columns = request.env["ll.sourcing.footer.column"].sudo().search([
            ("website_id", "=", website.id),
            ("active", "=", True),
            ("published", "=", True),
        ], order="sequence, id")
        values = {
            "sourcing_website": website,
            "sourcing_project": project,
            "countries": request.env["res.country"].sudo().search([], order="name"),
            "sourcing_assets": {asset.key: asset for asset in assets},
            "sourcing_services": offerings.filtered(lambda item: item.kind == "service"),
            "sourcing_solutions": offerings.filtered(lambda item: item.kind == "solution"),
            "sourcing_plans": offerings.filtered(lambda item: item.kind == "plan"),
            "sourcing_featured_services": offerings.filtered(
                lambda item: item.kind == "service" and item.featured
            ),
            "sourcing_featured_solutions": offerings.filtered(
                lambda item: item.kind == "solution" and item.featured
            ),
            "sourcing_value_services": offerings.filtered(
                lambda item: item.kind == "service" and item.slug in _VALUE_SERVICE_SLUGS
            ),
            "sourcing_metrics": metrics,
            "sourcing_testimonials": testimonials,
            "sourcing_footer_columns": footer_columns,
            "sourcing_service_email": (
                project.website_service_email if project and project.website_service_email
                else website.sourcing_service_email
            ),
            "sourcing_whatsapp_url": (
                project.website_whatsapp_url if project and project.website_whatsapp_url
                else website.sourcing_whatsapp_url
            ),
        }
        values.update(extra)
        return values

    @staticmethod
    def _catalog_categories(website):
        Product = request.env["product.template"].sudo()
        Category = request.env["product.public.category"].sudo()
        catalog_domain = website.sale_product_domain()
        assigned_categories = Product.search(catalog_domain).mapped("public_categ_ids")
        root_categories = Category.search([
            ("website_id", "=", website.id), ("parent_id", "=", False),
        ])
        for category in assigned_categories:
            root = category
            while root.parent_id:
                root = root.parent_id
            root_categories |= root

        result = []
        for category in root_categories.sorted(lambda item: (item.sequence, item.name, item.id)):
            category_domain = catalog_domain & Domain(
                "public_categ_ids", "child_of", category.id
            )
            count = Product.search_count(category_domain)
            image_asset = category.sourcing_image_asset_id or category.child_id.mapped(
                "sourcing_image_asset_id"
            )[:1]
            result.append({
                "record": category,
                "count": count,
                "image_asset": image_asset,
                "image_product": Product.search(
                    category_domain, limit=1, order="website_sequence, id desc"
                ),
            })
        return result

    @staticmethod
    def _mirror_page(source_path):
        website = LightLinkSourcingWebsite._sourcing_website()
        normalized = "/" + str(source_path or "").strip("/")
        if normalized == "//":
            normalized = "/"
        return request.env["ll.sourcing.content.page"].sudo().search([
            ("website_id", "=", website.id),
            ("source_path", "=", normalized),
            ("imported_from_mirror", "=", True),
            ("active", "=", True),
            ("published", "=", True),
        ], limit=1)

    def _render_mirror_page(self, source_path):
        page = self._mirror_page(source_path)
        if not page:
            return request.not_found()
        return request.render(
            "lightlink_sourcing_website.sourcing_mirror_page",
            self._base_values(mirror_page=page),
        )

    @http.route("/sourcing", type="http", auth="public", website=True, sitemap=True)
    def sourcing_home(self, **kwargs):
        mirror_page = self._mirror_page("/")
        if mirror_page:
            return request.render(
                "lightlink_sourcing_website.sourcing_mirror_page",
                self._base_values(mirror_page=mirror_page),
            )
        website = self._sourcing_website()
        products = request.env["product.template"].sudo().search(
            website.sale_product_domain(), limit=8, order="website_sequence, id desc"
        )
        return request.render(
            "lightlink_sourcing_website.sourcing_home",
            self._base_values(featured_products=products),
        )

    @http.route(
        ["/sourcing/site", "/sourcing/site/<path:source_path>"],
        type="http", auth="public", website=True, sitemap=True,
    )
    def sourcing_mirror_page(self, source_path="", **kwargs):
        return self._render_mirror_page(source_path)

    @http.route(
        "/sourcing/styles/<string:style_hash>.css",
        type="http", auth="public", website=True, sitemap=False,
    )
    def sourcing_mirror_style(self, style_hash, **kwargs):
        if not re.fullmatch(r"[0-9a-f]{64}", style_hash or ""):
            return request.not_found()
        try:
            style_path = tools.file_path(
                "lightlink_sourcing_website/static/mirror_styles/%s.css.gz"
                % style_hash
            )
            with open(style_path, "rb") as stream:
                payload = stream.read()
        except (FileNotFoundError, OSError):
            return request.not_found()
        return request.make_response(payload, headers=[
            ("Content-Type", "text/css; charset=utf-8"),
            ("Content-Encoding", "gzip"),
            ("Cache-Control", "public, max-age=31536000, immutable"),
        ])

    @http.route("/sourcing/products", type="http", auth="public", website=True, sitemap=True)
    def sourcing_products(self, category=None, search=None, page=0, **kwargs):
        return request.redirect("/sourcing/site/our-products", code=302)
        website = self._sourcing_website()
        Product = request.env["product.template"].sudo()
        catalog_domain = website.sale_product_domain()
        category_values = self._catalog_categories(website)
        selected_category = request.env["product.public.category"]
        if str(category or "").isdigit():
            category_id = int(category)
            selected = [
                item["record"] for item in category_values
                if item["record"].id == category_id
            ]
            if selected:
                selected_category = selected[0]
                catalog_domain = catalog_domain & Domain(
                    "public_categ_ids", "child_of", selected_category.id
                )

        search_term = self._clean(search, 80)
        if search_term:
            catalog_domain = catalog_domain & Domain("name", "ilike", search_term)
        try:
            page_number = max(0, min(int(page or 0), 9999))
        except (TypeError, ValueError):
            page_number = 0
        page_size = 24
        total = Product.search_count(catalog_domain)
        url_args = {}
        if selected_category:
            url_args["category"] = selected_category.id
        if search_term:
            url_args["search"] = search_term
        pager = website.pager(
            url="/sourcing/products",
            total=total,
            page=page_number,
            step=page_size,
            scope=7,
            url_args=url_args,
        )
        products = Product.search(
            catalog_domain,
            limit=page_size,
            offset=pager["offset"],
            order="website_sequence, id desc",
        )
        return request.render(
            "lightlink_sourcing_website.sourcing_products",
            self._base_values(
                products=products,
                product_total=total,
                product_categories=category_values,
                selected_category=selected_category,
                product_search=search_term,
                pager=pager,
            ),
        )

    @http.route(
        "/sourcing/products/category/<int:category_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def sourcing_product_category(self, category_id, **kwargs):
        return request.redirect("/sourcing/site/our-products", code=302)
        website = self._sourcing_website()
        Category = request.env["product.public.category"].sudo()
        Product = request.env["product.template"].sudo()
        category = Category.browse(category_id).exists()
        if not category or category.website_id.id != website.id:
            return request.not_found()

        catalog_domain = website.sale_product_domain() & Domain(
            "public_categ_ids", "child_of", category.id
        )
        children = Category.search([
            ("parent_id", "=", category.id),
            ("website_id", "=", website.id),
        ], order="sequence, name, id")
        child_values = []
        for child in children:
            child_domain = website.sale_product_domain() & Domain(
                "public_categ_ids", "child_of", child.id
            )
            child_values.append({
                "record": child,
                "count": Product.search_count(child_domain),
                "image_product": Product.search(
                    child_domain, limit=1, order="website_sequence, id desc"
                ),
            })

        return request.render(
            "lightlink_sourcing_website.sourcing_product_category",
            self._base_values(
                category=category,
                category_children=child_values,
                category_products=Product.search(
                    catalog_domain, limit=12, order="website_sequence, id desc"
                ),
                category_product_total=Product.search_count(catalog_domain),
            ),
        )

    @http.route("/sourcing/services", type="http", auth="public", website=True, sitemap=True)
    def sourcing_services(self, **kwargs):
        return self._render_mirror_page("pricing")

    @http.route(
        "/sourcing/<string:kind>/<string:slug>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def sourcing_offering(self, kind, slug, **kwargs):
        legacy_paths = {
            "sourcing-purchasing": "pricing",
            "dropshipping-fulfillment": "dropshipping",
            "packaging-graphic-design": "graphics-and-design-service",
            "private-label-customization": "private-label-packaging-service",
            "product-development": "product-development",
            "consolidation-shipping": "shipping-and-cargo-consolidation-service",
            "marketplace-fba-preparation": "amazon-fba-prep-service",
            "quality-inspection": "quality-control-service",
        }
        if slug in legacy_paths:
            return self._render_mirror_page(legacy_paths[slug])
        offering_kind = _OFFERING_KINDS.get(kind)
        if not offering_kind:
            return request.not_found()
        website = self._sourcing_website()
        offering = request.env["ll.sourcing.offering"].sudo().search([
            ("website_id", "=", website.id),
            ("kind", "=", offering_kind),
            ("slug", "=", self._clean(slug, 120)),
            ("active", "=", True),
        ], limit=1)
        if not offering:
            return request.not_found()
        return request.render(
            "lightlink_sourcing_website.sourcing_offering",
            self._base_values(offering=offering, offering_url_kind=kind),
        )

    @http.route("/sourcing/solutions", type="http", auth="public", website=True, sitemap=True)
    def sourcing_solutions(self, **kwargs):
        return self._render_mirror_page("business-modes-supported")

    @http.route("/sourcing/pricing", type="http", auth="public", website=True, sitemap=True)
    def sourcing_pricing(self, **kwargs):
        return self._render_mirror_page("pricing")

    def _render_content_page(self, code):
        website = self._sourcing_website()
        content_page = request.env["ll.sourcing.content.page"].sudo().search([
            ("website_id", "=", website.id),
            ("code", "=", code),
            ("active", "=", True),
            ("published", "=", True),
        ], limit=1)
        if not content_page:
            return request.not_found()
        payments = request.env["ll.sourcing.payment.method"]
        if code == "payment-information":
            payments = payments.sudo().search([
                ("website_id", "=", website.id),
                ("active", "=", True),
                ("published", "=", True),
            ], order="sequence, id")
        chapters = content_page.chapter_ids.filtered(
            lambda item: item.active and item.published
        ).sorted(lambda item: (item.sequence, item.id))
        yiwu_sections = request.env["ll.sourcing.content.page"].sudo().search([
            ("website_id", "=", website.id),
            ("code", "like", "yiwu-%"),
            ("active", "=", True),
            ("published", "=", True),
        ], order="sequence, id")
        template = "lightlink_sourcing_website.sourcing_content_page"
        if code == "visit-yiwu":
            template = "lightlink_sourcing_website.sourcing_yiwu"
        elif code.startswith("yiwu-"):
            template = "lightlink_sourcing_website.sourcing_yiwu_detail"
        return request.render(
            template,
            self._base_values(
                content_page=content_page,
                payment_methods=payments,
                guide_chapters=chapters,
                yiwu_sections=yiwu_sections,
            ),
        )

    @http.route("/sourcing/about", type="http", auth="public", website=True, sitemap=True)
    def sourcing_about(self, **kwargs):
        return self._render_mirror_page("about-us")

    @http.route("/sourcing/payment", type="http", auth="public", website=True, sitemap=True)
    def sourcing_payment(self, **kwargs):
        return self._render_mirror_page("payment")

    @http.route("/sourcing/founder", type="http", auth="public", website=True, sitemap=True)
    def sourcing_founder(self, **kwargs):
        return self._render_mirror_page("jing")

    @http.route("/sourcing/resources", type="http", auth="public", website=True, sitemap=True)
    def sourcing_resources(self, **kwargs):
        return self._render_mirror_page("blog")

    @http.route(
        "/sourcing/resources/importing-from-china",
        type="http", auth="public", website=True, sitemap=True,
    )
    def sourcing_importing_guide(self, **kwargs):
        return self._render_mirror_page("blog/c-import-from-china-guide")

    @http.route(
        "/sourcing/resources/sourcing-agent-guide",
        type="http", auth="public", website=True, sitemap=True,
    )
    def sourcing_agent_guide(self, **kwargs):
        return self._render_mirror_page("find-china-sourcing-agents-company")

    @http.route("/sourcing/yiwu-china", type="http", auth="public", website=True, sitemap=True)
    def sourcing_visit_yiwu(self, **kwargs):
        return self._render_mirror_page("yiwu-china")

    @http.route(
        "/sourcing/yiwu-china/<string:slug>",
        type="http", auth="public", website=True, sitemap=True,
    )
    def sourcing_yiwu_detail(self, slug, **kwargs):
        clean_slug = self._clean(slug, 100)
        if clean_slug not in {
            "markets", "business-services", "trade-fairs", "transportation",
            "hotels", "entertainment", "muslim-culture",
        }:
            return request.not_found()
        return self._render_content_page("yiwu-%s" % clean_slug)

    @http.route("/sourcing/request", type="http", auth="public", website=True, sitemap=True)
    def sourcing_request(self, product_id=None, error=None, **kwargs):
        website = self._sourcing_website()
        product = request.env["product.template"]
        if product_id and str(product_id).isdigit():
            candidate = request.env["product.template"].sudo().browse(int(product_id)).exists()
            if candidate:
                product = request.env["product.template"].sudo().search(
                    Domain("id", "=", candidate.id) & website.sale_product_domain(),
                    limit=1,
                )
        return request.render(
            "lightlink_sourcing_website.sourcing_request",
            self._base_values(product=product, form_error=error, form_data=kwargs),
        )

    @http.route(
        "/sourcing/request/submit",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def sourcing_request_submit(self, **post):
        if self._clean(post.get("website"), 50):
            return request.redirect("/sourcing/thank-you")
        client_key = request.httprequest.remote_addr or "unknown"
        if not self._consume_rate_limit(client_key):
            return request.redirect("/sourcing/request?error=rate")

        contact_name = self._clean(post.get("contact_name"), 120)
        email = self._clean(post.get("email"), 254)
        company_name = self._clean(post.get("company_name"), 160)
        requirement_details = self._clean(post.get("requirement_details"), 5000)
        request_type = self._clean(post.get("request_type"), 40)
        business_stage = self._clean(post.get("business_stage"), 40)
        if business_stage not in _BUSINESS_STAGES:
            business_stage = False
        valid_email = email_split(email)
        if (
            not contact_name
            or not valid_email
            or not requirement_details
            or request_type not in _REQUEST_TYPES
            or post.get("privacy_consent") != "on"
        ):
            query = urlencode({"error": "missing"})
            return request.redirect("/sourcing/request?%s" % query)

        website = self._sourcing_website()
        project = self._active_project()
        country = request.env["res.country"]
        if str(post.get("country_id", "")).isdigit():
            country = country.sudo().browse(int(post["country_id"])).exists()
        country_id = country.id if country else False
        product_id = int(post["product_id"]) if str(post.get("product_id", "")).isdigit() else False
        product = request.env["product.template"]
        if product_id:
            product = request.env["product.template"].sudo().search(
                Domain("id", "=", product_id) & website.sale_product_domain(),
                limit=1,
            )

        subject = self._clean(post.get("product_category"), 160) or (
            product.name if product else "General sourcing request"
        )
        lead = request.env["crm.lead"].sudo().create(
            {
                "name": "Website sourcing inquiry: %s" % subject,
                "type": "lead",
                "contact_name": contact_name,
                "partner_name": company_name,
                "email_from": valid_email[0],
                "phone": self._clean(post.get("phone"), 80),
                "country_id": country_id,
                "description": self._lead_description(post),
                "psc_project_id": project.id if project else False,
                "ll_source_website_id": website.id,
            }
        )

        requirement = request.env["psc.customer.requirement"]
        if project:
            requirement = requirement.sudo().create(
                {
                    "name": subject,
                    "lead_id": lead.id,
                    "project_id": project.id,
                    "product_ids": [(6, 0, product.ids)] if product else False,
                    "request_type": request_type,
                    "product_category": self._clean(post.get("product_category"), 160),
                    "business_stage": business_stage,
                    "organization_type": self._clean(post.get("organization_type"), 120),
                    "contact_role": self._clean(post.get("contact_role"), 120),
                    "requirement_details": requirement_details,
                    "quantity": self._float(post.get("quantity")),
                    "target_unit_price": self._float(post.get("target_unit_price")),
                    "customization_requirements": self._clean(post.get("customization_requirements"), 3000),
                    "packaging_requirements": self._clean(post.get("packaging_requirements"), 3000),
                    "certification_requirements": self._clean(post.get("certification_requirements"), 3000),
                    "delivery_country_id": country_id,
                    "delivery_port": self._clean(post.get("delivery_port"), 160),
                    "incoterm": self._clean(post.get("incoterm"), 40),
                    "sample_required": post.get("sample_required") == "on",
                    "reference_url": self._clean(post.get("reference_url"), 1000),
                    "website_source_url": self._clean(request.httprequest.referrer, 1000),
                    "website_language": request.env.lang,
                    "website_id": website.id,
                }
            )

        request.env["psc.customer.touchpoint"].sudo().create(
            {
                "lead_id": lead.id,
                "event_type": "inquiry",
                "source_type": "website",
                "project_id": project.id if project else False,
                "website_id": website.id,
                "product_id": product.id if product else False,
                "landing_url": self._clean(request.httprequest.referrer, 1000),
                "utm_source": self._clean(post.get("utm_source"), 120),
                "utm_medium": self._clean(post.get("utm_medium"), 120),
                "utm_campaign": self._clean(post.get("utm_campaign"), 160),
                "utm_content": self._clean(post.get("utm_content"), 160),
                "utm_term": self._clean(post.get("utm_term"), 160),
                "verified": True,
            }
        )

        attachments = self._save_attachments(lead, requirement)
        if requirement and attachments:
            requirement.sudo().write({"attachment_ids": [(6, 0, attachments.ids)]})
        return request.redirect("/sourcing/thank-you")

    @http.route("/sourcing/thank-you", type="http", auth="public", website=True, sitemap=False)
    def sourcing_thank_you(self, **kwargs):
        return request.render(
            "lightlink_sourcing_website.sourcing_thank_you", self._base_values()
        )

    def _save_attachments(self, lead, requirement):
        Attachment = request.env["ir.attachment"].sudo()
        created = Attachment
        for uploaded in request.httprequest.files.getlist("attachments")[:_MAX_FILES]:
            mimetype = self._clean(uploaded.mimetype, 150)
            if mimetype not in _ALLOWED_MIMETYPES:
                continue
            raw = uploaded.stream.read(_MAX_FILE_BYTES + 1)
            if not raw or len(raw) > _MAX_FILE_BYTES:
                continue
            record = requirement if requirement else lead
            created |= Attachment.create(
                {
                    "name": self._clean(uploaded.filename, 255) or "sourcing-reference",
                    "raw": raw,
                    "mimetype": mimetype,
                    "res_model": record._name,
                    "res_id": record.id,
                }
            )
        return created

    def _lead_description(self, post):
        labels = [
            ("Service", post.get("request_type")),
            ("Product category", post.get("product_category")),
            ("Organization", post.get("organization_type")),
            ("Business stage", post.get("business_stage")),
            ("Contact role", post.get("contact_role")),
            ("Quantity", post.get("quantity")),
            ("Target unit price", post.get("target_unit_price")),
            ("Delivery", post.get("delivery_port")),
            ("Incoterm", post.get("incoterm")),
            ("Reference", post.get("reference_url")),
            ("Requirements", post.get("requirement_details")),
        ]
        return "<br/>".join(
            "%s: %s" % (escape(label), escape(self._clean(value, 5000)))
            for label, value in labels
            if self._clean(value, 5000)
        )

    @staticmethod
    def _float(value):
        try:
            number = float(str(value or "").replace(",", "").strip())
            return max(0.0, number) if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0
