#!/usr/bin/env python3
"""Validate an ad-copy draft against competition and proposition constraints."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.dont_write_bytecode = True

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = SKILL_ROOT / "references/competitions/ad-copy-profiles.json"
KNOWN_SUBTYPES = (
    "slogan", "short-copy", "long-copy", "seeding-copy",
    "brand-story", "script", "social-copy",
)

MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HTML_TAG = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
DATA_IMAGE = re.compile(r"data\s*:\s*image/", re.IGNORECASE)
MARKDOWN_TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(name: str, passed: bool, evidence, severity: str = "error") -> dict:
    return {"name": name, "passed": bool(passed), "severity": severity, "evidence": evidence}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def normalize_text(raw: str, contract: dict) -> tuple[str, dict]:
    bom_present = raw.startswith("\ufeff")
    if bom_present and contract.get("strip_initial_bom"):
        raw = raw[1:]
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    normalized = unicodedata.normalize(contract.get("unicode_normalization", "NFC"), raw)
    content = [char for char in normalized if not char.isspace()]
    metrics = {
        "contract_id": contract["contract_id"],
        "initial_bom_removed": bom_present,
        "normalized_codepoint_count": len(normalized),
        "content_character_count": len(content),
        "whitespace_count": sum(char.isspace() for char in normalized),
        "newline_count": normalized.count("\n"),
        "punctuation_count": sum(unicodedata.category(char).startswith("P") for char in content),
    }
    return normalized, metrics


def is_emoji(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x2300 <= codepoint <= 0x23FF
        or 0xFE00 <= codepoint <= 0xFE0F
    )


def invalid_invisible_characters(text: str) -> list[dict]:
    invalid = []
    for index, char in enumerate(text):
        category = unicodedata.category(char)
        if char == "\n":
            continue
        if char == "\t" or category in {"Cc", "Cf"}:
            invalid.append({
                "index": index,
                "codepoint": f"U+{ord(char):04X}",
                "name": unicodedata.name(char, "UNNAMED"),
            })
    return invalid


def has_markdown_table(text: str) -> bool:
    lines = text.splitlines()
    if any(MARKDOWN_TABLE_SEPARATOR.match(line) for line in lines):
        return True
    return any(line.count("|") >= 2 for line in lines)


def validate_brief_document(document: dict, competition: str, profile: dict) -> list[str]:
    errors = []
    if document.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    if document.get("competition") != competition:
        errors.append("competition does not match")
    if not isinstance(document.get("proposition_id"), str) or not document["proposition_id"].strip():
        errors.append("proposition_id is required")
    allowed = document.get("allowed_subtypes")
    if not isinstance(allowed, list) or not allowed:
        errors.append("allowed_subtypes must be a non-empty list")
        allowed = []
    elif len(allowed) != len(set(allowed)):
        errors.append("allowed_subtypes must be unique")
    unknown = sorted(set(allowed) - set(profile["allowed_subtypes"]))
    if unknown:
        errors.append(f"allowed_subtypes expand the competition profile: {unknown}")
    if document.get("subtype_basis", "brief-explicit") not in {
        "brief-explicit", "broad-category-working-classification", "competition-default",
    }:
        errors.append("subtype_basis is invalid")
    length_status = document.get("length_status", "specified")
    if length_status not in {"specified", "not-specified", "not-applicable", "conflict"}:
        errors.append("length_status is invalid")
    constraints = document.get("subtype_constraints")
    if not isinstance(constraints, dict):
        errors.append("subtype_constraints must be an object")
        constraints = {}
    for subtype in allowed:
        rule = constraints.get(subtype)
        if not isinstance(rule, dict):
            errors.append(f"missing subtype_constraints for {subtype}")
            continue
        minimum, maximum = rule.get("minimum"), rule.get("maximum")
        if minimum is not None and (not isinstance(minimum, int) or minimum < 0):
            errors.append(f"{subtype}.minimum must be null or a non-negative integer")
        if maximum is not None and (not isinstance(maximum, int) or maximum < 1):
            errors.append(f"{subtype}.maximum must be null or a positive integer")
        if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
            errors.append(f"{subtype}.minimum exceeds maximum")
        if length_status in {"not-specified", "not-applicable"} and (minimum is not None or maximum is not None):
            errors.append(f"{subtype} must use null bounds when length_status is {length_status}")
        if rule.get("unit") != "content-codepoints":
            errors.append(f"{subtype}.unit must be content-codepoints")
    for key in ("required_terms", "prohibited_terms"):
        value = document.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            errors.append(f"{key} must be a list of non-empty strings")
    groups = document.get("required_any_groups", [])
    if not isinstance(groups, list) or any(
        not isinstance(group, list) or not group or any(not isinstance(item, str) or not item for item in group)
        for group in groups
    ):
        errors.append("required_any_groups must contain non-empty string lists")
    if document.get("claim_review_status", "pending") not in {"pending", "reviewed", "blocked"}:
        errors.append("claim_review_status is invalid")
    if document.get("emoji_policy", "inherit") not in {"inherit", "forbidden", "warning", "allowed"}:
        errors.append("emoji_policy is invalid")
    evidence = document.get("evidence")
    if not isinstance(evidence, dict) or not evidence.get("source") or not evidence.get("checked_at"):
        errors.append("evidence.source and evidence.checked_at are required")
    return errors


def validate_rule_verification(path: Path | None, competition: str, profile: dict) -> tuple[str, dict]:
    if not profile.get("refresh_before_real_submission"):
        return "current", {"required": False}
    if path is None or not path.is_file():
        return "needs_rule_refresh", {"required": True, "verification": str(path) if path else None}
    value = load_json(path)
    passed = (
        value.get("competition") == competition
        and value.get("status") == "verified-current"
        and value.get("source_url") == profile.get("source_url")
        and isinstance(value.get("checked_at"), str)
        and bool(value.get("checked_at"))
        and value.get("platform_count_contract_checked") is True
    )
    return ("current" if passed else "needs_rule_refresh"), value


def self_check(profiles_path: Path) -> int:
    result = {
        "schema_version": "0.1.0",
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "skill_root": str(SKILL_ROOT),
        "profiles": str(profiles_path.resolve()),
        "profiles_present": profiles_path.is_file(),
    }
    try:
        document = load_json(profiles_path)
        result["profile_schema_version"] = document.get("schema_version")
        result["competitions"] = sorted(document.get("profiles", {}))
        result["count_contract_id"] = document.get("count_contract", {}).get("contract_id")
        result["status"] = "passed" if set(result["competitions"]) == {"academy-award", "daguangsai"} else "failed"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", choices=["daguangsai", "academy-award"])
    parser.add_argument("--subtype", choices=KNOWN_SUBTYPES)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--brief-constraints", type=Path)
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
    for name in ("competition", "subtype", "input", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required unless --self-check is used")
    if not args.input.is_file():
        parser.error(f"Input file does not exist: {args.input}")

    profiles_document = load_json(args.profiles)
    profile = profiles_document["profiles"][args.competition]
    contract = profiles_document["count_contract"]
    checks = []

    checks.append(check("input-extension", args.input.suffix.lower() in profile["allowed_input_extensions"], {
        "actual": args.input.suffix.lower(), "allowed": profile["allowed_input_extensions"],
    }))
    checks.append(check("input-size", args.input.stat().st_size <= profile["max_input_bytes"], {
        "actual": args.input.stat().st_size, "maximum": profile["max_input_bytes"],
    }))
    try:
        raw_text = args.input.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raw_text = ""
        checks.append(check("utf8-decode", False, str(exc)))
    else:
        checks.append(check("utf8-decode", True, "UTF-8"))
    normalized, metrics = normalize_text(raw_text, contract)

    checks.append(check("non-empty-content", metrics["content_character_count"] > 0, metrics["content_character_count"]))
    checks.append(check("leading-trailing-whitespace", normalized == normalized.strip(), {
        "leading": bool(normalized and normalized[0].isspace()),
        "trailing": bool(normalized and normalized[-1].isspace()),
    }))
    invisibles = invalid_invisible_characters(normalized)
    checks.append(check("tabs-controls-zero-width", not invisibles, invisibles[:20]))
    checks.append(check("embedded-image", not (MARKDOWN_IMAGE.search(normalized) or DATA_IMAGE.search(normalized)), None))
    checks.append(check("html", not HTML_TAG.search(normalized), None))
    checks.append(check("table", not has_markdown_table(normalized), None))

    creator_matches = []
    for pattern in profiles_document.get("creator_marker_patterns", []):
        creator_matches.extend(match.group(0).strip() for match in re.finditer(pattern, normalized))
    checks.append(check("creator-markers", not creator_matches, sorted(set(creator_matches))))

    competition_allowed = args.subtype in profile["allowed_subtypes"]
    checks.append(check("subtype-allowed-by-competition", competition_allowed, {
        "selected": args.subtype, "allowed": profile["allowed_subtypes"],
    }))

    brief_document = None
    brief_errors = []
    if args.brief_constraints:
        if not args.brief_constraints.is_file():
            brief_errors = [f"file does not exist: {args.brief_constraints}"]
        else:
            try:
                brief_document = load_json(args.brief_constraints)
                brief_errors = validate_brief_document(brief_document, args.competition, profile)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                brief_errors = [str(exc)]
    brief_required = bool(profile.get("brief_constraints_required"))
    if args.real_submission and profile.get("brief_constraints_required_for_real_submission"):
        brief_required = True
    brief_missing = brief_required and brief_document is None
    checks.append(check("brief-constraints", not brief_missing and not brief_errors, {
        "required": brief_required,
        "provided": args.brief_constraints is not None,
        "errors": brief_errors,
    }, "error" if brief_required or brief_errors else "warning"))

    length_rule = profile.get("default_length")
    if brief_document and not brief_errors:
        allowed_by_brief = args.subtype in brief_document["allowed_subtypes"]
        checks.append(check("subtype-allowed-by-brief", allowed_by_brief, {
            "selected": args.subtype, "allowed": brief_document["allowed_subtypes"],
        }))
        if allowed_by_brief:
            length_rule = brief_document["subtype_constraints"].get(args.subtype)
        length_status = brief_document.get("length_status", "specified")
        if length_status == "conflict":
            checks.append(check(
                "length-constraint-status", False,
                {"status": length_status, "action": "resolve conflicting official rules"},
            ))
        elif length_status == "not-specified":
            checks.append(check(
                "length-unspecified-by-brief", False,
                {"status": length_status, "action": "continue without a length gate; recheck before real submission"},
                "warning",
            ))
        else:
            checks.append(check("length-constraint-status", True, {"status": length_status}))
        for term in brief_document.get("required_terms", []):
            checks.append(check(f"required-term:{term}", term in normalized, term))
        for index, group in enumerate(brief_document.get("required_any_groups", []), start=1):
            matches = [term for term in group if term in normalized]
            checks.append(check(f"required-any-group:{index}", bool(matches), {"group": group, "matches": matches}))
        for term in brief_document.get("prohibited_terms", []):
            checks.append(check(f"prohibited-term:{term}", term not in normalized, term))

    emoji_found = sorted({char for char in normalized if is_emoji(char)})
    emoji_policy = profile["emoji"]
    if brief_document and not brief_errors:
        override = brief_document.get("emoji_policy", "inherit")
        if override != "inherit":
            emoji_policy = override
    if emoji_policy == "allowed":
        checks.append(check("emoji", True, {"policy": emoji_policy, "found": emoji_found}))
    else:
        emoji_severity = "error" if emoji_policy == "forbidden" else "warning"
        checks.append(check("emoji", not emoji_found, {"policy": emoji_policy, "found": emoji_found}, emoji_severity))

    if length_rule:
        minimum = length_rule.get("minimum")
        maximum = length_rule.get("maximum")
        count_value = metrics["content_character_count"]
        if minimum is not None:
            checks.append(check("minimum-length", count_value >= minimum, {"actual": count_value, "minimum": minimum}))
        if maximum is not None:
            checks.append(check("maximum-length", count_value <= maximum, {"actual": count_value, "maximum": maximum}))

    if args.aigc_used == "yes":
        record_present = bool(args.aigc_record and args.aigc_record.is_file() and args.aigc_record.stat().st_size > 0)
        checks.append(check("aigc-record-present", record_present, str(args.aigc_record) if args.aigc_record else None))
    elif args.aigc_used == "unknown":
        checks.append(check("aigc-use-declared", False, "Declare yes or no before final delivery", "warning"))
    else:
        checks.append(check("aigc-use-declared", True, "no"))

    failed_errors = [item for item in checks if not item["passed"] and item["severity"] == "error"]
    failed_warnings = [item for item in checks if not item["passed"] and item["severity"] == "warning"]
    if brief_missing or brief_errors:
        technical_status = "needs_brief_constraint" if brief_required else ("fail" if brief_errors else "pass")
    else:
        technical_status = "fail" if failed_errors else "pass"

    if args.real_submission:
        rule_status, rule_evidence = validate_rule_verification(args.rule_verification, args.competition, profile)
    else:
        rule_status = profile["publication_status"]
        rule_evidence = {"source_url": profile["source_url"], "checked_at": profile["checked_at"]}

    claim_status = brief_document.get("claim_review_status", "pending") if brief_document else "pending"
    content_review_status = "blocked" if claim_status == "blocked" else "requires-human-review"
    payload = {
        "schema_version": "0.1.0",
        "competition": args.competition,
        "subtype": args.subtype,
        "profile_snapshot": profile["snapshot"],
        "input": {
            "path": str(args.input.resolve()),
            "bytes": args.input.stat().st_size,
            "sha256": sha256(args.input),
        },
        "count_contract": contract,
        "text_metrics": metrics,
        "technical_validation_status": technical_status,
        "rule_snapshot_status": rule_status,
        "rule_evidence": rule_evidence,
        "content_review_status": content_review_status,
        "claim_review_status": claim_status,
        "brief_subtype_basis": brief_document.get("subtype_basis") if brief_document else None,
        "brief_length_status": brief_document.get("length_status") if brief_document else None,
        "checks_total": len(checks),
        "checks_passed": sum(item["passed"] for item in checks),
        "error_failures": [item["name"] for item in failed_errors],
        "warnings": [item["name"] for item in failed_warnings],
        "checks": checks,
        "submission_ready": False,
        "submission_ready_reason": (
            "Technical text checks do not prove semantic compliance, factual support, originality, rights, "
            "the official platform count, current registration fields, or an actual submission."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_keys = (
        "technical_validation_status", "rule_snapshot_status", "content_review_status",
        "checks_total", "checks_passed", "error_failures", "warnings",
    )
    print(json.dumps({key: payload[key] for key in summary_keys}, ensure_ascii=False))
    return 0 if technical_status == "pass" and (not args.real_submission or rule_status == "current") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
