#!/usr/bin/env python3
"""Query the bundled, principle-only competition knowledge pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
from knowledge_pack_contract import jsonl_rows, validate_pack


KINDS = {
    "method": "method-cards.jsonl",
    "case": "case-cards.jsonl",
    "failure": "failure-patterns.jsonl",
    "compliance": "compliance-boundaries.jsonl",
}
SEARCHABLE_METHOD_STATUSES = {
    "supported-by-independent-sources",
    "supported-by-eligible-cases",
    "supported-by-independent-sources-and-eligible-cases",
}
RISK_POLICY = {
    "levels": ["consider", "return-on-observed-failure", "hard-stop"],
    "diagnostic_default": "consider",
    "diagnostic_effect": "Preserve the creative choice and run a proportionate check; do not treat a possible risk as a style ban or automatic downgrade.",
    "return_trigger": "Use only after a target-size, three-second, brand-replacement, prototype, factual, or human review records a concrete failure.",
    "hard_stop_trigger": "Use only when current official rules, identity, key factual claims, rights, required fidelity assets, or an explicit quality gate blocks the affected step.",
}


def searchable_text(value) -> str:
    if isinstance(value, dict):
        return " ".join(searchable_text(child) for child in value.values())
    if isinstance(value, list):
        return " ".join(searchable_text(child) for child in value)
    return str(value or "")


def query_terms(text: str, vocabulary=()) -> list[str]:
    """Lexical candidates, not semantic segmentation; preserve original phrases."""
    terms = [value.lower() for value in re.findall(r"[\w\u3400-\u9fff]+", text) if value.strip()]
    lower = text.lower()
    terms.extend(word.lower() for word in vocabulary if len(word) >= 2 and word.lower() in lower)
    return sorted(set(terms))


METHOD_FIELDS = {'name': 8, 'aliases': 8, 'problem': 5, 'mechanism': 4, 'steps': 1}


def match_details(row: dict, terms: list[str]) -> list[dict]:
    if not row.get('method_id'):
        return [{'field': 'record', 'term': term, 'weight': 3}
                for term in terms if term in searchable_text(row).lower()]
    return [{'field': field, 'term': term, 'weight': weight}
            for field, weight in METHOD_FIELDS.items()
            for term in terms if term in searchable_text(row.get(field, '')).lower()]


def score(row: dict, terms: list[str]) -> int:
    if not terms:
        return int(row.get("occurrence_count", 1))
    matches = match_details(row, terms)
    return sum(max(m['weight'] for m in matches if m['term'] == term)
               for term in {m['term'] for m in matches})


def in_scope(row: dict, competition: str | None, category: str | None) -> bool:
    if row.get("method_id"):
        scope = row.get("scope", {})
        if competition and competition not in scope.get("competitions", []):
            return False
        if category and category not in scope.get("categories", []):
            return False
        return True
    if competition:
        source_competition = row.get("competition")
        applicable_competitions = row.get("applicable_competitions", [])
        if source_competition not in {None, competition} and competition not in applicable_competitions:
            return False
    categories = row.get("categories")
    if category and isinstance(categories, list) and categories and category not in categories:
        return False
    if category and row.get("category") not in {None, category}:
        return False
    return True


def runtime_view(kind: str, row: dict, full: bool) -> dict:
    if full or kind != "method":
        return row
    validation = row.get("validation", {})
    return {
        "schema_version": row.get("schema_version"),
        "method_id": row.get("method_id"),
        "name": row.get("name"),
        "aliases": row.get("aliases", []),
        "family": row.get("family"),
        "scope": row.get("scope", {}),
        "problem": row.get("problem"),
        "mechanism": row.get("mechanism"),
        "steps": row.get("steps", []),
        "diagnostic_signals": row.get("diagnostic_signals", []),
        "anti_signals": row.get("anti_signals", []),
        "failure_modes": row.get("failure_modes", []),
        "transfer": row.get("transfer", {}),
        "evidence_status": row.get("evidence_status"),
        "method_evidence_maturity": row.get("method_evidence_maturity"),
        "effectiveness_boundary": row.get("effectiveness_boundary"),
        "source_evidence": row.get("source_evidence", []),
        "evidence_projection": row.get("evidence_projection", {}),
        "validation": {
            key: validation.get(key)
            for key in ("status", "evidence_basis", "corpus_cases_checked", "machine_cases_checked", "human_reviewed_cases_checked", "human_reviewed")
            if key in validation
        },
    }


def eligible_for_runtime(kind: str, row: dict, eligibility: dict) -> bool:
    if kind == "method":
        return row.get("evidence_status") in SEARCHABLE_METHOD_STATUSES
    if kind == "case":
        return row.get("case_id") in set(eligibility.get("approved_runtime_case_ids", []))
    return row.get("evidence_status") in {"eligible-case-derived", "independent-runtime-policy"}


def risk_level(kind: str) -> str:
    return "evidence-boundary" if kind == "compliance" else "consider"


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, help="Explicit candidate pack; omission resolves version.json")
    parser.add_argument("--kind", choices=["all", *KINDS], default="all")
    parser.add_argument("--competition", choices=["daguangsai", "academy-award"])
    parser.add_argument("--category", choices=["print-ad", "ad-copy", "marketing-plan"])
    parser.add_argument("--query", default="")
    parser.add_argument("--term", action="append", default=[], help="Explicit lexical keyword; repeat as needed while preserving the original --problem")
    parser.add_argument("--problem", default="")
    parser.add_argument("--mechanism", default="")
    parser.add_argument("--risk", default="")
    parser.add_argument("--reference-role")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--full", action="store_true", help="Include complete method evidence arrays")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("limit must be between 1 and 100")

    integrity = validate_pack(args.pack)
    if args.self_check:
        print(json.dumps(integrity, ensure_ascii=False))
        return 0 if integrity["status"] == "passed" else 1
    if integrity["status"] != "passed":
        raise SystemExit("Knowledge pack integrity check failed: " + "; ".join(integrity["errors"]))

    pack = Path(integrity["pack"])
    eligibility_path = pack / "eligibility.json"
    if not eligibility_path.is_file():
        raise SystemExit("Knowledge pack has no eligible-evidence projection; historical packs may be validated but cannot be queried by this candidate runtime.")
    eligibility = json.loads(eligibility_path.read_text(encoding="utf-8-sig"))
    original_query = " ".join([args.query, args.problem, args.mechanism, args.risk])
    # Discover names/aliases only from eligible methods in this scope.
    vocabulary = []
    for row in jsonl_rows(pack / KINDS['method']):
        if eligible_for_runtime('method', row, eligibility) and in_scope(row, args.competition, args.category):
            vocabulary.extend([row.get('name', ''), *row.get('aliases', [])])
    terms = query_terms(original_query + ' ' + ' '.join(args.term), vocabulary)
    selected_kinds = list(KINDS) if args.kind == "all" else [args.kind]
    candidates = []
    excluded_before_matching = {kind: 0 for kind in selected_kinds}
    for kind in selected_kinds:
        for row in jsonl_rows(pack / KINDS[kind]):
            if not eligible_for_runtime(kind, row, eligibility):
                excluded_before_matching[kind] += 1
                continue
            if not in_scope(row, args.competition, args.category):
                continue
            if args.reference_role and row.get("reference_role") != args.reference_role:
                continue
            item_score = score(row, terms)
            if terms and item_score == 0:
                continue
            candidates.append({"kind": kind, "score": item_score, "record": row})
    candidates.sort(key=lambda item: (-item["score"], item["kind"], searchable_text(item["record"])))
    payload = {
        "execution": {
            "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            "cwd": str(Path.cwd()), "pack": str(pack.resolve()),
            "pack_manifest_sha256": hashlib.sha256((pack / 'manifest.json').read_bytes()).hexdigest(),
            "started_at": started_at, "completed_at": datetime.now(timezone.utc).isoformat(),
        },
        "schema_version": "0.2.0",
        "knowledge_pack_version": integrity["knowledge_pack_version"],
        "eligibility": {
            "state_fingerprint": eligibility.get("state_fingerprint"),
            "input_fingerprint": eligibility.get("input_fingerprint"),
            "excluded_before_matching": excluded_before_matching,
        },
        "query": {
            "competition": args.competition,
            "category": args.category,
            "terms": terms,
            "reference_role": args.reference_role,
            "original": original_query.strip(),
            "explicit_terms": args.term,
            "matching": "lexical-with-eligible-name-alias-expansion",
        },
        "risk_policy": RISK_POLICY,
        "available_matches": len(candidates),
        "returned": min(len(candidates), args.limit),
        "results": [
            {
                "kind": item["kind"],
                "score": item["score"],
                "match_details": match_details(item['record'], terms),
                "risk_level": risk_level(item["kind"]),
                "record": runtime_view(item["kind"], item["record"], args.full),
            }
            for item in candidates[: args.limit]
        ],
        "empty_reason": None if candidates else "No eligible bundled knowledge matched; quarantined and unreviewed records were not searched.",
        "effectiveness_boundary": "Scores rank positive lexical matches, not applicability or creative quality. Source/validation/negative-only mentions do not recommend a method. If empty, extract explicit keywords from the original problem or acknowledge a knowledge gap; do not replace the problem with a preferred technique.",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
