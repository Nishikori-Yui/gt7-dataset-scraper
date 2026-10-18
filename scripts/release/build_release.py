#!/usr/bin/env python3
import argparse
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.release.release_native import (
    PLATFORM_CONFIG,
    build_go_binaries,
    release_basename,
)
from scripts.release.release_package import (
    copy_launcher,
    copy_native,
    copy_project,
    make_archive,
    write_manifest,
    write_sha256sums,
)


def build_release(args: argparse.Namespace) -> Path:
    cfg = PLATFORM_CONFIG[args.platform]
    if not args.skip_build:
        build_go_binaries(cfg, args.platform)

    package_name = release_basename(args.version, args.platform)
    stage_root = Path(args.out_dir).resolve() / package_name
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)
    copy_project(stage_root)
    copy_launcher(stage_root, args.platform)
    copy_native(stage_root, args.platform)
    write_manifest(
        stage_root,
        platform_id=args.platform,
        version=args.version,
    )
    write_sha256sums(stage_root)
    archive = make_archive(stage_root, Path(args.out_dir).resolve(), args.platform, args.version)

    print(f"[ok] package dir: {stage_root}")
    print(f"[ok] archive: {archive}")
    return stage_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package GT7 source and Go tools; requires Python on the target machine.")
    parser.add_argument("--platform", choices=sorted(PLATFORM_CONFIG.keys()), required=True)
    parser.add_argument("--version", required=True, help="Version/tag string, for example v1.2.3")
    parser.add_argument("--out-dir", default="./dist/release", help="Output directory for package and archive")
    parser.add_argument("--skip-build", action="store_true", help="Skip native build steps and reuse local/bin artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_release(args)


if __name__ == "__main__":
    main()
