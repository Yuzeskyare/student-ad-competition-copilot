"""Validate the visual-generation capability preflight for visual tracks."""

from __future__ import annotations

from typing import Any


CURRENT_SCHEMA = "0.3.0"
VISUAL_TRACKS = {"print-ad", "marketing-plan"}
STATUSES = {"available", "unavailable", "unknown"}
DECISIONS = {
    "use-available-capability",
    "accept-limited-mode",
    "enable-or-switch-environment",
    "pending",
}


def _check(name: str, passed: bool, evidence: object) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def validate_visual_generation_capability(manifest: dict, run_scope: object) -> list[dict[str, Any]]:
    """Return checks for new visual-track manifests; legacy schemas remain readable."""
    if manifest.get("schema_version") not in {CURRENT_SCHEMA, "0.4.0"} or manifest.get("category") not in VISUAL_TRACKS:
        return []

    capability = manifest.get("visual_generation_capability")
    if not isinstance(capability, dict):
        return [_check("visual-generation-capability-record", False, type(capability).__name__)]

    status = capability.get("status")
    provider = capability.get("provider")
    operations = capability.get("operations")
    decision = capability.get("user_decision")
    checked_at = capability.get("checked_at")
    evidence = capability.get("evidence")
    acknowledged = capability.get("impact_acknowledged")
    record_valid = (
        status in STATUSES
        and isinstance(operations, list)
        and len(operations) == len(set(operations))
        and all(item in {"generate", "edit"} for item in operations)
        and decision in DECISIONS
        and isinstance(checked_at, str) and bool(checked_at.strip())
        and isinstance(evidence, str) and bool(evidence.strip())
        and isinstance(acknowledged, bool)
    )
    checks = [_check("visual-generation-capability-record", record_valid, capability)]

    if status == "available":
        ready = (
            isinstance(provider, str) and bool(provider.strip())
            and "generate" in operations
            and decision == "use-available-capability"
        )
    else:
        ready = (
            decision == "accept-limited-mode"
            and acknowledged is True
            and run_scope == "concept-only"
        )
    checks.append(_check("visual-generation-capability-resolution", ready, {
        "status": status,
        "provider": provider,
        "operations": operations,
        "user_decision": decision,
        "impact_acknowledged": acknowledged,
        "run_scope": run_scope,
    }))

    production_ready = run_scope == "concept-only" or (
        status == "available"
        and isinstance(provider, str) and bool(provider.strip())
        and "generate" in operations
        and decision == "use-available-capability"
    )
    checks.append(_check("visual-generation-production-readiness", production_ready, {
        "run_scope": run_scope,
        "status": status,
        "provider": provider,
    }))
    return checks
