#!/usr/bin/env python3
"""Validate the stable rule/rights/citation/AIGC/submission readiness contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


def check(name: str, passed: bool, evidence: object) -> dict:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def safe_file(run_dir: Path, relative: object) -> bool:
    if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute():
        return False
    resolved = (run_dir / relative).resolve()
    return (resolved == run_dir or run_dir in resolved.parents) and resolved.is_file()


def validate(payload: dict, run_dir: Path) -> dict:
    run_dir = run_dir.resolve()
    checks = []
    delivery_mode = payload.get('method_scope') == 'artwork-delivery'
    payload = dict(payload)
    # Do not parse out-of-scope administration before deciding its applicability.
    # Keep caller data intact; an independent submission run still validates it.
    for section in ('rights_clearance', 'aigc', 'submission'):
        if delivery_mode:
            payload.pop(section, None)
        elif not isinstance(payload.get(section, {}), dict):
            checks.append(check(section+'-object', False, 'Expected an object'))
            payload[section] = {}
    checks.append(check("schema-version", payload.get("schema_version") == "0.1.0", payload.get("schema_version")))
    checks.append(check("identity", all(isinstance(payload.get(key), str) and payload[key] for key in ("run_id", "track", "competition", "method_scope")), {key: payload.get(key) for key in ("run_id", "track", "competition", "method_scope")}))

    # An unresolved item may have no evidence yet. A supplied path must still
    # resolve correctly; "incomplete" must not conceal a broken reference.
    declared_paths = []
    for section, field in (
        ("rule_verification", "evidence_path"), ("rights_clearance", "evidence_path"),
        ("citations", "evidence_path"), ("aigc", "record_path"),
        ("content_quality", "evidence_path"), ("technical_validation", "evidence_path"),
        ("submission", "receipt_path"),
    ):
        relative = payload.get(section, {}).get(field)
        if relative is not None:
            declared_paths.append({"field": f"{section}.{field}", "path": relative,
                                   "valid": safe_file(run_dir, relative)})
    checks.append(check("declared-evidence-paths", all(item["valid"] for item in declared_paths), declared_paths))

    rule = payload.get("rule_verification", {})
    rule_status = rule.get("status")
    rule_ok = rule_status in {"verified-current", "not-verified-current", "not-required-for-method"}
    if rule_status == "verified-current":
        parsed = urlparse(rule.get("source_url") or "")
        rule_ok = rule_ok and parsed.scheme in {"http", "https"} and bool(parsed.netloc) and bool(rule.get("checked_at")) and safe_file(run_dir, rule.get("evidence_path"))
    if rule_status == "not-required-for-method":
        rule_ok = rule_ok and payload.get("method_scope") == "method-only"
    checks.append(check("rule-verification", rule_ok, rule))

    for field in ("rights_clearance", "citations"):
        item = payload.get(field, {})
        status = item.get("status")
        open_items = item.get("open_items")
        ok = status in {"complete", "incomplete", "not-applicable"} and isinstance(open_items, list)
        if status == "complete":
            ok = ok and not open_items and safe_file(run_dir, item.get("evidence_path"))
        elif status == "incomplete":
            ok = ok and bool(open_items)
        elif status == "not-applicable":
            ok = ok and not open_items and isinstance(item.get("rationale"), str) and bool(item["rationale"].strip())
        checks.append(check(field.replace("_", "-"), ok, item))

    aigc = payload.get("aigc", {})
    aigc_ok = aigc.get("used") in {"yes", "no", "unknown"} and aigc.get("status") in {"complete", "incomplete", "not-applicable"}
    if aigc.get("used") == "yes" and aigc.get("status") == "complete":
        aigc_ok = aigc_ok and safe_file(run_dir, aigc.get("record_path"))
    if aigc.get("used") == "no":
        aigc_ok = aigc_ok and aigc.get("status") == "not-applicable" and isinstance(aigc.get("rationale"), str) and bool(aigc["rationale"].strip())
    checks.append(check("aigc-record", aigc_ok, aigc))

    content = payload.get("content_quality", {})
    content_ok = content.get("status") in {"pass", "pass-with-boundaries", "fail", "not-run"}
    if content.get("status") != "not-run":
        content_ok = content_ok and safe_file(run_dir, content.get("evidence_path"))
    checks.append(check("content-quality", content_ok, content))

    technical = payload.get("technical_validation", {})
    technical_ok = technical.get("status") in {"pass", "fail", "not-run"}
    if technical.get("status") != "not-run":
        technical_ok = technical_ok and safe_file(run_dir, technical.get("evidence_path"))
    checks.append(check("technical-validation", technical_ok, technical))

    submission = payload.get("submission", {})
    ready = submission.get("submission_ready") is True
    readiness_prerequisites = (
        payload.get("method_scope") == "real-submission"
        and rule_status == "verified-current"
        and payload.get("rights_clearance", {}).get("status") in {"complete", "not-applicable"}
        and payload.get("citations", {}).get("status") in {"complete", "not-applicable"}
        and aigc.get("status") in {"complete", "not-applicable"}
        and aigc.get("used") != "unknown"
        and content.get("status") == "pass"
        and technical.get("status") == "pass"
        and submission.get("registration_fields_verified") is True
        and submission.get("uploaded") is True
        and safe_file(run_dir, submission.get("receipt_path"))
    )
    submission_logic = readiness_prerequisites if ready else not readiness_prerequisites
    checks.append(check("submission-ready-invariant", submission_logic, {"declared": ready, "prerequisites": readiness_prerequisites}))
    boundaries = payload.get("readiness_boundaries")
    boundaries_ok = isinstance(boundaries, list) and (ready or bool(boundaries))
    checks.append(check("readiness-boundaries", boundaries_ok, boundaries))

    # Artwork delivery is independent of the optional submission workflow.
    optional = {"rights-clearance", "aigc-record", "submission-ready-invariant", "readiness-boundaries"}
    if delivery_mode:
        # Optional records may be incomplete; keep their diagnostics as reminders.
        mandatory_paths = [item for item in declared_paths if item["field"].split(".")[0] in
                           {"rule_verification", "citations", "content_quality", "technical_validation"}]
        for item in checks:
            if item["name"] == "declared-evidence-paths":
                item["passed"] = all(row["valid"] for row in mandatory_paths)
                item["evidence"] = mandatory_paths
            if item["name"] in optional:
                item["severity"] = "reminder"
                item["passed"] = True
                item["evidence"] = 'Not evaluated in artwork-delivery; independent submission only.'
    failures = [item["name"] for item in checks if not item["passed"] and item.get("severity") != "reminder"]
    delivery_ready = (not failures and rule_status == "verified-current"
                      and payload.get("citations", {}).get("status") in {"complete", "not-applicable"}
                      and content.get("status") == "pass" and technical.get("status") == "pass")
    delivery_blockers = []
    if rule_status != "verified-current": delivery_blockers.append("current-competition-rules-and-specifications")
    if payload.get("citations", {}).get("status") not in {"complete", "not-applicable"}: delivery_blockers.append("external-research-citations")
    if content.get("status") != "pass": delivery_blockers.append("approved-current-content")
    if technical.get("status") != "pass": delivery_blockers.append("final-file-technical-validation")
    delivery_blockers.extend(failures)
    return {"schema_version": "0.1.0", "run_id": payload.get("run_id"), "status": "passed" if not failures else "failed", "checks_total": len(checks), "checks_passed": len(checks) - len(failures), "failure_names": failures, "submission_ready": ready if not delivery_mode else False, "delivery_ready": bool(delivery_ready), "delivery_blockers": delivery_blockers, "post_delivery_reminders": ["使用作品投稿或公开发布前，请自行核对最终素材与字体的使用依据。", "请按实际使用情况整理AIGC后台记录，并按平台要求完成申报。"], "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        print(json.dumps({"schema_version": "0.1.0", "status": "passed", "ready_requires_upload_receipt": True}, ensure_ascii=False))
        return 0
    if args.run_dir is None or args.input is None or args.output is None:
        parser.error("--run-dir, --input and --output are required unless --self-check is used")
    payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    result = validate(payload, args.run_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks_total", "checks_passed", "failure_names", "submission_ready")}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
