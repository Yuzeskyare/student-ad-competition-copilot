#!/usr/bin/env python3
"""Check a bound production request immediately before a tool or local command."""
import argparse
from datetime import datetime, timezone
import json
import subprocess
import sys

from review_contract import inside, load, preflight, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--manifest", required=True, help="Run-relative manifest path")
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--output", required=True, help="Run-relative receipt path")
    parser.add_argument("--execute", action="store_true", help="Execute the explicitly recorded local command, without a shell, after rechecking")
    args = parser.parse_args()
    from pathlib import Path
    root = Path(args.run_dir).resolve()
    try:
        target = inside(root, args.output)
        manifest_path = inside(root, args.manifest)
        if target.exists():
            raise ValueError("Use a new receipt path; do not overwrite production history")
        manifest = load(manifest_path)
        receipt = preflight(root, manifest, args.request_id)
        receipt["executed"] = False
        command = receipt["request"].get("command")
        if args.execute and (not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command)):
            raise ValueError("--execute requires an explicit command array in the approved request")
        if args.execute:
            # Re-read immediately before dispatch, so a change after the first
            # check cannot reuse a stale receipt.
            fresh = preflight(root, load(manifest_path), args.request_id)
            if any(fresh[k] != receipt[k] for k in ("request_sha256", "decision_sha256", "decision_id")) or fingerprint(load(manifest_path)) != fingerprint(manifest):
                raise ValueError("Inputs changed during preflight; review the new request")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.execute:
            receipt["action_started_at"] = datetime.now(timezone.utc).isoformat()
            target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            try:
                process = subprocess.run(command, cwd=root, shell=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
                receipt.update(executed=True, command_returncode=process.returncode,
                               stdout_tail=process.stdout[-2000:], stderr_tail=process.stderr[-2000:])
            except OSError as exc:
                receipt.update(executed=False, command_returncode=1, execution_error=str(exc))
            receipt["action_finished_at"] = datetime.now(timezone.utc).isoformat()
            target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: receipt.get(k) for k in ("status", "request_id", "authorization_kind", "content_pass_granted", "executed", "command_returncode")}, ensure_ascii=False))
        return receipt.get("command_returncode", 0)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "executed": False}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
