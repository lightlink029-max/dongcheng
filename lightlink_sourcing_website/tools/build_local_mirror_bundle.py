"""Build the editable Odoo seed bundle from the private offline website mirror.

The source mirror is intentionally not served as a static website.  This tool
extracts the page body and metadata, rewrites internal links to the Odoo route,
copies only assets actually used by the extracted pages, and writes a compact
gzip bundle consumed by the module install/upgrade hook.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse


SOURCE_HOSTS = {"jingsourcing.com", "www.jingsourcing.com"}
STATIC_PREFIX = "/lightlink_sourcing_website/static/mirror/"
PAGE_PREFIX = "/sourcing/site"
ASSET_EXTENSIONS = {
    ".avif", ".css", ".eot", ".gif", ".ico", ".jpeg", ".jpg", ".js",
    ".mp4", ".pdf", ".png", ".svg", ".ttf", ".webm", ".webp", ".woff",
    ".woff2",
}


class HeadScanner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonical = ""
        self.description = ""
        self.stylesheets: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []

    @property
    def title(self) -> str:
        return " ".join("".join(self._title_parts).split())

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "link":
            rel = values.get("rel", "").lower()
            href = values.get("href", "")
            if "canonical" in rel:
                self.canonical = href
            if "stylesheet" in rel and href:
                self.stylesheets.append(href)
        elif tag == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content", "")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self._title_parts.append(data)


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value or "").split())


def _rebrand(value: str) -> str:
    value = re.sub(r"Jing\s*Sourcing", "LightLink Global Sourcing", value, flags=re.I)
    value = re.sub(r"Jing\s+Sourcing", "LightLink Global Sourcing", value, flags=re.I)
    return value


def _source_path(root: Path, source_file: Path, canonical: str) -> str:
    parsed = urlparse(canonical)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower() in SOURCE_HOSTS:
        path = unquote(parsed.path).rstrip("/") or "/"
        if not path.startswith("/../"):
            return path
    relative = source_file.parent.relative_to(root).as_posix()
    return "/" if relative == "." else "/" + relative.rstrip("/")


def _keep_page(path: str, title: str) -> bool:
    lowered = path.lower()
    if lowered.endswith("/feed") or "/page/" in lowered:
        return False
    if lowered.startswith(("/author/", "/_/")):
        return False
    if "test" in lowered or lowered.startswith("/elementor-"):
        return False
    return not title.startswith(("Page has moved", "Page not found"))


def _page_type(path: str) -> str:
    if path == "/":
        return "home"
    if path == "/our-products":
        return "product_index"
    if path.startswith("/our-products/"):
        return "product_category"
    if path == "/blog" or path.endswith("-posts") or path in {
        "/amazon-ecommerce", "/china-sourcing", "/deal-with-chinese-suppliers",
    }:
        return "archive"
    if path.startswith(("/b-", "/bg-", "/ca-", "/fb-", "/blog/")):
        return "article"
    if path in {
        "/pricing", "/dropshipping", "/graphics-and-design-service",
        "/extra-service", "/private-label-packaging-service",
        "/product-development", "/shipping-and-cargo-consolidation-service",
        "/amazon-fba-prep-service", "/quality-control-service",
        "/credit-payment-terms", "/affiliates",
    }:
        return "service"
    return "page"


class MirrorBuilder:
    def __init__(self, source_root: Path, module_root: Path):
        self.source_root = source_root.resolve()
        self.module_root = module_root.resolve()
        self.static_root = self.module_root / "static" / "mirror"
        self.bundle_path = self.module_root / "data" / "mirror_pages.json.gz"
        self.assets: set[Path] = set()

    def _resolve_local(self, source_file: Path, raw_url: str) -> Path | None:
        value = html.unescape(raw_url or "").strip().split("?", 1)[0]
        if not value or value.startswith(("data:", "//")):
            return None
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            if parsed.netloc.lower() not in SOURCE_HOSTS:
                return None
            candidate = self.source_root / unquote(parsed.path).lstrip("/")
        elif value.startswith("/"):
            candidate = self.source_root / unquote(value).lstrip("/")
        else:
            candidate = source_file.parent / unquote(value)
        try:
            candidate = candidate.resolve()
            candidate.relative_to(self.source_root)
        except (OSError, ValueError):
            return None
        return candidate if candidate.is_file() else None

    def _asset_url(self, source_file: Path, raw_url: str) -> str:
        local = self._resolve_local(source_file, raw_url)
        # HTTrack stores failed image downloads as small ``.html`` 404 pages.
        # Never publish those files as image sources: browsers reject their MIME
        # type and show a broken-image marker.
        if local and local.suffix.lower() not in ASSET_EXTENSIONS:
            return ""
        if not local:
            return raw_url
        self.assets.add(local)
        return STATIC_PREFIX + local.relative_to(self.source_root).as_posix()

    def _page_url(self, source_file: Path, source_path: str, raw_url: str) -> str:
        value = html.unescape(raw_url or "").strip()
        if not value or value.startswith(("#", "mailto:", "tel:")):
            return value
        if value.lower().startswith("javascript:"):
            return "#"
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc.lower() not in SOURCE_HOSTS:
            return value
        if Path(parsed.path).suffix.lower() in ASSET_EXTENSIONS:
            return self._asset_url(source_file, value)
        base = "https://jingsourcing.com" + (source_path if source_path != "/" else "") + "/"
        target = urlparse(urljoin(base, value))
        if target.netloc.lower() not in SOURCE_HOSTS:
            return value
        path = unquote(target.path).rstrip("/") or "/"
        path = re.sub(r"/index(?:[-_a-z0-9]*)?\.html$", "", path, flags=re.I) or "/"
        path = path.lower()
        rewritten = "/sourcing" if path == "/" else PAGE_PREFIX + path
        if target.query:
            rewritten += "?" + target.query
        if target.fragment:
            rewritten += "#" + target.fragment
        return rewritten

    def _rewrite_html(self, source_file: Path, source_path: str, fragment: str) -> str:
        fragment = re.sub(r"<script\b[^>]*>.*?</script\s*>", "", fragment, flags=re.I | re.S)
        fragment = re.sub(r"<noscript\b[^>]*>.*?</noscript\s*>", "", fragment, flags=re.I | re.S)
        fragment = re.sub(r"<link\b[^>]*>", "", fragment, flags=re.I | re.S)
        fragment = re.sub(r"<!--.*?-->", "", fragment, flags=re.S)
        fragment = re.sub(
            r"\s(?:srcset|data-srcset|sizes|data-settings|data-widget_type|data-element_type|"
            r"data-elementor-type|data-elementor-id|data-elementor-post-type|data-id)="
            r"(?:\"[^\"]*\"|'[^']*')",
            "",
            fragment,
            flags=re.I,
        )
        fragment = re.sub(
            r"\son[a-z]+=(?:\"[^\"]*\"|'[^']*')", "", fragment, flags=re.I,
        )

        def replace_attr(match):
            attr, quote, value = match.group(1), match.group(2), match.group(3)
            if attr.lower() in {"src", "poster"}:
                rewritten = self._asset_url(source_file, value)
            elif attr.lower() == "action":
                rewritten = "/sourcing/request"
            else:
                rewritten = self._page_url(source_file, source_path, value)
            return f" {attr}={quote}{html.escape(rewritten, quote=True)}{quote}"

        fragment = re.sub(
            r"\s(href|src|poster|action)=(\"|')(.+?)\2",
            replace_attr,
            fragment,
            flags=re.I | re.S,
        )
        fragment = re.sub(
            r"<img\b[^>]*\bsrc=(?:\"\"|'')[^>]*>", "", fragment, flags=re.I,
        )

        def replace_css_url(match):
            quote = match.group(1) or ""
            value = match.group(2).strip()
            return f"url({quote}{self._asset_url(source_file, value)}{quote})"

        fragment = re.sub(r"url\((['\"]?)([^)'\"]+)\1\)", replace_css_url, fragment, flags=re.I)
        fragment = re.sub(r">\s+<", "><", fragment)
        fragment = re.sub(
            r"<img\b[^>]*(?:Jingsourcing-logo|JingSourcing-logo)[^>]*>",
            '<span class="ll-imported-brand">LightLink Global Sourcing</span>',
            fragment,
            flags=re.I,
        )
        fragment = re.sub(
            r"(?<=>)([^<]+)(?=<)",
            lambda match: _rebrand(match.group(1)),
            fragment,
        )
        fragment = re.sub(
            r"https?://(?:www\.)?jingsourcing\.com[^\"']*",
            "LightLink Global Sourcing",
            fragment,
            flags=re.I,
        )
        return fragment.strip()

    def _stylesheet_urls(self, source_file: Path, values: list[str]) -> list[str]:
        result = []
        for value in values:
            local = self._resolve_local(source_file, value)
            if not local or local.suffix.lower() != ".css":
                continue
            self.assets.add(local)
            url = STATIC_PREFIX + local.relative_to(self.source_root).as_posix()
            if url not in result:
                result.append(url)
        return result

    @staticmethod
    def _extract_element(document: str, tag: str) -> str:
        start = re.search(rf"<{tag}\b", document, flags=re.I)
        end = document.lower().rfind(f"</{tag}>")
        if not start or end < start.start():
            return ""
        return document[start.start(): end + len(tag) + 3]

    @classmethod
    def _extract_page_body(cls, document: str) -> str:
        structured = cls._extract_element(document, "main") or cls._extract_element(document, "article")
        if structured:
            return structured
        start = re.search(r"<div\b[^>]*data-elementor-type=", document, flags=re.I)
        if not start:
            return ""
        footer = re.search(r"<footer\b", document[start.start():], flags=re.I)
        if footer:
            return document[start.start(): start.start() + footer.start()]
        body_end = document.lower().rfind("</body>")
        return document[start.start():body_end] if body_end > start.start() else ""

    def _copy_assets(self):
        pending = list(self.assets)
        copied: set[Path] = set()
        while pending:
            source = pending.pop()
            if source in copied or not source.is_file():
                continue
            copied.add(source)
            relative = source.relative_to(self.source_root)
            target = self.static_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() != ".css":
                shutil.copy2(source, target)
                continue
            css = source.read_text(encoding="utf-8", errors="ignore")

            def replace_url(match):
                quote = match.group(1) or ""
                raw = match.group(2).strip()
                local = self._resolve_local(source, raw)
                if not local:
                    return match.group(0)
                self.assets.add(local)
                pending.append(local)
                return f"url({quote}{STATIC_PREFIX}{local.relative_to(self.source_root).as_posix()}{quote})"

            css = re.sub(r"url\((['\"]?)([^)'\"]+)\1\)", replace_url, css, flags=re.I)
            target.write_text(css, encoding="utf-8", newline="\n")
        return copied

    def build(self) -> dict:
        # The directory is generated output.  Clearing it keeps removed or
        # invalid mirror assets out of subsequent builds and deployments.
        if self.static_root.is_dir():
            shutil.rmtree(self.static_root)
        self.static_root.mkdir(parents=True, exist_ok=True)
        page_candidates: dict[str, tuple[tuple[int, int, str], dict]] = {}
        root_footer = ""
        for source_file in sorted(self.source_root.rglob("index.html")):
            document = source_file.read_text(encoding="utf-8", errors="ignore")
            scanner = HeadScanner()
            scanner.feed(document)
            source_path = _source_path(self.source_root, source_file, scanner.canonical)
            title = _rebrand(_clean_text(scanner.title))
            if not _keep_page(source_path, title):
                continue
            main_html = self._extract_page_body(document)
            if not main_html:
                continue
            source_relative = source_file.relative_to(self.source_root).as_posix()
            expected = "index.html" if source_path == "/" else source_path.strip("/") + "/index.html"
            priority = (0 if source_relative == expected else 1, len(source_relative), source_relative)
            body_html = self._rewrite_html(source_file, source_path, main_html)
            record = {
                "path": source_path,
                "title": title or source_path.strip("/").replace("-", " ").title(),
                "description": _rebrand(_clean_text(scanner.description)) or title,
                "page_type": _page_type(source_path),
                "source_file": source_relative,
                "source_hash": hashlib.sha256(body_html.encode("utf-8")).hexdigest(),
                "stylesheets": self._stylesheet_urls(source_file, scanner.stylesheets),
                "body_html": body_html,
            }
            current = page_candidates.get(source_path)
            if not current or priority < current[0]:
                page_candidates[source_path] = (priority, record)
            if source_path == "/":
                footer = self._extract_element(document, "footer")
                if footer:
                    root_footer = self._rewrite_html(source_file, source_path, footer)

        pages = [value[1] for value in sorted(page_candidates.values(), key=lambda item: item[1]["path"])]
        known_paths = {item["path"] for item in pages}

        def repair_link(match):
            quote, value = match.group(1), html.unescape(match.group(2))
            parsed = urlparse(value)
            target_path = parsed.path[len(PAGE_PREFIX):].rstrip("/") or "/"
            if target_path in known_paths:
                return match.group(0)
            return f"href={quote}/sourcing/request{quote}"

        for item in pages:
            item["body_html"] = re.sub(
                r"href=(\"|')(/sourcing/site[^\"']*)\1",
                repair_link,
                item["body_html"],
                flags=re.I,
            )
            item["source_hash"] = hashlib.sha256(
                item["body_html"].encode("utf-8")
            ).hexdigest()
        root_footer = re.sub(
            r"href=(\"|')(/sourcing/site[^\"']*)\1",
            repair_link,
            root_footer,
            flags=re.I,
        )
        copied = self._copy_assets()
        payload = {
            "schema_version": 1,
            "source": "private offline jingsourcing.com mirror",
            "route_prefix": PAGE_PREFIX,
            "footer_html": root_footer,
            "pages": pages,
        }
        self.bundle_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self.bundle_path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as archive:
                archive.write(encoded)
        return {
            "pages": len(pages),
            "assets": len(copied),
            "bundle_bytes": self.bundle_path.stat().st_size,
            "source_bytes": len(encoded),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("module_root", type=Path)
    args = parser.parse_args()
    result = MirrorBuilder(args.source_root, args.module_root).build()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
