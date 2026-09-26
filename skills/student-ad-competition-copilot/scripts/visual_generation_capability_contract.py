"""Validate the visual-generation capability preflight for visual tracks."""

from __future__ import annotations

from typing import Any
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re


CURRENT_SCHEMA = "0.3.0"
VISUAL_TRACKS = {"print-ad", "marketing-plan"}
STATUSES = {"available", "unavailable", "unknown"}
DECISIONS = {
    "use-available-capability",
    "accept-limited-mode",
    "enable-or-switch-environment",
    "pending",
    "use-external-assets",
}


def _check(name: str, passed: bool, evidence: object) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def _bound_file(root: Path | None, ref: object, *, bitmap: bool = False) -> bool:
    """Verify a returned asset/evidence file; never treat a URL or prompt as an asset."""
    if root is None or not isinstance(ref, dict):
        return False
    name, expected = ref.get("path"), ref.get("sha256")
    if not isinstance(name, str) or not name.strip() or not isinstance(expected, str):
        return False
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        return False
    if Path(name).is_absolute() or PureWindowsPath(name).drive or ":" in name or "\\" in name:
        return False
    try:
        root = root.resolve()
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file() or path.stat().st_size == 0:
            return False
        with path.open("rb") as handle:
            digest = hashlib.sha256()
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
            actual = digest.hexdigest()
        if actual != expected:
            return False
        if bitmap:
            from PIL import Image
            with Image.open(path) as img:
                img.verify()
        return True
    except (OSError, ValueError, ImportError, SyntaxError):
        return False


def _external_supply(supply: object, run_scope: object, root: Path | None) -> tuple[bool, bool]:
    """Return record validity and asset readiness, not an artistic quality verdict."""
    if not isinstance(supply, dict):
        return False, False
    status = supply.get("status")
    scope = supply.get("scope")
    assets = supply.get("assets")
    record = (
        isinstance(supply.get("kind"), str) and supply["kind"] in {"external-generation", "provided-assets"}
        and isinstance(status, str) and status in {"awaiting-assets", "ready"}
        and isinstance(scope, str) and scope in {"production-candidate", "delivery-candidate"}
        and isinstance(supply.get("evidence"), str) and bool(supply["evidence"].strip())
        and isinstance(assets, list)
    )
    if not record:
        return False, False
    if status == "awaiting-assets":
        return assets == [] and supply.get("review") is None, False
    # This receipt may be a small section of an existing JSON review. It binds
    # the reviewer's coverage observation to files, not to individual image objects.
    unique_paths = [row.get("path") for row in assets if isinstance(row, dict)]
    valid_paths = all(isinstance(name, str) for name in unique_paths)
    ready = (
        bool(assets) and len(unique_paths) == len(assets) and valid_paths
        and len(set(unique_paths)) == len(unique_paths)
        and all(_bound_file(root, row, bitmap=True) for row in assets)
        and _bound_file(root, supply.get("review"))
        and (run_scope == "concept-only" or scope == run_scope)
    )
    if ready:
        try:
            payload = json.loads((root / supply["review"]["path"]).read_text(encoding="utf-8-sig"))
            review = payload.get("external_asset_review", payload) if isinstance(payload, dict) else {}
            ready = (
                isinstance(review, dict) and review.get("status") == "pass"
                and review.get("scope") == scope and review.get("assets") == assets
                and isinstance(review.get("observation"), str) and bool(review["observation"].strip())
            )
        except (OSError, ValueError):
            ready = False
    return bool(ready), bool(ready)


def validate_visual_generation_capability(manifest: dict, run_scope: object, run_dir: Path | None = None) -> list[dict[str, Any]]:
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
        isinstance(status, str) and status in STATUSES
        and isinstance(operations, list)
        and all(isinstance(item, str) and item in {"generate", "edit"} for item in operations)
        and len(operations) == len(set(operations))
        and isinstance(decision, str) and decision in DECISIONS
        and isinstance(checked_at, str) and bool(checked_at.strip())
        and isinstance(evidence, str) and bool(evidence.strip())
        and isinstance(acknowledged, bool)
    )
    checks = [_check("visual-generation-capability-record", record_valid, capability)]
    if not record_valid:
        return checks

    supply_ready = False
    if decision == "use-external-assets":
        supply_valid, supply_ready = _external_supply(capability.get("external_supply"), run_scope, run_dir)
        # External use never changes what the host can actually call.
        direct_record = status != "available" or (
            isinstance(provider, str) and bool(provider.strip()) and bool(operations)
        )
        ready = record_valid and direct_record and supply_valid and (supply_ready or run_scope == "concept-only")
        checks.append(_check("visual-external-asset-supply", supply_valid and direct_record,
                             "Ready requires readable bitmap files, matching hashes, a linked review and current scope; pending is preparation only."))
    elif "external_supply" in capability:
        ready = False
        checks.append(_check("visual-external-asset-supply", False, "external_supply requires use-external-assets"))
    elif status == "available":
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
    checks.append(_check("visual-generation-capability-resolution", record_valid and ready, {
        "status": status,
        "provider": provider,
        "operations": operations,
        "user_decision": decision,
        "impact_acknowledged": acknowledged,
        "run_scope": run_scope,
    }))

    production_ready = record_valid and ready and (run_scope == "concept-only" or supply_ready or (
        status == "available"
        and isinstance(provider, str) and bool(provider.strip())
        and "generate" in operations
        and decision == "use-available-capability"
    ))
    checks.append(_check("visual-generation-production-readiness", production_ready, {
        "run_scope": run_scope,
        "status": status,
        "provider": provider,
    }))
    return checks
