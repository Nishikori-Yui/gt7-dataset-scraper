import re
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, local as thread_local
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from ..utils import looks_like_image_url
from .catalog_parse import fetch_text, parse_og_description, resolve_asset_url
from .constants import BASE_URL


def extract_detail_with_playwright_on_page(
    page: Any, car_id: str, locale: str, timeout: int
) -> Dict[str, Any]:
    url = f"{BASE_URL}/{locale}/gt7/carlist/id/{car_id}"
    data: Dict[str, Any] = {}
    page.set_default_navigation_timeout(timeout * 1000)
    navigated = False
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        navigated = True
    except Exception:
        pass
    if not navigated:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception:
            return {}

    parsed = {}
    max_wait = min(8, max(3, int(timeout)))
    for _ in range(max_wait):
        try:
            page.wait_for_timeout(800)
        except Exception:
            pass
        html = page.content()
        parsed = parse_detail_html(html, car_id)
        hero = parsed.get("hero_images") or []
        if any("/carlist/assets/" in value for value in hero):
            data.update(parsed)
            break

    if not data and parsed:
        data.update(parsed)

    return data


def extract_detail_with_playwright(car_id: str, locale: str, timeout: int) -> Dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}

    data: Dict[str, Any] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        data = extract_detail_with_playwright_on_page(page, car_id, locale, timeout)
        browser.close()
    return data


class PlaywrightPool:
    def __init__(self, locale: str, timeout: int, workers: int) -> None:
        self.locale = locale
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=workers)
        self.local = thread_local()
        self.contexts: List[Dict[str, Any]] = []
        self.lock = Lock()

    def _get_page(self):
        if hasattr(self.local, "page"):
            return self.local.page
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return None
        pw = sync_playwright().start()
        browser = pw.chromium.launch()
        page = browser.new_page()
        self.local.pw = pw
        self.local.browser = browser
        self.local.page = page
        with self.lock:
            self.contexts.append({"pw": pw, "browser": browser, "page": page})
        return page

    def _task(self, car_id: str) -> Dict[str, Any]:
        page = self._get_page()
        if page is None:
            return {}
        return extract_detail_with_playwright_on_page(page, car_id, self.locale, self.timeout)

    def fetch(self, car_id: str) -> Dict[str, Any]:
        future = self.executor.submit(self._task, car_id)
        return future.result()

    def close(self) -> None:
        try:
            self.executor.shutdown(wait=True)
        except Exception:
            pass
        for ctx in self.contexts:
            try:
                ctx["page"].close()
            except Exception:
                pass
            try:
                ctx["browser"].close()
            except Exception:
                pass
            try:
                ctx["pw"].stop()
            except Exception:
                pass


def parse_list_html_for_thumbs(html: str) -> Dict[str, List[str]]:
    soup = BeautifulSoup(html, "lxml")
    thumb_map: Dict[str, List[str]] = {}
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if "/car_thumbnails/" in src and "car" in src:
            match = re.search(r"(car\d+)", src)
            if match:
                car_id = match.group(1)
                thumb_map.setdefault(car_id, []).append(src)
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/gt7/carlist/id/" not in href:
            continue
        match = re.search(r"/id/(car\d+)", href)
        if not match:
            continue
        car_id = match.group(1)
        img_url = None
        img_tag = anchor.find("img")
        if img_tag and img_tag.get("src"):
            img_url = img_tag.get("src")
        if not img_url and anchor.parent is not None:
            parent_img = anchor.parent.find("img")
            if parent_img and parent_img.get("src"):
                img_url = parent_img.get("src")
        if not img_url:
            style = anchor.get("style") or (anchor.parent.get("style") if anchor.parent else None)
            if style:
                match = re.search(r"url\\([\"']?([^\"')]+)", style)
                if match:
                    img_url = match.group(1)
        if img_url:
            thumb_map.setdefault(car_id, []).append(img_url)
    deduped: Dict[str, List[str]] = {}
    for car_id, urls in thumb_map.items():
        seen = set()
        out = []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
        deduped[car_id] = out
    return deduped


def parse_list_html_for_thumbs_with_backend(
    html: str,
    go_catalog_bin: Optional[str],
) -> Dict[str, List[str]]:
    if go_catalog_bin:
        try:
            from ..backends.catalog.go_parser import parse_list_thumbs_with_go

            parsed = parse_list_thumbs_with_go(go_catalog_bin, html)
            if parsed:
                return parsed
        except Exception:
            pass
    return parse_list_html_for_thumbs(html)


def extract_list_thumbs_with_playwright(locale: str, timeout: int = 30) -> Dict[str, List[str]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}

    url = f"{BASE_URL}/{locale}/gt7/carlist/"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.set_default_navigation_timeout(timeout * 1000)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except Exception:
                browser.close()
                return {}
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            try:
                page.wait_for_selector("a[href*='/gt7/carlist/id/']", timeout=15000)
            except Exception:
                pass
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
            except Exception:
                pass
            html = page.content()
            browser.close()
        return parse_list_html_for_thumbs_with_backend(html, go_catalog_bin=None)
    except Exception:
        return {}


