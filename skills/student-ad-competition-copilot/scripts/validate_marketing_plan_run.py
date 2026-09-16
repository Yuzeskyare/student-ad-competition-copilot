#!/usr/bin/env python3
"""Validate completeness and traceability of a marketing-plan production run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from quality_gate_contract import validate_quality_gate_results

sys.dont_write_bytecode = True

CONCEPT_ARTIFACTS = (
    "brief_evidence", "brief_constraints", "research_synthesis", "evidence_register",
    "reference_review", "direction_cards", "method_application", "concept_gate",
    "quality_gate_results", "run_status",
)
PRODUCTION_ARTIFACTS = ("page_blueprint", "budget_kpi", "sample_review")
DELIVERY_ARTIFACTS = ("full_deck_review", "technical_validation")
RUN_SCOPE_ARTIFACTS = {
    "concept-only": CONCEPT_ARTIFACTS,
    "production-candidate": CONCEPT_ARTIFACTS + PRODUCTION_ARTIFACTS,
    "delivery-candidate": CONCEPT_ARTIFACTS + PRODUCTION_ARTIFACTS + DELIVERY_ARTIFACTS,
}
# Backward-compatible export for existing fixture builders; new code should select by run_scope.
REQUIRED_ARTIFACTS = RUN_SCOPE_ARTIFACTS["delivery-candidate"]
RUN_SCOPE_GATES = {
    "concept-only": {
        "marketing-plan.research-evidence", "marketing-plan.insight",
        "marketing-plan.strategy-intermediary",
    },
    "production-candidate": {
        "marketing-plan.research-evidence", "marketing-plan.insight",
        "marketing-plan.strategy-intermediary", "marketing-plan.five-page-content",
        "marketing-plan.execution-engineering",
    },
    "delivery-candidate": {
        "marketing-plan.research-evidence", "marketing-plan.insight",
        "marketing-plan.strategy-intermediary", "marketing-plan.five-page-content",
        "marketing-plan.execution-engineering", "marketing-plan.full-deck-human-quality",
        "marketing-plan.technical-delivery",
    },
}
PASS_STATES = {"passed", "passed-with-boundaries"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def check(name: str, passed: bool, evidence: object) -> dict:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


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


def pptx_slide_count(path: Path) -> int | None:
    try:
        with zipfile.ZipFile(path) as archive:
            return sum(1 for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
    except (OSError, zipfile.BadZipFile):
        return None


def technical_pass(payload: dict, final_hash: str | None) -> tuple[bool, dict]:
    direct = payload.get("technical_validation_status") == "pass" and not payload.get("error_failures")
    finalizer = (
        payload.get("packageIntegrity", {}).get("status") == "pass"
        and payload.get("presentationLayout", {}).get("finding_count") == 0
        and payload.get("fontSelection", {}).get("passed") is True
        and payload.get("firstPartyImport", {}).get("passed") is True
        and payload.get("nativeTableArithmetic", {}).get("passed") is True
    )
    linked_hash = payload.get("finalSha256") or payload.get("input", {}).get("sha256")
    return (direct or finalizer) and linked_hash == final_hash, {
        "direct_pass": direct, "presentation_finalizer_pass": finalizer,
        "linked_hash": linked_hash, "final_hash": final_hash,
    }


def number(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def budget_kpi_checks(payload: dict) -> list[dict]:
    checks: list[dict] = []
    budget = payload.get("budget", {})
    status = budget.get("status")
    checks.append(check("budget-status", status in {"specified", "open-decision", "not-required-by-brief"}, status))
    items = budget.get("items", [])
    if items:
        arithmetic_ok = True
        total = Decimal("0")
        for item in items:
            quantity = number(item.get("quantity")) if isinstance(item, dict) else None
            unit_cost = number(item.get("unit_cost")) if isinstance(item, dict) else None
            amount = number(item.get("amount")) if isinstance(item, dict) else None
            if None in (quantity, unit_cost, amount) or quantity * unit_cost != amount or not item.get("basis"):
                arithmetic_ok = False
                continue
            total += amount
        declared = number(budget.get("declared_total"))
        checks.append(check("budget-arithmetic", arithmetic_ok and declared == total, {"declared": str(declared), "calculated": str(total)}))
    elif status == "specified":
        checks.append(check("budget-arithmetic", False, "specified budget requires items"))

    kpi = payload.get("kpi", {})
    kpi_status = kpi.get("status")
    checks.append(check("kpi-status", kpi_status in {"specified", "open-decision", "not-required-by-brief"}, kpi_status))
    metrics = kpi.get("metrics", [])
    if kpi_status != "not-required-by-brief":
        valid_metrics = isinstance(metrics, list) and len(metrics) >= 1 and all(
            isinstance(metric, dict)
            and all(isinstance(metric.get(field), str) and metric[field].strip() for field in ("metric", "formula", "source", "boundary"))
            for metric in metrics
        )
        checks.append(check("kpi-measurement-contract", valid_metrics, len(metrics) if isinstance(metrics, list) else None))
    return checks


def validate(run_dir: Path, manifest_path: Path) -> dict:
    run_dir = run_dir.resolve()
    checks: list[dict] = []
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        return {"schema_version": "0.1.0", "status": "failed", "run_dir": str(run_dir), "checks": [], "errors": [str(exc)]}

    checks.append(check("manifest-schema", manifest.get("schema_version") in {"0.1.0", "0.2.0"}, manifest.get("schema_version")))
    checks.append(check("category-marketing-plan", manifest.get("category") == "marketing-plan", manifest.get("category")))
    run_scope = manifest.get("run_scope", "delivery-candidate" if manifest.get("schema_version") == "0.1.0" else None)
    checks.append(check("run-scope", run_scope in RUN_SCOPE_ARTIFACTS, run_scope))
    checks.append(check("identity-fields", all(isinstance(manifest.get(key), str) and manifest[key] for key in (
        "run_id", "competition", "proposition_id", "selected_direction"
    )), {key: manifest.get(key) for key in ("run_id", "competition", "proposition_id")}))
    aigc_used = manifest.get("aigc_used")
    if manifest.get("schema_version") == "0.1.0" and aigc_used is None:
        aigc_used = "yes" if isinstance(manifest.get("artifacts"), dict) and manifest["artifacts"].get("aigc_record") else "no"
    if run_scope in {"production-candidate", "delivery-candidate"}:
        checks.append(check("aigc-use-declaration", aigc_used in {"yes", "no", "unknown"}, aigc_used))
    if run_scope == "delivery-candidate":
        checks.append(check("aigc-use-resolved", aigc_used in {"yes", "no"}, aigc_used))

    methods = manifest.get("method_cards_used")
    rejected = manifest.get("method_cards_rejected", [])
    checks.append(check("method-cards-used", isinstance(methods, list) and len(methods) >= 1 and len(methods) == len(set(methods)), methods))
    checks.append(check("method-cards-rejected", isinstance(rejected, list) and len(rejected) == len(set(rejected)), rejected))

    directions = manifest.get("directions")
    direction_count = len(directions) if isinstance(directions, list) else 0
    checks.append(check("direction-count-3-to-5", 3 <= direction_count <= 5, direction_count))
    if isinstance(directions, list):
        ids = [item.get("direction_id") for item in directions if isinstance(item, dict)]
        strategies = [item.get("one_line_strategy") for item in directions if isinstance(item, dict)]
        selected = [item.get("direction_id") for item in directions if isinstance(item, dict) and item.get("status") == "selected"]
        checks.append(check("directions-distinct", len(ids) == direction_count and len(set(ids)) == direction_count and len(set(strategies)) == direction_count, {"ids": ids, "strategies": strategies}))
        checks.append(check("direction-selection-linked", selected == [manifest.get("selected_direction")], selected))

    checks.append(check("formal-quality-gates-authoritative", True, {
        "source": manifest.get("artifacts", {}).get("quality_gate_results") if isinstance(manifest.get("artifacts"), dict) else None,
        "legacy_quality_gates_ignored": "quality_gates" in manifest,
    }))

    artifacts = manifest.get("artifacts")
    checks.append(check("artifact-map", isinstance(artifacts, dict), type(artifacts).__name__))
    resolved: dict[str, Path] = {}
    if isinstance(artifacts, dict):
        for key in RUN_SCOPE_ARTIFACTS.get(run_scope, CONCEPT_ARTIFACTS):
            path, error = safe_path(run_dir, artifacts.get(key))
            present = path is not None and path.is_file()
            checks.append(check(f"artifact:{key}", present and error is None, error or str(path)))
            if present and error is None:
                resolved[key] = path
        if run_scope in {"production-candidate", "delivery-candidate"} and aigc_used == "yes":
            path, error = safe_path(run_dir, artifacts.get("aigc_record"))
            present = path is not None and path.is_file()
            checks.append(check("artifact:aigc_record", present and error is None, error or str(path)))
            if present and error is None:
                resolved["aigc_record"] = path
        if "quality_gate_results" in resolved:
            checks.extend(validate_quality_gate_results(
                run_dir, resolved["quality_gate_results"], "marketing-plan", manifest.get("run_id"),
                RUN_SCOPE_GATES.get(run_scope, set()),
            ))

    final = manifest.get("final_artifact")
    final_path = None
    final_hash = None
    if run_scope == "delivery-candidate" and isinstance(final, dict):
        final_path, final_error = safe_path(run_dir, final.get("path"))
        if final_path is not None and final_path.is_file() and final_error is None:
            final_hash = sha256(final_path)
        count = pptx_slide_count(final_path) if final_path and final_path.is_file() else None
        checks.append(check("final-artifact", final_hash == final.get("sha256") and count == final.get("slide_count") and final.get("authoring_mode") == "native-editable-pptx", {"path_error": final_error, "sha256": final_hash, "slide_count": count}))
    elif run_scope == "delivery-candidate":
        checks.append(check("final-artifact", False, type(final).__name__))

    try:
        constraints = load_json(resolved["brief_constraints"])
        concept = load_json(resolved["concept_gate"])
        budget_kpi = load_json(resolved["budget_kpi"]) if run_scope in {"production-candidate", "delivery-candidate"} else None
        technical = load_json(resolved["technical_validation"]) if run_scope == "delivery-candidate" else None
        status = load_json(resolved["run_status"])
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        checks.append(check("linked-json-readable", False, str(exc)))
    else:
        checks.append(check("linked-json-readable", True, "all linked JSON objects parsed"))
        checks.append(check("brief-authorized", constraints.get("category_authorized") is True, constraints.get("category_authorized")))
        checks.append(check("concept-selection-linked", concept.get("selected_direction") == manifest.get("selected_direction"), concept.get("selected_direction")))
        if isinstance(budget_kpi, dict):
            checks.extend(budget_kpi_checks(budget_kpi))
        if isinstance(technical, dict):
            passed, evidence = technical_pass(technical, final_hash)
            checks.append(check("technical-validation-linked", passed, evidence))
        checks.append(check("run-method-complete", status.get("method_run_complete") is True, status.get("method_run_complete")))
        if run_scope in {"production-candidate", "delivery-candidate"}:
            checks.append(check("run-content-review", status.get("content_review_status") in PASS_STATES, status.get("content_review_status")))
        if run_scope == "delivery-candidate":
            checks.append(check("submission-status-explicit", isinstance(status.get("submission_ready"), bool), status.get("submission_ready")))

    failed = [item["name"] for item in checks if not item["passed"]]
    return {
        "schema_version": "0.1.0",
        "run_id": manifest.get("run_id"),
        "run_dir": str(run_dir),
        "manifest": str(manifest_path.resolve()),
        "status": "passed" if not failed else "failed",
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "failure_names": failed,
        "checks": checks,
    }


def self_check() -> int:
    print(json.dumps({
        "schema_version": "0.1.0", "status": "passed", "python_executable": sys.executable,
        "run_scope_artifacts": {key: list(value) for key, value in RUN_SCOPE_ARTIFACTS.items()},
        "run_scope_gates": {key: sorted(value) for key, value in RUN_SCOPE_GATES.items()},
        "direction_range": [3, 5],
    }, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        return self_check()
    if args.run_dir is None or args.output is None:
        parser.error("--run-dir and --output are required unless --self-check is used")
    run_dir = args.run_dir.resolve()
    manifest = args.manifest.resolve() if args.manifest else run_dir / "marketing-plan-run-manifest.json"
    result = validate(run_dir, manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks_total", "checks_passed", "failure_names")}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
