#!/usr/bin/env python3
"""Validate completeness and traceability of an ad-copy production run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from quality_gate_contract import validate_quality_gate_results

sys.dont_write_bytecode = True

CONCEPT_ARTIFACTS = (
    "brief_evidence",
    "brief_constraints",
    "research_notes",
    "method_query",
    "direction_cards",
    "method_application",
    "concept_gate",
    "quality_gate_results",
    "run_status",
)
PRODUCTION_ARTIFACTS = (
    "candidate_review",
)
DELIVERY_ARTIFACTS = (
    "final_copy",
    "technical_validation",
)
RUN_SCOPE_ARTIFACTS = {
    "concept-only": CONCEPT_ARTIFACTS,
    "production-candidate": CONCEPT_ARTIFACTS + PRODUCTION_ARTIFACTS,
    "delivery-candidate": CONCEPT_ARTIFACTS + PRODUCTION_ARTIFACTS + DELIVERY_ARTIFACTS,
}
RUN_SCOPE_GATES = {
    "concept-only": {"ad-copy.brief-claim", "ad-copy.subtype", "ad-copy.direction-distinctness"},
    "production-candidate": {
        "ad-copy.brief-claim", "ad-copy.subtype", "ad-copy.direction-distinctness",
        "ad-copy.semantic-brand", "ad-copy.subtype-quality", "ad-copy.voice-prosody",
    },
    "delivery-candidate": {
        "ad-copy.brief-claim", "ad-copy.subtype", "ad-copy.direction-distinctness",
        "ad-copy.semantic-brand", "ad-copy.subtype-quality", "ad-copy.voice-prosody",
        "ad-copy.technical-text",
    },
}
PROSODY_REVIEW_SUBTYPES = {"slogan", "short-copy"}


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


def validate(run_dir: Path, manifest_path: Path) -> dict:
    run_dir = run_dir.resolve()
    checks: list[dict] = []
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        return {"schema_version": "0.1.0", "status": "failed", "run_dir": str(run_dir), "checks": [], "errors": [str(exc)]}

    checks.append(check("manifest-schema", manifest.get("schema_version") in {"0.1.0", "0.2.0"}, manifest.get("schema_version")))
    checks.append(check("category-ad-copy", manifest.get("category") == "ad-copy", manifest.get("category")))
    run_scope = manifest.get("run_scope", "delivery-candidate" if manifest.get("schema_version") == "0.1.0" else None)
    checks.append(check("run-scope", run_scope in RUN_SCOPE_ARTIFACTS, run_scope))
    identity_keys = ["run_id", "competition", "subtype", "brief_id", "selected_direction"]
    if run_scope in {"production-candidate", "delivery-candidate"}:
        identity_keys.append("selected_candidate_id")
    checks.append(check("identity-fields", all(isinstance(manifest.get(key), str) and manifest[key] for key in (
        identity_keys
    )), {key: manifest.get(key) for key in identity_keys}))
    aigc_used = manifest.get("aigc_used")
    if manifest.get("schema_version") == "0.1.0" and aigc_used is None:
        aigc_used = "yes" if isinstance(manifest.get("artifacts"), dict) and manifest["artifacts"].get("aigc_record") else "no"
    if run_scope in {"production-candidate", "delivery-candidate"}:
        checks.append(check("aigc-use-declaration", aigc_used in {"yes", "no", "unknown"}, aigc_used))
    if run_scope == "delivery-candidate":
        checks.append(check("aigc-use-resolved", aigc_used in {"yes", "no"}, aigc_used))

    artifacts = manifest.get("artifacts")
    checks.append(check("artifact-map", isinstance(artifacts, dict), type(artifacts).__name__))
    resolved_artifacts: dict[str, Path] = {}
    if isinstance(artifacts, dict):
        for key in RUN_SCOPE_ARTIFACTS.get(run_scope, CONCEPT_ARTIFACTS):
            path, error = safe_path(run_dir, artifacts.get(key))
            present = path is not None and path.is_file()
            checks.append(check(f"artifact:{key}", present and error is None, error or str(path)))
            if present and error is None:
                resolved_artifacts[key] = path
        if run_scope in {"production-candidate", "delivery-candidate"} and aigc_used == "yes":
            path, error = safe_path(run_dir, artifacts.get("aigc_record"))
            present = path is not None and path.is_file()
            checks.append(check("artifact:aigc_record", present and error is None, error or str(path)))
            if present and error is None:
                resolved_artifacts["aigc_record"] = path
        if "quality_gate_results" in resolved_artifacts:
            checks.extend(validate_quality_gate_results(
                run_dir, resolved_artifacts["quality_gate_results"], "ad-copy", manifest.get("run_id"),
                RUN_SCOPE_GATES.get(run_scope, set()),
            ))

    method_ids = manifest.get("method_cards_used")
    rejected_ids = manifest.get("method_cards_rejected", [])
    checks.append(check("method-cards-used", isinstance(method_ids, list) and len(method_ids) >= 1 and len(method_ids) == len(set(method_ids)), method_ids))
    checks.append(check("method-cards-rejected", isinstance(rejected_ids, list) and len(rejected_ids) == len(set(rejected_ids)), rejected_ids))
    if "method_application" in resolved_artifacts and isinstance(method_ids, list):
        method_text = resolved_artifacts["method_application"].read_text(encoding="utf-8-sig")
        checks.append(check("used-methods-documented", all(method_id in method_text for method_id in method_ids), method_ids))

    candidates = manifest.get("candidates")
    candidate_by_id: dict[str, dict] = {}
    candidate_hashes: list[str] = []
    candidate_count = len(candidates) if isinstance(candidates, list) else 0
    if run_scope in {"production-candidate", "delivery-candidate"}:
        checks.append(check("candidate-count-3-to-5", 3 <= candidate_count <= 5, candidate_count))
    if run_scope in {"production-candidate", "delivery-candidate"} and isinstance(candidates, list):
        for index, candidate in enumerate(candidates, start=1):
            candidate_id = candidate.get("candidate_id") if isinstance(candidate, dict) else None
            path, error = safe_path(run_dir, candidate.get("path") if isinstance(candidate, dict) else None)
            digest = sha256(path) if path is not None and path.is_file() else None
            valid = (
                isinstance(candidate_id, str) and bool(candidate_id)
                and candidate_id not in candidate_by_id
                and error is None and path is not None and path.is_file()
                and digest == candidate.get("sha256")
            )
            checks.append(check(f"candidate:{index}", valid, {"candidate_id": candidate_id, "path_error": error, "sha256": digest}))
            if valid:
                candidate_by_id[candidate_id] = candidate
                candidate_hashes.append(digest)
    if run_scope in {"production-candidate", "delivery-candidate"}:
        checks.append(check("candidate-drafts-distinct", len(candidate_hashes) == candidate_count and len(set(candidate_hashes)) == candidate_count, candidate_hashes))

    selected_id = manifest.get("selected_candidate_id")
    selected = candidate_by_id.get(selected_id)
    final_path = resolved_artifacts.get("final_copy")
    final_hash = sha256(final_path) if final_path else None
    if run_scope in {"production-candidate", "delivery-candidate"}:
        checks.append(check("selected-candidate-exists", selected is not None, selected_id))
    if run_scope == "delivery-candidate":
        checks.append(check("final-equals-selected-candidate", selected is not None and final_hash == selected.get("sha256"), {"final": final_hash, "selected": selected.get("sha256") if selected else None}))

    try:
        concept = load_json(resolved_artifacts["concept_gate"])
        constraints = load_json(resolved_artifacts["brief_constraints"])
        status = load_json(resolved_artifacts["run_status"])
        review = load_json(resolved_artifacts["candidate_review"]) if run_scope in {"production-candidate", "delivery-candidate"} else None
        technical = load_json(resolved_artifacts["technical_validation"]) if run_scope == "delivery-candidate" else None
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        checks.append(check("linked-json-readable", False, str(exc)))
    else:
        checks.append(check("linked-json-readable", True, "all linked JSON objects parsed"))
        checks.append(check("direction-selection-linked", concept.get("selected_direction") == manifest.get("selected_direction"), concept.get("selected_direction")))
        if isinstance(review, dict):
            selected_reviews = [item for item in review.get("candidates", []) if item.get("candidate_id") == selected_id and item.get("verdict") == "selected"]
            checks.append(check("candidate-review-selection-linked", len(selected_reviews) == 1 and review.get("selected_candidate") == selected_id, review.get("selected_candidate")))
            manual = review.get("manual_content_review", {})
            checks.append(check("manual-content-review", manual.get("status") in {"passed", "passed-with-boundaries"}, manual.get("status")))
            if manifest.get("subtype") in PROSODY_REVIEW_SUBTYPES:
                prosody = manual.get("prosody_review", {})
                prosody_passed = (
                    isinstance(prosody, dict)
                    and prosody.get("status") == "passed"
                    and prosody.get("semantic_logic_first") is True
                    and prosody.get("parallelism_checked") is True
                    and prosody.get("rhythm_read_aloud_checked") is True
                    and prosody.get("rhyme_checked") is True
                    and prosody.get("forced_rhyme") is False
                    and prosody.get("natural_language_pass") is True
                )
                checks.append(check("short-copy-prosody-review", prosody_passed, prosody))

        length_status = constraints.get("length_status", "specified")
        subtype_rule = constraints.get("subtype_constraints", {}).get(manifest.get("subtype"), {})
        open_length_valid = not (
            length_status in {"not-specified", "not-applicable"}
            and (subtype_rule.get("minimum") is not None or subtype_rule.get("maximum") is not None)
        )
        checks.append(check("open-length-null-bounds", open_length_valid, {"length_status": length_status, "rule": subtype_rule}))
        if isinstance(technical, dict):
            checks.append(check("technical-pass", technical.get("technical_validation_status") == "pass" and not technical.get("error_failures"), {
                "status": technical.get("technical_validation_status"), "errors": technical.get("error_failures"),
            }))
            checks.append(check("technical-final-hash-linked", technical.get("input", {}).get("sha256") == final_hash, technical.get("input", {}).get("sha256")))
            if length_status == "not-specified":
                checks.append(check("open-length-warning-linked", "length-unspecified-by-brief" in technical.get("warnings", []), technical.get("warnings")))
        checks.append(check("run-method-complete", status.get("method_run_complete") is True, status.get("method_run_complete")))
        if isinstance(technical, dict):
            checks.append(check("run-technical-status-linked", status.get("technical_validation_status") == technical.get("technical_validation_status"), status.get("technical_validation_status")))
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
    payload = {
        "schema_version": "0.1.0",
        "status": "passed",
        "python_executable": sys.executable,
        "run_scope_artifacts": {key: list(value) for key, value in RUN_SCOPE_ARTIFACTS.items()},
        "run_scope_gates": {key: sorted(value) for key, value in RUN_SCOPE_GATES.items()},
        "candidate_range": [3, 5],
        "prosody_review_subtypes": sorted(PROSODY_REVIEW_SUBTYPES),
    }
    print(json.dumps(payload, ensure_ascii=False))
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
    manifest = args.manifest.resolve() if args.manifest else run_dir / "ad-copy-run-manifest.json"
    result = validate(run_dir, manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks_total", "checks_passed", "failure_names")}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
