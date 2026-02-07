import json
import subprocess
from argparse import Namespace
from typing import Any


def run_go_backend(args: Namespace) -> Any:
    command = [args.query_go_bin, args.command, "--db", args.db]
    if args.command == "list":
        command.extend(["--locale", args.locale, "--sort", args.sort, "--limit", str(args.limit)])
    elif args.command == "car":
        command.extend(["--locale", args.locale, "--car-id", args.car_id])
    elif args.command == "stats":
        command.extend(["--locale", args.locale, "--by", args.by])
    elif args.command == "overview":
        pass
    else:
        raise RuntimeError(f"Unsupported command for go backend: {args.command}")

    proc = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"go query backend failed rc={proc.returncode}: {detail}")
    payload = (proc.stdout or "").strip()
    if not payload:
        raise RuntimeError("go query backend returned empty payload")
    try:
        return json.loads(payload)
    except Exception as exc:
        raise RuntimeError(f"go query backend returned invalid json: {exc}") from exc
