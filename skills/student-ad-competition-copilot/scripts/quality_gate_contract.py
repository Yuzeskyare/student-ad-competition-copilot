"""Shared stdlib-only checks for track quality-gate result files."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


CONTINUE_STATES = {"pass", "pass-with-boundaries", "waived"}
RISK_LEVELS = {"consider", "return-on-observed-failure", "hard-stop"}


def _check(name: str, passed: bool, evidence: object) -> dict:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def check_summary(checks):
    """A valid unfinished check is different from a failed requirement."""
    for row in checks:
        if row['passed'] or row.get('state') == 'in-progress':
            continue
        name, evidence = row['name'], row.get('evidence')
        kind = None
        if name in {'run-content-review', 'manual-content-review'} and isinstance(evidence, str) and evidence in {'pending', 'not-run'}:
            kind = 'human'
        elif name == 'run-method-complete' and evidence is False:
            kind = 'work'
        elif name == 'short-copy-prosody-review' and isinstance(evidence, dict) and evidence.get('status') in {'pending', 'not-run'}:
            kind = 'work'
        if kind:
            row.update(state='in-progress', waiting_kind=kind)
    unfinished = [r for r in checks if not r['passed'] and r.get('severity') != 'reminder']
    waiting = [r for r in unfinished if r.get('state') == 'in-progress']
    repairs = [r for r in unfinished if r.get('state') != 'in-progress']
    return {
        'status': 'failed' if repairs else ('in-progress' if waiting else 'passed'),
        'repair_checks': [r['name'] for r in repairs],
        'waiting_checks': [r['name'] for r in waiting],
        'waiting_details': [{'name': r['name'], 'kind': r.get('waiting_kind', 'work'),
                             'stage': r.get('stage'), 'evidence': r.get('evidence')} for r in waiting],
    }


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _inside(run_dir: Path, relative: object) -> tuple[Path | None, str | None]:
    if not isinstance(relative, str) or not relative.strip():
        return None, "path must be a non-empty string"
    path = Path(relative)
    if path.is_absolute():
        return None, "absolute paths are forbidden"
    resolved = (run_dir / path).resolve()
    if resolved != run_dir and run_dir not in resolved.parents:
        return None, "path escapes run directory"
    return resolved, None


def _valid_time(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_quality_gate_results(
    run_dir: Path,
    result_path: Path,
    track: str,
    expected_run_id: str | None,
    completed_gate_ids: set[str] | None = None,
) -> list[dict]:
    checks: list[dict] = []
    definitions_path = Path(__file__).resolve().parents[1] / "references" / "tracks" / track / "quality-gates.json"
    try:
        definitions = _load(definitions_path)
        results = _load(result_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [_check("quality-gate-files-readable", False, str(exc))]

    checks.append(_check("quality-gate-files-readable", True, {"definitions": str(definitions_path), "results": str(result_path)}))
    checks.append(_check("quality-gate-track", results.get("track") == track and definitions.get("track") == track, results.get("track")))
    checks.append(_check("quality-gate-definition-set", results.get("definition_set_id") == definitions.get("definition_set_id"), results.get("definition_set_id")))
    checks.append(_check("quality-gate-run-id", results.get("run_id") == expected_run_id, results.get("run_id")))

    gate_by_id = {gate.get("gate_id"): gate for gate in definitions.get("gates", []) if isinstance(gate, dict)}
    expected_completed = set(gate_by_id) if completed_gate_ids is None else set(completed_gate_ids)
    scope_valid = expected_completed <= set(gate_by_id)
    checks.append(_check(
        "quality-gate-scope",
        scope_valid,
        {"completed": sorted(expected_completed), "known": sorted(gate_by_id)},
    ))
    severity_rows = [
        (gate.get("gate_id"), check.get("check_id"), check.get("failure_severity"))
        for gate in gate_by_id.values()
        for check in gate.get("checks", []) if isinstance(check, dict)
    ]
    severities_valid = bool(severity_rows) and all(level in RISK_LEVELS for _, _, level in severity_rows)
    checks.append(_check("quality-gate-definition-risk-levels", severities_valid, severity_rows))
    result_items = results.get("results")
    result_by_id = {
        item.get("gate_id"): item for item in result_items or [] if isinstance(item, dict)
    } if isinstance(result_items, list) else {}
    checks.append(_check("quality-gate-complete-set", set(result_by_id) == set(gate_by_id) and len(result_by_id) == len(result_items or []), {"expected": sorted(gate_by_id), "actual": sorted(result_by_id)}))

    continue_ready = scope_valid
    unfinished_gates = []
    for gate_id, gate in gate_by_id.items():
        result = result_by_id.get(gate_id)
        if not isinstance(result, dict):
            continue_ready = False
            continue
        status = result.get("status")
        known_checks = {item.get("check_id") for item in gate.get("checks", []) if isinstance(item, dict)}
        required_checks = {item.get("check_id") for item in gate.get("checks", []) if isinstance(item, dict) and "applies_when" not in item}
        passed = set(result.get("passed_check_ids", []))
        failed = set(result.get("failed_check_ids", []))
        reviewer_types = {item.get("type") for item in result.get("reviewers", []) if isinstance(item, dict)}

        boundaries = result.get("boundaries")
        waiver_reason = result.get("waiver_reason")
        checked_at = result.get("checked_at")
        result_contract = (
            isinstance(boundaries, list)
            and (status != "pass-with-boundaries" or bool(boundaries))
            and (status != "waived" or isinstance(waiver_reason, str) and bool(waiver_reason.strip()))
            and (status == "not-run" or _valid_time(checked_at))
        )
        checks.append(_check(
            f"quality-gate:{gate_id}:result-contract",
            result_contract,
            {"boundaries": boundaries, "waiver_reason": waiver_reason, "checked_at": checked_at},
        ))

        failed_routes = []
        for check in gate.get("checks", []):
            if check.get("check_id") not in failed:
                continue
            failed_routes.append({
                "check_id": check.get("check_id"),
                "risk_level": check.get("failure_severity"),
                "return_to_stage": check.get("return_to_stage"),
            })
        routing_ok = status != "fail" or (
            bool(failed_routes)
            and all(
                row["risk_level"] in {"return-on-observed-failure", "hard-stop"}
                and isinstance(row["return_to_stage"], str)
                and bool(row["return_to_stage"])
                for row in failed_routes
            )
        )
        checks.append(_check(f"quality-gate:{gate_id}:failure-routing", routing_ok, failed_routes))

        logical = not (passed & failed) and (passed | failed) <= known_checks
        if status in {"pass", "pass-with-boundaries"}:
            logical = logical and not failed and required_checks <= passed
        elif status == "fail":
            logical = logical and bool(failed)
        elif status == "not-run":
            logical = logical and not passed and not failed
        elif status == "waived":
            logical = logical and gate.get("waiver_policy", {}).get("allowed") is True and not passed and not failed
        else:
            logical = False
        checks.append(_check(f"quality-gate:{gate_id}:logic", logical, {"status": status, "passed": sorted(passed), "failed": sorted(failed)}))

        reviewer_ok = status == "not-run" or (
            (gate.get("gate_type") not in {"human", "hybrid"} or "human" in reviewer_types)
            and (gate.get("gate_type") not in {"machine", "hybrid"} or "machine" in reviewer_types)
        )
        checks.append(_check(f"quality-gate:{gate_id}:reviewer", reviewer_ok, sorted(item for item in reviewer_types if item)))

        evidence_ok = True
        evidence_report = []
        if status != "not-run":
            evidence_paths = result.get("evidence_paths", [])
            evidence_ok = isinstance(evidence_paths, list) and bool(evidence_paths)
            for relative in evidence_paths if isinstance(evidence_paths, list) else []:
                resolved, error = _inside(run_dir, relative)
                exists = resolved is not None and resolved.is_file() and error is None
                evidence_report.append({"path": relative, "exists": exists, "error": error})
                evidence_ok = evidence_ok and exists
        checks.append(_check(f"quality-gate:{gate_id}:evidence", evidence_ok, evidence_report))
        status_matches_scope = (
            status != "not-run" if gate_id in expected_completed else status == "not-run"
        )
        checks.append(_check(
            f"quality-gate:{gate_id}:scope-status",
            status_matches_scope,
            {"status": status, "expected": "continue" if gate_id in expected_completed else "not-run"},
        ))
        if not status_matches_scope and status == 'not-run' and gate_id in expected_completed:
            checks[-1].update(state='in-progress', stage=gate.get('stage'),
                              waiting_kind='human' if gate.get('gate_type') == 'human' else 'work')
            unfinished_gates.append(gate_id)
        ready_status = status in CONTINUE_STATES if gate_id in expected_completed else status == "not-run"
        continue_ready = (
            continue_ready and severities_valid and ready_status and logical
            and result_contract and routing_ok and reviewer_ok and evidence_ok
        )

    checks.append(_check("quality-gates-ready", continue_ready, {gate_id: item.get("status") for gate_id, item in result_by_id.items()}))
    if not continue_ready and unfinished_gates and all(item.get('status') in CONTINUE_STATES | {'not-run'} for item in result_by_id.values()):
        checks[-1].update(state='in-progress', waiting_kind='aggregate')
    return checks
