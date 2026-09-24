#!/usr/bin/env python3
"""Validate a print-ad run manifest and its structured quality gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quality_gate_contract import validate_quality_gate_results
from review_contract import validate_review_contract
from visual_review_contract import validate_visual_review
from visual_generation_capability_contract import validate_visual_generation_capability

sys.dont_write_bytecode = True

BASE_ARTIFACTS = (
    "brief_evidence", "direction_cards", "concept_gate", "quality_gate_results", "run_status",
)
PRODUCTION_ARTIFACTS = (
    "official_asset_manifest", "production_manifest", "human_visual_review",
    "technical_validation",
)
DELIVERY_ARTIFACTS = ("delivery_manifest",)
RUN_SCOPE_ARTIFACTS = {
    "concept-only": BASE_ARTIFACTS,
    "production-candidate": BASE_ARTIFACTS + PRODUCTION_ARTIFACTS,
    "delivery-candidate": BASE_ARTIFACTS + PRODUCTION_ARTIFACTS + DELIVERY_ARTIFACTS,
}
RUN_SCOPE_GATES = {
    "concept-only": {"print-ad.brief-evidence", "print-ad.direction-distinctness"},
    "production-candidate": {
        "print-ad.brief-evidence", "print-ad.direction-distinctness",
        "print-ad.visual-relation-prototype", "print-ad.official-asset-fidelity",
        "print-ad.series-increment", "print-ad.human-visual-quality",
        "print-ad.technical-delivery",
    },
    "delivery-candidate": {
        "print-ad.brief-evidence", "print-ad.direction-distinctness",
        "print-ad.visual-relation-prototype", "print-ad.official-asset-fidelity",
        "print-ad.series-increment", "print-ad.human-visual-quality",
        "print-ad.technical-delivery",
    },
}


def check(name: str, passed: bool, evidence: object) -> dict:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def safe_path(run_dir: Path, relative: object) -> tuple[Path | None, str | None]:
    if not isinstance(relative, str) or not relative.strip():
        return None, "path must be a non-empty string"
    candidate = Path(relative)
    if candidate.is_absolute():
        return None, "absolute paths are forbidden"
    resolved = (run_dir / candidate).resolve()
    if resolved != run_dir and run_dir not in resolved.parents:
        return None, "path escapes run directory"
    return resolved, None


def validate(run_dir: Path, manifest_path: Path) -> dict:
    run_dir = run_dir.resolve()
    checks: list[dict] = []
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        return {"schema_version": "0.1.0", "status": "failed", "checks": [], "errors": [str(exc)]}

    checks.append(check("manifest-schema", manifest.get("schema_version") in {"0.1.0", "0.2.0", "0.3.0", "0.4.0"}, manifest.get("schema_version")))
    checks.append(check("category-print-ad", manifest.get("category") == "print-ad", manifest.get("category")))
    run_scope = manifest.get("run_scope")
    checks.append(check("run-scope", run_scope in RUN_SCOPE_ARTIFACTS, run_scope))
    checks.extend(validate_visual_generation_capability(manifest, run_scope))
    checks.append(check("identity-fields", all(isinstance(manifest.get(key), str) and manifest[key] for key in ("run_id", "competition", "brief_id", "selected_direction", "series_mode")), {key: manifest.get(key) for key in ("run_id", "competition", "brief_id", "selected_direction")}))
    method_status = manifest.get("method_validation_status", "not-claimed")
    checks.append(check("method-validation-status", method_status in {"not-claimed", "method-validated"}, method_status))

    artifacts = manifest.get("artifacts")
    checks.append(check("artifact-map", isinstance(artifacts, dict), type(artifacts).__name__))
    resolved: dict[str, Path] = {}
    if isinstance(artifacts, dict):
        for key in RUN_SCOPE_ARTIFACTS.get(run_scope, BASE_ARTIFACTS):
            path, error = safe_path(run_dir, artifacts.get(key))
            present = path is not None and path.is_file()
            checks.append(check(f"artifact:{key}", present and error is None, error or str(path)))
            if present and error is None:
                resolved[key] = path

        if run_scope in {"production-candidate", "delivery-candidate"}:
            aigc_used = manifest.get("aigc_used")
            checks.append(check("aigc-use-declaration", aigc_used in {"yes", "no", "unknown"}, aigc_used))
            if run_scope == "delivery-candidate":
                checks.append(check("aigc-use-resolved", aigc_used in {"yes", "no"}, aigc_used))
            if aigc_used == "yes":
                path, error = safe_path(run_dir, artifacts.get("aigc_record"))
                present = path is not None and path.is_file()
                checks.append(check("artifact:aigc_record", present and error is None, error or str(path)))
                if present and error is None:
                    resolved["aigc_record"] = path

    if "quality_gate_results" in resolved:
        checks.extend(validate_quality_gate_results(
            run_dir, resolved["quality_gate_results"], "print-ad", manifest.get("run_id"),
            RUN_SCOPE_GATES.get(run_scope, set()),
        ))

    if method_status == "method-validated":
        used = manifest.get("method_cards_used")
        rejected = manifest.get("method_cards_rejected", [])
        checks.append(check("method-cards-used", isinstance(used, list) and bool(used) and len(used) == len(set(used)), used))
        checks.append(check("method-cards-rejected", isinstance(rejected, list) and len(rejected) == len(set(rejected)), rejected))
        method_path, method_error = safe_path(run_dir, artifacts.get("method_application") if isinstance(artifacts, dict) else None)
        present = method_path is not None and method_path.is_file() and method_error is None
        checks.append(check("artifact:method_application", present, method_error or str(method_path)))
        if present and isinstance(used, list):
            method_text = method_path.read_text(encoding="utf-8-sig")
            checks.append(check("used-methods-documented", all(item in method_text for item in used), used))

    checks.extend(validate_visual_review(run_dir, manifest))
    review_checks = validate_review_contract(run_dir, manifest)
    # Historical validation stays reproducible, but is never new-contract acceptance.
    if manifest.get("schema_version") == "0.4.0":
        checks.extend(review_checks)
    failed = [item["name"] for item in checks if not item["passed"]]
    return {
        "schema_version": "0.1.0", "run_id": manifest.get("run_id"),
        "run_dir": str(run_dir), "manifest": str(manifest_path.resolve()),
        "status": "passed" if not failed else "failed", "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed), "failure_names": failed, "review_contract_status": "verified" if all(c["passed"] for c in review_checks) else ("failed" if manifest.get("schema_version") == "0.4.0" else "legacy-not-verified"), "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        print(json.dumps({
            "schema_version": "0.1.0", "status": "passed",
            "run_scope_artifacts": {key: list(value) for key, value in RUN_SCOPE_ARTIFACTS.items()},
            "run_scope_gates": {key: sorted(value) for key, value in RUN_SCOPE_GATES.items()},
            "method_validation_statuses": ["not-claimed", "method-validated"],
        }, ensure_ascii=False))
        return 0
    if args.run_dir is None or args.output is None:
        parser.error("--run-dir and --output are required unless --self-check is used")
    run_dir = args.run_dir.resolve()
    manifest = args.manifest.resolve() if args.manifest else run_dir / "print-ad-run-manifest.json"
    result = validate(run_dir, manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks_total", "checks_passed", "failure_names")}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
