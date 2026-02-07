from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from ..engine.downloader import run_downloader_jobs
from ..utils import download_file, looks_like_image_url
from .catalog_parse import normalize_url


def collect_image_urls(obj: Any) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []

    def walk(value: Any, path: List[str]) -> None:
        if isinstance(value, dict):
            for key, val in value.items():
                walk(val, path + [str(key)])
        elif isinstance(value, list):
            for idx, val in enumerate(value):
                walk(val, path + [str(idx)])
        elif isinstance(value, str) and looks_like_image_url(value):
            found.append((".".join(path), value))

    walk(obj, [])
    return found


def split_images(obj: Any) -> Dict[str, List[str]]:
    logos: List[str] = []
    heroes: List[str] = []
    thumbs: List[str] = []

    for keypath, url in collect_image_urls(obj):
        lower = keypath.lower()
        if "logo" in lower:
            logos.append(url)
        elif any(token in lower for token in ["thumb", "list", "card", "small"]):
            thumbs.append(url)
        else:
            heroes.append(url)

    def unique(values: Iterable[str]) -> List[str]:
        seen = set()
        out = []
        for val in values:
            if val in seen:
                continue
            seen.add(val)
            out.append(val)
        return out

    return {
        "logos": unique(logos),
        "heroes": unique(heroes),
        "thumbs": unique(thumbs),
    }


def build_car_images(
    car_id: str,
    image_dir: Path,
    hero_urls: List[str],
    thumb_urls: List[str],
    session: requests.Session,
    timeout: int,
) -> List[Dict[str, str]]:
    images = []
    for idx, url in enumerate(hero_urls, start=1):
        if not url or url.startswith("data:"):
            continue
        url = normalize_url(url)
        filename = f"{car_id}_hero_{idx:02d}"
        path = image_dir / "cars" / car_id / filename
        try:
            final_path = download_file(url, path, session, timeout)
        except Exception:
            continue
        images.append(
            {
                "image_path": str(final_path.relative_to(image_dir)),
                "sort_order": idx,
                "image_type": "hero",
            }
        )

    for idx, url in enumerate(thumb_urls, start=1):
        if not url or url.startswith("data:"):
            continue
        url = normalize_url(url)
        filename = f"{car_id}_thumb_{idx:02d}"
        path = image_dir / "cars" / car_id / filename
        try:
            final_path = download_file(url, path, session, timeout)
        except Exception:
            continue
        images.append(
            {
                "image_path": str(final_path.relative_to(image_dir)),
                "sort_order": idx,
                "image_type": "thumb",
            }
        )

    return images


def build_logo(
    manufacturer_id: str,
    logo_url: Optional[str],
    image_dir: Path,
    session: requests.Session,
    timeout: int,
) -> Optional[str]:
    if not logo_url:
        return None
    logo_url = normalize_url(logo_url)
    path = image_dir / "manufacturers" / manufacturer_id / "logo"
    try:
        final_path = download_file(logo_url, path, session, timeout)
    except Exception:
        return None
    return str(final_path.relative_to(image_dir))


def build_assets_with_go_downloader(
    car_id: str,
    manufacturer_id: str,
    logo_url: Optional[str],
    hero_urls: List[str],
    thumb_urls: List[str],
    image_dir: Path,
    go_binary: str,
    workers: int,
    timeout: int,
    retries: int,
) -> Tuple[Optional[str], List[Dict[str, str]]]:
    jobs: List[Dict[str, object]] = []
    if logo_url and not logo_url.startswith("data:"):
        jobs.append(
            {
                "job_id": "logo",
                "url": normalize_url(logo_url),
                "dest_rel": f"manufacturers/{manufacturer_id}/logo",
            }
        )
    for idx, url in enumerate(hero_urls, start=1):
        if not url or url.startswith("data:"):
            continue
        jobs.append(
            {
                "job_id": f"hero_{idx}",
                "url": normalize_url(url),
                "dest_rel": f"cars/{car_id}/{car_id}_hero_{idx:02d}",
            }
        )
    for idx, url in enumerate(thumb_urls, start=1):
        if not url or url.startswith("data:"):
            continue
        jobs.append(
            {
                "job_id": f"thumb_{idx}",
                "url": normalize_url(url),
                "dest_rel": f"cars/{car_id}/{car_id}_thumb_{idx:02d}",
            }
        )
    if not jobs:
        return None, []
    results = run_downloader_jobs(
        binary=go_binary,
        image_dir=image_dir,
        jobs=jobs,
        workers=workers,
        timeout=timeout,
        retries=retries,
    )
    logo_path = None
    images: List[Dict[str, str]] = []
    for job in jobs:
        job_id = str(job["job_id"])
        item = results.get(job_id)
        if not item:
            continue
        if item.get("status") not in {"ok", "skipped"}:
            continue
        path_rel = item.get("path_rel")
        if not path_rel:
            continue
        if job_id == "logo":
            logo_path = str(path_rel)
            continue
        if job_id.startswith("hero_"):
            sort_order = int(job_id.split("_", 1)[1])
            images.append(
                {
                    "image_path": str(path_rel),
                    "sort_order": sort_order,
                    "image_type": "hero",
                }
            )
            continue
        if job_id.startswith("thumb_"):
            sort_order = int(job_id.split("_", 1)[1])
            images.append(
                {
                    "image_path": str(path_rel),
                    "sort_order": sort_order,
                    "image_type": "thumb",
                }
            )
    return logo_path, images


def merge_image_rows_preserve_non_regression(
    existing_rows: List[Dict[str, object]],
    new_rows: List[Dict[str, object]],
    protected_types: Optional[Iterable[str]] = None,
) -> List[Dict[str, object]]:
    protected = {str(item).lower() for item in (protected_types or ["hero", "thumb"])}

    def group_by_type(rows: List[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
        grouped: Dict[str, List[Dict[str, object]]] = {}
        for row in rows:
            image_type = str(row.get("image_type") or "").strip().lower()
            if not image_type:
                image_type = "unknown"
            grouped.setdefault(image_type, []).append(
                {
                    "image_path": str(row.get("image_path") or ""),
                    "sort_order": row.get("sort_order"),
                    "image_type": image_type,
                }
            )
        for values in grouped.values():
            values.sort(key=lambda item: (item.get("sort_order") is None, item.get("sort_order"), item["image_path"]))
        return grouped

    existing_map = group_by_type(existing_rows)
    new_map = group_by_type(new_rows)
    type_order: List[str] = []
    for image_type in ["hero", "thumb"]:
        if image_type in existing_map or image_type in new_map:
            type_order.append(image_type)
    for image_type in list(existing_map.keys()) + list(new_map.keys()):
        if image_type not in type_order:
            type_order.append(image_type)

    merged: List[Dict[str, object]] = []
    for image_type in type_order:
        old_items = existing_map.get(image_type, [])
        new_items = new_map.get(image_type, [])
        if image_type in protected and len(new_items) < len(old_items):
            chosen = old_items
        elif new_items:
            chosen = new_items
        else:
            chosen = old_items
        merged.extend(chosen)
    return merged
