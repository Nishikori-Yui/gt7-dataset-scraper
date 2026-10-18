#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def doctor(root: Path, packaged: bool, as_json: bool) -> None:
    native = root / "local" / "bin"
    payload = {
        "packaged": packaged,
        "project_root": str(root),
        "native_dir": str(native),
        "manifest": str(root / "manifest.json") if packaged else "",
        "python": sys.executable,
        "native_bins": {
            name: any((native / candidate).is_file() for candidate in (name, name + ".exe"))
            for name in ("gt7-catalog-go", "gt7-downloader")
        },
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for key in ("packaged", "project_root", "native_dir", "python"):
        print(f"{key}: {payload[key]}")
    print("tools:")
    for name, available in payload["native_bins"].items():
        print(f"  {name}: {'available' if available else 'not installed'}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print("gt7db <scrape|build-dbs|query|doctor> [args]")
        return

    command, passthrough = args[0], args[1:]
    if command not in {"scrape", "build-dbs", "query", "doctor"}:
        raise SystemExit(f"error: unsupported command {command!r}; expected scrape, build-dbs, query, doctor")

    root = Path(__file__).resolve().parents[1]
    packaged = (root / "manifest.json").is_file()
    if command == "doctor":
        doctor(root, packaged, "--json" in passthrough)
        return

    sys.path.insert(0, str(root))
    sys.argv = [f"gt7db {command}", *passthrough]
    if command == "scrape":
        from gt7_scraper.cli import main as run
    elif command == "build-dbs":
        from scripts.build_dbs import main as run
    else:
        from gt7_query.cli import main as run
    run()


if __name__ == "__main__":
    main()
