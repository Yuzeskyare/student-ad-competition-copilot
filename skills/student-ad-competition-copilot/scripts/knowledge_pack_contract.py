"""Resolve and validate the one active or explicitly selected knowledge pack."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

SKILL_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = SKILL_ROOT / "version.json"
SUPPORTED_MANIFEST_SCHEMAS = {"0.1.2", "0.2.0"}
BASE_REQUIRED_FILES = {
    "case-cards.jsonl": "case_id",
    "compliance-boundaries.jsonl": "pattern_id",
    "failure-patterns.jsonl": "pattern_id",
    "method-cards.jsonl": "method_id",
    "taxonomy.json": None,
}
PROJECTED_REQUIRED_FILES = {**BASE_REQUIRED_FILES, "eligibility.json": None}

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def jsonl_rows(path: Path) -> list[dict]:
    values = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected object at {path}:{line_number}")
        values.append(value)
    return values

def _safe_skill_path(relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("version.json knowledge_manifest.path must be a non-empty string")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative or ":" in relative:
        raise ValueError("version.json knowledge manifest path must be a safe relative POSIX path")
    path = (SKILL_ROOT / Path(*posix.parts)).resolve()
    if path != SKILL_ROOT and SKILL_ROOT not in path.parents:
        raise ValueError("version.json knowledge manifest path escapes the Skill")
    return path

def resolve_pack(explicit_pack: Path | None = None) -> dict:
    if explicit_pack is not None:
        pack = explicit_pack.resolve()
        manifest_path = pack / "manifest.json"
        source = "explicit"
        expected_manifest_sha256 = None
    else:
        version = read_json(VERSION_FILE)
        pointer = version.get("knowledge_manifest")
        if not isinstance(pointer, dict):
            raise ValueError("version.json knowledge_manifest object is missing")
        manifest_path = _safe_skill_path(pointer.get("path"))
        pack = manifest_path.parent
        source = "version.json"
        expected_manifest_sha256 = pointer.get("sha256")
        if not isinstance(expected_manifest_sha256, str) or len(expected_manifest_sha256) != 64:
            raise ValueError("version.json knowledge_manifest.sha256 is invalid")
    if not manifest_path.is_file():
        raise ValueError(f"Knowledge manifest is missing: {manifest_path}")
    actual = sha256(manifest_path)
    if expected_manifest_sha256 is not None and actual != expected_manifest_sha256:
        raise ValueError("Active knowledge manifest hash differs from version.json")
    return {"pack": pack, "manifest_path": manifest_path, "manifest_sha256": actual,
            "resolution_source": source}

def _projection_errors(parsed: dict[str, object], manifest: dict) -> list[str]:
    errors: list[str] = []
    eligibility = parsed.get("eligibility.json")
    if not isinstance(eligibility, dict):
        return ["eligibility.json must contain an object"]
    if eligibility.get("schema_version") != "1.0.0":
        errors.append("unsupported eligibility schema_version")
    if len(eligibility.get("source_inventory_sha256", "")) != 64:
        errors.append("eligibility.source_inventory_sha256 is invalid")
    if "source_hashes" in eligibility or "state_source_hashes" in eligibility:
        errors.append("eligibility.json must not distribute project source path inventories")
    for key in ("open_annotation_ids_sha256", "unclassified_annotation_ids_sha256"):
        if len(eligibility.get(key, "")) != 64:
            errors.append(f"eligibility.{key} is invalid")
    sets: dict[str, set[str]] = {}
    for key in ("eligible_annotation_case_ids", "approved_runtime_case_ids"):
        values = eligibility.get(key)
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            errors.append(f"eligibility.{key} must be an array of non-empty strings")
            sets[key] = set()
        else:
            sets[key] = set(values)
            if len(sets[key]) != len(values):
                errors.append(f"eligibility.{key} contains duplicates")
    eligible = sets["eligible_annotation_case_ids"]
    counts = eligibility.get("counts", {})
    expected_counts = {
        "eligible_annotations": len(eligible),
        "approved_runtime_cases": len(sets["approved_runtime_case_ids"]),
    }
    for key, value in expected_counts.items():
        if counts.get(key) != value:
            errors.append(f"eligibility.counts.{key} must equal {value}")
    if any(not isinstance(counts.get(key), int) or counts.get(key) < 0 for key in ("annotation_universe", "open_annotations", "unclassified_annotations")):
        errors.append("eligibility annotation counts must be non-negative integers")
    elif counts["annotation_universe"] != counts["eligible_annotations"] + counts["open_annotations"] + counts["unclassified_annotations"]:
        errors.append("eligibility annotation counts do not conserve the universe")
    cases = parsed.get("case-cards.jsonl", [])
    if {row.get("case_id") for row in cases} != sets["approved_runtime_case_ids"]:
        errors.append("approved runtime case IDs differ from case-cards.jsonl")
    allowed_statuses = {
        "supported-by-independent-sources-and-eligible-cases",
        "supported-by-independent-sources",
        "supported-by-eligible-cases",
        "provisional-quarantined",
    }
    methods = parsed.get("method-cards.jsonl", [])
    for row in methods:
        method_id = row.get("method_id")
        status = row.get("evidence_status")
        if status not in allowed_statuses:
            errors.append(f"method has invalid evidence_status: {method_id}")
            continue
        validation = row.get("validation", {})
        case_evidence = validation.get("case_evidence", [])
        case_ids = {item.get("case_id") for item in case_evidence if isinstance(item, dict)}
        if len(case_ids) != len({value for value in case_ids if isinstance(value, str)}) or not case_ids <= eligible:
            errors.append(f"method contains ineligible case evidence: {method_id}")
        sources = row.get("source_evidence", [])
        if not isinstance(sources, list):
            errors.append(f"method source_evidence must be an array: {method_id}")
            sources = []
        for source in sources:
            if not isinstance(source, dict) or not source.get("source_id") or not source.get("title") or not source.get("url") or not source.get("claims"):
                errors.append(f"method contains incomplete source evidence: {method_id}")
        expected_status = (
            "supported-by-independent-sources-and-eligible-cases" if sources and case_evidence else
            "supported-by-independent-sources" if sources else
            "supported-by-eligible-cases" if case_evidence else
            "provisional-quarantined"
        )
        if status != expected_status:
            errors.append(f"method evidence_status disagrees with admitted evidence: {method_id}")
        projection = row.get("evidence_projection", {})
        if projection.get("eligible_case_evidence_entries") != len(case_evidence):
            errors.append(f"method eligible entry count mismatch: {method_id}")
        total = sum(projection.get(key, -10**9) for key in ("eligible_case_evidence_entries", "excluded_open_entries", "excluded_unclassified_entries"))
        if total != projection.get("original_case_evidence_entries"):
            errors.append(f"method evidence conservation failed: {method_id}")
        if projection.get("excluded_evidence_is_searchable") is not False:
            errors.append(f"method excluded evidence search flag is unsafe: {method_id}")
    for name in ("failure-patterns.jsonl", "compliance-boundaries.jsonl"):
        for row in parsed.get(name, []):
            status = row.get("evidence_status")
            if status == "eligible-case-derived":
                if not set(row.get("sample_case_ids", [])) <= eligible:
                    errors.append(f"{name} sample contains ineligible case: {row.get('pattern_id')}")
                if not isinstance(row.get("case_count"), int) or row["case_count"] < 1 or row["case_count"] > len(eligible):
                    errors.append(f"{name} case_count is invalid: {row.get('pattern_id')}")
                if not isinstance(row.get("occurrence_count"), int) or row["occurrence_count"] < row.get("case_count", 0):
                    errors.append(f"{name} occurrence_count is invalid: {row.get('pattern_id')}")
            elif status == "independent-runtime-policy" and name == "compliance-boundaries.jsonl":
                sources = row.get("source_evidence", [])
                if row.get("case_count") != 0 or row.get("sample_case_ids") != [] or row.get("occurrence_count") != 1:
                    errors.append(f"{name} independent policy counts are invalid: {row.get('pattern_id')}")
                if not isinstance(sources, list) or not sources or any(not isinstance(item, dict) or not item.get("source_path") or len(item.get("source_sha256", "")) != 64 or not item.get("source_text") for item in sources):
                    errors.append(f"{name} independent policy source is incomplete: {row.get('pattern_id')}")
                else:
                    for item in sources:
                        try:
                            source_path = _safe_skill_path(item["source_path"])
                            if sha256(source_path) != item["source_sha256"] or item["source_text"] not in source_path.read_text(encoding="utf-8-sig"):
                                errors.append(f"{name} independent policy source drifted: {row.get('pattern_id')}")
                        except (OSError, ValueError):
                            errors.append(f"{name} independent policy source is invalid: {row.get('pattern_id')}")
            else:
                errors.append(f"{name} contains non-eligible evidence status: {row.get('pattern_id')}")
            if row.get("eligibility_state_fingerprint") != eligibility.get("state_fingerprint"):
                errors.append(f"{name} state fingerprint mismatch: {row.get('pattern_id')}")
    source = manifest.get("source_corpus", {})
    if source.get("eligible_annotations") != len(eligible):
        errors.append("source_corpus.eligible_annotations differs from eligibility")
    if source.get("excluded_open_annotations") != counts.get("open_annotations") or source.get("excluded_unclassified_annotations") != counts.get("unclassified_annotations"):
        errors.append("source_corpus exclusion counts differ from eligibility")
    policy = manifest.get("content_policy", {})
    if policy.get("eligibility_state_fingerprint") != eligibility.get("state_fingerprint") or policy.get("eligibility_input_fingerprint") != eligibility.get("input_fingerprint"):
        errors.append("manifest eligibility fingerprints differ from eligibility.json")
    taxonomy = parsed.get("taxonomy.json", {})
    status_counts: dict[str, int] = {}
    for row in methods:
        status_counts[row.get("evidence_status")] = status_counts.get(row.get("evidence_status"), 0) + 1
    if taxonomy.get("method_evidence_statuses") != dict(sorted(status_counts.items())):
        errors.append("taxonomy.method_evidence_statuses differs from actual methods")
    return errors

def validate_pack(explicit_pack: Path | None = None) -> dict:
    errors: list[str] = []
    try:
        resolved = resolve_pack(explicit_pack)
        pack = resolved["pack"]
        manifest = read_json(resolved["manifest_path"])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "failed", "pack": str(explicit_pack) if explicit_pack else None,
                "errors": [str(exc)]}
    manifest_schema = manifest.get("schema_version")
    if manifest_schema not in SUPPORTED_MANIFEST_SCHEMAS:
        errors.append(f"unsupported manifest schema_version: {manifest_schema}")
    required_files = PROJECTED_REQUIRED_FILES if manifest_schema == "0.2.0" else BASE_REQUIRED_FILES
    pack_version = manifest.get("knowledge_pack_version")
    if not isinstance(pack_version, str) or not pack_version.strip():
        errors.append("knowledge_pack_version must be a non-empty string")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        entries = []; errors.append("manifest.files must be an array")
    names = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    if len(names) != len(entries): errors.append("every manifest file entry must be an object with path")
    if len(names) != len(set(names)): errors.append("manifest contains duplicate file paths")
    if set(names) != set(required_files):
        errors.append(f"manifest file set must equal {sorted(required_files)}")
    actual_names = {path.name for path in pack.iterdir() if path.is_file()}
    expected_names = {"manifest.json", *required_files}
    if actual_names != expected_names:
        errors.append(f"pack file set differs: expected {sorted(expected_names)}, actual {sorted(actual_names)}")
    parsed: dict[str, object] = {}; counts: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("path") not in required_files: continue
        name = entry["path"]
        if PurePosixPath(name).name != name or "\\" in name:
            errors.append(f"unsafe manifest path: {name}"); continue
        path = pack / name
        if not path.is_file(): errors.append(f"missing knowledge file: {name}"); continue
        if path.stat().st_size != entry.get("bytes"): errors.append(f"byte count mismatch: {name}")
        if sha256(path) != entry.get("sha256"): errors.append(f"SHA-256 mismatch: {name}")
        try:
            value = jsonl_rows(path) if path.suffix == ".jsonl" else read_json(path)
            parsed[name] = value
            if path.suffix == ".jsonl":
                counts[name] = len(value)
                if entry.get("records") != len(value): errors.append(f"record count mismatch: {name}")
            elif entry.get("records") is not None: errors.append(f"records must be null for {name}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"unreadable {name}: {exc}")
    for name, key in required_files.items():
        if key is None or name not in parsed: continue
        identifiers = [row.get(key) for row in parsed[name]]
        if any(not isinstance(value, str) or not value for value in identifiers):
            errors.append(f"{name} contains missing {key}")
        if len(identifiers) != len(set(identifiers)):
            errors.append(f"{name} contains duplicate {key}")
    methods = parsed.get("method-cards.jsonl", []); cases = parsed.get("case-cards.jsonl", [])
    for row in methods:
        if row.get("validation", {}).get("status") != "candidate":
            errors.append(f"method is not candidate: {row.get('method_id')}")
        if row.get("transfer", {}).get("reuse_level") != "principle-only":
            errors.append(f"method reuse level is not principle-only: {row.get('method_id')}")
    forbidden = {"annotation_file", "evidence_overview", "evidence_units", "local_path", "cache_path"}
    for row in cases:
        if row.get("review_status") != "targeted-semantic-review-passed":
            errors.append(f"case is not targeted-review-passed: {row.get('case_id')}")
        if row.get("generation_use") != "abstract-method-and-risk-only; raw source content prohibited":
            errors.append(f"case generation boundary is unsafe: {row.get('case_id')}")
        if row.get("rights_basis") not in {"analysis-only", "link-only"}:
            errors.append(f"case rights basis is unsafe: {row.get('case_id')}")
        leaked = sorted(forbidden & set(row))
        if leaked: errors.append(f"case contains local-only fields: {row.get('case_id')}: {leaked}")
    source = manifest.get("source_corpus", {}); selection = manifest.get("selection_summary", {})
    universe = source.get("official_case_universe"); annotations = source.get("deep_annotations")
    if not isinstance(universe, int) or universe < 0 or not isinstance(annotations, int) or annotations < 0:
        errors.append("source corpus counts must be non-negative integers")
    equation = source.get("counting_equation")
    try:
        left, right = equation.split("=")
        if sum(int(part.strip()) for part in left.split("+")) != int(right.strip()) or int(right.strip()) != universe:
            errors.append("counting equation does not equal official_case_universe")
    except (AttributeError, TypeError, ValueError): errors.append("counting equation is invalid")
    annotation_records_used = source.get("eligible_annotations") if manifest_schema == "0.2.0" else annotations
    expected = {"annotation_records_used": annotation_records_used, "method_cards_included": len(methods),
        "reviewed_case_cards_included": len(cases),
        "source_cases_without_runtime_case_card": universe-len(cases) if isinstance(universe, int) else None,
        "raw_source_case_records_distributed": 0, "raw_media_files_distributed": 0}
    for key, value in expected.items():
        if selection.get(key) != value: errors.append(f"selection_summary.{key} must equal {value}")
    taxonomy = parsed.get("taxonomy.json")
    if isinstance(taxonomy, dict):
        if taxonomy.get("failure_patterns") != len(parsed.get("failure-patterns.jsonl", [])):
            errors.append("taxonomy.failure_patterns differs from actual records")
        if taxonomy.get("compliance_boundaries") != len(parsed.get("compliance-boundaries.jsonl", [])):
            errors.append("taxonomy.compliance_boundaries differs from actual records")
    if manifest_schema == "0.2.0":
        errors.extend(_projection_errors(parsed, manifest))
    return {"status":"passed" if not errors else "failed", "pack":str(pack),
        "manifest_path":str(resolved["manifest_path"]), "manifest_sha256":resolved["manifest_sha256"],
        "resolution_source":resolved["resolution_source"], "knowledge_pack_version":pack_version,
        "counts":counts, "bytes":sum(e.get("bytes",0) for e in entries if isinstance(e,dict)), "errors":errors}
