import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Optional

import requests


def normalize_image_extension(ext: str) -> str:
    lowered = (ext or "").strip().lower()
    if not lowered:
        return ".jpg"
    if lowered in {".jpe", ".jpeg"}:
        return ".jpg"
    return lowered


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown"


def guess_extension(url: str, content_type: Optional[str]) -> str:
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return normalize_image_extension(ext)
    parsed = re.split(r"[?#]", url)[0]
    ext = Path(parsed).suffix
    if ext:
        return normalize_image_extension(ext)
    return ".jpg"


def stable_filename_from_url(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return digest


def download_file(url: str, path: Path, session: requests.Session, timeout: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    final_path = path
    if path.suffix == "":
        ext = guess_extension(url, None)
        final_path = path.with_suffix(ext)
    if final_path.exists():
        return final_path
    with session.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type")
        ext = guess_extension(url, content_type)
        if path.suffix == "":
            final_path = path.with_suffix(ext)
        tmp_path = final_path.with_suffix(final_path.suffix + ".part")
        with tmp_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
        tmp_path.replace(final_path)
    return final_path


def looks_like_image_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(lowered.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]) or "image" in lowered
