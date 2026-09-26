#!/usr/bin/env python3
"""Validate print-ad files against a versioned competition profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = SKILL_ROOT / "references/competitions/submission-profiles.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(name: str, passed: bool, evidence, severity: str = "error") -> dict:
    return {"name": name, "passed": bool(passed), "severity": severity, "evidence": evidence}


def load_pillow():
    try:
        from PIL import Image, ImageSequence
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Pillow is unavailable in {sys.executable}. Select a Python environment with Pillow "
            "and rerun this script using that interpreter. See image-tool-adaptation.md for "
            "interpreter setup. In Codex, load_workspace_dependencies may locate an available interpreter."
        ) from exc
    return Image, ImageSequence


def dpi_tuple(image) -> tuple[float, float]:
    value = image.info.get("dpi")
    if isinstance(value, (int, float)):
        return float(value), float(value)
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            pass
    return 0.0, 0.0


def target_canvas_mm(size: tuple[int, int], canvas_mm: list[int]) -> tuple[float, float]:
    short_mm, long_mm = sorted(float(value) for value in canvas_mm)
    return (short_mm, long_mm) if size[0] <= size[1] else (long_mm, short_mm)


def geometry_result(size: tuple[int, int], dpi: tuple[float, float], profile: dict) -> dict:
    target_mm = target_canvas_mm(size, profile["canvas_mm"])
    has_dpi = all(value > 0 for value in dpi)
    if has_dpi:
        actual_mm = tuple(size[index] / dpi[index] * 25.4 for index in (0, 1))
        delta_mm = tuple(abs(actual_mm[index] - target_mm[index]) for index in (0, 1))
        geometry_passed = all(value <= profile["canvas_tolerance_mm"] for value in delta_mm)
        effective_dpi = dpi
        basis = "metadata-dpi"
    else:
        effective_dpi = tuple(size[index] / (target_mm[index] / 25.4) for index in (0, 1))
        mismatch = abs(effective_dpi[0] - effective_dpi[1]) / max(effective_dpi)
        geometry_passed = mismatch <= profile["effective_dpi_tolerance_ratio"]
        actual_mm = None
        delta_mm = None
        basis = "pixel-geometry"
    return {
        "basis": basis,
        "target_mm": list(target_mm),
        "actual_mm": list(actual_mm) if actual_mm else None,
        "delta_mm": list(delta_mm) if delta_mm else None,
        "effective_dpi": list(effective_dpi),
        "has_dpi_metadata": has_dpi,
        "geometry_passed": geometry_passed,
    }


def validate_rule_verification(path: Path | None, competition: str, profile: dict) -> tuple[str, dict]:
    if not profile.get("refresh_before_real_submission"):
        return "current", {"required": False}
    if path is None or not path.is_file():
        return "needs_rule_refresh", {"required": True, "verification": str(path) if path else None}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    passed = (
        value.get("competition") == competition
        and value.get("status") == "verified-current"
        and value.get("source_url") == profile.get("source_url")
        and isinstance(value.get("checked_at"), str)
    )
    return ("current" if passed else "needs_rule_refresh"), value


def self_check(profiles: Path) -> int:
    result = {
        "schema_version": "0.1.1",
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "profiles": str(profiles.resolve()),
        "profiles_present": profiles.is_file(),
    }
    try:
        Image, _ = load_pillow()
        result["pillow_version"] = getattr(Image, "__version__", "unknown")
        result["pillow_status"] = "available"
    except RuntimeError as exc:
        result["pillow_version"] = None
        result["pillow_status"] = "missing"
        result["dependency_error"] = str(exc)
    try:
        from knowledge_pack_contract import validate_pack

        result["knowledge_pack"] = validate_pack()
    except Exception as exc:
        result["knowledge_pack"] = {"status": "failed", "errors": [str(exc)]}
    result["status"] = (
        "passed"
        if result["profiles_present"]
        and result["pillow_status"] == "available"
        and result["knowledge_pack"].get("status") == "passed"
        else "failed"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


def validate_file(path: Path, profile: dict, Image, ImageSequence) -> tuple[dict, list[dict]]:
    with Image.open(path) as image:
        image_format = image.format
        size = image.size
        dpi = dpi_tuple(image)
        frames = [
            {"index": index, "mode": frame.mode, "size": list(frame.size)}
            for index, frame in enumerate(ImageSequence.Iterator(image))
        ]
        allowed_modes = set(profile["allowed_modes_by_format"].get(image_format, []))
        frames_valid = bool(frames) and all(
            frame["mode"] in allowed_modes and tuple(frame["size"]) == size for frame in frames
        )
        geometry = geometry_result(size, dpi, profile)
        require_metadata = bool(profile.get("require_dpi_metadata"))
        minimum_dpi_passed = (
            (geometry["has_dpi_metadata"] or not require_metadata)
            and all(value + 0.5 >= profile["min_dpi"] for value in geometry["effective_dpi"])
        )
        result = {
            "path": str(path.resolve()),
            "format": image_format,
            "mode": image.mode,
            "frames": frames,
            "size": list(size),
            "dpi_metadata": list(dpi),
            "geometry": geometry,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    checks = [
        check(f"{path.name}:format", image_format in profile["allowed_formats"], image_format),
        check(f"{path.name}:color-mode", frames_valid, {"allowed_modes": sorted(allowed_modes), "frames": frames}),
        check(
            f"{path.name}:minimum-dpi",
            minimum_dpi_passed,
            {
                "minimum": profile["min_dpi"],
                "effective": geometry["effective_dpi"],
                "metadata_required": require_metadata,
                "metadata_present": geometry["has_dpi_metadata"],
            },
        ),
        check(f"{path.name}:a3-geometry", geometry["geometry_passed"], geometry),
        check(
            f"{path.name}:file-size",
            path.stat().st_size <= profile["max_bytes_per_file"],
            {"actual": path.stat().st_size, "max": profile["max_bytes_per_file"]},
        ),
    ]
    return result, checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", choices=["daguangsai", "academy-award"])
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--include", default="*", help="Glob selecting artwork files inside input-dir")
    parser.add_argument("--aigc-used", choices=["yes", "no", "unknown"], default="unknown")
    parser.add_argument("--aigc-record", type=Path)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--real-submission", action="store_true")
    parser.add_argument("--rule-verification", type=Path)
    args = parser.parse_args()

    if args.self_check:
        return self_check(args.profiles)
    for name in ("competition", "input_dir", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required unless --self-check is used")
    if not args.input_dir.is_dir():
        parser.error(f"Input directory does not exist: {args.input_dir}")

    profiles_document = json.loads(args.profiles.read_text(encoding="utf-8-sig"))
    profile = profiles_document["profiles"][args.competition]
    try:
        Image, ImageSequence = load_pillow()
    except RuntimeError as exc:
        print(f"DEPENDENCY ERROR: {exc}", file=sys.stderr)
        return 2
    allowed_extensions = {value.lower() for value in profile["allowed_extensions"]}
    files = sorted(
        path for path in args.input_dir.glob(args.include)
        if path.is_file() and path.suffix.lower() in allowed_extensions
    )
    checks = [check("series-count", 1 <= len(files) <= profile["max_files"], {"found": len(files), "max": profile["max_files"]})]
    file_results = []
    for path in files:
        result, file_checks = validate_file(path, profile, Image, ImageSequence)
        file_results.append(result)
        checks.extend(file_checks)
    if profile.get("aigc_record_required_when_used"):
        if args.aigc_used == "yes":
            exists = bool(args.aigc_record and args.aigc_record.is_file() and args.aigc_record.stat().st_size > 0)
            checks.append(check("aigc-record-present", exists, str(args.aigc_record.resolve()) if args.aigc_record else None, "warning"))
        elif args.aigc_used == "unknown":
            checks.append(check("aigc-use-declared", False, "Post-delivery reminder: verify actual AI use for platform disclosure", "warning"))
        else:
            checks.append(check("aigc-use-declared", True, "no"))

    failures = [item for item in checks if not item["passed"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["passed"] and item["severity"] == "warning"]
    technical_status = "pass" if not failures else "fail"
    if args.real_submission:
        rule_status, rule_evidence = validate_rule_verification(args.rule_verification, args.competition, profile)
    else:
        rule_status = profile["publication_status"]
        rule_evidence = {"source_url": profile["source_url"], "checked_at": profile["checked_at"]}
    payload = {
        "schema_version": "0.1.1",
        "competition": args.competition,
        "profile_snapshot": profile["snapshot"],
        "technical_validation_status": technical_status,
        "rule_snapshot_status": rule_status,
        "rule_evidence": rule_evidence,
        "checks_total": len(checks),
        "checks_passed": sum(item["passed"] for item in checks),
        "checks_failed": len(failures),
        "failure_names": [item["name"] for item in failures],
        "warnings": [item["name"] for item in warnings],
        "files": file_results,
        "checks": checks,
        "submission_ready": False,
        "submission_ready_reason": "Technical checks do not prove current registration fields, content judgment, rights, or an actual upload.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_keys = ("technical_validation_status", "rule_snapshot_status", "checks_total", "checks_passed", "checks_failed", "failure_names", "warnings")
    print(json.dumps({key: payload[key] for key in summary_keys}, ensure_ascii=False))
    return 0 if technical_status == "pass" and (not args.real_submission or rule_status == "current") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
