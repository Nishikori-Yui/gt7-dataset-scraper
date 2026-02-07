import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .hero_check import (
    evaluate_hero_check_outcome,
    load_hero_expected_counts,
    validate_hero_counts,
    write_hero_diff_reports,
)
from .hero_check_rust import run_rust_hero_check


def run_hero_validation(
    args: argparse.Namespace,
    out_dir: Path,
    per_locale_dbs: List[Path],
    combined_db: Optional[Path],
) -> None:
    if args.hero_check not in {"strict", "soft"}:
        return

    manifest_path = Path(args.hero_manifest)
    ref_counts: Dict[str, int] = load_hero_expected_counts(manifest_path)
    if not ref_counts:
        raise SystemExit(
            f"hero-check {args.hero_check}: hero manifest missing/empty at {manifest_path}. "
            "Generate it via scripts/generate_hero_manifest.py."
        )

    db_targets: List[Path] = []
    db_targets.extend(per_locale_dbs)
    if combined_db is not None:
        db_targets.append(combined_db)

    checked_rows = 0
    all_diffs: List[Dict[str, object]] = []
    if args.hero_check_engine == "rust":
        ok, msg, checked_rows, all_diffs = run_rust_hero_check(
            binary=Path(args.hero_check_rust_bin),
            db_paths=db_targets,
            manifest_path=manifest_path,
            hero_min=max(1, int(args.hero_min)),
        )
        if ok:
            if msg:
                print(msg)
        else:
            if args.backend_fallback == "off":
                raise SystemExit(f"hero-check-engine=rust failed and backend-fallback=off: {msg}")
            print(f"warning: {msg}; falling back to python hero-check", file=sys.stderr)
            checked_rows = 0
            all_diffs = []

    if checked_rows == 0 and not all_diffs:
        for path in db_targets:
            checked, diffs = validate_hero_counts(path, ref_counts, max(1, int(args.hero_min)))
            checked_rows += checked
            all_diffs.extend(diffs)

    write_hero_diff_reports(out_dir, all_diffs)
    mismatch_rows = len(all_diffs)
    should_fail, threshold_desc, mismatch_ratio = evaluate_hero_check_outcome(
        mode=args.hero_check,
        checked_rows=checked_rows,
        mismatch_rows=mismatch_rows,
        soft_max_ratio=float(args.hero_soft_max_ratio),
        soft_max_count=int(args.hero_soft_max_count),
    )
    result_text = "failed" if should_fail else ("warning" if mismatch_rows > 0 else "ok")
    stream = sys.stderr if should_fail or mismatch_rows > 0 else sys.stdout
    print(
        "hero-check summary: "
        f"mode={args.hero_check} "
        f"checked_rows={checked_rows} "
        f"mismatch_rows={mismatch_rows} "
        f"mismatch_ratio={mismatch_ratio:.6f} "
        f"threshold={threshold_desc} "
        f"result={result_text} "
        f"reports=({out_dir / 'hero_diff.csv'}, {out_dir / 'hero_diff.json'})",
        file=stream,
    )
    if should_fail:
        if args.hero_check == "strict":
            raise SystemExit(3)
        raise SystemExit(4)