def extract_intro_detail(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    intro = None
    detail = None

    for h4 in soup.find_all("h4"):
        text = h4.get_text(" ", strip=True)
        if not text or len(text) < 20:
            continue
        parent = h4.parent
        if parent:
            paragraph = parent.find("p")
            if paragraph:
                intro = text
                detail = paragraph.get_text(" ", strip=True)
                break

    if not intro:
        main = soup.find("main") or soup
        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in main.find_all("p")
            if paragraph.get_text(strip=True)
        ]
        filtered = [
            text
            for text in paragraphs
            if len(text) > 20 and "Gran Turismo" not in text and "Car List" not in text
        ]
        if filtered:
            intro = filtered[0]
            if len(filtered) > 1:
                detail = filtered[1]

    return intro, detail


def parse_detail_html(html: str, car_id: Optional[str] = None) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    data: Dict[str, Any] = {}

    h1 = soup.find("h1")
    if h1:
        data["name"] = h1.get_text(strip=True)

    h2 = soup.find("h2")
    if h2:
        data["manufacturer_name"] = h2.get_text(strip=True)

    intro, detail = extract_intro_detail(soup)
    if not intro:
        og_desc = parse_og_description(html)
        if og_desc:
            intro = og_desc
    if intro:
        data["intro"] = intro
    if detail:
        data["detail"] = detail

    specs = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                key = cells[0].get_text(" ", strip=True)
                val = cells[1].get_text(" ", strip=True)
                if key and val:
                    specs.append((key, val))
    if not specs:
        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                key = dt.get_text(" ", strip=True)
                val = dd.get_text(" ", strip=True)
                if key and val:
                    specs.append((key, val))

    if specs:
        data["specs"] = specs

    image_urls = []
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if looks_like_image_url(src):
            if car_id:
                if car_id in src and "/car_thumbnails/" not in src:
                    image_urls.append(src)
            else:
                image_urls.append(src)
    if car_id:
        pattern = rf"/common/dist/gt7/carlist/assets/{car_id}_[^\"'\\s]+\\.(?:jpg|jpeg|png|webp)"
        for match in re.findall(pattern, html, flags=re.IGNORECASE):
            image_urls.append(match)
    if not image_urls:
        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            content = og.get("content")
            if not car_id or (car_id and car_id in content):
                image_urls.append(content)
    if image_urls:
        seen = set()
        unique = []
        for url in image_urls:
            if url in seen:
                continue
            seen.add(url)
            unique.append(url)
        data["hero_images"] = unique

    return data


def extract_hero_module_files(index_js: str, car_id: str) -> List[str]:
    pattern = re.compile(
        rf'{re.escape(car_id)}_[0-9]+_[0-9]+\.(?:jpg|jpeg|png|webp)"\s*:\s*\(\)\s*=>\s*e\(\(\)\s*=>\s*import\("\./([^"]+\.js)"\)',
        flags=re.IGNORECASE,
    )
    modules: List[str] = []
    seen = set()
    for match in pattern.finditer(index_js):
        module_name = match.group(1)
        if module_name in seen:
            continue
        seen.add(module_name)
        modules.append(module_name)
    return modules


def extract_hero_urls_from_module_js(module_js: str, car_id: str) -> List[str]:
    pattern = re.compile(
        rf"(/common/dist/gt7/carlist/assets/{re.escape(car_id)}_[0-9]+_[0-9]+-[^\"']+\.(?:jpg|jpeg|png|webp))",
        flags=re.IGNORECASE,
    )
    urls: List[str] = []
    seen_keys = set()
    for match in pattern.finditer(module_js):
        url = match.group(1)
        key_match = re.search(rf"({re.escape(car_id)}_[0-9]+_[0-9]+)", url, flags=re.IGNORECASE)
        if not key_match:
            continue
        key = key_match.group(1).lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        urls.append(url)
    return urls


def resolve_hero_urls_from_asset_modules(
    session: requests.Session,
    index_js: str,
    car_id: str,
    timeout: int,
) -> List[str]:
    modules = extract_hero_module_files(index_js, car_id)
    if not modules:
        return []
    urls: List[str] = []
    seen_keys = set()
    for module_name in modules:
        module_url = resolve_asset_url(module_name)
        try:
            module_js = fetch_text(session, module_url, timeout)
        except Exception:
            continue
        for url in extract_hero_urls_from_module_js(module_js, car_id):
            key_match = re.search(rf"({re.escape(car_id)}_[0-9]+_[0-9]+)", url, flags=re.IGNORECASE)
            if not key_match:
                continue
            key = key_match.group(1).lower()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            urls.append(url)
    return urls
