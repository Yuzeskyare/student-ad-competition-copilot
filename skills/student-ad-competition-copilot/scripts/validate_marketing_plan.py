#!/usr/bin/env python3
"""Validate marketing-plan delivery structure, files, evidence, budget, and KPI records."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.dont_write_bytecode = True

try:
    from PIL import Image
except ImportError:  # pragma: no cover - reported by self-check/runtime
    Image = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - reported by self-check/runtime
    PdfReader = None


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = SKILL_ROOT / "references/competitions/marketing-plan-profiles.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def result(name: str, passed: bool, evidence, severity: str = "error") -> dict:
    return {"name": name, "passed": bool(passed), "severity": severity, "evidence": evidence}


def safe_path(root: Path, relative: str) -> tuple[Path | None, str | None]:
    if not isinstance(relative, str) or not relative.strip():
        return None, "path must be a non-empty string"
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None, "path escapes input directory"
    return candidate, None


def normalized_ratio(width: float, height: float) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    return max(width, height) / min(width, height)


def shape_matches(width: float, height: float, shape: str, shapes: dict, tolerance: float) -> bool:
    expected = float(shapes[shape])
    return abs(normalized_ratio(width, height) - expected) <= tolerance


def validate_brief(document: dict, competition: str, profile: dict) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    if document.get("competition") != competition:
        errors.append("competition does not match")
    if not isinstance(document.get("proposition_id"), str) or not document["proposition_id"].strip():
        errors.append("proposition_id is required")
    if not isinstance(document.get("category_authorized"), bool):
        errors.append("category_authorized must be boolean")
    for key in ("required_sections", "required_terms", "prohibited_terms"):
        value = document.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            errors.append(f"{key} must be a list of non-empty strings")
        elif len(value) != len(set(value)):
            errors.append(f"{key} must be unique")
    for key in ("budget_requirement", "kpi_requirement", "research_requirement"):
        if document.get(key, "not-specified") not in {"required", "recommended", "not-required", "not-specified"}:
            errors.append(f"{key} is invalid")
    shapes = document.get("allowed_page_shapes", profile["online_delivery"]["allowed_page_shapes"])
    if not isinstance(shapes, list) or not shapes:
        errors.append("allowed_page_shapes must be a non-empty list")
    elif not set(shapes).issubset(set(profile["online_delivery"]["allowed_page_shapes"])):
        errors.append("allowed_page_shapes expands the competition profile")
    evidence = document.get("evidence")
    if not isinstance(evidence, dict) or not evidence.get("source") or not evidence.get("checked_at"):
        errors.append("evidence.source and evidence.checked_at are required")
    return errors


def decimal_value(value, label: str, errors: list[str]) -> Decimal | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a decimal string")
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        errors.append(f"{label} is not a decimal")
        return None
    if not number.is_finite() or number < 0:
        errors.append(f"{label} must be finite and non-negative")
        return None
    return number


def validate_budget(budget: dict, requirement: str) -> tuple[list[str], dict]:
    errors: list[str] = []
    status = budget.get("status") if isinstance(budget, dict) else None
    if status not in {"specified", "not-required-by-brief", "open-decision"}:
        errors.append("budget.status is invalid")
        return errors, {"status": status}
    if requirement == "required" and status != "specified":
        errors.append("budget is required by the proposition")
    if status != "specified":
        return errors, {"status": status, "requirement": requirement}
    if not isinstance(budget.get("currency"), str) or not budget["currency"].strip():
        errors.append("budget.currency is required when specified")
    items = budget.get("line_items")
    if not isinstance(items, list) or not items:
        errors.append("budget.line_items must be non-empty when specified")
        items = []
    total = Decimal("0")
    ids: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"budget.line_items[{index}] must be an object")
            continue
        for key in ("item_id", "name", "basis"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"budget.line_items[{index}].{key} is required")
        ids.append(item.get("item_id", ""))
        quantity = decimal_value(item.get("quantity"), f"budget.line_items[{index}].quantity", errors)
        unit_cost = decimal_value(item.get("unit_cost"), f"budget.line_items[{index}].unit_cost", errors)
        amount = decimal_value(item.get("amount"), f"budget.line_items[{index}].amount", errors)
        if quantity is not None and unit_cost is not None and amount is not None:
            if quantity * unit_cost != amount:
                errors.append(f"budget.line_items[{index}] quantity × unit_cost does not equal amount")
            total += amount
    if len(ids) != len(set(ids)):
        errors.append("budget item_id values must be unique")
    declared = decimal_value(budget.get("declared_total"), "budget.declared_total", errors)
    if declared is not None and total != declared:
        errors.append("budget line-item sum does not equal declared_total")
    return errors, {"status": status, "requirement": requirement, "calculated_total": str(total), "declared_total": budget.get("declared_total")}


def validate_kpi(kpi: dict, requirement: str) -> tuple[list[str], dict]:
    errors: list[str] = []
    status = kpi.get("status") if isinstance(kpi, dict) else None
    if status not in {"specified", "not-required-by-brief", "open-decision"}:
        errors.append("kpi.status is invalid")
        return errors, {"status": status}
    if requirement == "required" and status != "specified":
        errors.append("KPI is required by the proposition")
    metrics = kpi.get("metrics", [])
    if not isinstance(metrics, list):
        errors.append("kpi.metrics must be an array")
        metrics = []
    if status == "specified" and not metrics:
        errors.append("kpi.metrics must be non-empty when specified")
    ids: list[str] = []
    for index, metric in enumerate(metrics, start=1):
        if not isinstance(metric, dict):
            errors.append(f"kpi.metrics[{index}] must be an object")
            continue
        for key in ("metric_id", "name", "definition", "unit", "formula", "data_source", "frequency", "owner", "stage", "target_status"):
            if not isinstance(metric.get(key), str) or not metric[key].strip():
                errors.append(f"kpi.metrics[{index}].{key} is required")
        if metric.get("target_status") not in {"evidence-backed", "creative-target", "open-decision"}:
            errors.append(f"kpi.metrics[{index}].target_status is invalid")
        ids.append(metric.get("metric_id", ""))
        for key in ("baseline", "target"):
            value = metric.get(key)
            if value is not None and not isinstance(value, (str, int, float)):
                errors.append(f"kpi.metrics[{index}].{key} must be scalar or null")
    if len(ids) != len(set(ids)):
        errors.append("KPI metric_id values must be unique")
    return errors, {"status": status, "requirement": requirement, "metrics": len(metrics)}


def validate_evidence(manifest: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    status = manifest.get("evidence_status")
    rows = manifest.get("evidence_register")
    if status not in {"registered", "no-external-claims"}:
        errors.append("evidence_status is invalid")
    if not isinstance(rows, list):
        errors.append("evidence_register must be an array")
        rows = []
    if status == "registered" and not rows:
        errors.append("registered evidence requires at least one entry")
    if status == "no-external-claims" and rows:
        errors.append("no-external-claims requires an empty evidence register")
    ids: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"evidence_register[{index}] must be an object")
            continue
        for key in ("claim_id", "claim", "source_title", "source_url_or_path", "checked_at", "status"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                errors.append(f"evidence_register[{index}].{key} is required")
        used_at = row.get("used_at")
        if not isinstance(used_at, list) or not used_at or any(not isinstance(value, str) or not value for value in used_at):
            errors.append(f"evidence_register[{index}].used_at must be a non-empty string list")
        if row.get("status") not in {"verified", "proposition-claim", "creative-assumption", "open-question"}:
            errors.append(f"evidence_register[{index}].status is invalid")
        ids.append(row.get("claim_id", ""))
    if len(ids) != len(set(ids)):
        errors.append("evidence claim_id values must be unique")
    return errors, {"status": status, "entries": len(rows)}


def validate_rule_verification(path: Path | None, competition: str, profile: dict) -> tuple[str, dict]:
    if path is None or not path.is_file():
        return "needs_rule_refresh", {"required": True, "verification": str(path) if path else None}
    value = load_json(path)
    passed = (
        value.get("competition") == competition
        and value.get("status") == "verified-current"
        and value.get("source_url") == profile.get("source_url")
        and isinstance(value.get("checked_at"), str)
        and bool(value.get("checked_at"))
        and value.get("registration_fields_checked") is True
    )
    return ("current" if passed else "needs_rule_refresh"), value


def self_check(profiles_path: Path) -> int:
    payload = {
        "schema_version": "0.1.0",
        "python_executable": sys.executable,
        "skill_root": str(SKILL_ROOT),
        "profiles": str(profiles_path.resolve()),
        "pillow_available": Image is not None,
        "pypdf_available": PdfReader is not None,
    }
    try:
        profiles = load_json(profiles_path)
        payload["competitions"] = sorted(profiles.get("profiles", {}))
        payload["status"] = "passed" if (
            set(payload["competitions"]) == {"academy-award", "daguangsai"}
            and Image is not None and PdfReader is not None
        ) else "failed"
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", choices=["daguangsai", "academy-award"])
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--delivery-manifest", type=Path)
    parser.add_argument("--brief-constraints", type=Path)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--real-submission", action="store_true")
    parser.add_argument("--rule-verification", type=Path)
    args = parser.parse_args()

    if args.self_check:
        return self_check(args.profiles)
    for name in ("competition", "input_dir", "delivery_manifest", "brief_constraints", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required unless --self-check is used")
    if not args.input_dir.is_dir():
        parser.error(f"Input directory does not exist: {args.input_dir}")

    profiles_doc = load_json(args.profiles)
    profile = profiles_doc["profiles"][args.competition]
    manifest = load_json(args.delivery_manifest)
    brief = load_json(args.brief_constraints)
    checks: list[dict] = []

    checks.append(result("manifest-schema", manifest.get("schema_version") == "0.1.0", manifest.get("schema_version")))
    checks.append(result("manifest-competition", manifest.get("competition") == args.competition, manifest.get("competition")))
    identity_match = manifest.get("proposition_id") == brief.get("proposition_id")
    checks.append(result("proposition-linked", identity_match, {"manifest": manifest.get("proposition_id"), "brief": brief.get("proposition_id")}))

    brief_errors = validate_brief(brief, args.competition, profile)
    checks.append(result("brief-constraints", not brief_errors, brief_errors))
    checks.append(result("category-authorized", brief.get("category_authorized") is True, brief.get("category_authorized")))

    selected_shape = manifest.get("selected_page_shape")
    allowed_shapes = brief.get("allowed_page_shapes", profile["online_delivery"]["allowed_page_shapes"])
    checks.append(result("selected-page-shape", selected_shape in allowed_shapes, {"selected": selected_shape, "allowed": allowed_shapes}))

    artifacts = manifest.get("artifacts")
    artifact_errors: list[str] = []
    artifact_map: dict[str, tuple[dict, Path]] = {}
    if not isinstance(artifacts, list) or not artifacts:
        artifact_errors.append("artifacts must be a non-empty array")
        artifacts = []
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            artifact_errors.append(f"artifact {index} must be an object")
            continue
        relative = artifact.get("path")
        path, path_error = safe_path(args.input_dir, relative)
        if path_error:
            artifact_errors.append(f"artifact {index}: {path_error}")
            continue
        if relative in artifact_map:
            artifact_errors.append(f"duplicate artifact path: {relative}")
            continue
        if not path.is_file():
            artifact_errors.append(f"artifact missing: {relative}")
            continue
        if artifact.get("sha256") != sha256(path):
            artifact_errors.append(f"artifact hash mismatch: {relative}")
        artifact_map[relative] = (artifact, path)
    checks.append(result("artifacts-and-hashes", not artifact_errors, artifact_errors))

    pages = manifest.get("pages")
    page_errors: list[str] = []
    if not isinstance(pages, list) or not pages:
        page_errors.append("pages must be a non-empty array")
        pages = []
    sequences = [row.get("sequence") for row in pages if isinstance(row, dict)]
    if sequences != list(range(1, len(pages) + 1)):
        page_errors.append("page sequence must be contiguous and ordered from 1")
    roles = set(profiles_doc.get("role_vocabulary", []))
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            page_errors.append(f"page {index} must be an object")
            continue
        if page.get("artifact") not in artifact_map:
            page_errors.append(f"page {index} references an unknown artifact")
        if page.get("role") not in roles:
            page_errors.append(f"page {index} has an invalid role")
        if not isinstance(page.get("page_number"), int) or page["page_number"] < 1:
            page_errors.append(f"page {index} has an invalid page_number")
    checks.append(result("page-manifest", not page_errors, page_errors))

    delivery = profile["online_delivery"]
    file_errors: list[str] = []
    page_metrics: list[dict] = []
    if delivery["mode"] == "single-pdf":
        pdf_artifacts = [(row, path) for row, path in artifact_map.values() if row.get("kind") == "plan-pdf"]
        if len(pdf_artifacts) != 1 or len(artifact_map) != 1:
            file_errors.append("daguangsai online delivery requires exactly one plan-pdf artifact")
        elif PdfReader is None:
            file_errors.append("pypdf is unavailable")
        else:
            artifact, path = pdf_artifacts[0]
            if path.suffix.lower() not in delivery["allowed_extensions"]:
                file_errors.append("plan artifact extension is not allowed")
            if path.stat().st_size > delivery["max_file_bytes"]:
                file_errors.append("plan PDF exceeds the byte limit")
            try:
                reader = PdfReader(str(path))
                if len(reader.pages) != len(pages):
                    file_errors.append("PDF page count does not match the page manifest")
                if [row.get("page_number") for row in pages] != list(range(1, len(pages) + 1)):
                    file_errors.append("PDF page_number values must be contiguous and ordered")
                for index, page in enumerate(reader.pages, start=1):
                    width = float(page.mediabox.width)
                    height = float(page.mediabox.height)
                    matched = selected_shape in profiles_doc["page_shapes"] and shape_matches(
                        width, height, selected_shape, profiles_doc["page_shapes"], delivery["shape_ratio_tolerance"]
                    )
                    if matched and selected_shape == "A4":
                        a4 = profiles_doc["a4"]
                        short, long = sorted((width, height))
                        tolerance = float(delivery["a4_size_tolerance_points"])
                        matched = abs(short - float(a4["short_side_points"])) <= tolerance and abs(long - float(a4["long_side_points"])) <= tolerance
                    page_metrics.append({"sequence": index, "width": width, "height": height, "shape_match": matched})
                    if not matched:
                        file_errors.append(f"PDF page {index} does not match selected_page_shape")
            except Exception as exc:
                file_errors.append(f"PDF inspection failed: {exc}")
        body_count = sum(row.get("role") in delivery["body_roles"] for row in pages if isinstance(row, dict))
        appendix_count = sum(row.get("role") in delivery["appendix_roles"] for row in pages if isinstance(row, dict))
        if body_count > delivery["body_maximum"]:
            file_errors.append("body page count exceeds the maximum")
        if delivery.get("body_minimum") is not None and body_count < delivery["body_minimum"]:
            file_errors.append("body page count is below the minimum")
        if appendix_count > delivery["appendix_maximum"]:
            file_errors.append("appendix page count exceeds the maximum")
    else:
        image_artifacts = [(row, path) for row, path in artifact_map.values() if row.get("kind") == "page-image"]
        if len(image_artifacts) != len(artifact_map):
            file_errors.append("academy-award online delivery accepts only page-image artifacts")
        referenced = [row.get("artifact") for row in pages if isinstance(row, dict)]
        if len(referenced) != len(set(referenced)) or set(referenced) != set(artifact_map):
            file_errors.append("each page image must be referenced exactly once")
        if any(row.get("page_number") != 1 for row in pages if isinstance(row, dict)):
            file_errors.append("page-image page_number must be 1")
        if Image is None:
            file_errors.append("Pillow is unavailable")
        else:
            for artifact, path in image_artifacts:
                if path.suffix.lower() not in delivery["allowed_extensions"]:
                    file_errors.append(f"page image extension is not allowed: {artifact['path']}")
                    continue
                if path.stat().st_size > delivery["max_file_bytes"]:
                    file_errors.append(f"page image exceeds the byte limit: {artifact['path']}")
                try:
                    with Image.open(path) as image:
                        dpi = image.info.get("dpi", (0, 0))
                        if not isinstance(dpi, tuple) or len(dpi) < 2:
                            dpi = (0, 0)
                        matched = selected_shape in profiles_doc["page_shapes"] and shape_matches(
                            image.width, image.height, selected_shape, profiles_doc["page_shapes"], delivery["shape_ratio_tolerance"]
                        )
                        physical_match = False
                        if float(dpi[0]) > 0 and float(dpi[1]) > 0:
                            physical = sorted((image.width / float(dpi[0]), image.height / float(dpi[1])))
                            a4 = profiles_doc["a4"]
                            tolerance = float(delivery["a4_physical_tolerance_inches"])
                            physical_match = abs(physical[0] - float(a4["short_side_inches"])) <= tolerance and abs(physical[1] - float(a4["long_side_inches"])) <= tolerance
                        matched = matched and physical_match
                        metric = {"artifact": artifact["path"], "width": image.width, "height": image.height, "mode": image.mode, "dpi": [float(value) for value in dpi[:2]], "shape_match": matched}
                        page_metrics.append(metric)
                        if image.mode != delivery["color_mode"]:
                            file_errors.append(f"page image is not RGB: {artifact['path']}")
                        if min(float(dpi[0]), float(dpi[1])) < delivery["minimum_dpi"] - 0.5:
                            file_errors.append(f"page image DPI is below 300: {artifact['path']}")
                        if not matched:
                            file_errors.append(f"page image is not A4 ratio: {artifact['path']}")
                except Exception as exc:
                    file_errors.append(f"image inspection failed for {artifact['path']}: {exc}")
        content_count = sum(row.get("role") in delivery["counted_roles"] for row in pages if isinstance(row, dict))
        if content_count < delivery["content_minimum"]:
            file_errors.append("counted content pages are below the minimum")
        if content_count > delivery["content_maximum"]:
            file_errors.append("counted content pages exceed the maximum")
    checks.append(result("delivery-files-and-page-counts", not file_errors, {"errors": file_errors, "pages": page_metrics}))

    sections = manifest.get("sections")
    section_errors: list[str] = []
    if not isinstance(sections, list) or any(not isinstance(item, str) or not item for item in sections):
        section_errors.append("sections must be a string list")
        sections = []
    missing_sections = sorted(set(brief.get("required_sections", [])) - set(sections))
    if missing_sections:
        section_errors.append(f"required sections missing: {missing_sections}")
    checks.append(result("required-sections", not section_errors, section_errors))

    fields = manifest.get("submission_fields")
    field_errors: list[str] = []
    if not isinstance(fields, dict):
        field_errors.append("submission_fields must be an object")
        fields = {}
    for key in profile.get("required_submission_fields", []):
        if not isinstance(fields.get(key), str) or not fields[key].strip():
            field_errors.append(f"submission field is required: {key}")
    checks.append(result("submission-fields", not field_errors, field_errors))

    evidence_errors, evidence_metrics = validate_evidence(manifest)
    checks.append(result("evidence-register", not evidence_errors, {"errors": evidence_errors, **evidence_metrics}))

    rights = manifest.get("rights_review")
    rights_status = rights.get("status") if isinstance(rights, dict) else None
    rights_structured = isinstance(rights, dict) and rights_status in {"passed", "pending", "blocked", "not-applicable"} and isinstance(rights.get("borrowed_assets"), list)
    checks.append(result("rights-review-structured", rights_structured, rights_status, "warning"))

    budget_errors, budget_metrics = validate_budget(manifest.get("budget"), brief.get("budget_requirement", "not-specified"))
    checks.append(result("budget-contract", not budget_errors, {"errors": budget_errors, **budget_metrics}))
    kpi_errors, kpi_metrics = validate_kpi(manifest.get("kpi"), brief.get("kpi_requirement", "not-specified"))
    checks.append(result("kpi-contract", not kpi_errors, {"errors": kpi_errors, **kpi_metrics}))

    aigc = manifest.get("aigc")
    aigc_errors: list[str] = []
    if not isinstance(aigc, dict) or aigc.get("used") not in {"yes", "no", "unknown"}:
        aigc_errors.append("aigc.used must be yes, no, or unknown")
    elif aigc["used"] == "yes":
        record, record_error = safe_path(args.input_dir, aigc.get("record_path"))
        if record_error or record is None or not record.is_file() or record.stat().st_size == 0:
            aigc_errors.append("aigc record is required and must be non-empty when used=yes")
    checks.append(result("aigc-record", not aigc_errors, aigc_errors, "warning"))

    if brief.get("required_terms"):
        checks.append(result("required-terms-human-review", False, brief["required_terms"], "warning"))
    if brief.get("prohibited_terms"):
        checks.append(result("prohibited-terms-human-review", False, brief["prohibited_terms"], "warning"))

    failed_errors = [row for row in checks if not row["passed"] and row["severity"] == "error"]
    failed_warnings = [row for row in checks if not row["passed"] and row["severity"] == "warning"]
    technical_status = "pass" if not failed_errors else "fail"
    if args.real_submission:
        rule_status, rule_evidence = validate_rule_verification(args.rule_verification, args.competition, profile)
    else:
        rule_status = profile["publication_status"]
        rule_evidence = {"source_url": profile["source_url"], "checked_at": profile["checked_at"]}
    if brief.get("category_authorized") is not True:
        content_status = "blocked"
    elif not any(row.get("status") == "open-question" for row in manifest.get("evidence_register", []) if isinstance(row, dict)):
        content_status = "requires-strategy-review"
    else:
        content_status = "requires-evidence-review"

    payload = {
        "schema_version": "0.1.0",
        "competition": args.competition,
        "plan_id": manifest.get("plan_id"),
        "proposition_id": manifest.get("proposition_id"),
        "profile_snapshot": profile["snapshot"],
        "technical_validation_status": technical_status,
        "content_review_status": content_status,
        "rule_snapshot_status": rule_status,
        "rule_evidence": rule_evidence,
        "checks_total": len(checks),
        "checks_passed": sum(row["passed"] for row in checks),
        "error_failures": [row["name"] for row in failed_errors],
        "warnings": [row["name"] for row in failed_warnings],
        "checks": checks,
        "method_run_complete": False,
        "submission_ready": False,
        "submission_ready_reason": "Technical checks do not prove strategy quality, factual truth, price validity, KPI fitness, rights clearance, current registration fields, or actual submission.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: payload[key] for key in ("technical_validation_status", "content_review_status", "rule_snapshot_status", "checks_total", "checks_passed", "error_failures", "warnings")}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if technical_status == "pass" and (not args.real_submission or rule_status == "current") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
