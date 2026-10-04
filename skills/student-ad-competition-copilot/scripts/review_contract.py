"""Version-bound review evidence. Validates records, not human identity or taste."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

CURRENT_MANIFEST = "0.4.0"
STATES = {"pass": "pass", "passed": "pass", "pending": "pending", "not-run": "pending",
          "pending-human-review": "pending", "fail": "fail", "failed": "fail",
          "pass-with-boundaries": "bounded", "passed-with-boundaries": "bounded"}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def inside(root, relative):
    if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute():
        raise ValueError("Expected a nonempty run-relative path")
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("Path escapes run directory")
    return path


def load(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Decision time must include timezone; do not invent missing historical times")
    return parsed


def bound_file(root, ref):
    if not isinstance(ref, dict):
        raise ValueError("Expected path and SHA-256 reference")
    path = inside(root, ref.get("path"))
    if not path.is_file() or digest(path) != ref.get("sha256"):
        raise ValueError(f"Missing or changed evidence: {ref.get('path')}")
    return path


def artifact(root, ref):
    path = bound_file(root, ref)
    units = ref.get("units")
    if (not isinstance(ref.get("version"), str) or not ref["version"].strip()
            or not isinstance(units, list) or not units
            or not all(isinstance(u, str) and u.strip() for u in units)
            or len(set(units)) != len(units)):
        raise ValueError("Artifacts need a version and explicit unique review units")
    return {(str(path), ref["sha256"], ref["version"], unit) for unit in units}


def coverage(root, refs):
    if not isinstance(refs, list) or not refs:
        raise ValueError("Explicit reviewed artifacts are required")
    result = set()
    for ref in refs:
        keys = artifact(root, ref)
        if result & keys:
            raise ValueError("Duplicate review units")
        result |= keys
    return result


def human_source(root, ref, quote):
    source = load(bound_file(root, ref))
    if (source.get("actor_type") != "human" or source.get("kind") not in {"user-message", "human-review"}
            or not isinstance(source.get("event_id"), str) or not source["event_id"].strip()
            or not isinstance(source.get("text"), str) or not isinstance(quote, str)
            or not quote.strip() or quote not in source["text"]):
        raise ValueError("A traceable human source and exact quotation are required; simulations do not qualify")
    at = timestamp(source.get("occurred_at"))
    basis = source.get('time_basis')
    if basis is not None:
        if basis not in {'message', 'turn', 'review-event'}:
            raise ValueError('Unknown human-source time basis')
        if basis == 'turn':
            if not isinstance(source.get('turn_id'), str) or not source['turn_id'].strip() or timestamp(source.get('turn_started_at')) != at:
                raise ValueError('Turn time needs its real turn ID and matching started_at')
        elif basis == 'review-event' and source.get('kind') != 'human-review':
            raise ValueError('A review-event time must belong to a human-review event')
        elif basis == 'message' and source.get('message_sent_at') is not None and timestamp(source['message_sent_at']) != at:
            raise ValueError('Message send time differs from source time')
    return at


def decisions(root, contract):
    rows = contract.get("decisions")
    if not isinstance(rows, list):
        raise ValueError("decisions must be a list")
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip() or row["id"] in by_id:
            raise ValueError("Decisions need unique nonempty IDs")
        at = timestamp(row.get("checked_at"))
        if at > datetime.now(timezone.utc):
            raise ValueError("Future decisions cannot authorize work")
        if human_source(root, row.get("source"), row.get("quote")) != at:
            raise ValueError("Decision time differs from original source time")
        if row.get("stage") not in {"direction", "representative", "final", "production-authorization"} or row.get("decision") not in {"pass", "reject"}:
            raise ValueError("Unknown decision stage or verdict")
        coverage(root, row.get("reviewed_artifacts"))
        by_id[row["id"]] = row
    return by_id


def latest(rows):
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: timestamp(r["checked_at"]))
    if len(rows) > 1 and timestamp(rows[-1]["checked_at"]) == timestamp(rows[-2]["checked_at"]):
        raise ValueError("Ambiguous simultaneous decisions; reconcile the source records")
    return rows[-1]


def final_state(root, refs, rows):
    required = coverage(root, refs)
    reviewed = [(r, coverage(root, r["reviewed_artifacts"]))
                for r in rows.values() if r["stage"] == "final"]
    decision_ids = set()
    pending = False
    failed = False
    for key in required:
        row = latest([r for r, keys in reviewed if key in keys])
        if row is None:
            pending = True
        else:
            decision_ids.add(row["id"])
            failed |= row["decision"] == "reject"
    return ("fail" if failed else "pending" if pending else "pass"), decision_ids


def request_decision(root, ref, rows):
    request = load(bound_file(root, ref))
    if not isinstance(request.get("id"), str) or not request["id"].strip() or not request.get("operation"):
        raise ValueError("Production request needs an ID and operation")
    scope = request.get("output_scope")
    if not isinstance(scope, list) or not scope or not all(isinstance(s, str) and s.strip() for s in scope) or len(set(scope)) != len(scope):
        raise ValueError("Production output scope must be explicit")
    needed = coverage(root, request.get("representatives"))
    rows = [r for r in rows.values() if r.get("production_request_sha256") == ref["sha256"]
            and r["stage"] in {"representative", "production-authorization"}]
    row = latest(rows)
    if row is None or row["decision"] != "pass" or not needed <= coverage(root, row["reviewed_artifacts"]):
        raise ValueError("Production is blocked: no current approval or explicit production authorization for this request")
    return request, row


def read_contract(root, manifest):
    if manifest.get("schema_version") != CURRENT_MANIFEST:
        raise ValueError("Legacy manifest: preserve historical results; migrate evidence explicitly before using the new contract")
    contract = load(inside(root, manifest.get("review_contract")))
    if (contract.get("schema_version") != "1.0.0" or contract.get("run_id") != manifest.get("run_id")
            or contract.get("track") != manifest.get("category")):
        raise ValueError("Review contract identity mismatch")
    if (contract.get("content_status") not in {"pending", "pass", "fail"}
            or any(not isinstance(contract.get(k), list) for k in
                   ("production_requests", "production_receipts", "final_artifacts"))):
        raise ValueError("Review contract needs explicit status and artifact/request/receipt lists")
    if not contract["final_artifacts"] and contract["content_status"] != "pending":
        raise ValueError("No final scope exists to support a content verdict")
    return contract, decisions(root, contract)


def concept_evidence_checks(root, manifest):
    """Check explicit top-level concept-gate evidence refs; no recursive history rewrite."""
    if manifest.get('execution_profile') != 'bound-production-v1':
        return []
    relative = manifest.get('artifacts', {}).get('concept_gate')
    if not relative:
        return []
    try:
        document = load(inside(root, relative))
        evidence = document.get('evidence', [])
        refs = [r for r in evidence if isinstance(r, dict) and 'path' in r and 'sha256' in r] if isinstance(evidence, list) else []
        for ref in refs:
            bound_file(root, ref)
        return [dict(name='concept-evidence-bindings', passed=True, evidence=dict(explicit_refs_checked=len(refs)))]
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        return [dict(name='concept-evidence-bindings', passed=False, evidence=str(exc))]


def validate_request_inputs(root, request):
    """Optional byte bindings protect local scripts and scoped brand assets.

    These checks cannot detect undeclared inputs or authenticate the supplied
    scope evidence. Historical requests without these fields remain readable.
    """
    inputs = request.get('input_files', [])
    if not isinstance(inputs, list):
        raise ValueError('input_files must be a list of bound files')
    for ref in inputs:
        bound_file(root, ref)
    if 'asset_scope' not in request:
        return
    scope = request['asset_scope']
    if not isinstance(scope, dict):
        raise ValueError('asset_scope must be a scope record')
    bound_file(root, scope.get('basis'))
    allowed, used = scope.get('allowed_assets'), scope.get('used_origins')
    if not isinstance(allowed, list) or not isinstance(used, list):
        raise ValueError('Asset scope needs allowed_assets and used_origins lists')
    allowed_hashes = {ref['sha256'] for ref in allowed if bound_file(root, ref)}
    for ref in used:
        bound_file(root, ref)
        if ref['sha256'] not in allowed_hashes:
            raise ValueError('Used brand asset is outside the bound allowed asset set')


def preflight(root, manifest, request_id, *, for_dispatch=False):
    contract, rows = read_contract(root, manifest)
    if request_id in cancelled_requests(root, contract):
        raise ValueError("Production request was cancelled before execution; create a new request to resume")
    matches = []
    for ref in contract.get("production_requests", []):
        request = load(bound_file(root, ref))
        if request.get("id") == request_id:
            matches.append(ref)
    if len(matches) != 1:
        raise ValueError("Production request ID must resolve exactly once")
    request, row = request_decision(root, matches[0], rows)
    validate_request_inputs(root, request)
    control = None
    if for_dispatch:
        from execution_contract import dispatch_inputs, validate_events
        events = validate_events(root, contract)
        if matches[0]['sha256'] in events:
            raise ValueError('Production already started; resume its actual call, do not dispatch again')
        for receipt_ref in contract['production_receipts']:
            existing = load(bound_file(root, receipt_ref))
            if existing.get('request_sha256') == matches[0]['sha256'] and existing.get('action_started_at'):
                raise ValueError('Production already started; use a new request for an authorized retry')
        control = dispatch_inputs(root, manifest, contract, request)
    return {"schema_version": "1.0.0", "run_id": manifest["run_id"], "status": "authorized",
            "request_id": request_id, "request_sha256": matches[0]["sha256"],
            "decision_id": row["id"], "decision_sha256": fingerprint(row),
            "authorization_kind": row["stage"], "checked_at": datetime.now(timezone.utc).isoformat(),
            "content_pass_granted": False, "dispatch_checked": for_dispatch,
            "execution_control": control, "request": request}


def cancelled_requests(root, contract):
    """Keep an unexecuted request and its reason without inventing a production receipt."""
    cancelled = {}
    requests = {ref['sha256']: load(bound_file(root, ref)) for ref in contract['production_requests']}
    receipts = [load(bound_file(root, ref)) for ref in contract['production_receipts']]
    refs = contract.get('production_cancellations', [])
    from execution_contract import validate_events
    started_events = validate_events(root, contract)
    if not isinstance(refs, list):
        raise ValueError("Production cancellations must be bound records")
    for ref in refs:
        record = load(bound_file(root, ref))
        request = requests.get(record.get('request_sha256'))
        if (not request or record.get('request_id') != request.get('id')
                or record.get('executed') is not False
                or not isinstance(record.get('reason'), str) or not record['reason'].strip()
                or timestamp(record.get('cancelled_at')) > datetime.now(timezone.utc)):
            raise ValueError("Cancellation needs a matching unexecuted request, reason and actual time")
        if request['id'] in cancelled:
            raise ValueError("Duplicate production cancellation")
        if record['request_sha256'] in started_events:
            raise ValueError('Started external production cannot be cancelled before execution')
        if any(r.get('request_sha256') == record['request_sha256'] and
               (r.get('executed') is True or r.get('action_started_at') or
                r.get('production_state') in {'running', 'completed', 'failed'}) for r in receipts):
            raise ValueError("Started production cannot be classified as cancelled before execution")
        cancelled[request['id']] = record
    return cancelled


def validate_receipts(root, contract, rows):
    requests = contract.get("production_requests")
    receipts = contract.get("production_receipts")
    if not isinstance(requests, list) or not requests or not isinstance(receipts, list):
        raise ValueError("Production/delivery requires requests and preproduction receipts")
    parsed = [load(bound_file(root, ref)) for ref in receipts]
    from execution_contract import PROFILE, validate_events
    events = validate_events(root, contract)
    cancelled = cancelled_requests(root, contract)
    ids = []
    for ref in requests:
        request = load(bound_file(root, ref))
        ids.append(request["id"])
        if request['id'] in cancelled:
            continue
        # Verify the original decision, not a later final approval; a later
        # rejection affects current content state without rewriting history.
        matching = [r for r in parsed if r.get("request_sha256") == ref["sha256"] and r.get("request_id") == request["id"]]
        if not matching:
            raise ValueError("Missing preproduction receipt")
        valid = False
        for receipt in matching:
            row = rows.get(receipt.get("decision_id"))
            if (not row or row["stage"] not in {"representative", "production-authorization"}
                    or row["decision"] != "pass" or row.get("production_request_sha256") != ref["sha256"]):
                continue
            at = timestamp(receipt.get("checked_at"))
            if at > datetime.now(timezone.utc):
                continue
            eligible = {k: v for k, v in rows.items() if timestamp(v["checked_at"]) <= at}
            try:
                _, original = request_decision(root, ref, eligible)
            except ValueError:
                continue
            valid |= (original["id"] == row["id"] and receipt.get("status") == "authorized"
                      and receipt.get("run_id") == contract["run_id"]
                      and receipt.get("content_pass_granted") is False
                      and receipt.get("decision_sha256") == fingerprint(row))
        if not valid:
            raise ValueError("Receipt is stale, precedes approval, or does not bind the production inputs")
        if request.get('execution_profile') == PROFILE:
            if not any(r.get('dispatch_checked') is True for r in matching):
                raise ValueError('New production needs dispatch-time checks, not a historical authorization check')
            if request.get('operation') == 'local':
                finished = [r for r in matching if r.get('production_state') in {'completed', 'failed'}]
                if not finished:
                    raise ValueError('Local production has not finished')
                for receipt in finished:
                    if receipt['production_state'] == 'completed':
                        if {r['path'] for r in receipt.get('outputs', [])} != set(request['output_files']):
                            raise ValueError('Completed production must bind declared outputs')
                        for output in receipt['outputs']:
                            bound_file(root, output)
            elif events.get(ref['sha256'], {}).get('state') not in {'saved', 'failed'}:
                raise ValueError('External production has no finished host lifecycle evidence')
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate production request IDs")
    if not set(ids) - set(cancelled):
        raise ValueError("Production/delivery needs an active production request, not only cancellations")


def validate_copy(root, manifest, contract, rows):
    delivery = contract.get("copy_delivery")
    if not isinstance(delivery, dict):
        raise ValueError("Copy delivery must bind slogan/copy, explanation and submission text")
    constraints = load(inside(root, manifest["artifacts"]["brief_constraints"]))
    required = constraints.get("creative_explanation_required")
    if not isinstance(required, bool):
        raise ValueError("Declare creative_explanation_required from the brief before delivery")
    copy_ref = delivery["copy"]
    artifact(root, copy_ref)
    if bound_file(root, copy_ref) != inside(root, manifest["artifacts"]["final_copy"]):
        raise ValueError("Copy delivery differs from manifest final_copy")
    parts = {"copy": bound_file(root, copy_ref).read_text(encoding="utf-8-sig")}
    refs = [copy_ref]
    explanation = delivery.get("explanation")
    if required and explanation is None:
        raise ValueError("Required creative explanation is missing")
    if explanation is not None:
        artifact(root, explanation)
        parts["explanation"] = bound_file(root, explanation).read_text(encoding="utf-8-sig")
        refs.append(explanation)
    layout = delivery.get("submission_layout")
    if not isinstance(layout, list) or not layout:
        raise ValueError("Submission layout must explicitly compose current content")
    used = []
    rendered = []
    for part in layout:
        if isinstance(part, str):
            rendered.append(part)
        elif isinstance(part, dict) and set(part) == {"artifact"} and part["artifact"] in parts:
            used.append(part["artifact"])
            rendered.append(parts[part["artifact"]])
        else:
            raise ValueError("Invalid submission layout component")
    if sorted(used) != sorted(parts):
        raise ValueError("Each final content object must occur exactly once in submission text")
    submission = delivery["submission"]
    artifact(root, submission)
    if bound_file(root, submission).read_text(encoding="utf-8-sig") != "".join(rendered):
        raise ValueError("Submission text does not exactly match the current copy and explanation")
    refs.append(submission)
    if coverage(root, refs) != coverage(root, contract.get("final_artifacts")):
        raise ValueError("Final review scope must cover copy, explanation (if present), and submission text")
    stable = contract.get("stable_copy")
    if manifest.get("revision_mode", "initial") == "challenge" and not stable:
        raise ValueError("Challenge mode requires an approved stable baseline")
    if stable:
        baseline = stable["artifact"]
        keys = artifact(root, baseline)
        decision = rows.get(stable.get("decision_id"))
        if not decision or decision["stage"] == "production-authorization" or decision["decision"] != "pass" or not keys <= coverage(root, decision["reviewed_artifacts"]):
            raise ValueError("Stable baseline is not bound to human content approval")
        if manifest.get("subtype") in {"slogan", "short-copy"}:
            snapshot = load(bound_file(root, stable.get("prosody_snapshot")))
            if snapshot.get("copy_sha256") != baseline["sha256"] or not all(snapshot.get(k) for k in ("syllables", "pauses", "stresses", "rhyme", "reading_evidence")):
                raise ValueError("Approved prosody snapshot must describe this exact baseline")
            bound_file(root, snapshot["reading_evidence"])
        feedback_ids = set()
        for feedback in stable.get("resolved_feedback", []):
            if feedback.get("id") in feedback_ids or not feedback.get("id"):
                raise ValueError("Resolved feedback needs unique IDs")
            feedback_ids.add(feedback["id"])
            human_source(root, feedback.get("source"), feedback.get("quote"))
            artifact(root, feedback.get("affected_artifact"))
            if (feedback.get("resolved_sha256") != baseline["sha256"]
                    or feedback.get("resolution_decision_id") != decision["id"]
                    or not feedback.get("layer") or not feedback.get("reopen_trigger")):
                raise ValueError("Feedback resolution must bind affected version/layer, approved fix and reopening trigger")
        if copy_ref["sha256"] != baseline["sha256"]:
            challenge = contract.get("challenge", {})
            if challenge.get("baseline_sha256") != baseline["sha256"] or challenge.get("trigger_kind") not in {"observed-failure", "explicit-user-change", "award-ceiling-review"}:
                raise ValueError("A new copy cannot silently replace the approved baseline")
            bound_file(root, challenge.get("trigger_evidence"))
            comparison = load(bound_file(root, challenge.get("comparison")))
            if (comparison.get("baseline_sha256") != baseline["sha256"] or comparison.get("challenger_sha256") != copy_ref["sha256"]
                    or not all(comparison.get(k) for k in ("clarity_delta", "mechanism_delta", "brand_delta", "voice_delta", "explanation_cost_delta"))):
                raise ValueError("Compare the exact baseline and challenger before replacement")
            replacement = rows.get(challenge.get("replacement_decision_id"))
            if (not replacement or replacement["stage"] != "final" or replacement["decision"] != "pass"
                    or not artifact(root, copy_ref) <= coverage(root, replacement["reviewed_artifacts"])
                    or timestamp(replacement["checked_at"]) <= timestamp(decision["checked_at"])):
                raise ValueError("Replacing approved copy requires a later exact-version human decision")


def validate_review_contract(root, manifest):
    root = root.resolve()
    checks = []
    if manifest.get("schema_version") != CURRENT_MANIFEST:
        return [{"name": "review-contract-current", "passed": False,
                 "evidence": "Legacy record remains readable but does not satisfy the v0.2.5 review contract; never backfill approval."}]
    try:
        contract, rows = read_contract(root, manifest)
        if manifest.get("run_scope") in {"production-candidate", "delivery-candidate"}:
            validate_receipts(root, contract, rows)
        if manifest.get("run_scope") == "delivery-candidate":
            refs = contract.get("final_artifacts")
            state, ids = final_state(root, refs, rows)
            if contract.get("content_status") != state:
                raise ValueError(f"Declared content status conflicts with exact-version decisions: {state}")
            status = load(inside(root, manifest["artifacts"]["run_status"]))
            if STATES.get(status.get("content_review_status")) != state or set(status.get("review_decision_ids", [])) != ids:
                raise ValueError("Run status and human decision scope disagree")
            if manifest["category"] == "ad-copy":
                validate_copy(root, manifest, contract, rows)
                candidate = load(inside(root, manifest["artifacts"]["candidate_review"]))
                review = candidate["manual_content_review"]
                if "status" in candidate and STATES.get(candidate["status"]) != state:
                    raise ValueError("Candidate review summary conflicts with the current content verdict")
                if STATES.get(review.get("status")) != state or set(review.get("review_decision_ids", [])) != ids:
                    raise ValueError("Candidate review still has pending/bounded or different-scope content")
                if state == "pass" and review.get("boundaries"):
                    raise ValueError("Resolve or separately scope candidate content boundaries before unconditional pass")
            elif manifest["category"] == "marketing-plan":
                final = manifest.get("final_artifact", {})
                if not any(inside(root, r["path"]) == inside(root, final.get("path")) and r["sha256"] == final.get("sha256") for r in refs):
                    raise ValueError("Reviewed deck differs from manifest final_artifact")
                required_pages = {str(i) for i in range(1, final.get("slide_count", 0) + 1)}
                pages = {u for r in refs if inside(root, r["path"]) == inside(root, final.get("path")) for u in r["units"]}
                if not required_pages or pages != required_pages:
                    raise ValueError("Whole-deck approval cannot be inferred from sample pages")
            elif manifest["category"] == "print-ad":
                delivery = load(inside(root, manifest["artifacts"]["delivery_manifest"]))
                if coverage(root, delivery.get("final_artifacts")) != coverage(root, refs):
                    raise ValueError("Reviewed print series differs from the actual delivery manifest")
                from current_artwork_contract import validate_current
                validate_current(root, manifest, contract)
            # Gate declarations cannot override pending or rejected content.
            gates = load(inside(root, manifest["artifacts"]["quality_gate_results"]))
            definitions = load(Path(__file__).resolve().parents[1] / "references/tracks" / manifest["category"] / "quality-gates.json")
            human_ids = {g["gate_id"] for g in definitions["gates"] if g["gate_type"] in {"human", "hybrid"}}
            if state != "pass" and any(r["gate_id"] in human_ids and r.get("status") in {"pass", "pass-with-boundaries"} for r in gates["results"] if r["gate_id"].endswith(("human-visual-quality", "full-deck-human-quality", "semantic-brand", "subtype-quality"))):
                raise ValueError("Internal quality pass cannot override current human pending/rejection")
        checks.append({"name": "review-contract-current", "passed": True, "evidence": "Bound evidence, authorization history and declared scope checked; human identity and aesthetics are not machine-proven."})
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        checks.append({"name": "review-contract-current", "passed": False, "evidence": str(exc)})
    return checks
