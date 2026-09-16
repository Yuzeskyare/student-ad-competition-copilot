#!/usr/bin/env python3
"""Validate the active or explicitly selected bundled knowledge pack."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from knowledge_pack_contract import jsonl_rows, resolve_pack, validate_pack

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, help="Explicit candidate pack; omission resolves version.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_pack(args.pack)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
